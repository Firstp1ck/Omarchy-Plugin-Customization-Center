from __future__ import annotations

import json
import re
from typing import Any

from .chords import runtime_identity

_HEADER = re.compile(r"^bind([a-z]*)$")
_FIELD = re.compile(r"^\t([a-z_]+):(?: (.*))?$")
_REQUIRED = ("modmask", "key", "keycode", "dispatcher")
_JSON_BOOLS = ("locked", "mouse", "release", "repeat", "longPress", "non_consuming", "auto_consuming",
               "has_description", "catch_all", "allow_input_capture")


def split_key_field(key: str, keycode: int) -> str:
    if key == "" and keycode:
        return f"code:{keycode}"
    if " + " in key:
        return key.rsplit(" + ", 1)[1]
    return key


def parse_plain(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_field = ""

    def close() -> None:
        nonlocal current, last_field
        if current is None:
            return
        fields = current.pop("_fields")
        missing = [name for name in _REQUIRED if name not in fields]
        error = ""
        try:
            modmask = int(fields.get("modmask", ""), 10)
            keycode = int(fields.get("keycode", ""), 10)
        except ValueError:
            modmask, keycode, error = 0, 0, "modmask or keycode is not a decimal integer"
        if missing:
            error = "missing fields: " + ", ".join(missing)
        if current.get("_parseProblems"):
            error = error or "; ".join(current.pop("_parseProblems"))
        catch = fields.get("catchall", "false")
        if catch not in {"true", "false"}:
            error = error or "catchall is not boolean"
        key = fields.get("key", "")
        token = split_key_field(key, keycode)
        identity, display, key_kind = runtime_identity(modmask, token, keycode)
        flags = sorted(current["headerFlags"])
        unknown = [letter for letter in flags if letter not in {"d", "l", "e"}]
        domain = "catchall" if catch == "true" or token == "catchall" else ("switch" if token.startswith("switch:") else ("pointer" if token.startswith("mouse") else "keyboard"))
        known = {name: fields.get(name, default) for name, default in (("submap", ""), ("description", ""), ("arg", ""))}
        extra = {name: value for name, value in fields.items() if name not in {*_REQUIRED, "submap", "catchall", "description", "arg"}}
        current.update({"modmask": modmask, "keyFieldRaw": key, "keyToken": token, "keycode": keycode,
                        "submap": known["submap"], "catchall": catch == "true", "description": known["description"],
                        "dispatcher": fields.get("dispatcher", ""), "arg": known["arg"], "extra": extra,
                        "flags": {"locked": "l" in flags, "release": False, "repeating": "e" in flags,
                                  "longPress": False, "nonConsuming": False, "autoConsuming": False,
                                  "mouse": domain == "pointer", "submapUniversal": False,
                                  "allowInputCapture": False, "unknownLetters": unknown},
                        "flagSource": "header", "domain": domain, "identity": identity, "phase": "press",
                        "display": display, "parseError": error or None})
        if error:
            warnings.append({"code": "keybindings_binds_unparseable", "message": error, "record": current["index"]})
        records.append(current)
        current, last_field = None, ""

    lines = text.split("\n")
    for line in lines:
        header = _HEADER.match(line)
        if header:
            close()
            current = {"index": len(records), "headerFlags": sorted(set(header.group(1))), "rawText": line, "_fields": {}}
            continue
        if current is None:
            if line:
                warnings.append({"code": "keybindings_binds_unparseable", "message": "text outside a bind record"})
            continue
        current["rawText"] += "\n" + line
        if line == "":
            close()
            continue
        field = _FIELD.match(line)
        if field:
            name, value = field.group(1), field.group(2) or ""
            if name in current["_fields"]:
                current.setdefault("_parseProblems", []).append("repeated field: " + name)
            current["_fields"][name] = value
            last_field = name
        elif last_field:
            current["_fields"][last_field] += "\n" + line
            warnings.append({"code": "keybindings_binds_continuation", "message": "continued bind field", "record": current["index"]})
        else:
            current.setdefault("_parseProblems", []).append("continuation before first field")
    close()
    return records, warnings


def reconcile_json(records: list[dict[str, Any]], text: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        values = json.loads(text)
    except json.JSONDecodeError:
        return records, {"code": "keybindings_binds_json_untrusted", "message": "JSON inventory is invalid"}
    if not isinstance(values, list) or len(values) != len(records):
        return records, {"code": "keybindings_binds_json_untrusted", "message": "JSON inventory count differs from plain inventory"}
    for index, (value, record) in enumerate(zip(values, records)):
        if not isinstance(value, dict):
            return records, {"code": "keybindings_binds_json_untrusted", "message": f"JSON record {index} is not an object"}
        if any(not isinstance(value.get(name), bool) for name in _JSON_BOOLS):
            return records, {"code": "keybindings_binds_json_untrusted", "message": f"JSON record {index} has an invalid boolean"}
        expected = (("modmask", record["modmask"]), ("key", record["keyFieldRaw"]), ("keycode", record["keycode"]),
                    ("submap", record["submap"]), ("dispatcher", record["dispatcher"]))
        if any(value.get(name) != wanted for name, wanted in expected) or value.get("submap_universal") not in {"true", "false"}:
            return records, {"code": "keybindings_binds_json_untrusted", "message": f"JSON record {index} is misaligned"}
    for value, record in zip(values, records):
        flags = record["flags"]
        flags.update({"locked": value["locked"], "release": value["release"], "repeating": value["repeat"],
                      "longPress": value["longPress"], "nonConsuming": value["non_consuming"],
                      "autoConsuming": value["auto_consuming"], "mouse": value["mouse"],
                      "submapUniversal": value["submap_universal"] == "true",
                      "allowInputCapture": value["allow_input_capture"]})
        record["catchall"] = value["catch_all"]
        record["phase"] = "release" if flags["release"] else ("long_press" if flags["longPress"] else "press")
        record["flagSource"] = "json"
    return records, None


def parse_devices(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"keyboard": None, "layouts": [], "multipleLayouts": False, "switches": [], "warning": "devices output is invalid"}
    if not isinstance(data, dict):
        return {"keyboard": None, "layouts": [], "multipleLayouts": False, "switches": [], "warning": "devices output is invalid"}
    keyboards = data.get("keyboards", [])
    valid = [item for item in keyboards if isinstance(item, dict)]
    keyboard = next((item for item in valid if item.get("main") is True), valid[0] if valid else None)
    layouts = sorted({(str(item.get("layout", "")), str(item.get("variant", "")), str(item.get("options", ""))) for item in valid})
    comma_separated = any(len([part for part in str(item.get("layout", "")).split(",") if part]) > 1 or
                          len(str(item.get("variant", "")).split(",")) > 1 for item in valid)
    multiple_layouts = comma_separated or len(layouts) > 1
    switches = [str(item.get("name", "")) for item in data.get("switches", []) if isinstance(item, dict) and item.get("name")]
    return {"keyboard": keyboard, "layouts": [list(item) for item in layouts], "multipleLayouts": multiple_layouts,
            "switches": switches, "warning": "multiple keyboard layouts are active" if multiple_layouts else ""}
