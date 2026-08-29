from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry


@pytest.fixture(scope="session")
def keybindings_backend():
    registry = load_registry(ROOT, paths=Paths.from_env())
    entry = registry.view.entry("keybindings")
    return sys.modules[entry.module.__class__.__module__]
