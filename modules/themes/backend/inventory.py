from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from .writer import parse_shell

_ALLOWED = {"colors.toml", "icons.theme", "preview.png"}
_ALLOWED_SECTIONS = {f"shell.{name}.toml" for name in (
    "bar controls spacing font popups tooltip notifications launcher menu polkit lock image-picker").split()}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_EXECUTABLE_CONFIG = {"hyprland.lua", "neovim.lua", "gum_env.lua", "vscode.json", "btop.theme",
                      "chromium.theme", "keyboard.rgb", "alacritty.toml", "foot.ini", "ghostty.conf", "kitty.conf"}


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, IsADirectoryError, OSError):
        return None


def _files(path: Path) -> list[Path]:
    try:
        return sorted((item for item in path.rglob("*") if item.is_file() and not item.is_symlink()),
                      key=lambda item: str(item.relative_to(path)))
    except OSError:
        return []


def classify(path: Path, sidecar: dict[str, Any] | None) -> tuple[str, list[str]]:
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


def theme_entry(path: Path, source: str, sidecar: dict[str, Any] | None = None) -> dict[str, Any]:
    classification, unsupported = (classify(path, sidecar) if source == "user" else ("builtin", []))
    files = [] if classification == "symlink" else _files(path)
    backgrounds = [item for item in files if item.parent.name == "backgrounds" and item.suffix.lower() in _IMAGE_EXTENSIONS]
    previews = [item for item in files if item.name.startswith("preview.") or item in backgrounds]
    entry = {"slug": path.name, "source": source, "path": str(path), "classification": classification,
             "hasPreviewImage": bool(previews), "wallpapers": len(backgrounds),
             "wallpaperPaths": [str(item.absolute()) for item in backgrounds], "unsupportedFiles": unsupported,
             "hasExecutableConfig": any(Path(name).name in _EXECUTABLE_CONFIG or
                                        (path / name).is_file() and bool((path / name).stat().st_mode & 0o111)
                                        for name in unsupported)}
    if source == "user":
        entry["sidecar"] = ({key: sidecar.get(key) for key in ("transactionId", "savedAt")} if sidecar else None)
    return entry


def _open_preview(ctx: Any) -> dict[str, Any] | None:
    history = ctx.journal.history(module="themes", limit=200)
    undone = {tx.plan.summary.removeprefix("Undo: ") for tx in history
              if tx.state == "committed" and tx.plan.summary.startswith("Undo: Try theme ")}
    for tx in history:
        if tx.state != "committed" or not tx.plan.summary.startswith("Try theme ") or tx.plan.summary in undone:
            continue
        operation = next((item for item in tx.plan.operations if item.kind == "ShellIpc" and
                          item.params.get("method") == "applyTheme"), None)
        if operation:
            return {"transactionId": tx.id, "createdAt": tx.created_at,
                    "slug": (operation.detail or {}).get("slug"), "state": tx.state}
    return None


def _absolute_link(path: Path) -> str | None:
    try:
        target = Path(os.readlink(path))
    except OSError:
        return None
    return str(target if target.is_absolute() else (path.parent / target).absolute())


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
        user_items = [item for item in users.iterdir() if not item.name.startswith(".")]
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
    colors = current / "theme/colors.toml"
    shell = current / "theme/shell.toml"
    background = _absolute_link(current / "background")
    override_path = home / ".config/omarchy/shell.toml"
    try:
        override_text = override_path.read_text(encoding="utf-8")
        override_values = {f"{section}.{key}": value for section, values in parse_shell(override_text).items()
                           for key, value in values.items()}
        override_present = True
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        override_values = {}; override_present = False
    templates_dir = home / ".config/omarchy/themed"
    try:
        template_paths = sorted(item for item in templates_dir.glob("*.tpl") if item.is_file())
    except OSError:
        template_paths = []

    wallpaper_sources = []
    for label, directory in (("Pictures", home / "Pictures"), ("Wallpapers", home / "Pictures/Wallpapers")):
        try:
            files = sorted(str(item.absolute()) for item in directory.iterdir()
                           if item.is_file() and not item.is_symlink() and item.suffix.lower() in _IMAGE_EXTENSIONS)
        except OSError:
            files = []
        if directory.is_dir():
            wallpaper_sources.append({"label": label, "path": str(directory), "files": files})
    icon_names: set[str] = set()
    for directory in (Path("/usr/share/icons"), home / ".local/share/icons", home / ".icons"):
        try:
            icon_names.update(item.name for item in directory.iterdir() if item.is_dir())
        except OSError:
            pass

    revision_items: list[Any] = [slug, _sha(colors), _sha(shell), background, _sha(override_path),
                                      _sha(ctx.paths.omarchy_path / "default/themed/shell.toml.tpl")]
    revision_items.extend((str(path), _sha(path)) for path in template_paths)
    for path in sorted(user_items):
        revision_items.append((path.name, "sidecar", _sha(sidecars / f"{path.name}.json")))
        try:
            for item in sorted(path.rglob("*")):
                info = item.lstat()
                revision_items.append((path.name, str(item.relative_to(path)), stat.S_IFMT(info.st_mode),
                                       info.st_size, info.st_mtime_ns))
        except OSError:
            revision_items.append((path.name, "unreadable"))
    return {"schemaVersion": 1, "active": {"slug": slug, "source": entries.get(slug or "", {}).get("source"),
            "background": background, "hasColors": colors.is_file(), "hasShell": shell.is_file()},
            "themes": sorted(entries.values(), key=lambda item: (item["slug"] != (slug or ""), item["slug"])),
            "builtInSlugs": builtin_names,
            "machineOverride": {"present": override_present, "path": str(override_path), "values": override_values},
            "userTemplates": [item.name for item in template_paths], "wallpaperSources": wallpaper_sources,
            "iconThemes": sorted(icon_names), "openPreviewTransaction": _open_preview(ctx),
            "revisionData": revision_items}
