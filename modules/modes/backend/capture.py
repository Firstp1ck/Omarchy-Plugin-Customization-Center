from __future__ import annotations

from typing import Any
from .members import ORDER


def captureable(ctx: Any, selections: dict[str, Any] | None = None) -> dict[str, Any]:
    selections = selections or {}
    result: dict[str, Any] = {}
    for adapter in ORDER:
        try:
            module = ctx.registry.module(adapter.module_id)
            status = module.status(ctx.ctx_for(adapter.module_id, "read"))
            section = adapter.capture(status, selections.get(adapter.module_id))
            result[adapter.module_id] = {"available": section is not None, "section": section,
                "reason": "" if section is not None else "Current state cannot be captured safely"}
        except Exception as error:
            result[adapter.module_id] = {"available": False, "section": None, "reason": str(error)}
    return {"schemaVersion": 1, "members": result}
