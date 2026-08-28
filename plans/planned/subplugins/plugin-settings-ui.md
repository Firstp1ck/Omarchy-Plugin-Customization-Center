# Plugin settings module

Module id: `plugins`. Directory: `modules/plugins/`. Backend package: `modules/plugins/backend/`, exporting `MODULE`.

Status: planned. Every Omarchy claim below was checked against `/mnt/SSD_NVME_4TB/GitHub/omarchy-fork` at commit `71b0887c`. Paths are relative to that checkout unless they start with `modules/`, `core/`, or `backend/`, which are paths in this project. Nothing in this plan was exercised against a live Quickshell session. This plan follows the contract amendments sheet; where it names a sheet section (A to J) that section is the authority.

## 1. What the module does

The page is a catalog of every plugin the running shell discovered, with the state the shell reports, the manifest facts the shell does not report, and the actions each row supports. It does four things:

1. Lists plugins with kind, origin, enablement, placement, clone relationship, and diagnostics.
2. Enables and disables plugins that have neither the `bar` nor the `bar-widget` kind, through `setPluginEnabled`, writing `plugins[]` and `disabledPlugins[]` only.
3. Shows bar widgets and full-bar plugins read-only (placement, configured and running bar, declared settings) with an "Edit in bar editor" deep link.
4. Runs Add, Update, Remove, and Clone through the existing Omarchy commands, in a terminal where those commands prompt, and reconciles the catalog afterwards.

Claim: `shell.plugin:<id>`, exclusive per plugin (sheet H). A lifecycle plan for a plugin with a `bar` or `bar-widget` kind also claims `shell.bar`, because `omarchy-plugin-remove` and `omarchy-plugin-clone` mutate the bar layout through the shell on their own (`bin/omarchy-plugin-remove:95-97`, `bin/omarchy-plugin-clone:159`).

### What the first release refuses to do

- Write anything under the `bar` subtree of `shell.json`: no placement, no moves, no inline settings, no `bar.id`. The bar module owns all of it (sheet H).
- Write `~/.config/omarchy/shell.json` from the backend. The two module writes go through `omarchy-shell shell setPluginEnabled`.
- Render an editable settings form for any plugin. Settings are shown as metadata. A form becomes editable for non-bar entries only when an upstream `patchPluginEntry` exists.
- Infer settings from QML, run plugin code, or resolve a `settingsForm` name dynamically.
- Pass `--yes` or `--enable` to any lifecycle command.
- Claim a plugin is healthy. The shell keeps no persistent load-error record (section 3.6).
- Show a remote URL derived from anything but `git config --get remote.origin.url` on a git checkout.
- Edit the weather location file. The weather popup already does this (`shell/plugins/panels/weather/Panel.qml:188-258`); no module owns it in the first release.

## 2. Ownership boundary with the bar module

Fixed by sheet H. Summary of what it means for this page:

| Concern | Owner | This page |
|---|---|---|
| `plugins[]`, `disabledPlugins[]` | `plugins` | enable and disable toggles |
| `bar.id`, `position`, `transparent`, `centerAnchor`, every `layout` entry and its inline settings | `bar` | read-only display; `requestNavigate("bar", {selectBar: id})` or `{select: {section, index}}` |
| Add, Update, Remove, Clone, Validate | `plugins` | actions |
| Schema normalizer, `SchemaForm.qml`, `spacerSettings@1`, `weatherSettings@1` | `core` (sheet F) | this plan carries the specification in section 6 because it was derived here; the code lives in core and the bar module is its first consumer |
| Join of `listPlugins`, `omarchy-plugin-catalog`, and manifest reads | `core/catalog.py` (sheet F) | this module adds origin classification and capabilities on top |

## 3. Verified Omarchy behavior

### 3.1 Discovery and listing

- `omarchy plugin list --json` and `omarchy-plugin-list --json` are the same command. There is no `bin/omarchy-plugin`. The `bin/omarchy` dispatcher builds the route `omarchy plugin list` from `# omarchy:group=plugin` (`bin/omarchy-plugin-list:4`) and the filename stem (`bin/omarchy:255-269`), then `exec`s the binary with the remaining args (`bin/omarchy:1045`). The binary prints `omarchy-shell shell listPlugins` unchanged when `--json` is given (`bin/omarchy-plugin-list:28-33`). Core `catalog.py` calls the IPC directly; the acceptance test compares against `omarchy-plugin-list --json` because that is what the master plan names.
- `listPlugins` rows have exactly `id`, `name`, `kinds`, `enabled`, `active`, `canDisable`, `firstParty`, `clonedFrom` (`shell/shell.qml:952-992`). `enabled` means: for a `bar` kind, whether it is the running bar; for a `bar-widget` kind, whether it sits in `bar.layout`; otherwise `isEnabled` (`:965-968`). `canDisable` is `false` for anything with kind `bar` (`:975`). Rows are sorted by name, then id (`:982-989`).
- `omarchy-plugin-catalog` is a hidden command (`bin/omarchy-plugin-catalog:5`). It walks `$OMARCHY_PATH/shell/plugins` at depth 2 to 4 (`:19`) and `~/.config/omarchy/plugins/*/manifest.json` following symlinks, skipping dot directories (`:25-26`). It emits `id`, `name`, `description`, `kinds`, `firstParty` (computed as `id` starts with `omarchy.`), `manifestPath`, `sourceDir`, `entryPoints`, `barWidget`, `bar`, `barWidgetPath`, `barPath` (`:39-58`), drops rows with an empty id (`:59`), and dedups by id (`:61`). It does not emit `version`, `author`, `license`, or `keepLoaded`. It does not validate anything, so a manifest the shell rejected still appears.
- The clean checkout has 37 manifests. Four carry `barWidget.schema` (`omarchy.agents`, `omarchy.indicators`, `omarchy.dropbox`, `omarchy.tailscale`). Two carry `barWidget.settingsForm` (`omarchy.spacer` at `shell/plugins/bar/widgets/Spacer.manifest.json:19`, `omarchy.weather` at `shell/plugins/panels/weather/manifest.json:19`). Two declare more than one kind (`omarchy.menu`: `menu`, `bar-widget`; `omarchy.media`: `service`, `bar-widget`). Field types present: `boolean`, `enum`, `integer`, `multiselect`, `path`, `string`. Bounds use `min`, `max`, `step`, `defaultValue`.
- Manifests carry fields the registry never looks at: `license` and `activation` on `shell/plugins/agents/manifest.json`, `license` on dropbox and tailscale, `barWidget.aliases` on agents, `noSelectionText`, `placeholderText`, `emptyText` on the Indicators multiselect field. `validateManifest` checks only `schemaVersion`, the five required fields, id characters, `kinds`, `entryPoints`, `barWidget.defaultSection`, and entry-point path shape (`shell/services/PluginRegistry.qml:43-91`) and returns the manifest object whole, so unknown keys survive into `installedPlugins`. A `customizationCenter` key would survive the same way.

### 3.2 Enablement by kind

All rules are in `shell/services/PluginRegistry.qml`.

- `isEnabled` (`:123-139`): a `bar` kind is enabled when `bar.id` (missing means `omarchy.bar`) equals its id. Anything listed in `disabledPlugins[]` is disabled (`:135`). Any other first-party plugin is enabled (`:136`). Anything else is enabled when `findEntryLocation` finds it in `bar.id`, `bar.layout.*`, or `plugins[]` (`:206-223`).
- `inBar` (`:164-167`) is placement only. The comment at `:159-163` says why: a built-in widget stays loadable so it can be put back, and `omarchy.menu` cannot be locked out by removing its button.
- `setEnabled(id, value, placement)` (`:449-542`), the parts this module relies on:
  - Enabling a first-party plugin whose clone is active restores the source first (`:478-484`).
  - `bar` kind: returns after writing or clearing `bar.id` (`:486-493`), so a manifest with both `bar` and `bar-widget` is a bar option and nothing else. The menu test states the same (`test/shell.d/menu-plugin-test.sh:145-146`).
  - Third-party non-widget, enable: `plugins.push({id})` (`:516-517`). First-party non-widget, enable: only `removeDisabled` (`:500`).
  - Clone with a non-widget kind, enable: source is added to `disabledPlugins[]` and remembered in `cloneSourceRestores[]` (`:523-526`).
  - Disable: a clone restores its source (`:530`, `:416-447`); a `plugins[]` entry is spliced (`:532`); a first-party non-widget is added to `disabledPlugins[]` (`:536`). A widget's layout entry is spliced with its settings (`:531`), which is why widget disable belongs to the bar module.
