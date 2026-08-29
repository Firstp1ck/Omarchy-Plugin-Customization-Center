from __future__ import annotations

from typing import Any


def classify(records: list[dict[str, Any]], model: dict[str, Any], catalog: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    enabled = [item for item in model.get("bindings", []) if item.get("enabled")]
    groups: dict[tuple[str, str, str], list[int]] = {}
    for record in records:
        groups.setdefault((record["domain"], record["identity"], record["phase"]), []).append(record["index"])
    by_index = {record["index"]: record for record in records}
    for indices in groups.values():
        stack_id = "stack:" + ":".join(str(i) for i in indices) if len(indices) > 1 else None
        for index in indices:
            by_index[index]["stackId"] = stack_id
            by_index[index]["stackSize"] = len(indices)
    for record in records:
        managed = [item for item in enabled if item["chord"]["sourceKeys"] and item["description"] == record["description"]]
        managed = [item for item in managed if _identity(item) == record["identity"] and _phase(item) == record["phase"]]
        defaults = [item for item in catalog if item["identity"] == record["identity"] and item["phase"] == record["phase"] and item["description"] == record["description"]]
        record.update({"classification": "external", "confidence": "", "managedId": None, "catalog": None,
                       "externalReason": "no_match", "editable": {"edit": False, "disable": False, "replace": False},
                       "readOnlyReason": "unknown_exact_source"})
        if len(managed) == 1:
            record.update({"classification": "managed", "confidence": "exact", "managedId": managed[0]["id"],
                           "externalReason": None, "editable": {"edit": True, "disable": False, "replace": False},
                           "readOnlyReason": None})
        elif len(defaults) == 1:
            item = defaults[0]
            catalog_data = {key: item.get(key) for key in ("module", "sourceFile", "sourceLine", "keys", "dispatcherKind", "command")}
            editable = record["domain"] == "keyboard" and not record["submap"] and not record["flags"]["unknownLetters"] and record["stackSize"] == 1
            record.update({"classification": "omarchy_default", "confidence": "exact" if record["flagSource"] == "json" else "probable",
                           "catalog": catalog_data, "externalReason": None,
                           "editable": {"edit": False, "disable": editable, "replace": editable},
                           "readOnlyReason": None if editable else ("stack_member" if record["stackSize"] > 1 else "unsupported_flag")})
        elif len(managed) > 1 or len(defaults) > 1:
            record["externalReason"] = "ambiguous_match"
    catalog_identities = {item["identity"] for item in catalog}
    disabled_defaults = []
    orphaned = []
    runtime_identities = {item["identity"] for item in records}
    for item in model.get("disabled", []):
        row = {"id": item["id"], "sourceKeys": item["sourceKeys"], "target": item["target"], "reason": item["reason"], "replacedBy": item["replacedBy"]}
        if item["target"]["identity"] in catalog_identities and item["target"]["identity"] not in runtime_identities:
            disabled_defaults.append(row)
        elif item["target"]["identity"] not in catalog_identities:
            orphaned.append(row)
    return records, disabled_defaults, orphaned


def _identity(binding: dict[str, Any]) -> str:
    from .chords import from_model
    try: return from_model(binding["chord"])["identity"]
    except Exception: return ""


def _phase(binding: dict[str, Any]) -> str:
    return "release" if binding.get("flags", {}).get("release") else "press"
