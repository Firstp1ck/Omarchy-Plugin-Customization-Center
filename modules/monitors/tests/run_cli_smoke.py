#!/usr/bin/python3
"""Run the three read-only monitors CLI smoke checks in an isolated home."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = Path(__file__).parent / "fixtures/sample-draft.json"
INVENTORY = Path(__file__).parent / "fixtures/hyprctl/laptop-only.json"

with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary); home = base / "home"; binary = base / "bin"; runtime = base / "run"
    for path in (home / ".config", home / ".local/state", home / ".cache", binary, runtime): path.mkdir(parents=True)
    hyprctl = binary / "hyprctl"
    hyprctl.write_text(f"#!/bin/sh\ncat {str(INVENTORY)!r}\n", encoding="utf-8"); hyprctl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "XDG_STATE_HOME": str(home / ".local/state"), "XDG_CACHE_HOME": str(home / ".cache"),
           "XDG_RUNTIME_DIR": str(runtime), "HYPRLAND_INSTANCE_SIGNATURE": "test",
           "PATH": str(binary) + os.pathsep + "/usr/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    commands = [["status", "monitors"], ["validate", "monitors", "--draft", str(SAMPLE)],
                ["plan", "monitors", "--draft", str(SAMPLE)]]
    for args in commands:
        result = subprocess.run([str(ROOT / "backend/ccctl"), *args], cwd=ROOT, env=env, text=True, capture_output=True, check=False)
        envelope = json.loads(result.stdout.strip().splitlines()[-1])
        if result.returncode or not envelope.get("ok") or any(item.get("code") == "internal_error" for item in envelope.get("errors", [])):
            raise SystemExit(result.stdout + result.stderr)
        print(json.dumps(envelope, separators=(",", ":")))