- `setPluginEnabled <id> <"true"|other>` returns `ok` or `unknown` (`shell/shell.qml:907-909`). With no placement argument it is exactly what this module needs for non-bar kinds. `omarchy-plugin-disable` uses the same call (`bin/omarchy-plugin-disable:22`).
- Third-party ids in the `omarchy.*` namespace or shadowing a first-party id are dropped at scan time with a console warning (`shell/services/PluginRegistry.qml:599-607`). `omarchy-plugin-validate` refuses them earlier (`bin/omarchy-plugin-validate:53`).

### 3.3 Full bar selection and fallback (display only)

`shell/shell.qml:167-174` derives `selectedBarId` from `bar.id`, defaulting to `omarchy.bar`. `activeBarId` (`:180`) falls back to `omarchy.bar` when the selected bar is unavailable or equals `failedBarId`. `failedBarId` is set when the plugin bar loader errors (`:253-259`) and cleared when the selection changes (`:188`). It is not persisted and not exposed over IPC; `listPlugins[].active` is the only IPC view of it. "Configured bar" comes from `listShellConfig`, "running bar" from the row with `active: true`, and fallback is their disagreement. This page shows the banner; the bar module changes the bar.

### 3.4 Clones

`bin/omarchy-plugin-clone <source-id> [--edit]` has no confirmation prompt. It requires a first-party source (`:120-128`), creates `~/.config/omarchy/plugins/<username>.<id-without-omarchy.>` (`:131-133`), copies the entry points and `omarchy.clonePaths` (`:16-51`), rewrites `id`, `name` to `My <name>`, `barWidget.displayName`, and stamps `omarchy.clonedFrom` (`:53-80`), rescans and polls `omarchy-plugin-list --json` up to 2 s for the new id (`:149-158`), enables it (`:159`), sends a notification (`:161-163`), and with `--edit` execs `$EDITOR` on the directory (`:165-168`). Omarchy's own menu always runs it with `--edit` in a terminal (`bin/omarchy-menu-plugin:39-41`).

Consequence: "Clone" without editing is a non-interactive command and the center runs it with `RunCommand` after a named confirmation. "Clone and edit" needs a terminal.

### 3.5 Lifecycle commands

- Add (`bin/omarchy-plugin-add`): args `[git-url] [--enable] [--yes]` (`:5`). Without a TTY and without `--yes`, every `confirm` fails (`:26-34`). Prompts for the URL if absent (`:89-94`), runs `omarchy-git-url-check` (`:101`), prints the unsandboxed-code warning and asks to continue (`:103-114`), clones into `.add.tmp.$$` (`:118-123`), validates (`:125-128`), rejects an id already in the catalog (`:130-138`), moves into place (`:140-147`), rescans (`:149`), then asks "Enable '<id>' now?" (`:151-159`) and, for a bar widget, which section (`:38-53`). The center never passes `--enable`; the user may still answer yes in the terminal.
- Update (`bin/omarchy-plugin-update [id] [--yes]`): requires a `.git` directory (`:111-112`), fetches `origin HEAD` (`:43`), shows the diff with `delta` when present (`:53-59`), asks to confirm (`:61`), fast-forwards only (`:67-70`), validates and `reset --hard ORIG_HEAD` on failure (`:72-76`), rescans if anything updated (`:130-132`).
- Remove (`bin/omarchy-plugin-remove [id] [--yes]`): validates the id (`:32-34`, `:69`), reads `was_enabled` from `listPlugins` (`:74-80`), reads `clonedFrom` (`:82-85`), confirms with a message that depends on checkout type (`:87-93`), disables through IPC first (`:95-97`), then unlinks a symlink, `rm -rf`s a git checkout, or moves a plain directory to `.<id>.bak.<timestamp>` (`:99-115`), rescans (`:117`), and reports source restoration for a clone (`:119-123`).
- Validate (`bin/omarchy-plugin-validate <dir>`): read-only; checks `schemaVersion == 1` (`:41-42`), required fields (`:44-47`), id shape and reserved namespace (`:51-53`), non-empty `kinds` (`:56-57`), `entryPoints` object (`:60-61`), `defaultSection` (`:65-74`), each entry point relative, no `..`, no newline, exists (`:79-87`), one entry point per declared kind (`:97-109`), no symlinks outside `.git` (`:115-116`). Because of `:53` it cannot run on first-party directories.
- The shell watches `~/.config/omarchy/plugins` with `inotifywait` and reloads a changed plugin on its own (`shell/services/PluginRegistry.qml:636-655`, `shell/shell.qml:766-772`), so the catalog changes even before a command's explicit rescan.

### 3.6 Load errors

`pluginLoadFailed(id, error)` is emitted only from `loadPluginWidget` when a bar-widget component errors (`shell/shell.qml:796-806`). Nothing stores it, and `listPlugins` has no error field. A full bar failure sets `failedBarId` (`:258`) and logs to the console. Panel, overlay, menu, and service failures are console warnings only. The center can show manifest-level diagnostics it computes, a bar fallback inferred from `active`, and widget errors observed while the overlay was open. It cannot show "healthy".

### 3.7 IPC transport

`bin/omarchy-shell` runs `qs ipc -n -p $OMARCHY_PATH/shell call -- <target> <method> [args]` under `timeout` (default 2 s, `OMARCHY_SHELL_IPC_TIMEOUT`, `:58-59`). Exit 124 or 137 becomes "not responding", any other non-zero exit becomes "not running" (`:62-66`), and `Target not found.`, `Function not found.`, `Too few/many arguments`, and `Not ready to accept queries yet` are turned into exit 1 (`:68-77`). Every other reply, including `unknown`, comes back on stdout with exit 0 (`:55-57`). Sheet B's `ShellIpc` maps these; this module only sees `ipc_rejected`, `runtime_unavailable`, and `unsupported_config`.

### 3.8 Settings metadata at runtime

`shell/shell.qml:686-698` copies `displayName`, `description`, `category`, `allowMultiple`, `defaults`, `settingsForm`, and `schema` into the bar widget registry. No file in the checkout reads `schema`, `settingsForm`, or `defaults` back out; the comment at `:709-711` refers to a settings panel that is not in this tree. Widgets receive the raw entry minus `id` as `settings` (`shell/plugins/bar/BarModel.js:10-18`) and read keys with `setting(name, fallback)` (`shell/Ui/BarWidget.qml:41`). So the manifest `defaultValue` and `barWidget.defaults` are documentation, not runtime behavior; the runtime default is whatever the widget's QML falls back to.

### 3.9 The two named forms

- `spacerSettings`: `shell/plugins/bar/widgets/Spacer.qml:8` reads `settings.size` as a number, default 12. `:12` hides the widget when `span <= 0`. `allowMultiple: true` (`Spacer.manifest.json:18`).
- `weatherSettings`: `shell/plugins/panels/weather/Panel.qml:138` reads `unit` (empty string means locale decides), `:141` reads `refreshMinutes` (parsed as int, minimum 1, default 15). Location is not an entry key. It lives in `~/.local/state/omarchy/settings/weather.json` as `{"name", "latitude", "longitude"}`, written by `omarchy-weather-location --set <name> [lat,lon]` or cleared with `--clear` (`bin/omarchy-weather-location:12-13`, `:28-40`). The panel calls that command from its popup (`Panel.qml:253-257`) and reads the file through a `FileView` (`:95-96`).

