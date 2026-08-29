from __future__ import annotations

from customization_center.core import Capabilities, Capability, CcError

_planner = __import__(__package__ + ".planner", fromlist=["planner"])
_catalog = __import__(__package__ + ".catalog", fromlist=["catalog"])

_ACTIONS = [
    {"id": "omarchy-menu", "title": "Omarchy menu", "command": "omarchy-menu toggle", "category": "Menus", "mirrors": "default/hypr/bindings/utilities.lua:1"},
    {"id": "screenshot", "title": "Screenshot", "command": "omarchy-capture-screenshot", "category": "Capture", "mirrors": "default/hypr/bindings/utilities.lua"},
    {"id": "lock", "title": "Lock system", "command": "omarchy-system-lock", "category": "System", "mirrors": "default/hypr/bindings/utilities.lua"},
    {"id": "keybindings", "title": "Show keybindings", "command": "omarchy-menu-keybindings", "category": "Menus", "mirrors": "default/hypr/bindings/utilities.lua"},
    {"id": "audio", "title": "Audio panel", "command": "omarchy-shell shell toggle omarchy.audio", "category": "Panels", "mirrors": "default/hypr/bindings/utilities.lua"}
]


class Keybindings:
    id = "keybindings"
    schema_version = 1

    def capabilities(self, ctx):
        probes = (
            ("hyprctl", "hyprctl", ("hyprctl",)),
            ("xkbcli", "xkbcli", ("xkbcli",)),
            ("lua", "lua", ("lua",)),
            ("luac", "luac", ("luac", "-p")),
        )
        items = tuple(Capability(name, ctx.commands.which(command) is not None,
                                 "" if ctx.commands.which(command) else command + " is not on PATH",
                                 True, prefix)
                      for name, command, prefix in probes)
        return Capabilities(self.id, items, ctx.clock.now_iso())

    def _capability_data(self, ctx):
        caps = self.capabilities(ctx)
        hyprctl = caps.get("hyprctl")
        return {"schemaVersion": 1, "hyprctl": {"available": hyprctl.available, "version": "", "reason": hyprctl.reason}}

    def status(self, ctx):
        return _planner.build_status(ctx, self._capability_data(ctx))

    def validate(self, ctx, draft, status):
        return _planner.validate(ctx, draft, status)

    def plan(self, ctx, draft, status):
        return _planner.build_plan(ctx, draft, status)

    def verify(self, ctx, plan, status_after, results):
        return _planner.verify(ctx, plan, status_after, results)

    def query(self, ctx, name, args):
        if name == "normalize_chord":
            status = self.status(ctx)
            return _planner.normalize_query(args.get("text", ""), status.data.get("keymapContext", {}))
        if name == "catalog_search":
            defaults, _, _ = _catalog.load_default_catalog(ctx)
            return {"schemaVersion": 1, "entries": _catalog.search_actions(_ACTIONS, defaults, str(args.get("text", "")))}
        raise CcError("unknown_query", "Unknown keybindings query: " + str(name))


MODULE = Keybindings()
