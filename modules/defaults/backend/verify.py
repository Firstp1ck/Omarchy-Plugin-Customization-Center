from __future__ import annotations

from typing import Any

from customization_center.core import VerifyResult


def _category(status: Any, category_id: str) -> dict[str, Any] | None:
    return next((item for item in status.data.get("categories", []) if item.get("id") == category_id), None)


def verify_plan(ctx: Any, plan: Any, status_after: Any, results: dict[str, Any]) -> VerifyResult:
    operations = [item for item in plan.operations if item.detail and item.detail.get("category")]
    for operation in operations:
        detail = operation.detail or {}
        category = _category(status_after, detail["category"])
        if category is None:
            return VerifyResult("fail", "full", "A changed category is absent from status",
                                "defaults_verification_failed")
        current_data = category.get("current", {})
        current = current_data.get("choice")
        current_reported = current_data.get("reported", "")
        target = detail.get("choice")
        target_state = next((item for item in category.get("choices", []) if item.get("id") == target), {})
        checks_pass = bool(category.get("checks")) and all(item.get("ok") for item in category.get("checks", []))
        if current == target and target_state.get("state") == "available" and checks_pass:
            continue
        if operation.kind == "TerminalHandoff":
            if target_state.get("runnable") is True and current == detail.get("previous"):
                return VerifyResult("fail", "full", "The application is installed but was not set",
                                    "defaults_installed_not_set", {"category": detail["category"], "choice": target})
            if current not in {None, "", detail.get("previous"), target} or (current is None and current_reported):
                return VerifyResult("fail", "full", "The default changed to an unexpected third value",
                                    "defaults_changed_unexpectedly", {"expected": target, "actual": current or current_reported})
            return VerifyResult("pending", "full", "Waiting for the Omarchy terminal install to finish",
                                evidence={"category": detail["category"], "choice": target})
        failed = [item for item in category.get("checks", []) if not item.get("ok")]
        return VerifyResult("fail", "full", "The selector state did not pass verification",
                            "defaults_verification_failed", {"category": detail["category"], "failedChecks": failed})
    return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision})
