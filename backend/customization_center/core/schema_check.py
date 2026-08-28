from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import CcError


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool), "null": value is None,
    }.get(expected, True)


def check(value: Any, schema: dict[str, Any], pointer: str = "", root: dict[str, Any] | None = None) -> list[str]:
    root = schema if root is None else root
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/"):
            target: Any = root
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return check(value, target, pointer, root)
        return []  # Cross-file references are checked by their owning loader.
    errors: list[str] = []
    if "oneOf" in schema:
        matches = [not check(value, choice, pointer, root) for choice in schema["oneOf"]]
        return [] if sum(matches) == 1 else [f"{pointer or '/'}: expected exactly one schema to match"]
    if "anyOf" in schema:
        return [] if any(not check(value, choice, pointer, root) for choice in schema["anyOf"]) else [f"{pointer or '/'}: no schema matched"]
    if "allOf" in schema:
        for choice in schema["allOf"]:
            errors.extend(check(value, choice, pointer, root))
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    if types and not any(_matches_type(value, item) for item in types):
        return [f"{pointer or '/'}: expected {' or '.join(types)}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{pointer or '/'}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{pointer or '/'}: value is not in enum")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 60):
            errors.append(f"{pointer or '/'}: string length is outside bounds")
        if schema.get("pattern") and re.search(schema["pattern"], value) is None:
            errors.append(f"{pointer or '/'}: string does not match pattern")
        try:
            if schema.get("format") == "uuid":
                uuid.UUID(value)
            elif schema.get("format") == "date-time":
                datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{pointer or '/'}: invalid {schema['format']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{pointer or '/'}: value is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{pointer or '/'}: value is above maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{pointer or '/'}: value is not above exclusive minimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(f"{pointer or '/'}: value is not below exclusive maximum")
    if isinstance(value, list):
        if schema.get("uniqueItems"):
            seen = [json.dumps(x, sort_keys=True, separators=(",", ":")) for x in value]
            if len(seen) != len(set(seen)):
                errors.append(f"{pointer or '/'}: array items are not unique")
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{pointer or '/'}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{pointer or '/'}: too many items")
        for index, item in enumerate(value):
            errors.extend(check(item, schema.get("items", {}), f"{pointer}/{index}", root))
    if isinstance(value, dict):
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                errors.append(f"{pointer or '/'}: missing {name}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{pointer}/{name}: additional property")
        additional = schema.get("additionalProperties")
        for name, item in value.items():
            child = properties.get(name, additional if isinstance(additional, dict) else None)
            if child is not None:
                errors.extend(check(item, child, f"{pointer}/{name}", root))
    return errors


def validate(value: Any, schema: dict[str, Any], label: str = "document") -> None:
    errors = check(value, schema)
    if errors:
        raise CcError("unsupported_config", f"Invalid {label}: {errors[0]}", {"issues": errors})


def load_and_validate(document_path: str | Path, schema_path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(document_path).read_text(encoding="utf-8"))
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CcError("unsupported_config", f"Cannot read JSON document: {document_path}") from error
    if not isinstance(value, dict) or not isinstance(schema, dict):
        raise CcError("unsupported_config", f"JSON object required: {document_path}")
    validate(value, schema, str(document_path))
    return value
