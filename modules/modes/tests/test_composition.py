from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import pytest
from customization_center.core import (Capabilities, Capability, CcError, Operation, Plan, ResourceClaim, Status, ValidationResult, VerifyResult)
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths

class Clock:
    def now_iso(self): return "2026-01-01T00:00:00Z"
class Member:
    def __init__(self,module_id,status,kind="WriteFileAtomic",claim=None): self.id=module_id; self._status=status; self.kind=kind; self.claim=claim
    def capabilities(self,ctx): return Capabilities(self.id,(Capability("apply",True,""),),"now")
    def status(self,ctx): return self._status
    def validate(self,ctx,draft,status): return ValidationResult(True,(),draft)
    def plan(self,ctx,draft,status):
        if self.id=="monitors" and draft.get("action")=="save-profile":
            profile=draft["profile"]
            record=Operation("monitors.0001","monitors","WriteFileAtomic",{"path":str(ctx.paths.module_config("monitors")/"monitor-profiles"/(profile["id"]+".json")),"content":__import__("json").dumps(profile),"mode":"0600"},"save profile",Operation("monitors.restore","monitors","RestoreBackup",{"path":str(ctx.paths.module_config("monitors")/"monitor-profiles"/(profile["id"]+".json"))},"undo",(),()),())
            ops=(record,)
        elif self.id=="monitors":
            first=Operation("monitors.0001","monitors","HyprctlReload",{"config_only":False},"reload",Operation("monitors.undo","monitors","HyprctlReload",{"config_only":False},"undo",(),()),())
            gate=Operation("monitors.0002","monitors","TimedConfirmation",{"seconds":30},"gate",Operation("monitors.gate","monitors","TimedConfirmation",{"seconds":30},"undo",(),()),())
            record=Operation("monitors.0003","monitors","WriteFileAtomic",{"path":"/tmp/record","content":"x","mode":"0600"},"record",Operation("monitors.restore","monitors","RestoreBackup",{"path":"/tmp/record"},"undo",(),()),())
            ops=(first,gate,record)
        else:
            ops=(Operation(f"{self.id}.0001",self.id,self.kind,{},self.id,Operation(f"{self.id}.undo",self.id,self.kind,{},"undo",(),()),()),)
        return Plan(self.id,status.revision,ops,(ResourceClaim(self.claim or "claim:"+self.id,"exclusive"),),self.id,(),())
    def verify(self,*args): return VerifyResult("pass","full","")
class Registry:
    def __init__(self,values): self.values=values
    def module(self,name): return self.values[name]
    def entry(self,name): return SimpleNamespace(metadata={"extraWritablePaths": []})
class Ctx(SimpleNamespace):
    def ctx_for(self,module_id,mode): return SimpleNamespace(module_id=module_id,cache=self.cache,paths=self.paths)

def statuses():
    return {
      "monitors":Status("monitors","r-mon",{"profiles":[{"id":"desk","profile":{"schemaVersion":1,"id":"desk"},"fit":{"state":"applicable"}}],"active":{"profileId":"desk","state":"verified"}},(),1),
      "themes":Status("themes","r-theme",{"themes":[{"slug":"night","wallpaperPaths":[]}],"active":{"slug":"night","background":None}},(),1),
      "plugins":Status("plugins","r-plug",{"rows":[{"id":"acme.service","kinds":["service"],"state":{"enabled":False,"canDisable":True}}]},(),1),
      "bar":Status("bar","r-bar",{"shell":{"available":True},"bar":{"id":None,"position":"top","transparent":False,"centerAnchor":"","extra":{},"layout":{"left":[],"center":[],"right":[]}}},(),1),
      "keybindings":Status("keybindings","r-key",{"model":{"schemaVersion":1,"bindings":[],"disabled":[]},"managedBlock":{"state":"absent","drift":False}},(),1),
      "defaults":Status("defaults","r-def",{"categories":[{"id":"browser","state":"ready","current":{"choice":"chromium"},"choices":[{"id":"firefox","state":"available"}]}]},(),1)}

def context(tmp_path, duplicate=False):
    values={name:Member(name,status,claim="same" if duplicate and name in {"themes","bar"} else None) for name,status in statuses().items()}
    paths=Paths(tmp_path,tmp_path/".config",tmp_path/"state",tmp_path/"cache",tmp_path/"runtime",tmp_path/"omarchy")
    return Ctx(registry=Registry(values),cache={},paths=paths,clock=Clock(),module_id="modes")

def mode(): return {"version":1,"id":"presentation","name":"Presentation","description":"","icon":"","members":{"monitors":{"profileId":"desk"},"themes":{"slug":"night"},"plugins":{"enabled":{"acme.service":True}},"bar":{"position":"bottom"},"keybindings":{"document":{"schemaVersion":1,"bindings":[],"disabled":[]}},"defaults":{"browser":"firefox"}},"triggers":[]}

def test_composition_order_segments_gate_and_last_record(modes_backend,tmp_path):
    compose=__import__("cc_modules.modes.compose",fromlist=["compose"]); ctx=context(tmp_path); status=Status("modes","r-modes",{},(),1)
    plan=compose.compose_apply(ctx,mode(),status)
    assert [segment.module_id for segment in plan.segments]==["monitors","themes","plugins","bar","keybindings","defaults","modes"]
    assert [op.module_id for op in plan.operations][:3]==["monitors"]*3
    gate=next(i for i,op in enumerate(plan.operations) if op.kind=="TimedConfirmation"); assert plan.operations[gate+1].module_id=="monitors" and plan.operations[gate+2].module_id=="themes"
    assert plan.operations[-1].module_id=="modes" and plan.operations[-1].summary.endswith("as last applied")
    record=__import__("json").loads(plan.operations[-1].params["content"])
    assert "compositionDigest" in record and "planDigest" not in record and "plannedAt" not in record


