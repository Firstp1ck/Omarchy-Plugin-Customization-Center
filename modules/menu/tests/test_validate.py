import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import CommandResult, Status
from modules.menu.backend.validate import validate_draft

SAMPLE = Path(__file__).parent / "fixtures/sample-draft.json"


class Commands:
    def run(self, argv, **kwargs):
        return CommandResult(tuple(argv), 0, "", "", False, 1, False)


class FailingCommands:
    def run(self, argv, **kwargs):
        return CommandResult(tuple(argv), 2, "", "bash: line 1: syntax error", False, 1, False)


def _validate(draft, semantics="full-shadow", status=None):
    status = status or Status("menu", "revision", {"document": {"entries": []}, "effective": {"rows": {}}}, (), 1)
    return validate_draft(SimpleNamespace(commands=Commands()), draft, status, semantics)


@pytest.mark.parametrize("item_id,code", [("Upper", "menu_invalid_id"), ("a..b", "menu_invalid_id"),
                                           ("10", "menu_reserved_id"), ("a.0.b", "menu_reserved_id"),
                                           ("root", "menu_reserved_id"), ("__proto__", "menu_reserved_id")])
def test_invalid_and_reserved_ids(item_id, code):
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = "revision"
    draft["entries"][0]["id"] = item_id
    result = _validate(draft)
    assert code in {issue.code for issue in result.issues}


def test_ambiguous_kind_code():
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = "revision"
    entry = draft["entries"][0]
    entry["kind"] = "command"
    entry["fields"] = {"action": "true", "target": "root"}
    assert "menu_ambiguous_kind" in {issue.code for issue in _validate(draft).issues}


def test_new_unknown_provider_code():
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = "revision"
    entry = draft["entries"][0]
    entry["kind"] = "provider"
    entry["fields"] = {"provider": "unknown"}
    result = _validate(draft)
    assert next(issue for issue in result.issues if issue.code == "menu_unknown_provider").severity == "error"


def _shadow_case(label="About me"):
    baseline = {"id": "about", "valueKind": "object", "fields": {"label": "About"}}
    status = Status("menu", "revision", {"document": {"entries": [baseline]},
                    "effective": {"rows": {"about": {"kind": "menu", "parent": "root", "fields": {"target": ""}}}}}, (), 1)
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = "revision"
    draft["entries"] = [{"draftId": "shadow", "id": "about", "originalId": "about", "origin": "shadowed",
                         "kind": "submenu", "fields": {"label": label}, "passthrough": {}, "raw": None, "deleted": False}]
    return draft, status


def test_full_shadow_is_immutable_but_delete_is_allowed():
    draft, status = _shadow_case("Changed")
    result = _validate(draft, "full-shadow", status)
    assert "menu_shadow_immutable" in {issue.code for issue in result.issues}
    draft["entries"][0]["deleted"] = True
    assert _validate(draft, "full-shadow", status).ok


def test_sparse_shadow_field_edit_is_allowed():
    draft, status = _shadow_case("Changed")
    draft["semantics"] = "sparse"
    assert _validate(draft, "sparse", status).ok


def _base_draft():
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = "revision"
    return draft


def test_duplicate_id_code():
    draft = _base_draft()
    draft["entries"].append({**draft["entries"][0], "draftId": "duplicate"})
    assert "menu_duplicate_id" in {issue.code for issue in _validate(draft).issues}


def test_orphan_parent_code():
    draft = _base_draft()
    draft["entries"][0]["id"] = "missing.child"
    assert "menu_orphan_parent" in {issue.code for issue in _validate(draft).issues}


def test_invalid_target_code():
    draft = _base_draft()
    draft["entries"][0].update({"id": "link", "kind": "link", "fields": {"target": "missing"}})
    assert "menu_invalid_target" in {issue.code for issue in _validate(draft).issues}


def test_cycle_code():
    draft = _base_draft()
    first = draft["entries"][0]
    draft["entries"] = [{**first, "draftId": "a", "id": "a", "passthrough": {"parent": "b"}},
                        {**first, "draftId": "b", "id": "b", "passthrough": {"parent": "a"}}]
    assert "menu_cycle" in {issue.code for issue in _validate(draft).issues}


