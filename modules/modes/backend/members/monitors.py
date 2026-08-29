from __future__ import annotations
from typing import Any
from customization_center.core import CcError

module_id = "monitors"
order = 10

def validate_section(section: dict[str, Any], status: Any, caps: Any) -> None:
    row = next((item for item in status.data.get("profiles", []) if item.get("id") == section["profileId"]), None)
    if row is None:
        raise CcError("modes_missing_profile", f"Monitor profile {section['profileId']} does not exist")
    if row.get("fit", {}).get("state") not in {None, "applicable"}:
        raise CcError("modes_section_invalid", "Monitor profile is not applicable", {"fit": row.get("fit")})

def to_draft(section: dict[str, Any], status: Any) -> dict[str, Any]:
    return {"schemaVersion": 1, "action": "activate", "profileId": section["profileId"]}

def target(section: dict[str, Any], status: Any) -> dict[str, Any]:
    return {"activeProfileId": section["profileId"], "verdict": "verified"}

def observe_target(expected: dict[str, Any], status: Any) -> dict[str, Any] | None:
    active = status.data.get("active", {})
    if not isinstance(active, dict): return None
    return {"activeProfileId": active.get("profileId"), "verdict": active.get("state")}

def capture(status: Any, selection: Any = None) -> dict[str, Any] | None:
    active = status.data.get("active", {})
    return {"profileId": active.get("profileId")} if active.get("profileId") and active.get("state") == "verified" else None

def summarize(section: dict[str, Any]) -> list[str]: return [f"Monitor profile: {section['profileId']}"]
def external_references(section: dict[str, Any]) -> list[dict[str, Any]]: return []
