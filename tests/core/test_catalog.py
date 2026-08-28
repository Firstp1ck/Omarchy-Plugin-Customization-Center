import json
from pathlib import Path
from types import SimpleNamespace

from customization_center.core import CommandRunner, Paths, ShellIpc
from customization_center.core.catalog import read


def test_catalog_join_authority_manifest_and_unmatched(fake_shell, stub_command):
    paths = Paths.from_env()
    manifests = sorted((paths.omarchy_path / "shell/plugins").rglob("manifest.json"))[:2]
    static = []
    for path in manifests:
        manifest = json.loads(path.read_text())
        static.append({"id": manifest["id"], "manifestPath": str(path), "sourceDir": str(path.parent),
                       "entryPoints": manifest.get("entryPoints", {}), "barWidget": manifest.get("barWidget")})
    static.append({"id": "not.loaded", "manifestPath": "/missing", "sourceDir": "/missing"})
    stub_command("omarchy-plugin-catalog", {"stdout": json.dumps(static)})
    runner = CommandRunner(mode="read")
    result = read(SimpleNamespace(commands=runner, shell=ShellIpc(runner), paths=paths))
    assert len(result.rows) == len(fake_shell.read()["plugins"])
    assert result.revision.startswith("sha256:")
    assert result.raw_document["listShellConfig"]["version"] == 1
    assert [item["id"] for item in result.diagnostics["undiscovered"]] == ["not.loaded"]
    joined = next(item for item in result.rows if item["id"] == static[0]["id"])
    assert joined["manifest"]["id"] == joined["id"]


def test_catalog_refuses_forged_manifest_path_outside_source(fake_shell, stub_command, isolated_home):
    paths = Paths.from_env()
    runtime_row = fake_shell.read()["plugins"][0]
    source = paths.omarchy_path / "shell/plugins" / runtime_row["id"].removeprefix("omarchy.")
    source.mkdir(parents=True, exist_ok=True)
    expected = source / "manifest.json"
    expected.write_text(json.dumps({"id": runtime_row["id"]}))
    outside = isolated_home / "forged-manifest.json"
    outside.write_text(json.dumps({"id": runtime_row["id"], "version": "forged"}))
    forged = [{"id": runtime_row["id"], "sourceDir": str(source), "manifestPath": str(outside)}]
    stub_command("omarchy-plugin-catalog", {"stdout": json.dumps(forged)})
    runner = CommandRunner(mode="read")
    result = read(SimpleNamespace(commands=runner, shell=ShellIpc(runner), paths=paths))
    warning = next(item for item in result.diagnostics["warnings"] if item["code"] == "plugins_manifest_mismatch")
    assert warning["pluginId"] == runtime_row["id"] and runtime_row["id"] in warning["message"]
    row = next(item for item in result.rows if item["id"] == runtime_row["id"])
    assert "manifest" not in row


def test_catalog_degrades_on_malformed_output(fake_shell, stub_command):
    stub_command("omarchy-plugin-catalog", {"stdout": "not json"})
    runner = CommandRunner(mode="read")
    result = read(SimpleNamespace(commands=runner, shell=ShellIpc(runner), paths=Paths.from_env()))
    assert result.rows and result.diagnostics["warnings"][0]["code"] == "plugins_catalog_unavailable"
