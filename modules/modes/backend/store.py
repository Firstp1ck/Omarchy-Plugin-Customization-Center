from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from customization_center.core import CcError, ValidationIssue

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
THEME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
MEMBERS = ("monitors", "themes", "plugins", "bar", "menu", "keybindings", "defaults")
APPLY_MEMBERS = tuple(item for item in MEMBERS if item != "menu")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mode_dir(ctx: Any) -> Path:
    return ctx.paths.xdg_config_home / "omarchy/customization-center/desktop-modes"


def mode_path(ctx: Any, mode_id: str) -> Path:
    if not ID_PATTERN.fullmatch(mode_id) or ".." in mode_id:
        raise CcError("modes_invalid_id", "Mode id is malformed", {"id": mode_id})
    return mode_dir(ctx) / f"{mode_id}.json"


def rewrite_monitor_profile_reference(mode: dict[str, Any], old_id: str, new_id: str) -> None:
    monitors = mode.get("members", {}).get("monitors")
    if isinstance(monitors, dict) and monitors.get("profileId") == old_id:
        monitors["profileId"] = new_id


def _issue(code: str, message: str, pointer: str) -> ValidationIssue:
    return ValidationIssue(code, message, pointer, "error")


def _control_free(value: str) -> bool:
    return not any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)


