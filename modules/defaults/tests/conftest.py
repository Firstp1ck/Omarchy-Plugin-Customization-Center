from __future__ import annotations

import json

import pytest

from customization_center.core.paths import Paths
from tests.conftest import fake_shell, isolated_home, outside_write_guard, stub_command


@pytest.fixture
def fault_plan(isolated_home, monkeypatch):
    def install(hooks):
        path = Paths.from_env().private_tmpfile("-fault-plan.json")
        path.write_text(json.dumps({"hooks": list(hooks)}), encoding="utf-8")
        monkeypatch.setenv("CC_TEST_FAULTS", str(path))
        return path
    return install
