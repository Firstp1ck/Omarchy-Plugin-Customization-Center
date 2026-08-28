from __future__ import annotations

from typing import Any

SHARED_CODES = frozenset({
    "stale_revision", "validation_failed", "invalid_draft", "schema_version_unsupported",
    "runtime_unavailable", "capability_missing", "permission_required", "unsupported_config",
    "resource_conflict", "nonreversible_requires_confirmation", "locked", "timeout",
    "malformed_output", "ipc_rejected", "handoff_failed", "verification_failed",
    "rollback_failed", "recovery_required", "transaction_not_found", "transaction_state_invalid",
    "confirmation_invalid", "confirmation_expired", "unknown_module", "unknown_query", "internal_error", "registry",
})


def is_shared_code(code: str) -> bool:
    return code in SHARED_CODES


def validate_code(code: str, module_id: str | None) -> None:
    if is_shared_code(code):
        return
    if module_id and code.startswith(module_id + "_") and len(code) > len(module_id) + 1:
        return
    raise ValueError(f"Invalid error code {code!r} for module {module_id!r}")


class CcError(Exception):
    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None,
                 pointer: str = "", operation_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}
        self.pointer = pointer
        self.operation_id = operation_id

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.pointer:
            out["pointer"] = self.pointer
        if self.operation_id:
            out["operationId"] = self.operation_id
        if self.data:
            out["data"] = self.data
        return out
