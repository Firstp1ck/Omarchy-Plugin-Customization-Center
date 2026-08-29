from __future__ import annotations

import hashlib
import heapq
import json
import os
import secrets
import shutil
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from . import operations as ops
from .atomic import mkdir_durable, write_bytes_atomic
from .backup import BackupStore
from .context import build_context
from .commands import redact
from .errors import CcError
from .journal import Journal
from .locking import ApplyLock, Locked
from .migrate import upgrade
from .types import Operation, OperationResult, Plan, Transaction, VerifyResult


class FaultPlan:
    def __init__(self, hooks: Iterable[str] = ()) -> None:
        self.hooks = set(hooks)
        self.consumed: list[str] = []

    @classmethod
    def from_environment(cls, paths: Any) -> "FaultPlan":
        value = os.environ.get("CC_TEST_FAULTS")
        if not value:
            return cls()
        path = Path(value).absolute()
        home = Path(paths.home).absolute()
        if not path.is_relative_to(home) or not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        hooks = data.get("hooks", data) if isinstance(data, dict) else data
        return cls(str(item) for item in hooks) if isinstance(hooks, list) else cls()

    def hit(self, hook: str) -> None:
        kill_hook = f"kill_process_at:{hook}"
        if kill_hook in self.hooks:
            self.hooks.remove(kill_hook)
            self.consumed.append(kill_hook)
            raise SystemExit(f"fault injection at {hook}")
        if hook in self.hooks:
            self.hooks.remove(hook)
            self.consumed.append(hook)
            raise CcError("verification_failed" if hook == "verification_mismatch" else "internal_error",
                          f"Injected fault at {hook}")