def test_semantics_changed_code():
    draft = _base_draft()
    draft["semantics"] = "sparse"
    assert "menu_semantics_changed" in {issue.code for issue in _validate(draft).issues}


def test_custom_entry_cannot_claim_position_before_shipped_shadow():
    draft, status = _shadow_case("About")
    custom = json.loads(SAMPLE.read_text())["entries"][0]
    draft["entries"].insert(0, custom)
    result = _validate(draft, "full-shadow", status)
    assert "menu_shipped_position" in {issue.code for issue in result.issues}


def test_stale_revision_code():
    draft = _base_draft()
    draft["baseRevision"] = "old"
    assert "stale_revision" in {issue.code for issue in _validate(draft).issues}


def test_field_content_code():
    draft = _base_draft()
    draft["entries"][0]["fields"]["label"] = "bad\nlabel"
    assert "menu_field_content" in {issue.code for issue in _validate(draft).issues}


def test_depth_exceeded_code():
    draft = _base_draft()
    base = draft["entries"][0]
    draft["entries"] = [{**base, "draftId": f"depth-{index}", "id": f"depth-{index}",
                         "passthrough": {} if index == 0 else {"parent": f"depth-{index - 1}"}}
                        for index in range(34)]
    assert "menu_depth_exceeded" in {issue.code for issue in _validate(draft).issues}


def test_preserved_modified_code():
    baseline = {"id": "legacy", "valueKind": "other", "fields": {}, "raw": 1, "typeErrors": []}
    status = Status("menu", "revision", {"document": {"entries": [baseline]}, "effective": {"rows": {}}}, (), 1)
    draft = _base_draft()
    draft["entries"] = [{"draftId": "legacy", "id": "legacy", "originalId": "legacy", "origin": "preserved",
                         "kind": "submenu", "fields": {}, "passthrough": {}, "raw": 2, "deleted": False}]
    assert "menu_preserved_modified" in {issue.code for issue in _validate(draft, status=status).issues}


def _syntax_result(fields):
    status = Status("menu", "revision", {"document": {"entries": []}, "effective": {"rows": {}}}, (), 1)
    draft = _base_draft()
    draft["entries"][0]["kind"] = "command"
    draft["entries"][0]["fields"] = {"action": "true", **fields}
    return validate_draft(SimpleNamespace(commands=FailingCommands()), draft, status, "full-shadow")


def test_action_syntax_failed_code():
    result = _syntax_result({"action": "[["})
    assert "menu_action_syntax_failed" in {issue.code for issue in result.issues}


def test_guard_syntax_failed_code():
    result = _syntax_result({"when": "[["})
    assert "menu_guard_syntax_failed" in {issue.code for issue in result.issues}


def test_existing_field_type_and_unknown_provider_are_reported():
    baseline = {"id": "provider", "valueKind": "object", "fields": {"provider": "future"},
                "typeErrors": [{"field": "label", "expected": "string", "actual": "int"}]}
    status = Status("menu", "revision", {"document": {"entries": [baseline]}, "effective": {"rows": {}}}, (), 1)
    draft = json.loads(SAMPLE.read_text())
    draft["baseRevision"] = "revision"
    draft["entries"] = [{"draftId": "provider", "id": "provider", "originalId": "provider", "origin": "custom",
                         "kind": "provider", "fields": {"provider": "future"}, "passthrough": {}, "raw": None, "deleted": False}]
    result = _validate(draft, status=status)
    codes = {issue.code: issue.severity for issue in result.issues}
    assert codes["menu_field_type"] == "error"
    assert codes["menu_unknown_provider"] == "warning"

    draft["entries"][0]["fields"]["provider"] = "different-future"
    changed = _validate(draft, status=status)
    changed_codes = {issue.code: issue.severity for issue in changed.issues}
    assert changed_codes["menu_unknown_provider"] == "error"
