from __future__ import annotations

import json
import re
from typing import Any

from customization_center.core import ValidationIssue
from .chords import ChordError, from_model
from .render import RenderError, render_body

_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_FLAGS = {"locked", "release", "repeating", "nonConsuming", "autoConsuming", "bypass"}


def empty_model() -> dict[str, Any]:
    return {"schemaVersion": 1, "bindings": [], "disabled": []}


def canonical_json(model: dict[str, Any]) -> str:
    return json.dumps(model, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _issue(code: str, message: str, pointer: str) -> ValidationIssue:
    return ValidationIssue(code, message, pointer, "error")


def validate_draft(draft: Any) -> tuple[list[ValidationIssue], dict[str, Any] | None, str | None]:
    issues: list[ValidationIssue] = []
    if not isinstance(draft, dict):
        return [_issue("keybindings_chord_grammar", "Draft must be an object", "")], None, None
    allowed_draft = {"schemaVersion", "expectedRevision", "model", "recoveryAction"}
    if not set(draft) <= allowed_draft or set(draft) < {"schemaVersion", "expectedRevision", "model"} or draft.get("schemaVersion") != 1:
        issues.append(_issue("keybindings_chord_grammar", "Draft fields or schemaVersion are invalid", "/schemaVersion"))
    if "recoveryAction" in draft and draft.get("recoveryAction") not in {"rewrite", "forget"}:
        issues.append(_issue("keybindings_chord_grammar", "Recovery action is invalid", "/recoveryAction"))
    if not isinstance(draft.get("expectedRevision"), str):
        issues.append(_issue("keybindings_chord_grammar", "Expected revision must be text", "/expectedRevision"))
    model = draft.get("model")
    if not isinstance(model, dict):
        issues.append(_issue("keybindings_chord_grammar", "Model must be an object", "/model"))
        return issues, None, None
    if set(model) != {"schemaVersion", "bindings", "disabled"} or model.get("schemaVersion") != 1:
        issues.append(_issue("keybindings_chord_grammar", "Model fields or schemaVersion are invalid", "/model/schemaVersion"))
    bindings = model.get("bindings")
    disabled = model.get("disabled")
    if not isinstance(bindings, list):
        issues.append(_issue("keybindings_chord_grammar", "Bindings must be an array", "/model/bindings")); bindings = []
    if not isinstance(disabled, list):
        issues.append(_issue("keybindings_chord_grammar", "Disabled defaults must be an array", "/model/disabled")); disabled = []
    ids: set[str] = set()
    identities: dict[tuple[str, bool], str] = {}
    for index, item in enumerate(bindings):
        pointer = f"/model/bindings/{index}"
        required = {"id", "enabled", "chord", "description", "action", "flags"}
        if not isinstance(item, dict) or set(item) != required:
            issues.append(_issue("keybindings_chord_grammar", "Binding fields are invalid", pointer)); continue
        binding_id = item.get("id")
        if not isinstance(binding_id, str) or not _UUID4.fullmatch(binding_id):
            issues.append(_issue("keybindings_chord_grammar", "Binding id must be a lowercase UUID v4", pointer + "/id"))
        elif binding_id in ids:
            issues.append(_issue("keybindings_draft_duplicate", "Binding and disable ids must be unique", pointer + "/id"))
        else: ids.add(binding_id)
        if not isinstance(item.get("enabled"), bool): issues.append(_issue("keybindings_chord_grammar", "enabled must be boolean", pointer + "/enabled"))
        description = item.get("description")
        if not isinstance(description, str) or not 1 <= len(description) <= 160 or any(ord(c) < 0x20 or ord(c) == 0x7f for c in description):
            issues.append(_issue("keybindings_control_character", "Description must be 1 to 160 printable characters", pointer + "/description"))
        try:
            chord = item.get("chord")
            if not isinstance(chord, dict) or set(chord) != {"sourceKeys", "modifiers", "key"}:
                raise ChordError("keybindings_chord_grammar", "Chord fields are invalid")
            parsed = from_model(chord)
            if parsed["sourceKeys"] != chord.get("sourceKeys"):
                raise ChordError("keybindings_chord_grammar", "sourceKeys is not the canonical chord spelling")
            duplicate_key = (parsed["identity"], bool(item.get("flags", {}).get("release")))
            if item.get("enabled") and duplicate_key in identities:
                issues.append(_issue("keybindings_draft_duplicate", "Two enabled bindings use the same chord and phase", pointer + "/chord"))
            identities[duplicate_key] = str(binding_id)
        except ChordError as error:
            issues.append(_issue(error.code, error.message, pointer + "/chord"))
        action = item.get("action")
        if not isinstance(action, dict) or set(action) != {"type", "command", "catalogId"} or action.get("type") != "exec" or not isinstance(action.get("catalogId"), (str, type(None))):
            issues.append(_issue("keybindings_chord_grammar", "Action fields are invalid", pointer + "/action"))
        else:
            command = action.get("command")
            if not isinstance(command, str) or not command or len(command.encode("utf-8", "surrogatepass")) > 4096 or "\0" in command or any(ord(c) < 0x20 and c != "\t" for c in command):
                issues.append(_issue("keybindings_control_character", "Command must be printable UTF-8 text up to 4096 bytes", pointer + "/action/command"))
        flags = item.get("flags")
        if not isinstance(flags, dict) or set(flags) != _FLAGS or any(not isinstance(value, bool) for value in flags.values()):
            issues.append(_issue("keybindings_flag_combination", "All six binding flags must be booleans", pointer + "/flags"))
        elif flags["nonConsuming"] and flags["autoConsuming"]:
            issues.append(_issue("keybindings_flag_combination", "nonConsuming and autoConsuming cannot both be enabled", pointer + "/flags"))
    binding_ids = {item.get("id") for item in bindings if isinstance(item, dict)}
    for index, item in enumerate(disabled):
        pointer = f"/model/disabled/{index}"
        required = {"id", "sourceKeys", "target", "reason", "replacedBy"}
        if not isinstance(item, dict) or set(item) != required:
            issues.append(_issue("keybindings_chord_grammar", "Disable fields are invalid", pointer)); continue
        disable_id = item.get("id")
        if not isinstance(disable_id, str) or not _UUID4.fullmatch(disable_id):
            issues.append(_issue("keybindings_chord_grammar", "Disable id must be a lowercase UUID v4", pointer + "/id"))
        elif disable_id in ids:
            issues.append(_issue("keybindings_draft_duplicate", "Binding and disable ids must be unique", pointer + "/id"))
        else: ids.add(disable_id)
        if not isinstance(item.get("sourceKeys"), str) or not item["sourceKeys"]:
            issues.append(_issue("keybindings_chord_grammar", "An exact source chord is required", pointer + "/sourceKeys"))
        target = item.get("target")
        if not isinstance(target, dict) or set(target) != {"kind", "module", "description", "identity"} or target.get("kind") not in {"omarchy_default", "managed"} or any(not isinstance(target.get(name), str) for name in ("module", "description", "identity")):
            issues.append(_issue("keybindings_chord_grammar", "Disable target is invalid", pointer + "/target"))
        if item.get("reason") not in {"disabled", "replaced"}:
            issues.append(_issue("keybindings_chord_grammar", "Disable reason is invalid", pointer + "/reason"))
        replacement = item.get("replacedBy")
        if replacement is not None and replacement not in binding_ids:
            issues.append(_issue("keybindings_unbind_target_missing", "Replacement binding does not exist", pointer + "/replacedBy"))
    rendered: str | None = None
    if not issues:
        try: rendered = render_body(model)
        except RenderError as error: issues.append(_issue(error.code, str(error), "/model"))
    normalized = json.loads(json.dumps(draft, ensure_ascii=False)) if not issues else None
    return issues, normalized, rendered
