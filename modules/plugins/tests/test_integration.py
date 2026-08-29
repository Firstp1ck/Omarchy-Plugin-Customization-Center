from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from customization_center.core.context import build_context
from customization_center.core.paths import Paths


def test_runtime_rows_are_authority_and_static_only_rows_stay_diagnostics(plugins_backend, isolated_home, stub_command):
    runtime = [{"id": "acme.service", "name": "Acme Service", "kinds": ["service"], "enabled": False,
                "active": False, "canDisable": True, "firstParty": False, "clonedFrom": ""}]
    shell_config = {"version": 1, "plugins": [], "disabledPlugins": [],
                    "bar": {"layout": {"left": [], "center": [], "right": []}}}
    static = [{"id": "acme.static", "sourceDir": "/not/actionable", "manifestPath": "/not/actionable/manifest.json"}]
    stub_command("omarchy-shell", {"exit_code": 0, "stdout": "ok\n", "byArgs": [
        {"args": ["shell", "ping"], "stdout": "ok\n"},
        {"args": ["shell", "listPlugins"], "stdout": json.dumps(runtime) + "\n"},
        {"args": ["shell", "listShellConfig"], "stdout": json.dumps(shell_config) + "\n"}]})
    stub_command("omarchy-plugin-catalog", {"exit_code": 0, "stdout": json.dumps(static) + "\n"})
    registry = SimpleNamespace(module=lambda module_id: plugins_backend.MODULE)
    ctx = build_context("plugins", "read", paths=Paths.from_env(), registry=registry,
                        plugin_dir=Path(__file__).resolve().parents[3])
    status = plugins_backend.MODULE.status(ctx)
    assert [row["id"] for row in status.data["rows"]] == ["acme.service"]
    assert status.data["diagnostics"]["undiscovered"][0]["id"] == "acme.static"
    assert status.data["rows"][0]["origin"]["checkout"] == "unknown"


def test_malformed_catalog_degrades_without_promoting_disk_rows(plugins_backend, isolated_home, stub_command):
    runtime = [{"id": "omarchy.nightlight", "name": "Night Light", "kinds": ["service"], "enabled": True,
                "active": True, "canDisable": True, "firstParty": True, "clonedFrom": ""}]
    stub_command("omarchy-shell", {"exit_code": 0, "stdout": "ok\n", "byArgs": [
        {"args": ["shell", "ping"], "stdout": "ok\n"},
        {"args": ["shell", "listPlugins"], "stdout": json.dumps(runtime) + "\n"},
        {"args": ["shell", "listShellConfig"], "stdout": '{"version":1,"plugins":[],"disabledPlugins":[],"bar":{"layout":{"left":[],"center":[],"right":[]}}}\n'}]})
    stub_command("omarchy-plugin-catalog", {"exit_code": 0, "stdout": "not-json\n"})
    registry = SimpleNamespace(module=lambda module_id: plugins_backend.MODULE)
    ctx = build_context("plugins", "read", paths=Paths.from_env(), registry=registry)
    status = plugins_backend.MODULE.status(ctx)
    assert len(status.data["rows"]) == 1
    assert status.data["rows"][0]["firstParty"] is True
    assert any(warning.code == "plugins_catalog_unavailable" for warning in status.warnings)
