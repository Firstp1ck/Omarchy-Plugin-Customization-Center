# Visual bar editor (module `bar`)

Status: planned. Verified against `omarchy-fork` at commit `71b0887c` and the module contract in the master plan.

## 1. What this module does

The bar module lets a user edit the `bar` subtree of `~/.config/omarchy/shell.json` without opening the file: which full-bar plugin is configured, its position, transparency, the center anchor, which widgets sit in the left, center, and right sections, their order, and their inline settings. The page shows a schematic preview, the user edits a draft, the shared ApplyBar runs validate, plan, review, apply through `ccctl`, and the backend confirms the running shell reflects the plan before reporting success.

The module owns every write to the `bar` subtree, including `bar.id` and therefore full-bar selection. No other module writes that subtree (contract amendment H). Section 12 explains how the plugins module deep-links to it and section 11 how desktop modes hand it a target subtree.

## 2. Verified Omarchy facts at 71b0887c

Everything below was read from the source. Line numbers are cited so a later Omarchy bump can be checked quickly.

### 2.1 Shell IPC methods the module uses

The `shell` IPC target is `shell/shell.qml:872-1030`. `omarchy-shell` (`bin/omarchy-shell`) forwards `omarchy-shell shell <method> [args...]` to `qs ipc -n -p $OMARCHY_PATH/shell call -- shell <method> args...` (`bin/omarchy-shell:59`).

| Method and argument form | Source | Reply | Notes |
|---|---|---|---|
| `ping` | `shell.qml:875` | `ok` | |
| `listShellConfig` | `shell.qml:994` | JSON document | The in-memory effective config, which is the user file when it parsed with `version: 1`, otherwise `$OMARCHY_PATH/config/omarchy/shell.json` (`shell.qml:72-88`). |
| `listPlugins` | `shell.qml:952-989` | JSON array of `{id, name, kinds, enabled, active, canDisable, firstParty, clonedFrom}` | For a `bar-widget`, `enabled` means "is somewhere in `bar.layout`" (`shell.qml:968-969`, `PluginRegistry.qml:164-167`). `active` is true only for the bar option that is running (`shell.qml:959`). Sorted by name then id. |
| `enablePlugin <id> <placementJson>` | `shell.qml:911-919` | `ok`, `unknown`, or an error string | Inserts a bare `{"id": id}` entry at `placement.section`/`placement.index` when the id is not already in the layout (`PluginRegistry.qml:499-515`). If the id is already in the layout it moves the first occurrence instead of inserting (`PluginRegistry.qml:520-521`). |
| `putBarWidget <id> <placementJson>` | `shell.qml:923-930` | `ok`, `not ready`, `unknown`, error string | Returns `ok` without doing anything when the id is already on the bar (`PluginRegistry.qml:297`). Not used by this module. |
| `moveBarWidget <id> <placementJson>` | `shell.qml:932-939` | `ok` or error string | With `fromSection` and `fromIndex` it moves exactly that occurrence and checks the id there (`PluginRegistry.qml:256-266`). Without them it moves the first occurrence found left, center, right (`PluginRegistry.qml:267-268`). Target `index` is clamped to the section length after the source is spliced out (`PluginRegistry.qml:240-243`, `271-278`). |
| `setBarWidget <id> <key> <valueJson> <selectorJson>` | `shell.qml:941-950` | `ok` or error string | With `section` and `index` (or `fromSection`/`fromIndex`) it targets one occurrence and checks the id (`PluginRegistry.qml:323-348`). Assigns one key; it cannot delete a key (`PluginRegistry.qml:354`). Fails with `widget entry must be an object` on a string-form entry (`PluginRegistry.qml:350-353`). |
| `setPluginEnabled <id> <"true"\|"false">` | `shell.qml:907-909` | `ok` or `unknown` | With `"false"` on a bar widget it removes the first occurrence found left, center, right (`PluginRegistry.qml:497`, `531`). For a widget whose manifest carries `omarchy.clonedFrom` it restores the source widget in place instead of removing (`PluginRegistry.qml:530`, `416-447`). |
| `toggleBarTransparency` | `shell.qml:899-905` | `ok` or `no-bar` | Flips, does not set. Returns `no-bar` when the running bar has no `toggleTransparency` function. Not used by this module. |
| `reloadConfig` | `shell.qml:894-897` | `ok` | Re-reads the user file. The shell also watches the file on its own (`shell.qml:130-139`). |
| `debugBarGeometry` | `shell.qml:998-1000` | JSON array | Built-in bar only (`Bar.qml:128-152`). Empty array for a third-party bar that does not implement it. Diagnostics only. |

IPC-level failures answer on stdout with exit 0 (`bin/omarchy-shell:56-57`). `omarchy-shell` turns four of them into exit 1 (`Target not found.`, `Function not found.`, argument-count errors, and `Not ready to accept queries yet`, `bin/omarchy-shell:68-77`). A missing shell is `omarchy-shell is not running` with exit 1, a hung one is `omarchy-shell is not responding` after `OMARCHY_SHELL_IPC_TIMEOUT` (`bin/omarchy-shell:58-66`). Every other miss (`unknown`, `not ready`, `no widget at right[3]`, `widget at center[1] is not omarchy.clock`, `could not find widget x`, `invalid placement: ...`) is a stdout string with exit 0. The core `ShellIpc` operation owns this classification (amendment B): exit 1 becomes `runtime_unavailable` or `unsupported_config`, and a stdout body outside `expect` becomes `ipc_rejected` with the body in the message. This module only lists which bodies it expects.

Every mutating method above goes through `shell.mutateShellConfig` (`shell.qml:158-162`), which clones the in-memory config, mutates it, assigns it, and writes `~/.config/omarchy/shell.json` through a `FileView` with `atomicWrites: true` (`shell.qml:108-113`, `130-139`). One IPC call is one file write and one `shellConfig` change. A structural layout change rebuilds every widget on every monitor; a settings-only change patches widgets in place (`Bar.qml:355-374`, `BarModel.js:78-107`).

### 2.2 What no IPC method can do

These gaps are exact at 71b0887c and drive the two-route design in section 8.

1. Insert a second instance of an id that is already on the bar. `putBarWidget` returns early (`PluginRegistry.qml:297`), and `enablePlugin` moves the existing entry instead (`PluginRegistry.qml:497`, `503`, `520-521`). `allowMultiple` is read only when registering widget metadata (`shell.qml:693`); no mutation path consults it.
2. Remove a chosen occurrence directly. `setPluginEnabled false` removes the first match. Section 8.3 shows that a move to `left[0]` followed by disable removes an exact occurrence, so this gap is closed by composition.
3. Delete an inline key. `setBarWidget` only assigns (`PluginRegistry.qml:354`). Assigning `null` is not the same as absence; `Spacer.qml:8` reads `settings.size !== undefined`, so `null` becomes `Number(null) = 0` and hides the spacer.
4. Set `bar.centerAnchor`. No IPC method and no `omarchy bar` subcommand touches it (`bin/omarchy-bar:371-403`).
5. Set `bar.position`, `bar.transparent` to a value, or `bar.id` over IPC. `omarchy bar position|transparent|use|reset|defaults` write the file with `jq` and then call `reloadConfig` (`bin/omarchy-shell-config:53-62`, `bin/omarchy-bar:151-155`, `203`, `213-216`).
6. A revision token. Nothing in the shell numbers config states. Staleness has to be detected by hashing `listShellConfig`.

### 2.3 `omarchy bar` subcommands

`bin/omarchy-bar` dispatches these forms (`bin/omarchy-bar:371-403`):

```text
omarchy-bar use <id>                    # id may be "default" or "built-in"; validates against omarchy-plugin-catalog; file write
omarchy-bar reset                       # same as use omarchy.bar; deletes bar.id; file write
omarchy-bar defaults                    # replaces .bar with $OMARCHY_PATH/config/omarchy/shell.json .bar, then re-adds
                                        #   omarchy.dropbox and omarchy.tailscale when omarchy-installed-service-<x> succeeds; file write
omarchy-bar position <top|bottom|left|right>       # file write
omarchy-bar transparent <true|false|toggle>        # file write
omarchy-bar put <id> [section] [--section s] [--index n] [--before id] [--after id]      # IPC putBarWidget, retries while "not ready"
omarchy-bar move <id> [section] [--section s] [--index n] [--before id] [--after id] [--from-section s] [--from-index n]   # IPC moveBarWidget
omarchy-bar set <id> <key> <value> [--json] [placement]                                  # IPC setBarWidget; value is a JSON string unless --json
```

Placement flags become `{"section","index","before","after","fromSection","fromIndex"}` (`bin/omarchy-bar:122-138`). The module does not shell out to `omarchy-bar`; it calls `omarchy-shell` directly for IPC and writes the file itself for the file route, because `omarchy-bar` prints prose and `commit()` sorts keys with `jq -S` (`bin/omarchy-shell-config:58`). `omarchy-bar` remains the documented manual recovery tool (section 16).

