from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CcError


@dataclass(frozen=True)
class CatalogRead:
    rows: tuple[dict[str, Any], ...]
    shell_config: dict[str, Any]
    raw_document: dict[str, Any]
    diagnostics: dict[str, Any]
    revision: str


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read(ctx_like: Any) -> CatalogRead:
    commands = ctx_like.commands
    if hasattr(commands, "allow_readonly"):
        commands.allow_readonly(("omarchy-plugin-catalog",))
    runtime = ctx_like.shell.list_plugins()
    shell_config = ctx_like.shell.list_shell_config()
    catalog_rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {"warnings": [], "undiscovered": []}
    result = commands.run(["omarchy-plugin-catalog"], timeout_s=5)
    if result.timed_out or result.exit_code != 0:
        diagnostics["warnings"].append({"code": "plugins_catalog_unavailable",
                                         "message": result.stderr.strip() or "Plugin catalog unavailable"})
    else:
        try:
            value = json.loads(result.stdout)
            if not isinstance(value, list):
                raise ValueError
            catalog_rows = [item for item in value if isinstance(item, dict)]
        except (json.JSONDecodeError, ValueError):
            diagnostics["warnings"].append({"code": "plugins_catalog_unavailable",
                                             "message": "Plugin catalog returned malformed JSON"})
    static = {str(item.get("id")): item for item in catalog_rows if item.get("id")}
    runtime_ids = {str(item.get("id")) for item in runtime}
    diagnostics["undiscovered"] = [item for key, item in static.items() if key not in runtime_ids]
    omarchy_root = Path(ctx_like.paths.omarchy_path) / "shell/plugins"
    user_root = Path(ctx_like.paths.home) / ".config/omarchy/plugins"
    rows: list[dict[str, Any]] = []
    for runtime_row in runtime:
        row = dict(runtime_row)
        catalog = static.get(str(row.get("id")))
        if catalog:
            try:
                source_declared = Path(catalog["sourceDir"]).absolute()
                source_dir = source_declared.resolve(strict=True)
                permitted = source_dir.is_relative_to(omarchy_root.resolve()) or source_dir.is_relative_to(user_root.resolve())
                if not permitted:
                    raise ValueError("sourceDir is outside plugin roots")
                declared_manifest = Path(catalog["manifestPath"]).absolute()
                if declared_manifest != source_declared / "manifest.json":
                    raise ValueError("manifestPath is not sourceDir/manifest.json")
                manifest_path = declared_manifest.resolve(strict=True)
                if manifest_path.parent != source_dir or manifest_path.name != "manifest.json":
                    raise ValueError("manifestPath escapes sourceDir")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("id") != row.get("id"):
                    raise ValueError("manifest id mismatch")
                row.update({"description": manifest.get("description"), "version": manifest.get("version"),
                            "author": manifest.get("author"), "license": manifest.get("license"),
                            "keepLoaded": manifest.get("keepLoaded") is True,
                            "entryPoints": catalog.get("entryPoints", {}), "barWidget": catalog.get("barWidget"),
                            "bar": catalog.get("bar"), "sourceDir": str(source_dir),
                            "manifestPath": str(manifest_path), "manifest": manifest})
            except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
                warning = {"code": "plugins_manifest_mismatch", "pluginId": row.get("id"),
                           "message": f"Catalog row {row.get('id')} was refused: {error}"}
                diagnostics["warnings"].append(warning)
                row.setdefault("diagnostics", []).append(warning)
        rows.append(row)
    digest = hashlib.sha256((_canonical(runtime) + "\n" + _canonical(shell_config)).encode()).hexdigest()
    raw = {"listPlugins": runtime, "listShellConfig": shell_config, "catalog": catalog_rows}
    return CatalogRead(tuple(rows), shell_config, raw, diagnostics, "sha256:" + digest)
