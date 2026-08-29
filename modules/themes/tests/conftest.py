from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest_plugins = ["tests.conftest"]

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry


@pytest.fixture
def fault_plan(isolated_home, monkeypatch):
    path = isolated_home / "faults.json"

    def arm(*hooks):
        path.write_text(json.dumps({"hooks": list(hooks)}), encoding="utf-8")
        monkeypatch.setenv("CC_TEST_FAULTS", str(path))
        return path

    return arm


@pytest.fixture(scope="session")
def themes_backend():
    registry = load_registry(ROOT, paths=Paths.from_env())
    entry = registry.view.entry("themes")
    package = sys.modules[entry.module.__class__.__module__.rsplit(".", 1)[0]]
    return package
