from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import customization_center.modules as registered_modules
from customization_center.core.context import build_context
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]


def test_wrapped_remove_handoff_launches_exact_argv_and_reconciles(plugins_backend, isolated_home, stub_command, monkeypatch):
    removed = {"value": False}

    def shell(argv, stdin, env):
        args = argv[1:]
        if args == ["shell", "ping"]:
            return {"exit_code": 0, "stdout": "ok\n"}
        if args == ["shell", "listPlugins"]:
            rows = [] if removed["value"] else [{"id": "acme.service", "name": "Acme Service", "kinds": ["service"],
                "enabled": True, "active": True, "canDisable": True, "firstParty": False, "clonedFrom": ""}]
            return {"exit_code": 0, "stdout": json.dumps(rows) + "\n"}
        if args == ["shell", "listShellConfig"]:
            return {"exit_code": 0, "stdout": '{"version":1,"plugins":[{"id":"acme.service"}],"disabledPlugins":[],"bar":{"layout":{"left":[],"center":[],"right":[]}}}\n'}
        return {"exit_code": 1, "stderr": "unexpected shell call\n"}

    stub_command("omarchy-shell", shell)
    stub_command("omarchy-plugin-catalog", {"exit_code": 0, "stdout": "[]\n"})
    stub_command("omarchy-launch-floating-terminal-with-presentation", {"exit_code": 0})
    monkeypatch.setattr(registered_modules, "MODULES", [*registered_modules.MODULES, "plugins"])
    paths = Paths.from_env()
    registry = load_registry(ROOT, paths=paths)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    status = registry.module("plugins").status(build_context("plugins", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    draft = {"schemaVersion": 1, "module": "plugins", "baseRevision": status.revision,
             "changes": [{"kind": "lifecycle", "action": "remove", "pluginId": "acme.service"}]}
    tx = executor.apply("plugins", draft, status.revision,
                        confirmations=["plugins.0001", "plugins_confirm_remove"])
    assert tx.state == "pending_handoff"
    launch = stub_command.calls("omarchy-launch-floating-terminal-with-presentation")[-1]
    assert launch[1:] == [str(ROOT / "backend/cc-handoff"), tx.id, "omarchy-plugin-remove", "acme.service"]

    handoff = paths.state / "handoffs" / f"{tx.id}.json"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text('{"exitCode":0,"finishedAt":"2026-01-01T00:00:00Z"}\n')
    completed = subprocess.run([str(ROOT / "backend/ccctl"), "status", "plugins"], cwd=ROOT,
        env=dict(os.environ), text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(completed.stdout.splitlines()[-1])
    pending = envelope["data"]["pendingHandoffs"]
    assert len(pending) == 1 and pending[0]["id"] == tx.id and pending[0]["sentinelExists"] is True
    removed["value"] = True
    reconciled = executor.reconcile(tx.id)
    assert reconciled.state == "committed"
    assert reconciled.verify is not None
    assert reconciled.verify.state == "pass"
    assert reconciled.verify.level == "limited"
