import json
from pathlib import Path

import pytest

from customization_center.core import CcError, Executor, FaultPlan, OperationResult, Status
from customization_center.core.context import build_context
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = Path(__file__).parent / "fixtures/sample-draft.json"


def _setup(stub_command):
    stub_command("omarchy-menu", {"exit_code": 0, "stdout": "ok\n"})
    stub_command("bash", {"exit_code": 0})
    paths = Paths.from_env()
    registry = load_registry(ROOT, paths=paths)
    return paths, registry


def test_status_validate_and_plan_are_read_only(isolated_home, stub_command, fake_shell):
    paths, registry = _setup(stub_command)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    validation = module.validate(build_context("menu", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    assert validation.ok
    before = [path.relative_to(isolated_home) for path in isolated_home.rglob("*")]
    plan = module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    after = [path.relative_to(isolated_home) for path in isolated_home.rglob("*")]
    assert before == after
    assert [operation.kind for operation in plan.operations] == ["WriteFileAtomic", "RunCommand"]


def test_plan_requires_reachable_shell(isolated_home, stub_command):
    paths, registry = _setup(stub_command)
    stub_command("omarchy-menu", {"exit_code": 1, "stderr": "omarchy-shell is not running\n"})
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    validation = module.validate(build_context("menu", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    with pytest.raises(CcError) as error:
        module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    assert error.value.code == "capability_missing"


def test_acknowledgements_are_unique_per_warning(isolated_home, stub_command):
    paths, registry = _setup(stub_command)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    draft["entries"] = [
        {**draft["entries"][0], "draftId": "one", "id": "one", "kind": "command", "fields": {"label": "One", "action": "sudo rm -rf /tmp/one"}},
        {**draft["entries"][0], "draftId": "two", "id": "two", "kind": "command", "fields": {"label": "Two", "action": "sudo rm -rf /tmp/two"}},
    ]
    validation = module.validate(build_context("menu", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    plan = module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    ack_warnings = [warning for warning in plan.warnings if warning.ack]
    assert len(plan.requires_confirmation) == len(ack_warnings)
    assert set(plan.requires_confirmation) == {warning.code for warning in ack_warnings}


def test_projection_marks_added_and_deleted_entries(isolated_home, stub_command):
    paths, registry = _setup(stub_command)
    module = registry.module("menu")
    target = isolated_home / ".config/omarchy/extensions/omarchy-menu.jsonc"
    target.parent.mkdir(parents=True)
    target.write_text('{"old":{"label":"Old","action":"true"}}\n')
    status = module.status(build_context("menu", "query", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = status.revision
    draft["entries"] = [
        {"draftId": "old", "id": "old", "originalId": "old", "origin": "custom", "kind": "command", "fields": {"label": "Old", "action": "true"}, "passthrough": {}, "raw": None, "deleted": True},
        {"draftId": "new", "id": "new", "originalId": None, "origin": "custom", "kind": "submenu", "fields": {"label": "New"}, "passthrough": {}, "raw": None, "deleted": False},
    ]
    projected = module.query(build_context("menu", "query", paths=paths, registry=registry.view, plugin_dir=ROOT), "projection", {"draft": draft})["effective"]
    assert projected["rows"]["new"]["draftState"] == "draft"
    assert projected["rows"]["old"]["draftState"] == "deleted"


def test_first_apply_creates_file_and_failed_first_apply_unlinks_it(isolated_home, stub_command, fake_shell):
    paths, registry = _setup(stub_command)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    transaction = executor.apply("menu", draft, status.revision)
    target = isolated_home / ".config/omarchy/extensions/omarchy-menu.jsonc"
    assert transaction.state == "committed" and target.is_file() and (target.stat().st_mode & 0o777) == 0o600

    target.unlink()
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    def menu_reply(request):
        return {"exit_code": 0, "stdout": "ok\n" if request["argv"][1] == "ping" else "unknown\n"}
    stub_command("omarchy-menu", menu_reply)
    with pytest.raises(CcError) as error:
        executor.apply("menu", draft, status.revision)
    assert error.value.code == "menu_refresh_failed"
    assert not target.exists()


def test_refresh_non_ok_and_timeout_verify_failures(isolated_home, stub_command):
    paths, registry = _setup(stub_command)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    validation = module.validate(build_context("menu", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    plan = module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    write, refresh = plan.operations
    digest = __import__("hashlib").sha256(write.params["content"].encode()).hexdigest()
    after = Status("menu", "after", {"user": {"sha256": digest}, "documentState": "ok"}, (), 1)
    unknown = OperationResult(refresh.id, 0, "unknown\n", "", False, 1, None)
    assert module.verify(None, plan, after, {refresh.id: unknown}).code == "menu_refresh_failed"
    timeout = OperationResult(refresh.id, None, "", "", True, 10000, None)
    assert module.verify(None, plan, after, {refresh.id: timeout}).code == "timeout"


def test_executor_refresh_timeout_rolls_back_and_runs_inverse_refresh(isolated_home, stub_command, fake_shell):
    calls = {"refresh": 0}
    def menu_reply(request):
        if request["argv"][1] == "ping":
            return {"exit_code": 0, "stdout": "ok\n"}
        calls["refresh"] += 1
        if calls["refresh"] == 1:
            return {"hang": True, "hangSeconds": 30}
        return {"exit_code": 0, "stdout": "ok\n"}

    paths, registry = _setup(stub_command)
    stub_command("omarchy-menu", menu_reply)
    target = isolated_home / ".config/omarchy/extensions/omarchy-menu.jsonc"
    target.parent.mkdir(parents=True)
    original = b"{}\n"
    target.write_bytes(original)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    with pytest.raises(CcError) as error:
        executor.apply("menu", json.loads(SAMPLE.read_text()), status.revision,
                       confirmations=("menu_normalization",))
    assert error.value.code == "timeout"
    transaction = executor.journal.history(limit=1)[0]
    assert transaction.state == "rolled_back"
    assert target.read_bytes() == original
    assert calls["refresh"] == 2
    write_inverse = transaction.plan.operations[0].inverse
    assert any(inverse.kind == "RunCommand" and inverse.params["argv"] == ["omarchy-menu", "refresh"]
               for inverse in write_inverse)


def test_fault_rolls_back_byte_identical_file(isolated_home, stub_command, fake_shell):
    paths, registry = _setup(stub_command)
    target = isolated_home / ".config/omarchy/extensions/omarchy-menu.jsonc"
    target.parent.mkdir(parents=True)
    original = b"{}\n"
    target.write_bytes(original)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(SAMPLE.read_text())
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    executor.faults = FaultPlan(["before_op:menu.0003"])
    with pytest.raises(CcError):
        executor.apply("menu", draft, status.revision, confirmations=("menu_normalization",))
    transaction = executor.journal.history(limit=1)[0]
    assert transaction.state == "rolled_back"
    assert target.read_bytes() == original
