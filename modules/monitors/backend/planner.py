from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from customization_center.core import (Capabilities, Capability, CcError, Plan, ResourceClaim, Status,
    ValidationIssue, ValidationResult, VerifyResult, Warning, ops)
from . import geometry, identity, inventory, lua_render, ownership, profile

_CONNECTOR = re.compile(r"^[A-Za-z0-9._-]+$")
_CACHE_FILE = "monitor-inventory.json"
_IDENTITY_FIELDS = ("description", "make", "model", "serial", "connector")
_ACTIVATION_GUARD_SECONDS = 180
_ACTIVATION_REVIEW_MAX_AGE_SECONDS = 120
_ACTIVATION_CLOCK_SKEW_SECONDS = 5


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _activation_plan_context(now: datetime) -> dict[str, Any]:
    applied_at = now.astimezone(timezone.utc)
    return {
        "confirmBy": int((applied_at + timedelta(seconds=_ACTIVATION_GUARD_SECONDS)).timestamp()),
        "appliedAt": applied_at.isoformat().replace("+00:00", "Z"),
    }


def _valid_activation_plan_context(value: Any, now: datetime) -> bool:
    if (not isinstance(value, dict) or set(value) != {"confirmBy", "appliedAt"} or
            not isinstance(value.get("confirmBy"), int) or isinstance(value.get("confirmBy"), bool)):
        return False
    applied_at = _parse_iso_timestamp(value.get("appliedAt"))
    if applied_at is None:
        return False
    expected_confirm_by = int((applied_at + timedelta(seconds=_ACTIVATION_GUARD_SECONDS)).timestamp())
    age_seconds = (now.astimezone(timezone.utc) - applied_at).total_seconds()
    return (value["confirmBy"] == expected_confirm_by and
            -_ACTIVATION_CLOCK_SKEW_SECONDS <= age_seconds <= _ACTIVATION_REVIEW_MAX_AGE_SECONDS)


def _paths(ctx: Any) -> dict[str, Path]:
    module_config = ctx.paths.module_config("monitors")
    return {
        "profiles": module_config / "monitor-profiles",
        "generated_dir": ctx.paths.xdg_config_home / "omarchy/customization-center/generated",
        "generated": ctx.paths.xdg_config_home / "omarchy/customization-center/generated/monitors.lua",
        "host": ctx.paths.home / ".config/hypr/monitors.lua",
        "active": ctx.paths.module_state("monitors") / "active.json",
    }


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b""


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _cache_identity(output: dict[str, Any]) -> dict[str, str]:
    return {key: str(output.get(key, "")) for key in _IDENTITY_FIELDS}


