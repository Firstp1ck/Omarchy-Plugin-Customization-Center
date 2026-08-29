from __future__ import annotations

from types import SimpleNamespace

from customization_center.core import Operation, Plan, ResourceClaim, Status


def state_row(plugin_id, enabled, storage, *, first_party=False, cloned_from=None):
    return {"id": plugin_id, "firstParty": first_party, "clonedFrom": cloned_from,
            "state": {"enabled": enabled, "storage": storage, "disabledByList": storage == "disabledPlugins[]"}}


def operation(action, plugin_id=None, **detail):
    return Operation("plugins.0001", "plugins", "TerminalHandoff" if action not in {"enable", "disable"} else "ShellIpc",
                     {}, action, None if action not in {"enable", "disable"} else (), (), detail={"action": action, "pluginId": plugin_id, **detail})


def plan_with(op):
    return Plan("plugins", "rev:1", (op,), (ResourceClaim("shell.plugin:test", "exclusive"),), "test", (), (op.id,) if op.inverse is None else ())


def test_verify_enable_and_storage(plugins_backend):
    status = Status("plugins", "rev:2", {"rows": [state_row("acme.service", True, "plugins[]")]}, (), 1)
    result = plugins_backend.MODULE.verify(SimpleNamespace(), plan_with(operation("enable", "acme.service", targetEnabled=True)), status, {})
    assert result.state == "pass"
    drifted = Status("plugins", "rev:2", {"rows": [state_row("acme.service", True, "implicit")]}, (), 1)
    assert plugins_backend.MODULE.verify(SimpleNamespace(), plan_with(operation("enable", "acme.service", targetEnabled=True)), drifted, {}).state == "fail"


def test_verify_terminal_reconciliation_outcomes(plugins_backend):
    module = plugins_backend.MODULE
    added = Status("plugins", "rev:2", {"rows": [state_row("acme.new", False, "implicit")]}, (), 1)
    assert module.verify(SimpleNamespace(), plan_with(operation("add", beforeIds=[])), added, {}).state == "pass"
    clone = Status("plugins", "rev:2", {"rows": [state_row("tester.clock", True, "bar.layout", cloned_from="omarchy.clock")]}, (), 1)
    assert module.verify(SimpleNamespace(), plan_with(operation("clone", "omarchy.clock")), clone, {}).state == "pass"
    incomplete = Status("plugins", "rev:2", {"rows": []}, (), 1)
    result = module.verify(SimpleNamespace(), plan_with(operation("clone", "omarchy.clock")), incomplete, {})
    assert result.code == "plugins_clone_incomplete"
