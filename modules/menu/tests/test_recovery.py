import json
from pathlib import Path

import pytest

from customization_center.core import CcError, Executor
from customization_center.core.context import build_context
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]


def test_malformed_file_requires_replace_after_backup(isolated_home, stub_command):
    stub_command("omarchy-menu", {"exit_code": 0, "stdout": "ok\n"})
    stub_command("bash", {"exit_code": 0})
    target = isolated_home / ".config/omarchy/extensions/omarchy-menu.jsonc"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"broken":')
    paths = Paths.from_env()
    registry = load_registry(ROOT, paths=paths)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    assert status.data["documentState"] == "malformed"
    draft = {"schemaVersion": 1, "module": "menu", "baseRevision": status.revision,
             "semantics": "full-shadow", "shape": "direct", "bom": False, "entries": [],
             "wrapperSiblings": [], "recovery": None}
    with pytest.raises(CcError) as error:
        module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    assert error.value.code == "unsupported_config"
    draft["recovery"] = {"mode": "replace-after-backup", "backupOfRevision": status.revision}
    plan = module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    assert "replace" in plan.requires_confirmation

    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    transaction = executor.apply("menu", draft, status.revision, confirmations=plan.requires_confirmation)
    manifest = executor.backups.read_manifest(transaction.id)
    backup_id = next(key for key, value in manifest.items() if value["path"] == str(target))
    assert (executor.backups._dir(transaction.id) / backup_id).read_bytes() == b'{"broken":'


def test_unsupported_default_wins_when_shell_is_down(isolated_home, stub_command):
    stub_command("omarchy-menu", {"exit_code": 1, "stderr": "omarchy-shell is not running\n"})
    stub_command("bash", {"exit_code": 0})
    paths = Paths.from_env()
    (paths.omarchy_path / "default/omarchy/omarchy-menu.jsonc").write_text('{"broken":')
    registry = load_registry(ROOT, paths=paths)
    module = registry.module("menu")
    status = module.status(build_context("menu", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    assert status.data["documentState"] == "unsupported"
    draft = {"schemaVersion": 1, "module": "menu", "baseRevision": status.revision,
             "semantics": "full-shadow", "shape": "direct", "bom": False, "entries": [],
             "wrapperSiblings": [], "recovery": {"mode": "replace-after-backup", "backupOfRevision": status.revision}}
    with pytest.raises(CcError) as error:
        module.plan(build_context("menu", "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    assert error.value.code == "unsupported_config"
