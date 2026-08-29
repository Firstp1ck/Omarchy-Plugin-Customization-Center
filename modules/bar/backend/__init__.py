from __future__ import annotations

from typing import Any

from customization_center.core import Capabilities, Capability, CcError, Status, VerifyResult
from . import model, planner, status as status_reader, validate
from .model import to_shell


class BarModule:
    id = "bar"
    schema_version = 1

    def capabilities(self, ctx: Any) -> Capabilities:
        try:
            ctx.shell.ping()
            shell = Capability("shell_ipc", True, "")
        except CcError as error:
            shell = Capability("shell_ipc", False, error.message)
        plugin_catalog = ctx.commands.which("omarchy-plugin-catalog") is not None
        return Capabilities(self.id, (shell, Capability("catalog", plugin_catalog, "" if plugin_catalog else "omarchy-plugin-catalog is not on PATH"),
                                      Capability("settings_schema", True, "")), ctx.clock.now_iso())

    def status(self, ctx: Any) -> Status:
        revision, data, warnings = status_reader.build(ctx)
        return Status(self.id, revision, data, warnings, 1)

    def validate(self, ctx: Any, draft: dict[str, Any], status: Status):
        return validate.validate(draft, status)

    def plan(self, ctx: Any, draft: dict[str, Any], status: Status):
        return planner.build_plan(ctx, draft, status)

    def verify(self, ctx: Any, plan: Any, status_after: Status, results: dict[str, Any]) -> VerifyResult:
        preset_detail = next((operation.detail for operation in plan.operations
                              if operation.detail and operation.detail.get("presetAction")), None)
        if preset_detail:
            presets = {item.get("id"): item for item in status_after.data.get("presets", [])}
            if preset_detail["presetAction"] == "save":
                expected = preset_detail["preset"]
                actual = presets.get(expected["id"])
                comparable = ({key: actual.get(key) for key in ("schemaVersion", "id", "name", "bar")}
                              if isinstance(actual, dict) else actual)
                if comparable != expected:
                    return VerifyResult("fail", "full", "Saved bar preset does not match the reviewed document",
                                        "bar_preset_verify_failed", {"expected": expected, "actual": comparable})
            elif preset_detail["presetId"] in presets:
                return VerifyResult("fail", "full", "Deleted bar preset is still present",
                                    "bar_preset_verify_failed", {"presetId": preset_detail["presetId"]})
            return VerifyResult("pass", "full", "", evidence={"presetAction": preset_detail["presetAction"]})
        detail = next((operation.detail for operation in plan.operations if operation.detail and operation.detail.get("expected")), {})
        expected = detail.get("expected", {}).get("bar")
        if not status_after.data.get("shell", {}).get("available"):
            return VerifyResult("fail", "full", "The shell stopped responding during verification", "runtime_unavailable")
        if not status_after.data.get("file", {}).get("matchesShell"):
            return VerifyResult("fail", "full", "shell.json and listShellConfig did not converge", "bar_file_desync",
                                {"file": status_after.data.get("file")})
        actual = to_shell(status_after.data["bar"], omit_empty_anchor=True,
                          base_had_anchor="centerAnchor" in status_after.data.get("rawShellConfig", {}).get("bar", {}))
        if expected is not None and actual != expected:
            return VerifyResult("fail", "full", "The configured bar differs from the reviewed draft", "verification_failed",
                                {"expected": expected, "actual": actual})
        configured = status_after.data.get("shell", {}).get("configuredBarId")
        active = status_after.data.get("shell", {}).get("activeBarId")
        if configured != active:
            return VerifyResult("fail", "full", f"Configured {configured}, but {active} is active", "bar_shell_fallback",
                                {"configuredBarId": configured, "activeBarId": active})
        return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision,
                                                            "configuredBarId": configured, "activeBarId": active})

    def query(self, ctx: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name != "catalog":
            raise CcError("unknown_query", "Unknown bar query: " + str(name))
        value = self.status(ctx)
        return {"schemaVersion": 1, "catalog": value.data.get("catalog", []),
                "barOptions": value.data.get("barOptions", [])}


MODULE = BarModule()
