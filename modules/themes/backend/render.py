from __future__ import annotations

import base64
import re
from typing import Any

from .palette import mix
from .writer import parse_shell, section_toml

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def render_shell(template: str, palette: dict[str, Any], sections: dict[str, Any]) -> str:
    def replacement(match: re.Match[str]) -> str:
        parts = match.group(1).split()
        if len(parts) == 1 and parts[0] in palette:
            return str(palette[parts[0]])
        if len(parts) == 4 and parts[0] == "mix" and parts[1] in palette and parts[2] in palette and parts[3].endswith("%"):
            return mix(palette[parts[1]], palette[parts[2]], float(parts[3][:-1]) / 100)
        if len(parts) == 3 and parts[0] == "shell_gradient":
            return str(palette.get(parts[1]) or palette.get(parts[2]) or "")
        raise ValueError("unresolved placeholder " + match.group(0))
    rendered = _PLACEHOLDER.sub(replacement, template)
    for name, values in sections.items():
        if values is None:
            continue
        block = re.compile(rf"(?ms)^\[{re.escape(name)}\]\n.*?(?=^\[|\Z)")
        rendered = block.sub("", rendered).rstrip() + "\n\n" + section_toml(name, values)
    parse_shell(rendered)
    return rendered


def preview_payload(colors: str, shell: str, tokens: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": 1, "colorsToml": colors, "shellToml": shell,
            "colorsB64": base64.b64encode(colors.encode()).decode(),
            "shellB64": base64.b64encode(shell.encode()).decode(), "tokens": tokens}
