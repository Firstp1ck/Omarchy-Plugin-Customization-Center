from __future__ import annotations

from customization_center.core import Capabilities, Capability, CcError

from .planner import build_plan, validate_draft
from .status import build_status
from .verify import verify_plan


class Defaults:
    id = "defaults"
    schema_version = 1

    def capabilities(self, ctx):
        probes = (
            ("selector_browser", "omarchy-default-browser", ("omarchy-default-browser",)),
            ("selector_terminal", "omarchy-default-terminal", ("omarchy-default-terminal",)),
            ("selector_editor", "omarchy-default-editor", ("omarchy-default-editor",)),
            ("selector_agent", "omarchy-default-agent", ("omarchy-default-agent",)),
            ("omarchy_commands", "omarchy", ("omarchy", "commands", "--json")),
            ("xdg_settings", "xdg-settings", ("xdg-settings",)),
            ("xdg_mime", "xdg-mime", ("xdg-mime", "query", "default")),
            ("xdg_terminal_exec", "xdg-terminal-exec", ("xdg-terminal-exec", "--print-id")),
            ("mise", "mise", ("mise", "where")),
            ("pacman", "pacman", ("pacman", "-Qq")),
            ("hyprctl_clients", "hyprctl", ("hyprctl", "-j", "clients")),
        )
        items = tuple(Capability(name, ctx.commands.which(command) is not None,
                                 "" if ctx.commands.which(command) else command + " is not on PATH",
                                 True, prefix) for name, command, prefix in probes)
        return Capabilities(self.id, items, ctx.clock.now_iso())

    def status(self, ctx):
        return build_status(ctx)

    def validate(self, ctx, draft, status):
        return validate_draft(ctx, draft, status)

    def plan(self, ctx, draft, status):
        return build_plan(ctx, draft, status)

    def verify(self, ctx, plan, status_after, results):
        return verify_plan(ctx, plan, status_after, results)

    def query(self, ctx, name, args):
        if name != "terminal_windows":
            raise CcError("unknown_query", "Unknown defaults query: " + str(name))
        try:
            clients = ctx.hyprctl.json("clients")
        except CcError as error:
            return {"schemaVersion": 1, "available": False, "count": None, "reason": error.message}
        count = sum(1 for item in clients if isinstance(item, dict) and item.get("class") == "org.omarchy.terminal")
        return {"schemaVersion": 1, "available": True, "count": count, "reason": ""}


MODULE = Defaults()