def _read_mode_cache(ctx: Any) -> dict[str, Any] | None:
    try:
        value = json.loads(ctx.paths.read_regular(ctx.paths.cache / _CACHE_FILE, 1024 * 1024))
    except (CcError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {"observedAt", "outputs"} or not isinstance(value.get("observedAt"), str) or not isinstance(value.get("outputs"), list):
        return None
    rows: list[dict[str, Any]] = []
    for row in value["outputs"]:
        if not isinstance(row, dict) or set(row) != {"identity", "modes"} or not isinstance(row.get("identity"), dict) or not isinstance(row.get("modes"), list):
            return None
        identity_value = row["identity"]
        if set(identity_value) != set(_IDENTITY_FIELDS) or any(not isinstance(identity_value.get(key), str) for key in _IDENTITY_FIELDS):
            return None
        modes = row["modes"]
        if any(not isinstance(mode, dict) or set(mode) != {"width", "height", "refreshMilliHz"}
               or any(not isinstance(mode.get(key), int) or isinstance(mode.get(key), bool) or mode[key] <= 0
                      for key in ("width", "height", "refreshMilliHz")) for mode in modes):
            return None
        rows.append({"identity": dict(identity_value), "modes": json.loads(json.dumps(modes))})
    return {"observedAt": value["observedAt"], "outputs": rows}


def _write_mode_cache(ctx: Any, outputs: list[dict[str, Any]], previous: dict[str, Any] | None, observed_at: str) -> None:
    by_identity: dict[str, dict[str, Any]] = {}
    for row in (previous or {}).get("outputs", []):
        key = json.dumps(row["identity"], sort_keys=True, separators=(",", ":"))
        by_identity[key] = row
    for output in outputs:
        row = {"identity": _cache_identity(output), "modes": json.loads(json.dumps(output.get("modes", [])))}
        key = json.dumps(row["identity"], sort_keys=True, separators=(",", ":"))
        by_identity[key] = row
    document = {"observedAt": observed_at, "outputs": [by_identity[key] for key in sorted(by_identity)]}
    ctx.paths.write_cache_json(_CACHE_FILE, document)


def _cached_mode_sources(profiles: list[dict[str, Any]], live_outputs: list[dict[str, Any]],
                         cache: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not cache:
        return []
    cached_outputs = [{**row["identity"], "modes": row["modes"]} for row in cache["outputs"]]
    sources: list[dict[str, Any]] = []
    for value in profiles:
        for rule in value["outputs"]:
            if any(identity.score(rule, output, {}) > 0 for output in live_outputs):
                continue
            candidates = [output for output in cached_outputs if identity.score(rule, output, {}) > 0]
            if len(candidates) != 1:
                continue
            candidate = candidates[0]
            sources.append({"profileId": value["id"], "outputId": rule["id"],
                            "identity": _cache_identity(candidate), "modes": candidate["modes"],
                            "observedAt": cache["observedAt"], "stale": True})
    return sources


def _load_profiles(root: Path) -> tuple[list[dict[str, Any]], tuple[Warning, ...]]:
    rows: list[dict[str, Any]] = []
    warnings: list[Warning] = []
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        paths = []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            issues = profile.validate_profile(value, "")
            if issues or value.get("id") != path.stem:
                warnings.append(Warning("monitors_profile_invalid", f"Profile file is invalid: {path.name}", str(path), "Fix or delete the profile file"))
                continue
            rows.append(value)
        except (OSError, json.JSONDecodeError):
            warnings.append(Warning("monitors_profile_invalid", f"Profile file is not valid JSON: {path.name}", str(path), "Fix or delete the profile file"))
    return rows, tuple(warnings)


def _topology(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("connector", "disabled", "width", "height", "refreshMilliHz", "x", "y", "scale120", "transform", "mirrorOf")
    return sorted(({key: item.get(key) for key in keys} for item in outputs), key=lambda item: str(item["connector"]))


def _topology_failures(expected: list[dict[str, Any]], actual: list[dict[str, Any]], require_root: bool = True) -> list[str]:
    actual_by = {item["connector"]: item for item in actual}
    failures: list[str] = []
    for wanted in expected:
        got = actual_by.get(wanted["connector"])
        if got is None:
            failures.append(f"{wanted['connector']} is absent")
            continue
        for key in ("disabled", "width", "height", "x", "y", "transform", "mirrorOf"):
            if got.get(key) != wanted.get(key):
                failures.append(f"{wanted['connector']} {key} differs")
        if abs(int(got.get("refreshMilliHz", 0)) - int(wanted["refreshMilliHz"])) > 100:
            failures.append(f"{wanted['connector']} refresh differs")
        if abs(int(got.get("scale120", 0)) - int(wanted["scale120"])) > 1:
            failures.append(f"{wanted['connector']} scale differs")
    roots = [item for item in actual if not item["disabled"] and not item.get("mirrorOf") and item["width"] > 0 and item["height"] > 0]
    if require_root and not roots:
        failures.append("No usable root output remains")
    return failures


def _profile_warnings(value: dict[str, Any]) -> tuple[Warning, ...]:
    warnings: list[Warning] = []
    roots = [item for item in value["outputs"] if item.get("enabled") and not item.get("mirrorOf")]
    rectangles = [geometry.logical(item) for item in roots]
    groups = geometry.islands(rectangles)
    if len(groups) > 1:
        warnings.append(Warning("monitors_layout_gap", f"The layout has {len(groups)} disconnected islands", value["id"], "Move outputs until their edges touch"))
    by_id = {item["id"]: item for item in value["outputs"]}
    for item in value["outputs"]:
        target = by_id.get(item.get("mirrorOf"))
        if not target:
            continue
        source_mode, target_mode = item["mode"], target["mode"]
        source_aspect = source_mode["width"] / source_mode["height"]
        target_aspect = target_mode["width"] / target_mode["height"]
        if abs(source_aspect / target_aspect - 1) > 0.01:
            warnings.append(Warning("monitors_mirror_aspect", f"{item['label']} and {target['label']} have different aspect ratios", item["id"], "Choose matching aspect ratios"))
        if source_mode != target_mode:
            warnings.append(Warning("monitors_mirror_mode_differs", f"{item['label']} and {target['label']} use different modes", item["id"], "Choose the same mode for both outputs"))
    return tuple(warnings)


def _expected_topology(value: dict[str, Any], assignments: dict[str, str], toggles: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in value["outputs"]}
    clamshell = toggles.get("internal-monitor-clamshell")
    clamshell_connector = clamshell["connectors"][0] if clamshell and clamshell.get("connectors") else None
    expected: list[dict[str, Any]] = []
    for rule_id, connector in assignments.items():
        rule = by_id[rule_id]
        disabled = not rule["enabled"] or connector == clamshell_connector
        mode = rule["mode"]
        expected.append({
            "connector": connector, "disabled": disabled,
            "width": 0 if disabled else mode["width"], "height": 0 if disabled else mode["height"],
            "refreshMilliHz": 0 if disabled else mode["refreshMilliHz"],
            "x": rule["position"]["x"] if not disabled and not rule.get("mirrorOf") else 0,
            "y": rule["position"]["y"] if not disabled and not rule.get("mirrorOf") else 0,
            "scale120": rule["scale120"], "transform": rule["transform"],
            "mirrorOf": assignments.get(rule.get("mirrorOf")),
        })
    return sorted(expected, key=lambda item: item["connector"])


def _sleep(ctx: Any, seconds: float) -> None:
    sleeper = getattr(ctx.clock, "sleep", None)
    if callable(sleeper):
        sleeper(seconds)
    else:
        time.sleep(seconds)


def _activation_detail(plan: Plan) -> dict[str, Any] | None:
    reload_op = next((item for item in plan.operations if item.kind == "HyprctlReload"), None)
    return reload_op.detail if reload_op else None


class MonitorsModule:
    id = "monitors"
    schema_version = 1

    def capabilities(self, ctx: Any) -> Capabilities:
        ctx.commands.allow_readonly(("hyprctl", "-j", "monitors", "all"))
        items = list(ctx.capabilities.items)
        if ctx.mode == "plan":
            available = ctx.capabilities.get("hyprctl").available
            reason = "" if available else ctx.capabilities.get("hyprctl").reason
        else:
            try:
                inventory.read(ctx)
                reason, available = "", True
            except CcError as error:
                reason, available = error.message, False
        environment = ctx.commands.environ
        session = bool(environment.get("HYPRLAND_INSTANCE_SIGNATURE") and environment.get("XDG_RUNTIME_DIR"))
        items.append(Capability("monitor_inventory", available, reason, True, ("hyprctl", "-j", "monitors", "all")))
        items.append(Capability("hyprland_session", session, "" if session else "Not inside a Hyprland session"))
        return Capabilities(self.id, tuple(items), ctx.clock.now_iso())

    def status(self, ctx: Any) -> Status:
        paths = _paths(ctx)
        warnings: list[Warning] = []
        inventory_live = False
        try:
            outputs, inventory_warnings = inventory.read(ctx)
            warnings.extend(inventory_warnings)
            runtime_error = None
            inventory_live = True
        except CcError as error:
            outputs = []
            runtime_error = {"code": error.code, "message": error.message, "recovery": "Run this page inside Hyprland and retry hyprctl monitors all"}
        profiles, profile_warnings = _load_profiles(paths["profiles"])
        warnings.extend(profile_warnings)
        mode_cache = _read_mode_cache(ctx)
        cached_modes = _cached_mode_sources(profiles, outputs, mode_cache)
        for source in cached_modes:
            warnings.append(Warning("monitors_stale_modes",
                f"Modes for disconnected profile output {source['outputId']} came from the cache",
                source["outputId"], "Reconnect the output before validating or applying this mode"))
        if inventory_live:
            try:
                _write_mode_cache(ctx, outputs, mode_cache, ctx.clock.now_iso())
            except (CcError, OSError):
                pass
        host = _read_bytes(paths["host"])
        loader = ownership.loader(host) if host else {"state": "host-missing", "beginLine": None, "endLine": None, "problems": []}
        loader["path"] = str(paths["host"])
        try:
            handwritten = ownership.scan(host, outputs) if host else {"catchAll": None, "conflicts": [], "others": []}
        except CcError as error:
            handwritten = {"catchAll": None, "conflicts": [{"line": error.data.get("line"), "call": error.message, "output": ""}], "others": []}
            warnings.append(Warning("unsupported_config", error.message, str(paths["host"]), "Open monitors.lua and remove unsupported monitor code"))
        toggle_data = ownership.toggles(ctx.paths.home)
        for finding in handwritten.get("others", []):
            warnings.append(Warning("monitors_handwritten_rule_other", f"Handwritten monitor rule does not match a connected output: {finding.get('output', '')}", str(paths["host"]), "Review the rule if the output is no longer used"))
        host_text = host.decode("utf-8", "replace")
        gdk_match = re.search(r"\blocal\s+omarchy_gdk_scale\s*=\s*(\d+)", host_text)
        monitor_match = re.search(r"\blocal\s+omarchy_monitor_scale\s*=\s*([^\n]+)", host_text)
        gdk_scale = int(gdk_match.group(1)) if gdk_match else None
        monitor_scale = monitor_match.group(1).strip().strip("\"'") if monitor_match else None
        focused = next((item for item in outputs if item.get("focused")), None)
        if gdk_scale is not None and focused and round(focused["scale120"] / 120) != gdk_scale:
            warnings.append(Warning("monitors_gdk_scale_mismatch", f"GDK_SCALE {gdk_scale} differs from focused output scale {focused['scale120'] / 120:g}", str(paths["host"]), "Update GDK_SCALE in monitors.lua or use a matching monitor scale"))
        pointer = ctx.paths.read_json(paths["active"], default=None)
        active_data = {"profileId": None, "state": "none", "transactionId": None, "details": []}
        history = ctx.journal.history("monitors", limit=1_000)
        in_flight = next((tx for tx in history if tx.state == "awaiting_confirmation" and _activation_detail(tx.plan)), None)
        if in_flight:
            detail = _activation_detail(in_flight.plan) or {}
            active_data = {"profileId": detail.get("profileId"), "state": "awaiting-confirmation", "transactionId": in_flight.id, "details": []}
        elif isinstance(pointer, dict):
            digest = pointer.get("planDigest")
            def owns_pointer(tx: Any) -> bool:
                if tx.state != "committed":
                    return False
                if tx.plan.plan_digest == digest:
                    return True
                pointer_op = next((item for item in tx.plan.operations if item.summary == "Record active monitor profile"), None)
                if not pointer_op:
                    return False
                try:
                    return json.loads(pointer_op.params["content"]).get("planDigest") == digest
                except (KeyError, TypeError, json.JSONDecodeError):
                    return False
            owner = next((tx for tx in history if owns_pointer(tx)), None)
            active_data = {"profileId": pointer.get("profileId"), "state": "drifted", "transactionId": owner.id if owner else None, "details": []}
            if owner:
                detail = _activation_detail(owner.plan) or {}
                untoggled_failures = _topology_failures(detail.get("untoggledExpectedTopology", detail.get("expectedTopology", [])), outputs, require_root=False)
                adjusted_failures = _topology_failures(detail.get("expectedTopology", []), outputs, require_root=False)
                if not untoggled_failures:
                    active_data["state"] = "verified"
                elif detail.get("clamshellApplied") and not adjusted_failures:
                    active_data["state"] = "overridden"
                    active_data["details"] = untoggled_failures
                else:
                    active_data["details"] = adjusted_failures or untoggled_failures
                    warnings.append(Warning("monitors_runtime_drift", "The live monitor topology differs from the committed profile", str(paths["generated"]), "Reapply the profile or update it from the current layout"))
        profile_rows = []
        for value in profiles:
            fit = identity.match(value["outputs"], outputs)
            if fit["ambiguous"]:
                fit_state = "ambiguous"
            elif fit["unmatched"]:
                fit_state = "missing-outputs"
            elif fit["extra"] and not value["match"]["allowExtra"]:
                fit_state = "extra-outputs"
            else:
                fit_state = "applicable"
            profile_rows.append({"id": value["id"], "name": value["name"], "updatedAt": value["updatedAt"], "fit": {"state": fit_state, **fit}, "profile": value})
        apply_cap = all(ctx.capabilities.get(name).available for name in ("timed_confirmation", "monitor_inventory", "hyprland_session"))
        reasons = [ctx.capabilities.get(name).reason for name in ("timed_confirmation", "monitor_inventory", "hyprland_session") if not ctx.capabilities.get(name).available]
        data = {
            "schemaVersion": 1,
            "inventory": {"outputs": outputs, "observedAt": ctx.clock.now_iso(), "configErrors": [], "error": runtime_error},
            "cachedModes": cached_modes,
            "profiles": profile_rows, "active": active_data, "loader": loader, "handwritten": handwritten,
            "toggles": toggle_data, "related": {"gdkScale": gdk_scale, "monitorScaleLocal": monitor_scale},
            "capabilities": {"apply": apply_cap, "reasons": reasons},
        }
        revision_parts = {
            "host": host.hex(), "generated": _read_bytes(paths["generated"]).hex(), "active": _read_bytes(paths["active"]).hex(),
            "toggles": toggle_data, "inventory": outputs, "profiles": profiles,
        }
        return Status(self.id, ctx.revision_of(revision_parts), data, tuple(warnings), 1)

    def validate(self, ctx: Any, draft: dict[str, Any], status: Status) -> ValidationResult:
        issues: list[ValidationIssue] = []
        allowed = {"schemaVersion", "action", "profileId", "profile", "assignments", "override", "acknowledgedWarnings", "_planContext"}
        for key in sorted(set(draft) - allowed):
            issues.append(ValidationIssue("validation_failed", f"Unknown draft field: {key}", f"/{key}", "error"))
        if draft.get("schemaVersion", draft.get("version")) != 1:
            issues.append(ValidationIssue("unsupported_config", "Draft schemaVersion must be 1", "/schemaVersion", "error"))
        action = draft.get("action")
        if action not in {"activate", "save-profile", "delete-profile", "clear-override", "install-loader"}:
            issues.append(ValidationIssue("validation_failed", "Unknown monitor action", "/action", "error"))
        normalized = dict(draft)
        normalized.pop("version", None)
        normalized["schemaVersion"] = 1
        if action in {"activate", "delete-profile"} and not isinstance(draft.get("profileId"), str):
            issues.append(ValidationIssue("validation_failed", "profileId is required", "/profileId", "error"))
        if action == "save-profile" and not isinstance(draft.get("profile"), dict):
            issues.append(ValidationIssue("validation_failed", "profile is required", "/profile", "error"))
        value = draft.get("profile")
        if isinstance(value, dict):
            issues.extend(profile.validate_profile(value))
            if not any(item.severity == "error" for item in issues):
                for warning in _profile_warnings(value):
                    issues.append(ValidationIssue(warning.code, warning.message, f"/profile/outputs", "warning"))
        if action == "activate" and isinstance(value, dict) and value.get("id") != draft.get("profileId"):
            issues.append(ValidationIssue("validation_failed", "profile.id must equal profileId", "/profile/id", "error"))
        if action == "clear-override" and draft.get("override") not in {"internal-monitor-disable", "internal-monitor-mirror"}:
            issues.append(ValidationIssue("validation_failed", "A supported override is required", "/override", "error"))
        errors = [item for item in issues if item.severity == "error"]
        if action == "activate" and not errors:
            plan_context = draft.get("_planContext")
            now = ctx.clock.now()
            if plan_context is None:
                plan_context = _activation_plan_context(now)
            if not _valid_activation_plan_context(plan_context, now):
                issues.append(ValidationIssue("validation_failed", "Invalid internal monitor plan context", "/_planContext", "error"))
            else:
                normalized["_planContext"] = dict(plan_context)
            rendered = self._render_for_validation(normalized, status)
            if rendered is not None:
                luac = ctx.capabilities.get("luac")
                if luac.available:
                    result = ctx.commands.run(["luac", "-p", "-"], timeout_s=5, capture_limit=65536, stdin=rendered)
                    if result.timed_out or result.exit_code != 0:
                        issues.append(ValidationIssue("unsupported_config", result.stderr.strip() or "Generated monitor Lua failed luac -p", "/profile", "error"))
                else:
                    issues.append(ValidationIssue("monitors_no_lua_check", "luac is unavailable; generated Lua was not syntax checked", "/profile", "warning"))
        elif "_planContext" in draft:
            issues.append(ValidationIssue("validation_failed", "Internal monitor plan context is only valid for activation", "/_planContext", "error"))
        errors = [item for item in issues if item.severity == "error"]
        return ValidationResult(not errors, tuple(issues), normalized if not errors else None)

    def _stored(self, status: Status, profile_id: str) -> dict[str, Any] | None:
        row = next((item for item in status.data["profiles"] if item["id"] == profile_id), None)
        return row.get("profile") if row else None

    def _render_for_validation(self, draft: dict[str, Any], status: Status) -> str | None:
        value = draft.get("profile") or self._stored(status, draft.get("profileId", ""))
        if not value:
            return None
        outputs = status.data["inventory"]["outputs"]
        matched = identity.match(value["outputs"], outputs, draft.get("assignments", {}))
        if matched["ambiguous"] or matched["unmatched"]:
            return None
        return lua_render.render(value, matched["matched"], outputs)

    def plan(self, ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
        paths = _paths(ctx)
        action = draft["action"]
        if action == "save-profile":
            value = draft["profile"]
            target = paths["profiles"] / f"{value['id']}.json"
            operation = ops.WriteFileAtomic(ctx, target, profile.canonical(value), "0600", "Save monitor profile")
            return Plan(self.id, status.revision, (operation,), (ResourceClaim(f"file:{target}", "exclusive"),), f"Save monitor profile {value['name']}", (), ())
        if action == "delete-profile":
            if status.data["active"].get("profileId") == draft["profileId"]:
                raise CcError("monitors_profile_active", "The active profile cannot be deleted")
            target = paths["profiles"] / f"{draft['profileId']}.json"
            operation = ops.RemoveFile(ctx, target, "Delete monitor profile")
            return Plan(self.id, status.revision, (operation,), (ResourceClaim(f"file:{target}", "exclusive"),), "Delete monitor profile", (), ())
        if action == "clear-override":
            name = draft["override"]
            command = "omarchy-hyprland-monitor-internal" if name == "internal-monitor-disable" else "omarchy-hyprland-monitor-internal-mirror"
            operation = ops.RunCommand(ctx, [command, "on" if name.endswith("disable") else "off"], timeout_s=10,
                inverse=[command, "off" if name.endswith("disable") else "on"], summary="Clear Omarchy monitor override")
            return Plan(self.id, status.revision, (operation,), (), "Clear monitor override", (), ())

        host = _read_bytes(paths["host"])
        loader_state = ownership.loader(host)["state"] if host else "host-missing"
        if loader_state not in {"absent", "present", "present-modified", "host-missing"}:
            raise CcError("monitors_managed_block_collision", f"Managed loader markers are {loader_state}", {"path": str(paths["host"])})
        operations = [ops.EnsureDirectory(ctx, paths["generated_dir"], "0700", "Ensure generated monitor directory")]
        if not paths["generated"].exists():
            operations.append(ops.WriteFileAtomic(ctx, paths["generated"], lua_render.NOOP, "0600", "Bootstrap generated monitor rules"))
        if action == "install-loader":
            if loader_state != "present":
                operations.append(ops.ReplaceManagedBlock(ctx, paths["host"], "MONITORS", 1, ownership.LOADER_BODY, "Install monitor loader"))
            operations.append(ops.HyprctlReload(ctx, summary="Reload Hyprland monitor configuration"))
            claims = (ResourceClaim(f"file:{paths['host']}", "exclusive"), ResourceClaim(f"file:{paths['generated']}", "exclusive"))
            return Plan(self.id, status.revision, tuple(operations), claims, "Install the monitor profile loader", (), ())

        value = draft.get("profile") or self._stored(status, draft["profileId"])
        if value is None:
            raise CcError("validation_failed", f"Monitor profile does not exist: {draft['profileId']}")
        warnings = list(_profile_warnings(value))
        if not ctx.capabilities.get("luac").available:
            warnings.append(Warning("monitors_no_lua_check", "luac is unavailable; generated Lua was not syntax checked", str(paths["generated"]), "Install luac to enable syntax checking"))
        outputs = status.data["inventory"]["outputs"]
        matched = identity.match(value["outputs"], outputs, draft.get("assignments", {}))
        blocking_ids = {item["id"] for item in value["outputs"] if item.get("whenMissing") == "block"}
        ambiguous = [item for item in matched["ambiguous"] if item["outputId"] in blocking_ids]
        missing = [item for item in matched["unmatched"] if item in blocking_ids]
        if ambiguous:
            raise CcError("monitors_ambiguous_identity", "Monitor identity is ambiguous", {"outputs": ambiguous})
        if missing:
            raise CcError("monitors_output_missing", "Required monitor output is missing", {"outputs": missing})
        if matched["extra"] and not value["match"]["allowExtra"]:
            raise CcError("monitors_unexpected_output", "Unexpected monitor outputs are connected", {"outputs": matched["extra"]})
        if matched["extra"] and value["match"]["allowExtra"] and value.get("extraOutputs") is None:
            warnings.append(Warning("monitors_extra_uses_catchall", "Extra connected outputs will use the catch-all rule from monitors.lua", str(paths["host"]), "Define extraOutputs to control unmatched outputs"))
        assignment_map = matched["matched"]
        matched_by_id = {item["id"]: item for item in value["outputs"]}
        if not any(matched_by_id[output_id].get("enabled") and not matched_by_id[output_id].get("mirrorOf") for output_id in assignment_map):
            raise CcError("monitors_no_root", "No matched enabled root output remains after skipped outputs")
        for connector in assignment_map.values():
            if not _CONNECTOR.fullmatch(connector):
                raise CcError("monitors_unsupported_output_name", f"Unsupported output connector: {connector}", {"connector": connector})
        connected_by = {item["connector"]: item for item in outputs}
        for rule in value["outputs"]:
            connector = assignment_map.get(rule["id"])
            if not connector:
                warnings.append(Warning("monitors_output_skipped", f"Skipped disconnected output {rule['label']}", rule["id"], "Reconnect the output to include it"))
                continue
            wanted = rule["mode"]
            if rule["enabled"] and not any(mode["width"] == wanted["width"] and mode["height"] == wanted["height"] and abs(mode["refreshMilliHz"] - wanted["refreshMilliHz"]) <= 100 for mode in connected_by[connector]["modes"]):
                raise CcError("monitors_mode_unavailable", f"Mode is unavailable on {connector}", {"output": rule["id"], "mode": wanted})
        scan = ownership.scan(host, outputs, value["outputs"]) if host else {"conflicts": []}
        if scan["conflicts"]:
            raise CcError("monitors_handwritten_rule_conflict", "monitors.lua contains a handwritten rule for this output", {"path": str(paths["host"]), "conflicts": scan["conflicts"]})
        toggles = status.data.get("toggles", {})
        unknown_toggle = next((item for item in toggles.values() if item and item.get("state") == "unknown"), None)
        if unknown_toggle:
            raise CcError("unsupported_config", "A monitor toggle file has unknown content", {"path": unknown_toggle["path"]})
        disable = toggles.get("internal-monitor-disable")
        if disable and disable.get("connectors") and any(assignment_map.get(rule["id"]) == disable["connectors"][0] and rule["enabled"] for rule in value["outputs"]):
            raise CcError("monitors_toggle_override", f"{disable['connectors'][0]} is disabled by an Omarchy toggle", {"path": disable["path"], "override": "internal-monitor-disable"})
        mirror = toggles.get("internal-monitor-mirror")
        if mirror and mirror.get("connectors"):
            external, internal = mirror["connectors"]
            matching = next((rule for rule in value["outputs"] if assignment_map.get(rule["id"]) == external), None)
            target = assignment_map.get(matching.get("mirrorOf")) if matching else None
            if not matching or target != internal or matching["scale120"] != 120:
                raise CcError("monitors_toggle_override", "The Omarchy mirror toggle overrides this profile", {"path": mirror["path"], "override": "internal-monitor-mirror"})
        clamshell = toggles.get("internal-monitor-clamshell")
        clamshell_applied = bool(clamshell and clamshell.get("connectors") and any(assignment_map.get(rule["id"]) == clamshell["connectors"][0] and rule["enabled"] for rule in value["outputs"]))
        if clamshell_applied:
            warnings.append(Warning("monitors_clamshell_override", "The closed-lid policy will keep the internal output disabled", clamshell["path"], "Open the lid before applying this profile"))
        if status.data.get("inventory", {}).get("error"):
            raise CcError("runtime_unavailable", status.data["inventory"]["error"]["message"])
        ctx.capabilities.require("timed_confirmation", "monitor_inventory", "hyprland_session")

        if draft.get("profile") is not None:
            operations.append(ops.EnsureDirectory(ctx, paths["profiles"], "0700", "Ensure monitor profile directory"))
            operations.append(ops.WriteFileAtomic(ctx, paths["profiles"] / f"{value['id']}.json", profile.canonical(value), "0600", "Save edited monitor profile"))
        if loader_state != "present":
            operations.append(ops.ReplaceManagedBlock(ctx, paths["host"], "MONITORS", 1, ownership.LOADER_BODY, "Install monitor loader"))

        plan_context = draft.get("_planContext")
        if plan_context is None:
            plan_context = _activation_plan_context(ctx.clock.now())
        confirm_by = plan_context["confirmBy"]
        guarded = lua_render.render(value, assignment_map, outputs, confirm_by)
        unguarded = lua_render.render(value, assignment_map, outputs)
        untoggled_expected = _expected_topology(value, assignment_map, {})
        expected = _expected_topology(value, assignment_map, toggles)
        operations.append(ops.WriteFileAtomic(ctx, paths["generated"], guarded, "0600", "Write guarded monitor rules"))
        wake_argv = ["hyprctl", "dispatch", 'hl.dsp.dpms({ action = "enable" })']
        operations.append(ops.RunCommand(ctx, wake_argv, timeout_s=5, inverse=wake_argv, summary="Wake monitor outputs"))
        reload_op = ops.HyprctlReload(ctx, summary="Reload Hyprland monitor configuration")
        detail = {"expectedTopology": expected, "untoggledExpectedTopology": untoggled_expected, "profileId": value["id"], "guardedSha256": _sha256(guarded.encode()),
                  "unguardedSha256": _sha256(unguarded.encode()), "clamshellApplied": clamshell_applied}
        operations.append(replace(reload_op, detail=detail))
        operations.append(ops.TimedConfirmation(ctx, 30, "Keep this monitor layout?"))
        operations.append(ops.WriteFileAtomic(ctx, paths["generated"], unguarded, "0600", "Remove monitor confirmation guard"))

        activation_digest = hashlib.sha256(json.dumps({"profile": value, "assignments": assignment_map, "rules": _sha256(unguarded.encode())}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        pointer = {"schemaVersion": 1, "profileId": value["id"], "planDigest": activation_digest,
                   "appliedAt": plan_context["appliedAt"], "rulesSha256": _sha256(unguarded.encode()), "assignments": assignment_map}
        operations.append(ops.WriteFileAtomic(ctx, paths["active"], profile.canonical(pointer), "0600", "Record active monitor profile"))
        claims = [ResourceClaim(f"file:{paths[key]}", "exclusive") for key in ("host", "generated", "active")]
        claims.append(ResourceClaim(f"file:{paths['profiles'] / (value['id'] + '.json')}", "exclusive"))
        return Plan(self.id, status.revision, tuple(operations), tuple(claims), f"Keep this monitor layout? {value['name']}", tuple(warnings), (), plan_digest=activation_digest)

    def verify(self, ctx: Any, plan: Plan, status_after: Status, results: dict[str, Any]) -> VerifyResult:
        detail = _activation_detail(plan)
        if not detail:
            return VerifyResult("pass", "full", "")
        expected = detail["expectedTopology"]
        final = any(item.kind == "WriteFileAtomic" and item.summary == "Record active monitor profile" and item.id in results for item in plan.operations)
        budget = 8.0 if final else 3.0
        deadline = ctx.clock.monotonic() + budget
        previous: list[dict[str, Any]] | None = None
        last: list[dict[str, Any]] = status_after.data.get("inventory", {}).get("outputs", [])
        stable = False
        while True:
            remaining = deadline - ctx.clock.monotonic()
            if remaining <= 0:
                break
            try:
                sample, _ = inventory.read(ctx, timeout_s=remaining)
            except CcError:
                sample = None
            if sample is not None:
                last = sample
                if not _topology_failures(expected, sample):
                    normalized = _topology(sample)
                    if previous == normalized:
                        stable = True
                        break
                    previous = normalized
                else:
                    previous = None
            remaining = deadline - ctx.clock.monotonic()
            if remaining <= 0:
                break
            _sleep(ctx, min(0.5, remaining))
        if not stable:
            return VerifyResult("fail", "full", "Monitor topology did not stabilize", "monitors_topology_unstable", {"actual": _topology(last), "expected": expected})
        if final:
            paths = _paths(ctx)
            generated = _read_bytes(paths["generated"])
            pointer = ctx.paths.read_json(paths["active"], default=None)
            pointer_op = next((item for item in plan.operations if item.summary == "Record active monitor profile"), None)
            expected_pointer = json.loads(pointer_op.params["content"]) if pointer_op else None
            if _sha256(generated) != detail["unguardedSha256"] or not isinstance(pointer, dict) or pointer != expected_pointer or pointer.get("profileId") != detail["profileId"] or pointer.get("rulesSha256") != detail["unguardedSha256"]:
                return VerifyResult("fail", "full", "Active profile pointer or generated rules did not match", "monitors_verification_failed", {"pointer": pointer})
        return VerifyResult("pass", "full", "", evidence={"actual": _topology(last), "expected": expected})

    def query(self, ctx: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name != "layout-preview":
            raise CcError("unsupported_config", f"Unknown monitors query: {name}")
        value = args.get("profile")
        issues = profile.validate_profile(value, "/profile")
        if issues:
            raise CcError("validation_failed", "Profile cannot be previewed", {"issues": [item.to_json() for item in issues]})
        return geometry.preview(value)

    def migrate(self, ctx: Any, kind: str, document: dict[str, Any], from_version: int) -> dict[str, Any]:
        if from_version == 1:
            return dict(document)
        raise CcError("unsupported_config", f"Unsupported {kind} schema version: {from_version}")


MODULE = MonitorsModule()