### 2.4 The `bar` subtree

`config/omarchy/shell.json:7-64` is the shipped default. It has no `bar.id` (built-in bar), `position: "top"`, `transparent: false`, `centerAnchor: "omarchy.clock"`, and 14 entries across the three sections. Only `omarchy.clock` carries inline settings (`format`, `formatAlt`, `verticalFormat`).

Rules the shell applies when reading:

- Entries may be objects with `id` or bare strings; both normalize to objects (`shell/Commons/Util.qml:127-135`). Entries without an id are dropped from rendering.
- `bar.id` missing or `omarchy.bar` means the built-in bar (`shell.qml:166-174`).
- `position` outside the four values renders as `top` (`BarModel.js:5-8`).
- `transparent` is true only when literally `true` (`Bar.qml:359`).
- `centerAnchor` names an id; the first matching center entry is pinned to the center and the rest flank it; empty or unmatched centers the group (`Bar.qml:1272-1276`, `1288-1293`, `shell/plugins/bar/README.md:49`).
- `omarchy.tray` is displayed at the inner edge of its section regardless of its index (`Bar.qml:336-353`, `BarModel.js:27-40`). The stored order is unchanged.
- Entries with `type: "command"`, `type: "qml"`, `exec`, or `source` are custom modules with no manifest (`shell/plugins/bar/README.md:81-124`, `BarModel.js:119-133`).
- Unknown keys on `bar` and on entries are kept by every shell write because the shell clones and re-serializes the whole document (`shell.qml:108-113`, `159`).

### 2.5 Widget manifest fields

`barWidget` metadata is read at `shell.qml:688-700`. Runtime validation (`PluginRegistry.qml:43-91`) checks only `schemaVersion`, the five required keys, id shape, `kinds`, `entryPoints` paths, and `barWidget.defaultSection`. The repository test `test/shell.d/plugins-test.sh:144-153` additionally requires `displayName`, `description`, `category` strings and a boolean `allowMultiple` on first-party manifests, but a third-party manifest with none of them still loads (`omarchy-plugin-validate` checks only `defaultSection`, `bin/omarchy-plugin-validate:66-74`).

| Field | Type | Fallback at runtime | Current values in the tree |
|---|---|---|---|
| `displayName` | string | `manifest.name` | |
| `description` | string | `manifest.description` | |
| `category` | string | `"Plugin"` | AI, Audio, Compositor, Files, Info, Layout, Media, Network, Status, System, Time |
| `allowMultiple` | boolean | `false` unless literally `true` | true only on `omarchy.indicators` and `omarchy.spacer` |
| `defaultSection` | `left`, `center`, `right` | `center` (`PluginRegistry.qml:169-173`) | `right` on dropbox and tailscale |
| `defaults` | object | `{}` | `agents`, `dropbox`, `tailscale` |
| `settingsForm` | string | `""` | `spacerSettings` (Spacer), `weatherSettings` (Weather). Identifiers only; no form implementation exists in the tree. |
| `schema` | array | `[]` | `agents`, `dropbox`, `tailscale`, `indicators` |

The schema dialect in the tree is `{key, type, label, description?, defaultValue?, min?, max?, step?, options?}` with types `boolean`, `integer`, `string`, `path`, `enum`, `multiselect` (`shell/plugins/agents/manifest.json`, `panels/dropbox/manifest.json`, `panels/tailscale/manifest.json`, `bar/widgets/Indicators.manifest.json`). `options` entries are strings or `{value, label, description}`. Indicators also carries `noSelectionText`, `placeholderText`, `emptyText`. There is no `select` or `number` type and no JSON Schema `minimum`/`maximum`/`default`; the earlier version of this plan listed those and was wrong.

`omarchy-plugin-catalog` (`bin/omarchy-plugin-catalog`) emits `{id, name, description, kinds, firstParty, manifestPath, sourceDir, entryPoints, barWidget, bar, barWidgetPath, barPath}` from the filesystem with `unique_by(.id)` and no namespace or validation checks. `listPlugins` does not include `barWidget`, so the catalog is the only CLI source of schema metadata. The module intersects the two: `listPlugins` decides which ids exist for the shell; the catalog adds metadata for those ids.

### 2.6 How the shell handles a missing or failed full bar

- `selectedBarId` is `bar.id` or `omarchy.bar` (`shell.qml:167-174`).
- `selectedBarAvailable` is false when the manifest is missing, lacks `kinds: ["bar"]`, or has no `entryPoints.bar` (`shell.qml:176-179`, `203-208`).
- `activeBarId` falls back to `omarchy.bar` when the selected bar is unavailable or equals `failedBarId` (`shell.qml:180`).
- `failedBarId` is set when the plugin bar `Loader` reports `Loader.Error` (`shell.qml:254-260`). The loader is `asynchronous: true` (`shell.qml:251`), so a freshly configured bar reports `active: true` in `listPlugins` while it is still loading, and flips to `omarchy.bar` only after the error.
- Any `shellConfig` change clears `failedBarId` (`shell.qml:66-70`), so every write, including this module's, makes the shell retry a broken bar once.
- `bar.id` is never rewritten by the fallback. The user's configuration keeps naming the broken bar.

Consequence for verification (section 9): after a `bar.id` change the backend waits a bounded time and then checks that `listPlugins` still reports the configured id as `active`. There is no positive "loaded" signal over IPC.

### 2.7 Other facts the plan relies on

- The same layout renders on every monitor; one bar surface per screen reads the same `layoutConfig` (`Bar.qml:952-977`).
- Vertical bars map left, center, right to top, middle, bottom; the anchored center entry has flanks above and below (`Bar.qml:1357-1385`). Vertical cross-axis size is `Style.bar.sizeVertical` (28), horizontal is `Style.bar.sizeHorizontal` (26); both scale with font size by default (`shell/Commons/Style.qml:341-347`, `docs/omarchy-shell.md:363-377`).
- Bar colors are `Color.bar.background`, `Color.bar.text`, `Color.bar.active` (`Bar.qml:65-72`).
- Widgets that update their own inline state call `shell.updateEntryInline`, which rewrites every entry with that id (`shell.qml:366-405`). The base can change under an open draft without any user gesture on the bar.
- Weather's location lives in `~/.local/state/omarchy/settings/weather.json` (`bin/omarchy-weather-location:15`, `panels/weather/Panel.qml:96`); its inline keys are `unit` and `refreshMinutes` (`Panel.qml:138`, `141`).
- `omarchy-restart-shell` kills and relaunches the shell through Hyprland and waits for `ping` (`bin/omarchy-restart-shell:69-95`). It refuses while the session is locked.

## 3. Module layout

```text
modules/bar/
├── module.json
├── Page.qml
├── components/
│   ├── BarOptions.qml          # full bar selector, position, transparency, center anchor
│   ├── BarPreview.qml          # screen mock with the bar strip in one of four positions
│   ├── BarSection.qml          # one section: cards, insertion points, empty state
│   ├── WidgetCard.qml          # one instance: label, badges, focus, grab state
│   ├── WidgetCatalog.qml       # search, category filter, add and duplicate
│   ├── WidgetInspector.qml     # identity, settings form, preserved keys, remove
│   └── ReorderController.qml   # pointer drag and keyboard grab on the draft model
├── backend/
│   ├── __init__.py             # exports MODULE
│   ├── status.py               # read pipeline, revision, defaults; calls core catalog.join
│   ├── model.py                # normalized layout, draft codec, occurrence identity, rebase
│   ├── validate.py             # uses core settings_schema for field checks
│   ├── plan_ipc.py             # ShellIpc route
│   ├── plan_file.py            # WriteFileAtomic route
│   └── verify.py
├── schemas/
│   ├── bar-status-v1.json
│   ├── bar-draft-v1.json
│   └── bar-preset-v1.json
└── tests/
    ├── fixtures/               # section 15
    ├── stubs/omarchy-shell     # replays fixtures, records calls
    └── test_*.py
```

`module.json`:

```json
{
  "id": "bar",
  "title": "Bar",
  "icon": "bar",
  "navOrder": 10,
  "page": "Page.qml",
  "backend": "customization_center.modules.bar",
  "schemas": ["schemas/bar-status-v1.json", "schemas/bar-draft-v1.json", "schemas/bar-preset-v1.json"],
  "coreServices": ["shell_ipc", "commands", "atomic", "settings_schema", "catalog"]
}
```

The schema normalizer, field renderer, and the `spacerSettings@1` and `weatherSettings@1` adapters are `backend/customization_center/core/settings_schema.py`, `core/SchemaForm.qml`, and `core/SchemaField.qml` (amendment F). The `listPlugins` and `omarchy-plugin-catalog` join is `core/catalog.py`. This module has no local copies of either.

