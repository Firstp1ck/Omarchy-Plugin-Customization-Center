from __future__ import annotations

import json
import multiprocessing
import os
import shutil
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
from customization_center.core.executor import Executor, FaultPlan
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


def test_fault_plan_only_loads_regular_file_under_private_runtime_tmp(isolated_home, monkeypatch):
    paths = Paths.from_env()
    outside = paths.home / "faults.json"
    outside.write_text('{"hooks":["outside"]}')
    monkeypatch.setenv("CC_TEST_FAULTS", str(outside))
    assert FaultPlan.from_environment(paths).hooks == set()

    private = paths.private_tmpfile("-faults.json")
    private.write_text('{"hooks":["safe"]}')
    monkeypatch.setenv("CC_TEST_FAULTS", str(private))
    assert FaultPlan.from_environment(paths).hooks == {"safe"}

    linked = private.with_name("linked-faults.json")
    linked.symlink_to(private)
    monkeypatch.setenv("CC_TEST_FAULTS", str(linked))
    assert FaultPlan.from_environment(paths).hooks == set()


def _hard_exit_after_first_forward_effect(paths, draft):
    executor, registry = _executor(paths)
    run_forward = ops.run_forward
    def exit_after_effect(operation, exec_ctx):
        result = run_forward(operation, exec_ctx)
        if operation.id == "hello.0001":
            os._exit(91)
        return result
    ops.run_forward = exit_after_effect
    revision = registry.module("hello").status(executor._ctx("hello", "read")).revision
    executor.apply("hello", draft, revision)


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


def test_before_verify_rollback_logs_every_executed_inverse(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    executor.faults.hooks.add("before_verify")
    with pytest.raises(CcError) as caught:
        executor.apply("hello", draft, status.revision)
    assert caught.value.code == "internal_error"
    tx = executor.journal.history(limit=1)[0]
    forward_ids = {entry["operationId"] for entry in tx.command_log if entry["phase"] == "forward"}
    rollback = [entry for entry in tx.command_log if entry["phase"] == "rollback"]
    assert len(rollback) == 2
    assert {entry["inverseOf"] for entry in rollback} == forward_ids


def test_failing_external_inverse_is_not_rerun_and_blocks_apply(isolated_home, stub_command):
    undo_effects = []

    def hello_command(request):
        if request["argv"][1:] == ["undo"]:
            undo_effects.append("performed")
            return {"exit_code": 7, "stderr": "undo failed after effect"}
        return {"exit_code": 0}

    paths, executor, status, draft = _hello_setup(stub_command)
    stub_command("hello-command", hello_command)
    executor.faults.hooks.add("before_verify")
    with pytest.raises(CcError) as caught:
        executor.apply("hello", draft, status.revision)
    assert caught.value.code == "rollback_failed"

    tx = executor.journal.history(limit=1)[0]
    failed = next(entry for entry in tx.command_log if entry.get("phase") == "rollback" and entry["exit"] == 7)
    assert failed["inverseOf"] in {entry["operationId"] for entry in tx.command_log if entry["phase"] == "forward"}
    assert len(tx.rollback_errors) == 1
    ambiguity = tx.rollback_errors[0]
    assert ambiguity["code"] == "recovery_required"
    assert ambiguity["evidence"]["kind"] == "RunCommand"
    assert ambiguity["evidence"]["phase"] == "rollback"
    assert undo_effects == ["performed"]

    recovered = executor.recover()
    assert recovered["blocked"] == [tx.id]
    assert executor.journal.load(tx.id).state == "rollback_failed"
    assert undo_effects == ["performed"]

    current = executor.registry.module("hello").status(executor._ctx("hello", "read"))
    with pytest.raises(CcError) as blocked:
        executor.apply("hello", draft, current.revision)
    assert blocked.value.code == "recovery_required"
    assert undo_effects == ["performed"]


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


def _command_operation(operation_id, *, inverse_after=()):
    return Operation(operation_id, "hello", "RunCommand",
        {"argv": ["true"], "timeout_s": 1.0, "expect_exit": 0, "capture_limit": 16,
         "env_extra": {}, "stdin": None, "wait_policy": "exit"}, "run", (), (), 1.0, None,
        tuple(inverse_after))


def test_inverse_after_validation_order_partial_completion_and_digest(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    first = _command_operation("hello.0001")
    second = _command_operation("hello.0002", inverse_after=(first.id,))
    third = _command_operation("hello.0003", inverse_after=(second.id,))
    plan = Plan("hello", "r", (first, second, third), (), "ordered", (), ())
    executor._validate_plan(plan, ())
    assert [item.id for item in executor._inverse_order(plan, (first.id, second.id, third.id))] == [
        first.id, second.id, third.id]
    assert [item.id for item in executor._inverse_order(plan, (first.id, third.id))] == [third.id, first.id]
    assert [item.id for item in executor._inverse_order(plan, (second.id, third.id))] == [second.id, third.id]
    plain = replace(plan, operations=tuple(replace(item, inverse_after=()) for item in plan.operations))
    assert [item.id for item in executor._inverse_order(plain, (first.id, second.id, third.id))] == [
        third.id, second.id, first.id]
    assert Executor.digest(plan) != Executor.digest(plain)
    assert Plan.from_json(plan.to_json()) == plan
    composed_first = replace(first, id="first.0001", module_id="first")
    composed_second = replace(second, id="second.0001", module_id="second",
                              inverse_after=(composed_first.id,))
    composed = replace(plan, operations=(composed_first, composed_second),
                       segments=(PlanSegment("first", "r1", (composed_first.id,)),
                                 PlanSegment("second", "r2", (composed_second.id,))))
    executor._validate_plan(composed, ())
    assert [item.id for item in executor._inverse_order(
        composed, (composed_first.id, composed_second.id))] == [composed_first.id, composed_second.id]

    missing = replace(plan, operations=(first, replace(second, inverse_after=("hello.9999",)), third))
    with pytest.raises(CcError) as caught:
        executor._validate_plan(missing, ())
    assert "missing operation" in caught.value.message
    forward = replace(plan, operations=(replace(first, inverse_after=(second.id,)),
                                        replace(second, inverse_after=()), third))
    with pytest.raises(CcError) as caught:
        executor._validate_plan(forward, ())
    assert "earlier operation" in caught.value.message
    cycle = replace(plan, operations=(replace(first, inverse_after=(second.id,)),
                                      replace(second, inverse_after=(first.id,)), third))
    with pytest.raises(CcError) as caught:
        executor._validate_plan(cycle, ())
    assert "cycle" in caught.value.message
    gate = Operation("hello.0002", "hello", "TimedConfirmation", {"seconds": 1}, "gate", (), (), 1.0)
    post_gate = replace(third, inverse_after=(first.id,))
    with pytest.raises(CcError) as caught:
        executor._validate_inverse_dependencies((first, gate, post_gate))
    assert "confirmation rollback boundary" in caught.value.message


@pytest.mark.parametrize(("segments", "message"), [
    ((PlanSegment("first", "r1", ("first.0001",)),), "omit"),
    ((PlanSegment("first", "r1", ("first.9999", "first.0001")),
      PlanSegment("second", "r2", ("second.0001",))), "unknown"),
    ((PlanSegment("first", "r1", ("first.0001",)),
      PlanSegment("second", "r2", ("first.0001", "second.0001"))), "multiple"),
    ((PlanSegment("second", "r2", ("first.0001", "second.0001")),), "owned"),
])
def test_composed_segments_must_exactly_partition_owned_operations(isolated_home, segments, message):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    first = replace(_command_operation("first.0001"), module_id="first")
    second = replace(_command_operation("second.0001"), module_id="second")
    plan = Plan("hello", "r", (first, second), (), "composed", (), (), segments=segments)
    with pytest.raises(CcError) as caught:
        executor._validate_plan(plan, ())
    assert message in caught.value.message


def test_composed_plan_cannot_omit_segments_entirely(isolated_home):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    foreign = replace(_command_operation("second.0001"), module_id="second")
    with pytest.raises(CcError) as caught:
        executor._validate_plan(Plan("hello", "r", (foreign,), (), "composed", (), ()), ())
    assert caught.value.code == "unsupported_config" and "declare segments" in caught.value.message

    local = _command_operation("hello.0001")
    executor._validate_plan(Plan("hello", "r", (local,), (), "single module", (), ()), ())


def test_user_rollback_preserves_concurrent_file_edit(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    committed = executor.apply("hello", draft, status.revision)
    target = paths.module_config("hello") / "hello.json"; target.write_text('{"message":"user edit"}')
    inverse = executor.rollback(committed.id, force_stale=True)
    assert target.read_text() == '{"message":"user edit"}'
    assert {item["why"] for item in inverse.skipped_inverse_ids} == {"rollback_conflict"}


def test_gate_partial_verify_includes_gate_segment_but_ignores_its_post_gate_ids(isolated_home):
    paths = Paths.from_env(); called = []
    class Module:
        def __init__(self, module_id): self.id = module_id
        def status(self, ctx): return Status(self.id, "r", {}, (), 1)
        def verify(self, ctx, plan, status, results): called.append((self.id, set(results))); return VerifyResult("pass", "full", "")
    modules = {module_id: Module(module_id) for module_id in ("first", "second")}
    registry = SimpleNamespace(view=SimpleNamespace(module=lambda module_id: modules[module_id],
        entry=lambda module_id: SimpleNamespace(metadata={"extraWritablePaths": []})))
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    op = SimpleNamespace(id="first.0001", kind="WriteFileAtomic")
    gate = SimpleNamespace(id="first.0002", kind="TimedConfirmation")
    post_gate = SimpleNamespace(id="first.0003", kind="WriteFileAtomic")
    second = SimpleNamespace(id="second.0001", kind="RunCommand")
    plan = SimpleNamespace(segments=(PlanSegment("first", "r", (op.id, gate.id, post_gate.id)),
        PlanSegment("second", "r", (second.id,))), operations=(op, gate, post_gate, second))
    executor._ctx = lambda *args: SimpleNamespace()
    result = OperationResult(op.id, None, "", "", False, 0, "hash")
    assert executor._verify(plan, {op.id: result}, partial=True).state == "pass"
    assert called == [("first", {op.id})]


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
        "timedOut": False, "writtenSha256": "abc", "phase": "forward"},
        {"operationId": operation.id, "argv": ["false"], "exit": 7, "durationMs": 1,
         "stdoutHead": "", "stderrHead": "failed", "timedOut": False, "writtenSha256": None,
         "phase": "rollback", "inverseOf": operation.id}))
    executor.journal.create(tx)
    result = executor._reconcile_record(tx)
    assert result.state == "committed" and seen[0][operation.id].written_sha256 == "abc"
    assert seen[0][operation.id].exit_code == 0