## 4. Catalog record

### 4.1 Read pipeline for `status`

`MODULE.status(ctx)` returns `{revision, rows, shell, pendingHandoffs, diagnostics}`.

1. `core.catalog.read(ctx)` (sheet F) does the shell ping, `listPlugins`, `listShellConfig`, `omarchy-plugin-catalog`, the join, and manifest reads. It returns `runtime_unavailable` when the shell is down; then `rows` is empty and `diagnostics.undiscovered` lists what the catalog found on disk. No static row is ever promoted to an actionable row. A catalog failure is warning `plugins_catalog_unavailable`; rows still render from `listPlugins` with `origin.sourceDir = null`. A catalog row with no runtime row goes to `diagnostics.undiscovered[]`, never to `rows`. A manifest whose path is outside `$OMARCHY_PATH/shell/plugins/` or `~/.config/omarchy/plugins/<id>/` after `realpath`, or whose `id` differs from the row, is diagnostic `plugins_manifest_mismatch` and the row keeps runtime fields only. All of this is core's join; the requirements are restated here so the module's tests can assert them through the module.
2. `revision = "sha256:" + sha256(canonical listPlugins + "\n" + canonical listShellConfig)`, computed by core and passed through.
3. For a user plugin, `lstat(~/.config/omarchy/plugins/<id>)`: symlink, git checkout (`.git` directory present), or plain directory. For a git checkout, `ctx.commands.run(["git", "-C", dir, "config", "--get", "remote.origin.url"], timeout_s=2)`; strip userinfo, and if the value still contains `token`, `ghp_`, `glpat`, or `x-access-token`, replace it with `"<redacted>"`. Memoized in `ctx.cache`.
4. Derive `instances[]` for every `bar-widget` row from `listShellConfig.bar.layout.{left,center,right}`: `{section, index, entry}` with the entry copied whole; a string-form entry becomes `{section, index, entry: {"id": s}, legacyString: true}`. Display only.
5. Derive `state`, `settings`, `capabilities`, `diagnostics` per the rules below. `settings` uses `core.settings_schema.normalize(manifest)`.
6. Attach `pendingHandoffs` from the transaction journal: every transaction of this module in state `pending_handoff` (sheet B, E).
7. Return.

`status` never writes. If the catalog subprocess takes longer than 5 s core cancels it and reports it unavailable.

### 4.2 Record fields

| Field | Type | Source |
|---|---|---|
| `id` | string | `listPlugins.id` |
| `name` | string | `listPlugins.name` |
| `description` | string or null | manifest via catalog |
| `version` | string or null | manifest (catalog omits it) |
| `author` | string or null | manifest (`omarchy.osd` has none) |
| `license` | string or null | manifest, optional and unvalidated |
| `kinds` | string[] | `listPlugins.kinds` |
| `keepLoaded` | boolean | manifest `keepLoaded === true` |
| `entryPoints` | object | catalog |
| `firstParty` | boolean | `listPlugins.firstParty` |
| `clonedFrom` | string or null | `listPlugins.clonedFrom`, empty string mapped to null |
| `self` | boolean | `id == "firstpick.customization-center"` |
| `ownership` | `"plugins"` or `"bar"` | `bar` when `kinds` contains `bar` or `bar-widget`; decides whether this page can write |
| `origin.class` | `"omarchy-shipped"`, `"user-installed"`, `"user-clone"` | `firstParty`; else `clonedFrom` set; else user-installed |
| `origin.sourceDir`, `origin.manifestPath` | string or null | catalog |
| `origin.checkout` | `"bundled"`, `"git"`, `"directory"`, `"symlink"`, `"unknown"` | step 3 |
| `origin.symlinkTarget` | string or null | `readlink`, shown, never followed |
| `origin.remote` | string or null | step 3, sanitized |
| `state.enabled`, `state.active`, `state.canDisable` | boolean | `listPlugins` |
| `state.storage` | `"bar.id"`, `"bar.layout"`, `"plugins[]"`, `"disabledPlugins[]"`, `"implicit"` | section 5 |
| `state.configuredBar` | string | `listShellConfig.bar.id` or `"omarchy.bar"` |
| `state.runningBar` | string | the row with `active: true`, else `"omarchy.bar"` |
| `state.barFallback` | boolean | `configuredBar != runningBar` |
| `state.disabledByList` | boolean | `id` in `listShellConfig.disabledPlugins` |
| `state.activeCloneId` | string or null | for a first-party row, the enabled row whose `clonedFrom` is this id |
| `instances` | array | step 4; empty for non-widgets |
| `barWidget` | object or null | `{displayName, description, category, allowMultiple, defaultSection, defaults, settingsForm}` from catalog, each type-checked or null |
| `settings.support` | `"schema"`, `"adapter"`, `"schema+adapter"`, `"none"`, `"invalid"` | `core.settings_schema` |
| `settings.adapterId` | string or null | `"spacerSettings@1"`, `"weatherSettings@1"`, or null with diagnostic `plugins_unknown_settings_form` |
| `settings.fields`, `settings.fingerprint`, `settings.problems` | | `core.settings_schema` |
| `settings.extension` | object or null | a `customizationCenter` block, normalized with the same rules, always read-only |
| `diagnostics` | array | `{code, severity, message, path}`; section 14 |
| `capabilities` | string[] | section 4.4 |
| `validation` | object or null | result of `ccctl query plugins validate {id}` when the page asked for it; not part of plain status |

Top-level `shell`: `{available, configuredBar, runningBar, barFallback, pluginsDir}`. Top-level `pendingHandoffs`: `[{transactionId, action, pluginId, startedAt}]`.

### 4.3 Origin classes and their evidence

- Shipped with Omarchy: `firstParty` from the registry, meaning the manifest was found under `$OMARCHY_PATH/shell/plugins` (`PluginRegistry.qml:565`). Provenance, not a security statement.
- User-installed: found under `~/.config/omarchy/plugins/<id>/`. Show `checkout`, local path, sanitized remote. A symlink shows its target as text.
- Local clone: user-installed with `clonedFrom`. Show both ids and "replaces `<source>` while enabled".

### 4.4 Capabilities per row

Computed in the backend; QML renders what it receives.

| Capability | Condition |
|---|---|
| `enable` | `ownership == "plugins"`; not enabled; shell available; not `self` |
| `disable` | `ownership == "plugins"`; enabled; `canDisable`; shell available |
| `edit-in-bar-editor` | `ownership == "bar"`; the deep link payload is `{selectBar: id}` for a `bar` kind, `{select: {section, index}}` for a placed widget (first instance; the picker in the bar module handles the rest), `{addWidget: id}` for an unplaced widget |
| `add` | on the page, not a row; shell available |
| `update` | `origin.checkout == "git"` |
| `remove` | `origin.class != "omarchy-shipped"` |
| `clone` | `firstParty`; no row has `clonedFrom == id` |
| `clone-edit` | as `clone` and `$EDITOR` is set in the environment `ccctl` sees |
| `validate` | `origin.class != "omarchy-shipped"` and `checkout != "symlink"` |
| `open-source` | `origin.sourceDir` exists |
| `view-diagnostics` | `diagnostics.length > 0` |

`self` rows keep `disable`, `update`, and `remove`, each with `closesCenter: true`, which the UI turns into a confirmation that says the overlay will close.

### 4.5 Revision

`revision` covers `listPlugins` and `listShellConfig`, so a plugin added by hand, a bar drag, or a `reloadConfig` all invalidate a draft. The executor compares it before running the plan. `setPluginEnabled` is idempotent, so the remaining window between compare and IPC cannot produce a wrong write, only a redundant one.

## 5. Enable and disable by kind

One row, one plugin-unit operation, never per-kind toggles.

