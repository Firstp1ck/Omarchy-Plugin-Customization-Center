from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


@pytest.fixture(scope="session")
def bar_backend():
    package = ROOT / "modules/bar/backend"
    name = "cc_modules.bar"
    if "cc_modules" not in sys.modules:
        parent = types.ModuleType("cc_modules")
        parent.__path__ = []
        sys.modules["cc_modules"] = parent
    spec = importlib.util.spec_from_file_location(name, package / "__init__.py", submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
