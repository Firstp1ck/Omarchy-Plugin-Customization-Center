from __future__ import annotations

import json
from pathlib import Path

from customization_center.core.context import build_context
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())


def test_compose_plan_materializes_only_with_core_operations(isolated_home):
    paths = Paths.from_env(); registry = load_registry(ROOT, paths=paths); module = registry.module("themes")
    status = module.status(build_context("themes", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    validation = module.validate(build_context("themes", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), SAMPLE, status)
    before = list(paths.state.rglob("*")) if paths.state.exists() else []
    plan = module.plan(build_context("themes", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    after = list(paths.state.rglob("*")) if paths.state.exists() else []
    assert before == after
    assert [operation.kind for operation in plan.operations].count("ReplaceDirectoryAtomic") == 1
    assert any(operation.kind == "WriteFileAtomic" and operation.params["path"].endswith("colors.toml") for operation in plan.operations)
    assert plan.operations[-2].kind == "ReplaceDirectoryAtomic"


def test_activation_inverse_dependencies_cover_same_slug_and_preferred_wallpaper(isolated_home):
    paths = Paths.from_env(); registry = load_registry(ROOT, paths=paths); module = registry.module("themes")
    current = isolated_home / ".local/state/omarchy/current"
    (current / "theme").mkdir(parents=True)
    (current / "theme.name").write_text("old\n")
    (current / "theme/colors.toml").write_text('foreground = "#ffffff"\nbackground = "#000000"\naccent = "#3366ff"\nmuted = "#777777"\nred = "#ff0000"\n')
    (current / "theme/shell.toml").write_text("[bar]\ntext = \"foreground\"\n")
    old_background = current / "theme/backgrounds/old.png"
    old_background.parent.mkdir(); old_background.write_bytes(b"old")
    (current / "background").symlink_to(old_background)
    wallpaper = Path(__file__).parent / "fixtures/wallpapers/ok.png"
    draft = json.loads(json.dumps(SAMPLE)); draft["activate"] = True
    draft["wallpapers"] = [{"sourcePath": str(wallpaper.absolute()), "outputName": "01-ok.png"}]
    draft["preferredWallpaper"] = "01-ok.png"
    status = module.status(build_context("themes", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    validation = module.validate(build_context("themes", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    assert validation.ok
    plan = module.plan(build_context("themes", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    replacement = next(item for item in plan.operations if item.kind == "ReplaceDirectoryAtomic")
    activation = next(item for item in plan.operations if item.kind == "RunCommand" and "omarchy-theme-set" in item.params["argv"])
    background = next(item for item in plan.operations if item.kind == "RunCommand" and "omarchy-theme-bg-set" in item.params["argv"])
    assert activation.inverse_after == (replacement.id,)
    assert background.inverse_after == (activation.id,)
    assert activation.params["argv"][:2] == ["env", "OMARCHY_THEME_SKIP_BACKGROUND=1"]
    assert activation.inverse.params["argv"][:2] == ["env", "OMARCHY_THEME_SKIP_BACKGROUND=1"]


def test_activation_only_wallpaper_inverse_waits_for_theme_inverse(isolated_home):
    paths = Paths.from_env(); registry = load_registry(ROOT, paths=paths); module = registry.module("themes")
    theme = isolated_home / ".config/omarchy/themes/next/backgrounds"
    theme.mkdir(parents=True); preferred = theme / "one.png"; preferred.write_bytes(b"png")
    current = isolated_home / ".local/state/omarchy/current"; (current / "theme").mkdir(parents=True)
    (current / "theme.name").write_text("old\n")
    status = module.status(build_context("themes", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = {"schemaVersion": 1, "kind": "activate", "slug": "next", "preferredWallpaper": str(preferred)}
    validation = module.validate(build_context("themes", "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    assert validation.ok
    plan = module.plan(build_context("themes", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    activation, background = plan.operations
    assert activation.inverse_after == ()
    assert background.inverse_after == (activation.id,)
