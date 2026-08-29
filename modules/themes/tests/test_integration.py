from __future__ import annotations

import json
from pathlib import Path

import pytest

from customization_center.core import CcError
from customization_center.core.context import build_context
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())


def setup_executor(paths):
    registry = load_registry(ROOT, paths=paths)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    status = registry.module("themes").status(build_context("themes", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    return executor, status.revision


def test_save_new_theme_end_to_end(isolated_home, stub_command, fake_shell):
    paths = Paths.from_env(); executor, revision = setup_executor(paths)
    tx = executor.apply("themes", SAMPLE, revision)
    target = isolated_home / ".config/omarchy/themes/ocean-focus"
    assert tx.state == "committed"
    assert (target / "colors.toml").is_file()
    assert (target / "preview.png").is_file()
    assert (paths.module_state("themes") / "ocean-focus.json").is_file()


def test_fault_after_directory_swap_rolls_back_byte_identically(isolated_home, stub_command, fake_shell, fault_plan):
    target = isolated_home / ".config/omarchy/themes/ocean-focus"
    target.mkdir(parents=True)
    original = b'legacy theme bytes\n'
    (target / "colors.toml").write_bytes(original)
    draft = json.loads(json.dumps(SAMPLE)); draft["acceptedWarnings"] = [*draft["acceptedWarnings"], "themes_replace_unmanaged:ocean-focus"]
    paths = Paths.from_env(); executor, revision = setup_executor(paths)
    module = executor.registry.module("themes")
    status = module.status(build_context("themes", "read", paths=paths, registry=executor.registry, plugin_dir=ROOT))
    normalized = module.validate(build_context("themes", "validate", paths=paths, registry=executor.registry, plugin_dir=ROOT), draft, status).normalized_draft
    plan = module.plan(build_context("themes", "plan", paths=paths, registry=executor.registry, plugin_dir=ROOT), normalized, status)
    replace = next(operation for operation in plan.operations if operation.kind == "ReplaceDirectoryAtomic")
    fault_plan("after_op:" + replace.id)
    executor, revision = setup_executor(paths)
    with pytest.raises(CcError):
        executor.apply("themes", draft, revision, confirmations=("themes_replace_unmanaged:ocean-focus",))
    record = executor.journal.history(limit=1)[0]
    assert record.state == "rolled_back"
    assert (target / "colors.toml").read_bytes() == original
