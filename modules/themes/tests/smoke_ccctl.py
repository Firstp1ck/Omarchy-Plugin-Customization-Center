#!/usr/bin/python3
"""Run the themes status, validate, and plan envelopes in an isolated home."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = Path(__file__).parent / "fixtures/sample-draft.json"

with tempfile.TemporaryDirectory(prefix="themes-ccctl-") as temporary:
    root = Path(temporary)
    home = root / "home"
    runtime = root / "runtime"
    omarchy = root / "omarchy"
    stubs = root / "bin"
    for directory in (home, runtime, stubs):
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "tests/fixtures/omarchy", omarchy)
    for name in ("omarchy-theme-set", "omarchy-theme-bg-set", "omarchy-theme-set-templates", "omarchy-shell"):
        path = stubs / name
        path.write_text("#!/bin/sh\n[ \"$2\" = ping ] && printf 'ok\\n'\nexit 0\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_STATE_HOME": str(home / ".local/state"), "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_RUNTIME_DIR": str(runtime), "OMARCHY_PATH": str(omarchy),
        "PATH": str(stubs), "PYTHONDONTWRITEBYTECODE": "1",
    }
    commands = (
        [str(ROOT / "backend/ccctl"), "status", "themes"],
        [str(ROOT / "backend/ccctl"), "validate", "themes", "--draft", str(SAMPLE)],
        [str(ROOT / "backend/ccctl"), "plan", "themes", "--draft", str(SAMPLE)],
    )
    for command in commands:
        completed = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
        if completed.returncode != 0 or "internal_error" in completed.stdout:
            raise SystemExit(completed.stdout + completed.stderr)
        print(completed.stdout.strip())
