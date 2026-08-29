from __future__ import annotations

from typing import Any


def _fingerprint(value: dict[str, Any]) -> tuple[str, str, str, str]:
    identity = value.get("identity", value)
    return tuple(str(identity.get(key, "")) for key in ("make", "model", "serial", "description"))  # type: ignore[return-value]


def score(profile_output: dict[str, Any], connected: dict[str, Any], assignments: dict[str, str]) -> int:
    identity = profile_output["identity"]
    if assignments.get(profile_output["id"]) == connected["connector"]:
        return 1000
    if identity.get("serial") and (identity.get("make"), identity.get("model"), identity.get("serial")) == (connected.get("make"), connected.get("model"), connected.get("serial")):
        result = 100
    elif identity.get("description") and identity["description"] == connected.get("description"):
        result = 80
    elif identity.get("make") and identity.get("model") and (identity["make"], identity["model"]) == (connected.get("make"), connected.get("model")) and not identity.get("serial") and not connected.get("serial") and not identity.get("description") and not connected.get("description"):
        result = 50
    else:
        result = 0
    if result:
        return result + (5 if identity.get("connector") == connected.get("connector") else 0)
    if identity.get("connector") != connected.get("connector") or profile_output.get("connectorPolicy") == "never":
        return 0
    if profile_output.get("connectorPolicy") == "if-no-fingerprint" and _fingerprint(connected) == ("", "", "", ""):
        return 20
    return 0


def match(profile_outputs: list[dict[str, Any]], connected: list[dict[str, Any]], assignments: dict[str, str] | None = None) -> dict[str, Any]:
    explicit = assignments or {}
    edges = {(p["id"], c["connector"]): score(p, c, explicit) for p in profile_outputs for c in connected}
    candidates = {p["id"]: [c["connector"] for c in connected if edges[(p["id"], c["connector"])] > 0] for p in profile_outputs}
    best_score = -1
    best: list[dict[str, str]] = []

    def visit(index: int, used: set[str], mapping: dict[str, str], total: int) -> None:
        nonlocal best_score, best
        if index == len(profile_outputs):
            if total > best_score:
                best_score, best = total, [dict(mapping)]
            elif total == best_score:
                best.append(dict(mapping))
            return
        output_id = profile_outputs[index]["id"]
        visit(index + 1, used, mapping, total)
        for connector in candidates[output_id]:
            if connector not in used:
                mapping[output_id] = connector; used.add(connector)
                visit(index + 1, used, mapping, total + edges[(output_id, connector)])
                used.remove(connector); del mapping[output_id]

    visit(0, set(), {}, 0)
    chosen = best[0] if best else {}
    ambiguous: list[dict[str, Any]] = []
    resolved: dict[str, str] = {}
    unmatched: list[str] = []
    for profile_output in profile_outputs:
        output_id = profile_output["id"]
        values = {item.get(output_id) for item in best}
        values.discard(None)
        if output_id not in chosen:
            unmatched.append(output_id)
        elif len(values) > 1 or any(output_id not in item for item in best):
            ambiguous.append({"outputId": output_id, "candidates": sorted(values)})
        else:
            resolved[output_id] = chosen[output_id]
    used = set(chosen.values())
    return {"matched": resolved, "unmatched": unmatched, "ambiguous": ambiguous,
            "extra": [item["connector"] for item in connected if item["connector"] not in used]}
