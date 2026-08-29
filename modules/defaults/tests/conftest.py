from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("defaults_root_conftest", ROOT / "tests/conftest.py")
assert spec and spec.loader
root_fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root_fixtures)

isolated_home = root_fixtures.isolated_home
stub_command = root_fixtures.stub_command
fake_shell = root_fixtures.fake_shell
outside_write_guard = root_fixtures.outside_write_guard


@pytest.fixture
def fault_plan(isolated_home, monkeypatch):
    def install(hooks):
        path = isolated_home / "fault-plan.json"
        path.write_text(json.dumps({"hooks": list(hooks)}), encoding="utf-8")
        monkeypatch.setenv("CC_TEST_FAULTS", str(path))
        return path
    return install
