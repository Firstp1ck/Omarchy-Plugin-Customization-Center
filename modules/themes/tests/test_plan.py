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
