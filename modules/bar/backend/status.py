from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from customization_center.core import CcError, Warning, catalog, settings_schema
from .model import SECTIONS, from_shell, to_shell


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_file(path: Path) -> tuple[bytes | None, dict[str, Any] | None, str]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None, ""
    except OSError as error:
        return None, None, str(error)
    try:
        value = json.loads(raw)
        return raw, value if isinstance(value, dict) else None, "" if isinstance(value, dict) else "root is not an object"
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return raw, None, str(error)


def enrich_catalog(rows: list[dict[str, Any]], bar: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for source in rows:
        if "bar-widget" not in source.get("kinds", []):
            continue
        metadata = source.get("barWidget") if isinstance(source.get("barWidget"), dict) else {}
        normalized = settings_schema.normalize(metadata)
        item = {"id": str(source.get("id", "")), "name": source.get("name") or source.get("id"),
                "displayName": metadata.get("displayName") or source.get("name") or source.get("id"),
                "description": metadata.get("description") or source.get("description") or "",
                "category": metadata.get("category") or "Plugin", "kinds": source.get("kinds", []),
                "firstParty": source.get("firstParty") is True, "clonedFrom": source.get("clonedFrom") or "",
                "activeCloneId": "", "enabled": source.get("enabled") is True,
                "allowMultiple": metadata.get("allowMultiple") is True,
                "defaultSection": metadata.get("defaultSection") if metadata.get("defaultSection") in SECTIONS else "center",
                "defaults": metadata.get("defaults") if isinstance(metadata.get("defaults"), dict) else {},
                "settingsForm": metadata.get("settingsForm") if isinstance(metadata.get("settingsForm"), str) else "",
                "schema": {**normalized, "ok": normalized.get("support") != "invalid"},
                "sizeClass": size_class(str(source.get("id", ""))), "presence": "shell"}
        by_id[item["id"]] = item
        result.append(item)
    for item in result:
        clone = next((row for row in result if row.get("clonedFrom") == item["id"] and row.get("enabled")), None)
        item["activeCloneId"] = clone["id"] if clone else ""
    for section in SECTIONS:
        for entry in bar["layout"][section]:
            widget_id = str(entry.get("id", ""))
            if widget_id in by_id:
                continue
            settings = entry.get("settings", {})
            custom = any(key in settings for key in ("type", "exec", "source"))
            item = {"id": widget_id, "name": widget_id, "displayName": widget_id, "description": "",
                    "category": "Custom" if custom else "Unavailable", "kinds": [], "firstParty": False,
                    "clonedFrom": "", "activeCloneId": "", "enabled": True, "allowMultiple": False,
                    "defaultSection": "center", "defaults": {}, "settingsForm": "",
                    "schema": {**settings_schema.normalize({}), "ok": False}, "sizeClass": size_class(widget_id),
                    "presence": "layout-only"}
            by_id[widget_id] = item
            result.append(item)
    return sorted(result, key=lambda item: (str(item["category"]), str(item["displayName"]), item["id"]))


def size_class(widget_id: str) -> str:
    if widget_id == "omarchy.spacer":
        return "spacer"
    if widget_id in {"omarchy.clock", "omarchy.workspaces", "omarchy.active-window", "omarchy.media", "omarchy.keyboard-layout"}:
        return "text"
    if widget_id in {"omarchy.indicators", "omarchy.tray"}:
        return "variable"
    return "icon"


def defaults_bar(ctx: Any) -> dict[str, Any]:
    _, document, _ = read_file(ctx.paths.omarchy_path / "config/omarchy/shell.json")
    result = from_shell((document or {}).get("bar", {}))
    result["id"] = None
    for service in ("dropbox", "tailscale"):
        command = f"omarchy-installed-service-{service}"
        if ctx.commands.which(command) is None:
            continue
        ctx.commands.allow_readonly((command,))
        probe = ctx.commands.run([command], timeout_s=5)
        if probe.exit_code == 0:
            right = result["layout"]["right"]
            tray = next((index for index, item in enumerate(right) if item.get("id") == "omarchy.tray"), len(right) - 1)
            right.insert(max(0, tray + 1), {"key": f"default:{service}", "origin": None,
                                          "id": f"omarchy.{service}", "settings": {}, "form": "object"})
    return result


def build(ctx: Any):
    file_path = ctx.paths.home / ".config/omarchy/shell.json"
    raw, file_document, parse_error = read_file(file_path)
    file_hash = hashlib.sha256(raw).hexdigest() if raw is not None else None
    warnings: list[Warning] = []
    shell_available = True
    reason = ""
    rows: list[dict[str, Any]] = []
    shell_config: dict[str, Any]
    try:
        joined = catalog.read(ctx)
        rows = [dict(item) for item in joined.rows]
        shell_config = joined.shell_config
        for warning in joined.diagnostics.get("warnings", []):
            warnings.append(Warning("bar_catalog_unavailable", warning.get("message", "Plugin catalog unavailable"), "", "Retry after the plugin scan finishes"))
    except CcError as error:
        if error.code not in {"runtime_unavailable", "timeout"}:
            raise
        shell_available = False
        reason = error.message
        shell_config = file_document or {}
    source_kind = "user" if file_document is not None and file_document.get("version") == 1 else "defaults"
    if not shell_available and file_document is None:
        _, shipped, _ = read_file(ctx.paths.omarchy_path / "config/omarchy/shell.json")
        shell_config = shipped or {}
        source_kind = "defaults"
    bar = from_shell(shell_config.get("bar", {}))
    plugins = joined.raw_document.get("listPlugins", []) if shell_available else []
    configured = bar.get("id") or "omarchy.bar"
    active = next((str(row.get("id")) for row in plugins if row.get("active") is True and "bar" in row.get("kinds", [])), "omarchy.bar")
    scanning = shell_available and not plugins and any(bar["layout"][section] for section in SECTIONS)
    version1 = file_document is not None and file_document.get("version") == 1
    file_bar = file_document.get("bar", {}) if file_document else None
    matches = shell_available and file_bar is not None and canonical(file_bar) == canonical(shell_config.get("bar", {}))
    revision_payload = {"config": shell_config, "fileSha256": file_hash,
                        "plugins": sorted(({key: row.get(key) for key in ("id", "kinds", "firstParty", "clonedFrom")} for row in plugins), key=lambda row: str(row.get("id")))}
    revision = ("sha256:" + hashlib.sha256(canonical(revision_payload).encode()).hexdigest()) if shell_available else "unavailable:" + (file_hash or "absent")
    widget_catalog = enrich_catalog(rows, bar)
    bar_options = [{"id": "omarchy.bar", "name": "Built-in bar", "firstParty": True, "available": True}]
    for row in rows:
        if "bar" in row.get("kinds", []) and row.get("id") != "omarchy.bar":
            bar_options.append({"id": row.get("id"), "name": row.get("name") or row.get("id"),
                                "firstParty": row.get("firstParty") is True,
                                "available": bool(row.get("entryPoints", {}).get("bar") or row.get("bar"))})
    apply_file = shell_available and not scanning and (raw is None or version1) and not parse_error and ctx.paths.symlink_safe(file_path)
    if shell_available and raw is not None and (parse_error or not version1):
        warnings.append(Warning("bar_file_desync", "shell.json is malformed or does not have version 1", str(file_path), "Repair the file before applying"))
    data = {"schemaVersion": 1, "module": "bar", "revision": revision,
            "shell": {"available": shell_available, "reason": reason, "configuredBarId": configured,
                      "configuredBarExplicit": bar.get("id") is not None, "activeBarId": active,
                      "fallback": configured != active, "scanning": scanning},
            "source": {"kind": source_kind, "path": str(file_path if source_kind == "user" else ctx.paths.omarchy_path / "config/omarchy/shell.json")},
            "file": {"exists": raw is not None, "parses": file_document is not None and not parse_error,
                     "version1": version1, "matchesShell": matches, "sha256": file_hash, "error": parse_error},
            "bar": bar, "defaults": defaults_bar(ctx), "catalog": widget_catalog, "barOptions": bar_options,
            "capabilities": {"applyIpc": {"available": shell_available and not scanning, "reason": reason or ("Plugin scan in progress" if scanning else "")},
                             "applyFile": {"available": apply_file, "reason": "" if apply_file else reason or parse_error or "shell.json must be version 1"},
                             "selectBar": {"available": len(bar_options) > 1, "reason": "" if len(bar_options) > 1 else "Only the built-in bar is installed"},
                             "debugGeometry": {"available": active == "omarchy.bar", "reason": "" if active == "omarchy.bar" else "Only the built-in bar exposes geometry"}},
            "rawShellConfig": shell_config}
    return revision, data, tuple(warnings)