| Plugin shape | Shown as | This page writes | Storage | Verify |
|---|---|---|---|---|
| Has kind `bar` | "Bar in use" or "Available bar"; fallback banner when configured and running differ | nothing; "Edit in bar editor" with `{selectBar: id}` | `bar.id` | n/a |
| Has kind `bar-widget` (with or without other kinds) | "On bar (n)" or "Not on bar"; kind chips for the other kinds; for first-party rows the note "the built-in `<kind>` stays available when the button is removed" | nothing; "Edit in bar editor" | `bar.layout` | n/a |
| First-party, no `bar`, no `bar-widget` | "Available" or "Switched off" | `setPluginEnabled <id> true|false` | `disabledPlugins[]` | `enabled` and `disabledByList` agree |
| Third-party, no `bar`, no `bar-widget` | "Enabled" or "Disabled" | `setPluginEnabled <id> true|false` | `plugins[]` | `enabled` and presence in `plugins[]` agree |
| Clone of a non-widget, non-bar plugin | as its shape plus "replacing `<source>`" | `setPluginEnabled`; the registry disables the source on enable (`:523-526`) and restores it on disable (`:530`) | `plugins[]` plus `cloneSourceRestores[]` | as its shape, and the source row flips back |
| Clone of a widget or bar | as its shape | nothing; deep link | bar subtree | n/a |

Enabling a first-party non-widget whose clone is active makes the registry restore the source and drop the clone from `plugins[]` (`:478-484`). The plan's summary says "Switch back to the built-in `<name>`; `<clone>` stays installed". Its inverse is `setPluginEnabled <clone> true`.

Self row: disabling `firstpick.customization-center` removes it from `plugins[]`, which unloads the overlay. The executor is a separate process and completes and verifies on its own. The confirmation says "The Customization Center will close. Re-enable it with `omarchy plugin enable firstpick.customization-center`" and the page closes the overlay before the apply call returns.

## 6. Specification handed to core

This section is the specification for `backend/customization_center/core/settings_schema.py`, `core/SchemaForm.qml`, `core/SchemaField.qml`, and the two named-form adapters (sheet F). The bar module uses them to edit inline settings. This module uses them only to render read-only metadata (section 12.3). The text stays here because the source analysis behind it is in section 3; core's own docs should link to it.

### 6.1 Normalized schema

