from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from customization_center.core import settings_schema
from .kinds import bar_payload, ownership, storage

_SECRET_REMOTE = re.compile(r"(?:token|ghp_|glpat|x-access-token)", re.IGNORECASE)


def sanitize_remote(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "://" in value:
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            if parsed.port:
                host += f":{parsed.port}"
            value = urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))
        except ValueError:
            return "<redacted>"
    elif "@" in value and ":" in value:
        value = value.split("@", 1)[1]
    return "<redacted>" if _SECRET_REMOTE.search(value) else value


def _instances(plugin_id: str, shell_config: dict[str, Any]) -> list[dict[str, Any]]:
    layout = shell_config.get("bar", {}).get("layout", {}) if isinstance(shell_config.get("bar"), dict) else {}
    result: list[dict[str, Any]] = []
    for section in ("left", "center", "right"):
        values = layout.get(section, []) if isinstance(layout, dict) else []
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if isinstance(value, str):
                entry, legacy = {"id": value}, True
            elif isinstance(value, dict):
                entry, legacy = dict(value), False
            else:
                continue
            if entry.get("id") == plugin_id:
                result.append({"section": section, "index": index, "entry": entry, "legacyString": legacy})
    return result


def _checkout(ctx: Any, plugin_id: str, first_party: bool) -> dict[str, Any]:
    if first_party:
        return {"class": "omarchy-shipped", "checkout": "bundled", "symlinkTarget": None, "remote": None}
    path = ctx.paths.home / ".config/omarchy/plugins" / plugin_id
    origin: dict[str, Any] = {"class": "user-installed", "checkout": "unknown", "symlinkTarget": None, "remote": None}
    try:
        if path.is_symlink():
            origin["checkout"] = "symlink"
            origin["symlinkTarget"] = str(path.readlink())
        elif path.is_dir() and (path / ".git").is_dir():
            origin["checkout"] = "git"
            ctx.commands.allow_readonly(("git", "-C", str(path), "config", "--get", "remote.origin.url"))
            remote = ctx.commands.run(["git", "-C", str(path), "config", "--get", "remote.origin.url"], timeout_s=2, capture_limit=4096)
            if remote.exit_code == 0 and not remote.timed_out:
                origin["remote"] = sanitize_remote(remote.stdout)
        elif path.is_dir():
            origin["checkout"] = "directory"
    except OSError:
        origin["checkout"] = "unknown"
    return origin


