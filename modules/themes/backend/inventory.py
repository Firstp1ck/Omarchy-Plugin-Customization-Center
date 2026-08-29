from __future__ import annotations

import hashlib
import json
import stat
from typing import Any

from .writer import parse_shell

_ALLOWED = {"colors.toml", "icons.theme", "preview.png"}
_ALLOWED_SECTIONS = {f"shell.{name}.toml" for name in (
    "bar controls spacing font popups tooltip notifications launcher menu polkit lock image-picker").split()}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def _sha(path: Any) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, OSError):
        return None


def _files(path: Any) -> list[Any]:
    try:
        return sorted((item for item in path.rglob("*") if item.is_file() and not item.is_symlink()), key=lambda item: str(item.relative_to(path)))
    except OSError:
        return []


def classify(path: Any, sidecar: dict[str, Any] | None) -> tuple[str, list[str]]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "absent", []
    if stat.S_ISLNK(mode):
        return "symlink", []
    if not stat.S_ISDIR(mode):
        return "unsupported", []
    if (path / ".git").exists():
        return "git", []
    actual = {str(item.relative_to(path)): _sha(item) for item in _files(path)}
    unsupported = sorted(relpath for relpath in actual if not (
        relpath in _ALLOWED or relpath in _ALLOWED_SECTIONS or
        relpath.startswith("backgrounds/") and path.joinpath(relpath).suffix.lower() in _IMAGE_EXTENSIONS))
    expected = sidecar.get("files") if isinstance(sidecar, dict) else None
    if isinstance(expected, dict):
        return ("managed" if actual == expected else "managed-modified"), unsupported
    return "plain", unsupported


def theme_entry(path: Any, source: str, sidecar: dict[str, Any] | None = None) -> dict[str, Any]:
    files = _files(path)
    backgrounds = [item for item in files if item.parent.name == "backgrounds" and item.suffix.lower() in _IMAGE_EXTENSIONS]
    previews = [item for item in files if item.name.startswith("preview.") or item in backgrounds]
    entry = {"slug": path.name, "source": source, "path": str(path), "hasPreviewImage": bool(previews),
             "wallpapers": len(backgrounds), "unsupportedFiles": []}
    if source == "user":
        classification, unsupported = classify(path, sidecar)
        entry.update({"classification": classification, "unsupportedFiles": unsupported,
                      "sidecar": {key: sidecar.get(key) for key in ("transactionId", "savedAt")} if sidecar else None})
    return entry


def read_status(ctx: Any) -> dict[str, Any]:
    home = ctx.paths.home
    builtins = ctx.paths.omarchy_path / "themes"
    users = home / ".config/omarchy/themes"
    sidecars = ctx.paths.module_state("themes")
    entries: dict[str, dict[str, Any]] = {}
    try:
        builtin_dirs = [item for item in builtins.iterdir() if item.is_dir()]
    except OSError:
        builtin_dirs = []
    builtin_names = sorted(path.name for path in builtin_dirs)
    for path in sorted(builtin_dirs):
        entries[path.name] = theme_entry(path, "builtin")
    try:
        user_items = list(users.iterdir())
    except OSError:
        user_items = []
    for path in sorted(user_items):
        sidecar = ctx.paths.read_json(sidecars / f"{path.name}.json", default=None)
        entries[path.name] = theme_entry(path, "user", sidecar)
    current = home / ".local/state/omarchy/current"
    try:
        slug = (current / "theme.name").read_text(encoding="utf-8").strip() or None
    except (FileNotFoundError, OSError):
        slug = None
    colors = current / "theme/colors.toml"; shell = current / "theme/shell.toml"
    background = ctx.paths.readlink(current / "background", None)
    override_path = home / ".config/omarchy/shell.toml"
    try:
        override_text = override_path.read_text(encoding="utf-8")
        override_values = {f"{section}.{key}": value for section, values in parse_shell(override_text).items() for key, value in values.items()}
        override_present = True
    except (FileNotFoundError, OSError):
        override_values = {}; override_present = False
    templates_dir = home / ".config/omarchy/themed"
    try:
        templates = sorted(item.name for item in templates_dir.glob("*.tpl") if item.is_file())
    except OSError:
        templates = []
    revision_items: list[Any] = [slug, _sha(colors), _sha(shell), background, _sha(override_path), _sha(ctx.paths.omarchy_path / "default/themed/shell.toml.tpl")]
    revision_items.extend((item["slug"], item.get("classification"), item.get("wallpapers"), item.get("unsupportedFiles")) for item in entries.values())
    for path in sorted(user_items):
        try:
            revision_items.extend((path.name, str(item.relative_to(path)), item.lstat().st_size, item.lstat().st_mtime_ns) for item in path.rglob("*"))
        except OSError:
            pass
    return {"schemaVersion": 1, "active": {"slug": slug, "source": entries.get(slug or "", {}).get("source"),
            "background": background, "hasColors": colors.is_file(), "hasShell": shell.is_file()},
            "themes": sorted(entries.values(), key=lambda item: (item["slug"] != (slug or ""), item["slug"])),
            "builtInSlugs": builtin_names,
            "machineOverride": {"present": override_present, "path": str(override_path), "values": override_values},
            "userTemplates": templates, "wallpaperSources": [], "iconThemes": [], "openPreviewTransaction": None,
            "revisionData": revision_items}
