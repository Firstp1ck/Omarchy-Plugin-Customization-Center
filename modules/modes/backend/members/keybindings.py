from __future__ import annotations
import copy
from typing import Any
from customization_center.core import CcError
from .common import canonical_digest

module_id = "keybindings"
order = 60

def validate_section(section: dict[str, Any], status: Any, caps: Any) -> None:
    managed = status.data.get("managedBlock", {})
    if managed.get("state") not in {"present", "absent"} or managed.get("drift"):
        raise CcError("modes_section_invalid", "Managed keybindings are ambiguous or drifted")

def to_draft(section: dict[str, Any], status: Any) -> dict[str, Any]:
    return {"schemaVersion":1,"expectedRevision":status.revision,"model":copy.deepcopy(section["document"])}
def target(section: dict[str, Any], status: Any) -> dict[str, Any]: return {"documentDigest": canonical_digest(section["document"]), "blockState": "absent" if not section["document"].get("bindings") and not section["document"].get("disabled") else "present"}
def observe_target(expected: dict[str, Any], status: Any) -> dict[str, Any] | None:
    managed = status.data.get("managedBlock", {})
    if managed.get("state") not in {"present", "absent"} or managed.get("drift"): return None
    return {"documentDigest":canonical_digest(status.data.get("model", {})),"blockState":managed.get("state")}
def capture(status: Any, selection: Any = None) -> dict[str, Any] | None:
    managed=status.data.get("managedBlock", {})
    return {"document":copy.deepcopy(status.data.get("model", {}))} if managed.get("state") in {"present","absent"} and not managed.get("drift") else None
def summarize(section: dict[str, Any]) -> list[str]: return [f"Keybindings: {len(section['document'].get('bindings', []))} bindings, {len(section['document'].get('disabled', []))} disabled"]
def external_references(section: dict[str, Any]) -> list[dict[str, Any]]: return []
