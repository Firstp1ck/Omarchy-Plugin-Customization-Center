from __future__ import annotations
from typing import Any
from customization_center.core import CcError
from .common import rows_by_id

module_id = "defaults"
order = 70
CATEGORIES = ("browser", "terminal", "editor")

def _categories(status: Any) -> dict[str, dict[str, Any]]: return rows_by_id(status.data.get("categories", []))
def validate_section(section: dict[str, Any], status: Any, caps: Any) -> None:
    categories = _categories(status)
    for category_id, choice in section.items():
        row = categories.get(category_id)
        if not row: raise CcError("modes_section_invalid", f"Default category {category_id} is unavailable")
        target = next((item for item in row.get("choices", []) if item.get("id") == choice), None)
        if target is None or target.get("state") != "available": raise CcError("modes_default_not_installed", f"Default option {category_id}:{choice} is not installed")

def to_draft(section: dict[str, Any], status: Any) -> dict[str, Any]: return {"schemaVersion":1,"changes":{key:{"choice":value,"install":False} for key,value in section.items()}}
def target(section: dict[str, Any], status: Any) -> dict[str, Any]: return dict(section)
def observe_target(expected: dict[str, Any], status: Any) -> dict[str, Any] | None:
    categories=_categories(status); result={}
    for category_id in expected:
        row=categories.get(category_id)
        if not row or row.get("state") not in {"ready","broken"}: return None
        result[category_id]=row.get("current",{}).get("choice")
    return result
def capture(status: Any, selection: Any = None) -> dict[str, Any] | None:
    categories=_categories(status); wanted=selection or CATEGORIES; result={}
    for category_id in wanted:
        row=categories.get(category_id)
        if row and row.get("state")=="ready" and row.get("current",{}).get("choice"): result[category_id]=row["current"]["choice"]
    return result or None
def summarize(section: dict[str, Any]) -> list[str]: return [f"Default {key}: {value}" for key,value in section.items()]
def external_references(section: dict[str, Any]) -> list[dict[str, Any]]: return [{"module":"defaults","kind":"option","category":key,"id":value} for key,value in section.items()]