## 4. Status (`ccctl status bar`)

### 4.1 Read pipeline

All subprocess calls go through `ctx.commands` with argv arrays, `OMARCHY_PATH` inherited, and a 5 second timeout (the inner `omarchy-shell` timeout stays at its default 2 seconds).

1. `["omarchy-shell", "shell", "ping"]` through core `shell_ipc`. A `runtime_unavailable` result sets `shell.available = false` with `shell.reason` set to the core's classification (`not running`, `not responding`, `not ready`). Status still returns; steps 2 to 4 are skipped and `bar` is read from the file instead so the page can show something and say it is unverified.
2. `["omarchy-shell", "shell", "listShellConfig"]` with `expect_json`. Anything that is not a JSON object is `malformed_output`.
3. and 4. `core/catalog.join(ctx)`, which runs `listPlugins` and `omarchy-plugin-catalog` and returns the joined rows plus a `catalogAvailable` flag. A failed or malformed catalog is the warning `bar_catalog_unavailable`; the layout is still shown with ids only.
5. Read `~/.config/omarchy/shell.json` if it exists. Record `file.exists`, `file.parses`, `file.version1`, and `file.matchesShell` (canonical JSON of the file's `bar` equals canonical JSON of step 2's `bar`).
6. Read `$OMARCHY_PATH/config/omarchy/shell.json` and compute `defaults` (section 11).
7. For `dropbox` and `tailscale`, run `["omarchy-installed-service-<name>"]`; exit 0 means installed. This is the same probe `omarchy-bar defaults` uses (`bin/omarchy-bar:164-165`).
8. Build the catalog (section 4.3), normalize the layout (section 5), compute `revision`.

### 4.2 Response

```json
{
  "schemaVersion": 1,
  "module": "bar",
  "revision": "sha256:3f1c...",
  "shell": {
    "available": true,
    "reason": "",
    "configuredBarId": "omarchy.bar",
    "configuredBarExplicit": false,
    "activeBarId": "omarchy.bar",
    "fallback": false,
    "scanning": false
  },
  "source": { "kind": "user", "path": "/home/u/.config/omarchy/shell.json" },
  "file": { "exists": true, "parses": true, "version1": true, "matchesShell": true },
  "bar": {
    "id": null,
    "position": "top",
    "transparent": false,
    "centerAnchor": "omarchy.clock",
    "extra": {},
    "layout": {
      "left":   [ { "key": "b:left:0", "id": "omarchy.menu", "settings": {}, "form": "object" } ],
      "center": [],
      "right":  []
    }
  },
  "defaults": { "id": null, "position": "top", "transparent": false, "centerAnchor": "omarchy.clock", "extra": {}, "layout": { "left": [], "center": [], "right": [] } },
  "catalog": [],
  "barOptions": [ { "id": "omarchy.bar", "name": "Bar", "firstParty": true, "available": true } ],
  "capabilities": {
    "applyIpc":    { "available": true,  "reason": "" },
    "applyFile":   { "available": true,  "reason": "" },
    "selectBar":   { "available": false, "reason": "only omarchy.bar is installed" },
    "debugGeometry": { "available": true, "reason": "" }
  },
  "warnings": [],
  "errors": []
}
```

Field notes:

- `revision` is exactly

  ```text
  "sha256:" + hex(sha256(canonical_json({
      "config":     <listShellConfig document>,
      "fileSha256": <hex sha256 of ~/.config/omarchy/shell.json bytes, or null when absent>,
      "plugins":    [ {"id", "kinds", "firstParty", "clonedFrom"} for every listPlugins row, sorted by id ]
  })))
  ```

  where `canonical_json` is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. It changes on any shell config change (including changes outside `bar`, which is deliberate because the file route rewrites the whole document), on any change to the file on disk (a pending shell write that has not landed yet makes the next status differ, which is the desync the file route must not race), and on any plugin appearing or disappearing. It does not include `enabled` or `active`, so a bar falling back does not make a draft stale. When the shell is unavailable the revision is `"unavailable:" + fileSha256` and no plan is accepted against it.
- `shell.configuredBarId` is `bar.id` or `omarchy.bar`. `configuredBarExplicit` is true when the key is present. `activeBarId` is the `listPlugins` row with `active: true`, or `omarchy.bar` when none. `fallback` is `configuredBarId != activeBarId`.
- `shell.scanning` cannot be read over IPC. It is inferred: `true` when `listPlugins` returned an empty array while `listShellConfig` has layout entries. The page shows "Plugin scan in progress" and disables Apply.
- `bar.id` is `null` when the key is absent, otherwise the string as stored. `extra` holds every `bar` key other than `id`, `position`, `transparent`, `centerAnchor`, `layout`, verbatim.
- `bar.layout.*[]` entries are normalized occurrences (section 5). `key` is a status-time identity `b:<section>:<index>`; the page replaces it with draft keys.
- `defaults` is the computed "Omarchy defaults" bar (section 11).
- `barOptions` lists every `listPlugins` row with `bar` in `kinds`, plus `available` from the catalog's `barPath` being non-null.
- Capabilities: `applyIpc` requires the shell and a non-scanning registry. `applyFile` additionally requires that `~/.config/omarchy/` is writable and, when the file exists, that it parsed with `version: 1` (a malformed user file is not overwritten; see section 10 state `load-error`). `selectBar` requires at least one bar option other than `omarchy.bar`. `debugGeometry` requires `activeBarId == "omarchy.bar"`.

### 4.3 Catalog item

```json
{
  "id": "omarchy.indicators",
  "name": "Indicators",
  "displayName": "Indicators",
  "description": "Manual state indicators",
  "category": "Status",
  "kinds": ["bar-widget"],
  "firstParty": true,
  "clonedFrom": "",
  "activeCloneId": "",
  "enabled": true,
  "allowMultiple": true,
  "defaultSection": "center",
  "defaults": {},
  "settingsForm": "",
  "schema": { "ok": true, "fields": [ { "key": "items", "type": "multiselect", "label": "Indicators", "options": [] } ], "problems": [] },
  "sizeClass": "variable",
  "presence": "shell"
}
```

Rules 1 to 4 are what `core/catalog.join` provides and this module relies on; rules 5 and 6 are added by `status.py`.

1. Rows come from `listPlugins` filtered to `kinds` containing `bar-widget`. `presence: "shell"`.
2. The catalog row with the same id supplies `displayName`, `description`, `category`, `allowMultiple` (literal `true` only), `defaultSection` (validated, else `center`), `defaults` (object, else `{}`), `settingsForm`, `schema`. Missing catalog row: `displayName = name`, `category = "Plugin"`, `schema = {ok: false, problems: ["no catalog metadata"]}`.
3. `schema` is normalized by `core/settings_schema.py`. A schema that fails normalization yields `ok: false` with per-field problems; the widget stays addable and movable, its settings are read-only.
4. `activeCloneId` is the id of any row whose `clonedFrom` equals this id and whose `enabled` is true.
5. Layout ids that match no row get a synthetic item with `presence: "layout-only"`, `displayName` equal to the id, `category: "Custom"` when the entry has `type`, `exec`, or `source`, otherwise `category: "Unavailable"`. They cannot be added or duplicated.
6. `sizeClass` is a fixed table used only by the preview: `spacer` for `omarchy.spacer`; `text` for `omarchy.clock`, `omarchy.workspaces`, `omarchy.active-window`, `omarchy.media`, `omarchy.keyboard-layout`, and every layout-only custom entry; `variable` for `omarchy.indicators` and `omarchy.tray`; `icon` for everything else. The table is documented as an approximation drawn from `shell/plugins/bar/README.md:55-73`.

## 5. Normalized layout model and draft identity

### 5.1 Occurrence

A layout is three ordered lists of occurrences. An occurrence is `(section, index)` in a concrete layout state plus the entry at that position. Ids are not identities: `allowMultiple` widgets and, in practice, any id can repeat because the shell never checks (section 2.2).

Normalized entry:

```json
{ "key": "d:7f3a", "origin": { "section": "center", "index": 1 }, "id": "omarchy.clock", "settings": { "format": "HH:mm" }, "form": "object" }
```

| Field | Type | Meaning |
|---|---|---|
| `key` | string | Draft identity. Unique within the draft, never written to `shell.json`, never derived from the id. The page mints `d:<8 hex>` for new entries and rewrites the status keys `b:<section>:<index>` to `d:...` on load so keys survive moves. |
| `origin` | object or null | The base occurrence this entry came from, recorded once when the draft was created from a status at `baseRevision`. `null` for new entries. |
| `id` | string | Widget id, non-empty. |
| `settings` | object | Every entry key except `id`, verbatim, with JSON types preserved. Includes unknown keys and custom-module keys such as `type`, `exec`, `interval`. |
| `form` | `"object"` or `"string"` | Whether the base entry was a bare string. A string-form entry is serialized back as a string unless its settings changed. |

