from __future__ import annotations

import re
from typing import Any

from customization_center.core import (
    Capabilities, Capability, CcError, Plan, ResourceClaim, Status, ValidationIssue,
    ValidationResult, VerifyResult, Warning, catalog as core_catalog, ops,
)
from . import catalog as plugin_catalog
from .kinds import bar_payload, expected_storage
from .messages import confirmation

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ACTIONS = {"add", "update", "remove", "clone"}


def _capability(row: dict[str, Any], name: str) -> dict[str, Any] | None:
    for value in row.get("capabilities", []):
        if value == name:
            return {"name": name}
        if isinstance(value, dict) and value.get("name") == name:
            return value
    return None


def _rows(status: Status) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in status.data.get("rows", [])}


class PluginsModule:
    id = "plugins"
    schema_version = 1

    def capabilities(self, ctx: Any) -> Capabilities:
        try:
            ctx.shell.ping()
            shell = Capability("shell_ipc", True, "")
        except CcError as error:
            shell = Capability("shell_ipc", False, error.message)
        catalog_available = ctx.commands.which("omarchy-plugin-catalog") is not None
        validate_available = ctx.commands.which("omarchy-plugin-validate") is not None
        launcher_available = ctx.commands.which("omarchy-launch-floating-terminal-with-presentation") is not None
        items = (
            shell,
            Capability("catalog", catalog_available, "" if catalog_available else "omarchy-plugin-catalog is not on PATH", True, ("omarchy-plugin-catalog",)),
            Capability("validate", validate_available, "" if validate_available else "omarchy-plugin-validate is not on PATH", True, ("omarchy-plugin-validate",)),
            Capability("terminal_handoff", launcher_available, "" if launcher_available else "omarchy-launch-floating-terminal-with-presentation is not on PATH"),
            Capability("patchPluginEntry", False, "The public shell IPC allowlist does not expose patchPluginEntry; non-bar settings are read-only."),
        )
        return Capabilities(self.id, items, ctx.clock.now_iso())

    def status(self, ctx: Any) -> Status:
        warnings: list[Warning] = []
        try:
            joined = core_catalog.read(ctx)
            rows, shell = plugin_catalog.enrich(ctx, joined)
            diagnostics = dict(joined.diagnostics)
            for item in diagnostics.get("warnings", []):
                warnings.append(Warning(item.get("code", "plugins_catalog_unavailable"), item.get("message", "Plugin catalog unavailable"), "", "Retry after the plugin scan finishes"))
            revision = joined.revision
        except CcError as error:
            if error.code not in {"runtime_unavailable", "timeout", "malformed_output"}:
                raise
            diagnostics = plugin_catalog.static_diagnostics(ctx)
            rows = []
            shell = {"available": False, "reason": error.message,
                     "configuredBar": None, "runningBar": None, "barFallback": False,
                     "pluginsDir": str(ctx.paths.home / ".config/omarchy/plugins")}
            revision = "unavailable"
            warnings.append(Warning("plugins_runtime_unavailable", error.message, "", "Start omarchy-shell and retry"))
        pending = []
        for transaction in ctx.journal.history(module=self.id, limit=100, state="pending_handoff"):
            operation = next((item for item in transaction.plan.operations if item.kind == "TerminalHandoff"), None)
            detail = operation.detail or {} if operation else {}
            pending.append({"transactionId": transaction.id, "action": detail.get("action"),
                            "pluginId": detail.get("pluginId"), "startedAt": transaction.created_at})
        data = {"schemaVersion": 1, "module": self.id, "revision": revision, "rows": rows,
                "shell": shell, "pendingHandoffs": pending, "diagnostics": diagnostics,
                "settingsWrite": {"available": False, "reason": "patchPluginEntry is not available in the public shell IPC contract"}}
        return Status(self.id, revision, data, tuple(warnings), 1)

    def validate(self, ctx: Any, draft: dict[str, Any], status: Status) -> ValidationResult:
        issues: list[ValidationIssue] = []
        normalized = {"schemaVersion": 1, "module": self.id,
                      "baseRevision": draft.get("baseRevision"), "changes": []}
        if draft.get("schemaVersion") != 1 or draft.get("module") != self.id:
            issues.append(ValidationIssue("plugins_invalid_draft", "Draft must be a plugins schemaVersion 1 document", "", "error"))
        if draft.get("baseRevision") != status.revision:
            issues.append(ValidationIssue("stale_revision", "The plugin catalog changed since this draft was created", "/baseRevision", "error"))
        changes = draft.get("changes")
        if not isinstance(changes, list) or not changes:
            issues.append(ValidationIssue("plugins_empty_draft", "Choose at least one plugin change", "/changes", "error"))
            changes = []
        lifecycle = [change for change in changes if isinstance(change, dict) and change.get("kind") == "lifecycle"]
        if lifecycle and len(changes) != 1:
            issues.append(ValidationIssue("plugins_lifecycle_not_alone", "A lifecycle action must be applied by itself", "/changes", "error"))
        known = _rows(status)
        seen: set[str] = set()
        navigation: dict[str, Any] = {}
        for index, raw in enumerate(changes):
            pointer = f"/changes/{index}"
            if not isinstance(raw, dict):
                issues.append(ValidationIssue("plugins_invalid_change", "Change must be an object", pointer, "error"))
                continue
            kind = raw.get("kind")
            plugin_id = raw.get("pluginId")
            if kind == "lifecycle" and raw.get("action") == "add":
                normalized["changes"].append({"kind": "lifecycle", "action": "add", "closesCenter": False})
                continue
            if not isinstance(plugin_id, str) or not _ID.fullmatch(plugin_id) or ".." in plugin_id:
                issues.append(ValidationIssue("plugins_invalid_id", "Plugin id is malformed", pointer + "/pluginId", "error"))
                continue
            if plugin_id in seen:
                issues.append(ValidationIssue("plugins_duplicate_change", "Each plugin may be changed only once", pointer + "/pluginId", "error"))
                continue
            seen.add(plugin_id)
            row = known.get(plugin_id)
            if row is None:
                issues.append(ValidationIssue("plugins_unknown_plugin", f"The shell did not discover {plugin_id}", pointer + "/pluginId", "error"))
                continue
            if kind in {"enable", "disable"}:
                if row.get("ownership") == "bar":
                    issues.append(ValidationIssue("plugins_bar_owned", "Bar plugins are edited in the bar editor", pointer, "error"))
                    navigation[plugin_id] = bar_payload(row)
                    continue
                if _capability(row, kind) is None:
                    issues.append(ValidationIssue("plugins_capability_missing", f"{kind.title()} is not available for {plugin_id}", pointer, "error"))
                    continue
                if row.get("self") and raw.get("closesCenter") is not True:
                    issues.append(ValidationIssue("plugins_self_action", "Acknowledge that the Customization Center will close", pointer + "/closesCenter", "error"))
                    continue
                normalized["changes"].append({"kind": kind, "pluginId": plugin_id,
                                               "closesCenter": bool(raw.get("closesCenter", False))})
            elif kind == "lifecycle":
                action = raw.get("action")
                capability_name = "clone-edit" if action == "clone" and raw.get("edit") is True else action
                if action not in _ACTIONS - {"add"}:
                    issues.append(ValidationIssue("plugins_invalid_action", "Unknown lifecycle action", pointer + "/action", "error"))
                    continue
                if _capability(row, str(capability_name)) is None:
                    issues.append(ValidationIssue("plugins_capability_missing", f"{capability_name} is not available for {plugin_id}", pointer, "error"))
                    continue
                if row.get("self") and action in {"remove", "update"} and raw.get("closesCenter") is not True:
                    issues.append(ValidationIssue("plugins_self_action", "Acknowledge that the Customization Center will close", pointer + "/closesCenter", "error"))
                    continue
                normalized["changes"].append({"kind": "lifecycle", "action": action, "pluginId": plugin_id,
                                               "edit": bool(raw.get("edit", False)),
                                               "closesCenter": bool(raw.get("closesCenter", False))})
            else:
                issues.append(ValidationIssue("plugins_invalid_change", "Change kind must be enable, disable, or lifecycle", pointer + "/kind", "error"))
        ok = not any(issue.severity == "error" for issue in issues)
        return ValidationResult(ok, tuple(issues), normalized if ok else None, {"navigate": navigation})

    def plan(self, ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
        if draft.get("baseRevision") != status.revision:
            raise CcError("stale_revision", "The plugin catalog changed since review")
        rows = _rows(status)
        changes = sorted(draft.get("changes", []), key=lambda item: 0 if item.get("kind") == "disable" else 1)
        operations = []
        claims: list[ResourceClaim] = []
        warnings: list[Warning] = []
        confirmations: list[str] = []
        for change in changes:
            kind = change["kind"]
            plugin_id = change.get("pluginId")
            row = rows.get(plugin_id, {})
            if kind in {"enable", "disable"}:
                value = kind == "enable"
                active_clone = row.get("state", {}).get("activeCloneId")
                inverse_id = active_clone if value and active_clone else plugin_id
                inverse = ops.ShellIpc(ctx, "setPluginEnabled", (inverse_id, "true" if value and active_clone else ("false" if value else "true")),
                                           expect=("ok",), inverse=(), summary=f"Restore plugin state for {inverse_id}")
                summary = (f"Enable {plugin_id}" if value else f"Disable {plugin_id}")
                if value and active_clone:
                    summary += f" and stop using {active_clone}"
                operation = ops.ShellIpc(ctx, "setPluginEnabled", (plugin_id, "true" if value else "false"),
                                         expect=("ok",), inverse=inverse, summary=summary,
                                         detail={"action": kind, "pluginId": plugin_id, "targetEnabled": value,
                                                 "activeCloneId": active_clone, "closesCenter": change.get("closesCenter", False)})
            else:
                action = change["action"]
                argv = {"add": ["omarchy-plugin-add"],
                        "update": ["omarchy-plugin-update", plugin_id],
                        "remove": ["omarchy-plugin-remove", plugin_id],
                        "clone": ["omarchy-plugin-clone", plugin_id]}[action]
                if action == "clone" and change.get("edit"):
                    argv.append("--edit")
                title = {"add": "Add plugin", "update": f"Update {plugin_id}",
                         "remove": f"Remove {plugin_id}", "clone": f"Clone {plugin_id}"}[action]
                detail = {"action": action, "pluginId": plugin_id,
                          "beforeIds": sorted(rows), "edit": change.get("edit", False),
                          "closesCenter": change.get("closesCenter", False)}
                operation = ops.TerminalHandoff(ctx, argv, title, wrapped=True,
                                                summary=confirmation("clone-edit" if action == "clone" and change.get("edit") else action,
                                                                     self_action=row.get("self") is True),
                                                detail=detail)
                warning = Warning(f"plugins_confirm_{action}", operation.summary, "", "Complete or cancel the terminal flow", True)
                warnings.append(warning)
                confirmations.extend((operation.id, warning.code))
            operations.append(operation)
            claim_id = plugin_id or "add"
            claims.append(ResourceClaim(f"shell.plugin:{claim_id}", "exclusive"))
            if kind == "lifecycle" and row.get("ownership") == "bar":
                claims.append(ResourceClaim("shell.bar", "exclusive"))
        summary = f"Apply {len(operations)} plugin change{'s' if len(operations) != 1 else ''}"
        return Plan(self.id, status.revision, tuple(operations), tuple(claims), summary,
                    tuple(warnings), tuple(confirmations))

    def verify(self, ctx: Any, plan: Plan, status_after: Status, results: dict[str, Any]) -> VerifyResult:
        rows = _rows(status_after)
        for operation in plan.operations:
            detail = operation.detail or {}
            action = detail.get("action")
            plugin_id = detail.get("pluginId")
            if action in {"enable", "disable"}:
                row = rows.get(plugin_id)
                target = detail.get("targetEnabled") is True
                if row is None or row.get("state", {}).get("enabled") is not target:
                    return VerifyResult("fail", "full", f"{plugin_id} did not reach the requested enabled state", "verification_failed", {"pluginId": plugin_id, "targetEnabled": target})
                expected, disabled = expected_storage(row, target)
                state = row.get("state", {})
                if target and row.get("firstParty"):
                    storage_ok = state.get("storage") == expected and state.get("disabledByList") is disabled
                else:
                    storage_ok = state.get("storage") == expected
                if not storage_ok:
                    return VerifyResult("fail", "full", f"{plugin_id} has unexpected shell storage after {action}", "verification_failed", {"state": state, "expectedStorage": expected})
                active_clone = detail.get("activeCloneId")
                if active_clone and rows.get(active_clone, {}).get("state", {}).get("enabled"):
                    return VerifyResult("fail", "full", f"Clone {active_clone} is still enabled", "verification_failed")
            elif action == "remove" and plugin_id in rows:
                return VerifyResult("fail", "full", f"Removed plugin {plugin_id} is still discovered", "verification_failed")
            elif action == "update" and plugin_id not in rows:
                return VerifyResult("fail", "limited", f"Updated plugin {plugin_id} is no longer discovered", "verification_failed")
            elif action == "clone":
                clone = next((row for row in rows.values() if row.get("clonedFrom") == plugin_id and row.get("state", {}).get("enabled")), None)
                if clone is None:
                    return VerifyResult("fail", "full", f"Clone of {plugin_id} was not discovered and enabled", "plugins_clone_incomplete")
            elif action == "add":
                before = set(detail.get("beforeIds", []))
                if not (set(rows) - before):
                    return VerifyResult("fail", "limited", "No newly added plugin was discovered after the terminal completed", "verification_failed")
        lifecycle = any((operation.detail or {}).get("action") in _ACTIONS for operation in plan.operations)
        if lifecycle:
            return VerifyResult("pass", "limited", "terminal-command-and-catalog-only",
                                evidence={"revision": status_after.revision, "rowCount": len(rows)})
        return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision, "rowCount": len(rows)})

    def query(self, ctx: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name != "validate":
            raise CcError("unknown_query", f"Unknown plugins query: {name}")
        plugin_id = args.get("id")
        if not isinstance(plugin_id, str) or not _ID.fullmatch(plugin_id) or ".." in plugin_id:
            raise CcError("plugins_invalid_id", "Plugin id is malformed")
        status = self.status(ctx)
        row = _rows(status).get(plugin_id)
        if row is None:
            raise CcError("plugins_unknown_plugin", f"The shell did not discover {plugin_id}")
        if _capability(row, "validate") is None:
            raise CcError("plugins_capability_missing", f"Validation is unavailable for {plugin_id}")
        directory = row.get("origin", {}).get("sourceDir")
        if not isinstance(directory, str):
            raise CcError("plugins_capability_missing", f"No safe source directory is known for {plugin_id}")
        ctx.commands.allow_readonly(("omarchy-plugin-validate", directory))
        result = ctx.commands.run(["omarchy-plugin-validate", directory], timeout_s=30, capture_limit=65536)
        return {"schemaVersion": 1, "pluginId": plugin_id, "exit": result.exit_code,
                "stdout": result.stdout, "stderr": result.stderr, "timedOut": result.timed_out,
                "diagnostic": None if result.exit_code == 0 else {"code": "plugins_validation_failed", "severity": "warning", "message": result.stderr.strip() or "Plugin validation failed", "path": directory}}


MODULE = PluginsModule()
