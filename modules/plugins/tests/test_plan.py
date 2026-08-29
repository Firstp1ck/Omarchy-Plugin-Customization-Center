from __future__ import annotations

from types import SimpleNamespace

from customization_center.core import Status


def row(plugin_id, *, kinds=("service",), enabled=False, first_party=False, capabilities=()):
    return {"id": plugin_id, "name": plugin_id, "kinds": list(kinds), "firstParty": first_party,
            "self": False, "ownership": "bar" if "bar" in kinds or "bar-widget" in kinds else "plugins",
            "origin": {"class": "omarchy-shipped" if first_party else "user-installed", "checkout": "git" if not first_party else "bundled"},
            "state": {"enabled": enabled, "active": False, "canDisable": True, "storage": "implicit",
                      "disabledByList": False, "activeCloneId": None}, "instances": [], "settings": {},
            "diagnostics": [], "capabilities": list(capabilities)}


def status_for(*rows):
    return Status("plugins", "rev:1", {"rows": list(rows)}, (), 1)


def ctx():
    return SimpleNamespace(module_id="plugins", cache={})


def test_enable_operation_inverse_claim_and_order(plugins_backend):
    module = plugins_backend.MODULE
    status = status_for(row("acme.service", capabilities=("enable",)), row("omarchy.nightlight", enabled=True, first_party=True, capabilities=("disable",)))
    draft = {"schemaVersion": 1, "module": "plugins", "baseRevision": "rev:1", "changes": [
        {"kind": "enable", "pluginId": "acme.service"}, {"kind": "disable", "pluginId": "omarchy.nightlight"}]}
    plan = module.plan(ctx(), draft, status)
    assert [operation.params["args"] for operation in plan.operations] == [["omarchy.nightlight", "false"], ["acme.service", "true"]]
    assert plan.operations[0].inverse.params["args"] == ["omarchy.nightlight", "true"]
    assert {claim.key for claim in plan.claims} == {"shell.plugin:acme.service", "shell.plugin:omarchy.nightlight"}


def test_lifecycle_uses_wrapped_terminal_handoffs_without_automatic_flags(plugins_backend):
    module = plugins_backend.MODULE
    cases = [("add", None, ["omarchy-plugin-add"]),
             ("update", "acme.service", ["omarchy-plugin-update", "acme.service"]),
             ("remove", "acme.service", ["omarchy-plugin-remove", "acme.service"]),
             ("clone", "omarchy.clock", ["omarchy-plugin-clone", "omarchy.clock"])]
    rows = [row("acme.service", enabled=True, capabilities=("update", "remove")),
            row("omarchy.clock", kinds=("bar-widget",), enabled=True, first_party=True, capabilities=("clone",))]
    for action, plugin_id, expected in cases:
        change = {"kind": "lifecycle", "action": action}
        if plugin_id: change["pluginId"] = plugin_id
        plan = module.plan(ctx(), {"schemaVersion": 1, "module": "plugins", "baseRevision": "rev:1", "changes": [change]}, status_for(*rows))
        operation = plan.operations[0]
        assert operation.kind == "TerminalHandoff"
        assert operation.params == {"argv": expected, "title": operation.params["title"], "wrapped": True}
        assert "--yes" not in expected and "--enable" not in expected
        assert operation.id in plan.requires_confirmation
        if action == "clone": assert "shell.bar" in {claim.key for claim in plan.claims}
