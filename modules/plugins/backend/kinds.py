from __future__ import annotations

from typing import Any


def ownership(kinds: list[str] | tuple[str, ...]) -> str:
    return "bar" if "bar" in kinds or "bar-widget" in kinds else "plugins"


def bar_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    kinds = row.get("kinds", [])
    if "bar" in kinds:
        return {"selectBar": row.get("id")}
    if "bar-widget" not in kinds:
        return None
    instances = row.get("instances", [])
    if instances:
        first = instances[0]
        return {"select": {"section": first["section"], "index": first["index"]}}
    return {"addWidget": row.get("id")}


def storage(row: dict[str, Any], shell_config: dict[str, Any]) -> str:
    kinds = row.get("kinds", [])
    plugin_id = row.get("id")
    if "bar" in kinds:
        return "bar.id"
    if "bar-widget" in kinds:
        return "bar.layout"
    disabled = shell_config.get("disabledPlugins", [])
    plugins = shell_config.get("plugins", [])
    if plugin_id in disabled:
        return "disabledPlugins[]"
    if any((item == plugin_id) or (isinstance(item, dict) and item.get("id") == plugin_id) for item in plugins):
        return "plugins[]"
    return "implicit"


def expected_storage(row: dict[str, Any], enabled: bool) -> tuple[str, bool]:
    if row.get("firstParty"):
        return ("implicit", False) if enabled else ("disabledPlugins[]", True)
    return ("plugins[]", enabled)
