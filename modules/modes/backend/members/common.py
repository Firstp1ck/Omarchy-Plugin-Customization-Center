from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from customization_center.core import CcError


def rows_by_id(values: Any) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in values or [] if isinstance(item, dict) and item.get("id")}


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def copy_value(value: Any) -> Any:
    return copy.deepcopy(value)


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten(item, name))
        return result
    return {prefix: value}


def file_name(value: Any) -> str | None:
    return Path(value).name if isinstance(value, str) and value else None


def require(condition: bool, code: str, message: str, **data: Any) -> None:
    if not condition:
        raise CcError(code, message, data)
