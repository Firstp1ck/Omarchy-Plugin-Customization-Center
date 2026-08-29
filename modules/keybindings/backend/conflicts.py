from __future__ import annotations

from typing import Any

from .chords import from_model


def _keymap(context: dict[str, Any] | None) -> tuple[dict[int, str], bool]:
    value = context or {}
    mapping = {int(key): str(symbol) for key, symbol in value.get("codeToKeysym", {}).items()}
    multiple = bool(value.get("multipleLayouts", len(value.get("layouts", [])) > 1)) and not bool(value.get("resolveBindsBySym", False))
    return mapping, multiple


def _record_key(record: dict[str, Any]) -> tuple[str, Any]:
    token = str(record.get("keyToken", ""))
    if token.startswith("code:") and token[5:].isdigit():
        return "code", int(token[5:])
    identity = str(record.get("identity", ""))
    parts = identity.split(":", 2)
    if len(parts) == 3:
        return parts[1], parts[2]
    return "unknown", token.casefold()


def _alias(left_kind: str, left_value: Any, right_kind: str, right_value: Any,
           mapping: dict[int, str], multiple_layouts: bool) -> str:
    if {left_kind, right_kind} != {"code", "keysym"}:
        return ""
    code = int(left_value if left_kind == "code" else right_value)
    symbol = str(right_value if left_kind == "code" else left_value).casefold()
    if multiple_layouts:
        return "possible_alias"
    if mapping:
        return "alias_conflict" if mapping.get(code, "").casefold() == symbol else ""
    return "possible_alias"


def classify_conflicts(model: dict[str, Any], records: list[dict[str, Any]],
                       keymap_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    enabled = [item for item in model.get("bindings", []) if item.get("enabled")]
    disabled_identities = {item.get("target", {}).get("identity") for item in model.get("disabled", [])}
    mapping, multiple_layouts = _keymap(keymap_context)
    seen: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for item in enabled:
        parsed = from_model(item["chord"])
        phase = "release" if item["flags"]["release"] else "press"
        for other, other_parsed, other_phase in seen:
            if parsed["identity"] == other_parsed["identity"] and phase == other_phase:
                findings.append(_finding("draft_duplicate", "blocker", item["id"], [other["id"]],
                                         "Two draft bindings use the same chord", ["choose_another_chord"]))
            alias = _alias(parsed["keyKind"], parsed["keyValue"], other_parsed["keyKind"], other_parsed["keyValue"], mapping, multiple_layouts)
            if alias and phase == other_phase and parsed["modmask"] == other_parsed["modmask"]:
                findings.append(_finding(alias, "blocker" if alias == "alias_conflict" else "warning", item["id"], [other["id"]],
                                         "Two draft bindings may name the same physical key",
                                         ["choose_another_chord"] if alias == "alias_conflict" else ["confirm_overlap", "use_physical_key", "use_symbol_key"]))
        seen.append((item, parsed, phase))
        remaining = [record for record in records if record.get("domain") == "keyboard" and not record.get("submap")
                     and record.get("identity") not in disabled_identities and record.get("managedId") != item.get("id")]
        exact = [record for record in remaining if record.get("identity") == parsed["identity"] and record.get("phase") == phase]
        if exact:
            findings.append(_finding("exact_conflict", "blocker", item["id"], [record["index"] for record in exact],
                                     "The chord is already bound", ["choose_another_chord", "replace_affected"]))
            if any(record.get("flags", {}).get("unknownLetters") for record in exact):
                findings.append(_finding("device_scope_unknown", "blocker", item["id"], [record["index"] for record in exact],
                                         "The existing binding may be device scoped", ["choose_another_chord"]))
        phase_rows = [record for record in remaining if record.get("identity") == parsed["identity"] and record.get("phase") != phase]
        if not exact and phase_rows:
            findings.append(_finding("phase_pair", "note", item["id"], [record["index"] for record in phase_rows],
                                     "The chord has an action in another phase", ["replace_affected"]))
        for record in remaining:
            record_kind, record_value = _record_key(record)
            alias = _alias(parsed["keyKind"], parsed["keyValue"], record_kind, record_value, mapping, multiple_layouts)
            if alias and parsed["modmask"] == int(record.get("modmask", -1)) and phase == record.get("phase"):
                findings.append(_finding(alias, "blocker" if alias == "alias_conflict" else "warning", item["id"], [record["index"]],
                                         "The chord may alias an active binding on the current keymap",
                                         ["replace_affected"] if alias == "alias_conflict" else ["confirm_overlap", "use_physical_key", "use_symbol_key"]))
        submaps = [record for record in records if record.get("identity") == parsed["identity"] and
                   (record.get("submap") or record.get("flags", {}).get("submapUniversal"))]
        if submaps:
            findings.append(_finding("submap_shadow", "warning", item["id"], [record["index"] for record in submaps],
                                     "The chord is also used in a submap", ["confirm_overlap"]))
        wildcard = [record for record in remaining if record.get("catchall") or
                    any(letter in record.get("headerFlags", []) for letter in ("i", "s"))]
        if wildcard:
            findings.append(_finding("wildcard_overlap", "warning", item["id"], [record["index"] for record in wildcard],
                                     "A wildcard binding may overlap this chord", ["confirm_overlap"]))
        value = str(parsed["keyValue"])
        if parsed["keyKind"] == "keysym" and value.isdigit() and "SHIFT" in parsed["modifiers"]:
            findings.append(_finding("shifted_digit", "warning", item["id"], [],
                                     "Shifted digits depend on the active layout", ["use_physical_key"]))
        stable_names = {"Return", "Tab", "Escape", "BackSpace", "Delete", "Insert", "Home", "End", "Prior", "Next", "Left", "Right", "Up", "Down"}
        stable = (len(value) == 1 and value.isascii() and value.isalnum()) or value.startswith("F") or value.startswith("XF86") or value in stable_names
        if parsed["keyKind"] == "keysym" and multiple_layouts and not stable:
            findings.append(_finding("layout_dependent", "warning", item["id"], [],
                                     "This symbol depends on the active keyboard layout", ["use_physical_key"]))
    runtime_identities = {record.get("identity") for record in records}
    for item in model.get("disabled", []):
        identity = item.get("target", {}).get("identity")
        if identity and identity not in runtime_identities and item.get("target", {}).get("kind") != "omarchy_default":
            findings.append(_finding("unbind_target_missing", "blocker", item["id"], [],
                                     "The unbind target no longer exists", ["choose_another_chord"]))
        affected = [record["index"] for record in records if record.get("identity") == identity]
        if len(affected) > 1:
            findings.append(_finding("stack_collateral", "warning", item["id"], affected,
                                     "Unbinding removes every action on this chord", ["confirm_overlap"]))
    return findings


def _finding(category: str, severity: str, subject: str, affected: list[Any], reason: str,
             remedies: list[str]) -> dict[str, Any]:
    return {"category": category, "severity": severity, "subjectId": subject,
            "affected": affected, "reason": reason, "remedies": remedies}
