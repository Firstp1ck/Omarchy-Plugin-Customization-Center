from __future__ import annotations
from typing import Any
from customization_center.core import CcError
from .common import rows_by_id

module_id = "plugins"
order = 30

def validate_section(section: dict[str, Any], status: Any, caps: Any) -> None:
    rows = rows_by_id(status.data.get("rows", []))
    for plugin_id, enabled in section["enabled"].items():
        row = rows.get(plugin_id)
        if row is None: raise CcError("modes_unknown_plugin", f"Plugin {plugin_id} was not discovered")
        if set(row.get("kinds", [])) & {"bar", "bar-widget"}: raise CcError("modes_bar_kind_in_plugins", f"{plugin_id} belongs to the bar editor")
        if not enabled and row.get("state", {}).get("canDisable") is False: raise CcError("modes_section_invalid", f"Plugin {plugin_id} cannot be disabled")

def to_draft(section: dict[str, Any], status: Any) -> dict[str, Any]:
    rows = rows_by_id(status.data.get("rows", [])); changes = []
    for plugin_id, enabled in sorted(section["enabled"].items()):
        if rows.get(plugin_id, {}).get("state", {}).get("enabled") is enabled: continue
        changes.append({"kind": "enable" if enabled else "disable", "pluginId": plugin_id, "closesCenter": False})
    return {"schemaVersion": 1, "module": "plugins", "baseRevision": status.revision, "changes": changes}

def target(section: dict[str, Any], status: Any) -> dict[str, Any]: return dict(sorted(section["enabled"].items()))
def observe_target(expected: dict[str, Any], status: Any) -> dict[str, Any] | None:
    rows = rows_by_id(status.data.get("rows", [])); value = {}
    for plugin_id in expected:
        if plugin_id not in rows: return None
        value[plugin_id] = rows[plugin_id].get("state", {}).get("enabled")
    return value

def capture(status: Any, selection: Any = None) -> dict[str, Any] | None:
    wanted = set(selection or []); rows = rows_by_id(status.data.get("rows", [])); values = {}
    for plugin_id in sorted(wanted):
        row = rows.get(plugin_id)
        if row and not set(row.get("kinds", [])) & {"bar", "bar-widget"}: values[plugin_id] = row.get("state", {}).get("enabled") is True
    return {"enabled": values} if values else None

def summarize(section: dict[str, Any]) -> list[str]: return [f"{plugin_id}: {'enabled' if value else 'disabled'}" for plugin_id, value in sorted(section["enabled"].items())]
def external_references(section: dict[str, Any]) -> list[dict[str, Any]]: return [{"module":"plugins","kind":"plugin","id":item} for item in sorted(section["enabled"])]
