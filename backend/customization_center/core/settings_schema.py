from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .types import ValidationIssue, ValidationResult

_TYPES = {"boolean", "integer", "string", "path", "enum", "multiselect"}
_RESERVED = {"id", "type", "exec", "source"}
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_ADAPTERS: dict[str, dict[str, Any]] = {
    "spacerSettings": {
        "adapterId": "spacerSettings@1", "ownership": "inline-entry",
        "fields": [{"key": "size", "type": "integer", "label": "Size (px)",
                    "description": "0 hides the spacer", "defaultValue": 12, "min": 0, "max": 4096, "step": 1}],
    },
    "weatherSettings": {
        "adapterId": "weatherSettings@1", "ownership": "inline-entry",
        "fields": [
            {"key": "unit", "type": "enum", "label": "Units", "defaultValue": "",
             "options": [{"value": "", "label": "Automatic"}, {"value": "metric", "label": "Metric"},
                         {"value": "imperial", "label": "Imperial"}]},
            {"key": "refreshMinutes", "type": "integer", "label": "Refresh interval (minutes)",
             "defaultValue": 15, "min": 1, "max": 1440, "step": 1},
        ],
        "external": {"ownership": "external", "path": "{home}/.local/state/omarchy/settings/weather.json",
                     "fields": ["name", "latitude", "longitude"],
                     "description": "Change the location from the weather popup"},
    },
}


