from __future__ import annotations

import copy
import re
from typing import Any

from customization_center.core import ValidationIssue, ValidationResult, settings_schema
from .model import SECTIONS, all_entries, counts, rebase


def validate(draft: dict[str, Any], status: Any) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if not isinstance(draft, dict) or draft.get("schemaVersion") != 1 or draft.get("module") != "bar":
        return ValidationResult(False, (ValidationIssue("validation_failed", "Expected a bar schemaVersion 1 draft", "", "error"),), None)
    if draft.get("baseRevision") != status.revision:
        issues.append(ValidationIssue("stale_revision", "The shell configuration or plugin catalog changed", "/baseRevision", "error"))
    action = draft.get("action", "apply")
    if action not in {"apply", "save-preset", "delete-preset"}:
        issues.append(ValidationIssue("validation_failed", "Unknown bar draft action", "/action", "error"))
    if action in {"save-preset", "delete-preset"}:
        preset_id = draft.get("presetId")
        if not isinstance(preset_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", preset_id):
            issues.append(ValidationIssue("bar_preset_id_invalid", "Preset id must use lowercase letters, digits, and hyphens", "/presetId", "error"))
        if action == "save-preset" and (not isinstance(draft.get("presetName"), str) or not draft.get("presetName", "").strip() or len(draft.get("presetName", "")) > 60):
            issues.append(ValidationIssue("bar_preset_name_invalid", "Preset name must be 1 to 60 characters", "/presetName", "error"))
    candidate = draft.get("bar")
    if not isinstance(candidate, dict):
        return ValidationResult(False, tuple(issues) + (ValidationIssue("validation_failed", "bar must be an object", "/bar", "error"),), None)
    bar = rebase(status.data["bar"], candidate)
    if bar.get("position") not in {"top", "bottom", "left", "right"}:
        issues.append(ValidationIssue("bar_position_invalid", "Position must be top, bottom, left, or right", "/bar/position", "error"))
    options = {item.get("id"): item for item in status.data.get("barOptions", [])}
    configured = bar.get("id") or "omarchy.bar"
    if configured not in options or not options[configured].get("available"):
        issues.append(ValidationIssue("bar_bar_option_unknown", f"Bar option {configured} is not available", "/bar/id", "error"))
    elif configured != "omarchy.bar" and not options[configured].get("firstParty"):
        issues.append(ValidationIssue("bar_third_party_bar", "Third-party bars run unsandboxed and may fall back to the built-in bar", "/bar/id", "warning"))
    catalog = {item.get("id"): item for item in status.data.get("catalog", [])}
    base_counts = counts(status.data["bar"]); draft_counts = counts(bar)
    seen_origins: set[tuple[str, int]] = set()
    edited_by_origin: dict[tuple[str, int], dict[str, Any]] = {}
    for section, index, entry in all_entries(bar):
        pointer = f"/bar/layout/{section}/{index}"
        widget_id = entry.get("id")
        if not isinstance(widget_id, str) or not widget_id or "/" in widget_id or ".." in widget_id:
            issues.append(ValidationIssue("bar_entry_id_invalid", "Widget id is empty or unsafe", pointer + "/id", "error")); continue
        if any(key in entry.get("settings", {}) for key in ("key", "origin", "form")):
            issues.append(ValidationIssue("bar_draft_keys_leak", "Draft identity fields cannot be widget settings", pointer + "/settings", "error"))
        origin = entry.get("origin")
        if origin is not None:
            key = (origin.get("section"), origin.get("index")) if isinstance(origin, dict) else (None, None)
            base_values = status.data["bar"]["layout"].get(key[0], []) if key[0] in SECTIONS else []
            if key in seen_origins or not isinstance(key[1], int) or key[1] < 0 or key[1] >= len(base_values) or base_values[key[1]].get("id") != widget_id:
                issues.append(ValidationIssue("bar_origin_invalid", "Entry origin does not identify a unique base occurrence", pointer + "/origin", "error"))
            else:
                seen_origins.add(key); edited_by_origin[key] = entry
        elif catalog.get(widget_id, {}).get("presence") != "shell":
            issues.append(ValidationIssue("bar_unknown_widget", "Only widgets currently discovered by the shell can be added", pointer + "/id", "error"))
        item = catalog.get(widget_id, {})
        if item.get("schema", {}).get("ok"):
            result = settings_schema.validate(entry.get("settings", {}), item["schema"])
            base_entry = None
            if isinstance(origin, dict) and origin.get("section") in SECTIONS:
                values = status.data["bar"]["layout"][origin["section"]]
                if isinstance(origin.get("index"), int) and 0 <= origin["index"] < len(values): base_entry = values[origin["index"]]
            for problem in result.issues:
                preexisting = base_entry and base_entry.get("settings", {}).get(problem.pointer.lstrip("/")) == entry.get("settings", {}).get(problem.pointer.lstrip("/"))
                issues.append(ValidationIssue("bar_settings_preexisting" if preexisting else "bar_settings_invalid", problem.message,
                                              pointer + "/settings" + problem.pointer, "warning" if preexisting else problem.severity))
        elif entry.get("settings"):
            issues.append(ValidationIssue("bar_schema_readonly", "This widget has no supported settings schema; preserved settings are read-only", pointer + "/settings", "warning"))
    for widget_id, total in draft_counts.items():
        item = catalog.get(widget_id, {})
        if total > max(base_counts.get(widget_id, 0), 1) and not item.get("allowMultiple"):
            issues.append(ValidationIssue("bar_duplicate_not_allowed", f"{widget_id} does not allow another instance", "/bar/layout", "error"))
        elif total > 1 and total <= base_counts.get(widget_id, 0) and not item.get("allowMultiple"):
            issues.append(ValidationIssue("bar_existing_duplicate", f"Existing repeated {widget_id} instances are preserved", "/bar/layout", "warning"))
    anchor = bar.get("centerAnchor", "")
    anchor_count = sum(1 for item in bar["layout"]["center"] if item.get("id") == anchor) if anchor else 0
    if anchor and anchor_count == 0:
        issues.append(ValidationIssue("bar_anchor_missing", "Center anchor must name a widget in the center section", "/bar/centerAnchor", "error"))
    elif anchor_count > 1:
        inherited = anchor == status.data["bar"].get("centerAnchor")
        issues.append(ValidationIssue("bar_anchor_ambiguous_inherited" if inherited else "bar_anchor_ambiguous",
                                      "The shell anchors the first matching center instance", "/bar/centerAnchor", "warning" if inherited else "error"))
    if status.data.get("shell", {}).get("fallback") and configured == status.data["shell"].get("configuredBarId"):
        issues.append(ValidationIssue("bar_fallback_now", "The configured bar is currently falling back to the built-in bar", "/bar/id", "warning"))
    if bar.get("position") in {"left", "right"}:
        text_ids = {item["id"] for item in status.data.get("catalog", []) if item.get("sizeClass") == "text"}
        if sum(1 for _, _, entry in all_entries(bar) if entry.get("id") in text_ids) > 4:
            issues.append(ValidationIssue("bar_vertical_text", "Many text widgets collapse to icons on a vertical bar", "/bar/position", "warning"))
    errors = any(item.severity == "error" for item in issues)
    normalized = copy.deepcopy(draft); normalized["bar"] = bar
    return ValidationResult(not errors, tuple(issues), None if errors else normalized)
