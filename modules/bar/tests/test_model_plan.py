from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from customization_center.core import Capabilities, Status

FIXTURE = Path(__file__).parent / "fixtures/config-basic.json"


def status_value(bar_backend):
    document = json.loads(FIXTURE.read_text())
    bar = bar_backend.model.from_shell(document["bar"])
    catalog = [
        {"id": "omarchy.menu", "presence": "shell", "allowMultiple": False, "schema": {"ok": True, "fields": []}},
        {"id": "omarchy.clock", "presence": "shell", "allowMultiple": False, "schema": {"ok": True, "fields": []}},
        {"id": "omarchy.spacer", "presence": "shell", "allowMultiple": True, "schema": {"ok": True, "fields": [{"key": "size", "type": "integer", "min": 0, "max": 4096}]}}
    ]
    data = {"bar": bar, "catalog": catalog, "barOptions": [{"id": "omarchy.bar", "available": True, "firstParty": True}],
            "shell": {"available": True, "scanning": False, "fallback": False}, "rawShellConfig": document,
            "file": {"exists": True}, "capabilities": {"applyFile": {"available": True, "reason": ""}}}
    return Status("bar", "rev:1", data, (), 1)


def draft_from(status):
    bar = json.loads(json.dumps(status.data["bar"]))
    for section in ("left", "center", "right"):
        for index, entry in enumerate(bar["layout"][section]): entry["key"] = f"d:{section}:{index}"
    return {"schemaVersion": 1, "module": "bar", "baseRevision": status.revision, "bar": bar}


class Paths:
    home = Path("/tmp/bar-test-home")
    def module_config(self, module_id): return self.home / ".config/omarchy/customization-center" / module_id


class Ctx:
    module_id = "bar"
    paths = Paths()
    cache = {}


def test_model_round_trip_preserves_unknown_keys(bar_backend):
    document = json.loads(FIXTURE.read_text())
    normalized = bar_backend.model.from_shell(document["bar"])
    assert normalized["extra"] == {"futureKey": 7}
    assert bar_backend.model.to_shell(normalized) == document["bar"]


def test_validate_repeated_instances_and_anchor(bar_backend):
    status = status_value(bar_backend); draft = draft_from(status)
    valid = bar_backend.validate.validate(draft, status)
    assert valid.ok
    draft["bar"]["layout"]["right"].append({"key": "d:new", "origin": None, "id": "omarchy.clock", "settings": {}, "form": "object"})
    invalid = bar_backend.validate.validate(draft, status)
    assert {issue.code for issue in invalid.issues} >= {"bar_duplicate_not_allowed"}


def test_file_route_preserves_non_bar_document(bar_backend):
    status = status_value(bar_backend); draft = draft_from(status); draft["bar"]["position"] = "left"
    plan = bar_backend.planner.build_plan(Ctx(), draft, status)
    assert [operation.kind for operation in plan.operations] == ["ShellIpc", "WriteFileAtomic", "ShellIpc"]
    written = json.loads(plan.operations[1].params["content"])
    assert written["idle"] == {"timeout": 300} and written["plugins"] == ["example.panel"]
    assert written["bar"]["position"] == "left"
    assert plan.claims[0].key == "shell.bar"


def test_ipc_exact_second_instance_settings(bar_backend):
    status = status_value(bar_backend); draft = draft_from(status)
    draft["bar"]["layout"]["right"][1]["settings"]["size"] = 44
    plan = bar_backend.planner.build_plan(Ctx(), draft, status)
    assert len(plan.operations) == 1
    operation = plan.operations[0]
    assert operation.kind == "ShellIpc" and operation.params["method"] == "setBarWidget"
    assert operation.params["args"][-1] == {"section": "right", "index": 1}
    assert operation.inverse.params["args"][2] == 40


def test_remove_second_repeated_instance_is_addressed_exactly(bar_backend):
    status = status_value(bar_backend); draft = draft_from(status)
    draft["bar"]["layout"]["right"].pop(1)
    plan = bar_backend.planner.build_plan(Ctx(), draft, status)
    assert [operation.params["method"] for operation in plan.operations] == ["moveBarWidget", "setPluginEnabled"]
    assert plan.operations[0].params["args"][1]["fromIndex"] == 1


def test_preset_save_and_delete_plans_use_executor(bar_backend):
    status = status_value(bar_backend); status.data["presets"] = []
    draft = draft_from(status) | {"action": "save-preset", "presetId": "presentation", "presetName": "Presentation"}
    validation = bar_backend.validate.validate(draft, status)
    assert validation.ok
    plan = bar_backend.planner.build_plan(Ctx(), validation.normalized_draft, status)
    assert [item.kind for item in plan.operations] == ["EnsureDirectory", "WriteFileAtomic"]
    document = json.loads(plan.operations[-1].params["content"])
    assert document["id"] == "presentation" and document["name"] == "Presentation"
    assert all("key" not in item and "origin" not in item for values in document["bar"]["layout"].values() for item in values)

    status.data["presets"] = [document]
    deletion = draft_from(status) | {"action": "delete-preset", "presetId": "presentation", "presetName": None}
    plan = bar_backend.planner.build_plan(Ctx(), deletion, status)
    assert [item.kind for item in plan.operations] == ["RemoveFile"]
    assert plan.requires_confirmation == ("bar_preset_delete:presentation",)
