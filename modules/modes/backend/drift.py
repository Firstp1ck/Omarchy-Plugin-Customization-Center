from __future__ import annotations

from typing import Any
from .members import BY_ID
from .members.common import flatten
from .store import digest


def report(ctx: Any, record: dict[str, Any] | None, mode: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(record, dict): return None
    findings: list[dict[str, Any]] = []; indeterminate: list[dict[str, Any]] = []
    for member_id, expected in record.get("targets", {}).items():
        adapter = BY_ID.get(member_id)
        if adapter is None:
            indeterminate.append({"member":member_id,"field":"","reason":"adapter unavailable"}); continue
        try:
            status = ctx.registry.module(member_id).status(ctx.ctx_for(member_id, "read"))
            observed = adapter.observe_target(expected, status)
        except Exception as error:
            observed = None; indeterminate.append({"member":member_id,"field":"","reason":str(error)})
        if observed is None:
            if not any(item["member"] == member_id for item in indeterminate): indeterminate.append({"member":member_id,"field":"","reason":"state is not safely observable"})
            continue
        expected_flat=flatten(expected); observed_flat=flatten(observed)
        for field, wanted in expected_flat.items():
            if field not in observed_flat:
                indeterminate.append({"member":member_id,"field":field,"reason":"field unavailable"})
            elif observed_flat[field] != wanted:
                findings.append({"member":member_id,"field":field,"expected":wanted,"actual":observed_flat[field]})
    state = "indeterminate" if indeterminate else "drifted" if findings else "applied"
    definition_changed = mode is None or digest(mode) != record.get("modeDigest")
    return {"modeId":record.get("modeId"),"state":state,"findings":findings,"indeterminate":indeterminate,
            "definitionChanged":definition_changed,"record":record}
