from __future__ import annotations

import json
from typing import Any
from customization_center.core import CcError, ValidationIssue
from .store import digest, validate_mode

MAX_BYTES=1024*1024; MAX_DEPTH=12; MAX_ARRAY=10000; MAX_STRING=65536; MAX_ARTIFACTS=16

def _walk(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH: raise CcError("modes_import_limit", "Bundle nesting exceeds 12 levels")
    if isinstance(value, str) and len(value.encode("utf-8")) > MAX_STRING: raise CcError("modes_import_limit", "Bundle string exceeds 65536 bytes")
    if isinstance(value, list):
        if len(value) > MAX_ARRAY: raise CcError("modes_import_limit", "Bundle array exceeds 10000 items")
        for item in value: _walk(item, depth+1)
    elif isinstance(value, dict):
        for key,item in value.items(): _walk(key, depth+1); _walk(item, depth+1)

def check(bundle: Any) -> dict[str, Any]:
    try: size=len(json.dumps(bundle,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode())
    except (TypeError,ValueError) as error: raise CcError("modes_import_limit", "Bundle is not bounded JSON") from error
    if size>MAX_BYTES: raise CcError("modes_import_limit", "Bundle exceeds 1 MiB")
    _walk(bundle)
    if not isinstance(bundle,dict) or bundle.get("bundleVersion")!=1: raise CcError("modes_unsupported_version", "Bundle version must be 1")
    if set(bundle)-{"bundleVersion","exportedBy","exportedAt","mode","artifacts","externalReferences"}: raise CcError("validation_failed", "Bundle contains unknown fields")
    artifacts=bundle.get("artifacts",[]); references=bundle.get("externalReferences",[])
    if not isinstance(artifacts,list) or len(artifacts)>MAX_ARTIFACTS: raise CcError("modes_import_limit", "Bundle has too many artifacts")
    if not isinstance(references,list): raise CcError("validation_failed", "externalReferences must be an array")
    issues,mode=validate_mode(bundle.get("mode"),"/import/bundle/mode")
    if issues or mode is None: raise CcError(issues[0].code,issues[0].message,{"issues":[item.to_json() for item in issues]})
    seen=set()
    for artifact in artifacts:
        if not isinstance(artifact,dict) or artifact.get("module")!="monitors" or artifact.get("kind")!="monitor-profile" or not isinstance(artifact.get("id"),str) or not isinstance(artifact.get("data"),dict):
            raise CcError("validation_failed", "Only monitor-profile artifacts are supported")
        key=(artifact["module"],artifact["kind"],artifact["id"])
        if key in seen: raise CcError("validation_failed", "Bundle contains a duplicate artifact")
        seen.add(key)
        if artifact.get("digest") != digest(artifact["data"]): raise CcError("validation_failed", "Artifact digest does not match its data")
    return {"bundle":bundle,"mode":mode,"artifacts":artifacts,"externalReferences":references,"size":size}

def commands(mode: dict[str,Any]) -> list[dict[str,Any]]:
    result=[]
    for index,item in enumerate(mode.get("members",{}).get("keybindings",{}).get("document",{}).get("bindings",[])):
        action=item.get("action",{}) if isinstance(item,dict) else {}
        if action.get("type")=="exec" and isinstance(action.get("command"),str): result.append({"source":f"keybindings.bindings[{index}]","chord":item.get("chord"),"command":action["command"]})
    return result

def review(parsed: dict[str,Any], existing: dict[str,str]) -> dict[str,Any]:
    mode=parsed["mode"]; command_rows=commands(mode)
    return {"mode":{"id":mode["id"],"collision":"exists" if mode["id"] in existing else "none"},
        "artifacts":[{"kind":item["kind"],"id":item["id"],"collision":"unknown","machineSpecific":item.get("machineSpecific",False)} for item in parsed["artifacts"]],
        "externalReferences":parsed["externalReferences"],"commands":command_rows,
        "machineSpecific":[f"{item['kind']}:{item['id']}" for item in parsed["artifacts"] if item.get("machineSpecific")],"sizeBytes":parsed["size"]}