class Executor:
    def __init__(self, plugin_dir: str | Path, registry: Any, paths: Any, ccctl_path: str | Path,
                 *, environ: dict[str, str] | None = None) -> None:
        self.plugin_dir = Path(plugin_dir).absolute()
        self.registry = registry.view if hasattr(registry, "view") else registry
        self.paths = paths
        self.ccctl_path = str(Path(ccctl_path).absolute())
        self.environ = environ
        self.journal = Journal(paths)
        self.backups = BackupStore(paths)
        self.faults = FaultPlan.from_environment(paths)

    def _ctx(self, module_id: str, mode: str) -> Any:
        return build_context(module_id, mode, paths=self.paths, registry=self.registry,
                             plugin_dir=self.plugin_dir, environ=self.environ)

    @staticmethod
    def digest(plan: Plan) -> str:
        document = plan.to_json()
        document["planDigest"] = ""
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()

    def _save(self, tx: Transaction, **changes: Any) -> Transaction:
        state = changes.get("state", tx.state)
        self.faults.hit(f"before_journal_fsync:{state}")
        updated = replace(tx, updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), **changes)
        self.journal.save(updated)
        return updated

    def _extra_paths(self, module_id: str) -> tuple[str, ...]:
        entry = self.registry.entry(module_id)
        return tuple(self.paths.expand_template(item, module_id) for item in entry.metadata.get("extraWritablePaths", []))

    def _validate_plan(self, plan: Plan, confirmations: Iterable[str]) -> None:
        ids: set[str] = set()
        gate_count = 0
        exclusive: dict[str, str] = {}
        for index, operation in enumerate(plan.operations):
            if operation.id in ids:
                raise CcError("unsupported_config", f"Duplicate operation id: {operation.id}")
            ids.add(operation.id)
            try:
                extra = self._extra_paths(operation.module_id)
            except CcError:
                extra = self._extra_paths(plan.module_id)
            ops.validate_operation(operation, self.paths, extra)
            if operation.kind == "TimedConfirmation":
                gate_count += 1
            if operation.kind == "TerminalHandoff" and index != len(plan.operations) - 1:
                raise CcError("unsupported_config", "TerminalHandoff must be the final operation")
        self._validate_inverse_dependencies(plan.operations)
        if gate_count > 1:
            raise CcError("unsupported_config", "A plan may contain at most one TimedConfirmation")
        if gate_count and not self._ctx(plan.module_id, "read").capabilities.get("timed_confirmation").available:
            raise CcError("capability_missing", "Timed confirmation requires systemd-run",
                          {"capability": "timed_confirmation"})
        for claim in plan.claims:
            if claim.access not in {"exclusive", "shared"}:
                raise CcError("unsupported_config", f"Invalid claim access: {claim.access}")
            if claim.access == "exclusive" and claim.key in exclusive:
                raise CcError("resource_conflict", f"Duplicate exclusive claim: {claim.key}",
                              {"key": claim.key, "first": exclusive[claim.key], "second": plan.module_id})
            if claim.access == "exclusive":
                exclusive[claim.key] = plan.module_id
        declared = set(plan.requires_confirmation)
        mandatory = {operation.id for operation in plan.operations if operation.inverse is None}
        mandatory.update(warning.code for warning in plan.warnings if warning.ack)
        undeclared = sorted(mandatory - declared)
        if undeclared:
            raise CcError("unsupported_config", "Plan omitted required confirmation keys",
                          {"missingKeys": undeclared})
        missing = sorted(declared - set(confirmations))
        if missing:
            raise CcError("nonreversible_requires_confirmation", "Confirmation is required for non-reversible changes",
                          {"missingKeys": missing})

    @staticmethod
    def _validate_inverse_dependencies(operations: tuple[Operation, ...]) -> None:
        positions = {operation.id: index for index, operation in enumerate(operations)}
        successors: dict[str, list[str]] = {operation.id: [] for operation in operations}
        for operation in operations:
            if len(set(operation.inverse_after)) != len(operation.inverse_after):
                raise CcError("unsupported_config", f"Operation {operation.id} has duplicate inverseAfter entries")
            for dependency in operation.inverse_after:
                if dependency not in positions:
                    raise CcError("unsupported_config",
                                  f"Operation {operation.id} inverseAfter names missing operation {dependency}")
                successors[dependency].append(operation.id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(operation_id: str) -> None:
            if operation_id in visiting:
                raise CcError("unsupported_config", "Operation inverseAfter dependencies contain a cycle")
            if operation_id in visited:
                return
            visiting.add(operation_id)
            for successor in successors[operation_id]:
                visit(successor)
            visiting.remove(operation_id)
            visited.add(operation_id)

        for operation in operations:
            visit(operation.id)
        for operation in operations:
            for dependency in operation.inverse_after:
                if positions[dependency] >= positions[operation.id]:
                    raise CcError("unsupported_config",
                                  f"Operation {operation.id} inverseAfter must name an earlier operation")
        gate_index = next((index for index, operation in enumerate(operations)
                           if operation.kind == "TimedConfirmation"), -1)
        if gate_index >= 0:
            for operation in operations[gate_index:]:
                if any(positions[dependency] < gate_index for dependency in operation.inverse_after):
                    raise CcError("unsupported_config",
                                  f"Operation {operation.id} inverseAfter crosses the confirmation rollback boundary")

    @staticmethod
    def _inverse_order(plan: Plan, completed_operation_ids: Iterable[str]) -> tuple[Operation, ...]:
        by_id = {operation.id: operation for operation in plan.operations}
        reverse_completed: list[str] = []
        seen: set[str] = set()
        for operation_id in reversed(tuple(completed_operation_ids)):
            if operation_id in by_id and operation_id not in seen:
                reverse_completed.append(operation_id)
                seen.add(operation_id)
        rank = {operation_id: index for index, operation_id in enumerate(reverse_completed)}
        indegree = {operation_id: 0 for operation_id in reverse_completed}
        successors: dict[str, list[str]] = {operation_id: [] for operation_id in reverse_completed}
        for operation_id in reverse_completed:
            for dependency in by_id[operation_id].inverse_after:
                if dependency not in indegree:
                    continue
                successors[dependency].append(operation_id)
                indegree[operation_id] += 1
        available = [(rank[operation_id], operation_id) for operation_id, count in indegree.items() if count == 0]
        heapq.heapify(available)
        ordered: list[Operation] = []
        while available:
            _, operation_id = heapq.heappop(available)
            ordered.append(by_id[operation_id])
            for successor in successors[operation_id]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    heapq.heappush(available, (rank[successor], successor))
        if len(ordered) != len(reverse_completed):
            raise CcError("unsupported_config", "Operation inverseAfter dependencies contain a cycle")
        return tuple(ordered)

    def _status_revisions(self, module_id: str, plan: Plan) -> None:
        for segment in plan.segments:
            current = self.registry.module(segment.module_id).status(self._ctx(segment.module_id, "read"))
            if current.revision != segment.expected_revision:
                raise CcError("stale_revision", f"{segment.module_id} changed since planning",
                              {"expectedRevision": segment.expected_revision, "currentRevision": current.revision,
                               "module": segment.module_id})

    def _execution_context(self, txid: str, module_id: str) -> Any:
        ctx = self._ctx(module_id, "apply")
        ctx.txid = txid
        ctx.backups = self.backups
        ctx.ccctl_path = self.ccctl_path
        return ctx

    def _backup_paths(self, plan: Plan) -> list[str]:
        paths: list[str] = []
        for operation in plan.operations:
            paths.extend(operation.backup_paths)
            if operation.kind in {"WriteFileAtomic", "ReplaceManagedBlock", "RemoveFile"}:
                paths.append(operation.params["path"])
        return list(dict.fromkeys(paths))

    def _arm_gate(self, tx: Transaction, gate_index: int) -> Transaction:
        gate = tx.plan.operations[gate_index]
        before_budget = sum(item.timeout_s for item in tx.plan.operations[:gate_index])
        budget = int(before_budget + gate.params["seconds"] + 5)
        unit = f"omarchy-cc-confirm-{tx.id}"
        context = self._execution_context(tx.id, tx.module_id)
        result = context.commands.run([
            "systemd-run", "--user", "--unit", unit, f"--on-active={budget}s",
            "--timer-property=AccuracySec=1s", "--", "/usr/bin/python3", self.ccctl_path,
            "rollback", tx.id, "--reason", "timeout",
        ], timeout_s=10)
        if result.timed_out or result.exit_code != 0:
            raise CcError("runtime_unavailable", result.stderr.strip() or "Could not arm confirmation backstop")
        confirmation = {"unit": unit, "armedAt": self._ctx(tx.module_id, "read").clock.now_iso(),
                        "deadline": None, "tokenSha256": None, "status": "armed"}
        return self._save(tx, confirmation=confirmation)

    def _stop_gate(self, tx: Transaction) -> None:
        confirmation = tx.confirmation or {}
        if confirmation.get("unit"):
            try:
                self._execution_context(tx.id, tx.module_id).commands.run(
                    ["systemctl", "--user", "stop", confirmation["unit"] + ".timer"], timeout_s=10)
            except Exception:
                pass
        self._remove_tokens(tx.id)

    def _token_paths(self, txid: str) -> tuple[Path, Path]:
        return self.paths.runtime / "confirm" / txid, self.paths.runtime / "pending-confirm" / txid

    def _remove_tokens(self, txid: str) -> None:
        for path in self._token_paths(txid):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def _verify(self, plan: Plan, results: dict[str, OperationResult], partial: bool = False) -> VerifyResult:
        if plan.segments:
            final = VerifyResult("pass", "full", "")
            completed = set(results)
            for segment in plan.segments:
                required_ids = {operation_id for operation_id in segment.operation_ids
                                if next((op for op in plan.operations if op.id == operation_id), None) is not None
                                and next(op for op in plan.operations if op.id == operation_id).kind != "TimedConfirmation"}
                if partial and not required_ids.issubset(completed):
                    continue
                module = self.registry.module(segment.module_id)
                ctx = self._ctx(segment.module_id, "verify")
                status = module.status(self._ctx(segment.module_id, "read"))
                selected = {key: value for key, value in results.items() if key in segment.operation_ids}
                value = module.verify(ctx, plan, status, selected)
                if value.state != "pass":
                    return value
                if value.level == "limited":
                    final = value
            return final
        module = self.registry.module(plan.module_id)
        status = module.status(self._ctx(plan.module_id, "read"))
        return module.verify(self._ctx(plan.module_id, "verify"), plan, status, results)

    def _wait_gate(self, tx: Transaction, operation: Operation,
                   results: dict[str, OperationResult], verify_partial: bool = True) -> Transaction:
        if verify_partial:
            verified = self._verify(tx.plan, results, partial=True)
            if verified.state == "fail":
                raise CcError(verified.code or "verification_failed", verified.reason or "Pre-confirmation verification failed")
        token = secrets.token_urlsafe(32)
        clock = self._ctx(tx.module_id, "read").clock
        deadline_dt = clock.now() + timedelta(seconds=operation.params["seconds"])
        deadline = deadline_dt.isoformat().replace("+00:00", "Z")
        digest = hashlib.sha256(token.encode()).hexdigest()
        pending = self.paths.runtime / "pending-confirm" / tx.id
        mkdir_durable(pending.parent, 0o700)
        write_bytes_atomic(pending, token.encode() + b"\n", 0o600)
        confirmation = {**(tx.confirmation or {}), "deadline": deadline, "tokenSha256": digest, "status": "armed"}
        tx = self._save(tx, state="awaiting_confirmation", confirmation=confirmation)
        confirm_path, _ = self._token_paths(tx.id)
        while clock.now() < deadline_dt:
            self.faults.hit("gate_confirm_replay")
            try:
                supplied = confirm_path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                supplied = ""
            if supplied and hashlib.sha256(supplied.encode()).hexdigest() == digest:
                self._stop_gate(tx)
                confirmation = {**confirmation, "status": "confirmed"}
                return self._save(tx, state="applying", confirmation=confirmation)
            time.sleep(0.2)
        self.faults.hit("gate_timeout")
        self._remove_tokens(tx.id)
        raise CcError("confirmation_expired", "Confirmation deadline expired")

    def apply(self, module_id: str, draft: dict[str, Any], expected_revision: str,
              plan_digest: str | None = None, confirmations: Iterable[str] = ()) -> Transaction:
        self.recover()
        if any(tx.state == "rollback_failed" and any(not item.get("resolved") for item in tx.rollback_errors)
               for tx in self.journal.history(limit=1_000_000)):
            raise CcError("recovery_required", "A failed rollback must be resolved before applying")
        txid = str(uuid.uuid4())
        with ApplyLock(self.paths, txid, module_id):
            module = self.registry.module(module_id)
            status = module.status(self._ctx(module_id, "read"))
            document = draft.get("draft") if isinstance(draft.get("draft"), dict) else draft
            migrated = upgrade(module, "draft", document, self._ctx(module_id, "validate"))
            validation = module.validate(self._ctx(module_id, "validate"), migrated, status)
            if not validation.ok or validation.normalized_draft is None:
                raise CcError("validation_failed", "Draft validation failed",
                              {"issues": [item.to_json() for item in validation.issues]})
            if status.revision != expected_revision:
                raise CcError("stale_revision", "State changed since the draft was reviewed",
                              {"expectedRevision": expected_revision, "currentRevision": status.revision})
            plan = module.plan(self._ctx(module_id, "plan"), validation.normalized_draft, status)
            if plan.module_id != module_id or plan.expected_revision != status.revision:
                raise CcError("unsupported_config", "Plan ownership or expected revision does not match current status")
            digest = self.digest(plan)
            plan = replace(plan, plan_digest=digest)
            if plan_digest is not None and plan_digest != digest:
                raise CcError("stale_revision", "Reviewed plan digest does not match",
                              {"expectedDigest": plan_digest, "currentDigest": digest})
            self._status_revisions(module_id, plan)
            self._validate_plan(plan, confirmations)
            now = self._ctx(module_id, "read").clock.now_iso()
            tx = Transaction(txid, module_id, "applying", now, now, plan, status.revision, None,
                             (), (), {}, None, None, (), ())
            self.journal.create(tx)
            self.journal.set_current(txid)
            gate_index = next((i for i, item in enumerate(plan.operations) if item.kind == "TimedConfirmation"), -1)
            try:
                if gate_index >= 0:
                    tx = self._arm_gate(tx, gate_index)
                self.faults.hit("before_backup")
                backups = self.backups.take(txid, self._backup_paths(plan))
                tx = self._save(tx, backups=backups)
                self.faults.hit("after_backup")
                exec_ctx = self._execution_context(txid, module_id)
                try:
                    exec_ctx.cache["hyprctl_configerrors_baseline"] = exec_ctx.hyprctl.configerrors()
                except Exception:
                    exec_ctx.cache["hyprctl_configerrors_baseline"] = []
                results: dict[str, OperationResult] = {}
                for operation in plan.operations:
                    self.faults.hit(f"before_op:{operation.id}")
                    if operation.kind == "TimedConfirmation":
                        result = ops.run_forward(operation, exec_ctx)
                        tx = self._wait_gate(tx, operation, results)
                    else:
                        result = ops.run_forward(operation, exec_ctx)
                    if operation.kind == "TerminalHandoff":
                        injected = next((item for item in self.faults.hooks if item.startswith("handoff_exit:")), None)
                        if injected is not None:
                            code = int(injected.rsplit(":", 1)[1])
                            if code != 0:
                                raise CcError("handoff_failed", f"Injected handoff exit {code}", {"exitCode": code})
                    results[operation.id] = result
                    log_entry = self._command_log_entry(operation, result, "forward")
                    tx = self._save(tx, completed_operation_ids=tx.completed_operation_ids + (operation.id,),
                                    command_log=tx.command_log + (log_entry,))
                    self.faults.hit(f"after_op:{operation.id}")
                    if operation.kind == "TerminalHandoff":
                        tx = self._save(tx, state="pending_handoff")
                        return tx
                self.faults.hit("before_verify")
                verified = self._verify(plan, results)
                self.faults.hit("verification_mismatch")
                if verified.state != "pass":
                    raise CcError(verified.code or "verification_failed", verified.reason or "Verification did not pass")
                after = module.status(self._ctx(module_id, "read")).revision
                tx = self._save(tx, state="committed", after_revision=after, verify=verified)
                self._stop_gate(tx)
                return tx
            except SystemExit:
                raise
            except Exception as error:
                cc_error = error if isinstance(error, CcError) else CcError("internal_error", str(error))
                tx = self._save(tx, errors=tx.errors + ({**cc_error.to_json(), "at": self._ctx(module_id, "read").clock.now_iso()},))
                rollback_reason = ("timeout" if cc_error.code == "confirmation_expired" else
                                   "handoff_failed" if cc_error.code == "handoff_failed" else "operation")
                tx = self._rollback_record(tx, rollback_reason)
                cc_error.data = {**cc_error.data, "transactionId": tx.id, "state": tx.state}
                if tx.state == "rollback_failed":
                    raise CcError("rollback_failed", "One or more operations could not be reversed",
                                  self._recovery_data(tx)) from error
                raise cc_error
            finally:
                self.journal.clear_current(txid)
                if 'tx' in locals() and tx.state not in {"awaiting_confirmation"}:
                    self._remove_tokens(txid)

    @staticmethod
    def _affected_paths(operation: Operation) -> list[str]:
        paths = list(operation.backup_paths)
        primary = operation.params.get("path")
        if isinstance(primary, str):
            paths.append(primary)
        return list(dict.fromkeys(str(Path(item).absolute()) for item in paths))

    @staticmethod
    def _command_log_entry(operation: Operation, result: OperationResult, phase: str,
                           inverse_of: str | None = None) -> dict[str, Any]:
        entry = {"operationId": operation.id, "argv": operation.params.get("argv", []),
                 "exit": result.exit_code, "durationMs": result.duration_ms,
                 "stdoutHead": redact(result.stdout_head)[:4096],
                 "stderrHead": redact(result.stderr_head)[:4096], "timedOut": result.timed_out,
                 "writtenSha256": result.written_sha256, "phase": phase}
        if inverse_of is not None:
            entry["inverseOf"] = inverse_of
        if operation.kind == "ReplaceDirectoryAtomic" and result.stdout_head:
            entry["directoryReplacement"] = json.loads(result.stdout_head)
        return entry

    @staticmethod
    def _failed_operation_result(operation: Operation, error: Exception, started: float) -> OperationResult:
        data = getattr(error, "data", {})
        exit_code = data.get("exitCode") if isinstance(data, dict) else None
        return OperationResult(operation.id, exit_code if isinstance(exit_code, int) else None, "", str(error),
                               getattr(error, "code", "") == "timeout",
                               int((time.monotonic() - started) * 1000), None)

    @staticmethod
    def _results_from_log(tx: Transaction) -> dict[str, OperationResult]:
        return {
            str(item.get("operationId")): OperationResult(str(item.get("operationId")), item.get("exit"),
                str(item.get("stdoutHead", "")), str(item.get("stderrHead", "")),
                bool(item.get("timedOut", False)), int(item.get("durationMs", 0)), item.get("writtenSha256"))
            for item in tx.command_log if item.get("phase", "forward") == "forward"
        }

    def _rollback_record(self, tx: Transaction, reason: str) -> Transaction:
        if tx.state != "rolling_back":
            tx = self._save(tx, state="rolling_back", reason=reason)
        exec_ctx = self._execution_context(tx.id, tx.module_id)
        operations = {item.id: item for item in tx.plan.operations}
        results = self._results_from_log(tx)
        rollback_errors = list(tx.rollback_errors)
        skipped = list(tx.skipped_inverse_ids)
        deferred_reloads: list[tuple[Operation, str]] = []
        restored_hypr_operation_id: str | None = None
        for operation in self._inverse_order(tx.plan, tx.completed_operation_ids):
            operation_id = operation.id
            if operation.kind == "TimedConfirmation":
                continue
            try:
                self.faults.hit(f"before_inverse:{operation_id}")
            except CcError as error:
                rollback_errors.append({"code": error.code, "message": error.message, "operationId": operation_id,
                                        "affectedPaths": self._affected_paths(operation)})
                continue
            if operation.inverse is None:
                skipped.append({"operationId": operation_id, "why": "nonreversible"})
                continue
            if operation.kind == "WriteFileAtomic":
                path = Path(operation.params["path"])
                try:
                    forward_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                except FileNotFoundError:
                    forward_hash = None
                expected = results.get(operation_id).written_sha256 if operation_id in results else None
                if expected is None or forward_hash != expected:
                    skipped.append({"operationId": operation_id, "why": "rollback_conflict"})
                    continue
            inverses = ops.build_inverse(operation, exec_ctx, results.get(operation_id))
            if operation.kind in {"WriteFileAtomic", "RemoveFile"} and not inverses:
                inverses = (Operation(operation.id + ".restore", operation.module_id, "RestoreBackup",
                                      {"path": operation.params["path"]}, "Restore backup", (), (), 30),)
            if operation.kind == "ReplaceManagedBlock" and not inverses:
                inverses = (Operation(operation.id + ".restore", operation.module_id, "RestoreBackup",
                                      {"path": operation.params["path"]}, "Restore backup", (), (), 30),)
            if operation.kind == "ReplaceDirectoryAtomic":
                replacement = exec_ctx.cache.get("directory_replacements", {}).get(operation.id)
                if replacement is None:
                    entry = next((item for item in tx.command_log if item.get("operationId") == operation.id), {})
                    details = entry.get("directoryReplacement")
                    if isinstance(details, dict):
                        from .atomic import DirectoryReplacement
                        replacement = DirectoryReplacement(Path(operation.params["path"]),
                            Path(details["previous"]) if details.get("previous") else None,
                            bool(details.get("installed")))
                if replacement:
                    inverse = inverses[0] if inverses else Operation(
                        operation.id + ".inverse", operation.module_id, "ReplaceDirectoryAtomic", {},
                        "Restore directory", (), (), 30)
                    started = time.monotonic()
                    try:
                        replacement.undo()
                        result = OperationResult(inverse.id, None, "", "", False,
                                                 int((time.monotonic() - started) * 1000), None)
                        tx = self._save(tx, command_log=tx.command_log +
                                        (self._command_log_entry(inverse, result, "rollback", operation_id),),
                                        rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
                    except Exception as error:
                        result = self._failed_operation_result(inverse, error, started)
                        tx = self._save(tx, command_log=tx.command_log +
                                        (self._command_log_entry(inverse, result, "rollback", operation_id),))
                        rollback_errors.append({"code": "rollback_failed", "message": str(error),
                                                "operationId": operation_id,
                                                "affectedPaths": self._affected_paths(operation)})
                    continue
            for inverse in inverses:
                if inverse.kind == "HyprctlReload":
                    deferred_reloads.append((inverse, operation_id))
                    continue
                started = time.monotonic()
                try:
                    if inverse.kind == "RestoreBackup" and Path(inverse.params["path"]).is_relative_to(self.paths.home / ".config/hypr"):
                        restored_hypr_operation_id = operation_id
                    result = ops.run_forward(inverse, exec_ctx)
                except Exception as error:
                    result = self._failed_operation_result(inverse, error, started)
                    rollback_errors.append({"code": getattr(error, "code", "rollback_failed"),
                                            "message": str(error), "operationId": operation_id,
                                            "affectedPaths": self._affected_paths(operation)})
                tx = self._save(tx, command_log=tx.command_log +
                                (self._command_log_entry(inverse, result, "rollback", operation_id),))
            tx = self._save(tx, rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
            try:
                self.faults.hit(f"after_inverse:{operation_id}")
            except CcError as error:
                rollback_errors.append({"code": error.code, "message": error.message, "operationId": operation_id,
                                        "affectedPaths": self._affected_paths(operation)})
        if deferred_reloads or restored_hypr_operation_id:
            inverse, inverse_of = (deferred_reloads[-1] if deferred_reloads else
                                    (Operation("hyprctl.reload", tx.module_id, "HyprctlReload", {},
                                               "Reload Hyprland", (), (), 30), restored_hypr_operation_id))
            inverse = replace(inverse, params={"config_only": bool(deferred_reloads) and
                                                all(item.params.get("config_only") for item, _ in deferred_reloads)})
            started = time.monotonic()
            try:
                result = ops.run_forward(inverse, exec_ctx)
            except Exception as error:
                result = self._failed_operation_result(inverse, error, started)
                rollback_errors.append({"code": getattr(error, "code", "rollback_failed"),
                                        "message": str(error), "operationId": "hyprctl.reload",
                                        "affectedPaths": []})
            tx = self._save(tx, command_log=tx.command_log +
                            (self._command_log_entry(inverse, result, "rollback", inverse_of),))
        tx = self._save(tx, rollback_errors=tuple(rollback_errors), skipped_inverse_ids=tuple(skipped))
        self._stop_gate(tx)
        if rollback_errors:
            return self._save(tx, state="rollback_failed")
        try:
            current = self.registry.module(tx.module_id).status(self._ctx(tx.module_id, "read")).revision
            if current != tx.before_revision:
                errors = tx.errors + ({"code": "revision_drift_after_rollback",
                                       "message": "State revision differs after rollback"},)
                tx = self._save(tx, errors=errors)
        except Exception:
            pass
        return self._save(tx, state="rolled_back")

    def _recovery_data(self, tx: Transaction) -> dict[str, Any]:
        unresolved = [item for item in tx.rollback_errors if not item.get("resolved")]
        affected = list(tx.backups)
        manual_paths = [{"operationId": str(item.get("operationId")), "path": path}
                        for item in unresolved for path in item.get("affectedPaths", [])
                        if path not in tx.backups]
        resolvable = list(dict.fromkeys(str(item.get("operationId")) for item in unresolved
                                        if not item.get("affectedPaths") or
                                        set(item.get("affectedPaths", [])) - set(tx.backups)))
        return {"transactionId": tx.id, "backupPaths": affected, "manualPaths": manual_paths,
                "rollbackErrors": list(tx.rollback_errors),
                "recoveryCommands": [f"{self.ccctl_path} restore {tx.id} --path {path}" for path in affected],
                "resolveCommands": [f"{self.ccctl_path} resolve {tx.id} --operation {operation_id}"
                                    for operation_id in resolvable]}

    def recover(self) -> dict[str, Any]:
        recovered: list[str] = []
        blocked: list[str] = []
        live_executor = False
        for tx in self.journal.history(limit=1_000_000):
            if tx.state == "rollback_failed":
                unresolved = [item for item in tx.rollback_errors if not item.get("resolved")]
                if unresolved:
                    blocked.append(tx.id)
            elif tx in self.journal.pending_recovery():
                try:
                    with ApplyLock(self.paths, tx.id, tx.module_id):
                        if tx.state == "pending_handoff":
                            self._reconcile_record(tx)
                        else:
                            self._rollback_record(tx, "recovery")
                        recovered.append(tx.id)
                except Locked:
                    live_executor = True
                    continue
        if not live_executor:
            records = self.journal.history(limit=1_000_000)
            newest_created = max((datetime.fromisoformat(tx.created_at.replace("Z", "+00:00")).timestamp()
                                  for tx in records), default=time.time())
            age_cutoff = time.time() - 30 * 60
            for path in ((self.paths.state / "staging").glob("*/*")
                         if (self.paths.state / "staging").exists() else ()):
                try:
                    modified = path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if path.is_dir() and modified < newest_created and modified < age_cutoff:
                    shutil.rmtree(path, ignore_errors=True)
        return {"recovered": recovered, "blocked": blocked, "required": bool(blocked)}

    def confirm(self, txid: str, token: str) -> Transaction:
        tx = self.journal.load(txid)
        if tx.state != "awaiting_confirmation":
            raise CcError("confirmation_expired", "Transaction is not awaiting confirmation")
        expected = (tx.confirmation or {}).get("tokenSha256")
        if not expected or not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected):
            raise CcError("confirmation_invalid", "Confirmation token is invalid")
        path, pending = self._token_paths(txid)
        if path.exists():
            raise CcError("confirmation_invalid", "Confirmation token was already submitted")
        mkdir_durable(path.parent, 0o700)
        write_bytes_atomic(path, token.encode() + b"\n", 0o600)
        try:
            pending.unlink()
        except FileNotFoundError:
            pass
        return tx

    def rollback(self, txid: str, reason: str = "user", force_stale: bool = False) -> Transaction:
        if reason not in {"user", "timeout", "recovery"}:
            raise CcError("transaction_state_invalid", f"Invalid rollback reason: {reason}")
        tx = self.journal.load(txid)
        if tx.state in {"rolled_back", "rollback_failed"} or (reason in {"timeout", "recovery"} and tx.state == "committed"):
            return tx
        apply_lock = ApplyLock(self.paths, txid, tx.module_id)
        deadline = time.monotonic() + 10 if reason == "timeout" else None
        while True:
            try:
                apply_lock.acquire()
                break
            except Locked:
                if deadline is None:
                    raise
                if time.monotonic() >= deadline:
                    # A live executor owns the gate. The backstop exits successfully and lets it finish.
                    return self.journal.load(txid)
                time.sleep(0.1)
        try:
            tx = self.journal.load(txid)
            if tx.state in {"applying", "awaiting_confirmation", "rolling_back", "pending_handoff"}:
                return self._rollback_record(tx, reason)
            if reason in {"timeout", "recovery"} and tx.state in {"committed", "rolled_back", "rollback_failed"}:
                return tx
            if tx.state != "committed":
                raise CcError("transaction_state_invalid", f"Cannot roll back transaction in state {tx.state}")
            current = self.registry.module(tx.module_id).status(self._ctx(tx.module_id, "read")).revision
            if not force_stale and tx.after_revision and current != tx.after_revision:
                raise CcError("stale_revision", "State changed since this transaction committed",
                              {"expectedRevision": tx.after_revision, "currentRevision": current})
            return self._apply_user_inverse(tx, current)
        finally:
            apply_lock.release()

    def _apply_user_inverse(self, original: Transaction, current_revision: str) -> Transaction:
        """Apply a committed transaction's inverses as a separate transaction."""
        original_results = self._results_from_log(original)
        original_exec = self._execution_context(original.id, original.module_id)
        gate_index = next((index for index, item in enumerate(original.plan.operations)
                           if item.kind == "TimedConfirmation"), -1)
        ordered: list[tuple[Operation, Operation]] = []
        completed_ids = original.completed_operation_ids or tuple(item.id for item in original.plan.operations)
        inverse_order = self._inverse_order(original.plan, completed_ids)
        positions = {operation.id: index for index, operation in enumerate(original.plan.operations)}

        def append_inverses(items: Iterable[Operation]) -> None:
            for forward in items:
                for inverse in ops.build_inverse(forward, original_exec, original_results.get(forward.id)):
                    ordered.append((inverse, forward))

        if gate_index >= 0:
            append_inverses(item for item in inverse_order if positions[item.id] > gate_index)
            gate = original.plan.operations[gate_index]
            gate_inverse = next(iter(ops.build_inverse(gate, original_exec, original_results.get(gate.id))), gate)
            ordered.append((gate_inverse, gate))
            append_inverses(item for item in inverse_order if positions[item.id] < gate_index)
        else:
            append_inverses(inverse_order)

        rebuilt: list[Operation] = []
        for sequence, (inverse, forward) in enumerate(ordered, 1):
            rebuilt.append(replace(inverse, id=f"{original.module_id}.{sequence:04d}",
                                   module_id=original.module_id, inverse=forward, inverse_after=()))
        inverse_plan = Plan(original.module_id, current_revision, tuple(rebuilt), original.plan.claims,
                            f"Undo: {original.plan.summary}", (), (), original.plan.residual_side_effects,
                            (), "")
        inverse_plan = replace(inverse_plan, plan_digest=self.digest(inverse_plan))
        now = self._ctx(original.module_id, "read").clock.now_iso()
        tx = Transaction(str(uuid.uuid4()), original.module_id, "applying", now, now, inverse_plan,
                         current_revision, None, (), (), original.backups, None, None, (), (), reason="user")
        source_backups = self.backups.root / original.id
        inverse_backups = self.backups.root / tx.id
        if source_backups.is_dir():
            shutil.copytree(source_backups, inverse_backups)
        self.journal.create(tx)
        self.journal.set_current(tx.id)
        inverse_gate_index = next((index for index, item in enumerate(rebuilt)
                                   if item.kind == "TimedConfirmation"), -1)
        results: dict[str, OperationResult] = {}
        exec_ctx = self._execution_context(tx.id, tx.module_id)
        try:
            if inverse_gate_index >= 0:
                tx = self._arm_gate(tx, inverse_gate_index)
            for operation in rebuilt:
                forward = operation.inverse if isinstance(operation.inverse, Operation) else None
                if forward is not None and forward.kind == "WriteFileAtomic":
                    recorded = original_results.get(forward.id)
                    try:
                        current_hash = hashlib.sha256(Path(forward.params["path"]).read_bytes()).hexdigest()
                    except FileNotFoundError:
                        current_hash = None
                    if recorded is None or recorded.written_sha256 != current_hash:
                        tx = self._save(tx, skipped_inverse_ids=tx.skipped_inverse_ids +
                                        ({"operationId": forward.id, "why": "rollback_conflict"},))
                        continue
                if operation.kind == "TimedConfirmation":
                    result = ops.run_forward(operation, exec_ctx)
                    tx = self._wait_gate(tx, operation, results, verify_partial=False)
                else:
                    result = ops.run_forward(operation, exec_ctx)
                results[operation.id] = result
                entry = self._command_log_entry(operation, result, "forward")
                tx = self._save(tx, completed_operation_ids=tx.completed_operation_ids + (operation.id,),
                                command_log=tx.command_log + (entry,))
            after = self.registry.module(tx.module_id).status(self._ctx(tx.module_id, "read")).revision
            if after != original.before_revision:
                if tx.skipped_inverse_ids:
                    tx = self._save(tx, errors=tx.errors + ({"code": "revision_drift_after_rollback",
                        "message": "State revision differs after rollback"},))
                else:
                    raise CcError("verification_failed", "State did not return to the pre-transaction revision",
                                  {"expectedRevision": original.before_revision, "currentRevision": after})
            tx = self._save(tx, state="committed", after_revision=after,
                            verify=VerifyResult("pass", "full", ""))
            self._stop_gate(tx)
            return tx
        except Exception as error:
            cc_error = error if isinstance(error, CcError) else CcError("internal_error", str(error))
            tx = self._save(tx, errors=tx.errors + (cc_error.to_json(),))
            rolled = self._rollback_record(tx, "timeout" if cc_error.code == "confirmation_expired" else "operation")
            if rolled.state == "rollback_failed":
                raise CcError("rollback_failed", "Undo could not restore the committed state",
                              self._recovery_data(rolled)) from error
            raise cc_error
        finally:
            self.journal.clear_current(tx.id)
            self._remove_tokens(tx.id)

    def reconcile(self, txid: str) -> Transaction:
        tx = self.journal.load(txid)
        with ApplyLock(self.paths, txid, tx.module_id):
            return self._reconcile_record(self.journal.load(txid))

    def _reconcile_record(self, tx: Transaction) -> Transaction:
        txid = tx.id
        if tx.state != "pending_handoff":
            raise CcError("transaction_state_invalid", "Transaction is not pending a handoff")
        sentinel = self.paths.state / "handoffs" / f"{txid}.json"
        terminal = next((item for item in tx.plan.operations if item.kind == "TerminalHandoff"), None)
        if terminal and terminal.params.get("wrapped") and not sentinel.exists():
            return tx
        if sentinel.exists():
            try:
                code = int(json.loads(sentinel.read_text(encoding="utf-8"))["exitCode"])
            except Exception as error:
                raise CcError("malformed_output", "Handoff sentinel is malformed") from error
            if code != 0:
                return self._rollback_record(tx, "handoff_failed")
        verified = self._verify(tx.plan, self._results_from_log(tx))
        if verified.state == "pending":
            return tx
        if verified.state == "fail":
            error = {"code": verified.code or "verification_failed",
                     "message": verified.reason or "Handoff verification failed",
                     "data": dict(verified.evidence),
                     "at": self._ctx(tx.module_id, "read").clock.now_iso()}
            tx = self._save(tx, verify=verified, errors=tx.errors + (error,))
            return self._rollback_record(tx, "verification")
        status = self.registry.module(tx.module_id).status(self._ctx(tx.module_id, "read"))
        return self._save(tx, state="committed", after_revision=status.revision, verify=verified)

    def abandon(self, txid: str) -> Transaction:
        tx = self.journal.load(txid)
        apply_lock = ApplyLock(self.paths, txid, tx.module_id)
        deadline = time.monotonic() + 10
        while True:
            try:
                apply_lock.acquire()
                break
            except Locked:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        try:
            tx = self.journal.load(txid)
            if tx.state != "pending_handoff":
                raise CcError("transaction_state_invalid", "Only a pending handoff can be abandoned")
            self._remove_tokens(txid)
            return self._rollback_record(tx, "user")
        finally:
            apply_lock.release()

    def restore(self, txid: str, path: str | Path) -> Transaction:
        initial = self.journal.load(txid)
        with ApplyLock(self.paths, txid, initial.module_id):
            tx = self.journal.load(txid)
            if tx.state != "rollback_failed":
                raise CcError("transaction_state_invalid", "Restore is only available for rollback_failed")
            target = str(Path(path).absolute())
            if target not in tx.backups:
                raise CcError("permission_required", f"Path was not backed up by this transaction: {target}")
            self.backups.restore(txid, target)
            errors: list[dict[str, Any]] = []
            for item in tx.rollback_errors:
                affected = [str(Path(value).absolute()) for value in item.get("affectedPaths", [])]
                if target not in affected:
                    errors.append(item)
                    continue
                restored = set(item.get("restoredPaths", []))
                restored.add(target)
                errors.append({**item, "restoredPaths": sorted(restored),
                               "resolved": set(affected).issubset(restored)})
            return self._save(tx, rollback_errors=tuple(errors))

    def resolve(self, txid: str, operation_id: str) -> Transaction:
        initial = self.journal.load(txid)
        with ApplyLock(self.paths, txid, initial.module_id):
            tx = self.journal.load(txid)
            if tx.state != "rollback_failed":
                raise CcError("transaction_state_invalid", "Resolve is only available for rollback_failed")
            found = False
            errors: list[dict[str, Any]] = []
            for item in tx.rollback_errors:
                if item.get("operationId") == operation_id and not item.get("resolved"):
                    backed = set(item.get("affectedPaths", [])) & set(tx.backups)
                    restored = set(item.get("restoredPaths", []))
                    if not backed.issubset(restored):
                        raise CcError("transaction_state_invalid",
                                      f"Restore every backed path before resolving {operation_id}",
                                      {"missingPaths": sorted(backed - restored)})
                    item = {**item, "resolved": True, "acknowledged": True}
                    found = True
                errors.append(item)
            if not found:
                raise CcError("transaction_not_found", f"No unresolved rollback failure for operation {operation_id}")
            return self._save(tx, rollback_errors=tuple(errors))


def _default_executor() -> Executor:
    from .paths import Paths
    from .registry import load_registry
    plugin = Path(__file__).resolve().parents[3]
    paths = Paths.from_env()
    registry = load_registry(plugin, paths=paths)
    return Executor(plugin, registry, paths, plugin / "backend/ccctl")


def apply(module_id: str, draft: dict[str, Any], expected_revision: str,
          plan_digest: str | None = None, confirmations: Iterable[str] = ()) -> Transaction:
    return _default_executor().apply(module_id, draft, expected_revision, plan_digest, confirmations)


def rollback(txid: str, reason: str = "user", force_stale: bool = False) -> Transaction:
    return _default_executor().rollback(txid, reason, force_stale)


def reconcile(txid: str) -> Transaction:
    return _default_executor().reconcile(txid)


def abandon(txid: str) -> Transaction:
    return _default_executor().abandon(txid)


def restore(txid: str, path: str | Path) -> Transaction:
    return _default_executor().restore(txid, path)


def confirm(txid: str, token: str) -> Transaction:
    return _default_executor().confirm(txid, token)


def resolve(txid: str, operation_id: str) -> Transaction:
    return _default_executor().resolve(txid, operation_id)


def recover() -> dict[str, Any]:
    return _default_executor().recover()
