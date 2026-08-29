from __future__ import annotations

import json
import re
from typing import Any

HEADER = (
    "// Omarchy menu extension. Written by Customization Center (firstpick.customization-center).",
    "// Editing by hand is fine; the next save from the center rewrites the file and drops",
    "// comments and formatting. Entries and unknown fields are kept. Format: docs/menu.md.",
    "// Backups: ~/.local/state/omarchy/customization-center/backups/",
)
FIELD_ORDER = ("icon", "iconFont", "label", "title", "description", "aliases", "parent", "provider",
               "target", "when", "checked", "disabled", "action")


def _entry_value(entry: dict[str, Any]) -> Any:
    if entry.get("origin") == "preserved" and entry.get("raw") is not None:
        return entry.get("raw")
    fields = dict(entry.get("fields", {}))
    fields.update(entry.get("passthrough", {}))
    result: dict[str, Any] = {}
    for key in FIELD_ORDER:
        if key in fields and (key in {"aliases", "parent"} or fields[key] != ""):
            result[key] = fields[key]
    for key, value in fields.items():
        if key not in result and key not in FIELD_ORDER:
            result[key] = value
    return result


def authored_value(draft: dict[str, Any]) -> dict[str, Any]:
    entries = {entry["id"]: _entry_value(entry) for entry in draft.get("entries", []) if not entry.get("deleted")}
    if draft.get("shape") != "wrapper":
        return entries
    value: dict[str, Any] = {"items": entries}
    for sibling in draft.get("wrapperSiblings", []):
        value[sibling["key"]] = sibling.get("value")
    return value


def render(draft: dict[str, Any]) -> bytes:
    entries = [entry for entry in draft.get("entries", []) if not entry.get("deleted")]
    lines = ["{"] + ["  " + line for line in HEADER] + [""]
    wrapper = draft.get("shape") == "wrapper"
    if wrapper:
        lines.append('  "items": {')
    indent = "    " if wrapper else "  "
    rendered: list[str] = []
    previous_group = None
    for entry in entries:
        group = str(entry.get("id", "entry")).split(".", 1)[0]
        if previous_group != group:
            if rendered:
                rendered.append("")
            rendered.append(f"{indent}// {group}")
            previous_group = group
        value = json.dumps(_entry_value(entry), ensure_ascii=False, separators=(",", ":"))
        rendered.append(f"{indent}{json.dumps(entry['id'], ensure_ascii=False)}: {value}")
    value_indexes = [index for index, line in enumerate(rendered) if line.startswith(indent + '"')]
    for index in value_indexes[:-1]:
        rendered[index] += ","
    lines.extend(rendered)
    if wrapper:
        if rendered:
            lines.append("  },") if draft.get("wrapperSiblings") else lines.append("  }")
        else:
            lines.append("  },") if draft.get("wrapperSiblings") else lines.append("  }")
        siblings = draft.get("wrapperSiblings", [])
        for index, sibling in enumerate(siblings):
            encoded = json.dumps(sibling.get("value"), ensure_ascii=False, indent=2)
            encoded_lines = encoded.splitlines()
            first = f"  {json.dumps(sibling['key'], ensure_ascii=False)}: {encoded_lines[0]}"
            if len(encoded_lines) > 1:
                first += "\n" + "\n".join("  " + line for line in encoded_lines[1:])
            if index < len(siblings) - 1:
                first += ","
            lines.append(first)
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def is_canonical(raw: bytes) -> bool:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    comments = [line.strip() for line in text.splitlines() if line.strip().startswith("//")]
    return comments[:len(HEADER)] == list(HEADER) and all(
        re.fullmatch(r"// [a-z0-9_-]+", line) for line in comments[len(HEADER):]
    )
