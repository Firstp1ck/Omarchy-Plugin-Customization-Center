from __future__ import annotations

import re
from typing import Any

from customization_center.core import ValidationIssue, ValidationResult

from .guards import check
from .warnings import classify

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*$")
_INDEX = re.compile(r"^(0|[1-9][0-9]*)$")
_PROTOTYPE = {"constructor", "hasOwnProperty", "isPrototypeOf", "propertyIsEnumerable", "toLocaleString",
              "toString", "valueOf", "__proto__", "__defineGetter__", "__defineSetter__",
              "__lookupGetter__", "__lookupSetter__"}
_EDITABLE = {"icon", "iconFont", "label", "title", "description", "action", "target", "provider",
             "when", "checked", "disabled"}
_PROVIDERS = {"apps", "fonts", "power-profiles"}


def _issue(code: str, message: str, pointer: str, severity: str = "error") -> ValidationIssue:
    return ValidationIssue(code, message, pointer, severity)


def _invalid_content(value: str, multiline: bool = True) -> bool:
    return any(ord(character) == 0 or ord(character) < 32 and character not in "\t\n" for character in value) or (not multiline and "\n" in value)


def validate_draft(ctx: Any, draft: dict[str, Any], status: Any, semantics: str) -> ValidationResult:
    issues: list[ValidationIssue] = []
    warnings: list[dict[str, Any]] = []
    if draft.get("schemaVersion") != 1 or draft.get("module") != "menu":
        issues.append(_issue("menu_invalid_draft", "Draft schemaVersion 1 and module menu are required", ""))
        return ValidationResult(False, tuple(issues), None)
    normalized = {**draft, "bom": False, "entries": []}
    base_revision = draft.get("baseRevision", "")
    if base_revision and base_revision != status.revision:
        issues.append(_issue("stale_revision", "The menu files changed on disk", "/baseRevision"))
    draft_semantics = draft.get("semantics", semantics)
    if draft_semantics != semantics:
        issues.append(_issue("menu_semantics_changed", "The installed menu merge semantics changed", "/semantics"))
    normalized["baseRevision"] = base_revision or status.revision
    normalized["semantics"] = draft_semantics
    shape = draft.get("shape", "direct")
    if shape not in {"direct", "wrapper"}:
        issues.append(_issue("menu_invalid_draft", "shape must be direct or wrapper", "/shape"))
    normalized["shape"] = shape
    seen: dict[str, int] = {}
    projected: dict[str, dict[str, Any]] = {}
    entries = draft.get("entries", [])
    if not isinstance(entries, list):
        issues.append(_issue("menu_invalid_draft", "entries must be an array", "/entries"))
        return ValidationResult(False, tuple(issues), None)
    for index, original in enumerate(entries):
        pointer = f"/entries/{index}"
        if not isinstance(original, dict):
            issues.append(_issue("menu_invalid_draft", "entry must be an object", pointer))
            continue
        entry = dict(original)
        entry.setdefault("draftId", f"entry-{index}")
        entry.setdefault("originalId", None)
        entry.setdefault("origin", "custom")
        entry.setdefault("kind", "submenu")
        entry.setdefault("fields", {})
        entry.setdefault("passthrough", {})
        entry.setdefault("raw", None)
        entry.setdefault("deleted", False)
        if not isinstance(entry["fields"], dict) or not isinstance(entry["passthrough"], dict):
            issues.append(_issue("menu_invalid_draft", "fields and passthrough must be objects", pointer))
            continue
        entry["fields"] = {key: value for key, value in entry["fields"].items()
                           if key in _EDITABLE and value != ""}
        item_id = entry.get("id")
        if not isinstance(item_id, str):
            issues.append(_issue("menu_invalid_id", "An entry id is required", pointer + "/id"))
            continue
        changed_id = entry.get("originalId") is None or item_id != entry.get("originalId")
        if entry.get("origin") != "preserved" and changed_id:
            if (item_id == "root" or item_id in _PROTOTYPE or any(_INDEX.fullmatch(segment) for segment in item_id.split("."))
                    or shape == "direct" and item_id == "items"):
                issues.append(_issue("menu_reserved_id", "This id is reserved by the menu runtime", pointer + "/id"))
            elif not _ID.fullmatch(item_id) or len(item_id.encode("utf-8")) > 128:
                issues.append(_issue("menu_invalid_id", "Use lowercase dotted menu id segments", pointer + "/id"))
        elif entry.get("origin") == "preserved":
            baseline = next((row for row in status.data.get("document", {}).get("entries", []) if row.get("id") == entry.get("originalId")), None)
            if baseline and not entry.get("deleted"):
                expected_raw = baseline.get("raw") if baseline.get("valueKind") == "other" else baseline.get("fields")
                actual_raw = entry.get("raw") if baseline.get("valueKind") == "other" else {**entry.get("fields", {}), **entry.get("passthrough", {})}
                if actual_raw != expected_raw:
                    issues.append(_issue("menu_preserved_modified", "Preserved entries may only be deleted", pointer))
        if entry.get("origin") == "shadowed" and semantics == "full-shadow" and not entry.get("deleted"):
            baseline = next((row for row in status.data.get("document", {}).get("entries", [])
                             if row.get("id") == entry.get("originalId")), None)
            authored = {**entry.get("fields", {}), **entry.get("passthrough", {})}
            if (baseline is None or item_id != entry.get("originalId") or baseline.get("valueKind") != "object"
                    or authored != baseline.get("fields", {})):
                issues.append(_issue("menu_shadow_immutable", "Remove this whole shadow; field edits require sparse merge semantics", pointer))
        baseline_entry = next((row for row in (status.data.get("document") or {}).get("entries", [])
                               if row.get("id") == (entry.get("originalId") or item_id)), None)
        if baseline_entry and baseline_entry.get("typeErrors") and not entry.get("deleted"):
            issues.append(_issue("menu_field_type", "This existing entry has a known field with the wrong JSON type; remove it before applying", pointer))
        if not entry.get("deleted"):
            if item_id in seen:
                issues.append(_issue("menu_duplicate_id", f"Duplicate id {item_id}", pointer + "/id"))
            seen[item_id] = index
            projected[item_id] = entry
        kind = entry.get("kind")
        fields = entry["fields"]
        action, target, provider = fields.get("action"), fields.get("target"), fields.get("provider")
        valid_kind = ((kind == "command" and bool(action) and not target and not provider)
                      or (kind == "link" and bool(target) and not action and not provider)
                      or (kind == "provider" and bool(provider) and not action and not target)
                      or (kind == "submenu" and not action and not target and not provider)
                      or entry.get("origin") == "preserved")
        if not valid_kind:
            issues.append(_issue("menu_ambiguous_kind", "Entry fields do not match its kind", pointer + "/kind"))
        if kind == "provider" and provider not in _PROVIDERS:
            baseline_provider = None
            if entry.get("originalId"):
                baseline_provider = next((row.get("fields", {}).get("provider")
                                          for row in (status.data.get("document") or {}).get("entries", [])
                                          if row.get("id") == entry.get("originalId")), None)
            severity = "warning" if provider == baseline_provider and baseline_provider is not None else "error"
            issues.append(_issue("menu_unknown_provider", f"Unknown provider {provider}", pointer + "/fields/provider", severity))
        for field, value in fields.items():
            if not isinstance(value, str) or _invalid_content(value, field not in {"label", "title"}):
                issues.append(_issue("menu_field_content", f"Invalid content in {field}", pointer + "/fields/" + field))
                continue
            if field in {"action", "when", "checked", "disabled"} and value:
                result = check(ctx, value, "action" if field == "action" else "guard")
                if not result["ok"]:
                    issues.append(_issue(result["code"], result["message"], pointer + "/fields/" + field))
                warnings.extend(classify(field, value, entry["draftId"]))
        normalized["entries"].append(entry)
    custom_seen = False
    for index, entry in enumerate(normalized["entries"]):
        if entry.get("deleted"):
            continue
        if entry.get("origin") == "custom":
            custom_seen = True
        elif entry.get("origin") == "shadowed" and custom_seen:
            issues.append(_issue("menu_shipped_position", "Shipped rows stay before custom rows in the runtime menu", f"/entries/{index}"))

    for item_id, entry in projected.items():
        if entry.get("origin") == "preserved":
            continue
        pointer = f"/entries/{seen[item_id]}"
        parent = entry.get("passthrough", {}).get("parent")
        if parent is None and "." in item_id:
            parent = item_id.rsplit(".", 1)[0]
        if parent and parent != "root" and parent not in projected and parent not in status.data.get("effective", {}).get("rows", {}):
            issues.append(_issue("menu_orphan_parent", f"Parent {parent} does not exist", pointer + "/id"))
        target = entry.get("fields", {}).get("target")
        if target:
            target_entry = projected.get(target)
            target_row = status.data.get("effective", {}).get("rows", {}).get(target)
            target_kind = target_entry.get("kind") if target_entry else ("submenu" if target_row and target_row.get("kind") == "menu" else None)
            if target_kind != "submenu":
                issues.append(_issue("menu_invalid_target", "A link target must be a submenu", pointer + "/fields/target"))
    rows = status.data.get("effective", {}).get("rows", {})
    parent_by_id = {item_id: row.get("parent", row.get("fields", {}).get("parent", "root")) for item_id, row in rows.items()}
    kind_by_id = {item_id: ("submenu" if row.get("kind") == "menu" else row.get("kind")) for item_id, row in rows.items()}
    target_by_id = {item_id: row.get("fields", {}).get("target", "") for item_id, row in rows.items()}
    for entry in normalized["entries"]:
        original_id = entry.get("originalId")
        if original_id:
            parent_by_id.pop(original_id, None)
            kind_by_id.pop(original_id, None)
            target_by_id.pop(original_id, None)
        if entry.get("deleted") or entry.get("origin") == "preserved":
            continue
        item_id = entry["id"]
        parent_by_id[item_id] = entry.get("passthrough", {}).get("parent", item_id.rsplit(".", 1)[0] if "." in item_id else "root")
        kind_by_id[item_id] = entry.get("kind")
        target_by_id[item_id] = entry.get("fields", {}).get("target", "")
    for item_id in projected:
        walked: set[str] = set()
        current = item_id
        depth = 0
        while current in parent_by_id and parent_by_id[current] not in {"", "root"}:
            current = parent_by_id[current]
            if current in walked or current == item_id:
                issues.append(_issue("menu_cycle", "Parent hierarchy contains a cycle", f"/entries/{seen[item_id]}/id"))
                break
            walked.add(current)
            depth += 1
            if depth >= 32:
                issues.append(_issue("menu_depth_exceeded", "Menu nesting reaches the runtime depth limit", f"/entries/{seen[item_id]}/id"))
                break
        if kind_by_id.get(item_id) == "link":
            walked = {item_id}
            target = target_by_id.get(item_id, "")
            while target and kind_by_id.get(target) == "link":
                if target in walked:
                    issues.append(_issue("menu_cycle", "Link targets contain a cycle", f"/entries/{seen[item_id]}/fields/target"))
                    break
                walked.add(target)
                target = target_by_id.get(target, "")
    errors = tuple(issue for issue in issues if issue.severity == "error")
    details = {"warnings": warnings, "issues": [issue.to_json() for issue in issues if issue.severity != "error"]}
    return ValidationResult(not errors, tuple(issues), normalized if not errors else None, details)
