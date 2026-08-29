from __future__ import annotations

import copy
from typing import Any

SECTIONS = ("left", "center", "right")
KNOWN_BAR_KEYS = {"id", "position", "transparent", "centerAnchor", "layout"}


def normalize_entry(entry: Any, section: str, index: int, *, draft_key: bool = False) -> dict[str, Any]:
    if isinstance(entry, str):
        widget_id, settings, form = entry, {}, "string"
    elif isinstance(entry, dict):
        widget_id = entry.get("id", "")
        settings = {key: copy.deepcopy(value) for key, value in entry.items() if key != "id"}
        form = "object"
    else:
        widget_id, settings, form = "", {}, "object"
    prefix = "d" if draft_key else "b"
    return {"key": f"{prefix}:{section}:{index}", "origin": {"section": section, "index": index},
            "id": widget_id, "settings": settings, "form": form}


def from_shell(bar: Any, *, draft_keys: bool = False) -> dict[str, Any]:
    source = bar if isinstance(bar, dict) else {}
    raw_layout = source.get("layout") if isinstance(source.get("layout"), dict) else {}
    layout = {section: [normalize_entry(item, section, index, draft_key=draft_keys)
                        for index, item in enumerate(raw_layout.get(section, []) if isinstance(raw_layout.get(section), list) else [])]
              for section in SECTIONS}
    return {"id": source.get("id") if isinstance(source.get("id"), str) else None,
            "position": source.get("position", "top"),
            "transparent": source.get("transparent") is True,
            "centerAnchor": source.get("centerAnchor", ""),
            "extra": {key: copy.deepcopy(value) for key, value in source.items() if key not in KNOWN_BAR_KEYS},
            "layout": layout}


def serialize_entry(entry: dict[str, Any]) -> Any:
    settings = copy.deepcopy(entry.get("settings", {})) if isinstance(entry.get("settings"), dict) else {}
    if entry.get("form") == "string" and not settings:
        return entry.get("id", "")
    return {"id": entry.get("id", ""), **settings}


def to_shell(bar: dict[str, Any], *, omit_empty_anchor: bool = False, base_had_anchor: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if bar.get("id") is not None:
        result["id"] = bar["id"]
    result["position"] = bar.get("position", "top")
    result["transparent"] = bar.get("transparent") is True
    anchor = bar.get("centerAnchor", "")
    if not omit_empty_anchor or anchor or base_had_anchor:
        result["centerAnchor"] = anchor
    result.update(copy.deepcopy(bar.get("extra", {})))
    layout = bar.get("layout", {})
    result["layout"] = {section: [serialize_entry(item) for item in layout.get(section, [])] for section in SECTIONS}
    return result


def all_entries(bar: dict[str, Any]):
    for section in SECTIONS:
        for index, entry in enumerate(bar.get("layout", {}).get(section, [])):
            yield section, index, entry


def rebase(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(candidate)
    base_entries = list(all_entries(base))
    used: set[tuple[str, int]] = set()
    serial = 0
    for section in SECTIONS:
        values = result.setdefault("layout", {}).setdefault(section, [])
        for index, entry in enumerate(values):
            serial += 1
            if not isinstance(entry, dict):
                entry = normalize_entry(entry, section, index, draft_key=True)
                values[index] = entry
            origin = entry.get("origin")
            valid = isinstance(origin, dict) and (origin.get("section"), origin.get("index")) not in used
            if valid:
                found = next((item for item in base_entries if item[0] == origin.get("section") and item[1] == origin.get("index") and item[2].get("id") == entry.get("id")), None)
                valid = found is not None
            if not valid:
                match = next((item for item in base_entries if (item[0], item[1]) not in used and item[0] == section and item[1] == index and item[2].get("id") == entry.get("id")), None)
                if match is None:
                    match = next((item for item in base_entries if (item[0], item[1]) not in used and item[2].get("id") == entry.get("id")), None)
                entry["origin"] = {"section": match[0], "index": match[1]} if match else None
            if entry.get("origin") is not None:
                used.add((entry["origin"]["section"], entry["origin"]["index"]))
            entry["key"] = str(entry.get("key") or f"d:{serial:08x}")
            entry.setdefault("settings", {})
            entry.setdefault("form", "object")
    return result


def counts(bar: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for _, _, entry in all_entries(bar):
        widget_id = str(entry.get("id", ""))
        result[widget_id] = result.get(widget_id, 0) + 1
    return result
