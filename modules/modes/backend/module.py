from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from customization_center.core import (Capabilities, Capability, CcError, Plan, PlanSegment, ResourceClaim,
    Status, ValidationIssue, ValidationResult, VerifyResult, Warning, ops)
from . import bundle, capture, compose, drift, shortcut, store
from .members import ORDER

ACTIONS={"save","delete","apply","import","export"}
OUTPUT_PATTERN=re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}\.json$")


def _valid_iso_timestamp(value:Any)->bool:
    if not isinstance(value,str) or not 1<=len(value)<=64: return False
    try: parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _envelope_issues(draft: Any) -> list[ValidationIssue]:
    if not isinstance(draft,dict): return [ValidationIssue("validation_failed","Draft must be an object","","error")]
    issues=[]; allowed={"schemaVersion","action","mode","import","export","expected","_planContext"}
    for key in sorted(set(draft)-allowed): issues.append(ValidationIssue("validation_failed",f"Unknown draft field: {key}",f"/{key}","error"))
    if draft.get("schemaVersion")!=1: issues.append(ValidationIssue("modes_unsupported_version","Draft schemaVersion must be 1","/schemaVersion","error"))
    if draft.get("action") not in ACTIONS: issues.append(ValidationIssue("validation_failed","Unknown modes action","/action","error"))
    return issues


def _read_last(ctx: Any) -> tuple[dict[str,Any]|None,list[Warning]]:
    path=ctx.paths.module_state("modes")/"last-applied.json"
    if not path.is_file(): return None,[]
    try:
        raw=ctx.paths.read_regular(path,1024*1024); value=json.loads(raw)
        if not isinstance(value,dict) or value.get("version")!=1 or not isinstance(value.get("targets"),dict): raise ValueError("invalid last-applied shape")
        return value,[]
    except FileNotFoundError: return None,[]
    except Exception as error: return None,[Warning("modes_last_applied_invalid",f"Last-applied record is unreadable: {error}",str(path),"Restore it from transaction history or remove it")]


