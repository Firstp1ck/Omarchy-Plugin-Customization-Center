from __future__ import annotations

import json
import re
from typing import Any

MAX_BYTES = 1024 * 1024
KNOWN_FIELDS = (
    "icon", "iconFont", "label", "title", "description", "action", "target", "provider",
    "aliases", "parent", "when", "checked", "disabled",
)
_STRING_FIELDS = set(KNOWN_FIELDS) - {"aliases"}


class _Pairs(list):
    pass


def _diagnostic(code: str, message: str, *, json_path: str | None = None,
                line: int | None = None, column: int | None = None) -> dict[str, Any]:
    return {"code": code, "severity": "error", "path": "", "jsonPath": json_path,
            "line": line, "column": column, "message": message}


def _strip_safe(text: str) -> tuple[str, bool, bool]:
    comments = False
    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("//"):
            comments = True
            lines.append("\n" if line.endswith("\n") else "")
        else:
            lines.append(line)
    text = "".join(lines)
    output: list[str] = []
    in_string = False
    escaped = False
    trailing = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            look = index + 1
            while look < len(text) and text[look].isspace():
                look += 1
            if look < len(text) and text[look] in "}]":
                trailing = True
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output), comments, trailing


def _convert_pairs(value: Any, path: str, duplicates: list[dict[str, Any]]) -> Any:
    if isinstance(value, _Pairs):
        result: dict[str, Any] = {}
        indexes: dict[str, int] = {}
        for index, (key, child) in enumerate(value):
            child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
            if key in result:
                duplicates.append({"jsonPath": child_path, "keptIndex": index})
            result[key] = _convert_pairs(child, child_path, duplicates)
            indexes[key] = index
        return result
    if isinstance(value, list):
        return [_convert_pairs(child, f"{path}[{index}]", duplicates) for index, child in enumerate(value)]
    return value


def _document(value: dict[str, Any], bom: bool, duplicates: list[dict[str, Any]]) -> dict[str, Any]:
    wrapper = isinstance(value.get("items"), dict)
    source = value["items"] if wrapper else value
    siblings = [{"key": key, "value": child} for key, child in value.items() if wrapper and key != "items"]
    entries = []
    for item_id, raw in source.items():
        if isinstance(raw, dict):
            declared = list(raw)
            known = [key for key in declared if key in KNOWN_FIELDS]
            unknown = [key for key in declared if key not in KNOWN_FIELDS]
            type_errors = []
            for key in known:
                child = raw[key]
                valid = isinstance(child, str) if key in _STRING_FIELDS else (
                    isinstance(child, str) or isinstance(child, list) and all(isinstance(x, str) for x in child)
                )
                if not valid:
                    type_errors.append({"field": key, "expected": "string or string array" if key == "aliases" else "string",
                                        "actual": type(child).__name__})
            entries.append({"id": item_id, "valueKind": "object", "fields": raw, "raw": None,
                            "declared": declared, "known": known, "unknown": unknown, "typeErrors": type_errors})
        else:
            entries.append({"id": item_id, "valueKind": "other", "fields": {}, "raw": raw,
                            "declared": [], "known": [], "unknown": [], "typeErrors": []})
    return {"schemaVersion": 1, "shape": "wrapper" if wrapper else "direct", "bom": bom,
            "entries": entries, "wrapperSiblings": siblings, "duplicates": duplicates}


def parse_safe(raw: bytes) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if len(raw) > MAX_BYTES:
        return None, [_diagnostic("menu_unparseable", "file exceeds 1 MiB")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, [_diagnostic("menu_unparseable", f"invalid UTF-8 at byte {error.start}")]
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    stripped, comments, trailing = _strip_safe(text)
    if not stripped.strip():
        document = _document({}, bom, [])
        document["format"] = {"comments": comments, "trailingCommas": trailing, "empty": True}
        return document, []
    try:
        pairs = json.loads(stripped, object_pairs_hook=_Pairs)
    except json.JSONDecodeError as error:
        return None, [_diagnostic("menu_unparseable", error.msg, line=error.lineno, column=error.colno)]
    if not isinstance(pairs, _Pairs):
        return None, [_diagnostic("menu_unparseable", "root is not an object", json_path="$")]
    duplicates: list[dict[str, Any]] = []
    value = _convert_pairs(pairs, "$", duplicates)
    document = _document(value, bom, duplicates)
    document["format"] = {"comments": comments, "trailingCommas": trailing, "empty": False}
    return document, []


def parse_runtime(raw: bytes) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, [_diagnostic("menu_unparseable", f"invalid UTF-8 at byte {error.start}")]
    text = re.sub(r"^\s*//[^\n]*(\n|$)", "", text, flags=re.MULTILINE)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    if not text.strip():
        return {}, []
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return None, [_diagnostic("menu_unparseable", error.msg, line=error.lineno, column=error.colno)]
    if not isinstance(value, dict):
        return None, [_diagnostic("menu_unparseable", "root is not an object", json_path="$")]
    return value, []


def document_value(document: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for entry in document.get("entries", []):
        entries[entry["id"]] = entry.get("fields", {}) if entry.get("valueKind") == "object" else entry.get("raw")
    if document.get("shape") != "wrapper":
        return entries
    value = {"items": entries}
    for sibling in document.get("wrapperSiblings", []):
        value[sibling["key"]] = sibling.get("value")
    return value


def first_difference(left: Any, right: Any, path: str = "$") -> str | None:
    if type(left) is not type(right):
        return path
    if isinstance(left, dict):
        if list(left) != list(right):
            return path
        for key in left:
            found = first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return path
        for index, child in enumerate(left):
            found = first_difference(child, right[index], f"{path}[{index}]")
            if found:
                return found
        return None
    return None if left == right else path


def parse_with_parity(raw: bytes) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    safe, safe_diagnostics = parse_safe(raw)
    runtime, runtime_diagnostics = parse_runtime(raw)
    if safe is None and runtime is None:
        return None, "failed", safe_diagnostics or runtime_diagnostics
    if safe is None or runtime is None:
        diagnostics = safe_diagnostics or runtime_diagnostics
        diagnostics.append(_diagnostic("menu_runtime_parser_hazard", "safe and runtime parsers disagree"))
        return safe, "hazard", diagnostics
    path = first_difference(document_value(safe), runtime)
    if path:
        return safe, "hazard", [_diagnostic("menu_runtime_parser_hazard", "runtime parser changes this value", json_path=path)]
    is_empty = safe.get("format", {}).get("empty") or document_value(safe) == {}
    return safe, "empty" if is_empty else "ok", []


def js_key_order(keys: list[str]) -> list[str]:
    indexed: list[tuple[int, str]] = []
    others: list[str] = []
    for key in keys:
        if re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < 4294967295:
            indexed.append((int(key), key))
        else:
            others.append(key)
    indexed.sort(key=lambda item: item[0])
    return [key for _, key in indexed] + others
