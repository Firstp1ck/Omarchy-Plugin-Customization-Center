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
| `~/.config/omarchy/extensions/omarchy-menu.jsonc` | menu | Canonical personal menu entries; exact pre-apply bytes are backed up by core |
| `~/.config/omarchy/themes/<slug>/` | themes | Generated data-only theme: palette, complete section overrides, icon theme, preview, and wallpapers |
| `~/.local/state/omarchy/customization-center/themes/<slug>.json` | themes | Generated theme ownership and file-hash sidecar |
| `~/.local/state/omarchy/current/theme.name` and `theme/` | `omarchy-theme-set` invoked by themes | Active theme name and rendered theme used for verification |
| `~/.local/state/omarchy/current/background` | `omarchy-theme-set` or `omarchy-theme-bg-set` invoked by themes | Active wallpaper symlink used for verification |
| `~/.config/hypr/monitors.lua` | monitors | Versioned managed loader block |
| `~/.config/hypr/bindings.lua` | keybindings | Versioned managed binding block |
| `~/.config/omarchy/customization-center/keybindings.json` | keybindings | Canonical managed binding model |
| `~/.config/omarchy/customization-center/generated/monitors.lua` | monitors | Generated monitor rules |
| `~/.config/omarchy/customization-center/monitors/monitor-profiles/<id>.json` | monitors | Named monitor layout profile |
| `~/.local/state/omarchy/customization-center/monitors/active.json` | monitors | Active profile pointer |
| `~/.config/omarchy/customization-center/<module>/` | owning module | Profiles and stored documents |
| `~/.local/state/omarchy/customization-center/<module>/` | owning module | Applied-state sidecars |
| `~/.config/omarchy/customization-center/exports/` | modes and exporting modules | User-requested exports |
| `~/.config/mimeapps.list` | defaults selector and rollback | Browser XDG handlers set by `omarchy-default-browser`; exact pre-apply bytes are backed up by core |
| `~/.config/xdg-terminals.list` | defaults selector and rollback | Terminal preference set by `omarchy-default-terminal`; exact pre-apply bytes are backed up by core |
| `~/.local/state/omarchy/defaults/editor` | defaults selector and rollback | Editor preference set by `omarchy-default-editor`; exact pre-apply bytes are backed up by core |
| `~/.config/omarchy/defaults/agent` | defaults selector and rollback | Coding agent preference set by `omarchy-default-agent`; exact pre-apply bytes are backed up by core |
| `~/.config/mise/config.toml` | defaults selector backup | Agent selector global mise pin; backed up for history but retained as a rollback residual |
| `tests/.../{module_config}/hello.json` | hello fixture only | Contract test output in an isolated home |

Every plan target is checked against shared roots and the module's validated `extraWritablePaths`. Symlinked components and writes under `$OMARCHY_PATH` or the plugin directory are refused.