Serialization to a shell entry is `{"id": id, **settings}` for object form and `id` for string form with empty settings. Key order inside an entry is `id` first, then settings in the order they appear in the draft, which is base order for existing keys and append order for new ones.

### 5.2 Draft (`bar-draft-v1.json`)

```json
{
  "schemaVersion": 1,
  "module": "bar",
  "baseRevision": "sha256:3f1c...",
  "bar": {
    "id": null,
    "position": "left",
    "transparent": true,
    "centerAnchor": "omarchy.clock",
    "extra": {},
    "layout": { "left": [], "center": [], "right": [] }
  }
}
```

| Field | Type | Rules |
|---|---|---|
| `baseRevision` | string | Copied from the status the draft was created from. `plan` refuses a draft whose base does not equal the current status revision (`stale_revision`). |
| `bar.id` | string or null | `null` writes no `id` key. The page sets `null` when the user picks the built-in bar and the base had no key, `"omarchy.bar"` when the base had the key explicitly, and the plugin id otherwise. |
| `bar.position` | enum | `top`, `bottom`, `left`, `right`. |
| `bar.transparent` | boolean | |
| `bar.centerAnchor` | string | Empty string disables anchoring. Written as-is, including when the base had the key absent (the page treats absent and empty as equal for editing; `plan` writes the key only if the base had it or the value is non-empty). |
| `bar.extra` | object | Copied from status, not editable in the page, written back verbatim. |
| `bar.layout` | object | Three arrays of normalized entries. Every `origin` in the draft must refer to a distinct base occurrence, and every base occurrence referenced must exist at `baseRevision`. |

The draft is stored by the core `DraftStore` in memory and, on explicit "Save draft", at `~/.config/omarchy/customization-center/drafts/bar.json`. A saved draft reopened against a different revision is shown in state `stale` with its base and the current status both available for Compare.

A draft may also carry layout entries without `key` and `origin`. `validate` and `plan` then call `model.rebase(status, bar)` first, which matches entries to base occurrences by `(section, index, id)`, then by id ordinal, and marks the rest new. This is the shape desktop modes uses (amendment I): the mode file stores the target `bar` subtree inline under `members.bar` in shell form (`{"id"?, "position", "transparent", "centerAnchor", "layout": {"left": [<shell entries>], ...}}` plus any extra keys), and modes builds `{"schemaVersion": 1, "module": "bar", "baseRevision": <current bar revision>, "bar": <that subtree normalized by model.from_shell>}` before calling this module's `validate` and `plan` through `ctx.registry`. Nothing in modes references a preset.

### 5.3 Identity mapping to shell instances

The shell addresses an instance only by `(section, index)` at the moment of a call. The mapping from a draft `key` to a shell selector is therefore computed against a simulated working copy at plan time and never stored (section 8.3). Two properties make this safe:

- Every move and set carries `fromSection`/`fromIndex` or `section`/`index` plus the id, and the shell rejects a mismatch (`PluginRegistry.qml:263-264`, `345-347`). A race that shifts indices between plan and apply produces a rejected call and a rollback, not a wrong edit, unless the racing change puts an entry with the same id at the same index, which is the residual risk stated in section 17.
- The executor re-checks `status().revision` under the lock immediately before the first operation, so the working copy starts from the state the shell reports.

## 6. Validation (`ccctl validate bar`)

Pure function of draft, status, and catalog. Errors block; warnings show in review.

Errors (code, condition):

- `validation_failed` / `bar_position_invalid`: position not in the four values.
- `validation_failed` / `bar_entry_id_invalid`: empty or non-string id, or id containing `/` or `..` (`PluginRegistry.qml:60`).
- `validation_failed` / `bar_duplicate_not_allowed`: an id occurs more than once and its catalog item has `allowMultiple != true`. Existing duplicates in the base are exempt (warning `bar_existing_duplicate`) because Omarchy did not prevent them; adding a further one is an error.
- `validation_failed` / `bar_unknown_widget`: a new entry (`origin: null`) whose id has `presence != "shell"`. Custom modules cannot be created in the first release (section 16).
- `validation_failed` / `bar_origin_invalid`: an origin refers to a base occurrence that does not exist, or two entries share an origin.
- `validation_failed` / `bar_anchor_missing`: `centerAnchor` non-empty and no center entry has that id.
- `validation_failed` / `bar_anchor_ambiguous`: the anchor id occurs more than once in center and the anchor value differs from the base value. An inherited ambiguous anchor is a warning `bar_anchor_ambiguous_inherited` ("the shell pins the first one").
- `validation_failed` / `bar_settings_invalid`: a value edited in this draft violates its normalized schema field (type, `min`, `max`, `step`, option membership, uniqueness for `multiselect`). Unedited values that violate the schema are a warning `bar_settings_preexisting`.
- `validation_failed` / `bar_bar_option_unknown`: `bar.id` names an id absent from `barOptions`, or present but `available: false`.
- `validation_failed` / `bar_draft_keys_leak`: an entry's `settings` contains `key`, `origin`, or `form`.

Warnings:

- `bar_third_party_bar`: `bar.id` is a non-first-party option ("runs unsandboxed inside the shell; if it fails to load the shell falls back to the built-in bar and keeps your setting").
- `bar_fallback_now`: status reports `fallback: true` and the draft keeps the same `bar.id`.
- `bar_custom_entry_touched`: a layout-only entry is moved or removed.
- `bar_tray_pinned`: `omarchy.tray` is not at the inner edge of its section in the draft ("the bar draws the tray at the inner edge regardless").
- `bar_vertical_text`: position is `left` or `right` and the draft has more than four `text` widgets.
- `bar_schema_readonly`: an entry's widget has `schema.ok == false`.
- `bar_route_file`: the plan will use the file route (section 8.2), with the reason list.
- `bar_rollback_approximate`: the ipc route will roll back a newly added key by writing `null` (section 8.4).

## 7. Capabilities and error codes

Shared codes are used as defined in the contract. Module codes, all prefixed `bar_`:

| Code | Raised by | Meaning |
|---|---|---|
| `ipc_rejected` (shared) | core ShellIpc | The shell answered something other than `expect`. The reply body is in the message. Not a module code; listed because the page maps it to the failing summary line. |
| `bar_shell_fallback` | verify | The configured bar is not the active bar after the settle time. |
| `bar_file_desync` | verify, status warning | The file's `bar` differs from `listShellConfig` after the settle time. |
| `bar_scan_in_progress` | plan | `shell.scanning` inferred true. |
| `bar_plan_mismatch` | plan (internal) | The simulated result of the operations differs from the draft. Indicates a planner bug; never applied. |
| `bar_catalog_unavailable` | status warning | `omarchy-plugin-catalog` failed. |

## 8. Planning (`ccctl plan bar`)

### 8.1 Inputs and outputs

`plan(ctx, draft, status)` returns a `Plan`:

```json
{
  "module": "bar",
  "expectedRevision": "sha256:3f1c...",
  "route": "ipc",
  "summary": [ "Move Clock to center, position 1", "Set Spacer #2 size to 24", "Remove Weather" ],
  "operations": [],
  "expected": { "bar": {} },
  "rollbackExact": true,
  "warnings": []
}
```

`expected.bar` is the serialized draft bar (section 5.1 serialization) and is what `verify` compares against. `summary` lines name instances as `<displayName> #<n>` where `n` is the ordinal among same-id entries in the draft, plus the final `section[index]`.

### 8.2 Route selection

Compute `count_B(id)` and `count_D(id)` over base and draft. The plan uses the file route when any of the following holds; otherwise the ipc route.

1. `bar.id`, `position`, `transparent`, or `centerAnchor` differs from the base.
2. For some id, `count_D(id) > max(count_B(id), 1)`. A first instance can be inserted by `enablePlugin`; a second cannot (section 2.2, item 1).
3. An existing entry loses a key (present in base settings, absent in draft settings).
4. A string-form entry has changed settings.
5. An inserted or removed id has a clone relationship: its catalog item has `clonedFrom != ""` or `activeCloneId != ""`. `enablePlugin` and `setPluginEnabled` run clone bookkeeping for these ids (`PluginRegistry.qml:478-484`, `504-509`, `530`) that would change entries the draft did not touch.
6. A removed entry is layout-only (no manifest). `enablePlugin` cannot re-insert it (`PluginRegistry.qml:457-460`), so the ipc route would have no inverse.
7. The draft only changes `extra` (cannot happen from the page, but a hand-edited draft could).

Routes are never mixed in one plan. Reason: an ipc mutation makes the shell write the file asynchronously (`shell.qml:112`, `FileView.setText`), and a file write that follows it can land before or after that write. Keeping one writer per transaction removes the race. Position, transparency, and bar id could have been delegated to `omarchy-bar`, but those commands are themselves file writes (`bin/omarchy-shell-config:53-62`), so they belong to the file route and gain nothing by going through the CLI.

