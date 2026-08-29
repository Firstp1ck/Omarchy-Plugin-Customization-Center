from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from customization_center.core import (CcError, Plan, ResourceClaim, Status, ValidationIssue, ValidationResult,
                                       VerifyResult, Warning, managed_block, ops)
from .catalog import load_default_catalog
from .chords import ChordError, from_model, normalize
from .classify import classify
from .conflicts import classify_conflicts
from .inventory import parse_devices, parse_plain, reconcile_json
from .keymap import keymap_from_context
from .luacheck import capability as luac_capability, check_candidate
from .model import canonical_json, empty_model, validate_draft
from .render import render_body


def bindings_path(ctx: Any) -> Path:
    return ctx.paths.home / ".config/hypr/bindings.lua"


def model_path(ctx: Any) -> Path:
    return ctx.paths.xdg_config_home / "omarchy/customization-center/keybindings.json"


def _read_bytes(path: Path) -> bytes:
    try: return path.read_bytes()
    except FileNotFoundError: return b""


def _option_bool(text: str) -> bool:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return False
    if isinstance(value, dict):
        raw = value.get("int", value.get("value", False))
        return raw is True or raw == 1 or str(raw).lower() == "true"
    return value is True or value == 1


def _run(ctx: Any, argv: list[str], limit: int) -> tuple[str, str]:
    result = ctx.commands.run(argv, timeout_s=5, env_extra={"LC_ALL": "C"}, capture_limit=limit)
    if result.timed_out: return "", "timeout"
    if result.exit_code != 0: return "", result.stderr.strip() or "command failed"
    if result.truncated: return result.stdout, "truncated"
    return result.stdout, ""


