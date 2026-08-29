from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from customization_center.core import CcError
from customization_center.core.context import build_context
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())


def _module(paths):
    registry = load_registry(ROOT, paths=paths)
    return registry, registry.module("themes")


def _ctx(paths, registry, mode="read"):
    return build_context("themes", mode, paths=paths, registry=registry.view, plugin_dir=ROOT)


def _current(isolated_home: Path, colors: str | None = None):
    theme = isolated_home / ".local/state/omarchy/current/theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme / "colors.toml").write_text(colors or '\n'.join([
        'background = "#000000"', 'foreground = "#ffffff"', 'accent = "#3366ff"',
        'muted = "#777777"', 'red = "#ff0000"', 'yellow = "#ffff00"',
        'green = "#00ff00"', 'cyan = "#00ffff"', 'blue = "#0000ff"', 'magenta = "#ff00ff"',
    ]) + "\n")
    (theme / "shell.toml").write_text('[bar]\nbackground = "background"\ntext = "foreground"\n')
    (theme.parent / "theme.name").write_text("old\n")


def test_try_in_shell_requires_ping_exact_restore_and_one_open_transaction(isolated_home, stub_command, fake_shell):
    _current(isolated_home)
    paths = Paths.from_env(); registry, module = _module(paths)
    caps = module.capabilities(_ctx(paths, registry))
    assert caps.get("tryInShell").available
    status = module.status(_ctx(paths, registry))
    validation = module.validate(_ctx(paths, registry, "validate"), {**SAMPLE, "tryInShell": True}, status)
    plan = module.plan(_ctx(paths, registry, "plan"), validation.normalized_draft, status)
    assert len(plan.operations) == 1 and plan.operations[0].kind == "ShellIpc"
    assert plan.operations[0].inverse is not None and plan.operations[0].inverse.kind == "ShellIpc"

    opened_data = {**status.data, "openPreviewTransaction": {"transactionId": "existing"}}
    opened = replace(status, data=opened_data)
    with pytest.raises(CcError, match="Stop the current"):
        module.plan(_ctx(paths, registry, "plan"), validation.normalized_draft, opened)

    _current(isolated_home, 'background = "#000000"\nforeground = "#ffffff"\n')
    caps = module.capabilities(_ctx(paths, registry))
    assert not caps.get("tryInShell").available
    assert "missing" in caps.get("tryInShell").reason
    fake_shell.switch("down", True)
    assert not module.capabilities(_ctx(paths, registry)).get("tryInShell").available


def test_import_materializes_complete_provenance_draft_and_drops_extras(isolated_home):
    paths = Paths.from_env(); registry, module = _module(paths)
    source = isolated_home / ".config/omarchy/themes/plain"
    (source / "backgrounds").mkdir(parents=True)
    (source / "colors.toml").write_text('\n'.join([
        'mode = "dark"', 'background = "#101010"', 'foreground = "#eeeeee"', 'accent = "#3366ff"',
        'red = "#ff0000"', 'yellow = "#ffff00"', 'green = "#00ff00"', 'cyan = "#00ffff"',
        'blue = "#0000ff"', 'magenta = "#ff00ff"']) + "\n")
    (source / "shell.lock.toml").write_text('[lock]\ntext = "foreground"\nunknown = 4\n')
    (source / "hyprland.lua").write_text("return {}\n")
    (source / "backgrounds/scene.png").write_bytes((Path(__file__).parent / "fixtures/wallpapers/ok.png").read_bytes())
    result = module.query(_ctx(paths, registry), "import", {"slug": "plain", "duplicateSlug": "plain-copy"})
    draft = result["draft"]
    assert draft["slug"] == "plain-copy"
    assert draft["origin"]["type"] == "user" and draft["origin"]["slug"] == "plain"
    assert len(draft["palette"]) >= 26
    assert set(draft["sections"]) == {"bar", "controls", "spacing", "font", "popups", "tooltip", "notifications", "launcher", "menu", "polkit", "lock", "image-picker"}
    assert draft["sections"]["lock"]["text"] == "foreground"
    assert result["unsupportedKeys"] == ["lock.unknown"]
    assert result["unsupportedFiles"] == ["hyprland.lua"]
    assert Path(draft["wallpapers"][0]["sourcePath"]).is_absolute()


def test_activation_preferred_must_stay_under_declared_background_roots_and_plain_extras_warn(isolated_home):
    paths = Paths.from_env(); registry, module = _module(paths)
    theme = isolated_home / ".config/omarchy/themes/plain"
    backgrounds = theme / "backgrounds"; backgrounds.mkdir(parents=True)
    preferred = backgrounds / "ok.png"; preferred.write_bytes(b"ok")
    (theme / "hyprland.lua").write_text("return {}\n")
    outside = isolated_home / "outside.png"; outside.write_bytes(b"ok")
    status = module.status(_ctx(paths, registry))
    valid = {"schemaVersion": 1, "kind": "activate", "slug": "plain", "preferredWallpaper": str(preferred)}
    assert module.validate(_ctx(paths, registry, "validate"), valid, status).ok
    invalid = {**valid, "preferredWallpaper": str(outside)}
    validation = module.validate(_ctx(paths, registry, "validate"), invalid, status)
    assert not validation.ok and "themes_preferred_unknown" in {item.code for item in validation.issues}
    plan = module.plan(_ctx(paths, registry, "plan"), valid, status)
    warning = next(item for item in plan.warnings if item.code == "themes_activation_untrusted_files")
    assert warning.ack and "hyprland.lua" in warning.message
    assert warning.code in plan.requires_confirmation