`schemas/settings-schema-v1.json` (cross-module, next to `transaction-v1.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "settings-schema-v1.json",
  "type": "object",
  "required": ["version", "scope", "fields"],
  "additionalProperties": false,
  "properties": {
    "version": { "const": 1 },
    "scope": { "enum": ["bar-widget-entry", "shell-entry"] },
    "fields": { "type": "array", "items": { "$ref": "#/$defs/field" } }
  },
  "$defs": {
    "field": {
      "type": "object",
      "required": ["key", "type", "label"],
      "additionalProperties": false,
      "properties": {
        "key": { "type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$", "not": { "enum": ["id", "type", "exec", "source"] } },
        "type": { "enum": ["boolean", "integer", "string", "path", "enum", "multiselect"] },
        "label": { "type": "string", "minLength": 1, "maxLength": 80 },
        "description": { "type": "string", "maxLength": 500 },
        "defaultValue": {},
        "defaultSource": { "enum": ["field", "barWidget.defaults"] },
        "min": { "type": "integer" },
        "max": { "type": "integer" },
        "step": { "type": "integer", "minimum": 1 },
        "options": {
          "type": "array", "minItems": 1,
          "items": {
            "type": "object", "required": ["value", "label"], "additionalProperties": false,
            "properties": { "value": { "type": "string" }, "label": { "type": "string" }, "description": { "type": "string" } }
          }
        },
        "ui": {
          "type": "object", "additionalProperties": false,
          "properties": { "noSelectionText": { "type": "string" }, "placeholderText": { "type": "string" }, "emptyText": { "type": "string" } }
        }
      },
      "allOf": [
        { "if": { "properties": { "type": { "const": "integer" } } }, "then": { "properties": { "defaultValue": { "type": "integer" } } } },
        { "if": { "properties": { "type": { "const": "boolean" } } }, "then": { "properties": { "defaultValue": { "type": "boolean" } } } },
        { "if": { "properties": { "type": { "enum": ["string", "path"] } } }, "then": { "properties": { "defaultValue": { "type": "string" } } } },
        { "if": { "properties": { "type": { "const": "enum" } } }, "then": { "required": ["options"], "properties": { "defaultValue": { "type": "string" } } } },
        { "if": { "properties": { "type": { "const": "multiselect" } } }, "then": { "required": ["options"], "properties": { "defaultValue": { "type": "array", "items": { "type": "string" }, "uniqueItems": true } } } }
      ]
    }
  }
}
```

Enforced by the normalizer beyond the JSON Schema: `min <= max`; `defaultValue` within bounds; `enum` and `multiselect` defaults are declared option values; option values unique per field; keys unique per schema; `key` is never `id` (stripped by the bar), `type`, `exec`, or `source` (custom-module keys, `docs/omarchy-shell.md:379-397`).

No conditional visibility. No manifest declares any, and a hidden field raises a question (keep or delete its value?) that `setBarWidget` cannot answer because it cannot delete. Fields render flat, in manifest order.

### 6.2 Normalization from the manifest dialect

Input `barWidget.schema`. Output the normalized document or `support: "invalid"` with `problems[]`.

1. Absent or `[]`: no fields; continue to adapters.
2. Not an array: `plugins_schema_not_array`; invalid.
3. Per element, in order: not an object, `plugins_field_not_object`, skip. `key` missing, wrong shape, reserved, or duplicate, `plugins_field_bad_key`, skip. `type` outside the six, `plugins_field_unknown_type`, kept in `problems` with the type string, not in `fields`. `label` missing, use `key`. `description` if a string. Aliases `minimum`, `maximum`, `default` accepted when the canonical name is absent, recorded as `plugins_field_alias_used`. `min`, `max`, `step` only for `integer`; numeric strings coerced; other non-integers dropped with `plugins_field_bad_bound`. `options` only for `enum` and `multiselect`; strings become `{value, label: value}`; objects need a string `value`; bad elements dropped with `plugins_field_bad_option`; none left, `plugins_field_no_options`, skip. `defaultValue` type-checked, dropped on mismatch with `plugins_field_bad_default`; absent and `barWidget.defaults[key]` type-checks, use it with `defaultSource: "barWidget.defaults"`. `noSelectionText`, `placeholderText`, `emptyText` copied into `ui`. Every other property dropped and listed as `plugins_field_extra_ignored`.
4. `support` is `schema` when at least one field survived and no field was skipped; `invalid` when any field was skipped; else `none`. A skipped field invalidates the whole schema because a partial form could write a value another field depends on.

Fingerprint: `sha256` of the canonical JSON of `{fields, adapterId}`.

### 6.3 Rendering rules

Controls from `shell/Ui/` (verified: `TextField.qml`, `NumberField.qml`, `Dropdown.qml`, `SearchableDropdown.qml`, `MultiSelect.qml`, `ToggleSwitch.qml`). Each row: label, control, description in `Color.foreground.muted`, state chip.

| Type | Control | Absent key shows | Validation | Written value |
|---|---|---|---|---|
| `boolean` | `ToggleSwitch` | `defaultValue` or off, chip "Default" | none | `true`/`false` |
| `integer` | `NumberField` bound to `min`, `max`, `step` | `defaultValue` or empty | integer within bounds; step misalignment is a warning because `omarchy bar set` never enforced it | number |
| `string` | `TextField` | `defaultValue` or empty | string | string |
| `path` | `TextField` | as string | no existence check, no `~` expansion, no shell syntax | string as typed |
| `enum` | `Dropdown` up to 8 options, else `SearchableDropdown` | `defaultValue` or "Not set" | value in options | string |
| `multiselect` | `MultiSelect` with the `ui` strings | `defaultValue` or empty with `noSelectionText` | every value declared, no duplicates, declared order | string array |

Chips: "Default" (absent), "Set", "Changed", "Invalid" (existing value fails validation; shown raw in a disabled `TextField` with a Replace button). `SchemaForm` has a `readOnly` property; when true every control is disabled and chips still render. Labels for value state: "Set to 30", "Not set (declared default 60)", "Not set (widget default 12)". There is no "Reset" that removes a key; the bar module offers key deletion through its file route (sheet H), and the form exposes a `requestDeleteKey(key)` signal for it.

### 6.4 Named-form adapters

Exactly two, because the checkout declares exactly two form names. An adapter contributes normalized fields and declares `ownership`; only `inline-entry` fields may feed a bar entry.

`spacerSettings@1`, `ownership: inline-entry`. Field `size`: `integer`, label "Size (px)", `min: 0`, `max: 4096`, `step: 1`, `defaultValue: 12` (`Spacer.qml:8`), description "0 hides the spacer" (`Spacer.qml:12`). The upper bound is the center's choice. Retire the adapter when `Spacer.manifest.json` declares a schema.

`weatherSettings@1`, `ownership: inline-entry` for two fields; location is `external` and no module writes it in the first release. Field `unit`: `enum`; the accepted strings depend on `Model.shouldUseImperial` in `shell/plugins/panels/weather/Model.js`, which was not read for this plan; the implementer copies the comparison from there before freezing option values, and until then the field is read-only. Field `refreshMinutes`: `integer`, `min: 1`, `max: 1440`, `step: 1`, `defaultValue: 15` (`Panel.qml:141`). External: `{path: ~/.local/state/omarchy/settings/weather.json, exists, name, latitude, longitude}` for display, with the text "Change the location from the weather popup".

### 6.5 Proposed manifest extension

```json
{ "customizationCenter": { "settingsVersion": 1, "scope": "shell-entry",
    "schema": [ { "key": "interval", "type": "integer", "label": "Refresh interval", "min": 5, "max": 3600, "defaultValue": 60 } ] } }
```

The registry tolerates the key (section 3.1). This module normalizes it with the same rules and renders it read-only with "No write path for `plugins[]` settings exists in this Omarchy version". Editing starts when Omarchy provides `patchPluginEntry <id> <patchJson> <deleteKeysJson> <expectedHash>`; that request goes in the master plan's upstream table. The dialect is `min`, `max`, `defaultValue`, not the master plan's `minimum`/`maximum`/`default` example.

## 7. Draft schema

`modules/plugins/schemas/draft-v1.json`. A draft is a list of changes applied in one transaction; a lifecycle change must be alone.

```json
{
  "version": 1,
  "module": "plugins",
  "baseRevision": "sha256:...",
  "changes": [
    { "kind": "enable", "pluginId": "acme.service" },
    { "kind": "disable", "pluginId": "omarchy.nightlight" },
    { "kind": "lifecycle", "action": "add" },
    { "kind": "lifecycle", "action": "update", "pluginId": "acme.widget" },
    { "kind": "lifecycle", "action": "remove", "pluginId": "acme.widget" },
    { "kind": "lifecycle", "action": "clone", "pluginId": "omarchy.clock", "edit": false }
  ]
}
```

`validate` enforces: `pluginId` matches `^[A-Za-z0-9][A-Za-z0-9._-]*$` with no `..` (the check in `bin/omarchy-plugin-remove:32-34`, which also satisfies sheet B's argv token rule); each id at most once; `enable` and `disable` only for rows with `ownership == "plugins"` (`plugins_bar_owned` otherwise, with the deep-link payload in `details`); a lifecycle change is alone (`plugins_lifecycle_not_alone`); the row has the needed capability (`plugins_capability_missing`); `clone` with `edit: true` requires `clone-edit`.

## 8. Plan

`MODULE.plan(ctx, draft, status)` orders disables before enables, so a clone's source restoration and a re-enable of that source never interleave. Every operation carries `summary`, `claims`, and `inverse` (sheet B shapes).

| Change | Operation | Inverse |
|---|---|---|
| `enable` | `ShellIpc("setPluginEnabled", [id, "true"])` | `ShellIpc("setPluginEnabled", [id, "false"])` |
| `enable` of a first-party source whose clone is active | same; summary adds "and stops using `<clone>`" | `ShellIpc("setPluginEnabled", [cloneId, "true"])` |
| `disable` | `ShellIpc("setPluginEnabled", [id, "false"])` | `ShellIpc("setPluginEnabled", [id, "true"])` |
| `disable` of a clone | `ShellIpc("setPluginEnabled", [cloneId, "false"])` | `ShellIpc("setPluginEnabled", [cloneId, "true"])` |
| `lifecycle add` | `TerminalHandoff(["omarchy-plugin-add"], "Add plugin")` | `None` |
| `lifecycle update` | `TerminalHandoff(["omarchy-plugin-update", id], "Update <id>")` | `None` |
| `lifecycle remove` | `TerminalHandoff(["omarchy-plugin-remove", id], "Remove <id>")` | `None` |
| `lifecycle clone`, `edit: false` | `RunCommand(["omarchy-plugin-clone", id], timeout_s=60, expect_exit=0, capture_limit=65536)` | `None`; summary "Creates `~/.config/omarchy/plugins/<user>.<x>/` and switches to it. Undo by removing the clone." |
| `lifecycle clone`, `edit: true` | `TerminalHandoff(["omarchy-plugin-clone", id, "--edit"], "Clone <id>")` | `None` |

Claims: `shell.plugin:<id>` on every operation; lifecycle operations for a row with `ownership == "bar"` add `shell.bar`. `TerminalHandoff` uses `wrapped: true` (sheet B). Every `None` inverse forces the shared confirmation; the texts are fixed in `modules/plugins/backend/messages.py`.

Validate is not a plan. `ccctl query plugins validate {id}` runs `RunCommand(["omarchy-plugin-validate", dir])` read-only and returns `{exit, stderr}`; `module.json` lists `validate` under `queries` (sheet J).

## 9. Verify

`MODULE.verify(ctx, plan, status_after)`:

- `enable`/`disable`: the row's `state.enabled` equals the target; `state.storage` shows the expected list membership. For a clone enable, the source row is disabled; for a clone disable, the source row is enabled again.
- `clone` via `RunCommand`: after exit 0, poll `listPlugins` up to 3 s for the new id (the command polls 2 s itself, `:151-157`); the new row has `clonedFrom == source` and `enabled: true`; the source row is not enabled (or, for a widget source, not in the bar).
- `TerminalHandoff`: the transaction sits in `pending_handoff`. `ccctl reconcile` (sheet B) reads `$XDG_STATE_HOME/omarchy/customization-center/handoffs/<txid>.json`; exit 0 leads to `status` plus this `verify`, which checks only that `status` succeeded and that the affected id is present (add, update, clone) or absent (remove) as appropriate; a non-zero exit records `handoff_failed`.

Verification never reads `~/.config/omarchy/shell.json` on disk; `listShellConfig` is the truth.

## 10. Terminal handoff

Sheet B fixes the mechanism: core launches `omarchy-launch-floating-terminal-with-presentation` with `<absolute path to backend/cc-handoff> <txid> <argv...>` as positional parameters; `cc-handoff` runs `"$@"` and writes the sentinel on exit. What this module adds:

- Argv is always one of the five shapes in section 8; plugin ids satisfy the token rule.
- While `status.pendingHandoffs` is non-empty the page calls `BackendClient.pollStatus("plugins", 2000)`; `BackendClient` runs `ccctl reconcile` when a poll shows a sentinel for a pending transaction and stops polling 10 s after the last one resolves (the shell's inotify reload and the commands' own `rescanPlugins` land inside that window). A pending transaction older than 30 minutes shows "No result recorded" with a Dismiss that runs `ccctl rollback <txid> --reason user`, which records `skipped_nonreversible` and closes it.
- Exit codes and page text: 0 "Finished. Catalog refreshed."; 130 "Cancelled in the terminal."; add 1 "Not added. The terminal showed why." (validation, URL check, id collision, and an aborted confirm all exit 1); update 1 "Not updated. Fetch failed, the checkout has local changes, or validation rolled the update back."; remove 1 "Not removed."; clone non-zero "Clone failed. Nothing was switched." (the script's trap removes a half-made target, `:139-143`).

Add is the one flow whose outcome the page cannot fully describe, because the terminal asks whether to enable and where to place. After exit 0 the refreshed catalog shows the truth.

## 11. Trust presentation

Fixed text, asserted by tests:

- Shipped with Omarchy: chip "Omarchy". Detail: "Shipped with Omarchy under `$OMARCHY_PATH/shell/plugins`."
- User-installed: chip "Installed". Banner on the Overview tab, never dismissable: "This plugin runs as unsandboxed code inside omarchy-shell with your user's permissions. Omarchy does not verify or sign it." Then local path, checkout type, sanitized remote as copyable text.
- Clone: chip "Clone of `<source>`". Same banner plus "While enabled it replaces `<source>`. Disabling or removing it restores `<source>`."
- Symlink: as installed plus "Linked to `<target>`" and that Update is unavailable.

No row ever gets "trusted", "verified", or "safe". "Open source" runs `RunCommand(["xdg-open", dir])`; a remote URL is text only.

## 12. UI

### 12.1 Page structure

`modules/plugins/Page.qml` exposes the contract properties, `requestPlan`, `requestApply`, `requestReset`, `requestNavigate`, `focusFirst()`, and `handlePayload(payload)`. `handlePayload({select: "<id>", tab: "overview"|"placement"|"settings"|"diagnostics"})` selects a row and tab; `{action: "add"}` opens the Add confirmation.

- Header: "Plugins", shell chip, configured and running bar with a fallback banner when they differ (banner button: "Open in bar editor", `requestNavigate("bar", {selectBar: configuredBar})`), Refresh, Add.
- Filter row: search (id, name, description); chips All, Omarchy, Installed, Clones, On bar, Switched off, Bars, Has settings, Diagnostics.
- List: `components/PluginRow.qml`, sorted as the shell sorts.
- Detail pane (right at 900 px and wider, pushed page below): tabs Overview, Placement (widgets and bars), Settings (when `support != none` or an extension block exists), Diagnostics (when any).
- Handoff strip above the apply bar while `pendingHandoffs` is non-empty.
- The shared `ApplyBar`.

Selecting a row never changes the draft. Only the enable toggle on a `plugins`-owned row and the lifecycle actions do.

### 12.2 Page state machine

```text
loading -> ready | shell-unavailable
ready -> ready (refresh, filter, select, deep link out)
ready -> dirty (enable or disable toggled; lifecycle chosen)
dirty -> reviewing -> applying -> verifying -> committed -> ready
reviewing -> dirty (cancel)
applying | verifying -> rolled-back -> ready
applying | verifying -> rollback-failed
applying -> pending-handoff (lifecycle) -> ready (reconcile committed or rolled back, or Dismiss)
* -> stale (status revision != draft.baseRevision) -> ready (Reload) | dirty (Keep draft)
```

Exceptional states:

- `shell-unavailable`: rows empty; `diagnostics.undiscovered` lists what the catalog found on disk with "not loaded by the shell (shell not running)"; actions Retry and "Start shell" (`RunCommand(["omarchy-launch-shell"])`, present in `bin/`). No draft.
- `catalog-degraded`: rows from `listPlugins` alone; origin chips "unknown"; Settings tabs hidden; banner names `omarchy-plugin-catalog` and its stderr.
- `stale`: banner with Reload and Compare (Compare lists rows whose state changed since the draft base).
- `rollback-failed`: panel with transaction id, the operations that ran, the failed inverse and its IPC reply, and the manual commands `omarchy plugin enable|disable <id>`.
- `pending-handoff`: draft cleared; the rest of the page stays usable.

### 12.3 Tab contents

Placement tab (read-only): for a widget, every instance as `section[index]` with its inline keys; for a bar, configured and running state. One button, "Edit in bar editor", with the payload from section 4.4. For an unplaced widget the button reads "Add to bar in bar editor" with `{addWidget: id}`.

Settings tab (read-only): `core/SchemaForm.qml` with `readOnly: true`, rendering `settings.fields` against the first instance's entry (or against nothing when unplaced, chips all "Default"), the adapter heading when present ("Built-in Spacer settings, stored on the bar entry"), the extension block when present with the section 6.5 note, and for an invalid schema the problems list with the manifest path. Below the form: "Edit in bar editor" for `bar`-owned rows; "No write path in this Omarchy version" for `plugins`-owned rows with an extension block. Several instances: a note "n instances; values shown are for `section[index]`" and the deep link. A legacy string entry: "stored as a plain string; the bar editor can convert it".

Diagnostics tab: the row's diagnostics, the last `validate` query result with a "Run validation" button that calls `ccctl query plugins validate {id}` through `BackendClient.query`, and widget load errors observed this session labeled "Observed while this page was open".

### 12.4 Keyboard

`focusFirst()` focuses the search field. Tab order: search, filter chips, list, detail tabs, detail content, apply bar. In the list Up and Down move selection, Enter opens the detail. Every row action is in a menu reachable with `Shift+F10` or the Menu key. Confirmations use `ConfirmDialog` with the destructive button last and not default-focused.

## 13. Files

```text
modules/plugins/
├── module.json          # id "plugins", title "Plugins", navOrder 20, page "Page.qml", backend "modules.plugins.backend",
│                        #   schemas ["draft-v1.json"], queries ["validate"],
│                        #   coreServices ["BackendClient", "DraftStore", "TransactionModel", "settings_schema", "catalog"]
├── Page.qml
├── components/
│   ├── PluginRow.qml
│   ├── OriginChip.qml
│   ├── StateChip.qml
│   ├── TrustBanner.qml
│   ├── DetailOverview.qml
│   ├── DetailPlacement.qml
│   ├── DetailSettings.qml     # wraps core/SchemaForm.qml with readOnly: true
│   ├── DetailDiagnostics.qml
│   └── HandoffStrip.qml
├── backend/
│   ├── __init__.py            # exports MODULE
│   ├── module.py              # capabilities, status, validate, plan, verify, queries
│   ├── catalog.py             # origin classification, remote sanitizing, capabilities, on top of core.catalog
│   ├── kinds.py               # ownership and storage rules per kind
│   └── messages.py            # fixed confirmation and summary strings
├── schemas/
│   └── draft-v1.json
└── tests/
    ├── fixtures/
    ├── test_catalog.py
    ├── test_kinds.py
    ├── test_plan.py
    ├── test_verify.py
    ├── test_handoff.py
    └── test_integration.py
```

Paths through `ctx.paths`: `$OMARCHY_PATH/shell/plugins`, `~/.config/omarchy/plugins`, the handoff sentinel directory (core-owned). Commands through `ctx.commands`: `omarchy-shell` (via `ShellIpc`), `omarchy-plugin-validate`, `omarchy-plugin-clone`, `omarchy-plugin-add`, `omarchy-plugin-update`, `omarchy-plugin-remove` (via `TerminalHandoff`), `omarchy-launch-shell`, `git`, `xdg-open`.

## 14. Error and diagnostic codes

Module errors:

| Code | When |
|---|---|
| `plugins_unknown_plugin` | draft names an id not in status |
| `plugins_capability_missing` | draft asks for an action the row lacks; `detail` names it |
| `plugins_bar_owned` | enable or disable of a `bar`-owned row; `details.navigate` carries the deep-link payload |
| `plugins_lifecycle_not_alone` | a lifecycle change shares a draft |
| `plugins_self_action` | an action on the center's own row without `closesCenter` acknowledged |
| `plugins_clone_incomplete` | clone exited 0 but the new id did not appear within 3 s |

Shared codes this module raises through core: `ipc_rejected` (message carries the reply body), `runtime_unavailable`, `unsupported_config`, `stale_revision`, `handoff_failed`.

Diagnostics on rows:

| Code | Severity | Meaning |
|---|---|---|
| `plugins_catalog_unavailable` | warning | enrichment failed; page-level |
| `plugins_manifest_mismatch` | warning | manifest outside allowed roots or id differs |
| `plugins_undiscovered` | info | catalog row without a runtime row; page-level |
| `plugins_bar_fallback` | error | on the configured bar's row |
| `plugins_widget_load_error` | error | observed `pluginLoadFailed` this session |
| `plugins_unknown_settings_form` | info | `settingsForm` has no adapter |
| `plugins_schema_*`, `plugins_field_*` | info or warning | section 6.2 |
| `plugins_bar_and_widget` | info | manifest declares both; treated as a bar |
| `plugins_legacy_string_entry` | info | string-form layout entry |
| `plugins_symlink_checkout` | info | Update unavailable |
| `plugins_validation_failed` | warning | validate query exit 1 with stderr |

## 15. Test matrix

Fixtures under `modules/plugins/tests/fixtures/`; command stubs record argv and reply from a script.

- `listPlugins/clean-default.json`: the 37 first-party rows, `omarchy.bar` active.
- `listPlugins/third-party-mixed.json`: adds `acme.widget` (bar-widget, enabled), `acme.service` (service, disabled), `acme.bar` (bar, not active), `acme.both` (bar and bar-widget).
- `listPlugins/clone-active.json`: `tester.clock` with `clonedFrom: omarchy.clock` enabled; `omarchy.clock` disabled. `listPlugins/clone-service.json`: `tester.nightlight` enabled, `omarchy.nightlight` disabled.
- `listPlugins/bar-fallback.json`: `acme.bar` `enabled: false`, `active: false`, while config names it.
- `listPlugins/self.json`: adds `firstpick.customization-center`.
- `shellConfig/default.json` (copy of `config/omarchy/shell.json`), `disabled-builtins.json` (`disabledPlugins: ["omarchy.nightlight"]`), `third-party.json` (`plugins: [{"id":"acme.service"}]`, `acme.widget` at `right[2]`), `bar-third-party.json` (`bar.id: "acme.bar"`), `duplicate-indicators.json`, `spacer-with-size.json`, `legacy-strings.json`, `custom-modules.json`, `clone-service.json` (`cloneSourceRestores: ["tester.nightlight"]`).
- `catalog/clean-default.json`, `catalog/with-user.json`, `catalog/malformed.txt`, `catalog/unmatched-static.json`.
- `manifests/`: `agents.json`, `indicators.json`, `dropbox.json`, `tailscale.json`, `spacer.json`, `weather.json` copied from the checkout; `schema-duplicate-key.json`, `schema-unknown-type.json`, `schema-bad-bounds.json`, `schema-bad-default.json`, `schema-aliases.json`, `schema-not-array.json`, `id-mismatch.json`, `extension-block.json`, `no-author.json`.
- `plugins-dir/`: `acme.widget/` with a fake `.git`, `acme.local/` plain, `acme.linked` symlink, `tester.clock/` with `omarchy.clonedFrom`.
- `stubs/omarchy-shell` (scripted replies including `unknown`, `Function not found.` with exit 1, and a sleep past the timeout), `stubs/omarchy-plugin-catalog`, `stubs/omarchy-plugin-validate`, `stubs/omarchy-plugin-clone`, `stubs/git`, `stubs/omarchy-launch-floating-terminal-with-presentation`.

| Id | Area | Fixture | Assertion |
|---|---|---|---|
| PL-U-01 | catalog | `clean-default` | 37 rows; `configuredBar` and `runningBar` both `omarchy.bar` |
| PL-U-02 | catalog | catalog `unmatched-static` | extra row in `diagnostics.undiscovered`, not in `rows` |
| PL-U-03 | catalog | catalog `malformed.txt` | rows built; `plugins_catalog_unavailable`; no `origin.sourceDir` |
| PL-U-04 | catalog | `manifests/id-mismatch.json` | `plugins_manifest_mismatch`; `version` null |
| PL-U-05 | origin | `plugins-dir/*` | `git`, `directory`, `symlink` classified; symlink not followed; `https://user:token@host/x` becomes `https://host/x` |
| PL-U-06 | state | `disabled-builtins` | `omarchy.nightlight` `enabled: false`, `storage: disabledPlugins[]`, `disabledByList: true` |
| PL-U-07 | state | `third-party` | `acme.service` storage `plugins[]`, ownership `plugins`; `acme.widget` ownership `bar`, one instance at `right[2]` |
| PL-U-08 | state | `bar-fallback` + `bar-third-party` | `barFallback: true`; `acme.bar` row has `plugins_bar_fallback` |
| PL-U-09 | state | `clone-active` | `omarchy.clock.activeCloneId == tester.clock`; `tester.clock` is `user-clone`, ownership `bar` |
| PL-U-10 | capabilities | `third-party-mixed` | `acme.both` and `acme.bar` have only `edit-in-bar-editor` with `{selectBar}`; `acme.widget` has `edit-in-bar-editor` with `{select: {section: "right", index: 2}}`; `acme.service` has `enable` |
| PL-U-11 | capabilities | `self.json` | `disable` and `remove` carry `closesCenter` |
| PL-U-12 | settings (core) | `manifests/agents.json` | 5 fields; `syncDir` is `path`; no default from `barWidget.defaults` |
| PL-U-13 | settings (core) | `manifests/indicators.json` | multiselect with 6 object options; `ui.noSelectionText` copied |
| PL-U-14 | settings (core) | `schema-aliases.json` | aliases accepted; `plugins_field_alias_used` |
| PL-U-15 | settings (core) | the five invalid schema fixtures | each yields the named code; `schema-bad-default` drops only the default and stays `schema` |
| PL-U-16 | settings (core) | `spacer.json`, `weather.json`, `settingsForm: "mystery"` | `spacerSettings@1` one integer field default 12; `weatherSettings@1` two fields plus external; `mystery` gives `none` with `plugins_unknown_settings_form` |
| PL-U-17 | settings | `extension-block.json` | `settings.extension` normalized; row still has no `enable`-independent write capability |
| PL-U-18 | validate | enable on `acme.widget` | `plugins_bar_owned` with `details.navigate.select` |
| PL-U-19 | validate | lifecycle plus enable | `plugins_lifecycle_not_alone` |
| PL-U-20 | validate | id `../x` | `validation_failed` |
| PL-U-21 | plan | enable `acme.service` | `ShellIpc setPluginEnabled acme.service true`; inverse `false`; claim `shell.plugin:acme.service` |
| PL-U-22 | plan | disable `omarchy.nightlight` | `setPluginEnabled false`; inverse `true` |
| PL-U-23 | plan | `clone-service`: enable `omarchy.nightlight` | summary mentions `tester.nightlight`; inverse `setPluginEnabled tester.nightlight true` |
| PL-U-24 | plan | disable then enable in one draft | disables ordered first |
| PL-U-25 | plan | clone `omarchy.clock` without edit | `RunCommand ["omarchy-plugin-clone","omarchy.clock"]`, no `--edit`, no `--yes`, claims include `shell.bar` |
| PL-U-26 | plan | add, update, remove, clone-edit | `TerminalHandoff` argv exact, `wrapped: true`; `--yes` and `--enable` absent |
| PL-A-01 | ipc | stub replies `unknown` | `ipc_rejected` with body `unknown` |
| PL-A-02 | ipc | stub replies `Function not found.` exit 1 | `unsupported_config` |
| PL-A-03 | ipc | stub sleeps 6 s | `timeout` |
| PL-A-04 | ipc | non-JSON `listPlugins` | `malformed_output` |
| PL-A-05 | catalog | catalog stub exits 1 | warning, rows intact |
| PL-A-06 | query | validate stub exit 1 with stderr | `ccctl query plugins validate acme.local` returns `{exit: 1, stderr}`; nothing else changes |
| PL-A-07 | handoff | launcher stub | argv is `<cc-handoff path> <txid> omarchy-plugin-remove acme.widget`; no shell string contains the id |
| PL-I-01 | integration | fake shell, enable `acme.service` | `plugins[]` gains the entry; verify passes; journal has the op and inverse |
| PL-I-02 | integration | disable `omarchy.nightlight`, then `ccctl rollback` | `disabledPlugins[]` gains then loses the id |
| PL-I-03 | integration | `clone-service`: enable source | source enabled, clone gone from `plugins[]`; rollback re-enables the clone |
| PL-I-04 | integration | revision changed between plan and apply | `stale_revision`; no IPC call recorded |
| PL-I-05 | integration | clone stub creates dir, fake shell adds row | verify sees `clonedFrom` and source disabled |
| PL-I-06 | integration | clone stub exits 1 | transaction rolled back; no rows changed |
| PL-I-07 | integration | clone exits 0, fake shell never lists the id | `plugins_clone_incomplete` |
| PL-I-08 | integration | fake shell dies after the first of two ops | inverse attempted; `rollback_failed` with manual commands when it cannot reach the shell |
| PL-I-09 | integration | handoff, sentinel `{exitCode: 0}`, fake shell adds row | `reconcile` commits; status shows the row; `pendingHandoffs` empty |
| PL-I-10 | integration | handoff, sentinel `{exitCode: 1}` | `rolled_back` with reason `handoff_failed` |
| PL-I-11 | integration | handoff, no sentinel | stays `pending_handoff`; listed in status |
| PL-Q-01 | qml | states | loading, ready, shell-unavailable, catalog-degraded, stale, pending-handoff, rollback-failed render their banner text |
| PL-Q-02 | qml | selection | selecting rows and tabs produces no draft change and no backend call |
| PL-Q-03 | qml | settings read-only | all six field types render disabled from `manifests/*`; chips present; no field emits a change |
| PL-Q-04 | qml | deep links | Placement and Settings buttons emit `requestNavigate("bar", payload)` with the payloads of PL-U-10; fallback banner emits `{selectBar}` |
| PL-Q-05 | qml | handlePayload | `{select: "acme.service", tab: "diagnostics"}` selects the row and tab |
| PL-Q-06 | qml | trust | installed and clone rows show the banner verbatim; no "trusted" |
| PL-Q-07 | qml | keyboard | `focusFirst` on search; Tab order per 12.4; `Shift+F10` opens the row menu |
| PL-Q-08 | qml | confirmations | non-reversible plan shows the `messages.py` text; destructive button not default; self row text names the re-enable command |
| PL-L-01 | live | disposable Omarchy | enable and disable a first-party service and a third-party service; state survives `omarchy-restart-shell` |
| PL-L-02 | live | disposable Omarchy | a third-party bar with a syntax error: fallback banner; deep link opens the bar editor on that bar |
| PL-L-03 | live | disposable Omarchy | add through the page, answer "no" to enable; row appears disabled; `pendingHandoffs` clears |
| PL-L-04 | live | disposable Omarchy | clone `omarchy.nightlight` without edit; source shows replaced; remove the clone through the page; source returns |
| PL-L-05 | live | disposable Omarchy | update a git plugin with a pending commit; diff in the terminal; version changes after reconcile |
| PL-L-06 | live | disposable Omarchy | disable the center itself; overlay closes; `omarchy plugin enable firstpick.customization-center` brings it back with the transaction committed |

## 16. Acceptance criteria

1. Rows and enabled state match `omarchy-plugin-list --json`; static-only rows are diagnostics.
2. Every row identifies kinds and origin; installed and clone rows say the code is unsandboxed.
3. Enable and disable of every non-bar shape persist across shell restart and write nothing outside `plugins[]` and `disabledPlugins[]`.
4. No operation from this page touches the `bar` subtree; every bar-owned row offers the deep link and no toggle.
5. A configured bar that fell back is shown as such, never as success.
6. Add, Update, Remove, and Clone keep Omarchy's terminal warning, diff, confirmation, editor, and output; Add never receives `--enable`.
7. A handoff resolves through `reconcile` with the right journal state; the page never claims success without a sentinel.
8. Declared settings render read-only for all six types; invalid schemas show their problems and never crash the page.
9. Opening, filtering, inspecting, validating, or refreshing performs no persistent write.
10. A stale revision blocks apply and offers Reload and Compare.

## 17. Required core changes

Sheet A to J covers inverse tuples, `ShellIpc` semantics, `TerminalHandoff` wrapping and `reconcile`, `SchemaForm` and `settings_schema.py`, `catalog.py`, `requestNavigate` and `handlePayload`, `pollStatus`, `query`, and journal states. What remains for this module:

1. `BackendClient` should run `ccctl reconcile` itself when a `pollStatus` result lists a pending handoff whose sentinel exists, and expose the outcome through `TransactionModel`. Without it each page with handoffs needs its own reconcile timer. Small; the defaults module needs the same.
2. `core.catalog.read(ctx)` should return the raw `listShellConfig` document alongside the join so this module can derive `instances[]`, `disabledByList`, and `configuredBar` without a second IPC call.
3. `SchemaForm.qml` needs a `readOnly` property and a `requestDeleteKey(key)` signal (section 6.3). Listed here because the form's first specification is in this plan.

With these, the module needs exactly its directory and one line in `backend/customization_center/modules/__init__.py`.

## 18. Conflicts and open decisions

Resolved by the sheet and reflected above: ownership of the bar subtree (H), the schema renderer and adapters in core (F), no `dependsOn` (F), handoff mechanics (B), `query` instead of status flags (J).

Remaining differences with the master plan's Module 2 text, to be applied there:

- "`omarchy plugin list --json`" is a dispatcher route; the binary is `omarchy-plugin-list` and the data is `listPlugins`.
- "A full-bar plugin cannot be disabled directly": the IPC accepts it and reverts to `omarchy.bar` (`PluginRegistry.qml:489-492`); only `canDisable` hides it. Moot for this module since bars are bar-owned.
- "Never automatically enable a newly installed plugin": the Omarchy add flow asks in the terminal (`bin/omarchy-plugin-add:151-159`); the center does not pass `--enable` and cannot suppress that prompt.
- "Terminal-backed Clone": clone has no prompt; plain clone is a `RunCommand` after a named confirmation, `--edit` is the handoff.
- The settings extension example should use `min`, `max`, `defaultValue`.
- Module 2's "Placement controls for bar widgets" and "Use shell IPC for placement and inline settings" move to Module 1 per sheet H.

Open decisions:

1. Weather location has no owner in the first release; the weather popup already edits it. Decide later whether the bar module's `weatherSettings@1` external part gets a write path or stays a pointer to the popup.
2. Whether `validate` should run for every user plugin on page open. It forks `jq` about a dozen times per plugin. Recommendation: on demand only, as planned.
3. The weather `unit` option strings (section 6.4) wait on a read of `Model.js`.
4. Whether Add is offered while the shell is down. The command works without the shell except its `rescanPlugins` call (`:149`) and enable poll. Recommendation: hide it; the plugin appears on next shell start anyway.

## 19. Delivery

1. P0, contracts and fixtures: draft schema, every fixture in section 15, command stubs; PL-U-01 to PL-U-26 pass with no writes.
2. P1, read-only catalog: `status`, origin classification, trust text, diagnostics, filters, Overview, Placement and Settings tabs read-only, fallback banner, deep links. Exit: PL-Q-01 to PL-Q-06.
3. P2, enablement: enable and disable of non-bar kinds including clone sources; plan, verify, rollback. Exit: PL-I-01 to PL-I-04, PL-I-08, PL-L-01, PL-L-06.
4. P3, lifecycle: handoffs, reconcile polling, plain clone through `RunCommand`, validate query, self-row safeguards. Exit: PL-A-07, PL-I-05 to PL-I-07, PL-I-09 to PL-I-11, PL-L-03 to PL-L-05.
5. P4, hardening: keyboard pass, catalog performance (200 fake plugins under 1 s for `status`), recovery documentation for handoffs left pending. Exit: PL-Q-07, PL-Q-08, PL-L-02, and no open high-severity issue.