def build_status(ctx: Any, capability_data: dict[str, Any]) -> Status:
    warnings: list[Warning] = []
    plain = json_text = devices_text = version = resolve_text = ""
    if capability_data["hyprctl"]["available"]:
        plain, error = _run(ctx, ["hyprctl", "binds"], 4 * 1024 * 1024)
        if error:
            warnings.append(Warning("keybindings_binds_unparseable", "Cannot read hyprctl binds: " + error, recovery="Start Hyprland and retry"))
        json_text, json_error = _run(ctx, ["hyprctl", "-j", "binds"], 8 * 1024 * 1024)
        devices_text, devices_error = _run(ctx, ["hyprctl", "-j", "devices"], 1024 * 1024)
        version, _ = _run(ctx, ["hyprctl", "version"], 65536)
        resolve_text, _ = _run(ctx, ["hyprctl", "-j", "getoption", "input.resolve_binds_by_sym"], 4096)
        if json_error: json_text = ""
        if devices_error: devices_text = "{}"
    records, parser_warnings = parse_plain(plain)
    for item in parser_warnings:
        warnings.append(Warning(item["code"], item["message"], recovery="Inspect the raw hyprctl binds output"))
    if json_text:
        records, json_warning = reconcile_json(records, json_text)
        if json_warning: warnings.append(Warning(json_warning["code"], json_warning["message"], recovery="Plain inventory remains available"))
    devices = parse_devices(devices_text or "{}")
    resolve_binds_by_sym = _option_bool(resolve_text)
    code_to_keysym = keymap_from_context(ctx, devices["keyboard"])
    if devices["warning"]:
        warnings.append(Warning("keybindings_layout_dependent", devices["warning"], recovery="Review bindings on every keyboard layout"))
    if not code_to_keysym:
        warnings.append(Warning("keybindings_keymap_unavailable", "The active keycode map is unavailable", recovery="Install xkbcli to classify physical-key aliases"))
    catalog, catalog_digest, catalog_error = load_default_catalog(ctx)
    if catalog_error:
        warnings.append(Warning("keybindings_catalog_unavailable", catalog_error, recovery="Install lua or repair the package-owned Omarchy binding files"))
    if not catalog:
        warnings.append(Warning("keybindings_catalog_unavailable", "Omarchy default binding catalog is unavailable", recovery="Set OMARCHY_PATH to the installed Omarchy tree"))
    stored_path = model_path(ctx)
    raw_model = _read_bytes(stored_path)
    unsupported_model = False
    try:
        model = json.loads(raw_model) if raw_model else empty_model()
        if not isinstance(model, dict) or model.get("schemaVersion") != 1:
            raise ValueError("unsupported schemaVersion")
        stored_issues, _, _ = validate_draft({"schemaVersion": 1, "expectedRevision": "", "model": model})
        if stored_issues: raise ValueError(stored_issues[0].message)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        unsupported_model = True
        model = empty_model()
        warnings.append(Warning("keybindings_managed_drift", "keybindings.json is unsupported: " + str(error), str(stored_path), "Restore it from a transaction backup or remove it"))
    lua_path = bindings_path(ctx)
    lua_bytes = _read_bytes(lua_path)
    inspected = managed_block.inspect(lua_bytes, "BINDINGS", 1)
    expected_body = render_body(model)
    drift = False
    if inspected["state"] == "present":
        try:
            drift = bool(raw_model) and managed_block.extract(lua_bytes, "BINDINGS", 1) != expected_body
        except CcError:
            drift = True
    elif inspected["state"] == "absent":
        drift = expected_body is not None
    else:
        warnings.append(Warning("keybindings_markers_ambiguous", "bindings.lua managed markers are ambiguous", str(lua_path), "Fix the marker lines by hand before applying"))
    inspected = {**inspected, "drift": drift}
    if drift:
        warnings.append(Warning("keybindings_managed_drift", "The managed block differs from keybindings.json", str(lua_path), "Rewrite the block from the stored model or restore a backup"))
    records, disabled_defaults, orphaned = classify(records, model, catalog)
    luac = luac_capability(ctx)
    edit_reasons = []
    if not capability_data["hyprctl"]["available"]: edit_reasons.append("hyprctl_unavailable")
    if unsupported_model: edit_reasons.append("unsupported_model")
    if not lua_path.is_file():
        edit_reasons.append("bindings_file_missing")
        warnings.append(Warning("keybindings_bindings_file_missing", "bindings.lua is missing", str(lua_path), "Run omarchy-refresh-config hypr/bindings.lua"))
    if inspected["state"] not in {"absent", "present"}: edit_reasons.append("markers_ambiguous")
    capabilities = {**capability_data,
        "inventory": {"available": not bool(next((w for w in warnings if w.code == "keybindings_binds_unparseable"), None)), "jsonTrusted": bool(json_text) and not any(w.code == "keybindings_binds_json_untrusted" for w in warnings)},
        "keymap": {"available": bool(code_to_keysym), "layout": str((devices["keyboard"] or {}).get("layout", "")),
                   "variant": str((devices["keyboard"] or {}).get("variant", "")), "options": str((devices["keyboard"] or {}).get("options", "")),
                   "layouts": len(devices["layouts"]), "multipleLayouts": devices["multipleLayouts"],
                   "resolveBindsBySym": resolve_binds_by_sym},
        "catalog": {"available": bool(catalog), "omarchyPath": str(ctx.paths.omarchy_path), "digest": catalog_digest},
        "luac": luac, "bindingsFile": {"present": lua_path.is_file(), "path": str(lua_path), "markers": inspected["state"]},
        "edit": {"available": not edit_reasons, "reasons": edit_reasons}}
    revision_payload = b"\0".join([plain.encode(), json_text.encode() if json_text else b"-", version.splitlines()[0].encode() if version else b"-",
                                    resolve_text.encode() if resolve_text else b"-", json.dumps(devices["layouts"], sort_keys=True).encode(),
                                    lua_bytes or b"-", raw_model or b"-", catalog_digest.encode()])
    revision = "sha256:" + hashlib.sha256(revision_payload).hexdigest()
    data = {"schemaVersion": 1, "revision": revision, "capabilities": capabilities, "records": records,
            "disabledDefaults": disabled_defaults, "orphanedDisables": orphaned, "model": model,
            "managedBlock": inspected, "switches": devices["switches"], "warnings": [warning.to_json() for warning in warnings],
            "keymapContext": {"codeToKeysym": {str(key): value for key, value in code_to_keysym.items()},
                              "layouts": devices["layouts"], "multipleLayouts": devices["multipleLayouts"],
                              "resolveBindsBySym": resolve_binds_by_sym}, "catalogEntries": catalog}
    return Status("keybindings", revision, data, tuple(warnings), 1)


