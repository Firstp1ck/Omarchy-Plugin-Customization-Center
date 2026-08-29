from __future__ import annotations

import json
import re
from typing import Any

from customization_center.core import ValidationIssue
from . import geometry

_PROFILE_KEYS = {"schemaVersion", "id", "name", "description", "outputs", "match", "extraOutputs", "createdAt", "updatedAt"}
_OUTPUT_KEYS = {"id", "label", "identity", "connectorPolicy", "enabled", "mode", "position", "scale120", "transform", "mirrorOf", "bitDepth", "vrr", "whenMissing"}
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_OUTPUT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_CONNECTOR = re.compile(r"^[A-Za-z0-9._-]+$")


def canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def validate_profile(value: Any, pointer: str = "/profile") -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    def issue(code: str, message: str, where: str) -> None:
        issues.append(ValidationIssue(code, message, where, "error"))
    if not isinstance(value, dict):
        return (ValidationIssue("validation_failed", "Profile must be an object", pointer, "error"),)
    unknown = set(value) - _PROFILE_KEYS
    for key in sorted(unknown): issue("validation_failed", f"Unknown profile field: {key}", f"{pointer}/{key}")
    if value.get("schemaVersion") != 1: issue("unsupported_config", "Profile file schemaVersion must be 1", f"{pointer}/schemaVersion")
    if not isinstance(value.get("id"), str) or not _ID.fullmatch(value["id"]): issue("validation_failed", "Profile id is invalid", f"{pointer}/id")
    if not isinstance(value.get("name"), str) or not 1 <= len(value["name"]) <= 80 or "\0" in value.get("name", ""): issue("validation_failed", "Profile name must contain 1 to 80 characters without NUL", f"{pointer}/name")
    if not isinstance(value.get("description", ""), str) or len(value.get("description", "")) > 500 or "\0" in value.get("description", ""): issue("validation_failed", "Profile description is invalid", f"{pointer}/description")
    for timestamp in ("createdAt", "updatedAt"):
        if not isinstance(value.get(timestamp), str) or not value[timestamp]: issue("validation_failed", f"{timestamp} is required", f"{pointer}/{timestamp}")
    match_rule = value.get("match")
    if not isinstance(match_rule, dict) or set(match_rule) != {"required", "allowExtra"} or not isinstance(match_rule.get("required"), list) or not isinstance(match_rule.get("allowExtra"), bool):
        issue("validation_failed", "Profile match policy is invalid", f"{pointer}/match")
    extra = value.get("extraOutputs")
    if extra is not None and (not isinstance(extra, dict) or set(extra) != {"mode", "position", "scale"} or extra.get("mode") not in {"preferred", "highres", "highrr", "maxwidth"} or extra.get("position") not in {"auto", "auto-right", "auto-left", "auto-up", "auto-down"} or not (extra.get("scale") == "auto" or isinstance(extra.get("scale"), int) and 30 <= extra["scale"] <= 960)):
        issue("validation_failed", "Extra-output catch-all is invalid", f"{pointer}/extraOutputs")
    outputs = value.get("outputs")
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 16:
        issue("validation_failed", "Profile must contain 1 to 16 outputs", f"{pointer}/outputs"); return tuple(issues)
    ids: set[str] = set()
    for index, output in enumerate(outputs):
        base = f"{pointer}/outputs/{index}"
        if not isinstance(output, dict): issue("validation_failed", "Output must be an object", base); continue
        for key in sorted(set(output) - _OUTPUT_KEYS): issue("validation_failed", f"Unknown output field: {key}", f"{base}/{key}")
        output_id = output.get("id")
        if not isinstance(output_id, str) or not _OUTPUT_ID.fullmatch(output_id): issue("validation_failed", "Output id is invalid", f"{base}/id")
        elif output_id in ids: issue("validation_failed", "Output ids must be unique", f"{base}/id")
        else: ids.add(output_id)
        identity = output.get("identity")
        if not isinstance(identity, dict) or set(identity) != {"description", "make", "model", "serial", "connector"}:
            issue("validation_failed", "Identity fields are incomplete", f"{base}/identity")
        elif not isinstance(identity.get("connector"), str) or not _CONNECTOR.fullmatch(identity["connector"]):
            issue("monitors_unsupported_output_name", "Connector contains unsupported characters", f"{base}/identity/connector")
        if output.get("connectorPolicy") not in {"never", "if-no-fingerprint", "confirm"}: issue("validation_failed", "Connector policy is invalid", f"{base}/connectorPolicy")
        if not isinstance(output.get("enabled"), bool): issue("validation_failed", "enabled must be boolean", f"{base}/enabled")
        if output.get("whenMissing") not in {"block", "skip"}: issue("validation_failed", "whenMissing is invalid", f"{base}/whenMissing")
        if not isinstance(output.get("transform"), int) or not 0 <= output["transform"] <= 7: issue("validation_failed", "Transform must be 0 through 7", f"{base}/transform")
        if not isinstance(output.get("scale120"), int) or not 30 <= output["scale120"] <= 960: issue("validation_failed", "scale120 must be 30 through 960", f"{base}/scale120")
        mode = output.get("mode")
        if not isinstance(mode, dict) or set(mode) != {"width", "height", "refreshMilliHz"} or any(not isinstance(mode.get(k), int) or mode[k] <= 0 for k in mode): issue("validation_failed", "Exact mode is invalid", f"{base}/mode")
        position = output.get("position")
        if not isinstance(position, dict) or set(position) != {"x", "y"} or any(not isinstance(position.get(k), int) for k in ("x", "y")): issue("validation_failed", "Position is invalid", f"{base}/position")
        if output.get("bitDepth") not in {None, 8, 10}: issue("validation_failed", "Bit depth must be 8, 10, or null", f"{base}/bitDepth")
        if output.get("vrr") not in {None, 0, 1, 2, 3}: issue("validation_failed", "VRR must be 0 through 3 or null", f"{base}/vrr")
    by_id = {item.get("id"): item for item in outputs if isinstance(item, dict)}
    if isinstance(match_rule, dict) and isinstance(match_rule.get("required"), list):
        for index, required_id in enumerate(match_rule["required"]):
            if not isinstance(required_id, str) or required_id not in by_id:
                issue("validation_failed", "match.required must reference an output id", f"{pointer}/match/required/{index}")
    for index, output in enumerate(outputs):
        if not isinstance(output, dict): continue
        target = output.get("mirrorOf")
        if target is not None and (target == output.get("id") or target not in by_id or not by_id[target].get("enabled") or by_id[target].get("mirrorOf")):
            issue("monitors_mirror_invalid", "Mirror target must be a different enabled root output", f"{pointer}/outputs/{index}/mirrorOf")
    for output in outputs:
        seen: set[str] = set(); current = output
        while isinstance(current, dict) and current.get("mirrorOf"):
            if current["id"] in seen: issue("monitors_mirror_invalid", "Mirror graph contains a cycle", pointer + "/outputs"); break
            seen.add(current["id"]); current = by_id.get(current["mirrorOf"])
    roots = []
    for index, output in enumerate(outputs):
        if isinstance(output, dict) and output.get("enabled") and not output.get("mirrorOf"):
            try: roots.append(geometry.logical(output))
            except (ValueError, KeyError) as error: issue("monitors_invalid_scale", str(error), f"{pointer}/outputs/{index}/scale120")
    if not roots: issue("monitors_no_root", "At least one enabled non-mirrored output is required", f"{pointer}/outputs")
    for first in range(len(roots)):
        for second in range(first + 1, len(roots)):
            if geometry.overlaps(roots[first], roots[second]): issue("monitors_overlap", f"Outputs {roots[first]['id']} and {roots[second]['id']} overlap", f"{pointer}/outputs")
    return tuple(issues)
