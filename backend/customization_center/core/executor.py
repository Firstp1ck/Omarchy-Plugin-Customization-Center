from __future__ import annotations

import base64
import hashlib
import heapq
import json
import os
import re
import secrets
import shutil
import stat
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
        private_root = (Path(paths.runtime) / "tmp").absolute()
        try:
            resolved_root = private_root.resolve(strict=True)
            resolved_path = path.resolve(strict=True)
            if (path.is_symlink() or not resolved_path.is_relative_to(resolved_root) or
                    not path.is_relative_to(private_root)):
                return cls()
            data = json.loads(paths.read_regular(path, 1024 * 1024).decode("utf-8"))
        except (CcError, OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
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
        self._validate_segments(plan)
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
    def _validate_segments(plan: Plan) -> None:
        if not plan.segments:
            foreign = sorted(operation.id for operation in plan.operations
                             if operation.module_id != plan.module_id)
            if foreign:
                raise CcError("unsupported_config", "Composed plan must declare segments",
                              {"operationIds": foreign})
            return
        operations = {operation.id: operation for operation in plan.operations}
        assigned: dict[str, str] = {}
        for segment in plan.segments:
            for operation_id in segment.operation_ids:
                if operation_id not in operations:
                    raise CcError("unsupported_config",
                                  f"Plan segment {segment.module_id} names unknown operation {operation_id}")
                if operation_id in assigned:
                    raise CcError("unsupported_config",
                                  f"Operation {operation_id} appears in multiple plan segments",
                                  {"firstModule": assigned[operation_id], "secondModule": segment.module_id})
                operation = operations[operation_id]
                if operation.module_id != segment.module_id:
                    raise CcError("unsupported_config",
                                  f"Operation {operation_id} is owned by {operation.module_id}, not {segment.module_id}")
                assigned[operation_id] = segment.module_id
        omitted = sorted(set(operations) - set(assigned))
        if omitted:
            raise CcError("unsupported_config", "Composed plan segments omit operations",
                          {"operationIds": omitted})

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

    @staticmethod
    def _snapshot(path: str | Path) -> dict[str, Any]:
        target = Path(path)
        try:
            stat_result = target.lstat()
        except FileNotFoundError:
            return {"exists": False}
        if target.is_symlink():
            return {"exists": True, "type": "symlink", "target": os.readlink(target)}
        mode = stat_result.st_mode & 0o7777
        if target.is_file():
            return {"exists": True, "type": "file", "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "mode": f"{mode:04o}"}
        if target.is_dir():
            digest = hashlib.sha256()
            for item in sorted(target.rglob("*"), key=lambda value: str(value.relative_to(target))):
                relative = str(item.relative_to(target))
                item_stat = item.lstat()
                item_mode = item_stat.st_mode
                permissions = item_mode & 0o7777
                if stat.S_ISLNK(item_mode):
                    marker = f"L\0{relative}\0{permissions:04o}\0{os.readlink(item)}\0"
                    digest.update(marker.encode())
                elif stat.S_ISDIR(item_mode):
                    digest.update(f"D\0{relative}\0{permissions:04o}\0".encode())
                elif stat.S_ISREG(item_mode):
                    digest.update(f"F\0{relative}\0{permissions:04o}\0".encode())
                    digest.update(hashlib.sha256(item.read_bytes()).digest())
                elif stat.S_ISFIFO(item_mode):
                    digest.update(f"P\0{relative}\0{permissions:04o}\0".encode())
                elif stat.S_ISSOCK(item_mode):
                    digest.update(f"S\0{relative}\0{permissions:04o}\0".encode())
                elif stat.S_ISCHR(item_mode):
                    digest.update(f"C\0{relative}\0{permissions:04o}\0{item_stat.st_rdev}\0".encode())
                elif stat.S_ISBLK(item_mode):
                    digest.update(f"B\0{relative}\0{permissions:04o}\0{item_stat.st_rdev}\0".encode())
                else:
                    digest.update(f"O\0{relative}\0{item_mode:o}\0".encode())
            return {"exists": True, "type": "directory", "sha256": digest.hexdigest(),
                    "mode": f"{mode:04o}"}
        return {"exists": True, "type": "other", "mode": f"{mode:04o}"}

    @staticmethod
    def _write_digest(operation: Operation) -> str:
        content = operation.params["content"]
        data = (base64.b64decode(content["base64"], validate=True)
                if isinstance(content, dict) else str(content).encode())
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _valid_directory_snapshot(value: Any, *, allow_absent: bool = True) -> bool:
        if allow_absent and value == {"exists": False}:
            return True
        return (isinstance(value, dict) and
                set(value) == {"exists", "type", "sha256", "mode"} and
                value.get("exists") is True and value.get("type") == "directory" and
                isinstance(value.get("sha256"), str) and
                re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None and
                isinstance(value.get("mode"), str) and
                re.fullmatch(r"[0-7]{4}", value["mode"]) is not None)

    @staticmethod
    def _valid_previous_candidates(target: Path, value: Any) -> bool:
        prefix = f".{target.name}.previous-"
        return (isinstance(value, list) and all(isinstance(item, str) for item in value) and
                value == sorted(set(value)) and
                all(Path(item).name == item and item.startswith(prefix) for item in value))

    @staticmethod
    def _valid_previous_path(target: Path, previous: Path, candidates_before: list[str]) -> bool:
        generated = rf"{re.escape(f'.{target.name}.previous-')}[0-9a-f]{{32}}"
        return (previous.is_absolute() and previous.parent == target.parent and
                re.fullmatch(generated, previous.name) is not None and
                previous.name not in candidates_before and not previous.is_symlink())

    def _validated_directory_replacement(self, operation: Operation,
                                         details: dict[str, Any]) -> tuple[Path, Path | None, bool]:
        required = {"previous", "installed", "expectedInstalledSnapshot", "installedSnapshot",
                    "originalTargetSnapshot", "previousCandidatesBefore"}
        if set(details) != required:
            raise CcError("rollback_conflict", "Directory replacement evidence fields are incomplete")
        target = Path(operation.params["path"])
        intended_install = operation.params.get("staged_dir") is not None
        installed = details.get("installed")
        expected = details.get("expectedInstalledSnapshot")
        observed = details.get("installedSnapshot")
        original = details.get("originalTargetSnapshot")
        candidates = details.get("previousCandidatesBefore")
        if (not target.is_absolute() or not isinstance(installed, bool) or
                installed is not intended_install or
                not self._valid_directory_snapshot(original) or
                not self._valid_previous_candidates(target, candidates)):
            raise CcError("rollback_conflict", "Directory replacement evidence contradicts the operation")
        if intended_install:
            if not self._valid_directory_snapshot(expected, allow_absent=False):
                raise CcError("rollback_conflict", "Installed directory evidence is malformed")
        elif expected != {"exists": False}:
            raise CcError("rollback_conflict", "Directory removal evidence does not prove absence")
        current = self._snapshot(target)
        if (not self._valid_directory_snapshot(observed) or
                expected != observed or observed != current):
            raise CcError("rollback_conflict", "Installed directory post-image does not match current state")

        previous_value = details.get("previous")
        if original.get("exists"):
            if not operation.params.get("allow_existing") or not isinstance(previous_value, str):
                raise CcError("rollback_conflict", "Previous directory evidence contradicts the original target")
            previous = Path(previous_value)
            if (not self._valid_previous_path(target, previous, candidates) or
                    self._snapshot(previous) != original):
                raise CcError("rollback_conflict", "Previous directory no longer matches the original target")
        else:
            if previous_value is not None:
                raise CcError("rollback_conflict", "A previous directory was claimed for an absent original target")
            previous = None
        return target, previous, installed

    def _directory_replacement_details(self, operation: Operation, result: OperationResult,
                                       evidence: dict[str, Any] | None) -> dict[str, Any]:
        try:
            details = json.loads(result.stdout_head)
        except (TypeError, json.JSONDecodeError) as error:
            raise CcError("rollback_conflict", "Directory replacement result is malformed") from error
        if not isinstance(details, dict) or set(details) != {"previous", "installed"}:
            raise CcError("rollback_conflict", "Directory replacement result fields are malformed")
        if not isinstance(evidence, dict):
            raise CcError("rollback_conflict", "Directory replacement pre-effect evidence is missing")
        target = Path(operation.params["path"])
        original = evidence.get("before")
        candidates = evidence.get("previousCandidatesBefore")
        intended_install = operation.params.get("staged_dir") is not None
        if (evidence.get("path") != str(target.absolute()) or
                not self._valid_directory_snapshot(original) or
                not self._valid_previous_candidates(target, candidates)):
            raise CcError("rollback_conflict", "Directory replacement pre-effect evidence is malformed")
        if intended_install:
            staged = Path(operation.params["staged_dir"])
            staged_before = evidence.get("stagedBefore")
            if (evidence.get("stagedPath") != str(staged.absolute()) or
                    not self._valid_directory_snapshot(staged_before, allow_absent=False)):
                raise CcError("rollback_conflict", "Staged directory pre-effect evidence is malformed")
            expected = staged_before
        else:
            if evidence.get("stagedBefore") is not None or "stagedPath" in evidence:
                raise CcError("rollback_conflict", "Directory removal has contradictory staged evidence")
            expected = {"exists": False}
        durable = {**details, "expectedInstalledSnapshot": expected,
                   "installedSnapshot": self._snapshot(target),
                   "originalTargetSnapshot": original,
                   "previousCandidatesBefore": candidates}
        self._validated_directory_replacement(operation, durable)
        return durable

    def _in_flight_record(self, operation: Operation, phase: str, exec_ctx: Any | None = None, *,
                          inverse_key: str | None = None, inverse_index: int | None = None,
                          extra_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        primary = operation.params.get("path")
        if isinstance(primary, str):
            evidence["path"] = str(Path(primary).absolute())
            evidence["before"] = self._snapshot(primary)
        staged = operation.params.get("staged_dir")
        if isinstance(staged, str):
            evidence["stagedPath"] = str(Path(staged).absolute())
            evidence["stagedBefore"] = self._snapshot(staged)
        if operation.kind == "ReplaceDirectoryAtomic":
            target = Path(operation.params["path"])
            evidence.setdefault("stagedBefore", None)
            evidence["previousCandidatesBefore"] = sorted(
                candidate.name for candidate in target.parent.glob(f".{target.name}.previous-*"))
        if operation.kind == "WriteFileAtomic":
            evidence["writtenSha256"] = self._write_digest(operation)
        elif operation.kind == "ReplaceManagedBlock":
            if exec_ctx is None:
                raise CcError("internal_error", "Managed-block post-image requires an execution context")
            expected = ops.managed_block_post_image(operation, exec_ctx)
            evidence["expectedSha256"] = hashlib.sha256(expected).hexdigest()
        elif operation.kind == "EnsureDirectory":
            remove_if_empty = bool(operation.params.get("remove_if_empty"))
            evidence["removeIfEmpty"] = remove_if_empty
            if not remove_if_empty:
                before = evidence.get("before", {})
                evidence["created"] = not before.get("exists", False)
                evidence["previousMode"] = before.get("mode") if before.get("type") == "directory" else None
                evidence["requestedMode"] = operation.params.get("restore_mode") or operation.params.get("mode")
        if operation.kind in {"RunCommand", "TerminalHandoff"}:
            evidence["argv"] = [redact(str(item)) for item in operation.params.get("argv", [])]
        elif operation.kind == "ShellIpc":
            evidence["method"] = operation.params.get("method")
            evidence["args"] = [redact(str(item)) for item in operation.params.get("args", [])]
        elif operation.kind == "HyprctlReload":
            evidence["configOnly"] = bool(operation.params.get("config_only"))
        if extra_evidence:
            evidence.update(extra_evidence)
        record: dict[str, Any] = {"phase": phase, "operationId": operation.id, "kind": operation.kind,
                                  "affectedPaths": self._affected_paths(operation), "evidence": evidence}
        if inverse_key is not None:
            record["inverseKey"] = inverse_key
        if inverse_index is not None:
            record["inverseIndex"] = inverse_index
        return record

    @staticmethod
    def _snapshot_matches_backup(snapshot: dict[str, Any], backup: dict[str, Any] | None) -> bool:
        if not backup:
            return False
        if not backup.get("existed"):
            return not snapshot.get("exists")
        return (snapshot.get("type") == "file" and snapshot.get("sha256") == backup.get("sha256") and
                (backup.get("mode") is None or snapshot.get("mode") == backup.get("mode")))

    def _record_ambiguous_effect(self, tx: Transaction, record: dict[str, Any]) -> Transaction:
        key = str(record.get("inverseKey") or f"forward:{record.get('operationId')}")
        if any(item.get("evidenceKey") == key for item in tx.rollback_errors):
            return self._save(tx, in_flight_operation=None)
        message = (f"Recovery cannot determine whether {record.get('kind')} completed; "
                   "the operation was not rerun")
        error = {"code": "recovery_required", "message": message,
                 "operationId": str(record.get("operationId")), "affectedPaths": record.get("affectedPaths", []),
                 "evidenceKey": key, "evidence": record}
        progress = tx.inverse_progress
        if record.get("phase") == "rollback" and key not in progress:
            progress += (key,)
        return self._save(tx, rollback_errors=tx.rollback_errors + (error,), inverse_progress=progress,
                          in_flight_operation=None)

    def _durable_in_flight_operation(self, tx: Transaction, record: dict[str, Any]) -> Operation | None:
        operation_id = str(record.get("operationId", ""))
        if record.get("phase") == "forward":
            return next((item for item in tx.plan.operations if item.id == operation_id), None)
        if record.get("phase") != "rollback":
            return None
        key = record.get("inverseKey")
        index = record.get("inverseIndex")
        if not isinstance(key, str) or not isinstance(index, int) or ":" not in key:
            return None
        forward_id = key.rsplit(":", 1)[0]
        forward = next((item for item in tx.plan.operations if item.id == forward_id), None)
        if forward is None:
            return None
        try:
            inverses = ops.build_inverse(
                forward, self._execution_context(tx.id, tx.module_id), self._results_from_log(tx).get(forward.id))
        except Exception:
            return None
        if index < 0 or index >= len(inverses):
            return None
        inverse = inverses[index]
        return inverse if inverse.id == operation_id else None

    def _reconcile_in_flight(self, tx: Transaction) -> Transaction:
        record = tx.in_flight_operation
        if not record:
            return tx
        operation_id = str(record.get("operationId", ""))
        phase = record.get("phase")
        kind = str(record.get("kind", ""))
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        path = evidence.get("path")
        before = evidence.get("before") if isinstance(evidence.get("before"), dict) else None
        external = {"RunCommand", "ShellIpc", "HyprctlReload", "TerminalHandoff"}
        if kind in external:
            return self._record_ambiguous_effect(tx, record)

        completed = False
        unchanged = False
        invalid_evidence = False
        stdout = ""
        written_sha256: str | None = None
        if kind == "TimedConfirmation":
            unchanged = True
        elif path and before is not None:
            current = self._snapshot(path)
            unchanged = current == before
            operation = next((item for item in tx.plan.operations if item.id == operation_id), None)
            if kind == "WriteFileAtomic":
                written_sha256 = evidence.get("writtenSha256")
                completed = (isinstance(written_sha256, str) and current.get("type") == "file" and
                             current.get("sha256") == written_sha256)
            elif kind == "ReplaceManagedBlock":
                expected_sha256 = evidence.get("expectedSha256")
                completed = (isinstance(expected_sha256, str) and current.get("type") == "file" and
                             current.get("sha256") == expected_sha256)
                written_sha256 = expected_sha256 if completed else None
            elif kind == "RemoveFile":
                completed = bool(before.get("exists")) and not current.get("exists")
                unchanged = unchanged or (not before.get("exists") and not current.get("exists"))
            elif kind == "RestoreBackup":
                completed = self._snapshot_matches_backup(current, tx.backups.get(str(Path(path).absolute())))
            elif kind == "EnsureDirectory":
                intended = self._durable_in_flight_operation(tx, record)
                intended_remove = bool(intended and intended.params.get("remove_if_empty"))
                intended_target = intended.params.get("path") if intended else None
                if evidence.get("removeIfEmpty"):
                    invalid_evidence = (intended is None or intended.kind != "EnsureDirectory" or
                                        intended_target != path or not intended_remove or
                                        before.get("type") != "directory")
                    completed = not invalid_evidence and not current.get("exists")
                else:
                    expected_mode = evidence.get("requestedMode")
                    intended_mode = ((intended.params.get("restore_mode") or intended.params.get("mode"))
                                     if intended and intended.kind == "EnsureDirectory" and not intended_remove else None)
                    created = evidence.get("created")
                    previous_mode = evidence.get("previousMode")
                    mode_valid = lambda value: isinstance(value, str) and re.fullmatch(r"[0-7]{4}", value) is not None
                    absent_before = before == {"exists": False}
                    directory_before = (set(before) == {"exists", "type", "sha256", "mode"} and
                        before.get("exists") is True and before.get("type") == "directory" and
                        isinstance(before.get("sha256"), str) and mode_valid(before.get("mode")))
                    if absent_before:
                        evidence_consistent = created is True and previous_mode is None
                    elif directory_before:
                        evidence_consistent = (created is False and mode_valid(previous_mode) and
                                               previous_mode == before.get("mode"))
                    else:
                        evidence_consistent = False
                    invalid_evidence = (intended_target != path or not evidence_consistent or
                                        not mode_valid(expected_mode) or expected_mode != intended_mode)
                    completed = (not invalid_evidence and current.get("type") == "directory" and
                                 current.get("mode") == expected_mode)
                    if completed:
                        stdout = json.dumps({"created": created, "previousMode": previous_mode,
                                             "requestedMode": expected_mode})
            elif kind in {"ReplaceDirectoryAtomic", "ReplaceDirectoryUndo"}:
                expected = evidence.get("expected")
                if isinstance(expected, dict) and current == expected:
                    completed = True
                elif kind == "ReplaceDirectoryAtomic" and phase == "forward":
                    target = Path(path)
                    staged_param = operation.params.get("staged_dir") if operation else None
                    staged_before = evidence.get("stagedBefore")
                    candidate_names = evidence.get("previousCandidatesBefore")
                    evidence_valid = (operation is not None and operation.kind == "ReplaceDirectoryAtomic" and
                        operation.params.get("path") == path and self._valid_directory_snapshot(before) and
                        self._valid_previous_candidates(target, candidate_names))
                    if staged_param is not None:
                        evidence_valid = (evidence_valid and
                            evidence.get("stagedPath") == str(Path(staged_param).absolute()) and
                            self._valid_directory_snapshot(staged_before, allow_absent=False))
                    else:
                        evidence_valid = (evidence_valid and staged_before is None and
                                          "stagedPath" not in evidence)
                    if evidence_valid:
                        old_names = set(candidate_names)
                        candidates = sorted((candidate for candidate in target.parent.glob(
                            f".{target.name}.previous-*") if candidate.name not in old_names), key=lambda item: item.name)
                        matching = (len(candidates) == 1 and
                                    self._valid_previous_path(target, candidates[0], candidate_names) and
                                    self._snapshot(candidates[0]) == before)
                        if before.get("exists") and matching:
                            if staged_param is not None and current == staged_before:
                                completed = True
                                stdout = json.dumps({"previous": str(candidates[0]), "installed": True})
                            elif staged_param is None and current == {"exists": False}:
                                completed = True
                                stdout = json.dumps({"previous": str(candidates[0]), "installed": False})
                        elif (not before.get("exists") and not candidates and staged_param is not None and
                              current == staged_before):
                            completed = True
                            stdout = json.dumps({"previous": None, "installed": True})
                    else:
                        invalid_evidence = True
        if unchanged:
            return self._save(tx, in_flight_operation=None)
        if invalid_evidence or not completed:
            return self._record_ambiguous_effect(tx, record)
        if phase == "rollback":
            key = str(record.get("inverseKey"))
            progress = tx.inverse_progress if key in tx.inverse_progress else tx.inverse_progress + (key,)
            return self._save(tx, inverse_progress=progress, in_flight_operation=None)
        operation = next((item for item in tx.plan.operations if item.id == operation_id), None)
        if operation is None:
            return self._record_ambiguous_effect(tx, record)
        result = OperationResult(operation_id, None, stdout, "", False, 0, written_sha256)
        try:
            entry = self._command_log_entry(operation, result, "forward", forward_evidence=evidence)
        except CcError:
            return self._record_ambiguous_effect(tx, record)
        completed_ids = (tx.completed_operation_ids if operation_id in tx.completed_operation_ids else
                         tx.completed_operation_ids + (operation_id,))
        return self._save(tx, completed_operation_ids=completed_ids, command_log=tx.command_log + (entry,),
                          in_flight_operation=None)

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
            by_id = {operation.id: operation for operation in plan.operations}
            positions = {operation.id: index for index, operation in enumerate(plan.operations)}
            gate_index = next((index for index, operation in enumerate(plan.operations)
                               if operation.kind == "TimedConfirmation"), -1)
            gate_id = plan.operations[gate_index].id if gate_index >= 0 else None
            for segment in plan.segments:
                segment_ids = tuple(operation_id for operation_id in segment.operation_ids if operation_id in by_id)
                required_ids = {operation_id for operation_id in segment_ids
                                if by_id[operation_id].kind != "TimedConfirmation"}
                if partial and gate_index >= 0:
                    segment_positions = [positions[operation_id] for operation_id in segment_ids]
                    if gate_id in segment_ids:
                        required_ids = {operation_id for operation_id in required_ids
                                        if positions[operation_id] < gate_index}
                    elif not segment_positions or max(segment_positions) >= gate_index:
                        continue
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
                    tx = self._save(tx, in_flight_operation=self._in_flight_record(
                        operation, "forward", exec_ctx))
                    if operation.kind == "TimedConfirmation":
                        result = ops.run_forward(operation, exec_ctx)
                        self.faults.hit(f"after_op_effect:{operation.id}")
                        tx = self._wait_gate(tx, operation, results)
                    else:
                        result = ops.run_forward(operation, exec_ctx)
                        self.faults.hit(f"after_op_effect:{operation.id}")
                    if operation.kind == "TerminalHandoff":
                        injected = next((item for item in self.faults.hooks if item.startswith("handoff_exit:")), None)
                        if injected is not None:
                            code = int(injected.rsplit(":", 1)[1])
                            if code != 0:
                                raise CcError("handoff_failed", f"Injected handoff exit {code}", {"exitCode": code})
                    results[operation.id] = result
                    forward_evidence = ((tx.in_flight_operation or {}).get("evidence")
                                        if isinstance(tx.in_flight_operation, dict) else None)
                    log_entry = self._command_log_entry(
                        operation, result, "forward", forward_evidence=forward_evidence)
                    tx = self._save(tx, completed_operation_ids=tx.completed_operation_ids + (operation.id,),
                                    command_log=tx.command_log + (log_entry,), in_flight_operation=None)
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

    def _mutates_hypr_config(self, operation: Operation) -> bool:
        if operation.kind not in {"WriteFileAtomic", "ReplaceManagedBlock", "RemoveFile", "RestoreBackup",
                                  "EnsureDirectory", "ReplaceDirectoryAtomic"}:
            return False
        path = operation.params.get("path")
        return (isinstance(path, str) and
                Path(path).absolute().is_relative_to(self.paths.home / ".config/hypr"))

    def _command_log_entry(self, operation: Operation, result: OperationResult, phase: str,
                           inverse_of: str | None = None,
                           forward_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = {"operationId": operation.id, "argv": operation.params.get("argv", []),
                 "exit": result.exit_code, "durationMs": result.duration_ms,
                 "stdoutHead": redact(result.stdout_head)[:4096],
                 "stderrHead": redact(result.stderr_head)[:4096], "timedOut": result.timed_out,
                 "writtenSha256": result.written_sha256, "phase": phase}
        if inverse_of is not None:
            entry["inverseOf"] = inverse_of
        if operation.kind == "ReplaceDirectoryAtomic" and result.stdout_head:
            details = (self._directory_replacement_details(operation, result, forward_evidence)
                       if phase == "forward" else json.loads(result.stdout_head))
            entry["directoryReplacement"] = details
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
        tx = self._reconcile_in_flight(tx)
        exec_ctx = self._execution_context(tx.id, tx.module_id)
        try:
            exec_ctx.cache["hyprctl_configerrors_baseline"] = exec_ctx.hyprctl.configerrors()
        except Exception:
            exec_ctx.cache["hyprctl_configerrors_baseline"] = []
        results = self._results_from_log(tx)
        rollback_errors = list(tx.rollback_errors)
        skipped = list(tx.skipped_inverse_ids)
        ordered = self._inverse_order(tx.plan, tx.completed_operation_ids)
        deferred_reloads: list[tuple[Operation, str]] = []
        hypr_mutation_operation_id: str | None = None

        def inverse_items(operation: Operation) -> tuple[Operation, ...]:
            inverses = ops.build_inverse(operation, exec_ctx, results.get(operation.id))
            if operation.kind in {"WriteFileAtomic", "RemoveFile", "ReplaceManagedBlock"} and not inverses:
                inverses = (Operation(operation.id + ".restore", operation.module_id, "RestoreBackup",
                                      {"path": operation.params["path"]}, "Restore backup", (), (), 30),)
            return inverses

        def persist_inverse_attempt(current: Transaction, inverse: Operation, result: OperationResult,
                                    inverse_of: str, key: str, error: Exception | None,
                                    affected_paths: list[str]) -> Transaction:
            nonlocal rollback_errors
            log = current.command_log + (self._command_log_entry(inverse, result, "rollback", inverse_of),)
            if error is None:
                progress = (current.inverse_progress if key in current.inverse_progress else
                            current.inverse_progress + (key,))
                return self._save(current, command_log=log, inverse_progress=progress,
                                  in_flight_operation=None)

            current = self._save(current, command_log=log)
            previous_error_count = len(current.rollback_errors)
            current = self._reconcile_in_flight(current)
            if key not in current.inverse_progress and len(current.rollback_errors) == previous_error_count:
                rollback_errors = list(current.rollback_errors)
                rollback_errors.append({"code": getattr(error, "code", "rollback_failed"),
                                        "message": str(error), "operationId": inverse_of,
                                        "affectedPaths": affected_paths})
                current = self._save(current, rollback_errors=tuple(rollback_errors))
            rollback_errors = list(current.rollback_errors)
            return current

        def persist_inverse_preparation_failure(current: Transaction, inverse: Operation, inverse_of: str,
                                                key: str, error: Exception,
                                                affected_paths: list[str]) -> Transaction:
            nonlocal rollback_errors
            result = self._failed_operation_result(inverse, error, time.monotonic())
            context = {"phase": "rollback", "operationId": inverse.id, "kind": inverse.kind,
                       "preEffect": True, "inverseKey": key, "affectedPaths": affected_paths}
            rollback_errors = list(current.rollback_errors)
            rollback_errors.append({"code": getattr(error, "code", "rollback_failed"),
                                    "message": str(error), "operationId": inverse_of,
                                    "affectedPaths": affected_paths, "evidence": context})
            progress = (current.inverse_progress if key in current.inverse_progress else
                        current.inverse_progress + (key,))
            return self._save(current, command_log=current.command_log +
                              (self._command_log_entry(inverse, result, "rollback", inverse_of),),
                              rollback_errors=tuple(rollback_errors), inverse_progress=progress,
                              in_flight_operation=None)

        # Reload intent is derived from the complete durable rollback set, including operations
        # whose non-reload inverses finished in an earlier process.
        for operation in ordered:
            if operation.kind == "TimedConfirmation" or operation.inverse is None:
                continue
            for inverse in inverse_items(operation):
                if inverse.kind == "HyprctlReload":
                    deferred_reloads.append((inverse, operation.id))
                elif self._mutates_hypr_config(inverse):
                    hypr_mutation_operation_id = operation.id

        for operation in ordered:
            operation_id = operation.id
            if operation.kind == "TimedConfirmation" or operation_id in tx.rolled_back_operation_ids:
                continue
            try:
                self.faults.hit(f"before_inverse:{operation_id}")
            except CcError as error:
                rollback_errors.append({"code": error.code, "message": error.message,
                                        "operationId": operation_id,
                                        "affectedPaths": self._affected_paths(operation)})
                tx = self._save(tx, rollback_errors=tuple(rollback_errors),
                                rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
                continue
            if operation.inverse is None:
                skipped.append({"operationId": operation_id, "why": "nonreversible"})
                tx = self._save(tx, skipped_inverse_ids=tuple(skipped),
                                rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
                continue
            inverses = inverse_items(operation)
            inverse_keys = tuple(f"{operation_id}:{index}" for index, inverse in enumerate(inverses)
                                 if inverse.kind != "HyprctlReload")
            if inverse_keys and all(key in tx.inverse_progress for key in inverse_keys):
                tx = self._save(tx, rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
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
                    tx = self._save(tx, skipped_inverse_ids=tuple(skipped),
                                    rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
                    continue
            if operation.kind == "ReplaceDirectoryAtomic":
                entry = next((item for item in tx.command_log
                              if item.get("operationId") == operation.id and
                              item.get("phase", "forward") == "forward"), {})
                details = entry.get("directoryReplacement")
                raw_details: dict[str, Any] | None = None
                try:
                    parsed = json.loads(entry.get("stdoutHead", ""))
                    if (not isinstance(parsed, dict) or set(parsed) != {"previous", "installed"} or
                            not (parsed["previous"] is None or isinstance(parsed["previous"], str)) or
                            not isinstance(parsed["installed"], bool)):
                        raise CcError("rollback_conflict", "Raw directory replacement result is malformed")
                    raw_details = parsed
                    if not isinstance(details, dict):
                        raise CcError("rollback_conflict", "Directory replacement evidence is missing")
                    if (details.get("previous") != raw_details["previous"] or
                            details.get("installed") is not raw_details["installed"]):
                        raise CcError("rollback_conflict",
                                      "Directory replacement evidence contradicts the raw forward result")
                    target, previous, installed = self._validated_directory_replacement(operation, details)
                except Exception as error:
                    target = Path(operation.params["path"])
                    affected_paths = self._affected_paths(operation)
                    for evidence in (details, raw_details):
                        previous_value = evidence.get("previous") if isinstance(evidence, dict) else None
                        if isinstance(previous_value, str):
                            affected_paths.append(str(Path(previous_value).absolute()))
                    rollback_errors.append({"code": "rollback_conflict",
                                            "message": f"{error}; directory rollback preserved all paths",
                                            "operationId": operation_id,
                                            "affectedPaths": list(dict.fromkeys(affected_paths)),
                                            "data": {"directoryReplacement": details,
                                                     "rawDirectoryReplacement": raw_details,
                                                     "currentSnapshot": self._snapshot(target)}})
                    skipped.append({"operationId": operation_id, "why": "rollback_conflict"})
                    tx = self._save(tx, rollback_errors=tuple(rollback_errors),
                                    skipped_inverse_ids=tuple(skipped),
                                    rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
                    continue
                from .atomic import DirectoryReplacement
                replacement = DirectoryReplacement(target, previous, installed)
                key = f"{operation_id}:0"
                if key not in tx.inverse_progress:
                    inverse = inverses[0] if inverses else Operation(
                        operation.id + ".inverse", operation.module_id, "ReplaceDirectoryAtomic",
                        {"path": operation.params["path"], "staged_dir": details.get("previous"),
                         "allow_existing": True}, "Restore directory", (), (), 30)
                    expected = self._snapshot(replacement.previous) if replacement.previous else {"exists": False}
                    try:
                        record = self._in_flight_record(
                            replace(inverse, params={**inverse.params, "path": operation.params["path"]}),
                            "rollback", exec_ctx, inverse_key=key, inverse_index=0,
                            extra_evidence={"expected": expected})
                    except Exception as error:
                        tx = persist_inverse_preparation_failure(
                            tx, inverse, operation_id, key, error, self._affected_paths(operation))
                    else:
                        record["kind"] = "ReplaceDirectoryUndo"
                        tx = self._save(tx, in_flight_operation=record)
                        started = time.monotonic()
                        attempt_error: Exception | None = None
                        try:
                            replacement.undo()
                            self.faults.hit(f"after_inverse_effect:{operation_id}:0")
                            result = OperationResult(inverse.id, None, "", "", False,
                                                     int((time.monotonic() - started) * 1000), None)
                        except Exception as error:
                            attempt_error = error
                            result = self._failed_operation_result(inverse, error, started)
                        tx = persist_inverse_attempt(tx, inverse, result, operation_id, key,
                                                     attempt_error, self._affected_paths(operation))
                tx = self._save(tx, rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
                continue
            for index, inverse in enumerate(inverses):
                if inverse.kind == "HyprctlReload":
                    continue
                key = f"{operation_id}:{index}"
                if key in tx.inverse_progress:
                    continue
                try:
                    record = self._in_flight_record(
                        inverse, "rollback", exec_ctx, inverse_key=key, inverse_index=index)
                except Exception as error:
                    tx = persist_inverse_preparation_failure(
                        tx, inverse, operation_id, key, error, self._affected_paths(operation))
                    continue
                tx = self._save(tx, in_flight_operation=record)
                started = time.monotonic()
                attempt_error = None
                try:
                    result = ops.run_forward(inverse, exec_ctx)
                    self.faults.hit(f"after_inverse_effect:{operation_id}:{index}")
                except Exception as error:
                    attempt_error = error
                    result = self._failed_operation_result(inverse, error, started)
                tx = persist_inverse_attempt(tx, inverse, result, operation_id, key,
                                             attempt_error, self._affected_paths(operation))
            tx = self._save(tx, rolled_back_operation_ids=tx.rolled_back_operation_ids + (operation_id,))
            try:
                self.faults.hit(f"after_inverse:{operation_id}")
            except CcError as error:
                rollback_errors.append({"code": error.code, "message": error.message,
                                        "operationId": operation_id,
                                        "affectedPaths": self._affected_paths(operation)})
                tx = self._save(tx, rollback_errors=tuple(rollback_errors))

        reload_key = "deferred:hyprctl.reload"
        if (deferred_reloads or hypr_mutation_operation_id) and reload_key not in tx.inverse_progress:
            inverse, inverse_of = (deferred_reloads[-1] if deferred_reloads else
                                    (Operation("hyprctl.reload", tx.module_id, "HyprctlReload", {},
                                               "Reload Hyprland", (), (), 30),
                                     hypr_mutation_operation_id or "hyprctl.reload"))
            inverse = replace(inverse, params={"config_only": bool(deferred_reloads) and
                                                all(item.params.get("config_only")
                                                    for item, _ in deferred_reloads)})
            try:
                record = self._in_flight_record(
                    inverse, "rollback", exec_ctx, inverse_key=reload_key, inverse_index=0)
            except Exception as error:
                tx = persist_inverse_preparation_failure(tx, inverse, inverse_of, reload_key, error, [])
            else:
                tx = self._save(tx, in_flight_operation=record)
                started = time.monotonic()
                attempt_error = None
                try:
                    result = ops.run_forward(inverse, exec_ctx)
                    self.faults.hit("after_inverse_effect:hyprctl.reload:0")
                except Exception as error:
                    attempt_error = error
                    result = self._failed_operation_result(inverse, error, started)
                tx = persist_inverse_attempt(tx, inverse, result, inverse_of, reload_key,
                                             attempt_error, [])
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
        live_executor = False
        pending_ids = {item.id for item in self.journal.pending_recovery()}
        for tx in self.journal.history(limit=1_000_000):
            if tx.id in pending_ids:
                try:
                    with ApplyLock(self.paths, tx.id, tx.module_id):
                        if tx.state == "pending_handoff":
                            self._reconcile_record(tx)
                        else:
                            self._rollback_record(tx, "recovery")
                        self.journal.clear_current(tx.id)
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
        blocked = [tx.id for tx in self.journal.history(limit=1_000_000)
                   if tx.state == "rollback_failed" and
                   any(not item.get("resolved") for item in tx.rollback_errors)]
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
        deferred_reloads: list[tuple[Operation, Operation]] = []
        hypr_mutation_forward: Operation | None = None
        completed_ids = original.completed_operation_ids or tuple(item.id for item in original.plan.operations)
        inverse_order = self._inverse_order(original.plan, completed_ids)
        positions = {operation.id: index for index, operation in enumerate(original.plan.operations)}

        def append_inverses(items: Iterable[Operation]) -> None:
            nonlocal hypr_mutation_forward
            for forward in items:
                for inverse in ops.build_inverse(forward, original_exec, original_results.get(forward.id)):
                    if inverse.kind == "HyprctlReload":
                        deferred_reloads.append((inverse, forward))
                    else:
                        ordered.append((inverse, forward))
                        if self._mutates_hypr_config(inverse):
                            hypr_mutation_forward = forward

        if gate_index >= 0:
            append_inverses(item for item in inverse_order if positions[item.id] > gate_index)
            gate = original.plan.operations[gate_index]
            gate_inverse = next(iter(ops.build_inverse(gate, original_exec, original_results.get(gate.id))), gate)
            ordered.append((gate_inverse, gate))
            append_inverses(item for item in inverse_order if positions[item.id] < gate_index)
        else:
            append_inverses(inverse_order)
        if deferred_reloads or hypr_mutation_forward is not None:
            if deferred_reloads:
                reload_inverse, reload_forward = deferred_reloads[-1]
                reload_inverse = replace(reload_inverse, params={
                    "config_only": all(item.params.get("config_only") for item, _ in deferred_reloads)})
            else:
                reload_forward = hypr_mutation_forward
                assert reload_forward is not None
                reload_inverse = Operation("hyprctl.reload", original.module_id, "HyprctlReload",
                                           {"config_only": False}, "Reload Hyprland", (), (), 30)
            ordered.append((reload_inverse, reload_forward))

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
            try:
                exec_ctx.cache["hyprctl_configerrors_baseline"] = exec_ctx.hyprctl.configerrors()
            except Exception:
                exec_ctx.cache["hyprctl_configerrors_baseline"] = []
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
                tx = self._save(tx, in_flight_operation=self._in_flight_record(
                    operation, "forward", exec_ctx))
                if operation.kind == "TimedConfirmation":
                    result = ops.run_forward(operation, exec_ctx)
                    self.faults.hit(f"after_op_effect:{operation.id}")
                    tx = self._wait_gate(tx, operation, results, verify_partial=False)
                else:
                    result = ops.run_forward(operation, exec_ctx)
                    self.faults.hit(f"after_op_effect:{operation.id}")
                results[operation.id] = result
                forward_evidence = ((tx.in_flight_operation or {}).get("evidence")
                                    if isinstance(tx.in_flight_operation, dict) else None)
                entry = self._command_log_entry(
                    operation, result, "forward", forward_evidence=forward_evidence)
                tx = self._save(tx, completed_operation_ids=tx.completed_operation_ids + (operation.id,),
                                command_log=tx.command_log + (entry,), in_flight_operation=None)
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
