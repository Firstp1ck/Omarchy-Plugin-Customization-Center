from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import (Capabilities, Capability, CcError, Operation, OperationResult, Plan,
    PlanSegment, ResourceClaim, Status, Transaction, VerifyResult, ops)
from customization_center.core.context import build_context
from customization_center.core.types import ValidationResult
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths
from customization_center.core.locking import ApplyLock
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests/fixtures/modules/hello/tests/fixtures/sample-draft.json"


def _hold_apply_lock(runtime: str, ready):
    with ApplyLock(runtime, "holder", "hello"):
        ready.set()
        time.sleep(2)


def _executor(paths):
    registry = load_registry(ROOT, [ROOT / "tests/fixtures/modules/hello"], paths)
    return Executor(ROOT, registry, paths, ROOT / "backend/ccctl"), registry


def _hello_setup(stub_command):
    stub_command("hello-command", {"exit_code": 0})
    paths = Paths.from_env(); executor, registry = _executor(paths)
    module = registry.module("hello")
    status = module.status(build_context("hello", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    return paths, executor, status, json.loads(SAMPLE.read_text())


def test_timeout_rollback_retries_lock_until_released(isolated_home):
    paths = Paths.from_env(); executor, registry = _executor(paths)
    revision = registry.module("hello").status(build_context("hello", "read", paths=paths,
        registry=registry.view, plugin_dir=ROOT)).revision
    plan = Plan("hello", revision, (), (), "waiting", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    tx = Transaction(txid, "hello", "awaiting_confirmation", now, now, plan, revision, None,
                     (), (), {}, None, {"deadline":"2099-01-01T00:00:00Z"}, (), ())
    executor.journal.create(tx)
    ready = multiprocessing.Event(); process = multiprocessing.Process(target=_hold_apply_lock,
        args=(str(paths.runtime), ready)); process.start(); assert ready.wait(2)
    started = time.monotonic(); result = executor.rollback(txid, "timeout"); elapsed = time.monotonic() - started
    process.join(5)
    assert elapsed >= 1.8 and result.state == "rolled_back"


def test_stale_digest_and_confirmation_errors(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    with pytest.raises(CcError) as caught: executor.apply("hello", draft, "stale")
    assert caught.value.code == "stale_revision"
    with pytest.raises(CcError) as caught: executor.apply("hello", draft, status.revision, "0" * 64)
    assert caught.value.code == "stale_revision"


def test_missing_nonreversible_confirmation_lists_key(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    operation = Operation("hello.0001", "hello", "TerminalHandoff",
        {"argv":["true"],"title":"handoff","wrapped":False}, "handoff", None, (), 5)
    plan = Plan("hello", "r", (operation,), (), "confirm", (), (operation.id,))
    with pytest.raises(CcError) as caught: executor._validate_plan(plan, ())
    assert caught.value.code == "nonreversible_requires_confirmation"
    assert caught.value.data["missingKeys"] == [operation.id]


def test_duplicate_exclusive_claims_fail_before_backup(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    plan = Plan("hello", "r", (), (ResourceClaim("same", "exclusive"), ResourceClaim("same", "exclusive")),
                "conflict", (), ())
    with pytest.raises(CcError) as caught: executor._validate_plan(plan, ())
    assert caught.value.code == "resource_conflict" and not executor.backups.root.exists()


def test_user_rollback_preserves_concurrent_file_edit(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    committed = executor.apply("hello", draft, status.revision)
    target = paths.module_config("hello") / "hello.json"; target.write_text('{"message":"user edit"}')
    inverse = executor.rollback(committed.id, force_stale=True)
    assert target.read_text() == '{"message":"user edit"}'
    assert {item["why"] for item in inverse.skipped_inverse_ids} == {"rollback_conflict"}


def test_gate_partial_verify_includes_segment_ending_at_gate(isolated_home):
    paths = Paths.from_env(); called = []
    class Module:
        id = "first"
        def status(self, ctx): return Status(self.id, "r", {}, (), 1)
        def verify(self, ctx, plan, status, results): called.append(set(results)); return VerifyResult("pass", "full", "")
    module = Module()
    registry = SimpleNamespace(view=SimpleNamespace(module=lambda module_id: module,
        entry=lambda module_id: SimpleNamespace(metadata={"extraWritablePaths": []})))
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    op = SimpleNamespace(id="first.0001", kind="WriteFileAtomic")
    gate = SimpleNamespace(id="first.0002", kind="TimedConfirmation")
    second = SimpleNamespace(id="second.0001", kind="RunCommand")
    plan = SimpleNamespace(segments=(PlanSegment("first", "r", (op.id, gate.id)),
        PlanSegment("second", "r", (second.id,))), operations=(op, gate, second))
    executor._ctx = lambda *args: SimpleNamespace()
    result = OperationResult(op.id, None, "", "", False, 0, "hash")
    assert executor._verify(plan, {op.id: result}, partial=True).state == "pass"
    assert called == [{op.id}]


def test_reconcile_passes_command_log_results(isolated_home):
    paths = Paths.from_env(); seen = []
    class Module:
        id = "fake"
        def status(self, ctx): return Status("fake", "after", {}, (), 1)
        def verify(self, ctx, plan, status, results): seen.append(results); return VerifyResult("pass", "full", "")
    module = Module(); registry = SimpleNamespace(view=SimpleNamespace(module=lambda _: module,
        entry=lambda _: SimpleNamespace(metadata={"extraWritablePaths": []})))
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl"); executor._ctx = lambda *args: SimpleNamespace()
    operation = Operation("fake.0001", "fake", "RunCommand", {}, "run", (), (), 1)
    plan = Plan("fake", "before", (operation,), (), "fake", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    tx = Transaction(txid, "fake", "pending_handoff", now, now, plan, "before", None,
        (operation.id,), (), {}, None, None, (), (), command_log=({"operationId": operation.id,
        "argv": ["true"], "exit": 0, "durationMs": 1, "stdoutHead": "ok", "stderrHead": "",
        "timedOut": False, "writtenSha256": "abc"},))
    executor.journal.create(tx)
    result = executor._reconcile_record(tx)
    assert result.state == "committed" and seen[0][operation.id].written_sha256 == "abc"


def test_directory_replacement_survives_recovery(isolated_home):
    paths = Paths.from_env(); executor, registry = _executor(paths)
    target = paths.module_config("hello") / "theme"; target.mkdir(parents=True); (target / "value").write_text("old")
    staged = paths.staging_dir("hello", "swap"); (staged / "value").write_text("new")
    ctx = build_context("hello", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT)
    operation = ops.ReplaceDirectoryAtomic(ctx, target, staged, allow_existing=True)
    exec_ctx = executor._execution_context("placeholder", "hello")
    result = ops.run_forward(operation, exec_ctx)
    plan = Plan("hello", "before", (operation,), (), "swap", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    # Move the replacement cache out of process and rely only on the persisted record.
    details = json.loads(result.stdout_head); exec_ctx.cache.clear()
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
        (operation.id,), (), {}, None, None, (), (), command_log=({"operationId": operation.id,
        "argv": [], "exit": None, "durationMs": 1, "stdoutHead": result.stdout_head, "stderrHead": "",
        "timedOut": False, "writtenSha256": None, "directoryReplacement": details},))
    executor.journal.create(tx)
    executor.recover()
    assert (target / "value").read_text() == "old"


def test_recover_keeps_young_staging_and_removes_old(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    young = paths.staging_dir("hello", "young"); old = paths.staging_dir("hello", "old")
    old_time = time.time() - 3600; os.utime(old, (old_time, old_time))
    executor.recover()
    assert young.exists() and not old.exists()


class GateModule:
    id = "gate"
    schema_version = 1
    def capabilities(self, ctx):
        return Capabilities(self.id, (Capability("timed_confirmation", True, ""),), ctx.clock.now_iso())
    def status(self, ctx):
        values = {}
        for name in ("pre", "post"):
            path = ctx.paths.module_config(self.id) / name
            values[name] = path.read_text() if path.exists() else None
        return Status(self.id, ctx.revision_of(values), values, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        root = ctx.paths.module_config(self.id)
        pre = ops.WriteFileAtomic(ctx, root / "pre", "new-pre", "0600")
        gate = ops.TimedConfirmation(ctx, 1)
        post = ops.WriteFileAtomic(ctx, root / "post", "new-post", "0600")
        return Plan(self.id, status.revision, (pre, gate, post), (), "gate", (), ())
    def verify(self, ctx, plan, status, results): return VerifyResult("pass", "full", "")


class FixtureRegistry:
    def __init__(self, module):
        self.view = self
        self._module = module
    def module(self, module_id):
        if module_id != self._module.id: raise CcError("unknown_module", module_id)
        return self._module
    def entry(self, module_id):
        self.module(module_id)
        return SimpleNamespace(metadata={"extraWritablePaths": [], "draftSchema": "tests/fixtures/any-draft-v1.json"}, directory=ROOT)


def test_gate_confirm_token_and_timeout(isolated_home, stub_command, monkeypatch):
    stub_command("systemd-run", {"exit_code": 0}); stub_command("systemctl", {"exit_code": 0})
    paths = Paths.from_env(); registry = FixtureRegistry(GateModule())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    status = registry.module("gate").status(build_context("gate", "read", paths=paths, registry=registry, plugin_dir=ROOT))
    observed = {}
    def confirmer():
        pending_root = paths.runtime / "pending-confirm"
        deadline = time.time() + 3
        while time.time() < deadline:
            files = [path for path in pending_root.glob("*") if not path.name.startswith(".")] if pending_root.exists() else []
            if files:
                token = files[0].read_text().strip(); observed["token"] = token
                cli = subprocess.run([str(ROOT / "backend/ccctl"), "transaction", "current"],
                    text=True, capture_output=True, timeout=5, env=dict(os.environ))
                envelope = json.loads(cli.stdout.splitlines()[-1])
                assert envelope["data"]["confirmationToken"] == token
                with pytest.raises(CcError) as caught: executor.confirm(files[0].name, "wrong")
                assert caught.value.code == "confirmation_invalid"
                executor.confirm(files[0].name, token)
                observed["gone"] = not files[0].exists()
                return
            time.sleep(.02)
    thread = threading.Thread(target=confirmer); thread.start()
    tx = executor.apply("gate", {"schemaVersion": 1}, status.revision)
    thread.join(timeout=3)
    assert tx.state == "committed" and observed == {"token": observed["token"], "gone": True}
    transaction = subprocess.run([str(ROOT / "backend/ccctl"), "transaction", tx.id],
        text=True, capture_output=True, timeout=5, env=dict(os.environ))
    assert "confirmationToken" not in json.loads(transaction.stdout.splitlines()[-1])["data"]
    original_run_forward = ops.run_forward
    sequence = []
    def recording_forward(operation, exec_ctx):
        sequence.append((operation.id, operation.kind))
        return original_run_forward(operation, exec_ctx)
    monkeypatch.setattr(ops, "run_forward", recording_forward)
    # A timed-out inverse gate re-runs the post-gate forwards and keeps the confirmed state.
    with pytest.raises(CcError) as caught: executor.rollback(tx.id)
    assert caught.value.code == "confirmation_expired"
    assert sequence == [("gate.0001", "RestoreBackup"), ("gate.0002", "TimedConfirmation"),
                        ("gate.0005", "WriteFileAtomic")]
    root = paths.module_config("gate")
    assert (root / "pre").read_text() == "new-pre" and (root / "post").read_text() == "new-post"
    # Confirmed undo runs post-gate inverses, the gate, then pre-gate inverses.
    sequence.clear()
    undo_thread = threading.Thread(target=confirmer); undo_thread.start(); executor.rollback(tx.id); undo_thread.join(timeout=3)
    assert sequence == [("gate.0001", "RestoreBackup"), ("gate.0002", "TimedConfirmation"),
                        ("gate.0003", "RestoreBackup")]
    status = registry.module("gate").status(build_context("gate", "read", paths=paths, registry=registry, plugin_dir=ROOT))
    with pytest.raises(CcError) as caught:
        executor.apply("gate", {"schemaVersion": 1}, status.revision)
    assert caught.value.code == "confirmation_expired"
    expired = executor.journal.history(limit=1)[0]
    assert expired.state == "rolled_back" and expired.reason == "timeout"


class HandoffModule:
    id = "handoff"
    schema_version = 1
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx): return Status(self.id, "stable", {}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        operation = ops.TerminalHandoff(ctx, ["handoff-command"], "Handoff", wrapped=draft.get("wrapped", True))
        return Plan(self.id, status.revision, (operation,), (), "handoff", (), (operation.id,))
    def verify(self, ctx, plan, status, results):
        return VerifyResult("pass" if plan.operations[0].id in results else "pending", "full", "")


def test_handoff_reconcile_and_abandon(isolated_home, stub_command):
    stub_command("omarchy-launch-floating-terminal-with-presentation", {"exit_code": 0})
    stub_command("handoff-command", {"exit_code": 0})
    paths = Paths.from_env(); registry = FixtureRegistry(HandoffModule())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    tx = executor.apply("handoff", {"schemaVersion": 1, "wrapped": True}, "stable",
                        confirmations=("handoff.0001",))
    assert tx.state == "pending_handoff"
    sentinel = paths.state / "handoffs" / f"{tx.id}.json"; sentinel.parent.mkdir(parents=True)
    sentinel.write_text('{"exitCode":0,"finishedAt":"2024-01-01T00:00:00Z"}')
    assert executor.reconcile(tx.id).state == "committed"
    pending = executor.apply("handoff", {"schemaVersion": 1, "wrapped": True}, "stable",
                             confirmations=("handoff.0001",))
    assert executor.reconcile(pending.id).state == "pending_handoff"
    assert executor.abandon(pending.id).state == "rolled_back"
    failed = executor.apply("handoff", {"schemaVersion": 1, "wrapped": True}, "stable",
                            confirmations=("handoff.0001",))
    bad = paths.state / "handoffs" / f"{failed.id}.json"; bad.write_text('{"exitCode":7,"finishedAt":"x"}')
    assert executor.reconcile(failed.id).state == "rolled_back"
    unwrapped = executor.apply("handoff", {"schemaVersion": 1, "wrapped": False}, "stable",
                               confirmations=("handoff.0001",))
    assert executor.reconcile(unwrapped.id).state == "committed"


def test_concurrent_reconcile_wins_over_abandon(isolated_home, stub_command):
    stub_command("omarchy-launch-floating-terminal-with-presentation", {"exit_code": 0})
    class SlowHandoff(HandoffModule):
        def verify(self, ctx, plan, status, results):
            time.sleep(1)
            return super().verify(ctx, plan, status, results)
    paths = Paths.from_env(); registry = FixtureRegistry(SlowHandoff())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    tx = executor.apply("handoff", {"schemaVersion":1,"wrapped":True}, "stable",
                        confirmations=("handoff.0001",))
    sentinel = paths.state / "handoffs" / f"{tx.id}.json"; sentinel.parent.mkdir(parents=True)
    sentinel.write_text('{"exitCode":0,"finishedAt":"2024-01-01T00:00:00Z"}')
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("tx", executor.reconcile(tx.id)))
    thread.start(); time.sleep(.1)
    with pytest.raises(CcError) as caught: executor.abandon(tx.id)
    thread.join(timeout=3)
    assert caught.value.code == "transaction_state_invalid"
    assert result["tx"].state == "committed" and executor.journal.load(tx.id).state == "committed"


def test_restore_and_resolve_clear_file_and_non_file_failures(isolated_home, stub_command):
    stub_command("hello-command", {"exit_code": 0})
    paths = Paths.from_env(); executor, registry = _executor(paths)
    target = paths.module_config("hello") / "hello.json"; target.parent.mkdir(parents=True); target.write_text('{"message":"before"}')
    manual = paths.module_config("hello") / "theme-directory"
    txid = str(uuid.uuid4()); backups = executor.backups.take(txid, [target]); target.write_text('{"message":"broken"}')
    operation = Operation("hello.0001", "hello", "ReplaceDirectoryAtomic",
        {"path": str(manual), "staged_dir": None, "allow_existing": True},
        "directory swap", (), (str(target),), 30)
    plan = Plan("hello", "r", (operation,), (), "failure", (), ())
    now = "2024-01-01T00:00:00Z"
    errors = ({"code":"rollback_failed","message":"directory inverse","operationId":operation.id,
               "affectedPaths":[str(target), str(manual)]},
              {"code":"rollback_failed","message":"reload","operationId":"hyprctl.reload","affectedPaths":[]})
    tx = Transaction(txid, "hello", "rollback_failed", now, now, plan, "r", None, (), (), backups,
                     None, None, (), errors)
    executor.journal.create(tx)
    status = registry.module("hello").status(build_context("hello", "read", paths=paths,
        registry=registry.view, plugin_dir=ROOT))
    with pytest.raises(CcError) as caught: executor.apply("hello", {"schemaVersion":1,"message":"x"}, status.revision)
    assert caught.value.code == "recovery_required"
    recovery = executor._recovery_data(tx)
    assert recovery["manualPaths"] == [{"operationId": operation.id, "path": str(manual)}]
    assert recovery["recoveryCommands"] == [f"{ROOT / 'backend/ccctl'} restore {txid} --path {target}"]
    restored = executor.restore(txid, target)
    assert restored.rollback_errors[0].get("resolved") is not True
    assert target.read_text() == '{"message":"before"}'
    # After backed paths are restored, manual acknowledgement may resolve the directory path.
    resolved_directory = executor.resolve(txid, operation.id)
    assert resolved_directory.rollback_errors[0]["resolved"] is True
    resolved = executor.resolve(txid, "hyprctl.reload")
    assert all(item.get("resolved") for item in resolved.rollback_errors)
    assert executor.recover()["required"] is False
    status = registry.module("hello").status(build_context("hello", "read", paths=paths,
        registry=registry.view, plugin_dir=ROOT))
    assert executor.apply("hello", {"schemaVersion":1,"message":"accepted"}, status.revision).state == "committed"


def test_revision_drift_after_rollback_is_recorded(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    plan = Plan("hello", "different", (), (), "drift", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    tx = Transaction(txid, "hello", "applying", now, now, plan, "different", None,
                     (), (), {}, None, None, (), ())
    executor.journal.create(tx)
    rolled = executor.rollback(txid, "recovery")
    assert rolled.state == "rolled_back"
    assert any(item["code"] == "revision_drift_after_rollback" for item in rolled.errors)


def test_abandon_reloads_committed_state(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    plan = Plan("hello", "r", (), (), "handoff", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    tx = Transaction(txid, "hello", "committed", now, now, plan, "r", "r", (), (), {}, None, None, (), ())
    executor.journal.create(tx)
    with pytest.raises(CcError) as caught: executor.abandon(txid)
    assert caught.value.code == "transaction_state_invalid"
