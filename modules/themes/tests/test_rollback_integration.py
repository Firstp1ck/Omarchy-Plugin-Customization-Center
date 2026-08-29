from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from customization_center.core import CcError
from customization_center.core.context import build_context
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())
WALLPAPER = Path(__file__).parent / "fixtures/wallpapers/ok.png"


def _setup_theme(paths: Paths, isolated_home: Path):
    registry = load_registry(ROOT, paths=paths); module = registry.module("themes")
    package = sys.modules[module.__class__.__module__]
    ctx = build_context("themes", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT)
    old = json.loads(json.dumps(SAMPLE)); old["palette"]["accent"] = "#112233"
    target = isolated_home / ".config/omarchy/themes/ocean-focus"
    target.mkdir(parents=True)
    for name, content in module._generated(ctx, old).items():
        path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    (target / "backgrounds").mkdir(); (target / "backgrounds/old.png").write_bytes(WALLPAPER.read_bytes())
    current = isolated_home / ".local/state/omarchy/current"
    shutil.copytree(target, current / "theme")
    (current / "theme/shell.toml").write_text(module._rendered_shell(ctx, old))
    (current / "theme.name").write_text("ocean-focus\n")
    (current / "background").symlink_to(current / "theme/backgrounds/old.png")
    return registry, module, package, target, current


def _handlers(stub_command, module, package, paths, current, accents, events, fail_first=False):
    calls = {"theme": 0}

    def switch(slug):
        calls["theme"] += 1
        source = paths.home / ".config/omarchy/themes" / slug
        palette = package._parse_colors(source / "colors.toml")
        accents.append(palette["accent"])
        shutil.rmtree(current / "theme", ignore_errors=True); shutil.copytree(source, current / "theme")
        shell = module._rendered_shell(build_context("themes", "plan", paths=paths, registry=None, plugin_dir=ROOT), {"palette": palette, "sections": {}})
        if fail_first and calls["theme"] == 1:
            shell += "\n[unexpected]\nvalue = 1\n"
        (current / "theme/shell.toml").write_text(shell)
        (current / "theme.name").write_text(slug + "\n")
        backgrounds = sorted((current / "theme/backgrounds").glob("*")) if (current / "theme/backgrounds").is_dir() else []
        if backgrounds:
            (current / "background").unlink(missing_ok=True); (current / "background").symlink_to(backgrounds[0])
        events.append("theme:" + slug)
        return {"exit_code": 0}

    def env_handler(request):
        argv = request["argv"]
        assert argv[1] == "OMARCHY_THEME_SKIP_BACKGROUND=1" and argv[2] == "omarchy-theme-set"
        return switch(argv[3])

    def theme_handler(request):
        return switch(request["argv"][1])

    def background_handler(request):
        path = Path(request["argv"][1])
        events.append("background:" + path.name)
        if not path.is_file():
            return {"exit_code": 1, "stderr": "missing wallpaper"}
        (current / "background").unlink(missing_ok=True); (current / "background").symlink_to(path)
        return {"exit_code": 0}

    stub_command("env", env_handler)
    stub_command("omarchy-theme-set", theme_handler)
    stub_command("omarchy-theme-bg-set", background_handler)


def _activated_draft():
    draft = json.loads(json.dumps(SAMPLE)); draft["activate"] = True
    draft["wallpapers"] = [{"sourcePath": str(WALLPAPER.absolute()), "outputName": "01-new.png"}]
    draft["preferredWallpaper"] = "01-new.png"
    draft["acceptedWarnings"] = [*draft["acceptedWarnings"], "themes_replace_unmanaged:ocean-focus"]
    return draft


def test_failure_rollback_restores_same_slug_directory_then_theme_then_wallpaper(isolated_home, stub_command, fake_shell):
    paths = Paths.from_env(); registry, module, package, target, current = _setup_theme(paths, isolated_home)
    accents: list[str] = []; events: list[str] = []
    _handlers(stub_command, module, package, paths, current, accents, events, fail_first=True)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    revision = module.status(build_context("themes", "read", paths=paths, registry=registry.view, plugin_dir=ROOT)).revision
    with pytest.raises(CcError, match="Check 3"):
        executor.apply("themes", _activated_draft(), revision, confirmations=("themes_replace_unmanaged:ocean-focus",))
    record = executor.journal.history(limit=1)[0]
    assert record.state == "rolled_back"
    assert accents == ["#7aa2f7", "#112233"]
    assert events == ["theme:ocean-focus", "background:01-new.png", "theme:ocean-focus", "background:old.png"]
    assert package._parse_colors(target / "colors.toml")["accent"] == "#112233"
    assert Path(current / "background").resolve().name == "old.png"


def test_committed_undo_uses_the_same_inverse_order(isolated_home, stub_command, fake_shell):
    paths = Paths.from_env(); registry, module, package, target, current = _setup_theme(paths, isolated_home)
    accents: list[str] = []; events: list[str] = []
    _handlers(stub_command, module, package, paths, current, accents, events)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    revision = module.status(build_context("themes", "read", paths=paths, registry=registry.view, plugin_dir=ROOT)).revision
    applied = executor.apply("themes", _activated_draft(), revision, confirmations=("themes_replace_unmanaged:ocean-focus",))
    assert applied.state == "committed"
    undone = executor.rollback(applied.id)
    assert undone.state == "committed"
    assert accents == ["#7aa2f7", "#112233"]
    assert events[-2:] == ["theme:ocean-focus", "background:old.png"]
    assert package._parse_colors(target / "colors.toml")["accent"] == "#112233"
