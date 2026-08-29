from __future__ import annotations

from typing import Any

from customization_center.core import lua_string

_FLAG_ORDER = (("locked", "locked"), ("release", "release"), ("repeating", "repeating"),
               ("nonConsuming", "non_consuming"), ("autoConsuming", "auto_consuming"), ("bypass", "bypass"))


class RenderError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _literal(value: str) -> str:
    try:
        return lua_string(value)
    except UnicodeEncodeError as error:
        raise RenderError("keybindings_invalid_unicode", "Lua text contains an invalid Unicode surrogate") from error
    except (TypeError, ValueError) as error:
        raise RenderError("keybindings_control_character", str(error)) from error


def render_body(model: dict[str, Any]) -> str | None:
    lines = ["-- Rendered from ~/.config/omarchy/customization-center/keybindings.json by the",
             "-- Customization Center. Edit there; this block is rewritten on every apply."]
    disabled = sorted(model.get("disabled", []), key=lambda item: (item.get("sourceKeys", ""), item.get("id", "")))
    enabled = sorted((item for item in model.get("bindings", []) if item.get("enabled")),
                     key=lambda item: (item.get("chord", {}).get("sourceKeys", ""), item.get("id", "")))
    if not disabled and not enabled:
        return None
    for item in disabled:
        lines.extend(["-- cc:" + item["id"], "hl.unbind(" + _literal(item["sourceKeys"]) + ")"])
    for item in enabled:
        flags = [lua_name + " = true" for json_name, lua_name in _FLAG_ORDER if item["flags"].get(json_name)]
        args = [_literal(item["chord"]["sourceKeys"]), _literal(item["description"]), _literal(item["action"]["command"])]
        if flags:
            args.append("{ " + ", ".join(flags) + " }")
        lines.extend(["-- cc:" + item["id"], "o.bind(" + ", ".join(args) + ")"])
    return "\n".join(lines)