def _widget_metadata(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("displayName", "description", "category", "settingsForm"):
        result[key] = value.get(key) if isinstance(value.get(key), str) else None
    result["allowMultiple"] = value.get("allowMultiple") is True
    result["defaultSection"] = value.get("defaultSection") if value.get("defaultSection") in {"left", "center", "right"} else None
    result["defaults"] = value.get("defaults") if isinstance(value.get("defaults"), dict) else {}
    return result


def enrich(ctx: Any, joined: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    shell_config = joined.shell_config
    runtime = [dict(item) for item in joined.rows]
    configured = shell_config.get("bar", {}).get("id", "omarchy.bar") if isinstance(shell_config.get("bar"), dict) else "omarchy.bar"
    configured = configured or "omarchy.bar"
    running = next((str(item.get("id")) for item in runtime if item.get("active") is True and "bar" in item.get("kinds", [])), "omarchy.bar")
    disabled = shell_config.get("disabledPlugins", []) if isinstance(shell_config.get("disabledPlugins"), list) else []
    clone_by_source = {str(item.get("clonedFrom")): str(item.get("id")) for item in runtime if item.get("clonedFrom") and item.get("enabled")}
    rows: list[dict[str, Any]] = []
    for raw in runtime:
        plugin_id = str(raw.get("id", ""))
        kinds = [str(item) for item in raw.get("kinds", []) if isinstance(item, str)]
        manifest = raw.get("manifest") if isinstance(raw.get("manifest"), dict) else {}
        first_party = raw.get("firstParty") is True
        clone_source = str(raw.get("clonedFrom") or "") or None
        origin = _checkout(ctx, plugin_id, first_party)
        if clone_source:
            origin["class"] = "user-clone"
        origin["sourceDir"] = raw.get("sourceDir") if isinstance(raw.get("sourceDir"), str) else None
        origin["manifestPath"] = raw.get("manifestPath") if isinstance(raw.get("manifestPath"), str) else None
        instances = _instances(plugin_id, shell_config)
        normalized = settings_schema.normalize(manifest if manifest else (raw.get("barWidget") or {}))
        diagnostics = [dict(item) for item in raw.get("diagnostics", []) if isinstance(item, dict)]
        diagnostics.extend(dict(item) for item in normalized.get("problems", []))
        if "bar" in kinds and "bar-widget" in kinds:
            diagnostics.append({"code": "plugins_bar_and_widget", "severity": "info", "message": "This manifest declares both bar and bar-widget; it is treated as a full bar.", "path": origin["manifestPath"] or ""})
        if any(item.get("legacyString") for item in instances):
            diagnostics.append({"code": "plugins_legacy_string_entry", "severity": "info", "message": "This bar entry is stored as a plain string.", "path": "/bar/layout"})
        if origin["checkout"] == "symlink":
            diagnostics.append({"code": "plugins_symlink_checkout", "severity": "info", "message": "Update is unavailable for linked plugins.", "path": str(ctx.paths.home / ".config/omarchy/plugins" / plugin_id)})
        if configured == plugin_id and configured != running and "bar" in kinds:
            diagnostics.append({"code": "plugins_bar_fallback", "severity": "error", "message": f"Configured bar {configured} is not running; the shell fell back to {running}.", "path": "/bar/id"})
        row: dict[str, Any] = {
            "id": plugin_id, "name": raw.get("name") or plugin_id, "description": raw.get("description"),
            "version": raw.get("version"), "author": raw.get("author"), "license": raw.get("license"),
            "kinds": kinds, "keepLoaded": raw.get("keepLoaded") is True,
            "entryPoints": raw.get("entryPoints") if isinstance(raw.get("entryPoints"), dict) else {},
            "firstParty": first_party, "clonedFrom": clone_source,
            "self": plugin_id == "firstpick.customization-center", "ownership": ownership(kinds),
            "origin": origin, "instances": instances, "barWidget": _widget_metadata(raw.get("barWidget")),
            "settings": normalized, "diagnostics": diagnostics,
        }
        row["state"] = {
            "enabled": raw.get("enabled") is True, "active": raw.get("active") is True,
            "canDisable": raw.get("canDisable") is True, "storage": storage(row, shell_config),
            "configuredBar": configured, "runningBar": running, "barFallback": configured != running,
            "disabledByList": plugin_id in disabled, "activeCloneId": clone_by_source.get(plugin_id),
        }
        capabilities: list[Any] = []
        if row["ownership"] == "bar":
            capabilities.append({"name": "edit-in-bar-editor", "navigate": bar_payload(row)})
        elif row["self"]:
            if row["state"]["enabled"] and row["state"]["canDisable"]:
                capabilities.append({"name": "disable", "closesCenter": True})
        elif row["state"]["enabled"]:
            if row["state"]["canDisable"]:
                capabilities.append("disable")
        else:
            capabilities.append("enable")
        if origin["checkout"] == "git":
            capabilities.append("update")
        if not first_party:
            capabilities.append({"name": "remove", "closesCenter": row["self"]}) if row["self"] else capabilities.append("remove")
        if first_party and plugin_id not in clone_by_source:
            capabilities.append("clone")
            if ctx.commands.environ.get("EDITOR"):
                capabilities.append("clone-edit")
        if not first_party and origin["checkout"] != "symlink":
            capabilities.append("validate")
        if origin["sourceDir"]:
            capabilities.append("open-source")
        if diagnostics:
            capabilities.append("view-diagnostics")
        row["capabilities"] = capabilities
        rows.append(row)
    shell = {"available": True, "configuredBar": configured, "runningBar": running,
             "barFallback": configured != running,
             "pluginsDir": str(ctx.paths.home / ".config/omarchy/plugins")}
    return rows, shell


def static_diagnostics(ctx: Any) -> dict[str, Any]:
    ctx.commands.allow_readonly(("omarchy-plugin-catalog",))
    result = ctx.commands.run(["omarchy-plugin-catalog"], timeout_s=5, capture_limit=1024 * 1024)
    if result.exit_code != 0 or result.timed_out:
        return {"warnings": [{"code": "plugins_catalog_unavailable", "message": result.stderr.strip() or "Plugin catalog unavailable"}], "undiscovered": []}
    try:
        value = json.loads(result.stdout)
        if not isinstance(value, list):
            raise ValueError
        return {"warnings": [], "undiscovered": [item for item in value if isinstance(item, dict)]}
    except (json.JSONDecodeError, ValueError):
        return {"warnings": [{"code": "plugins_catalog_unavailable", "message": "Plugin catalog returned malformed JSON"}], "undiscovered": []}
