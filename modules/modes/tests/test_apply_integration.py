from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from customization_center.core import (Capabilities, Capability, CcError, Plan, ResourceClaim, Status,
    ValidationResult, VerifyResult, ops)
from customization_center.core.executor import Executor
from customization_center.core.paths import Paths

class ThemeMember:
    id="themes"; schema_version=1
    def capabilities(self,ctx): return Capabilities(self.id,(Capability("activate",True,""),),ctx.clock.now_iso())
    def _path(self,ctx): return ctx.paths.module_state("themes")/"active.txt"
    def status(self,ctx):
        try: active=self._path(ctx).read_text().strip()
        except FileNotFoundError: active="day"
        return Status(self.id,ctx.revision_of(active),{"themes":[{"slug":"day","wallpaperPaths":[]},{"slug":"night","wallpaperPaths":[]}],"active":{"slug":active,"background":None}},(),1)
    def validate(self,ctx,draft,status): return ValidationResult(True,(),draft)
    def plan(self,ctx,draft,status):
        path=self._path(ctx); operation=ops.WriteFileAtomic(ctx,path,draft["slug"]+"\n","0600","Activate fake theme")
        return Plan(self.id,status.revision,(operation,),(ResourceClaim("theme.current","exclusive"),),"Activate fake theme",(),())
    def verify(self,ctx,plan,status_after,results):
        return VerifyResult("pass","full","") if status_after.data["active"]["slug"]=="night" else VerifyResult("fail","full","theme mismatch")

class PassiveMember:
    schema_version=1
    def __init__(self,module_id,data): self.id=module_id; self.data=data
    def capabilities(self,ctx): return Capabilities(self.id,(),ctx.clock.now_iso())
    def status(self,ctx): return Status(self.id,ctx.revision_of(self.data),self.data,(),1)
    def validate(self,ctx,draft,status): return ValidationResult(True,(),draft)
    def plan(self,ctx,draft,status): return Plan(self.id,status.revision,(),(),"No change",(),())
    def verify(self,*args): return VerifyResult("pass","full","")

@dataclass
class Entry:
    id:str; module:object; metadata:dict; directory:Path
class Registry:
    def __init__(self,entries): self.entries=entries; self.view=self
    def module(self,module_id): return self.entries[module_id].module
    def entry(self,module_id): return self.entries[module_id]
    def __iter__(self): return iter(self.entries.values())

def registry(modes_backend,tmp_path):
    modules={
      "modes":modes_backend.MODULE,"themes":ThemeMember(),
      "monitors":PassiveMember("monitors",{"profiles":[],"active":{"profileId":None,"state":"none"}}),
      "plugins":PassiveMember("plugins",{"rows":[]}),
      "bar":PassiveMember("bar",{"shell":{"available":True},"bar":{"layout":{"left":[],"center":[],"right":[]}}}),
      "keybindings":PassiveMember("keybindings",{"model":{"schemaVersion":1,"bindings":[],"disabled":[]},"managedBlock":{"state":"absent","drift":False}}),
      "defaults":PassiveMember("defaults",{"categories":[]})}
    entries={name:Entry(name,module,{"extraWritablePaths":[],"draftSchema":"schemas/draft-v1.json"},
                              Path(__file__).resolve().parents[1] if name=="modes" else tmp_path/name)
             for name,module in modules.items()}
    return Registry(entries)

def setup(tmp_path,modes_backend,monkeypatch):
    home=tmp_path/"home"; paths=Paths(home,home/".config",home/"state",home/"cache",home/"runtime",tmp_path/"omarchy")
    for path in (home,paths.xdg_config_home,paths.state,paths.cache,paths.runtime,paths.omarchy_path): path.mkdir(parents=True,exist_ok=True)
    mode={"version":1,"id":"night","name":"Night","description":"","icon":"","members":{"themes":{"slug":"night"}},"triggers":[]}
    directory=paths.xdg_config_home/"omarchy/customization-center/desktop-modes"; directory.mkdir(parents=True); (directory/"night.json").write_text(json.dumps(mode))
    reg=registry(modes_backend,tmp_path); executor=Executor(tmp_path,reg,paths,tmp_path/"ccctl",environ={"HOME":str(home),"XDG_CONFIG_HOME":str(paths.xdg_config_home),"XDG_STATE_HOME":str(home/".local/state"),"XDG_CACHE_HOME":str(home/".cache"),"XDG_RUNTIME_DIR":str(home/"runtime"),"OMARCHY_PATH":str(paths.omarchy_path),"PATH":"/usr/bin"})
    draft={"schemaVersion":1,"action":"apply","mode":mode,"import":None,"export":None,"expected":{"modeDigest":None}}
    status=modes_backend.MODULE.status(executor._ctx("modes","read")); return executor,paths,draft,status

def test_real_executor_commits_composed_mode_and_record(modes_backend,tmp_path,monkeypatch):
    executor,paths,draft,status=setup(tmp_path,modes_backend,monkeypatch)
    tx=executor.apply("modes",draft,status.revision)
    assert tx.state=="committed" and [segment.module_id for segment in tx.plan.segments]==["themes","modes"]
    assert (paths.module_state("themes")/"active.txt").read_text().strip()=="night"
    assert json.loads((paths.module_state("modes")/"last-applied.json").read_text())["modeId"]=="night"

def test_fault_before_last_record_rolls_member_back(modes_backend,tmp_path,monkeypatch):
    executor,paths,draft,status=setup(tmp_path,modes_backend,monkeypatch)
    fault=paths.home/"fault.json"; fault.write_text(json.dumps({"hooks":["before_op:modes.0001"]}))
    executor.environ={**executor.environ,"CC_TEST_FAULTS":str(fault)}
    monkeypatch.setenv("CC_TEST_FAULTS",str(fault)); executor.faults=executor.faults.from_environment(paths)
    with pytest.raises(CcError) as caught: executor.apply("modes",draft,status.revision)
    assert caught.value.data["state"]=="rolled_back"
    assert not (paths.module_state("themes")/"active.txt").exists()
    assert not (paths.module_state("modes")/"last-applied.json").exists()