def test_identical_status_and_draft_produce_identical_composed_plan(modes_backend,tmp_path):
    compose=__import__("cc_modules.modes.compose",fromlist=["compose"]); status=Status("modes","r-modes",{},(),1)
    first=compose.compose_apply(context(tmp_path),mode(),status)
    second=compose.compose_apply(context(tmp_path),mode(),status)
    assert first.to_json()==second.to_json()
    assert Executor.digest(first)==Executor.digest(second)

def test_claim_conflict_is_rejected_before_execution(modes_backend,tmp_path):
    compose=__import__("cc_modules.modes.compose",fromlist=["compose"]); ctx=context(tmp_path,True); status=Status("modes","r-modes",{},(),1)
    with pytest.raises(CcError) as caught: compose.compose_apply(ctx,mode(),status)
    assert caught.value.code=="resource_conflict"

def test_import_plan_segments_are_an_exact_partition_accepted_by_executor(modes_backend,tmp_path):
    ctx=context(tmp_path); status=Status("modes","r-modes",{"modes":[]},(),1)
    imported={"bundleVersion":1,"mode":mode(),"artifacts":[],"externalReferences":[]}
    draft={"schemaVersion":1,"action":"import","import":{"bundle":imported,"resolutions":{}}}
    plan=modes_backend.MODULE.plan(ctx,draft,status)
    local_segment=next(segment for segment in plan.segments if segment.module_id=="modes")
    assert local_segment.operation_ids==tuple(operation.id for operation in plan.operations)
    executor=Executor(tmp_path,ctx.registry,ctx.paths,tmp_path/"backend/ccctl")
    executor._validate_plan(plan,())


@pytest.mark.parametrize("action,new_id,expected_reference,expects_artifact_write", [
    ("replace", None, "desk", True),
    ("reuse", None, "desk", False),
    ("rename", "projector", "projector", True),
])
def test_monitor_artifact_collision_resolution_keeps_or_rewrites_real_import_plan_reference(modes_backend,tmp_path,action,new_id,expected_reference,expects_artifact_write):
    store=__import__("cc_modules.modes.store",fromlist=["store"]); ctx=context(tmp_path)
    artifact_data={"schemaVersion":1,"id":"desk"}
    ctx.registry.values["monitors"]._status.data["profiles"][0]["profile"]=artifact_data
    imported_mode={"version":1,"id":"imported","name":"Imported","description":"","icon":"","members":{"monitors":{"profileId":"desk"}},"triggers":[]}
    artifact={"module":"monitors","kind":"monitor-profile","id":"desk","digest":store.digest(artifact_data),"data":artifact_data}
    bundle={"bundleVersion":1,"mode":imported_mode,"artifacts":[artifact],"externalReferences":[]}
    resolution={"action":action}
    if new_id is not None: resolution["id"]=new_id
    draft={"schemaVersion":1,"action":"import","import":{"bundle":bundle,"resolutions":{"artifacts":{"monitor-profile:desk":resolution}}}}
    status=Status("modes","r-modes",{"modes":[]},(),1)
    plan=modes_backend.MODULE.plan(ctx,draft,status)
    imported=__import__("json").loads(next(item.params["content"] for item in plan.operations if item.module_id=="modes" and item.kind=="WriteFileAtomic"))
    assert imported["members"]["monitors"]["profileId"]==expected_reference
    artifact_writes=[item for item in plan.operations if item.module_id=="monitors"]
    assert bool(artifact_writes) is expects_artifact_write
    if artifact_writes:
        saved=__import__("json").loads(artifact_writes[0].params["content"])
        assert saved["id"]==(new_id or "desk")


def test_renamed_monitor_artifact_reference_is_revalidated(modes_backend,tmp_path):
    store=__import__("cc_modules.modes.store",fromlist=["store"]); ctx=context(tmp_path)
    artifact_data={"schemaVersion":1,"id":"desk"}
    mode_value={"version":1,"id":"imported","name":"Imported","description":"","icon":"","members":{"monitors":{"profileId":"desk"}},"triggers":[]}
    bundle={"bundleVersion":1,"mode":mode_value,"artifacts":[{"module":"monitors","kind":"monitor-profile","id":"desk","digest":store.digest(artifact_data),"data":artifact_data}],"externalReferences":[]}
    draft={"schemaVersion":1,"action":"import","import":{"bundle":bundle,"resolutions":{"artifacts":{"monitor-profile:desk":{"action":"rename","id":"INVALID"}}}}}
    with pytest.raises(CcError) as caught:
        modes_backend.MODULE.plan(ctx,draft,Status("modes","r-modes",{"modes":[]},(),1))
    assert caught.value.code=="modes_section_invalid"


def test_nonreversible_and_import_runtime_plans_are_rejected(modes_backend):
    compose=__import__("cc_modules.modes.compose",fromlist=["compose"])
    op=Operation("themes.0001","themes","RunCommand",{"argv":["x"]},"x",None,())
    with pytest.raises(CcError) as caught: compose.check_composable("themes",Plan("themes","r",(op,),(),"",(),()))
    assert caught.value.code=="modes_nonreversible_member"
    reversible=Operation("monitors.0001","monitors","RunCommand",{"argv":["x"]},"x",Operation("monitors.undo","monitors","RunCommand",{},"",(),()),())
    with pytest.raises(CcError) as caught: compose.check_composable("monitors",Plan("monitors","r",(reversible,),(),"",(),()),imported=True)
    assert caught.value.code=="modes_import_runtime_op"
