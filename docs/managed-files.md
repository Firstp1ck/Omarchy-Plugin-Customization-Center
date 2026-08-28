# Managed files

Core writes transaction infrastructure only. Module plans own user-facing files.

| Path | Writer | Purpose |
|---|---|---|
| `~/.config/omarchy/customization-center/settings.json` | core settings | Plugin settings |
| `~/.config/omarchy/customization-center/drafts/<module>/current.json` | core drafts | Autosaved draft envelope |
| `~/.config/omarchy/customization-center/drafts/<module>/assets/<sha256>.<ext>` | core drafts | Bounded draft asset |
| `~/.local/state/omarchy/customization-center/transactions/<id>.json` | core executor | Transaction journal |
| `~/.local/state/omarchy/customization-center/backups/<id>/` | core executor | Exact pre-apply file backups |
| `~/.local/state/omarchy/customization-center/staging/<module>/<plan>/` | core executor and modules | Atomic directory staging |
| `~/.local/state/omarchy/customization-center/handoffs/<id>.json` | `cc-handoff` | Terminal completion sentinel |
| `~/.local/state/omarchy/customization-center/log/ccctl.log*` | core logger | Rotated structured backend log |
| `~/.cache/omarchy/customization-center/capabilities.json` | core capabilities | Expiring probe cache |
| `$XDG_RUNTIME_DIR/omarchy-customization-center/apply.lock` | core executor | Global apply lock and holder data |
| `$XDG_RUNTIME_DIR/omarchy-customization-center/current-transaction` | core executor | Current transaction id |
| `$XDG_RUNTIME_DIR/omarchy-customization-center/confirm/<id>` | `ccctl confirm` | Submitted confirmation token |
| `$XDG_RUNTIME_DIR/omarchy-customization-center/pending-confirm/<id>` | core executor | Clear token exposed during a gate |
| `$XDG_RUNTIME_DIR/omarchy-customization-center/tmp/` | core paths | Private temporary validation files |
| `~/.config/omarchy/shell.json` | bar | Shell bar configuration |
| `~/.config/omarchy/extensions/omarchy-menu.jsonc` | menu | Personal menu entries |
| `~/.config/omarchy/themes/<slug>/` | themes | Generated user theme |
| `~/.config/hypr/monitors.lua` | monitors | Versioned managed loader block |
| `~/.config/hypr/bindings.lua` | keybindings | Versioned managed binding block |
| `~/.config/omarchy/customization-center/generated/` | monitors | Generated monitor rules |
| `~/.config/omarchy/customization-center/<module>/` | owning module | Profiles and stored documents |
| `~/.local/state/omarchy/customization-center/<module>/` | owning module | Applied-state sidecars |
| `~/.config/omarchy/customization-center/exports/` | modes and exporting modules | User-requested exports |
| `~/.config/xdg-terminals.list` | defaults rollback | Restore selector-owned preference |
| `~/.local/state/omarchy/defaults/editor` | defaults rollback | Restore selector-owned preference |
| `~/.config/omarchy/defaults/agent` | defaults rollback | Restore selector-owned preference |
| `tests/.../{module_config}/hello.json` | hello fixture only | Contract test output in an isolated home |

Every plan target is checked against shared roots and the module's validated `extraWritablePaths`. Symlinked components and writes under `$OMARCHY_PATH` or the plugin directory are refused.
