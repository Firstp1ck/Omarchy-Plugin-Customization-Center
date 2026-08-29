from types import SimpleNamespace

from customization_center.core import Paths, Status
from modules.defaults.backend.planner import build_plan, validate_draft


def browser_status(state="available", current="zen"):
    return Status("defaults", "revision", {"pendingHandoffs": [], "categories": [{
        "id": "browser", "state": "ready" if current != "unknown" else "unknown", "drifted": False,
        "current": {"choice": None if current == "unknown" else current},
        "choices": [{"id": "zen", "state": "available"}, {"id": "firefox", "state": state}],
    }]}, (), 1)


def context(isolated_home):
    return SimpleNamespace(paths=Paths.from_env(), module_id="defaults", cache={})


def test_plan_set_installed_browser_has_backup_and_inverse(isolated_home):
    ctx = context(isolated_home); status = browser_status()
    draft = {"schemaVersion": 1, "changes": {"browser": {"choice": "firefox", "install": False}}}
    validation = validate_draft(ctx, draft, status)
    assert validation.ok
    plan = build_plan(ctx, draft, status)
    operation = plan.operations[0]
    assert operation.kind == "RunCommand"
    assert operation.params["argv"] == ["omarchy-default-browser", "firefox"]
    assert operation.params["env_extra"] == {"BROWSER": None}
    assert operation.backup_paths == (str(ctx.paths.xdg_config_home / "mimeapps.list"),)
    assert operation.inverse.params["argv"] == ["omarchy-default-browser", "zen"]


def test_missing_target_requires_consent_then_handoff(isolated_home):
    ctx = context(isolated_home); status = browser_status("missing")
    refused = validate_draft(ctx, {"schemaVersion": 1, "changes": {"browser": {"choice": "firefox", "install": False}}}, status)
    assert not refused.ok and refused.issues[0].code == "defaults_target_missing"
    accepted = {"schemaVersion": 1, "changes": {"browser": {"choice": "firefox", "install": True}}}
    plan = build_plan(ctx, accepted, status)
    assert plan.operations[0].kind == "TerminalHandoff"
    assert plan.operations[0].params["wrapped"] is False
    assert "--install" not in plan.operations[0].params["argv"]
