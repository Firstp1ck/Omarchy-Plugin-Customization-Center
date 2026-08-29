from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from customization_center.core.context import build_context
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())
WALLPAPER = Path(__file__).parent / "fixtures/wallpapers/ok.png"


def _context(paths, registry, mode="read"):
    return build_context("themes", mode, paths=paths, registry=registry.view, plugin_dir=ROOT)


def _setup(isolated_home, fake_shell):
    paths = Paths.from_env(); registry = load_registry(ROOT, paths=paths); module = registry.module("themes")
    source = isolated_home / ".config/omarchy/themes/candidate"
    source.mkdir(parents=True)
    draft = json.loads(json.dumps(SAMPLE)); draft["slug"] = "candidate"
    for name, content in module._generated(_context(paths, registry, "plan"), draft).items():
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    (source / "backgrounds").mkdir(); (source / "backgrounds/one.png").write_bytes(WALLPAPER.read_bytes())
    current = isolated_home / ".local/state/omarchy/current"
    (current / "theme").mkdir(parents=True)
    (current / "theme/colors.toml").write_text('\n'.join([
        'background = "#000000"', 'foreground = "#ffffff"', 'accent = "#3366ff"', 'muted = "#777777"',
        'red = "#ff0000"', 'yellow = "#ffff00"', 'green = "#00ff00"', 'cyan = "#00ffff"', 'blue = "#0000ff"', 'magenta = "#ff00ff"']) + "\n")
    (current / "theme/shell.toml").write_text('[bar]\nbackground = "background"\ntext = "foreground"\n')
    (current / "theme.name").write_text("old\n")
    before = module.status(_context(paths, registry))
    activation = {"schemaVersion": 1, "kind": "activate", "slug": "candidate", "preferredWallpaper": None}
    validation = module.validate(_context(paths, registry, "validate"), activation, before)
    plan = module.plan(_context(paths, registry, "plan"), validation.normalized_draft, before)
    detail = plan.operations[0].detail
    shutil.rmtree(current / "theme"); shutil.copytree(source, current / "theme")
    (current / "theme/shell.toml").write_text(detail["shellToml"])
    (current / "theme.name").write_text("candidate\n")
    (current / "background").symlink_to(current / "theme/backgrounds/one.png")
    after = module.status(_context(paths, registry))
    return paths, registry, module, plan, after, current


def test_all_eight_activation_verify_checks_pass_on_matching_state(isolated_home, stub_command, fake_shell):
    paths, registry, module, plan, after, _ = _setup(isolated_home, fake_shell)
    result = module.verify(_context(paths, registry, "verify"), plan, after, {})
    assert result.state == "pass" and result.evidence["checks"] == list(range(1, 9))


@pytest.mark.parametrize("check,expected_code", [
    (1, "themes_verify_active"), (2, "themes_verify_colors"), (3, "themes_verify_sections"),
    (4, "themes_verify_placeholder"), (5, "themes_verify_fragment"), (6, "themes_verify_background"),
    (7, "themes_verify_shell"), (8, "themes_concurrent_change"),
])
def test_each_activation_verify_check_fails_independently(isolated_home, stub_command, fake_shell, check, expected_code):
    paths, registry, module, plan, after, current = _setup(isolated_home, fake_shell)
    operation = plan.operations[0]
    detail = dict(operation.detail or {})
    if check == 1:
        after = replace(after, data={**after.data, "active": {**after.data["active"], "slug": "wrong"}})
    elif check == 2:
        (current / "theme/colors.toml").write_text('background = "#ffffff"\n')
    elif check == 3:
        (current / "theme/shell.toml").write_text('[bar]\ntext = "urgent"\n')
    elif check == 4:
        (current / "theme/hyprland.lua").write_text("return '{{ accent }}'\n")
    elif check == 5:
        detail["customSections"] = ["lock"]
        operation = replace(operation, detail=detail); plan = replace(plan, operations=(operation,))
    elif check == 6:
        detail["preferredWallpaper"] = str(current / "theme/backgrounds/missing.png")
        operation = replace(operation, detail=detail); plan = replace(plan, operations=(operation,))
    elif check == 7:
        fake_shell.switch("down", True)
    elif check == 8:
        other = isolated_home / ".config/omarchy/themes/unrelated"; other.mkdir(); (other / "colors.toml").write_text('mode = "dark"\n')
        after = module.status(_context(paths, registry))
    result = module.verify(_context(paths, registry, "verify"), plan, after, {})
    assert result.state == "fail" and result.code == expected_code
    assert result.evidence.get("check") == check
