from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .errors import CcError


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    path: str
    line: int | None = None


@dataclass(frozen=True)
class Diagnostics:
    duplicates: tuple[Diagnostic, ...] = ()
    line_map: dict[str, int] | None = None
    warnings: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.duplicates


class _Pairs(list):
    pass


def _pointer(path: tuple[str, ...]) -> str:
    return "".join("/" + value.replace("~", "~0").replace("/", "~1") for value in path)


class _LocationParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.decoder = json.JSONDecoder()
        self.locations: dict[str, list[int]] = {}

    def _skip_space(self) -> None:
        while self.index < len(self.text) and self.text[self.index].isspace():
            self.index += 1

    def _line(self, index: int) -> int:
        return self.text.count("\n", 0, index) + 1

    def parse(self) -> dict[str, list[int]]:
        self._value(())
        return self.locations

    def _value(self, path: tuple[str, ...]) -> None:
        self._skip_space()
        if self.text[self.index] == "{":
            self._object(path)
        elif self.text[self.index] == "[":
            self._array(path)
        else:
            _, self.index = self.decoder.raw_decode(self.text, self.index)

    def _object(self, path: tuple[str, ...]) -> None:
        self.index += 1
        self._skip_space()
        if self.text[self.index] == "}":
            self.index += 1
            return
        while True:
            self._skip_space()
            key_start = self.index
            key, self.index = self.decoder.raw_decode(self.text, self.index)
            child = path + (str(key),)
            pointer = _pointer(child)
            self.locations.setdefault(pointer, []).append(self._line(key_start))
            self._skip_space()
            self.index += 1  # colon
            self._value(child)
            self._skip_space()
            if self.text[self.index] == "}":
                self.index += 1
                return
            self.index += 1  # comma

    def _array(self, path: tuple[str, ...]) -> None:
        self.index += 1
        self._skip_space()
        if self.text[self.index] == "]":
            self.index += 1
            return
        item = 0
        while True:
            self._value(path + (str(item),))
            item += 1
            self._skip_space()
            if self.text[self.index] == "]":
                self.index += 1
                return
            self.index += 1  # comma


def _strip_comments(text: str) -> str:
    output: list[str] = []
    in_block = False
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        stripped = line.strip()
        ending = "\n" if line.endswith("\n") else ""
        if in_block:
            if "*/" in stripped:
                if not stripped.endswith("*/"):
                    raise CcError("invalid_draft", f"Block comment must occupy whole lines (line {number})")
                in_block = False
            output.append(ending)
            continue
        if stripped.startswith("//"):
            output.append(ending)
            continue
        if stripped.startswith("/*"):
            if not stripped.endswith("*/"):
                in_block = True
            output.append(ending)
            continue
        if "//" in line or "/*" in line or "*/" in line:
            # Let JSON strings containing these sequences through. Anything else fails in json.loads.
            output.append(line)
        else:
            output.append(line)
    if in_block:
        raise CcError("invalid_draft", "Unterminated block comment")
    return "".join(output)


def _strip_trailing_commas(text: str) -> str:
    chars = list(text)
    in_string = False
    escaped = False
    for i, char in enumerate(chars):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == ",":
            j = i + 1
            while j < len(chars) and chars[j].isspace():
                j += 1
            if j < len(chars) and chars[j] in "]}":
                chars[i] = " "
    return "".join(chars)


def parse(data: bytes) -> tuple[Any, Diagnostics]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CcError("invalid_draft", "JSONC must be UTF-8") from error
    cleaned = _strip_trailing_commas(_strip_comments(text))
    try:
        raw = json.loads(cleaned, object_pairs_hook=_Pairs)
    except json.JSONDecodeError as error:
        raise CcError("invalid_draft", f"Invalid JSONC at line {error.lineno}, column {error.colno}: {error.msg}",
                      {"line": error.lineno, "column": error.colno}) from error
    duplicates: list[Diagnostic] = []
    line_map: dict[str, int] = {"": 1}
    key_lines = _LocationParser(cleaned).parse()
    occurrences: dict[str, int] = {}

    def convert(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, _Pairs):
            out: dict[str, Any] = {}
            seen: set[str] = set()
            for key, item in value:
                child = path + (str(key),)
                pointer = _pointer(child)
                lines = key_lines.get(pointer, [])
                occurrence = occurrences.get(pointer, 0)
                occurrences[pointer] = occurrence + 1
                line = lines[occurrence] if occurrence < len(lines) else None
                line_map.setdefault(pointer, line or 1)
                if key in seen:
                    duplicates.append(Diagnostic("duplicate_key", f"Duplicate key {key!r}", pointer, line))
                seen.add(key)
                out[key] = convert(item, child)
            return out
        if isinstance(value, list):
            return [convert(item, path + (str(index),)) for index, item in enumerate(value)]
        return value

    value = convert(raw, ())
    return value, Diagnostics(tuple(duplicates), line_map, ())


def dumps_canonical(value: Any, indent: int = 2) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent, separators=(",", ": ")) + "\n"