### 8.3 The ipc route

Let `B` be the base layout from status, `D` the draft layout, `W` a deep copy of `B` where every occurrence carries the draft key that references it (via `origin`) or `null` if unreferenced. `locate(W, key)` returns the `(section, index)` of the occurrence with that key. `first(W, id)` returns the first occurrence of `id` scanning `left`, `center`, `right` and ascending index, which is exactly what `findBarLocation` does (`PluginRegistry.qml:179-194`).

```text
ops = []

# Phase 1: remove occurrences that the draft dropped.
# Order: right, center, left; within a section, highest index first.
removed = [occ for occ in B if occ.key is null], ordered as above
for occ in removed:
    (s, i) = locate(W, occ)
    if first(W, occ.id) != (s, i):
        emit ShellIpc("moveBarWidget", [occ.id, {"fromSection": s, "fromIndex": i, "section": "left", "index": 0}])
             inverse ShellIpc("moveBarWidget", [occ.id, {"fromSection": "left", "fromIndex": 0, "section": s, "index": i}])
        W.move((s, i) -> ("left", 0))
    (rs, ri) = first(W, occ.id)                   # now guaranteed to be occ
    emit ShellIpc("setPluginEnabled", [occ.id, "false"])
         inverse ( ShellIpc("enablePlugin", [occ.id, {"section": rs, "index": ri}]),
                   *[ ShellIpc("setBarWidget", [occ.id, k, json(v), {"section": rs, "index": ri}]) for (k, v) in occ.settings ] )
    W.remove((rs, ri))

# Phase 2: arrange. Left to right, index ascending. The settled prefix of each
# section is never touched again.
for S in [left, center, right]:
    for k in range(len(D[S])):
        target = D[S][k]
        cur = locate(W, target.key)               # null for new entries
        if cur is null:
            emit ShellIpc("enablePlugin", [target.id, {"section": S, "index": k}])
                 inverse ( removal pair for the occurrence at (S, k) as in phase 1 )
            W.insert((S, k), {id: target.id, settings: {}, key: target.key})
        elif cur != (S, k):
            emit ShellIpc("moveBarWidget", [target.id, {"fromSection": cur.s, "fromIndex": cur.i, "section": S, "index": k}])
                 inverse ShellIpc("moveBarWidget", [target.id, {"fromSection": S, "fromIndex": k, "section": cur.s, "index": cur.i}])
            W.move(cur -> (S, k))

# Phase 3: settings. Positions in W now equal positions in D.
for S in [left, center, right]:
    for k, target in enumerate(D[S]):
        current = W[S][k].settings
        for key, value in target.settings:
            if key in current and canonical(current[key]) == canonical(value): continue
            emit ShellIpc("setBarWidget", [target.id, key, json(value), {"section": S, "index": k}])
                 inverse ShellIpc("setBarWidget", [target.id, key, json(current[key]), {"section": S, "index": k}])   if key in current
                         ShellIpc("setBarWidget", [target.id, key, "null", {"section": S, "index": k}])              otherwise (approximate)
                         ()                                                                                           if target.origin is null
            W[S][k].settings[key] = value

assert serialize(W) == expected.bar.layout else fail bar_plan_mismatch
```

Ordering invariants, each of which a test in section 15 checks:

- I1. Removals precede inserts. `enablePlugin` for an id that still has an occurrence would move it instead of inserting.
- I2. Within phase 1, an occurrence is first moved to `left[0]` when it is not already the first match, so `setPluginEnabled false` removes exactly it. Processing right to left and high index first keeps every not-yet-processed `(s, i)` valid, because a move to `left[0]` only shifts indices in `left`, and `left` is processed last with live `locate`.
- I3. In phase 2, when processing `(S, k)`, positions `0..k-1` of `S` hold the first `k` draft entries of `S`. A move into `(S, k)` from `(S, i)` has `i > k`; the shell splices the source first and then inserts at `k` (`PluginRegistry.qml:271-278`), so the result is index `k`. A move from another section does not disturb `S[0..k-1]`. An insert at `k` is never clamped because `len(W[S]) >= k`.
- I4. After phase 2, `W` and `D` agree on `(id, key)` at every position, so phase 3 selectors equal the draft positions, which is what the review shows.
- I5. Every selector is computed from `W` at emission time, never from `B`.
- I6. No operation in the ipc route touches `bar.id`, `position`, `transparent`, `centerAnchor`, or `extra`.
- I7. The plan is immutable. `apply` receives the plan and the expected revision; it does not re-derive operations.

Every `ShellIpc` operation in this route is `ShellIpc(method, args, expect=("ok",), backup_paths=("~/.config/omarchy/shell.json",))` so the executor backs the file up before the first operation (the backup is for `ccctl history` and manual recovery, not for the automatic rollback, which runs the inverse tuples in the order amendment C describes).

### 8.4 Rollback exactness of the ipc route

`rollbackExact` is false when any phase 3 operation adds a key that the base entry did not have on an existing entry. Its inverse writes `null` because nothing can delete a key (section 2.2, item 3). The review shows the affected keys and, for `omarchy.spacer`, says that a rolled back `size` becomes 0 and hides the spacer. The user can avoid the approximation by choosing "Apply through file" in the review, which forces the file route for this plan.

### 8.5 The file route

```text
doc = deepcopy(status listShellConfig document)        # the effective document, which may be the defaults
doc["version"] = 1
doc["bar"] = serialize(draft.bar)                       # id (omitted when null), position, transparent, centerAnchor, extra keys, layout
if "plugins" not in doc: doc["plugins"] = []
content = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

ops = [
  ShellIpc("reloadConfig", [])                                       inverse ShellIpc("reloadConfig", [])
  WriteFileAtomic("~/.config/omarchy/shell.json", content, 0o644)    inverse: executor restores the backup (or removes the file if it did not exist)
  ShellIpc("reloadConfig", [])                                       inverse ShellIpc("reloadConfig", [])
]
```

Top-level key order follows the effective document, with `version` first and `bar`'s inner order `id, position, transparent, centerAnchor, <extra keys in base order>, layout`. The leading `reloadConfig` exists so that the reverse-order rollback ends with a reload after the file restore (reverse of `[reload, write, reload]` is `[reload, restore, reload]`). It is harmless going forward: the shell re-reads a file it already has.

`rollbackExact` is always true on this route. When the user had no `shell.json` (`source.kind == "defaults"`), the review states that the write creates the file and that from then on Omarchy stops following updates to the shipped defaults, which is the same consequence as any bar gesture or `omarchy bar` command (`docs/omarchy-shell.md:174-176`). The core `WriteFileAtomic` inverse removes a file that was absent at backup time, which restores that inheritance exactly. Per amendment C the inverse is skipped as `rollback_conflict` if the file's hash no longer matches what the plan wrote; the page then shows the recovery panel.

The route is refused (`capability_missing`, capability `applyFile`) when the shell is down or when an existing file does not parse with `version: 1`.

## 9. Verify (`verify(ctx, plan, status_after)`)

The executor calls `status()` after the last operation and passes the result. Verify may call status again while polling. Steps:

1. `status_after.shell.available` must be true, else `runtime_unavailable`.
2. Poll up to 2 seconds (10 × 200 ms) until `status_after.file.matchesShell` is true. On timeout return `bar_file_desync`. On the ipc route this waits for the shell's own asynchronous write; on the file route it waits for the shell's reload.
3. `serialize(status_after.bar)` must equal `plan.expected.bar` under these comparison rules: per section, same length, same id at each index, settings equal as canonical JSON; `extra` equal to the base `extra`; `id` compared by presence and value (`null` versus `"omarchy.bar"` are distinct, because the draft chose one); `position`, `transparent`, `centerAnchor` exact. Any difference is `validation_failed` with a diff in `errors[].detail`.
4. Every id inserted by the plan must have `enabled: true` in `listPlugins` (for a widget, that is `inBar`).
5. If the plan changed `bar.id`, or the base was in fallback: wait 3 seconds, take status again, and require `shell.fallback == false`. Failure is `bar_shell_fallback` with `configuredBarId` and `activeBarId` in the detail. This is the bounded wait described in section 2.6; the plan text in the review says "the shell gets three seconds to load the bar".
6. `status_after.revision` becomes the transaction's `afterRevision`.

Verify does not use `debugBarGeometry`. It stays available to the page as a diagnostics panel ("Show rendered geometry") for the built-in bar.

