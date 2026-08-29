from __future__ import annotations
from pathlib import Path
from typing import Any
from customization_center.core import CcError
from .common import file_name

module_id = "themes"
order = 20

def _entry(status: Any, slug: str) -> dict[str, Any] | None:
    return next((item for item in status.data.get("themes", []) if item.get("slug") == slug), None)

def validate_section(section: dict[str, Any], status: Any, caps: Any) -> None:
    entry = _entry(status, section["slug"])
    if entry is None: raise CcError("modes_missing_theme", f"Theme {section['slug']} does not exist")
    if section.get("preferredWallpaper") and not any(Path(path).name == section["preferredWallpaper"] for path in entry.get("wallpaperPaths", [])):
        raise CcError("modes_section_invalid", "Preferred wallpaper is not available in the theme")

def to_draft(section: dict[str, Any], status: Any) -> dict[str, Any]:
    draft = {"schemaVersion": 1, "kind": "activate", "slug": section["slug"]}
    if section.get("preferredWallpaper"):
        entry = _entry(status, section["slug"]) or {}
        draft["preferredWallpaper"] = next(path for path in entry.get("wallpaperPaths", []) if Path(path).name == section["preferredWallpaper"])
    return draft

def target(section: dict[str, Any], status: Any) -> dict[str, Any]:
    value = {"themeName": section["slug"]}
    if section.get("preferredWallpaper"): value["background"] = section["preferredWallpaper"]
    return value

def observe_target(expected: dict[str, Any], status: Any) -> dict[str, Any] | None:
    active = status.data.get("active", {})
    if not isinstance(active, dict): return None
    value = {"themeName": active.get("slug")}
    if "background" in expected: value["background"] = file_name(active.get("background"))
    return value

def capture(status: Any, selection: Any = None) -> dict[str, Any] | None:
    active = status.data.get("active", {}); slug = active.get("slug")
    if not slug: return None
    value = {"slug": slug}
    if isinstance(selection, dict) and selection.get("preferredWallpaper") and active.get("background"):
        value["preferredWallpaper"] = Path(active["background"]).name
    return value

def summarize(section: dict[str, Any]) -> list[str]:
    values = [f"Theme: {section['slug']}"]
    if section.get("preferredWallpaper"): values.append(f"Wallpaper: {section['preferredWallpaper']}")
    return values

def external_references(section: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"module": "themes", "kind": "theme", "id": section["slug"]}]
