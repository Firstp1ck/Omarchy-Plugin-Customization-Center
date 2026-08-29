from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import Plan, Status, ops
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

from .test_planner_extended import INVENTORY_TEXT, Journal, SAMPLE, context, status_for

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def backend():
    load_registry(ROOT, paths=Paths.from_env())
    return {name: importlib.import_module(f"cc_modules.monitors.{name}") for name in ("planner", "inventory")}


def _activate(module, ctx, status, value):
    return module.plan(ctx, {"schemaVersion":1,"action":"activate","profileId":value["id"],"profile":value,"assignments":{"laptop":"eDP-1"}}, status)


def test_monitors_output_skipped_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); value=json.loads(json.dumps(SAMPLE["profile"]))
    skipped=json.loads(json.dumps(value["outputs"][0])); skipped["id"]="projector"; skipped["label"]="Projector"; skipped["identity"]["connector"]="DP-9"; skipped["whenMissing"]="skip"; value["outputs"].append(skipped)
    plan=_activate(backend["planner"].MODULE,ctx,status_for(backend,ctx,value),value)
    assert "monitors_output_skipped" in {item.code for item in plan.warnings}


def test_monitors_extra_uses_catchall_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); value=json.loads(json.dumps(SAMPLE["profile"])); value["match"]["allowExtra"]=True
    status=status_for(backend,ctx,value); extra=json.loads(json.dumps(status.data["inventory"]["outputs"][0])); extra["connector"]="DP-2"; extra["serial"]="2"; status.data["inventory"]["outputs"].append(extra)
    plan=_activate(backend["planner"].MODULE,ctx,status,value)
    assert "monitors_extra_uses_catchall" in {item.code for item in plan.warnings}


def test_monitors_clamshell_override_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); status=status_for(backend,ctx)
    status.data["toggles"]["internal-monitor-clamshell"]={"state":"known","path":"clamshell.lua","connectors":["eDP-1"]}
    plan=_activate(backend["planner"].MODULE,ctx,status,SAMPLE["profile"])
    assert "monitors_clamshell_override" in {item.code for item in plan.warnings}


def test_monitors_gdk_scale_mismatch_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); outputs,_=backend["inventory"].parse_inventory(INVENTORY_TEXT); outputs[0]["scale120"]=120
    monkeypatch.setattr(backend["planner"].inventory,"read",lambda unused,timeout_s=3:(outputs,()))
    host=backend["planner"]._paths(ctx)["host"]; host.parent.mkdir(parents=True); host.write_text('local omarchy_monitor_scale = "auto"\nlocal omarchy_gdk_scale = 2\nhl.monitor({ output = "", mode = "preferred", position = "auto", scale = omarchy_monitor_scale })\n')
    assert "monitors_gdk_scale_mismatch" in {item.code for item in backend["planner"].MODULE.status(ctx).warnings}


def test_monitors_handwritten_rule_other_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); outputs,_=backend["inventory"].parse_inventory(INVENTORY_TEXT)
    monkeypatch.setattr(backend["planner"].inventory,"read",lambda unused,timeout_s=3:(outputs,()))
    host=backend["planner"]._paths(ctx)["host"]; host.parent.mkdir(parents=True); host.write_text('hl.monitor({ output = "DP-9", mode = "preferred", position = "auto", scale = 1 })\n')
    assert "monitors_handwritten_rule_other" in {item.code for item in backend["planner"].MODULE.status(ctx).warnings}


def test_monitors_profile_invalid_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); outputs,_=backend["inventory"].parse_inventory(INVENTORY_TEXT)
    monkeypatch.setattr(backend["planner"].inventory,"read",lambda unused,timeout_s=3:(outputs,()))
    profile_dir=backend["planner"]._paths(ctx)["profiles"]; profile_dir.mkdir(parents=True); (profile_dir / "broken.json").write_text("not json")
    assert "monitors_profile_invalid" in {item.code for item in backend["planner"].MODULE.status(ctx).warnings}


def test_monitors_runtime_drift_warning(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); outputs,_=backend["inventory"].parse_inventory(INVENTORY_TEXT)
    drifted=json.loads(json.dumps(outputs)); drifted[0]["x"]=99
    monkeypatch.setattr(backend["planner"].inventory,"read",lambda unused,timeout_s=3:(drifted,()))
    paths=backend["planner"]._paths(ctx); paths["active"].parent.mkdir(parents=True)
    pointer={"schemaVersion":1,"profileId":"laptop","planDigest":"digest","appliedAt":"now","rulesSha256":"sha256:x","assignments":{"laptop":"eDP-1"}}; paths["active"].write_text(json.dumps(pointer))
    reload=__import__("dataclasses").replace(ops.HyprctlReload(ctx),detail={"expectedTopology":backend["planner"]._topology(outputs),"untoggledExpectedTopology":backend["planner"]._topology(outputs),"profileId":"laptop"})
    ctx.journal=Journal([SimpleNamespace(id="tx",state="committed",plan=Plan("monitors","revision",(reload,),(),"",(),(),plan_digest="digest"))])
    assert "monitors_runtime_drift" in {item.code for item in backend["planner"].MODULE.status(ctx).warnings}
