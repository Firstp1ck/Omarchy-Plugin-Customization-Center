from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import CcError, Status
from customization_center.core.context import build_context
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "tests/fixtures/modules/hello/tests/fixtures/sample-draft.json").read_text())


def _template_plan():
    paths = Paths.from_env()
    registry = load_registry(ROOT, [ROOT / "tests/fixtures/modules/hello"], paths)
    module = registry.module("hello")
    ctx = SimpleNamespace(module_id="hello", cache={}, paths=paths)
    return module.plan(ctx, SAMPLE, Status("hello", "revision", {}, (), 1))


_TEMPLATE = _template_plan()
_OP_IDS = [operation.id for operation in _TEMPLATE.operations]
_BASE_HOOKS = (["before_backup", "after_backup", "before_verify", "verification_mismatch"] +
               [f"{side}_op:{operation_id}" for operation_id in _OP_IDS for side in ("before", "after")])
_INVERSE_HOOKS = [f"{side}_inverse:{operation_id}" for operation_id in _OP_IDS for side in ("before", "after")]
_JOURNAL_HOOKS = ["before_journal_fsync:applying", "before_journal_fsync:committed",
                  "before_journal_fsync:rolling_back", "before_journal_fsync:rolled_back",
                  "before_journal_fsync:rollback_failed"]
KILL_HOOKS = ["kill_process_at:after_backup", f"kill_process_at:after_op:{_OP_IDS[0]}",
              f"kill_process_at:before_inverse:{_OP_IDS[0]}",
              "kill_process_at:before_journal_fsync:rolling_back"]
CASES = [(hook, [hook], "internal_error") for hook in _BASE_HOOKS if hook != "verification_mismatch"]
CASES += [("verification_mismatch", ["verification_mismatch"], "verification_failed")]
CASES += [(hook, ["before_verify", hook], "rollback_failed") for hook in _INVERSE_HOOKS]
CASES += [
    ("before_journal_fsync:applying", ["before_journal_fsync:applying"], "internal_error"),
    ("before_journal_fsync:committed", ["before_journal_fsync:committed"], "internal_error"),
    ("before_journal_fsync:rolling_back", ["before_verify", "before_journal_fsync:rolling_back"], "internal_error"),
    ("before_journal_fsync:rolled_back", ["before_verify", "before_journal_fsync:rolled_back"], "internal_error"),
    ("before_journal_fsync:rollback_failed", ["before_verify", f"before_inverse:{_OP_IDS[0]}",
                                               "before_journal_fsync:rollback_failed"], "internal_error"),
]


def _make(paths, fault_file):
    os.environ["CC_TEST_FAULTS"] = str(fault_file)
    registry = load_registry(ROOT, [ROOT / "tests/fixtures/modules/hello"], paths)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    status = registry.module("hello").status(build_context("hello", "read", paths=paths,
        registry=registry.view, plugin_dir=ROOT))
    return executor, status.revision


def _seed_and_snapshot(paths: Paths):
    target = paths.module_config("hello") / "hello.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'{"message":"seed-0600"}\n'); target.chmod(0o600)
    return {str(target): (target.read_bytes(), target.stat().st_mode & 0o777)}


def _assert_snapshot(snapshot):
    for raw, (content, mode) in snapshot.items():
        path = Path(raw)
        assert path.read_bytes() == content
        assert path.stat().st_mode & 0o777 == mode


def _assert_recovery(executor: Executor, tx):
    data = executor._recovery_data(tx)
    expected = {f"{ROOT / 'backend/ccctl'} restore {tx.id} --path {path}" for path in tx.backups}
    assert set(data["recoveryCommands"]) == expected
    assert {item["path"] for item in data["manualPaths"]}.isdisjoint(tx.backups)


@pytest.mark.parametrize("label,hooks,expected_code", CASES, ids=[item[0] for item in CASES])
def test_hello_fault_matrix(label, hooks, expected_code, isolated_home, stub_command):
    stub_command("hello-command", {"exit_code": 0})
    paths = Paths.from_env(); snapshot = _seed_and_snapshot(paths)
    fault_file = isolated_home / "faults.json"; fault_file.write_text(json.dumps({"hooks": hooks}))
    executor, revision = _make(paths, fault_file)
    with pytest.raises(CcError) as caught:
        executor.apply("hello", SAMPLE, revision)
    assert caught.value.code == expected_code
    assert label in executor.faults.consumed
    record = executor.journal.history(limit=1)[0]
    if record.state in {"applying", "rolling_back"}:
        fault_file.write_text('{"hooks":[]}'); recovery, _ = _make(paths, fault_file); recovery.recover()
        record = recovery.journal.load(record.id); executor = recovery
    assert record.state in {"rolled_back", "rollback_failed"}
    if record.state == "rolled_back": _assert_snapshot(snapshot)
    else: _assert_recovery(executor, record)


@pytest.mark.parametrize("kill_hook", KILL_HOOKS)
def test_killed_process_hooks_recover(kill_hook, isolated_home, stub_command):
    stub_command("hello-command", {"exit_code": 0})
    paths = Paths.from_env(); snapshot = _seed_and_snapshot(paths)
    base_hook = kill_hook.removeprefix("kill_process_at:")
    hooks = [kill_hook]
    if "inverse" in kill_hook or "rolling_back" in kill_hook: hooks.insert(0, "before_verify")
    fault_file = isolated_home / "faults.json"; fault_file.write_text(json.dumps({"hooks": hooks}))
    executor, revision = _make(paths, fault_file)
    with pytest.raises(SystemExit): executor.apply("hello", SAMPLE, revision)
    assert kill_hook in executor.faults.consumed
    fault_file.write_text('{"hooks":[]}'); recovery, _ = _make(paths, fault_file); recovery.recover()
    record = recovery.journal.history(limit=1)[0]
    assert record.state in {"rolled_back", "rollback_failed"}
    if record.state == "rolled_back": _assert_snapshot(snapshot)
    else: _assert_recovery(recovery, record)
