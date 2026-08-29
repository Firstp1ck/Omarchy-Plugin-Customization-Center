from __future__ import annotations

from typing import Any

from customization_center.core import (CcError, Operation, Plan, ResourceClaim, ValidationIssue,
                                       ValidationResult, Warning, ops)

from .catalog import category, choice

_ORDER = ("browser", "terminal", "editor", "agent")


def _status_category(status: Any, category_id: str) -> dict[str, Any] | None:
    return next((item for item in status.data.get("categories", []) if item.get("id") == category_id), None)


def _status_choice(status_category: dict[str, Any], choice_id: str) -> dict[str, Any] | None:
    return next((item for item in status_category.get("choices", []) if item.get("id") == choice_id), None)


def validate_draft(ctx: Any, draft: dict[str, Any], status: Any) -> ValidationResult:
    issues: list[ValidationIssue] = []
    normalized = {"schemaVersion": 1, "changes": {}}
    if not isinstance(draft, dict) or draft.get("schemaVersion") != 1 or not isinstance(draft.get("changes"), dict):
        return ValidationResult(False, (ValidationIssue("validation_failed", "Draft must contain schemaVersion 1 and changes", "", "error"),), None)
    installs = 0
    pending = bool(status.data.get("pendingHandoffs"))
    for category_id, change in draft["changes"].items():
        category_data = category(str(category_id))
        pointer = "/changes/" + str(category_id)
        if category_data is None or not isinstance(change, dict) or not isinstance(change.get("choice"), str):
            issues.append(ValidationIssue("validation_failed", "Unknown default category or malformed change", pointer, "error"))
            continue
        choice_id = change["choice"]
        target = choice(category_data, choice_id)
        if target is None:
            alias_target = next((item for item in category_data["choices"] if choice_id in item["aliases"]), None)
            message = ("Use canonical choice " + alias_target["id"] + " instead of alias " + choice_id) if alias_target else "Unknown choice " + choice_id
            issues.append(ValidationIssue("validation_failed", message, pointer + "/choice", "error"))
            continue
        install = change.get("install", False)
        if not isinstance(install, bool):
            issues.append(ValidationIssue("validation_failed", "install must be true or false", pointer + "/install", "error"))
            continue
        status_category = _status_category(status, category_id)
        target_state = _status_choice(status_category or {}, choice_id)
        if not status_category or status_category.get("drifted"):
            issues.append(ValidationIssue("defaults_catalog_drift", "Omarchy's choice list differs from this catalog", pointer, "error"))
        elif status_category.get("state") == "probe_error":
            issues.append(ValidationIssue("runtime_unavailable", "The current default cannot be read", pointer, "error"))
        elif target_state is None:
            issues.append(ValidationIssue("validation_failed", "Choice status is unavailable", pointer, "error"))
        elif target_state.get("state") in {"missing", "unprobed"}:
            if not install:
                issues.append(ValidationIssue("defaults_target_missing", "The selected application is not installed; confirm Install and set", pointer, "error"))
            else:
                installs += 1
                if pending:
                    issues.append(ValidationIssue("defaults_handoff_pending", "Another install handoff is still pending", pointer, "error"))
        elif category_id == "browser" and target_state.get("state") == "degraded":
            issues.append(ValidationIssue("defaults_desktop_entry_missing", "The browser desktop file is missing", pointer, "error"))
        elif category_id == "terminal" and target_state.get("state") == "degraded":
            issues.append(ValidationIssue("defaults_desktop_entry_missing", "The terminal desktop file is missing; verification may fail", pointer, "warning"))
        if status_category:
            current = status_category.get("current", {}).get("choice")
            if current == choice_id and status_category.get("state") == "ready":
                issues.append(ValidationIssue("defaults_no_change", "This choice is already the current default", pointer, "warning"))
            if status_category.get("state") == "unknown":
                issues.append(ValidationIssue("defaults_replaces_unknown", "This replaces a value not managed by Omarchy", pointer, "warning"))
        if category_id == "agent":
            issues.append(ValidationIssue("defaults_launches_agent", "Setting this choice launches the coding agent", pointer, "warning"))
        normalized["changes"][category_id] = {"choice": choice_id, "install": install}
    if installs > 1:
        issues.append(ValidationIssue("validation_failed", "Only one install can be started per apply", "/changes", "error"))
    errors = [item for item in issues if item.severity == "error"]
    return ValidationResult(not errors, tuple(issues), normalized if not errors else None,
                            {"warnings": [item.to_json() for item in issues if item.severity == "warning"]})


def _with(operation: Operation, *, backup_paths: tuple[str, ...], detail: dict[str, Any]) -> Operation:
    return Operation(operation.id, operation.module_id, operation.kind, operation.params, operation.summary,
                     operation.inverse, backup_paths, operation.timeout_s, detail)


