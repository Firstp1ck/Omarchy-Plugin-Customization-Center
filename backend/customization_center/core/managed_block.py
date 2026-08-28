from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import CcError


def comment_prefix_for(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".lua":
        return "--"
    if suffix == ".jsonc":
        return "//"
    raise ValueError(f"No managed-block comment prefix for {path}")


def markers(name: str, version: int, comment_prefix: str) -> tuple[str, str]:
    label = str(name).strip().upper()
    if not label or "\n" in label:
        raise ValueError("marker name must be a non-empty line")
    stem = f"OMARCHY CUSTOMIZATION CENTER {label} v{int(version)}"
    return f"{comment_prefix} BEGIN {stem}", f"{comment_prefix} END {stem}"


def _marker_lines(data: bytes, name: str, version: int) -> tuple[list[str], list[int], list[int]]:
    text = data.decode("utf-8", "strict")
    lines = text.splitlines(keepends=True)
    escaped = re.escape(str(name).strip().upper())
    begin_re = re.compile(rf"^\s*(?:--|//) BEGIN OMARCHY CUSTOMIZATION CENTER {escaped} v{version}\s*$")
    end_re = re.compile(rf"^\s*(?:--|//) END OMARCHY CUSTOMIZATION CENTER {escaped} v{version}\s*$")
    begins = [i for i, line in enumerate(lines) if begin_re.match(line.rstrip("\r\n"))]
    ends = [i for i, line in enumerate(lines) if end_re.match(line.rstrip("\r\n"))]
    return lines, begins, ends


def inspect(data: bytes, name: str, version: int) -> dict[str, Any]:
    try:
        lines, begins, ends = _marker_lines(data, name, version)
    except UnicodeDecodeError:
        return {"state": "unterminated", "beginLine": None, "endLine": None,
                "problems": ["file is not UTF-8"]}
    begin_line = begins[0] + 1 if begins else None
    end_line = ends[0] + 1 if ends else None
    problems: list[str] = []
    if not begins and not ends:
        state = "absent"
    elif len(begins) > 1 or len(ends) > 1:
        state = "duplicate"
        problems.append("managed markers occur more than once")
    elif not begins or not ends:
        state = "reversed" if ends and not begins else "unterminated"
        problems.append("managed block has only one marker")
    elif ends[0] < begins[0]:
        state = "reversed"
        problems.append("end marker appears before begin marker")
    else:
        generic = re.compile(r"^\s*(?:--|//) (?:BEGIN|END) OMARCHY CUSTOMIZATION CENTER ")
        nested = [i for i in range(begins[0] + 1, ends[0]) if generic.match(lines[i])]
        if nested:
            state = "nested"
            problems.append("another managed marker is nested inside the block")
        else:
            state = "present"
    return {"state": state, "beginLine": begin_line, "endLine": end_line, "problems": problems}


def replace(data: bytes, name: str, version: int, body: str | None, comment_prefix: str) -> bytes:
    status = inspect(data, name, version)
    if status["state"] not in {"absent", "present"}:
        raise CcError("unsupported_config", f"Managed block collision: {status['state']}", status)
    lines, begins, ends = _marker_lines(data, name, version)
    begin, end = markers(name, version, comment_prefix)
    newline = "\r\n" if b"\r\n" in data else "\n"
    body_lines = [] if body is None else body.rstrip("\r\n").splitlines()
    marker_line = re.compile(r"^\s*(?:--|//) (?:BEGIN|END) OMARCHY CUSTOMIZATION CENTER ")
    if any(marker_line.match(line) for line in body_lines):
        raise CcError("unsupported_config", "Managed block body contains a marker collision")
    block = [begin + newline, *(line + newline for line in body_lines), end + newline]
    if status["state"] == "absent":
        if body is None:
            return data
        text = data.decode("utf-8")
        base = text.rstrip("\r\n")
        if base:
            return (base + newline + newline + "".join(block)).encode()
        return "".join(block).encode()
    start, finish = begins[0], ends[0]
    if body is not None:
        return ("".join(lines[:start] + block + lines[finish + 1:])).encode()
    before = lines[:start]
    after = lines[finish + 1:]
    if before and not before[-1].strip() and (not after or not after[0].strip()):
        before = before[:-1]
    elif before and not before[-1].strip():
        before = before[:-1]
    return "".join(before + after).encode()


def extract(data: bytes, name: str, version: int) -> str | None:
    status = inspect(data, name, version)
    if status["state"] == "absent":
        return None
    if status["state"] != "present":
        raise CcError("unsupported_config", f"Managed block collision: {status['state']}", status)
    lines, begins, ends = _marker_lines(data, name, version)
    return "".join(lines[begins[0] + 1:ends[0]]).rstrip("\r\n")
