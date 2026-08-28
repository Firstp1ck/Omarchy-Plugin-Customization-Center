from __future__ import annotations

import json
import shutil
from pathlib import Path

from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry


def _copy_hello(tmp_path: Path, repo: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(repo / "tests/fixtures/modules/hello", target)
    data = json.loads((target / "module.json").read_text())
    data["id"] = name
    (target / "module.json").write_text(json.dumps(data))
    source = (target / "backend/__init__.py").read_text().replace('id = "hello"', f'id = "{name}"')
    (target / "backend/__init__.py").write_text(source)
    return target


def test_broken_module_warns_and_healthy_loads(isolated_home, tmp_path):
    repo = Path(__file__).resolve().parents[2]
    healthy = _copy_hello(tmp_path, repo, "healthy")
    broken = _copy_hello(tmp_path, repo, "broken")
    (broken / "backend/__init__.py").write_text("raise RuntimeError('broken')\n")
    registry = load_registry(repo, [healthy, broken], Paths.from_env())
    assert registry.module("healthy").id == "healthy"
    assert len(registry.warnings) == 1 and registry.warnings[0].code == "registry"


def test_invalid_extra_template_is_registry_warning(isolated_home, tmp_path):
    repo = Path(__file__).resolve().parents[2]
    module = _copy_hello(tmp_path, repo, "unsafe")
    data = json.loads((module / "module.json").read_text())
    data["extraWritablePaths"] = ["{unknown}/file"]
    (module / "module.json").write_text(json.dumps(data))
    registry = load_registry(repo, [module], Paths.from_env())
    assert "unsafe" not in registry.entries and len(registry.warnings) == 1


def test_module_id_mismatch_is_registry_warning(isolated_home, tmp_path):
    repo = Path(__file__).resolve().parents[2]
    module = _copy_hello(tmp_path, repo, "mismatch")
    data = json.loads((module / "module.json").read_text()); data["id"] = "different"
    (module / "module.json").write_text(json.dumps(data))
    registry = load_registry(repo, [module], Paths.from_env())
    assert not registry.entries and len(registry.warnings) == 1