def _absolute_string(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith(("/", "~/"))
    if isinstance(value, dict):
        return any(_absolute_string(item) for item in value.values())
    if isinstance(value, list):
        return any(_absolute_string(item) for item in value)
    return False


def validate_mode(value: Any, pointer: str = "/mode") -> tuple[list[ValidationIssue], dict[str, Any] | None]:
    issues: list[ValidationIssue] = []
    if not isinstance(value, dict):
        return [_issue("validation_failed", "mode must be an object", pointer)], None
    allowed = {"version", "id", "name", "description", "icon", "members", "triggers"}
    for key in sorted(set(value) - allowed):
        issues.append(_issue("validation_failed", f"Unknown mode field: {key}", f"{pointer}/{key}"))
    if value.get("version") != 1:
        issues.append(_issue("modes_unsupported_version", "Mode version must be 1", f"{pointer}/version"))
    mode_id = value.get("id")
    if not isinstance(mode_id, str) or not ID_PATTERN.fullmatch(mode_id) or ".." in mode_id:
        issues.append(_issue("modes_invalid_id", "Mode id must be a safe lowercase identifier", f"{pointer}/id"))
    name = value.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 80 or not _control_free(name):
        issues.append(_issue("validation_failed", "Mode name must contain 1 to 80 printable characters", f"{pointer}/name"))
    description = value.get("description", "")
    if not isinstance(description, str) or len(description) > 400 or not _control_free(description):
        issues.append(_issue("validation_failed", "Description must contain at most 400 printable characters", f"{pointer}/description"))
    icon = value.get("icon", "")
    if not isinstance(icon, str) or len(icon) > 4 or not _control_free(icon):
        issues.append(_issue("validation_failed", "Icon must contain at most four printable characters", f"{pointer}/icon"))
    triggers = value.get("triggers")
    if triggers != []:
        issues.append(_issue("modes_triggers_unsupported", "Automatic triggers are not supported", f"{pointer}/triggers"))
    members = value.get("members")
    if not isinstance(members, dict) or not members:
        issues.append(_issue("modes_empty", "Choose at least one mode member", f"{pointer}/members"))
        members = {}
    for member_id, section in members.items():
        member_pointer = f"{pointer}/members/{member_id}"
        if member_id not in MEMBERS:
            issues.append(_issue("modes_unknown_member", f"Unknown mode member: {member_id}", member_pointer)); continue
        if member_id == "menu":
            issues.append(_issue("modes_member_field_refused", "Menu is reserved but cannot be a mode member in version 1", member_pointer)); continue
        if not isinstance(section, dict) or not section:
            issues.append(_issue("modes_section_invalid", "Member section must be a non-empty object", member_pointer)); continue
        if member_id == "monitors":
            if set(section) != {"profileId"} or not isinstance(section.get("profileId"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", section["profileId"]):
                issues.append(_issue("modes_section_invalid", "Monitors requires one safe profileId", member_pointer))
        elif member_id == "themes":
            if set(section) - {"slug", "preferredWallpaper"} or not isinstance(section.get("slug"), str) or not THEME_PATTERN.fullmatch(section["slug"]):
                issues.append(_issue("modes_section_invalid", "Themes requires a valid slug", member_pointer))
            preferred = section.get("preferredWallpaper")
            if preferred is not None and (not isinstance(preferred, str) or not preferred or Path(preferred).name != preferred):
                issues.append(_issue("modes_section_invalid", "preferredWallpaper must be a file name", member_pointer + "/preferredWallpaper"))
        elif member_id == "plugins":
            if set(section) != {"enabled"} or not isinstance(section.get("enabled"), dict) or not section["enabled"]:
                issues.append(_issue("modes_section_invalid", "Plugins requires a non-empty enabled map", member_pointer))
            else:
                for plugin_id, enabled in section["enabled"].items():
                    if not isinstance(plugin_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", plugin_id) or ".." in plugin_id or not isinstance(enabled, bool):
                        issues.append(_issue("modes_section_invalid", "Plugin ids and boolean targets must be valid", member_pointer + "/enabled"))
        elif member_id == "bar":
            allowed_bar = {"id", "position", "transparent", "centerAnchor", "layout"}
            if set(section) - allowed_bar:
                issues.append(_issue("modes_section_invalid", "Bar section contains an unknown field", member_pointer))
            if "position" in section and section["position"] not in {"top", "bottom", "left", "right"}:
                issues.append(_issue("modes_section_invalid", "Bar position is invalid", member_pointer + "/position"))
            if "transparent" in section and not isinstance(section["transparent"], bool):
                issues.append(_issue("modes_section_invalid", "Bar transparent must be boolean", member_pointer + "/transparent"))
            if "id" in section and not isinstance(section["id"], str):
                issues.append(_issue("modes_section_invalid", "Bar id must be a string", member_pointer + "/id"))
            if "centerAnchor" in section and not isinstance(section["centerAnchor"], str):
                issues.append(_issue("modes_section_invalid", "Bar centerAnchor must be a string", member_pointer + "/centerAnchor"))
            if "layout" in section:
                layout = section["layout"]
                if not isinstance(layout, dict) or set(layout) != {"left", "center", "right"} or any(not isinstance(layout.get(name), list) for name in ("left", "center", "right")):
                    issues.append(_issue("modes_section_invalid", "Bar layout must include left, center, and right arrays", member_pointer + "/layout"))
                elif _absolute_string(layout):
                    issues.append(_issue("modes_section_invalid", "Bar settings must not contain absolute paths", member_pointer + "/layout"))
                else:
                    for name in ("left", "center", "right"):
                        if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] for item in layout[name]):
                            issues.append(_issue("modes_section_invalid", "Each bar layout entry requires an id", member_pointer + f"/layout/{name}"))
        elif member_id == "keybindings":
            document = section.get("document")
            if set(section) != {"document"} or not isinstance(document, dict) or document.get("schemaVersion") != 1 or not isinstance(document.get("bindings"), list) or not isinstance(document.get("disabled"), list):
                issues.append(_issue("modes_section_invalid", "Keybindings requires a complete version 1 managed document", member_pointer))
        elif member_id == "defaults":
            if "agent" in section:
                issues.append(_issue("modes_member_field_refused", "Coding agents cannot be mode members", member_pointer + "/agent"))
            if set(section) - {"browser", "terminal", "editor", "agent"} or any(not isinstance(item, str) or not item for item in section.values()):
                issues.append(_issue("modes_section_invalid", "Defaults values must be non-empty option ids", member_pointer))
    normalized = json.loads(json.dumps(value)) if not issues else None
    if normalized is not None:
        normalized.setdefault("description", ""); normalized.setdefault("icon", "")
    return issues, normalized


def load_modes(ctx: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    directory = mode_dir(ctx)
    try:
        files = sorted(directory.glob("*.json"))
    except OSError:
        files = []
    modes: list[dict[str, Any]] = []
    unreadable: list[dict[str, Any]] = []
    for path in files:
        try:
            raw = ctx.paths.read_regular(path, 1024 * 1024)
            value = json.loads(raw)
            issues, normalized = validate_mode(value, "")
            if issues or normalized is None or normalized["id"] != path.stem:
                code = "modes_invalid_id" if normalized and normalized["id"] != path.stem else issues[0].code
                raise CcError(code, issues[0].message if issues else "File name does not match mode id")
            modes.append({"mode": normalized, "digest": digest(normalized), "path": str(path)})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, CcError) as error:
            unreadable.append({"path": str(path), "code": getattr(error, "code", "modes_unsupported_version"), "message": str(error)})
    return modes, unreadable