def _state_path(ctx: Any, category_id: str) -> str:
    paths = {"browser": ctx.paths.xdg_config_home / "mimeapps.list",
             "terminal": ctx.paths.xdg_config_home / "xdg-terminals.list",
             "editor": ctx.paths.home / ".local/state/omarchy/defaults/editor",
             "agent": ctx.paths.xdg_config_home / "omarchy/defaults/agent"}
    return str(paths[category_id])


def _set_operation(ctx: Any, category_data: dict[str, Any], target: dict[str, Any], status_category: dict[str, Any]) -> Operation:
    category_id = category_data["id"]
    previous = status_category.get("current", {}).get("choice")
    previous_state = _status_choice(status_category, previous) if previous else None
    backups = [_state_path(ctx, category_id)]
    if category_id == "agent":
        backups.append(str(ctx.paths.xdg_config_home / "mise/config.toml"))
    inverse: Operation | list[str] | None
    if category_id != "agent" and previous and previous_state and previous_state.get("state") == "available":
        inverse = [category_data["selector"], previous]
    else:
        inverse = ops.RestoreBackup(ctx, backups[0], "Restore the previous default selection")
    label = target["label"]
    summary = ("Set and launch " if category_id == "agent" else "Set default " + category_id + " to ") + label
    operation = ops.RunCommand(ctx, [category_data["selector"], target["id"]],
        timeout_s=category_data["setTimeoutS"], summary=summary, inverse=inverse,
        env_extra={"BROWSER": None}, wait_policy="detach" if category_id == "agent" else "exit")
    return _with(operation, backup_paths=tuple(backups), detail={"category": category_id, "choice": target["id"],
        "previous": previous, "action": "set", "launchesApp": category_data["setLaunches"]})


def _handoff_operation(ctx: Any, category_data: dict[str, Any], target: dict[str, Any], status_category: dict[str, Any]) -> Operation:
    title = "Install " + target["label"] + " and set it as the default " + category_data["label"].lower()
    operation = ops.TerminalHandoff(ctx, [category_data["selector"], target["id"]], title, wrapped=False,
                                    summary=title)
    return _with(operation, backup_paths=(_state_path(ctx, category_data["id"]),),
                 detail={"category": category_data["id"], "choice": target["id"],
                         "previous": status_category.get("current", {}).get("choice"), "action": "install_and_set",
                         "installer": target["installer"]})


def build_plan(ctx: Any, draft: dict[str, Any], status: Any) -> Plan:
    validation = validate_draft(ctx, draft, status)
    if not validation.ok or validation.normalized_draft is None:
        first = next((item for item in validation.issues if item.severity == "error"), None)
        raise CcError(first.code if first else "validation_failed", first.message if first else "Invalid defaults draft",
                      {"issues": [item.to_json() for item in validation.issues]})
    changes = validation.normalized_draft["changes"]
    sets: list[Operation] = []
    handoff: Operation | None = None
    warnings: list[Warning] = []
    confirmations: list[str] = []
    residual: list[str] = []
    claims: list[ResourceClaim] = []
    for category_id in _ORDER:
        change = changes.get(category_id)
        if not change:
            continue
        category_data = category(category_id)
        status_category = _status_category(status, category_id)
        if category_data is None or status_category is None:
            continue
        if status_category.get("current", {}).get("choice") == change["choice"] and status_category.get("state") == "ready":
            warnings.append(Warning("defaults_no_change", category_data["label"] + " is already current"))
            continue
        target = choice(category_data, change["choice"])
        target_state = _status_choice(status_category, change["choice"])
        if target is None or target_state is None:
            continue
        if target_state.get("state") in {"missing", "unprobed"}:
            handoff = _handoff_operation(ctx, category_data, target, status_category)
            confirmations.append(handoff.id)
        else:
            sets.append(_set_operation(ctx, category_data, target, status_category))
        claims.append(ResourceClaim("file:" + _state_path(ctx, category_id), "exclusive"))
        if category_id == "agent":
            warning = Warning("defaults_launches_agent", "Setting the coding agent launches it", ack=True)
            warnings.append(warning); confirmations.append(warning.code)
            residual.extend(("mise_global_pin", "running_agent"))
        if status_category.get("state") == "unknown":
            warning = Warning("defaults_replaces_unknown", "The current non-Omarchy value will be replaced", ack=True)
            warnings.append(warning); confirmations.append(warning.code)
        if category_id == "terminal" and target_state.get("state") == "degraded":
            warnings.append(Warning("defaults_desktop_entry_missing", "xdg-terminal-exec may not resolve the selected desktop file"))
    operations = tuple(sets + ([handoff] if handoff else []))
    return Plan("defaults", status.revision, operations, tuple(claims),
                "Update default applications" if operations else "Default applications are already up to date",
                tuple(warnings), tuple(dict.fromkeys(confirmations)), tuple(dict.fromkeys(residual)))
