from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_ccctl_does_not_create_bytecode(isolated_home: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([str(repo / "backend/ccctl"), "modules"], env=env,
                            text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0
    assert json.loads(result.stdout.splitlines()[-1])["ok"] is True
    assert not list(repo.rglob("__pycache__"))
