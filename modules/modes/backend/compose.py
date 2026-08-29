from __future__ import annotations

import hashlib
import json
from typing import Any

from customization_center.core import CcError, Plan, PlanSegment, ResourceClaim, Warning, ops
from .members import ORDER
from .store import canonical, digest

RUNTIME_KINDS = {"RunCommand", "ShellIpc", "HyprctlReload", "TimedConfirmation", "TerminalHandoff"}


def _member_status(ctx: Any, module_id: str) -> Any:
    key = f"modes:status:{module_id}"
    if key not in ctx.cache:
        ctx.cache[key] = ctx.registry.module(module_id).status(ctx.ctx_for(module_id, "read"))
    return ctx.cache[key]


def _member_caps(ctx: Any, module_id: str) -> Any:
    key = f"modes:caps:{module_id}"
    if key not in ctx.cache:
        ctx.cache[key] = ctx.registry.module(module_id).capabilities(ctx.ctx_for(module_id, "read"))
    return ctx.cache[key]


def check_composable(member_id: str, plan: Plan, *, imported: bool = False) -> None:
    for operation in plan.operations:
        if operation.inverse is None or operation.kind == "TerminalHandoff":
            raise CcError("modes_nonreversible_member", f"{member_id} includes a non-reversible operation", {"operationId":operation.id})
        if imported and operation.kind in RUNTIME_KINDS:
            raise CcError("modes_import_runtime_op", "Imported artifacts may only create inert files", {"operationId":operation.id})
    gates = [index for index,item in enumerate(plan.operations) if item.kind == "TimedConfirmation"]
    if member_id != "monitors" and gates:
        raise CcError("modes_unexpected_confirmation", f"Only monitors may contain a confirmation gate")
    if member_id == "monitors" and plan.operations:
        reloads = [index for index,item in enumerate(plan.operations) if item.kind == "HyprctlReload"]
        if reloads and (not gates or gates[0] <= max(reloads)):
            # The gate follows the guarded reload. Monitor-owned guard cleanup and pointer writes may follow it.
            raise CcError("modes_monitor_gate_missing", "Monitor changes are not protected by a gate")
        if len(gates) > 1:
            raise CcError("modes_unexpected_confirmation", "Monitor plan contains more than one gate")
        if gates and any(item.kind not in {"WriteFileAtomic"} for item in plan.operations[gates[0]+1:]):
            raise CcError("modes_monitor_gate_not_last", "Only monitor record and guard writes may follow its gate")


def _check_claims(claims: list[ResourceClaim]) -> None:
    exclusive: dict[str,int] = {}
    for claim in claims:
        if claim.access == "exclusive": exclusive[claim.key] = exclusive.get(claim.key,0)+1
    conflict = next((key for key,count in exclusive.items() if count>1),None)
    if conflict: raise CcError("resource_conflict", f"Mode members claim {conflict} more than once", {"key":conflict})


def _empty_plugin_plan(status: Any) -> Plan:
    return Plan("plugins", status.revision, (), (), "Plugin states are already up to date", (), ())