@pytest.mark.parametrize(("case", "completed", "installed"), [
    ("completed", True, True),
    ("rename-gap", False, None),
    ("stale-only", False, None),
    ("wrong-target", False, None),
    ("extra-fifo", False, None),
    ("legacy", False, None),
    ("legacy-staged", False, None),
])
def test_directory_replacement_forward_reconciliation_is_exact(
        isolated_home, case, completed, installed):
    if case == "extra-fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("os.mkfifo is unavailable")
    paths = Paths.from_env(); executor, registry = _executor(paths)
    target = paths.module_config("hello") / "reconcile-theme"
    target.mkdir(parents=True); target.chmod(0o755); (target / "value").write_text("old")
    if case == "stale-only":
        stale = target.parent / f".{target.name}.previous-stale"
        stale.mkdir(); stale.chmod(0o755); (stale / "value").write_text("old")
    staged = paths.staging_dir("hello", f"directory-{case}"); (staged / "value").write_text("new")
    operation = ops.ReplaceDirectoryAtomic(
        build_context("hello", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT),
        target, staged, allow_existing=True)
    plan = Plan("hello", "before", (operation,), (), "directory", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    record = executor._in_flight_record(operation, "forward", executor._execution_context(txid, "hello"))
    if case == "legacy":
        record["evidence"].pop("previousCandidatesBefore")
    elif case == "legacy-staged":
        record["evidence"].pop("stagedBefore")
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
                     (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx)

    if case == "stale-only":
        os.rename(target, target.parent / "discarded-target")
        os.rename(staged, target)
    else:
        previous = target.parent / f".{target.name}.previous-{'a' * 32}"
        os.rename(target, previous)
        if case in {"completed", "extra-fifo", "legacy", "legacy-staged"}:
            os.rename(staged, target)
            if case == "extra-fifo":
                os.mkfifo(target / "unexpected-fifo")
        elif case == "wrong-target":
            target.mkdir(); (target / "value").write_text("unrelated")

    reconciled = executor._reconcile_in_flight(tx)
    assert (operation.id in reconciled.completed_operation_ids) is completed
    if completed:
        details = json.loads(reconciled.command_log[-1]["stdoutHead"])
        assert details["installed"] is installed
        assert Path(details["previous"]).name == f".{target.name}.previous-{'a' * 32}"
        durable = reconciled.command_log[-1]["directoryReplacement"]
        assert durable["expectedInstalledSnapshot"] == record["evidence"]["stagedBefore"]
        assert durable["installedSnapshot"] == executor._snapshot(target)
        assert durable["originalTargetSnapshot"] == record["evidence"]["before"]
        assert durable["previousCandidatesBefore"] == record["evidence"]["previousCandidatesBefore"]
    else:
        assert reconciled.rollback_errors[-1]["code"] == "recovery_required"


def test_directory_replacement_absent_target_requires_exact_staged_snapshot(isolated_home):
    paths = Paths.from_env(); executor, registry = _executor(paths)
    target = paths.module_config("hello") / "new-theme"
    staged = paths.staging_dir("hello", "absent-target"); (staged / "value").write_text("new")
    operation = ops.ReplaceDirectoryAtomic(
        build_context("hello", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), target, staged)
    plan = Plan("hello", "before", (operation,), (), "directory", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    record = executor._in_flight_record(operation, "forward", executor._execution_context(txid, "hello"))
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
                     (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staged, target)
    reconciled = executor._reconcile_in_flight(tx)
    assert reconciled.completed_operation_ids == (operation.id,)
    assert json.loads(reconciled.command_log[-1]["stdoutHead"]) == {"previous": None, "installed": True}
    assert reconciled.command_log[-1]["directoryReplacement"]["installedSnapshot"] == executor._snapshot(target)


def test_directory_removal_command_log_records_bound_absent_post_image(isolated_home):
    paths = Paths.from_env(); executor, registry = _executor(paths)
    target = paths.module_config("hello") / "removed-theme"
    target.mkdir(parents=True); (target / "value").write_text("old")
    operation = ops.ReplaceDirectoryAtomic(
        build_context("hello", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT),
        target, None, allow_existing=True)
    exec_ctx = executor._execution_context("placeholder", "hello")
    record = executor._in_flight_record(operation, "forward", exec_ctx)
    result = ops.run_forward(operation, exec_ctx)
    entry = executor._command_log_entry(
        operation, result, "forward", forward_evidence=record["evidence"])
    details = entry["directoryReplacement"]
    assert details["expectedInstalledSnapshot"] == {"exists": False}
    assert details["installedSnapshot"] == {"exists": False}
    assert details["originalTargetSnapshot"] == record["evidence"]["before"]


def _completed_directory_replacement(paths, executor, registry, name):
    target = paths.module_config("hello") / name
    target.mkdir(parents=True); (target / "value").write_text("old")
    staged = paths.staging_dir("hello", f"swap-{name}"); (staged / "value").write_text("new")
    operation = ops.ReplaceDirectoryAtomic(
        build_context("hello", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT),
        target, staged, allow_existing=True)
    exec_ctx = executor._execution_context("placeholder", "hello")
    record = executor._in_flight_record(operation, "forward", exec_ctx)
    result = ops.run_forward(operation, exec_ctx)
    entry = executor._command_log_entry(
        operation, result, "forward", forward_evidence=record["evidence"])
    return target, operation, entry


def _recover_directory_record(executor, operation, entry):
    plan = Plan("hello", "before", (operation,), (), "swap", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
        (operation.id,), (), {}, None, None, (), (), command_log=(entry,))
    executor.journal.create(tx)
    recovery = executor.recover()
    return recovery, executor.journal.load(txid)


def test_directory_replacement_survives_recovery_with_exact_bound_evidence(isolated_home):
    paths = Paths.from_env(); executor, registry = _executor(paths)
    target, operation, entry = _completed_directory_replacement(paths, executor, registry, "theme")
    previous = Path(entry["directoryReplacement"]["previous"])
    recovery, recovered = _recover_directory_record(executor, operation, entry)
    assert recovery["required"] is False and recovered.state == "rolled_back"
    assert (target / "value").read_text() == "old"
    assert not previous.exists()


@pytest.mark.parametrize("case", [
    "mutated", "forged-installed", "legacy", "forged-previous", "forged-previous-clone",
    "mutated-previous", "forged-augmented-installed", "missing-raw", "malformed-raw",
])
def test_directory_replacement_recovery_conflicts_never_reach_undo(
        isolated_home, monkeypatch, case):
    from customization_center.core.atomic import DirectoryReplacement

    paths = Paths.from_env(); executor, registry = _executor(paths)
    target, operation, entry = _completed_directory_replacement(
        paths, executor, registry, f"theme-{case}")
    details = entry["directoryReplacement"]
    previous = Path(details["previous"])
    if case in {"mutated", "forged-installed"}:
        (target / "value").write_text("user-edit")
        if case == "forged-installed":
            details["installedSnapshot"] = executor._snapshot(target)
    elif case == "legacy":
        details.pop("expectedInstalledSnapshot")
    elif case in {"forged-previous", "forged-previous-clone"}:
        forged_previous = target.parent / f".{target.name}.previous-{'b' * 32}"
        if case == "forged-previous-clone":
            shutil.copytree(previous, forged_previous)
        else:
            forged_previous.mkdir(); (forged_previous / "value").write_text("forged-old")
        details["previous"] = str(forged_previous)
        assert json.loads(entry["stdoutHead"])["previous"] == str(previous)
    elif case == "mutated-previous":
        (previous / "value").write_text("tampered-old")
    elif case == "forged-augmented-installed":
        details["installed"] = False
        assert json.loads(entry["stdoutHead"])["installed"] is True
    elif case == "missing-raw":
        entry["stdoutHead"] = ""
    elif case == "malformed-raw":
        entry["stdoutHead"] = "{}"
    undo_calls = []
    monkeypatch.setattr(DirectoryReplacement, "undo", lambda unused: undo_calls.append(True))

    recovery, recovered = _recover_directory_record(executor, operation, entry)
    assert recovery["blocked"] == [recovered.id]
    assert recovered.state == "rollback_failed" and undo_calls == []
    assert (target / "value").read_text() == ("user-edit" if case in {"mutated", "forged-installed"} else "new")
    assert (previous / "value").read_text() == ("tampered-old" if case == "mutated-previous" else "old")
    if case in {"forged-previous", "forged-previous-clone"}:
        expected_forged = "old" if case == "forged-previous-clone" else "forged-old"
        assert (forged_previous / "value").read_text() == expected_forged
    assert recovered.rollback_errors[-1]["code"] == "rollback_conflict"
    affected = set(recovered.rollback_errors[-1]["affectedPaths"])
    assert str(target) in affected
    if case == "forged-previous-clone":
        assert {str(previous), str(forged_previous)} <= affected


def test_directory_removal_contradiction_never_reaches_undo(isolated_home, monkeypatch):
    from customization_center.core.atomic import DirectoryReplacement

    paths = Paths.from_env(); executor, registry = _executor(paths)
    target = paths.module_config("hello") / "remove-conflict"
    target.mkdir(parents=True); (target / "value").write_text("old")
    operation = ops.ReplaceDirectoryAtomic(
        build_context("hello", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT),
        target, None, allow_existing=True)
    exec_ctx = executor._execution_context("placeholder", "hello")
    record = executor._in_flight_record(operation, "forward", exec_ctx)
    result = ops.run_forward(operation, exec_ctx)
    entry = executor._command_log_entry(
        operation, result, "forward", forward_evidence=record["evidence"])
    previous = Path(entry["directoryReplacement"]["previous"])
    entry["directoryReplacement"]["installed"] = True
    undo_calls = []
    monkeypatch.setattr(DirectoryReplacement, "undo", lambda unused: undo_calls.append(True))

    recovery, recovered = _recover_directory_record(executor, operation, entry)
    assert recovery["blocked"] == [recovered.id]
    assert recovered.state == "rollback_failed" and undo_calls == []
    assert not target.exists() and (previous / "value").read_text() == "old"
    assert recovered.rollback_errors[-1]["code"] == "rollback_conflict"


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


class EnsureDirectoryModule:
    id = "ensure-mode"
    schema_version = 1
    def __init__(self): self.fail_verification = False
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx):
        path = ctx.paths.module_config(self.id) / "directory"
        mode = f"{path.stat().st_mode & 0o7777:04o}" if path.is_dir() else None
        return Status(self.id, ctx.revision_of({"mode": mode}), {"mode": mode}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        operation = ops.EnsureDirectory(ctx, ctx.paths.module_config(self.id) / "directory", "0700")
        return Plan(self.id, status.revision, (operation,), (), "ensure mode", (), ())
    def verify(self, ctx, plan, status, results):
        return VerifyResult("fail", "full", "injected") if self.fail_verification else VerifyResult("pass", "full", "")


class MalformedManagedInverseModule:
    id = "managed-prep"
    schema_version = 1
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx):
        path = ctx.paths.module_config(self.id) / "managed.lua"
        value = path.read_text() if path.exists() else None
        return Status(self.id, ctx.revision_of({"value": value}), {"value": value}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        path = ctx.paths.module_config(self.id) / "managed.lua"
        inverse = Operation("managed-prep.9999", self.id, "ReplaceManagedBlock",
            {"path": str(path), "name": "TEST", "version": 1, "body": None},
            "restore managed block", (), (), 30)
        malformed = ("-- BEGIN OMARCHY CUSTOMIZATION CENTER TEST v1\n"
                     "-- BEGIN OMARCHY CUSTOMIZATION CENTER TEST v1\n")
        write = ops.WriteFileAtomic(ctx, path, malformed, "0600", inverse=inverse)
        return Plan(self.id, status.revision, (write,), (), "malformed managed inverse", (), ())
    def verify(self, ctx, plan, status, results): return VerifyResult("fail", "full", "injected")


def test_ensure_directory_mode_is_restored_by_failure_and_committed_undo(isolated_home):
    paths = Paths.from_env(); module = EnsureDirectoryModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    target = paths.module_config(module.id) / "directory"
    target.mkdir(parents=True, mode=0o755); target.chmod(0o755)

    module.fail_verification = True
    before = module.status(executor._ctx(module.id, "read"))
    with pytest.raises(CcError) as caught:
        executor.apply(module.id, {"schemaVersion": 1}, before.revision)
    assert caught.value.code == "verification_failed"
    assert target.stat().st_mode & 0o777 == 0o755
    assert executor.journal.history(module=module.id, limit=1)[0].state == "rolled_back"

    module.fail_verification = False
    before = module.status(executor._ctx(module.id, "read"))
    committed = executor.apply(module.id, {"schemaVersion": 1}, before.revision)
    assert target.stat().st_mode & 0o777 == 0o700
    undone = executor.rollback(committed.id)
    assert undone.state == "committed"
    assert target.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize(("observed_mode", "legacy", "completed"), [
    (0o700, False, True),
    (0o711, False, False),
    (0o700, True, False),
])
def test_ensure_directory_reconciliation_requires_expected_mode(
        isolated_home, observed_mode, legacy, completed):
    paths = Paths.from_env(); module = EnsureDirectoryModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    target = paths.module_config(module.id) / "directory"
    target.mkdir(parents=True, mode=0o755); target.chmod(0o755)
    operation = ops.EnsureDirectory(executor._ctx(module.id, "plan"), target, "0700")
    plan = Plan(module.id, "before", (operation,), (), "ensure", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    record = executor._in_flight_record(operation, "forward", executor._execution_context(txid, module.id))
    if legacy:
        record["evidence"].pop("requestedMode")
    tx = Transaction(txid, module.id, "applying", now, now, plan, "before", None,
                     (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx)
    target.chmod(observed_mode)
    reconciled = executor._reconcile_in_flight(tx)
    assert (operation.id in reconciled.completed_operation_ids) is completed
    if completed:
        details = json.loads(reconciled.command_log[-1]["stdoutHead"])
        assert details == {"created": False, "previousMode": "0755", "requestedMode": "0700"}
    else:
        assert reconciled.rollback_errors[-1]["code"] == "recovery_required"


def test_ensure_directory_unchanged_regular_file_clears_invalid_pre_effect_marker(isolated_home):
    paths = Paths.from_env(); module = EnsureDirectoryModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    target = paths.module_config(module.id) / "directory"
    target.parent.mkdir(parents=True); target.write_text("not a directory")
    operation = ops.EnsureDirectory(executor._ctx(module.id, "plan"), target, "0700")
    plan = Plan(module.id, "before", (operation,), (), "ensure", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    record = executor._in_flight_record(operation, "forward", executor._execution_context(txid, module.id))
    tx = Transaction(txid, module.id, "applying", now, now, plan, "before", None,
                     (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx)

    reconciled = executor._reconcile_in_flight(tx)

    assert reconciled.in_flight_operation is None
    assert reconciled.completed_operation_ids == ()
    assert reconciled.rollback_errors == ()


def test_ensure_directory_reconciliation_binds_requested_mode_to_durable_plan(isolated_home):
    paths = Paths.from_env(); module = EnsureDirectoryModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    target = paths.module_config(module.id) / "directory"
    target.mkdir(parents=True, mode=0o755); target.chmod(0o755)
    recorded = ops.EnsureDirectory(executor._ctx(module.id, "plan"), target, "0700")
    durable = replace(recorded, params={**recorded.params, "mode": "0711"})
    plan = Plan(module.id, "before", (durable,), (), "ensure", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    record = executor._in_flight_record(recorded, "forward", executor._execution_context(txid, module.id))
    tx = Transaction(txid, module.id, "applying", now, now, plan, "before", None,
                     (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx); target.chmod(0o700)

    reconciled = executor._reconcile_in_flight(tx)

    assert reconciled.completed_operation_ids == ()
    assert reconciled.rollback_errors[-1]["code"] == "recovery_required"


@pytest.mark.parametrize("case", ["file-before", "created-mismatch", "previous-mode-mismatch"])
def test_ensure_directory_reconciliation_rejects_impossible_evidence(isolated_home, case):
    paths = Paths.from_env(); module = EnsureDirectoryModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    target = paths.module_config(module.id) / "directory"
    target.parent.mkdir(parents=True)
    if case == "file-before":
        target.write_text("not a directory")
    else:
        target.mkdir(mode=0o755); target.chmod(0o755)
    operation = ops.EnsureDirectory(executor._ctx(module.id, "plan"), target, "0700")
    plan = Plan(module.id, "before", (operation,), (), "ensure", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    record = executor._in_flight_record(operation, "forward", executor._execution_context(txid, module.id))
    if case == "created-mismatch":
        record["evidence"]["created"] = True
    elif case == "previous-mode-mismatch":
        record["evidence"]["previousMode"] = "0750"
    tx = Transaction(txid, module.id, "applying", now, now, plan, "before", None,
                     (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx)
    if case == "file-before":
        target.unlink(); target.mkdir(mode=0o700)
    else:
        target.chmod(0o700)

    reconciled = executor._reconcile_in_flight(tx)
    assert reconciled.completed_operation_ids == ()
    assert reconciled.rollback_errors[-1]["code"] == "recovery_required"
    assert reconciled.rollback_errors[-1]["evidence"]["kind"] == "EnsureDirectory"


def test_managed_inverse_evidence_failure_is_bounded_and_blocks_apply(isolated_home):
    paths = Paths.from_env(); module = MalformedManagedInverseModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    before = module.status(executor._ctx(module.id, "read"))
    with pytest.raises(CcError) as caught:
        executor.apply(module.id, {"schemaVersion": 1}, before.revision)
    assert caught.value.code == "rollback_failed"

    failed = executor.journal.history(module=module.id, limit=1)[0]
    assert failed.state == "rollback_failed" and len(failed.inverse_progress) == 1
    error = failed.rollback_errors[-1]
    assert error["code"] == "unsupported_config" and error["evidence"]["preEffect"] is True
    assert error["evidence"]["kind"] == "ReplaceManagedBlock"
    attempts = [entry for entry in failed.command_log if entry.get("phase") == "rollback"]
    assert len(attempts) == 1 and "collision" in attempts[0]["stderrHead"]

    recovered = executor.recover()
    assert recovered["blocked"] == [failed.id]
    assert executor.journal.load(failed.id).state == "rollback_failed"
    assert len([entry for entry in executor.journal.load(failed.id).command_log
                if entry.get("phase") == "rollback"]) == 1
    current = module.status(executor._ctx(module.id, "read"))
    with pytest.raises(CcError) as blocked:
        executor.apply(module.id, {"schemaVersion": 1}, current.revision)
    assert blocked.value.code == "recovery_required"


class InverseOrderModule:
    id = "ordered"
    schema_version = 1
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx): return Status(self.id, "stable", {}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        first = ops.RunCommand(ctx, ["ordered-command", "set-a"], inverse=["ordered-command", "undo-a"])
        second = ops.RunCommand(ctx, ["ordered-command", "set-b"], inverse=["ordered-command", "undo-b"],
                                inverse_after=(first.id,))
        third = ops.RunCommand(ctx, ["ordered-command", "set-c"], inverse=["ordered-command", "undo-c"],
                               inverse_after=(second.id,))
        return Plan(self.id, status.revision, (first, second, third), (), "ordered", (), ())
    def verify(self, ctx, plan, status, results): return VerifyResult("pass", "full", "")


def test_inverse_after_controls_failure_recovery_and_committed_undo(isolated_home, stub_command):
    stub_command("ordered-command", {"exit_code": 0})
    paths = Paths.from_env(); registry = FixtureRegistry(InverseOrderModule())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")

    def undo_calls():
        return [call[1] for call in stub_command.calls("ordered-command") if call[1].startswith("undo-")]

    executor.faults.hooks.add("before_verify")
    with pytest.raises(CcError):
        executor.apply("ordered", {"schemaVersion": 1}, "stable")
    assert undo_calls()[-3:] == ["undo-a", "undo-b", "undo-c"]

    committed = executor.apply("ordered", {"schemaVersion": 1}, "stable")
    executor.rollback(committed.id)
    assert undo_calls()[-3:] == ["undo-a", "undo-b", "undo-c"]

    executor.faults.hooks.add("kill_process_at:before_verify")
    with pytest.raises(SystemExit):
        executor.apply("ordered", {"schemaVersion": 1}, "stable")
    executor.recover()
    assert undo_calls()[-3:] == ["undo-a", "undo-b", "undo-c"]
    recovered = executor.journal.history(module="ordered", limit=1)[0]
    assert recovered.state == "rolled_back" and recovered.reason == "recovery"


class MixedHandoffModule:
    id = "mixed"
    schema_version = 1
    def __init__(self): self.fail_verification = False
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx): return Status(self.id, "stable", {}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        setter = ops.RunCommand(ctx, ["mixed-command", "set"], inverse=["mixed-command", "undo"])
        handoff = ops.TerminalHandoff(ctx, ["handoff-command"], "Handoff", wrapped=True)
        return Plan(self.id, status.revision, (setter, handoff), (), "mixed", (), (handoff.id,))
    def verify(self, ctx, plan, status, results):
        if self.fail_verification:
            return VerifyResult("fail", "full", "The application is installed but was not set",
                                "defaults_installed_not_set", {"category": "terminal", "choice": "kitty"})
        return VerifyResult("pending", "full", "Waiting")


def test_reconcile_persists_verification_failure_and_abandon_rolls_back(isolated_home, stub_command):
    undo_fails = {"value": False}
    stub_command("omarchy-launch-floating-terminal-with-presentation", {"exit_code": 0})
    stub_command("handoff-command", {"exit_code": 0})
    stub_command("mixed-command", lambda request: {"exit_code": 7, "stderr": "undo failed"}
                 if request["argv"][1:] == ["undo"] and undo_fails["value"] else {"exit_code": 0})
    paths = Paths.from_env(); module = MixedHandoffModule(); registry = FixtureRegistry(module)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")

    pending = executor.apply("mixed", {"schemaVersion": 1}, "stable", confirmations=("mixed.0003",))
    abandoned = executor.abandon(pending.id)
    assert abandoned.state == "rolled_back" and abandoned.reason == "user"
    assert any(entry.get("inverseOf") == "mixed.0001" for entry in abandoned.command_log)
    assert {item["operationId"] for item in abandoned.skipped_inverse_ids} == {"mixed.0003"}

    module.fail_verification = True
    pending = executor.apply("mixed", {"schemaVersion": 1}, "stable", confirmations=("mixed.0003",))
    sentinel = paths.state / "handoffs" / f"{pending.id}.json"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text('{"exitCode":0,"finishedAt":"2024-01-01T00:00:00Z"}')
    reconciled = executor.reconcile(pending.id)
    assert reconciled.state == "rolled_back" and reconciled.reason == "verification"
    assert reconciled.verify == VerifyResult("fail", "full", "The application is installed but was not set",
                                             "defaults_installed_not_set",
                                             {"category": "terminal", "choice": "kitty"})
    assert reconciled.errors[-1]["code"] == "defaults_installed_not_set"
    assert reconciled.errors[-1]["data"] == {"category": "terminal", "choice": "kitty"}

    module.fail_verification = False; undo_fails["value"] = True
    pending = executor.apply("mixed", {"schemaVersion": 1}, "stable", confirmations=("mixed.0003",))
    failed = executor.abandon(pending.id)
    assert failed.state == "rollback_failed" and failed.reason == "user"
    ambiguity = failed.rollback_errors[-1]
    assert ambiguity["code"] == "recovery_required"
    assert ambiguity["evidence"]["kind"] == "RunCommand"
    assert ambiguity["evidence"]["phase"] == "rollback"


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

    stub_command("handoff-command", {"exit_code": 7, "stderr": "launcher failed"})
    with pytest.raises(CcError) as caught:
        executor.apply("handoff", {"schemaVersion": 1, "wrapped": False}, "stable",
                       confirmations=("handoff.0001",))
    assert caught.value.code == "rollback_failed"
    failed_launch = executor.journal.history(module="handoff", limit=1)[0]
    assert failed_launch.state == "rollback_failed" and failed_launch.reason == "handoff_failed"


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


def test_hard_killed_process_after_file_effect_recovers_without_reexecution(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    target = paths.module_config("hello") / "hello.json"
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text('{"message":"before"}')
    status = executor.registry.module("hello").status(executor._ctx("hello", "read"))
    process = multiprocessing.Process(target=_hard_exit_after_first_forward_effect, args=(paths, draft))
    process.start(); process.join(10)
    assert process.exitcode == 91 and target.read_text() != '{"message":"before"}'
    record = executor.journal.history(limit=1)[0]
    assert record.in_flight_operation["operationId"] == "hello.0001"
    executor.recover()
    assert executor.journal.load(record.id).state == "rolled_back"
    assert target.read_text() == '{"message":"before"}'
    assert executor.journal.current_transaction_id() is None


def test_forward_file_effect_killed_before_completion_is_reconciled(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    target = paths.module_config("hello") / "hello.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"message":"before"}')
    status = executor.registry.module("hello").status(executor._ctx("hello", "read"))
    executor.faults.hooks.add("kill_process_at:after_op_effect:hello.0001")
    with pytest.raises(SystemExit):
        executor.apply("hello", draft, status.revision)
    crashed = executor.journal.history(limit=1)[0]
    assert crashed.in_flight_operation["operationId"] == "hello.0001"
    recovered = executor.recover()
    record = executor.journal.load(crashed.id)
    assert recovered["required"] is False and record.state == "rolled_back"
    assert target.read_text() == '{"message":"before"}'


def test_ambiguous_forward_command_is_not_rerun_and_blocks(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    command_id = executor.registry.module("hello").plan(
        executor._ctx("hello", "plan"), draft, status).operations[-1].id
    executor.faults.hooks.add(f"kill_process_at:after_op_effect:{command_id}")
    with pytest.raises(SystemExit):
        executor.apply("hello", draft, status.revision)
    assert len(stub_command.calls("hello-command")) == 1
    result = executor.recover()
    record = executor.journal.history(limit=1)[0]
    assert record.state == "rollback_failed" and result["blocked"] == [record.id]
    assert len(stub_command.calls("hello-command")) == 1
    evidence = record.rollback_errors[-1]["evidence"]
    assert evidence["kind"] == "RunCommand" and evidence["operationId"] == command_id


def test_caught_forward_command_failure_preserves_ambiguity_without_rerun(
        isolated_home, stub_command, monkeypatch):
    paths, executor, status, draft = _hello_setup(stub_command)
    command_id = executor.registry.module("hello").plan(
        executor._ctx("hello", "plan"), draft, status).operations[-1].id
    run_forward = ops.run_forward

    def raise_after_effect(operation, exec_ctx):
        result = run_forward(operation, exec_ctx)
        if operation.id == command_id:
            raise CcError("ipc_rejected", "response lost after effect")
        return result

    monkeypatch.setattr(ops, "run_forward", raise_after_effect)
    with pytest.raises(CcError) as caught:
        executor.apply("hello", draft, status.revision)
    assert caught.value.code == "rollback_failed"
    record = executor.journal.history(limit=1)[0]
    assert record.state == "rollback_failed"
    assert record.rollback_errors[-1]["evidence"]["operationId"] == command_id
    assert len(stub_command.calls("hello-command")) == 1

    result = executor.recover()
    assert result["blocked"] == [record.id]
    assert executor.journal.load(record.id).state == "rollback_failed"
    assert len(stub_command.calls("hello-command")) == 1


def test_caught_committed_undo_command_failure_preserves_ambiguity_and_blocks_apply(
        isolated_home, stub_command, monkeypatch):
    paths, executor, status, draft = _hello_setup(stub_command)
    committed = executor.apply("hello", draft, status.revision)
    run_forward = ops.run_forward

    def raise_after_undo_effect(operation, exec_ctx):
        result = run_forward(operation, exec_ctx)
        if operation.kind == "RunCommand" and operation.params.get("argv") == ["hello-command", "undo"]:
            raise CcError("ipc_rejected", "undo response lost after effect")
        return result

    monkeypatch.setattr(ops, "run_forward", raise_after_undo_effect)
    with pytest.raises(CcError) as caught:
        executor.rollback(committed.id)
    assert caught.value.code == "rollback_failed"

    undo = executor.journal.history(module="hello", limit=1)[0]
    ambiguity = next(error for error in undo.rollback_errors if error["code"] == "recovery_required")
    assert undo.id != committed.id and undo.state == "rollback_failed"
    assert ambiguity["evidence"]["kind"] == "RunCommand"
    assert ambiguity["evidence"]["phase"] == "forward"
    undo_calls = [call for call in stub_command.calls("hello-command") if call[1:] == ["undo"]]
    assert len(undo_calls) == 1

    current = executor.registry.module("hello").status(executor._ctx("hello", "read"))
    with pytest.raises(CcError) as blocked:
        executor.apply("hello", draft, current.revision)
    assert blocked.value.code == "recovery_required"
    assert executor.journal.load(undo.id).state == "rollback_failed"
    assert len([call for call in stub_command.calls("hello-command") if call[1:] == ["undo"]]) == 1


@pytest.mark.parametrize("variant", ["named", "raw", "body-from-backup"])
@pytest.mark.parametrize("outcome", ["correct", "wrong", "legacy"])
def test_managed_block_reconciliation_is_exact_for_all_marker_forms(isolated_home, variant, outcome):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    suffix = ".lua" if variant != "raw" else ".conf"
    target = paths.module_config("hello") / f"managed-{variant}{suffix}"
    target.parent.mkdir(parents=True); target.write_text("outside\n")
    txid = str(uuid.uuid4()); exec_ctx = executor._execution_context(txid, "hello")
    context = executor._ctx("hello", "plan")
    if variant == "raw":
        operation = ops.ReplaceManagedBlock(
            context, target, body="expected", begin_marker="# begin", end_marker="# end")
    elif variant == "body-from-backup":
        exec_ctx.backups.take(txid, [target])
        forward = ops.ReplaceManagedBlock(context, target, "TEST", 1, "temporary")
        result = ops.run_forward(forward, exec_ctx)
        operation = ops.build_inverse(forward, exec_ctx, result)[0]
    else:
        operation = ops.ReplaceManagedBlock(context, target, "TEST", 1, "expected")
    plan = Plan("hello", "before", (operation,), (), "managed", (), ())
    now = "2024-01-01T00:00:00Z"
    record = executor._in_flight_record(operation, "forward", exec_ctx)
    if outcome == "legacy":
        record["evidence"].pop("expectedSha256")
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
        (), (), {}, None, None, (), (), in_flight_operation=record)
    executor.journal.create(tx)
    if outcome == "wrong":
        target.write_text("unexpected\n")
    else:
        ops.run_forward(operation, exec_ctx)

    reconciled = executor._reconcile_in_flight(tx)
    if outcome == "correct":
        assert reconciled.completed_operation_ids == (operation.id,)
        assert reconciled.rollback_errors == ()
        assert reconciled.command_log[-1]["writtenSha256"] == record["evidence"]["expectedSha256"]
    else:
        assert reconciled.completed_operation_ids == ()
        assert reconciled.rollback_errors[-1]["code"] == "recovery_required"
        assert reconciled.rollback_errors[-1]["evidence"]["kind"] == "ReplaceManagedBlock"


def test_tuple_inverse_resumes_after_durable_element_progress(isolated_home, monkeypatch):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    root = paths.module_config("hello"); root.mkdir(parents=True)
    first = root / "first"; second = root / "second"
    first.write_text("before-first"); second.write_text("before-second")
    txid = str(uuid.uuid4()); backups = executor.backups.take(txid, (first, second))
    first.write_text("after-first"); second.write_text("after-second")
    inverse_one = Operation("inverse.1", "hello", "RestoreBackup", {"path": str(first)}, "one", (), (), 30)
    inverse_two = Operation("inverse.2", "hello", "RestoreBackup", {"path": str(second)}, "two", (), (), 30)
    forward = Operation("hello.tuple", "hello", "RunCommand", {"argv": ["true"]}, "tuple",
                        (inverse_one, inverse_two), (), 30)
    plan = Plan("hello", "before", (forward,), (), "tuple", (), ())
    now = "2024-01-01T00:00:00Z"
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
                     (forward.id,), (), backups, None, None, (), ())
    executor.journal.create(tx)
    calls = []
    restore = executor.backups.restore
    monkeypatch.setattr(executor.backups, "restore", lambda current_txid, path: (calls.append(str(path)), restore(current_txid, path))[1])
    executor.faults.hooks.add(f"kill_process_at:after_inverse_effect:{forward.id}:0")
    with pytest.raises(SystemExit):
        executor._rollback_record(tx, "recovery")
    executor.recover()
    record = executor.journal.load(txid)
    assert record.state == "rolled_back"
    assert calls == [str(first), str(second)]
    assert set(record.inverse_progress) == {f"{forward.id}:0", f"{forward.id}:1"}


def test_completed_write_inverse_recovery_skips_forward_hash_conflict(
        isolated_home, stub_command):
    paths = Paths.from_env(); executor, _ = _executor(paths)
    target = paths.module_config("hello") / "write.conf"
    target.parent.mkdir(parents=True); target.write_text("before")
    txid = str(uuid.uuid4()); backups = executor.backups.take(txid, (target,))
    inverse = Operation("hello.write.inverse", "hello", "RestoreBackup", {"path": str(target)},
                        "restore", (), (), 30)
    forward = Operation("hello.write", "hello", "WriteFileAtomic",
                        {"path": str(target), "content": "after", "mode": "0600"},
                        "write", inverse, (), 30)
    result = ops.run_forward(forward, executor._execution_context(txid, "hello"))
    plan = Plan("hello", "before", (forward,), (), "write", (), ())
    now = "2024-01-01T00:00:00Z"
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
                     (forward.id,), (), backups, None, None, (), (),
                     command_log=(executor._command_log_entry(forward, result, "forward"),))
    executor.journal.create(tx)
    executor.faults.hooks.add(f"kill_process_at:after_inverse_effect:{forward.id}:0")
    with pytest.raises(SystemExit):
        executor._rollback_record(tx, "recovery")

    recovered = executor.recover(); record = executor.journal.load(txid)
    assert recovered["required"] is False and record.state == "rolled_back"
    assert target.read_text() == "before"
    assert record.rolled_back_operation_ids == (forward.id,)
    assert record.skipped_inverse_ids == ()


def test_deferred_reload_crash_is_not_repeated_and_recovery_reports_block(isolated_home, stub_command):
    stub_command("omarchy-hyprland-reload-guard", {"exit_code": 1})
    stub_command("hyprctl", lambda request: {"stdout": "[]"} if request["argv"][1:3] == ["-j", "configerrors"] else {"stdout": "ok"})
    paths = Paths.from_env(); executor, _ = _executor(paths)
    inverse = Operation("hello.reload.inverse", "hello", "HyprctlReload", {"config_only": False},
                        "reload inverse", (), (), 30)
    forward = Operation("hello.reload", "hello", "HyprctlReload", {"config_only": False},
                        "reload", inverse, (), 30)
    plan = Plan("hello", "before", (forward,), (), "reload", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    tx = Transaction(txid, "hello", "applying", now, now, plan, "before", None,
                     (forward.id,), (), {}, None, None, (), ())
    executor.journal.create(tx)
    executor.faults.hooks.add("kill_process_at:after_inverse_effect:hyprctl.reload:0")
    with pytest.raises(SystemExit):
        executor._rollback_record(tx, "recovery")
    reloads = lambda: [call for call in stub_command.calls("hyprctl") if call[1:] == ["reload"]]
    assert len(reloads()) == 1
    result = executor.recover(); record = executor.journal.load(txid)
    assert len(reloads()) == 1 and record.state == "rollback_failed"
    assert result == {"recovered": [txid], "blocked": [txid], "required": True}


def test_orphaned_future_confirmation_is_recovered_before_new_apply(isolated_home, stub_command):
    paths, executor, status, draft = _hello_setup(stub_command)
    plan = Plan("hello", status.revision, (), (), "old gate", (), ())
    now = "2024-01-01T00:00:00Z"; txid = str(uuid.uuid4())
    old = Transaction(txid, "hello", "awaiting_confirmation", now, now, plan, status.revision, None,
                      (), (), {}, None, {"deadline": "2099-01-01T00:00:00Z"}, (), ())
    executor.journal.create(old)
    committed = executor.apply("hello", draft, status.revision)
    assert executor.journal.load(txid).state == "rolled_back"
    assert committed.state == "committed"


class HyprManagedBlockUndoModule:
    id = "hypr-managed-undo"
    schema_version = 1
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx):
        path = ctx.paths.home / ".config/hypr/managed-undo.conf"
        value = path.read_text() if path.exists() else None
        return Status(self.id, ctx.revision_of({"value": value}), {"value": value}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        path = ctx.paths.home / ".config/hypr/managed-undo.conf"
        inverse = Operation("hypr-managed-undo.9999", self.id, "ReplaceManagedBlock",
                            {"path": str(path), "name": "undo-test", "version": 1, "body": None},
                            "remove managed block", (), (), 30)
        managed = ops.ReplaceManagedBlock(ctx, path, "undo-test", body="new", inverse=inverse)
        return Plan(self.id, status.revision, (managed,), (), "managed hypr undo", (), ())
    def verify(self, ctx, plan, status, results): return VerifyResult("pass", "full", "")


class HyprUndoModule:
    id = "hypr-undo"
    schema_version = 1
    def capabilities(self, ctx): return Capabilities(self.id, (), ctx.clock.now_iso())
    def status(self, ctx):
        path = ctx.paths.home / ".config/hypr/undo-test.conf"
        value = path.read_text() if path.exists() else None
        return Status(self.id, ctx.revision_of({"value": value}), {"value": value}, (), 1)
    def validate(self, ctx, draft, status): return ValidationResult(True, (), draft)
    def plan(self, ctx, draft, status):
        path = ctx.paths.home / ".config/hypr/undo-test.conf"
        write = ops.WriteFileAtomic(ctx, path, "new", "0600")
        reload = ops.HyprctlReload(ctx, config_only=True)
        return Plan(self.id, status.revision, (write, reload), (), "hypr undo", (), ())
    def verify(self, ctx, plan, status, results): return VerifyResult("pass", "full", "")


def test_committed_managed_block_undo_emits_one_final_hypr_reload(isolated_home, stub_command):
    paths = Paths.from_env(); target = paths.home / ".config/hypr/managed-undo.conf"
    target.parent.mkdir(parents=True); target.write_text("base\n")
    reload_states = []
    stub_command("omarchy-hyprland-reload-guard", {"exit_code": 1})
    def hypr(request):
        if request["argv"][1:3] == ["-j", "configerrors"]:
            return {"stdout": "[]"}
        reload_states.append(target.read_text())
        return {"stdout": "ok"}
    stub_command("hyprctl", hypr)
    registry = FixtureRegistry(HyprManagedBlockUndoModule())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    before = registry.module("hypr-managed-undo").status(executor._ctx("hypr-managed-undo", "read"))
    committed = executor.apply("hypr-managed-undo", {"schemaVersion": 1}, before.revision)
    undone = executor.rollback(committed.id)

    assert undone.state == "committed" and target.read_text() == "base\n"
    assert reload_states == ["base\n"]
    assert [operation.kind for operation in undone.plan.operations] == ["ReplaceManagedBlock", "HyprctlReload"]


def test_unexpected_managed_block_inverse_result_is_ambiguous_and_not_rerun(
        isolated_home, stub_command, monkeypatch):
    paths = Paths.from_env(); target = paths.home / ".config/hypr/managed-undo.conf"
    target.parent.mkdir(parents=True); target.write_text("base\n")
    stub_command("omarchy-hyprland-reload-guard", {"exit_code": 1})
    stub_command("hyprctl", lambda request: {"stdout": "[]"})
    registry = FixtureRegistry(HyprManagedBlockUndoModule())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    before = registry.module("hypr-managed-undo").status(executor._ctx("hypr-managed-undo", "read"))
    run_forward = ops.run_forward
    inverse_attempts = []

    def write_unexpected_then_raise(operation, exec_ctx):
        if operation.kind == "ReplaceManagedBlock" and operation.params.get("body") is None:
            inverse_attempts.append(operation.id)
            Path(operation.params["path"]).write_bytes(b"unexpected\n")
            raise CcError("internal_error", "managed inverse failed after unexpected write")
        return run_forward(operation, exec_ctx)

    monkeypatch.setattr(ops, "run_forward", write_unexpected_then_raise)
    executor.faults.hooks.add("before_verify")
    with pytest.raises(CcError) as caught:
        executor.apply("hypr-managed-undo", {"schemaVersion": 1}, before.revision)
    assert caught.value.code == "rollback_failed"

    failed = executor.journal.history(module="hypr-managed-undo", limit=1)[0]
    log = next(entry for entry in failed.command_log
               if entry.get("phase") == "rollback" and "unexpected write" in entry["stderrHead"])
    ambiguity = next(error for error in failed.rollback_errors if error["code"] == "recovery_required")
    assert failed.state == "rollback_failed" and log["inverseOf"] == failed.plan.operations[0].id
    assert ambiguity["evidence"]["kind"] == "ReplaceManagedBlock"
    assert ambiguity["evidence"]["evidence"]["expectedSha256"]
    assert target.read_bytes() == b"unexpected\n"
    assert len(inverse_attempts) == 1

    recovered = executor.recover()
    assert recovered["blocked"] == [failed.id]
    assert executor.journal.load(failed.id).state == "rollback_failed"
    assert len(inverse_attempts) == 1

    current = registry.module("hypr-managed-undo").status(executor._ctx("hypr-managed-undo", "read"))
    with pytest.raises(CcError) as blocked:
        executor.apply("hypr-managed-undo", {"schemaVersion": 1}, current.revision)
    assert blocked.value.code == "recovery_required"
    assert len(inverse_attempts) == 1


def test_failed_committed_undo_restores_committed_hypr_file_then_reloads(isolated_home, stub_command):
    paths = Paths.from_env(); target = paths.home / ".config/hypr/undo-test.conf"
    target.parent.mkdir(parents=True); target.write_text("old")
    reloads = []
    stub_command("omarchy-hyprland-reload-guard", {"exit_code": 1})
    def hypr(request):
        if request["argv"][1:3] == ["-j", "configerrors"]:
            return {"stdout": "[]"}
        reloads.append((list(request["argv"][1:]), target.read_text()))
        if len(reloads) == 2:
            return {"exit_code": 1, "stderr": "undo reload failed"}
        return {"stdout": "ok"}
    stub_command("hyprctl", hypr)
    registry = FixtureRegistry(HyprUndoModule()); executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    before = registry.module("hypr-undo").status(executor._ctx("hypr-undo", "read"))
    committed = executor.apply("hypr-undo", {"schemaVersion": 1}, before.revision)
    with pytest.raises(CcError) as caught:
        executor.rollback(committed.id)
    assert caught.value.code == "rollback_failed"
    assert target.read_text() == "new"
    assert reloads == [(["reload", "config-only"], "new"),
                       (["reload", "config-only"], "old"),
                       (["reload"], "new")]
    failed_undo = executor.journal.history(module="hypr-undo", limit=1)[0]
    assert failed_undo.state == "rollback_failed"
    assert any(error["code"] == "recovery_required" for error in failed_undo.rollback_errors)
    recovery_reloads = [entry for entry in failed_undo.command_log
                        if entry.get("phase") == "rollback" and entry["operationId"] == "hyprctl.reload"]
    assert len(recovery_reloads) == 1


def test_committed_undo_restores_hypr_file_then_reloads_once_with_error_baseline(isolated_home, stub_command):
    paths = Paths.from_env(); target = paths.home / ".config/hypr/undo-test.conf"
    target.parent.mkdir(parents=True); target.write_text("old")
    events = []
    stub_command("omarchy-hyprland-reload-guard", {"exit_code": 1})
    def hypr(request):
        if request["argv"][1:3] == ["-j", "configerrors"]:
            return {"stdout": json.dumps([{"message": "pre-existing"}])}
        events.append(target.read_text())
        return {"stdout": "ok"}
    stub_command("hyprctl", hypr)
    registry = FixtureRegistry(HyprUndoModule()); executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    before = registry.module("hypr-undo").status(executor._ctx("hypr-undo", "read"))
    committed = executor.apply("hypr-undo", {"schemaVersion": 1}, before.revision)
    undone = executor.rollback(committed.id)
    assert undone.state == "committed" and target.read_text() == "old"
    assert events == ["new", "old"]
    undo_log = [entry for entry in undone.command_log if entry["phase"] == "forward"]
    assert [entry["operationId"] for entry in undo_log][-1] == "hypr-undo.0002"
