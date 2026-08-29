from __future__ import annotations
import copy
from typing import Any
from customization_center.core import CcError

module_id = "bar"
order = 40
SECTIONS = ("left", "center", "right")

def validate_section(section: dict[str, Any], status: Any, caps: Any) -> None:
    if not status.data.get("shell", {}).get("available"):
        raise CcError("modes_member_unavailable", "The shell is unavailable for the bar member")

def _entry(value: Any, current: list[dict[str, Any]], section: str, index: int) -> dict[str, Any]:
    widget_id = value.get("id", "")
    base = current[index] if index < len(current) and current[index].get("id") == widget_id else None
    return {"key": f"m:{section}:{index}", "origin": copy.deepcopy(base.get("origin")) if base else None,
            "id": widget_id, "settings": {key: copy.deepcopy(item) for key, item in value.items() if key != "id"}, "form": "object"}

def to_draft(section: dict[str, Any], status: Any) -> dict[str, Any]:
    value = copy.deepcopy(status.data.get("bar", {}))
    for key in ("position", "transparent", "centerAnchor"):
        if key in section: value[key] = section[key]
    if "id" in section: value["id"] = None if section["id"] == "omarchy.bar" else section["id"]
    if "layout" in section:
        value["layout"] = {name: [_entry(item, status.data.get("bar", {}).get("layout", {}).get(name, []), name, index)
                                  for index, item in enumerate(section["layout"][name])] for name in SECTIONS}
    return {"schemaVersion":1,"module":"bar","baseRevision":status.revision,"action":"apply","presetId":None,"presetName":None,"bar":value}

def _serialized(status: Any) -> dict[str, Any]:
    bar = status.data.get("bar", {}); result = {"id": bar.get("id") or "omarchy.bar", "position":bar.get("position"),"transparent":bar.get("transparent"),"centerAnchor":bar.get("centerAnchor","")}
    result["layout"] = {name:[{"id":item.get("id"), **copy.deepcopy(item.get("settings", {}))} for item in bar.get("layout", {}).get(name, [])] for name in SECTIONS}
    return result

def target(section: dict[str, Any], status: Any) -> dict[str, Any]: return copy.deepcopy(section)
def observe_target(expected: dict[str, Any], status: Any) -> dict[str, Any] | None:
    if not status.data.get("shell", {}).get("available"): return None
    current = _serialized(status); return {key: current.get(key) for key in expected}
def capture(status: Any, selection: Any = None) -> dict[str, Any] | None:
    if not status.data.get("shell", {}).get("available"): return None
    current = _serialized(status); fields = selection or ["id","position","transparent","centerAnchor","layout"]
    return {key: current[key] for key in fields if key in current}
def summarize(section: dict[str, Any]) -> list[str]: return [f"Bar {key}: {value if key != 'layout' else 'complete layout'}" for key, value in section.items()]
def external_references(section: dict[str, Any]) -> list[dict[str, Any]]: return []