def _unbind_target_issues(model: dict[str, Any], status: Status) -> list[ValidationIssue]:
    candidates: list[tuple[str, str, str, str, str]] = []
    for item in status.data.get("model", {}).get("bindings", []):
        try:
            identity = from_model(item["chord"])["identity"]
        except (KeyError, ChordError):
            continue
        candidates.append(("managed", "", item.get("description", ""), identity,
                           item.get("chord", {}).get("sourceKeys", "")))
    for item in status.data.get("catalogEntries", []):
        candidates.append(("omarchy_default", item.get("module", ""), item.get("description", ""),
                           item.get("identity", ""), item.get("keys", "")))
    issues: list[ValidationIssue] = []
    for index, item in enumerate(model.get("disabled", [])):
        target = item.get("target", {})
        wanted = (target.get("kind", ""), target.get("module", ""), target.get("description", ""),
                  target.get("identity", ""), item.get("sourceKeys", ""))
        if wanted not in candidates:
            issues.append(ValidationIssue("keybindings_unknown_unbind_target",
                                          "The disable target does not exactly match a managed or Omarchy binding",
                                          f"/model/disabled/{index}", "error"))
    return issues


def _pure_validation(draft: dict[str, Any], status: Status) -> ValidationResult:
    issues, normalized, rendered = validate_draft(draft)
    findings: list[dict[str, Any]] = []
    if normalized is not None:
        issues.extend(_unbind_target_issues(normalized["model"], status))
        findings = classify_conflicts(normalized["model"], status.data.get("records", []),
                                      status.data.get("keymapContext", {}))
        for finding in findings:
            if finding["severity"] == "blocker":
                issues.append(ValidationIssue("keybindings_" + finding["category"], finding["reason"],
                                              "/model/bindings", "error"))
    errors = [item for item in issues if item.severity == "error"]
    details = {"findings": findings, "renderedBlock": rendered}
    return ValidationResult(not errors, tuple(issues), normalized if not errors else None, details)


def validate(ctx: Any, draft: dict[str, Any], status: Status) -> ValidationResult:
    validation = _pure_validation(draft, status)
    issues = list(validation.issues)
    normalized = validation.normalized_draft
    if validation.ok and normalized is not None and normalized.get("recoveryAction") != "forget":
        state = status.data.get("managedBlock", {}).get("state")
        if state in {"absent", "present"}:
            body = render_body(normalized["model"])
            candidate = managed_block.replace(_read_bytes(bindings_path(ctx)), "BINDINGS", 1, body, "--")
            try:
                _, warning = check_candidate(ctx, candidate)
                if warning:
                    issues.append(ValidationIssue(warning, "Lua syntax was not checked because luac is unavailable",
                                                  "/model", "warning"))
            except CcError as error:
                issues.append(ValidationIssue(error.code, error.message, "/model", "error"))
    errors = [item for item in issues if item.severity == "error"]
    return ValidationResult(not errors, tuple(issues), normalized if not errors else None,
                            {**validation.details, "warnings": [item.to_json() for item in issues if item.severity == "warning"]})