class ModesModule:
    id="modes"; schema_version=1

    def capabilities(self,ctx:Any)->Capabilities:
        items=[Capability("registry",True,""),ctx.capabilities.get("timed_confirmation"),Capability("staging",True,"")]
        for adapter in ORDER:
            try:
                caps=ctx.registry.module(adapter.module_id).capabilities(ctx.ctx_for(adapter.module_id,"read"))
                available=all(item.available for item in caps.items if item.name in {"shell_ipc","activate","hyprctl","timed_confirmation","monitor_inventory","hyprland_session"})
                reason="; ".join(item.reason for item in caps.items if not item.available and item.reason)
            except Exception as error: available=False; reason=str(error)
            items.append(Capability("member:"+adapter.module_id,available,reason))
        return Capabilities(self.id,tuple(items),ctx.clock.now_iso())

    def status(self,ctx:Any)->Status:
        rows,unreadable=store.load_modes(ctx); last,last_warnings=_read_last(ctx); member_revisions={}; warnings=list(last_warnings)
        for adapter in ORDER:
            try:
                member_status=ctx.registry.module(adapter.module_id).status(ctx.ctx_for(adapter.module_id,"read"))
                ctx.cache[f"modes:status:{adapter.module_id}"]=member_status; member_revisions[adapter.module_id]=member_status.revision
            except Exception as error:
                member_revisions[adapter.module_id]="unavailable:"+type(error).__name__
                warnings.append(Warning("modes_member_unavailable",f"{adapter.module_id} status is unavailable: {error}",recovery=f"Open {adapter.module_id} and resolve its status error"))
        by_id={item["mode"]["id"]:item for item in rows}; drift_report=drift.report(ctx,last,by_id.get(last.get("modeId"),{}).get("mode") if last else None) if last else None
        cards=[]
        for item in rows:
            mode=item["mode"]; state="never-applied"; definition=False; report=None
            if drift_report and drift_report.get("modeId")==mode["id"]: state=drift_report["state"]; definition=drift_report["definitionChanged"]; report=drift_report
            cards.append({**item,"state":state,"definitionChanged":definition,"drift":report,"summaries":sum((adapter.summarize(mode["members"][adapter.module_id]) for adapter in ORDER if adapter.module_id in mode["members"]),[])})
        revision=ctx.revision_of({"modes":{item["mode"]["id"]:item["digest"] for item in rows},"lastApplied":store.digest(last) if last else None,"members":member_revisions})
        data={"schemaVersion":1,"modes":cards,"unreadable":unreadable,"lastApplied":drift_report,"memberRevisions":member_revisions,
              "memberCapabilities":{item.name.removeprefix("member:"):{"available":item.available,"reason":item.reason} for item in self.capabilities(ctx).items if item.name.startswith("member:")}}
        return Status(self.id,revision,data,tuple(warnings),1)

    def validate(self,ctx:Any,draft:dict[str,Any],status:Status)->ValidationResult:
        issues=_envelope_issues(draft); normalized=json.loads(json.dumps(draft)) if isinstance(draft,dict) else None; details={}
        action=draft.get("action") if isinstance(draft,dict) else None
        if action in {"save","apply","export"}:
            mode_issues,mode=store.validate_mode(draft.get("mode")); issues.extend(mode_issues)
            if normalized is not None and mode is not None: normalized["mode"]=mode
        elif action=="delete":
            mode=draft.get("mode")
            if not isinstance(mode,dict) or not isinstance(mode.get("id"),str) or not store.ID_PATTERN.fullmatch(mode["id"]): issues.append(ValidationIssue("modes_invalid_id","Delete requires a valid mode id","/mode/id","error"))
            elif normalized is not None: normalized["mode"]={"id":mode["id"]}
        elif action=="import":
            try:
                raw=draft.get("import")
                if not isinstance(raw,dict): raise CcError("validation_failed","import must be an object")
                parsed=bundle.check(raw.get("bundle")); details=bundle.review(parsed,{item["mode"]["id"]:item["digest"] for item in status.data.get("modes",[])})
                for artifact in parsed["artifacts"]:
                    module=ctx.registry.module(artifact["module"]); member_status=module.status(ctx.ctx_for(artifact["module"],"read"))
                    validation=module.validate(ctx.ctx_for(artifact["module"],"validate"),{"schemaVersion":1,"action":"save-profile","profile":artifact["data"]},member_status)
                    if not validation.ok: issues.append(ValidationIssue("modes_member_validation_failed","Imported artifact was rejected","/import/bundle/artifacts","error"))
                if normalized is not None: normalized["import"]={"bundle":parsed["bundle"],"resolutions":raw.get("resolutions",{})}
            except CcError as error: issues.append(ValidationIssue(error.code,error.message,"/import/bundle","error"))
        if action=="export":
            output=(draft.get("export") or {}).get("outputName") if isinstance(draft.get("export"),dict) else None
            if not isinstance(output,str) or not OUTPUT_PATTERN.fullmatch(output) or ".." in output: issues.append(ValidationIssue("modes_invalid_id","Export outputName must be a safe .json file name","/export/outputName","error"))
            plan_context=draft.get("_planContext")
            if plan_context is None: plan_context={"exportedAt":ctx.clock.now_iso()}
            valid_context=(isinstance(plan_context,dict) and set(plan_context)=={"exportedAt"} and
                           _valid_iso_timestamp(plan_context.get("exportedAt")))
            if not valid_context: issues.append(ValidationIssue("validation_failed","Invalid internal mode plan context","/_planContext","error"))
            elif normalized is not None: normalized["_planContext"]=dict(plan_context)
        elif isinstance(draft,dict) and "_planContext" in draft:
            issues.append(ValidationIssue("validation_failed","Internal mode plan context is only valid for export","/_planContext","error"))
        errors=any(item.severity=="error" for item in issues)
        return ValidationResult(not errors,tuple(issues),None if errors else normalized,details)

    def _stored_digest(self,status:Status,mode_id:str)->str|None:
        row=next((item for item in status.data.get("modes",[]) if item.get("mode",{}).get("id")==mode_id),None)
        return row.get("digest") if row else None

    def plan(self,ctx:Any,draft:dict[str,Any],status:Status)->Plan:
        action=draft["action"]
        if action=="apply": return compose.compose_apply(ctx,draft["mode"],status)
        if action in {"save","delete"}:
            mode_id=draft["mode"]["id"]; target=store.mode_path(ctx,mode_id); expected=(draft.get("expected") or {}).get("modeDigest")
            if expected != self._stored_digest(status,mode_id): raise CcError("stale_revision","Mode definition changed since editing",{"expectedDigest":expected,"currentDigest":self._stored_digest(status,mode_id)})
            if action=="save": operations=(ops.EnsureDirectory(ctx,target.parent,"0700","Ensure desktop modes directory"),ops.WriteFileAtomic(ctx,target,store.canonical(draft["mode"]),"0600",f"Save desktop mode {mode_id}")); warnings=(); confirmations=()
            else:
                operations=(ops.RemoveFile(ctx,target,f"Delete desktop mode {mode_id}"),); warning=Warning(f"modes_delete:{mode_id}",f"Delete desktop mode {mode_id}",str(target),"Confirm the named mode; rollback restores it",True); warnings=(warning,); confirmations=(warning.code,)
            return Plan(self.id,status.revision,operations,(ResourceClaim(f"file:{target}","exclusive"),),f"{action.title()} desktop mode {mode_id}",warnings,confirmations)
        if action=="export":
            mode=draft["mode"]; artifacts=[]; references=[]
            for adapter in ORDER:
                section=mode["members"].get(adapter.module_id)
                if section is None: continue
                references.extend(adapter.external_references(section))
                if adapter.module_id=="monitors":
                    member=ctx.registry.module("monitors"); member_status=member.status(ctx.ctx_for("monitors","read")); row=next((item for item in member_status.data.get("profiles",[]) if item.get("id")==section["profileId"]),None)
                    if row:
                        data=json.loads(json.dumps(row["profile"])); machine=not all(item.get("identity",{}).get("description") for item in data.get("outputs",[]))
                        if not machine:
                            for item in data.get("outputs",[]): item.get("identity",{}).pop("connectorFallback",None)
                        artifacts.append({"module":"monitors","kind":"monitor-profile","id":data["id"],"digest":store.digest(data),"data":data,"machineSpecific":machine})
            document={"bundleVersion":1,"exportedBy":{"application":"firstpick.customization-center","version":"0.1.0"},"exportedAt":draft["_planContext"]["exportedAt"],"mode":mode,"artifacts":artifacts,"externalReferences":references}
            target=ctx.paths.exports/draft["export"]["outputName"]; operations=(ops.EnsureDirectory(ctx,target.parent,"0700","Ensure export directory"),ops.WriteFileAtomic(ctx,target,store.canonical(document),"0600",f"Export desktop mode {mode['id']}"))
            return Plan(self.id,status.revision,operations,(ResourceClaim(f"file:{target}","exclusive"),),f"Export desktop mode {mode['id']}",(),())
        if action=="import":
            parsed=bundle.check(draft["import"]["bundle"]); resolutions=draft["import"].get("resolutions",{}); command_rows=bundle.commands(parsed["mode"])
            if command_rows and resolutions.get("commandsReviewed") is not True: raise CcError("modes_import_unreviewed","Review every imported keybinding command before committing")
            current_mode=self._stored_digest(status,parsed["mode"]["id"]); mode_resolution=resolutions.get("mode",{})
            if current_mode is not None and not isinstance(mode_resolution,dict): raise CcError("modes_import_unreviewed","Resolve the imported mode id collision")
            if current_mode is not None and mode_resolution.get("action") not in {"replace","rename","reuse"}: raise CcError("modes_import_unreviewed","Choose replace, rename, or reuse for the imported mode")
            if current_mode is not None and mode_resolution.get("action")=="reuse" and current_mode!=store.digest(parsed["mode"]): raise CcError("modes_import_unreviewed","Reuse is allowed only for an identical mode")
            operations,claims,segments=compose.import_artifacts(ctx,parsed,status,resolutions)
            mode=json.loads(json.dumps(parsed["mode"])); mode_resolution=resolutions.get("mode",{})
            if isinstance(mode_resolution,dict) and mode_resolution.get("action")=="rename": mode["id"]=mode_resolution.get("id",mode["id"]); mode["name"]=mode_resolution.get("name",mode["name"])
            artifact_resolutions=resolutions.get("artifacts",{}) if isinstance(resolutions,dict) else {}
            for artifact in parsed["artifacts"]:
                key=f"{artifact['kind']}:{artifact['id']}"; resolution=artifact_resolutions.get(key,{})
                if artifact["module"]=="monitors" and artifact["kind"]=="monitor-profile" and isinstance(resolution,dict) and resolution.get("action")=="rename":
                    store.rewrite_monitor_profile_reference(mode,artifact["id"],resolution.get("id",artifact["id"]))
            mode_issues,normalized_mode=store.validate_mode(mode)
            if mode_issues or normalized_mode is None: raise CcError(mode_issues[0].code,mode_issues[0].message,{"issues":[item.to_json() for item in mode_issues]})
            mode=normalized_mode
            target=store.mode_path(ctx,mode["id"]); local_operations=(ops.EnsureDirectory(ctx,target.parent,"0700","Ensure desktop modes directory"),ops.WriteFileAtomic(ctx,target,store.canonical(mode),"0600",f"Import desktop mode {mode['id']}")); operations.extend(local_operations); claims.append(ResourceClaim(f"file:{target}","exclusive")); segments.append(PlanSegment("modes",status.revision,tuple(item.id for item in local_operations)))
            compose._check_claims(claims)
            return Plan(self.id,status.revision,tuple(operations),tuple(claims),f"Import desktop mode {mode['id']} as an inert draft",(),(),(),tuple(segments))
        raise CcError("validation_failed","Unsupported modes action")

    def verify(self,ctx:Any,plan:Plan,status_after:Status,results:dict[str,Any])->VerifyResult:
        own=[item for item in plan.operations if item.module_id=="modes"]
        record_op=next((item for item in own if item.summary.startswith("Record ") and item.summary.endswith(" as last applied")),None)
        if record_op:
            try: expected=json.loads(record_op.params["content"]); actual=ctx.paths.read_json(record_op.params["path"])
            except Exception as error: return VerifyResult("fail","full",f"Last-applied record is unreadable: {error}","modes_verification_failed")
            if actual!=expected: return VerifyResult("fail","full","Last-applied record differs from the reviewed target","modes_verification_failed")
            report=status_after.data.get("lastApplied")
            if not report or report.get("state")!="applied" or report.get("definitionChanged"):
                return VerifyResult("fail","full","Mode members did not match immediately after apply","modes_verification_failed",{"drift":report})
        return VerifyResult("pass","full","",evidence={"revision":status_after.revision})

    def query(self,ctx:Any,name:str,args:dict[str,Any])->dict[str,Any]:
        if name=="captureable": return capture.captureable(ctx,args.get("selections") if isinstance(args,dict) else None)
        if name=="drift": return {"schemaVersion":1,"lastApplied":self.status(ctx).data.get("lastApplied")}
        if name=="shortcut":
            mode_id=str(args.get("modeId","")); mode=next((item["mode"] for item in self.status(ctx).data.get("modes",[]) if item["mode"]["id"]==mode_id),None)
            if mode is None: raise CcError("modes_invalid_id",f"Unknown mode: {mode_id}")
            return {"schemaVersion":1,"command":shortcut.command(mode_id),"keybindingPayload":shortcut.keybinding(mode,args.get("chord")),"menuPayload":shortcut.menu(mode)}
        raise CcError("unknown_query",f"Unknown modes query: {name}")

MODULE=ModesModule()
