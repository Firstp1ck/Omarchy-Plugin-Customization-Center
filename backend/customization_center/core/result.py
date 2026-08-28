from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import CcError, SHARED_CODES, validate_code
from .types import Warning


def _camel(name: str) -> str:
    first, *tail = name.split("_")
    return first + "".join(x[:1].upper() + x[1:] for x in tail)


class JsonEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if hasattr(obj, "to_json"):
            return obj.to_json()
        if dataclasses.is_dataclass(obj):
            return {_camel(f.name): getattr(obj, f.name) for f in dataclasses.fields(obj)}
        if isinstance(obj, (Path, tuple)):
            return str(obj) if isinstance(obj, Path) else list(obj)
        return super().default(obj)


@dataclass(frozen=True)
class Result:
    ok: bool
    command: str
    module: str | None = None
    revision: str | None = None
    data: dict[str, Any] | None = None
    warnings: tuple[Warning, ...] = ()
    errors: tuple[CcError | dict[str, Any], ...] = ()
    transaction_id: str | None = None
    duration_ms: int = 0
    schema_version: int = field(default=1, init=False)

    def to_json(self) -> dict[str, Any]:
        if self.ok and self.errors:
            raise ValueError("A result with errors cannot be ok")
        for item in self.warnings:
            validate_code(item.code, self.module)
        encoded_errors = []
        for item in self.errors:
            raw = item.to_json() if isinstance(item, CcError) else dict(item)
            validate_code(str(raw.get("code", "")), self.module)
            encoded_errors.append(raw)
        return {
            "schemaVersion": 1, "ok": self.ok, "command": self.command, "module": self.module,
            "revision": self.revision, "data": self.data,
            "warnings": [item.to_json() for item in self.warnings], "errors": encoded_errors,
            "transactionId": self.transaction_id, "durationMs": self.duration_ms,
        }


def emit(result: Result) -> str:
    return json.dumps(result.to_json(), cls=JsonEncoder, ensure_ascii=False, separators=(",", ":")) + "\n"

__all__ = ["Result", "JsonEncoder", "SHARED_CODES", "emit"]