On any verify failure the executor runs the inverses in reverse order and calls verify again against the base `expected` (the module returns `plan.before` for that purpose; the executor treats the inverse plan's expected as the base bar). If the inverse plan also fails verification the transaction ends in `rollback_failed` and the page shows the recovery panel (section 10.3).

## 10. Page (`modules/bar/Page.qml`)

### 10.1 Layout

Top to bottom inside the shared AppShell content area:

1. Header row (shared): title "Bar", status chip ("Running omarchy.bar", or "Configured local.neon-bar, running omarchy.bar (fallback)"), Refresh, History.
2. `BarOptions`: full bar dropdown (disabled with reason when `selectBar` is unavailable), position segmented control (Top, Bottom, Left, Right), transparency switch, center anchor dropdown listing the current center ids plus "None". When `bar.id` names a non-built-in bar, position, transparency, and anchor stay editable but carry the note "stored for the built-in bar; `<name>` may ignore these".
3. `BarPreview` (section 10.2).
4. Two-column area: `WidgetCatalog` on the left, `WidgetInspector` on the right. The inspector shows the selected instance; with nothing selected it shows the draft summary (counts per section, route the plan will take, warnings).
5. Shared ApplyBar.

`focusFirst()` focuses the full bar dropdown.

`handlePayload(payload)` (amendment G) accepts two shapes. `{"select": {"section": "center", "index": 1}}` selects the draft entry whose origin is that occurrence (or, when the draft has moved it, the entry with that origin wherever it now sits), scrolls the preview to it, and focuses the inspector. `{"selectBar": "local.neon-bar"}` sets `draft.bar.id` to that id when it is in `barOptions` and focuses the full bar dropdown; an unknown id is ignored with a toast. Both are the deep links the plugins page sends with `requestNavigate("bar", payload)`, and `CustomizationCenter.open('{"module": "bar", ...}')` routes through the same function.

### 10.2 Preview canvas

A 16:9 rectangle stands for one screen (labelled "All monitors" because the layout is shared). The bar strip is drawn along the edge named by `draft.bar.position` with cross-axis thickness `Style.bar.sizeHorizontal` or `Style.bar.sizeVertical` scaled by the canvas scale, background `Color.bar.background` at 100% alpha or 45% when transparent, text `Color.bar.text`.

Section placement per orientation:

| Position | Axis | left section | center section | right section |
|---|---|---|---|---|
| top | horizontal, x grows right | starts at the left edge | centered; anchor entry centered exactly, before-entries to its left, after-entries to its right | ends at the right edge |
| bottom | same as top, strip at the bottom edge | | | |
| left | vertical, y grows down | starts at the top edge | centered vertically; before-entries above the anchor, after-entries below | ends at the bottom edge |
| right | same as left, strip at the right edge | | | |

Card sizing along the axis, in unscaled bar pixels: `icon` 27 (`Style.bar.iconSlot`), `text` 84 horizontal or 27 vertical (text widgets collapse to icons on vertical bars, `shell/plugins/bar/README.md:79`), `variable` 54 horizontal or 27 vertical, `spacer` the draft `size` (default 12, minimum 4 for visibility with a dashed outline when the real value is smaller than 4 or 0). Cards show the display name horizontally and the first letter vertically, with the full name in a tooltip. `omarchy.tray` is drawn at its stored index, with a small "drawn at inner edge" marker when the index differs (warning `bar_tray_pinned`).

When no anchor applies, the center group is centered as a whole. When the total card length of a section exceeds its available span, the section shows a "crowded" chevron and the page raises `bar_vertical_text` or a generic crowding note; the preview never scales cards down below their class size.

Insertion points are drawn between cards and at both ends of every section, including empty sections (a section with no entries renders one wide insertion point labelled "Empty").

The preview loads no widget QML. It reads only the draft and the catalog.

### 10.3 States

The page derives one `pageState` from `status`, `draft`, the BackendClient transaction state, and the DraftStore. The ApplyBar reads it to enable actions.

| State | Entered when | Shown | Allowed |
|---|---|---|---|
| `loading` | `status` is null | skeleton preview, disabled controls | Refresh |
| `shell-unavailable` | `status.shell.available == false` | banner with the reason from stderr; layout read from the file, marked "from file, unverified" | Restart shell (`TerminalHandoff(["omarchy-restart-shell"], "Restart Omarchy shell")`), Retry, editing the draft (kept), Save draft |
| `load-error` | status returned `malformed_output`, or `file.parses == false` while the shell serves defaults | banner naming the file and the parse error | Open file in editor (`TerminalHandoff([$EDITOR, path])`), Retry. No Apply; the module never overwrites a file it could not parse. |
| `scanning` | `status.shell.scanning` | banner "Plugin scan in progress" | Retry (auto-retry every 1 s up to 10 times) |
| `fallback` | `status.shell.fallback` | persistent note in the header and on the bar selector | everything; Apply of an unchanged `bar.id` carries `bar_fallback_now` |
| `ready-clean` | draft equals status | | all edits, Load defaults, Load preset |
| `ready-dirty` | draft differs | dirty marker on changed cards and options | Reset draft, Review, Save draft |
| `invalid` | validate returned errors | inline errors on fields and cards, summary in the inspector | edits only |
| `stale` | `draft.baseRevision != status.revision` (detected on Refresh, on a `pluginsChanged` signal from the injected `pluginRegistry` while the overlay is open, and by the executor at apply) | banner "The bar changed since this draft was created" | Reload (discard draft), Compare (DiffView of base vs current), Rebase (re-anchor origins by `(section, index, id)` where unambiguous, else mark those entries new and warn), Save draft |
| `plugin-vanished` | a draft entry's id has `presence != "shell"` but did at `baseRevision` | the card shows "unavailable"; validate yields `bar_unknown_widget` only if the entry is new | move or remove the entry; not duplicate or add |
| `reviewing` | plan returned | ChangeList grouped: Bar option, Position and appearance, Center anchor, Added, Moved, Settings, Removed, Preserved keys; route name and `rollbackExact` | Back, Apply, and on the ipc route "Apply through file" |
| `applying` | executor running | progress per operation summary line | none; navigation away shows a ConfirmDialog and the transaction continues |
| `verifying` | operations finished | "Waiting for the shell" with the settle countdown when a bar id changed | none |
| `applied` | verify passed | UndoToast with the transaction id; draft cleared; status refreshed | Undo (`ccctl rollback <id>`) |
| `rolled-back` | apply or verify failed and the inverses verified | ErrorBanner with the failing operation, its reply string, and "Your previous bar is back" | Retry review, Save draft |
| `rollback-failed` | inverses failed | recovery panel with transaction id, backup path from the journal, current `listShellConfig` bar, and the commands from section 16 | Copy commands, Open history |

### 10.4 Keyboard model

Focus order: options row, catalog search, catalog list, preview sections (left, center, right), inspector, ApplyBar. The preview is one focus scope; Tab enters it at the selected card or the first card.

| Key | Without grab | With grab (card picked up) |
|---|---|---|
| Arrow along the bar axis (Left/Right on horizontal bars, Up/Down on vertical) | move focus to the previous or next card, crossing section boundaries | move the grabbed card one position, crossing section boundaries; the draft updates immediately and the live region announces "Clock, center, position 2 of 5" |
| Arrow across the axis | move focus between preview and inspector | ignored |
| Home / End | first or last card in the current section | move the card to the start or end of the current section |
| Ctrl+Shift+Left / Ctrl+Shift+Right (Up/Down when vertical) | jump focus to the previous or next section | move the card to the end of the previous section or the start of the next |
| Space | grab the focused card | drop (keeps the current position) |
| Enter | open the inspector for the card | drop |
| Esc | clear selection | cancel: the card returns to where it was when grabbed |
| Delete | remove the card from the draft and show an UndoToast (draft-level, Ctrl+Z restores) | cancel the grab, then remove |
| Ctrl+D | duplicate (only when `allowMultiple`) and focus the copy | same |
| Insert or `a` | focus the catalog search; Enter in the catalog adds the highlighted widget after the selected card, or at the end of its `defaultSection` when nothing is selected | |
| Ctrl+Z / Ctrl+Shift+Z | draft undo and redo (page-local stack, cleared on Reset draft) | |

Pointer: drag starts from the card's handle; drop targets are the insertion points; dropping outside the preview cancels. The pointer and keyboard paths call the same `ReorderController.move(key, section, index)` and produce byte-identical drafts, which section 15 tests.

## 11. Loading defaults and presets

"Load Omarchy defaults" replaces the draft's `bar` with `status.defaults`. `defaults` is computed in the backend from `$OMARCHY_PATH/config/omarchy/shell.json` `.bar`, plus `omarchy.dropbox` and `omarchy.tailscale` inserted after `omarchy.tray` in `right` (their catalog `defaultSection`, anchors from `bin/omarchy-bar:179`) when the corresponding `omarchy-installed-service-<name>` succeeded. This reproduces `bin/omarchy-bar:159-196` so the user reviews a diff instead of running a command blind. `bar.id` becomes `null`. The review then applies through the file route because options change. A parity test runs the real `omarchy-bar defaults` in an isolated HOME and compares.

"Save as preset" writes the draft `bar` (origins stripped, keys regenerated) to `~/.config/omarchy/customization-center/bar-presets/<slug>.json` under `bar-preset-v1.json`:

```json
{ "schemaVersion": 1, "id": "presentation", "name": "Presentation", "bar": { "id": null, "position": "top", "transparent": true, "centerAnchor": "omarchy.clock", "extra": {}, "layout": { "left": [], "center": [], "right": [] } } }
```

Loading a preset builds a draft from the stored subtree through `model.rebase` (section 5.2), so unchanged widgets keep their identity and the plan is a minimal diff. Presets are a convenience of this page only. Desktop modes does not reference them; it stores the target `bar` subtree inline in the mode file and hands it to this module in the shape described in section 5.2.

## 12. Ownership boundary with the plugins module

Amendment H fixes the boundary:

- The bar module is the only writer of the `bar` subtree: `bar.id` (full-bar selection), `bar.position`, `bar.transparent`, `bar.centerAnchor`, every `layout` entry, and every inline setting. It holds the claim `shell.bar`.
- The plugins module writes `plugins[]` and `disabledPlugins[]` only, and runs lifecycle actions. It does not place widgets, edit widget settings, or switch the bar.
- For a bar widget or a full-bar plugin, the plugins page shows placement and settings read-only and offers "Edit in bar editor", which is `requestNavigate("bar", {"select": {"section": s, "index": i}})` for an instance or `requestNavigate("bar", {"selectBar": id})` for a bar option. This page's `handlePayload` (section 10.1) selects the instance or pre-selects the bar in the draft; the user reviews and applies here. There is no other path: the plugins page never submits bar drafts on its own.

The schema renderer and the `spacerSettings@1` and `weatherSettings@1` adapters are core code (amendment F), so neither module owns the other's forms. Weather's location stays outside every draft; the inspector shows "Location is set with `omarchy-weather-location`" and offers `TerminalHandoff(["omarchy-weather-location"], "Weather location")`.

## 13. Required core changes

None beyond the contract amendment sheet. Everything this module needs from core is already in it: inverse tuples (B), `ShellIpc(method, args, expect, backup_paths)` with core-owned reply classification and the shared `ipc_rejected` code (B, J), `WriteFileAtomic` removing a previously absent file on rollback (B, C), `settings_schema` with the two named-form adapters and `catalog.join` (F), and `handlePayload` with `requestNavigate` (G).

Adding this module is `modules/bar/` plus one line in `backend/customization_center/modules/__init__.py`.

## 14. Upstream Omarchy changes that would remove the file route

The earlier version of this plan made a new shell IPC (`getBarState` and `applyBarConfig <expectedRevision> <barJsonB64>`) a prerequisite for Apply. At 71b0887c that IPC does not exist and nothing equivalent has appeared; the gaps are exactly the six items in section 2.2. This revision no longer waits for it. The file route covers those gaps with the same mechanism Omarchy's own `omarchy bar position` uses, and the ipc route keeps the shell as the writer for the common layout and settings edits.

If Omarchy later adds a compare-and-swap whole-bar method, this module should switch the file route to a single `ShellIpc("applyBarConfig", ...)` and drop section 8.5. Until then the request is recorded here rather than blocking the release.

## 15. Tests

### 15.1 Fixtures (`modules/bar/tests/fixtures/`)

Shell config documents (`listShellConfig` replies and, where noted, file contents):

| Fixture | Content |
|---|---|
| `config-default.json` | copy of `config/omarchy/shell.json` |
| `config-explicit-builtin.json` | default plus `"id": "omarchy.bar"` |
| `config-two-spacers.json` | default with `omarchy.spacer` (`size` 12) at `left[1]` and `omarchy.spacer` (`size` 40) at `right[0]` |
| `config-two-indicators.json` | default with a second `omarchy.indicators` (`items: ["Dnd"]`) at `right[2]` |
| `config-custom-command.json` | default with `{ "id": "vpn", "type": "command", "exec": "~/bin/vpn", "interval": 5 }` at `right[1]` |
| `config-string-entries.json` | default with `left` written as `["omarchy.menu", "omarchy.workspaces"]` |
| `config-third-party-bar.json` | default plus `"id": "local.neon-bar"` |
| `config-unknown-keys.json` | default plus `bar.futureKey: 7` and `omarchy.clock.futureSetting: true` |
| `config-clone-clock.json` | default with `omarchy.clock` replaced by `dhh.clock` |
| `config-empty-sections.json` | `layout` with three empty arrays |
| `config-no-anchor.json` | default with `centerAnchor: ""` |
| `config-duplicate-clock.json` | default with a second `omarchy.clock` at `right[3]` (not allowed by manifest, present anyway) |
| `config-malformed.txt` | `{ "version": 1, "bar": ` (truncated) |
| `config-version-missing.json` | default without `version` |

`listPlugins` replies:

| Fixture | Content |
|---|---|
| `plugins-default.json` | the 24 first-party rows at 71b0887c, `omarchy.bar` active |
| `plugins-with-local-bar.json` | default plus `local.neon-bar` (`kinds: ["bar"]`, `enabled: true`, `active: true`) and `omarchy.bar` inactive |
| `plugins-bar-fallback.json` | as above but `local.neon-bar` `active: false`, `omarchy.bar` `active: true` |
| `plugins-clone-clock.json` | default plus `dhh.clock` with `clonedFrom: "omarchy.clock"`, enabled |
| `plugins-missing-weather.json` | default without `omarchy.weather` |
| `plugins-empty.json` | `[]` (scan in progress) |
| `plugins-third-party-widget.json` | default plus `acme.gpu` bar widget with `allowMultiple: true` in its catalog row |

Catalog replies: `catalog-default.json` (real `omarchy-plugin-catalog` output captured from the tree), `catalog-bad-schema.json` (indicators schema with a duplicate key and an `integer` field whose `min` exceeds `max`), `catalog-missing.json` (empty array).

The `omarchy-shell` stub takes `BAR_TEST_CONFIG`, `BAR_TEST_PLUGINS`, and `BAR_TEST_MODE` from the environment, answers `ping`, `listShellConfig`, `listPlugins`, `reloadConfig`, applies `enablePlugin`, `moveBarWidget`, `setBarWidget`, `setPluginEnabled` to an in-memory copy with the same algorithms as `PluginRegistry.qml` (ported to Python in `tests/stubs/registry_model.py` with its own tests against captured shell behavior), appends every call to `$XDG_STATE_HOME/bar-test/ipc-calls`, and in mode `down` exits 1 with `omarchy-shell is not running`, in mode `hang` sleeps past the timeout, in mode `reject:<method>` answers `no widget at right[9]` to that method.

### 15.2 Backend unit tests

| Test | Fixture | Expectation |
|---|---|---|
| `test_status_default` | `config-default`, `plugins-default`, `catalog-default` | 14 occurrences, `bar.id == null`, `configuredBarExplicit == false`, `fallback == false`, indicators `allowMultiple == true`, categories match the manifests |
| `test_status_explicit_builtin` | `config-explicit-builtin` | `bar.id == "omarchy.bar"`, `configuredBarExplicit == true` |
| `test_status_string_entries` | `config-string-entries` | `form == "string"` on both left entries; serialization round-trips to strings |
| `test_status_unknown_keys` | `config-unknown-keys` | `extra == {"futureKey": 7}`; clock settings include `futureSetting` |
| `test_status_layout_only` | `config-custom-command` | `vpn` has `presence == "layout-only"`, `category == "Custom"` |
| `test_status_fallback` | `config-third-party-bar`, `plugins-bar-fallback` | `fallback == true` |
| `test_status_scanning` | `config-default`, `plugins-empty` | `scanning == true`, `applyIpc.available == false` |
| `test_status_shell_down` | mode `down` | `shell.available == false`, `bar` read from file, revision starts with `unavailable:` |
| `test_status_malformed_file` | file `config-malformed.txt`, shell serves defaults | `file.parses == false`, `applyFile.available == false` |
| `test_revision_ignores_active` | `plugins-with-local-bar` vs `plugins-bar-fallback` | equal revisions |
| `test_revision_changes_on_plugin_set` | `plugins-default` vs `plugins-missing-weather` | different revisions |
| `test_defaults_parity` | isolated HOME, stubs for `omarchy-installed-service-dropbox` (exit 0) and `-tailscale` (exit 1) | `status.defaults` equals the file `omarchy-bar defaults` writes |
| `test_validate_duplicate_not_allowed` | draft adds a second `omarchy.clock` | `bar_duplicate_not_allowed` |
| `test_validate_existing_duplicate_warns` | `config-duplicate-clock` unchanged | warning only |
| `test_validate_anchor_missing` | draft removes clock, keeps anchor | `bar_anchor_missing` |
| `test_validate_anchor_ambiguous_new` | draft adds second indicators to center and sets anchor to indicators | `bar_anchor_ambiguous` |
| `test_validate_schema_bad` | `catalog-bad-schema` | indicators `schema.ok == false`, edits to `items` rejected, moves allowed |
| `test_route_ipc_moves_only` | move clock to `right[0]` | route `ipc`, one `moveBarWidget` with `fromSection center fromIndex 1 section right index 0` |
| `test_route_file_position` | position `left` | route `file`, three operations |
| `test_route_file_second_instance` | `config-two-spacers`, draft adds a third spacer | route `file` |
| `test_route_file_key_removed` | draft deletes clock `formatAlt` | route `file` |
| `test_route_file_clone` | `config-clone-clock`, `plugins-clone-clock`, draft removes `dhh.clock` | route `file` |
| `test_route_file_custom_removed` | `config-custom-command`, draft removes `vpn` | route `file` |
| `test_plan_remove_exact_second_spacer` | `config-two-spacers`, draft removes `right[0]` spacer | ops: `moveBarWidget spacer fromSection right fromIndex 0 section left index 0`, `setPluginEnabled spacer false`; simulation equals draft |
| `test_plan_remove_first_match_no_move` | `config-two-spacers`, draft removes `left[1]` spacer | one `setPluginEnabled` only |
| `test_plan_insert_first_instance` | draft adds `omarchy.microphone` at `right[2]` with no settings | one `enablePlugin` with `section right index 2` |
| `test_plan_insert_then_settings` | draft adds `acme.gpu` with `{"unit": "C"}` | `enablePlugin` then `setBarWidget acme.gpu unit "\"C\""` selector `right[k]`; inverse of the set is `[]` |
| `test_plan_remove_then_add_same_id` | draft removes clock at `center[1]` and adds a new clock at `left[0]` | phase 1 disable precedes phase 2 enable (I1) |
| `test_plan_phase_order_invariants` | random drafts generated from `config-default` (property test, 500 cases) | simulation equals draft; every selector valid in `W` at emission; settled prefix never referenced |
| `test_plan_settings_inverse_exact` | change clock `format` | inverse `setBarWidget` with the old value |
| `test_plan_settings_inverse_approximate` | add `format` to `omarchy.keyboard-layout` | inverse writes `null`, `rollbackExact == false`, warning present |
| `test_plan_file_document` | `config-unknown-keys`, position `bottom` | written document keeps `futureKey`, `futureSetting`, `idle`, `plugins`, key order; `version` first |
| `test_plan_file_creates_when_defaults` | shell serves defaults, no user file | WriteFileAtomic declared; review text says the file will be created |
| `test_plan_stale` | draft base != status | `stale_revision`, no operations |
| `test_verify_pass` | stub applies ops | verify ok, `afterRevision` set |
| `test_verify_desync` | stub mode `nowrite` (applies in memory, never writes the file) | `bar_file_desync` after 2 s |
| `test_verify_fallback` | draft sets `local.neon-bar`, stub flips `active` after 1 s | `bar_shell_fallback` |
| `test_verify_mismatch` | stub mode `reject:setBarWidget` | operation failure, inverses run in reverse, base restored, transaction `rolled_back` |
| `test_rollback_file_route` | file route, verify forced to fail | file restored byte for byte (or removed when absent before), `reloadConfig` called after the restore |

### 15.3 Adapter contract tests

Exact argv this module emits for `omarchy-shell shell ping|listShellConfig|listPlugins|enablePlugin|moveBarWidget|setBarWidget|setPluginEnabled|reloadConfig`, `omarchy-plugin-catalog`, `omarchy-installed-service-dropbox`, and that each operation declares `expect=("ok",)` and `backup_paths`. Stderr and exit-code classification is core-owned and tested in `tests/core`; this module's tests only assert that the shell reply bodies `unknown`, `not ready`, `no widget at right[3]`, `widget at center[1] is not omarchy.clock`, `could not find widget x`, and `invalid placement: SyntaxError` become `ipc_rejected` with the body in the message, and that non-JSON stdout for the list methods becomes `malformed_output`.

### 15.4 QML and model tests

- Every state in section 10.3 renders from a fixture status and a scripted BackendClient; Apply is enabled only in `ready-dirty` with a valid draft.
- Keyboard grab and pointer drop produce identical drafts for: move within section, move across sections, move to an empty section, move to section start and end, cancel with Esc.
- `handlePayload({"select": {"section": "right", "index": 0}})` on `config-two-spacers` selects the second spacer; the same payload after that spacer was moved in the draft still selects it. `handlePayload({"selectBar": "local.neon-bar"})` with `plugins-with-local-bar` sets the draft bar id; with `plugins-default` it shows a toast and changes nothing.
- Selection follows `key`: with `config-two-spacers`, selecting the second spacer and editing `size` changes only that entry.
- Preview: for each of the four positions, the anchor card's center equals the strip's center within 1 px at scale 1; vertical bars place left entries above center entries above right entries; text cards shrink to 27 on vertical bars.
- No process call from selection, drag, or edits (the BackendClient spy records zero calls until Review).
- Font scale 1.5 and spacing overrides from `Style` do not overflow the options row.

### 15.5 Integration (fake shell, isolated HOME)

The stub applies operations and writes the file, so these run the executor end to end:

1. Add first `omarchy.microphone`, move it, apply, verify; restart the stub with the written file and confirm status matches.
2. `config-two-indicators`: change `items` on the second instance only; the first is unchanged in the file.
3. Remove the second spacer; the first spacer keeps `size` 12.
4. External change between plan and apply (stub mutates on `ping`): `stale_revision`, no mutation.
5. Manifest vanishes between plan and apply (`plugins-missing-weather` swapped in): revision differs, `stale_revision`.
6. Position change on the file route with no user file: file created, verify passes, rollback removes it.
7. Third-party bar selected, stub reports fallback after 1 s: `bar_shell_fallback`, rollback to `bar.id` absent, verify passes.
8. Shell stops after operation 2 of 4 (stub mode `die-after:2`): operation 3 fails `runtime_unavailable`, inverses of 1 and 2 also fail, transaction `rollback_failed`, journal has the backup path, no file written by the module.
9. Unknown keys survive an ipc-route apply and its undo.
10. Load defaults with dropbox installed: diff lists dropbox as added; apply via file route; parity with `omarchy-bar defaults` output.

### 15.6 Live checks (disposable Omarchy VM)

Top, bottom, left, right; one and two monitors; dark and light themes; default and enlarged font; the two-spacer and two-indicators layouts; a custom command entry; `dhh.clock` clone active; a third-party bar that loads and one whose `Bar.qml` has a syntax error; shell restart with a dirty draft and during `rollback-failed`.

## 16. Recovery without the page

Documented in `docs/recovery.md` and shown in the `rollback-failed` panel:

```text
ccctl history --module bar --limit 5            # find the transaction and its backup path
cp <backup> ~/.config/omarchy/shell.json && omarchy-shell shell reloadConfig
omarchy-bar defaults                             # last resort: shipped layout plus installed service widgets
omarchy-restart-shell                            # when the shell no longer answers ping
```

## 17. What the first release refuses to do

- Create new custom `command` or `qml` entries. Existing ones can be moved and removed.
- Edit `bar.extra` or unknown entry keys. They are preserved and listed.
- Edit theme bar dimensions (`shell.toml [bar]`) or the hidden flag.
- Per-monitor layouts. The shell has none.
- Instantiate widget QML in the preview.
- Apply while the shell is down, and write `shell.json` when the existing file does not parse.
- Preview on the real desktop before apply. The real bar changes only during apply, followed by verify and automatic rollback.
- Address one of several same-id center entries as the anchor. The shell pins the first; the page prevents creating new ambiguity and explains inherited ambiguity.

Residual risks, stated once: a bar gesture between the executor's revision check and the first operation can shift indices; the shell rejects mismatched ids but not a same-id swap between two `allowMultiple` instances. Rolling back a newly added key on the ipc route writes `null`. A third-party bar that fails after the 3 second settle window is reported by the next status, not by the transaction that selected it.

## 18. Delivery order

1. Backend status, model, revision, defaults, fixtures, stub. Exit: `ccctl status bar` matches every fixture; no writes.
2. Page in read-only form: options, preview in four orientations, catalog, inspector, states `loading`, `shell-unavailable`, `load-error`, `scanning`, `fallback`.
3. Draft editing: reorder controller (pointer and keyboard), add, duplicate, remove, settings via the core `SchemaForm`, validate.
4. Planner both routes, simulation, review ChangeList, verify, rollback, undo. Exit: section 15.5 cases 1 to 9 pass.
5. Load defaults, presets, deep link from the plugins module, desktop-modes plan entry.
6. Live checks, recovery doc, accessibility pass.
