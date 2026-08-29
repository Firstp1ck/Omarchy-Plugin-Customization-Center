from customization_center.core import Status


def base_row(plugin_id, ownership="plugins", capabilities=()):
    kinds = ["service"] if ownership == "plugins" else ["bar-widget"]
    return {"id": plugin_id, "kinds": kinds, "ownership": ownership, "self": False,
            "capabilities": list(capabilities), "state": {"enabled": False}, "instances": []}


def test_bar_mutation_is_rejected_with_navigation_detail(plugins_backend):
    status = Status("plugins", "rev:1", {"rows": [base_row("acme.widget", "bar", ({"name": "edit-in-bar-editor", "navigate": {"addWidget": "acme.widget"}},))]}, (), 1)
    draft = {"schemaVersion": 1, "module": "plugins", "baseRevision": "rev:1",
             "changes": [{"kind": "enable", "pluginId": "acme.widget"}]}
    result = plugins_backend.MODULE.validate(None, draft, status)
    assert result.ok is False
    assert result.issues[0].code == "plugins_bar_owned"
    assert result.details["navigate"]["acme.widget"] == {"addWidget": "acme.widget"}


def test_lifecycle_must_be_alone_and_ids_are_strict(plugins_backend):
    status = Status("plugins", "rev:1", {"rows": [base_row("acme.service", capabilities=("enable", "remove"))]}, (), 1)
    draft = {"schemaVersion": 1, "module": "plugins", "baseRevision": "rev:1", "changes": [
        {"kind": "lifecycle", "action": "remove", "pluginId": "acme.service"},
        {"kind": "enable", "pluginId": "../x"}]}
    result = plugins_backend.MODULE.validate(None, draft, status)
    assert {issue.code for issue in result.issues} >= {"plugins_lifecycle_not_alone", "plugins_invalid_id"}
