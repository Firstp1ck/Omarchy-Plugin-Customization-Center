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
STOCK = b"-- personal bindings\n"
DRAFT = {
    "schemaVersion": 1,
    "expectedRevision": "",
    "model": {
        "schemaVersion": 1,
        "bindings": [{
            "id": "b51ebad9-3854-4fd6-8904-d2986d9bd24c", "enabled": True,
            "chord": {"sourceKeys": "SUPER + SHIFT + R", "modifiers": ["SUPER", "SHIFT"], "key": {"kind": "keysym", "value": "r"}},
            "description": "Open project terminal", "action": {"type": "exec", "command": "xdg-terminal-exec", "catalogId": None},
            "flags": {"locked": False, "release": False, "repeating": False, "nonConsuming": False, "autoConsuming": False, "bypass": False}
        }],
        "disabled": []
    }
}


def setup_home(tmp_path, monkeypatch):
    home = tmp_path / "home"; config = home / ".config"; state = home / ".local/state"; runtime = tmp_path / "runtime"; cache = tmp_path / "cache"; omarchy = tmp_path / "omarchy"; bin_dir = tmp_path / "bin"
    for path in (config / "hypr", config / "omarchy", state, runtime, cache, omarchy / "default/hypr/bindings", bin_dir): path.mkdir(parents=True, exist_ok=True)
    bindings = config / "hypr/bindings.lua"; bindings.write_bytes(STOCK)
    script = bin_dir / "hyprctl"
    script.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
args=sys.argv[1:]
text=(pathlib.Path(os.environ["HOME"])/".config/hypr/bindings.lua").read_text() if (pathlib.Path(os.environ["HOME"])/".config/hypr/bindings.lua").exists() else ""
present="Open project terminal" in text
record="bindd\\n\\tmodmask: 65\\n\\tsubmap: \\n\\tkey: R\\n\\tkeycode: 0\\n\\tcatchall: false\\n\\tdescription: Open project terminal\\n\\tdispatcher: __lua\\n\\targ: 1\\n\\n"
obj={"locked":False,"mouse":False,"release":False,"repeat":False,"longPress":False,"non_consuming":False,"auto_consuming":False,"has_description":True,"modmask":65,"keycode":0,"submap":"","key":"R","description":"Open project terminal","dispatcher":"__lua","arg":"1","catch_all":False,"allow_input_capture":False,"submap_universal":"false"}
if args==["binds"]: print(record if present else "", end="")
elif args==["-j","binds"]: print(json.dumps([obj] if present else []))
elif args==["-j","devices"]: print('{"keyboards":[],"switches":[]}')
elif args==["version"]: print("Hyprland 0.56.2")
elif args==["-j","configerrors"]: print('[]')
elif args==["reload","config-only"]: print("ok")
else: print("{}")
''')
    script.chmod(0o755)
    luac = bin_dir / "luac"; luac.write_text("#!/bin/sh\nexit 0\n"); luac.chmod(0o755)
    values = {"HOME": home, "XDG_CONFIG_HOME": config, "XDG_STATE_HOME": state, "XDG_CACHE_HOME": cache,
              "XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": omarchy, "PATH": bin_dir}
    for key, value in values.items(): monkeypatch.setenv(key, str(value))
    return bindings


def apply_once(tmp_path, monkeypatch, fault_hook=None):
    bindings = setup_home(tmp_path, monkeypatch)
    paths = Paths.from_env(); registry = load_registry(ROOT, paths=paths); module = registry.view.module("keybindings")
    status = module.status(build_context("keybindings", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    if fault_hook:
        fault_file = paths.home / "faults.json"; fault_file.write_text(json.dumps({"hooks": [fault_hook]}))
        monkeypatch.setenv("CC_TEST_FAULTS", str(fault_file))
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    return bindings, paths, status, executor


def test_apply_and_verify(tmp_path, monkeypatch):
    bindings, paths, status, executor = apply_once(tmp_path, monkeypatch)
    tx = executor.apply("keybindings", DRAFT, status.revision)
    assert tx.state == "committed"
    assert b"Open project terminal" in bindings.read_bytes()
    assert (paths.xdg_config_home / "omarchy/customization-center/keybindings.json").is_file()
    module = executor.registry.module("keybindings")
    fresh = module.status(build_context("keybindings", "read", paths=paths, registry=executor.registry, plugin_dir=ROOT))
    validation = module.validate(build_context("keybindings", "validate", paths=paths, registry=executor.registry, plugin_dir=ROOT), DRAFT, fresh)
    assert validation.ok
    assert not any(issue.code == "keybindings_exact_conflict" for issue in validation.issues)


@pytest.mark.parametrize("hook", ["after_op:keybindings.0001", "after_op:keybindings.0003", "after_op:keybindings.0005", "verification_mismatch"])
def test_fault_rolls_back_byte_identical(tmp_path, monkeypatch, hook):
    bindings, paths, status, executor = apply_once(tmp_path, monkeypatch, hook)
    before = bindings.read_bytes()
    with pytest.raises(CcError) as raised:
        executor.apply("keybindings", DRAFT, status.revision)
    tx = executor.journal.load(raised.value.data["transactionId"])
    assert tx.state == "rolled_back"
    assert bindings.read_bytes() == before
    assert not (paths.xdg_config_home / "omarchy/customization-center/keybindings.json").exists()
