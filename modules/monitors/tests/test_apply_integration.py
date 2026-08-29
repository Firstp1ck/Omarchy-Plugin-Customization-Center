from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from customization_center.core import CcError
from customization_center.core.context import build_context
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())
INVENTORY = Path(__file__).parent / "fixtures/hyprctl/laptop-only.json"


def _environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    home = tmp_path / "home"; binary = tmp_path / "bin"; runtime = tmp_path / "run"
    for path in (home / ".config", home / ".local/state", home / ".cache", binary, runtime): path.mkdir(parents=True)
    hyprctl = binary / "hyprctl"
    hyprctl.write_text(f'''#!/bin/sh
if [ "$*" = "-j configerrors" ]; then printf '[]\\n';
elif [ "$1" = "reload" ]; then printf 'ok\\n';
else cat {str(INVENTORY)!r}; fi
'''); hyprctl.chmod(0o755)
    for command in ("systemd-run", "systemctl"):
        stub = binary / command; stub.write_text("#!/bin/sh\nexit 0\n"); stub.chmod(0o755)
    for name, value in {"HOME": home, "XDG_CONFIG_HOME": home / ".config", "XDG_STATE_HOME": home / ".local/state",
                        "XDG_CACHE_HOME": home / ".cache", "XDG_RUNTIME_DIR": runtime}.items(): monkeypatch.setenv(name, str(value))
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test"); monkeypatch.setenv("PATH", str(binary) + os.pathsep + "/usr/bin")
    return Paths.from_env()


def test_save_profile_fault_rolls_back_byte_identical(tmp_path, monkeypatch):
    paths = _environment(tmp_path, monkeypatch)
    target = paths.xdg_config_home / "omarchy/customization-center/monitor-profiles/laptop.json"
    target.parent.mkdir(parents=True); original = b'{"schemaVersion":1,"seed":true}\n'; target.write_bytes(original)
    faults = paths.home / "faults.json"; faults.write_text('{"hooks":["before_verify"]}')
    monkeypatch.setenv("CC_TEST_FAULTS", str(faults))
    registry = load_registry(ROOT, paths=paths); executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    status = registry.module("monitors").status(build_context("monitors", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    with pytest.raises(CcError): executor.apply("monitors", SAMPLE, status.revision)
    record = executor.journal.history(limit=1)[0]
    assert record.state == "rolled_back"
    assert target.read_bytes() == original


def test_activation_before_and_after_operation_faults_restore_all_files(tmp_path, monkeypatch):
    from customization_center.core.executor import Executor as ExecutorClass
    monkeypatch.setattr(ExecutorClass, "_wait_gate", lambda self, tx, operation, results, verify_partial=True: tx)

    probe_paths = _environment(tmp_path / "probe", monkeypatch)
    profile_path = probe_paths.module_config("monitors") / "monitor-profiles/laptop.json"
    profile_path.parent.mkdir(parents=True); profile_path.write_text(json.dumps(SAMPLE["profile"]))
    host = probe_paths.home / ".config/hypr/monitors.lua"; host.parent.mkdir(parents=True)
    host.write_bytes((Path(__file__).parent / "fixtures/monitors-lua/shipped-default.lua").read_bytes())
    registry = load_registry(ROOT, paths=probe_paths)
    module = registry.module("monitors")
    status = module.status(build_context("monitors", "read", paths=probe_paths, registry=registry.view, plugin_dir=ROOT))
    draft = json.loads(json.dumps(SAMPLE)); draft.update({"action":"activate","profileId":"laptop","assignments":{"laptop":"eDP-1"}})
    plan = module.plan(build_context("monitors", "plan", paths=probe_paths, registry=registry.view, plugin_dir=ROOT), draft, status)
    hooks = [f"{side}_op:{operation.id}" for operation in plan.operations for side in ("before", "after")]

    for index, hook in enumerate(hooks):
        paths = _environment(tmp_path / f"case-{index}", monkeypatch)
        profile_path = paths.module_config("monitors") / "monitor-profiles/laptop.json"
        profile_path.parent.mkdir(parents=True); original_profile = json.dumps(SAMPLE["profile"]).encode(); profile_path.write_bytes(original_profile)
        host = paths.home / ".config/hypr/monitors.lua"; host.parent.mkdir(parents=True)
        original_host = (Path(__file__).parent / "fixtures/monitors-lua/shipped-default.lua").read_bytes(); host.write_bytes(original_host)
        generated = paths.xdg_config_home / "omarchy/customization-center/generated/monitors.lua"
        active = paths.module_state("monitors") / "active.json"
        faults = paths.home / "faults.json"; faults.write_text(json.dumps({"hooks":[hook]})); monkeypatch.setenv("CC_TEST_FAULTS", str(faults))
        registry = load_registry(ROOT, paths=paths); executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
        status = registry.module("monitors").status(build_context("monitors", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
        with pytest.raises(CcError) as caught: executor.apply("monitors", draft, status.revision)
        history = executor.journal.history(limit=1)
        assert history, (hook, caught.value.code, caught.value.message)
        record = history[0]
        assert record.state == "rolled_back", (hook, record.rollback_errors)
        assert host.read_bytes() == original_host
        assert profile_path.read_bytes() == original_profile
        assert not generated.exists()
        assert not active.exists()

    inverse_targets = [operation for operation in plan.operations if operation.kind != "TimedConfirmation"]
    final_id = plan.operations[-1].id
    for index, target_operation in enumerate(inverse_targets):
        paths = _environment(tmp_path / f"inverse-{index}", monkeypatch)
        profile_path = paths.module_config("monitors") / "monitor-profiles/laptop.json"
        profile_path.parent.mkdir(parents=True); original_profile = json.dumps(SAMPLE["profile"]).encode(); profile_path.write_bytes(original_profile)
        host = paths.home / ".config/hypr/monitors.lua"; host.parent.mkdir(parents=True)
        original_host = (Path(__file__).parent / "fixtures/monitors-lua/shipped-default.lua").read_bytes(); host.write_bytes(original_host)
        generated = paths.xdg_config_home / "omarchy/customization-center/generated/monitors.lua"
        active = paths.module_state("monitors") / "active.json"
        faults = paths.home / "faults.json"
        faults.write_text(json.dumps({"hooks":[f"after_op:{final_id}", f"before_inverse:{target_operation.id}"]}))
        monkeypatch.setenv("CC_TEST_FAULTS", str(faults))
        registry = load_registry(ROOT, paths=paths); executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
        status = registry.module("monitors").status(build_context("monitors", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
        with pytest.raises(CcError): executor.apply("monitors", draft, status.revision)
        record = executor.journal.history(limit=1)[0]
        assert record.state == "rollback_failed"
        error = next(item for item in record.rollback_errors if item.get("operationId") == target_operation.id)
        for affected in error.get("affectedPaths", []):
            if affected in record.backups:
                executor.restore(record.id, affected)
        refreshed = executor.journal.load(record.id)
        remaining = next((item for item in refreshed.rollback_errors if item.get("operationId") == target_operation.id and not item.get("resolved")), None)
        if remaining is not None:
            executor.resolve(record.id, target_operation.id)
        assert host.read_bytes() == original_host
        assert profile_path.read_bytes() == original_profile
        assert not generated.exists()
        assert not active.exists()