def compose_apply(ctx: Any, mode: dict[str, Any], status: Any) -> Plan:
    operations=[]; claims=[]; warnings=[]; confirmations=[]; residual=[]; segments=[]; targets={}; summaries=[]
    before=[]
    for adapter in ORDER:
        section = mode["members"].get(adapter.module_id)
        if section is None: continue
        module=ctx.registry.module(adapter.module_id); member_status=_member_status(ctx,adapter.module_id); caps=_member_caps(ctx,adapter.module_id)
        adapter.validate_section(section,member_status,caps)
        member_draft=adapter.to_draft(section,member_status)
        if adapter.module_id == "plugins" and not member_draft["changes"]:
            member_plan=_empty_plugin_plan(member_status)
        else:
            validation=module.validate(ctx.ctx_for(adapter.module_id,"validate"),member_draft,member_status)
            if not validation.ok or validation.normalized_draft is None:
                raise CcError("modes_member_validation_failed", f"{adapter.module_id} rejected its mode section", {"member":adapter.module_id,"issues":[item.to_json() for item in validation.issues]})
            member_plan=module.plan(ctx.ctx_for(adapter.module_id,"plan"),validation.normalized_draft,member_status)
        check_composable(adapter.module_id,member_plan)
        operations.extend(member_plan.operations); claims.extend(member_plan.claims); warnings.extend(member_plan.warnings)
        confirmations.extend(member_plan.requires_confirmation); residual.extend(member_plan.residual_side_effects)
        segments.append(PlanSegment(adapter.module_id,member_status.revision,tuple(item.id for item in member_plan.operations)))
        targets[adapter.module_id]=adapter.target(section,member_status)
        before.append({"member":adapter.module_id,"revision":member_status.revision})
        summaries.append({"module":adapter.module_id,"fields":adapter.summarize(section),"operations":[item.summary for item in member_plan.operations]})
    _check_claims(claims)
    composition={"modeId":mode["id"],"modeDigest":digest(mode),"members":before,"targets":targets,
                 "operations":[item.to_json() for item in operations],"claims":[item.to_json() for item in claims]}
    composition_digest=digest(composition)
    record={"version":1,"modeId":mode["id"],"modeDigest":digest(mode),
            "compositionDigest":composition_digest,"targets":targets}
    path=ctx.paths.module_state("modes")/"last-applied.json"
    record_op=ops.WriteFileAtomic(ctx,path,canonical(record),"0600",f"Record {mode['name']} as last applied",
                                  detail={"modeId":mode["id"],"modeDigest":record["modeDigest"],"compositionDigest":composition_digest,"review":summaries})
    operations.append(record_op); claims.append(ResourceClaim(f"file:{path}","exclusive"))
    segments.append(PlanSegment("modes",status.revision,(record_op.id,)))
    return Plan("modes",status.revision,tuple(operations),tuple(claims),f"Apply desktop mode {mode['name']}",
                tuple(warnings),tuple(dict.fromkeys(confirmations)),tuple(dict.fromkeys(residual)),tuple(segments))


def import_artifacts(ctx: Any, parsed: dict[str,Any], status: Any, resolutions: dict[str,Any]) -> tuple[list[Any],list[ResourceClaim],list[PlanSegment]]:
    operations=[]; claims=[]; segments=[]
    artifact_resolutions=resolutions.get("artifacts",{}) if isinstance(resolutions,dict) else {}
    for artifact in parsed["artifacts"]:
        key=f"{artifact['kind']}:{artifact['id']}"; member_status=_member_status(ctx,artifact["module"])
        existing = next((item for item in member_status.data.get("profiles", []) if item.get("id") == artifact["id"]), None)
        resolution=artifact_resolutions.get(key)
        if existing is not None and not isinstance(resolution,dict):
            raise CcError("modes_import_unreviewed", f"Resolve the imported artifact collision for {key}")
        resolution = resolution or {"action":"replace"}
        action=resolution.get("action") if isinstance(resolution,dict) else resolution
        if action not in {"replace","rename","reuse"}: raise CcError("modes_import_unreviewed", f"Choose replace, rename, or reuse for {key}")
        if action=="reuse":
            if existing is None or digest(existing.get("profile")) != artifact["digest"]: raise CcError("modes_import_unreviewed", f"Reuse is allowed only for an identical artifact: {key}")
            continue
        data=json.loads(json.dumps(artifact["data"])); target_id=resolution.get("id") if isinstance(resolution,dict) and action=="rename" else artifact["id"]
        if target_id: data["id"]=target_id
        module=ctx.registry.module(artifact["module"])
        draft={"schemaVersion":1,"action":"save-profile","profile":data}
        validation=module.validate(ctx.ctx_for(artifact["module"],"validate"),draft,member_status)
        if not validation.ok or validation.normalized_draft is None: raise CcError("modes_member_validation_failed","Imported artifact was rejected",{"issues":[item.to_json() for item in validation.issues]})
        plan=module.plan(ctx.ctx_for(artifact["module"],"plan"),validation.normalized_draft,member_status); check_composable(artifact["module"],plan,imported=True)
        operations.extend(plan.operations); claims.extend(plan.claims); segments.append(PlanSegment(artifact["module"],member_status.revision,tuple(item.id for item in plan.operations)))
    return operations,claims,segments