def _problem(code: str, message: str, path: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def _valid_default(value: Any, kind: str, options: list[dict[str, str]] | None = None) -> bool:
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind in {"string", "path", "enum"}:
        valid = isinstance(value, str)
        return valid and (kind != "enum" or value in {x["value"] for x in options or []})
    if kind == "multiselect":
        allowed = {x["value"] for x in options or []}
        return isinstance(value, list) and all(isinstance(x, str) and x in allowed for x in value) and len(value) == len(set(value))
    return False


def normalize(manifest_or_bar_widget: dict[str, Any]) -> dict[str, Any]:
    manifest = manifest_or_bar_widget if ({"barWidget", "customizationCenter"} & set(manifest_or_bar_widget)) else None
    bar = manifest_or_bar_widget.get("barWidget", manifest_or_bar_widget)
    if not isinstance(bar, dict):
        bar = {}
    raw_schema = bar.get("schema", [])
    problems: list[dict[str, str]] = []
    fields: list[dict[str, Any]] = []
    skipped = False
    if not isinstance(raw_schema, list):
        problems.append(_problem("plugins_schema_not_array", "barWidget.schema must be an array", "/barWidget/schema"))
        skipped = True
        raw_schema = []
    seen: set[str] = set()
    defaults = bar.get("defaults") if isinstance(bar.get("defaults"), dict) else {}
    for index, raw in enumerate(raw_schema):
        path = f"/barWidget/schema/{index}"
        if not isinstance(raw, dict):
            problems.append(_problem("plugins_field_not_object", "Schema field must be an object", path))
            skipped = True
            continue
        key = raw.get("key")
        if not isinstance(key, str) or not _KEY.match(key) or key in _RESERVED or key in seen:
            problems.append(_problem("plugins_field_bad_key", "Field key is missing, reserved, malformed, or duplicated", path + "/key"))
            skipped = True
            continue
        seen.add(key)
        kind = raw.get("type")
        if kind not in _TYPES:
            problems.append(_problem("plugins_field_unknown_type", f"Unknown field type: {kind}", path + "/type"))
            skipped = True
            continue
        field: dict[str, Any] = {"key": key, "type": kind,
                                 "label": raw.get("label") if isinstance(raw.get("label"), str) and raw["label"] else key}
        if isinstance(raw.get("description"), str):
            field["description"] = raw["description"]
        aliases = {"min": "minimum", "max": "maximum", "defaultValue": "default"}
        values = dict(raw)
        for canonical, alias in aliases.items():
            if canonical not in values and alias in values:
                values[canonical] = values[alias]
                problems.append(_problem("plugins_field_alias_used", f"Use {canonical} instead of {alias}", path + "/" + alias))
        if kind == "integer":
            for bound in ("min", "max", "step"):
                if bound not in values:
                    continue
                value = values[bound]
                if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
                    value = int(value)
                if not isinstance(value, int) or isinstance(value, bool) or (bound == "step" and value < 1):
                    problems.append(_problem("plugins_field_bad_bound", f"Invalid {bound}", path + "/" + bound))
                else:
                    field[bound] = value
            if "min" in field and "max" in field and field["min"] > field["max"]:
                problems.append(_problem("plugins_field_bad_bound", "min must not exceed max", path))
                skipped = True
                continue
        options: list[dict[str, str]] | None = None
        if kind in {"enum", "multiselect"}:
            options = []
            option_seen: set[str] = set()
            for option_index, option in enumerate(values.get("options", []) if isinstance(values.get("options"), list) else []):
                normalized: dict[str, str] | None = None
                if isinstance(option, str):
                    normalized = {"value": option, "label": option}
                elif isinstance(option, dict) and isinstance(option.get("value"), str):
                    normalized = {"value": option["value"], "label": option.get("label", option["value"])}
                    if not isinstance(normalized["label"], str):
                        normalized["label"] = option["value"]
                    if isinstance(option.get("description"), str):
                        normalized["description"] = option["description"]
                if normalized is None or normalized["value"] in option_seen:
                    problems.append(_problem("plugins_field_bad_option", "Invalid or duplicate option", f"{path}/options/{option_index}"))
                    continue
                option_seen.add(normalized["value"])
                options.append(normalized)
            if not options:
                problems.append(_problem("plugins_field_no_options", "Enum fields require options", path + "/options"))
                skipped = True
                continue
            field["options"] = options
        default_source = "field"
        has_default = "defaultValue" in values
        default_value = values.get("defaultValue")
        if not has_default and key in defaults:
            has_default = True
            default_value = defaults[key]
            default_source = "barWidget.defaults"
        if has_default:
            if _valid_default(default_value, kind, options):
                if kind == "integer" and (("min" in field and default_value < field["min"]) or
                                          ("max" in field and default_value > field["max"])):
                    problems.append(_problem("plugins_field_bad_default", "Default is outside bounds", path + "/defaultValue"))
                else:
                    field["defaultValue"] = default_value
                    field["defaultSource"] = default_source
            else:
                problems.append(_problem("plugins_field_bad_default", "Default has the wrong type or value", path + "/defaultValue"))
        ui = {key: raw[key] for key in ("noSelectionText", "placeholderText", "emptyText") if isinstance(raw.get(key), str)}
        if ui:
            field["ui"] = ui
        recognized = {"key", "type", "label", "description", "min", "max", "step", "defaultValue", "options",
                      "noSelectionText", "placeholderText", "emptyText", "minimum", "maximum", "default"}
        for extra in sorted(set(raw) - recognized):
            problems.append(_problem("plugins_field_extra_ignored", f"Ignored field property: {extra}", path + "/" + extra))
        fields.append(field)
    form_name = bar.get("settingsForm") if isinstance(bar.get("settingsForm"), str) else None
    adapter = _ADAPTERS.get(form_name or "")
    adapter_id = adapter.get("adapterId") if adapter else None
    if form_name and not adapter:
        problems.append(_problem("plugins_unknown_settings_form", f"Unknown settings form: {form_name}", "/barWidget/settingsForm"))
    if adapter:
        adapter_keys = {field["key"] for field in fields}
        fields.extend(dict(field) for field in adapter["fields"] if field["key"] not in adapter_keys)
    if skipped:
        support = "invalid"
    elif raw_schema and adapter:
        support = "schema+adapter"
    elif raw_schema:
        support = "schema"
    elif adapter:
        support = "adapter"
    else:
        support = "none"
    result: dict[str, Any] = {"version": 1, "scope": "bar-widget-entry", "support": support,
                              "adapterId": adapter_id, "fields": fields, "problems": problems,
                              "extension": None}
    if adapter:
        result["ownership"] = adapter["ownership"]
        if "external" in adapter:
            result["external"] = adapter["external"]
    result["fingerprint"] = fingerprint(result)
    if manifest is not None and "customizationCenter" in manifest:
        extension_raw = manifest["customizationCenter"]
        extension_problems: list[dict[str, str]] = []
        if not isinstance(extension_raw, dict):
            extension = {"version": 1, "scope": "shell-entry", "support": "invalid", "adapterId": None,
                         "fields": [], "problems": [_problem("plugins_schema_not_array",
                                                              "customizationCenter must be an object",
                                                              "/customizationCenter")], "readOnly": True}
        else:
            extension_normalized = normalize({"barWidget": {"schema": extension_raw.get("schema", [])}})
            for item in extension_normalized["problems"]:
                changed = dict(item)
                changed["path"] = changed["path"].replace("/barWidget/schema", "/customizationCenter/schema")
                extension_problems.append(changed)
            if extension_raw.get("settingsVersion") != 1:
                extension_problems.append(_problem("plugins_schema_version_unsupported",
                                                   "customizationCenter.settingsVersion must be 1",
                                                   "/customizationCenter/settingsVersion"))
            if extension_raw.get("scope") != "shell-entry":
                extension_problems.append(_problem("plugins_schema_scope_invalid",
                                                   "customizationCenter.scope must be shell-entry",
                                                   "/customizationCenter/scope"))
            extension_support = extension_normalized["support"]
            if any(item["code"] in {"plugins_schema_version_unsupported", "plugins_schema_scope_invalid"}
                   for item in extension_problems):
                extension_support = "invalid"
            extension = {"version": extension_raw.get("settingsVersion"), "scope": extension_raw.get("scope"),
                         "support": extension_support, "adapterId": None,
                         "fields": extension_normalized["fields"], "problems": extension_problems,
                         "readOnly": True}
        extension["fingerprint"] = fingerprint(extension)
        result["extension"] = extension
    return result


def fingerprint(schema: dict[str, Any]) -> str:
    payload = {"fields": schema.get("fields", []), "adapterId": schema.get("adapterId")}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def validate(values: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
    issues: list[ValidationIssue] = []
    normalized: dict[str, Any] = {}
    for field in schema.get("fields", []):
        key, kind = field["key"], field["type"]
        if key not in values:
            continue
        value = values[key]
        valid = _valid_default(value, kind, field.get("options"))
        if valid and kind == "integer":
            valid = not (("min" in field and value < field["min"]) or ("max" in field and value > field["max"]))
        if not valid:
            issues.append(ValidationIssue("validation_failed", f"Invalid value for {key}", "/" + key, "error"))
        else:
            if kind == "integer" and "step" in field:
                origin = field.get("min", 0)
                if (value - origin) % field["step"] != 0:
                    issues.append(ValidationIssue("validation_failed", f"{key} is not aligned to step {field['step']}",
                                                  "/" + key, "warning"))
            if kind == "multiselect":
                order = {option["value"]: i for i, option in enumerate(field.get("options", []))}
                value = sorted(value, key=lambda item: order[item])
            normalized[key] = value
    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationResult(not has_errors, tuple(issues), normalized if not has_errors else None)


def adapter(name: str) -> dict[str, Any] | None:
    value = _ADAPTERS.get(name)
    return json.loads(json.dumps(value)) if value else None