def build_plan(ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
    validation = _pure_validation(draft, status)
    if not validation.ok or validation.normalized_draft is None:
        raise CcError("validation_failed", "Keybinding draft has blocking findings", {"issues": [item.to_json() for item in validation.issues]})
    normalized = validation.normalized_draft
    model = normalized["model"]
    if normalized.get("recoveryAction") == "forget":
        stored_path = model_path(ctx)
        forget = ops.RemoveFile(ctx, stored_path, "Forget managed keybinding records")
        detail = {"recoveryAction": "forget", "bindingsSha256": hashlib.sha256(_read_bytes(bindings_path(ctx))).hexdigest()}
        forget = type(forget)(forget.id, forget.module_id, forget.kind, forget.params, forget.summary,
                              forget.inverse, forget.backup_paths, forget.timeout_s, detail)
        return Plan("keybindings", status.revision, (forget,),
                    (ResourceClaim("file:" + str(stored_path), "exclusive"),),
                    "Forget managed keybinding records without changing bindings.lua", (), ())
    body = render_body(model)
    if model == status.data.get("model") and not status.data.get("managedBlock", {}).get("drift"):
        return Plan("keybindings", status.revision, (), (), "Keybindings are already up to date", (), ())
    state = status.data.get("managedBlock", {}).get("state")
    if state not in {"absent", "present"}:
        raise CcError("keybindings_markers_ambiguous", "bindings.lua managed markers must be repaired before applying")
    lua_path = bindings_path(ctx)
    current = _read_bytes(lua_path)
    candidate = managed_block.replace(current, "BINDINGS", 1, body, "--")
    stored_path = model_path(ctx)
    expected_present = []
    for item in model.get("bindings", []):
        if item.get("enabled"):
            parsed = from_model(item["chord"])
            expected_present.append({"identity": parsed["identity"], "phase": "release" if item["flags"]["release"] else "press", "description": item["description"]})
    expected_absent = [item["target"]["identity"] for item in model.get("disabled", []) if not item.get("replacedBy")]
    detail = {"expectedPresent": expected_present, "expectedAbsent": expected_absent,
              "blockState": "absent" if body is None else "present", "candidateSha256": hashlib.sha256(candidate).hexdigest()}
    write = ops.WriteFileAtomic(ctx, stored_path, canonical_json(model), "0644", "Write the managed keybinding model",
                                backup_paths=(str(stored_path.absolute()),))
    block = ops.ReplaceManagedBlock(ctx, lua_path, "BINDINGS", 1, body, "Update the managed keybinding block",
                                    backup_paths=(str(lua_path.absolute()),))
    reload_op = ops.HyprctlReload(ctx, config_only=True, summary="Reload Hyprland keybindings")
    write = type(write)(write.id, write.module_id, write.kind, write.params, write.summary, write.inverse,
                       write.backup_paths, write.timeout_s, detail)
    finding_warnings = [finding for finding in validation.details.get("findings", []) if finding["severity"] == "warning"]
    warnings_list = [Warning("keybindings_" + item["category"], item["reason"], ack=True) for item in finding_warnings]
    if ctx.commands.which("luac") is None:
        warnings_list.append(Warning("keybindings_no_lua_check", "Lua syntax was not checked because luac is unavailable"))
    warnings = tuple(warnings_list)
    confirmations = tuple(dict.fromkeys(item.code for item in warnings if item.ack))
    claims = (ResourceClaim("file:" + str(stored_path), "exclusive"), ResourceClaim("file:" + str(lua_path), "exclusive"))
    return Plan("keybindings", status.revision, (write, block, reload_op), claims,
                "Update managed keybindings", warnings, confirmations)


def verify(ctx: Any, plan: Plan, status_after: Status, results: dict[str, Any]) -> VerifyResult:
    if not plan.operations:
        return VerifyResult("pass", "full", "")
    detail = plan.operations[0].detail or {}
    if detail.get("recoveryAction") == "forget":
        model_exists = model_path(ctx).is_file()
        digest = hashlib.sha256(_read_bytes(bindings_path(ctx))).hexdigest()
        if model_exists or digest != detail.get("bindingsSha256"):
            return VerifyResult("fail", "full", "Forget recovery changed an unexpected file",
                                "keybindings_block_mismatch", {"modelExists": model_exists})
        return VerifyResult("pass", "limited", "Managed records were forgotten; bindings.lua was left unchanged")
    expected_state = detail.get("blockState", "present")
    block = status_after.data.get("managedBlock", {})
    if block.get("state") != expected_state or block.get("drift"):
        return VerifyResult("fail", "full", "Managed bindings.lua block does not match the model", "keybindings_block_mismatch", block)
    records = status_after.data.get("records", [])
    for expected in detail.get("expectedPresent", []):
        matches = [record for record in records if record.get("identity") == expected["identity"] and record.get("phase") == expected["phase"]
                   and record.get("description") == expected["description"] and not record.get("submap")]
        if len(matches) != 1:
            return VerifyResult("fail", "full", "A managed binding did not appear exactly once", "keybindings_runtime_mismatch", {"expected": expected, "count": len(matches)})
    for identity in detail.get("expectedAbsent", []):
        if any(record.get("identity") == identity and not record.get("submap") for record in records):
            return VerifyResult("fail", "full", "A disabled binding is still active", "keybindings_runtime_mismatch", {"identity": identity})
    return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision})


def normalize_query(text: Any, keymap_context: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        context = keymap_context or {}
        mapping = {int(key): str(value) for key, value in context.get("codeToKeysym", {}).items()}
        result = normalize(str(text or ""), code_to_keysym=mapping)
        findings = []
        if result.get("mappedKeysym"):
            findings.append({"category": "keycode_alias", "keysym": result["mappedKeysym"],
                             "confidence": "exact_current_keymap"})
        return {"schemaVersion": 1, **{key: result[key] for key in ("sourceKeys", "identity", "display", "keyKind", "modifiers", "key")}, "findings": findings}
    except ChordError as error:
        raise CcError(error.code, error.message) from error
