# Omarchy Customization Center master plan

Status: source implementation complete; live desktop and VM release acceptance pending. The design baseline was verified against `omarchy-fork` at commit `71b0887c`, Hyprland 0.56.2, and Python 3.14.7 on the development host.

## Execution record

Classification: complex. The feature crosses the QML shell, Python transaction core, eight module contracts, external command adapters, persistent schemas, and rollback behavior.

Integration owner: the active parent Pi session. Workers may edit only their assigned paths. The integration owner alone updates this plan, the module registry, shared documentation, the final report, and plan status.

Continuation base: repository commit `cd80826d2f9cf7575a41dbe411bddcf0da58a782`. The cumulative integration changes remain uncommitted so the parent session can review and integrate them as one release candidate. All eight modules are registered and implemented.

Current checkpoint:

- The transaction core records in-flight forward and inverse operations, reconciles only exact post-images, resumes partial rollback without repeating completed inverses, and blocks ambiguous external effects.
- Directory replacement rollback binds the expected staged image, observed installed image, raw forward result, original target image, and generated previous-directory identity before undo. Missing, legacy, contradictory, or changed evidence fails closed.
- Monitor mode caches are display-only. Plugin handoffs retain registry fallback polling. Mode imports rewrite renamed monitor-profile references.
- Reviewed drafts carry one validated plan context. Monitor activation rejects stale contexts; modes export and theme save reuse their reviewed timestamps. `ApplyBar.qml` applies the exact normalized draft that produced the reviewed plan.
- The canonical test command collected and passed 511 tests. One QML runtime test skipped because the required Quickshell/Hyprland runtime is unavailable. `git diff --check`, staged-file, bytecode, and pytest-cache checks passed.
- Three fresh provider-distinct final reviews approved the source candidate. Core review reported 94/100 confidence, module integration 87/100, and release/report truthfulness 88/100. No P0 or P1 remains. Reviewers retained the documented cross-filesystem residue and unavailable runtime checks as P2 notes.
- Live Quickshell/Hyprland desktop checks, the `omarchy-iso-test` VM matrix, and the manual TTY recovery drill remain release gates. This plan stays under `plans/planned/` until those checks pass.

Approved contract corrections:

- Add optional operation inverse dependencies as `inverseAfter` on the wire and `inverse_after` in Python. The generic executor validates and applies them in automatic rollback and committed user undo. Reverse completion order remains the stable default when no dependency changes it.
- A failed handoff reconciliation stores the module's `VerifyResult`, including code, reason, and evidence, then rolls back with reason `verification`. `handoff_failed` is reserved for launcher or sentinel failure.
- Abandoning a pending handoff rolls back every completed reversible operation. The handoff itself remains non-reversible and may continue outside the plugin.
- The monitor mode cache and `monitors_stale_modes` warning remain required. Removing them would be a product change and is not approved.

Execution waves:

1. Complete. `CORE-ROLLBACK-01` delivered generic verification persistence, safe abandon, inverse dependency ordering, schemas, and core tests. Handoff: `reports/handoffs/core-rollback-01.md`.
2. Complete. `DEFAULTS-HARDEN-01` and `THEMES-HARDEN-01` closed their module review findings. Handoffs: `reports/handoffs/defaults-harden-01.md` and `reports/handoffs/themes-harden-01.md`.
3. Complete. `BAR-IMPLEMENT-01`, `PLUGINS-IMPLEMENT-01`, and `MODES-IMPLEMENT-01` landed in dependency order. Handoffs are under `reports/handoffs/`.
4. Source-complete. Integration, monitor cache work, cross-workstream validation, review finding disposition, and `reports/customization-center-implementation.html` are complete. Live desktop, VM, and TTY recovery checks remain.

The unresolved release choices near the end of this plan block a tagged release claim, not source acceptance.

## Goal

Build one third-party Omarchy shell plugin that gives users a graphical, reviewable, reversible way to change their running desktop. The plugin ships eight modules:

1. Visual bar editor (`bar`)
2. Plugin settings (`plugins`)
3. Personal menu editor (`menu`)
4. Default application manager (`defaults`)
5. Monitor layout profiles (`monitors`)
6. Theme composer (`themes`)
7. Keybinding editor (`keybindings`)
8. Desktop modes (`modes`)

The plugin owns the interface, drafts, validation, previews, backups, and transaction history. Omarchy commands, shell IPC, and the documented user configuration files stay the source of truth. Nothing in this plugin replaces `omarchy plugin add`, `omarchy-theme-set`, the default-app selectors, or the updater.

The user's one hard requirement for the architecture is that it must be modular and easy to extend. Section "Shared architecture" is written to a single acceptance test: adding a ninth module touches one new directory and one line in a list, and nothing in `core/`.

## Recommendation

Ship one `overlay` plugin with eight internal modules, not eight plugins. The modules share navigation, discovery, the executor, backups, the journal, and rollback, and desktop modes have to compose plans across modules. Eight repositories would duplicate the executor eight times and make that composition impossible.

The plugin id is `firstpick.customization-center`. Third-party ids must match `^[A-Za-z0-9][A-Za-z0-9._-]*$` (`bin/omarchy-plugin-validate:51`), must not contain `/` or `..` (`shell/services/PluginRegistry.qml:60`), and must not start with `omarchy.`; the registry drops any third-party manifest in that namespace (`shell/services/PluginRegistry.qml:599-607`, `bin/omarchy-plugin-validate:53`).

Manifest:

```json
{
  "schemaVersion": 1,
  "id": "firstpick.customization-center",
  "name": "Customization Center",
  "version": "0.1.0",
  "author": "Firstpick",
  "description": "Graphical runtime customization for Omarchy",
  "kinds": ["overlay"],
  "entryPoints": {
    "overlay": "CustomizationCenter.qml"
  }
}
```

`validateManifest` requires `schemaVersion === 1` and the fields `id`, `name`, `version`, `kinds`, `entryPoints` (`shell/services/PluginRegistry.qml:48-58`). `author` and `description` are optional. Entry points must be relative paths without `..` (`PluginRegistry.qml:36-41, 83-88`). Extra top-level keys pass through untouched, which is what lets `keepLoaded` work and what lets this plugin add its own keys later.

Install and open:

```bash
omarchy plugin add https://github.com/firstpick/omarchy-customization-center.git
omarchy plugin enable firstpick.customization-center
omarchy-shell shell summon firstpick.customization-center '{}'
```

The enable step is not optional. A third-party plugin is enabled only when its id appears in `shell.json` `plugins[]` (`docs/omarchy-shell.md:168-169`, `PluginRegistry.qml:138`), `omarchy plugin add` lands plugins disabled by design (`docs/omarchy-shell.md:84-86`), and `summon` refuses a disabled plugin with a console warning (`shell/shell.qml:451-454`). The recovery docs must say this in the first paragraph, because "I installed it and nothing opens" will be the first support question.

Overlay contract, as the host actually implements it:

- The entry point is a QML `Item`. On load the host assigns `omarchyPath`, `shell`, `manifest`, `barWidgetRegistry`, `pluginRegistry`, and `service` if the item declares those properties (`shell/shell.qml:629-637`). `manifest.__sourceDir` is the absolute plugin directory (`PluginRegistry.qml:564`), which is how the overlay finds its own `backend/ccctl`.
- `summon <id> <payloadJson>` queues the payload and calls `item.open(payloadJson)` once the `Loader` has an item (`shell.qml:462-477, 546-551`). `omarchy-shell` fills in `{}` when the payload is omitted (`bin/omarchy-shell:51-53`).
- `hide <id>` calls `item.close()` and then removes the id from `openPanelIds` (`shell.qml:489-494`). The `Loader` is active only while the plugin is open or the manifest sets `keepLoaded: true` (`shell.qml:600, 625`; `docs/omarchy-shell.md:40-41`). Without `keepLoaded`, closing destroys the QML tree.
- `isPluginOpen` reads `item.opened` when it exists (`shell.qml:505-506`), so the overlay root exposes `property bool opened`.

Do not set `keepLoaded` in the first release. It keeps the whole overlay resident in the long-running shell process for the price of faster reopen; `omarchy.image-picker` pays that price because it is summoned many times a session (`shell/plugins/README.md:76-77`), a settings overlay is not. The consequence is that unsaved QML state dies on close, so drafts persist through the backend (see `DraftStore`). Revisit only with a measured cold-open number above 300 ms.

## Confirmed Omarchy findings

Every row cites the line that proves it.

| Area | What the source says | Consequence |
|---|---|---|
| Plugin host | One Quickshell process hosts `bar-widget`, `bar`, `panel`, `overlay`, `menu`, `service` plugins (`docs/omarchy-shell.md:27-36`). Panels, overlays, menus load on summon (`shell.qml:610-653`). | The center is one overlay in the existing process. It never starts a second Quickshell. |
| Plugin directory watch | `inotifywait -m -r` on `~/.config/omarchy/plugins` (`PluginRegistry.qml:636-655`); any `close_write,create,delete,move` under a plugin dir schedules `reloadPlugins()` 150 ms later (`shell.qml:59-63, 763-766`). Dot-prefixed entries and `.git` are ignored (`PluginRegistry.qml:707-709`). | The plugin must never write inside its own directory at runtime. That includes Python bytecode. `ccctl` sets `sys.dont_write_bytecode = True` before any import, or the first backend call reloads the overlay that spawned it. All state lives under XDG paths. |
| Third-party scan | Only `~/.config/omarchy/plugins/*/manifest.json` at the top level (`PluginRegistry.qml:683-689`). | `modules/<id>/` subdirectories are invisible to the registry. Module directories can hold `module.json` without being mistaken for plugins. |
| Unsandboxed code | Plugins run as unsandboxed code in `omarchy-shell` (`docs/omarchy-shell.md:84-86`). | Treat the backend and generated files as trusted local code. Argument arrays everywhere, no interpolated shell strings. |
| `shell.json` ownership | A valid user file is canonical, otherwise defaults; no deep merge; `version: 1` required (`shell.qml:72-87`; `docs/omarchy-shell.md:174-176`). The shell writes it through `FileView` with `atomicWrites: true` and watches it (`shell.qml:130-139, 108-113`). `omarchy bar use|reset|defaults|position|transparent` write the file with `mv` and then call `reloadConfig` (`bin/omarchy-shell-config:53-59, 14-18`; `bin/omarchy-bar:142-216`). `put|move|set` go through IPC (`bin/omarchy-bar:241, 329, 361`). | Omarchy itself has two writers, and the bar module uses both routes: IPC for what IPC expresses exactly, and the same file-then-`reloadConfig` route `omarchy bar position` uses for everything else, with a revision check against `listShellConfig` plus the file hash. |
| Shell IPC methods | `ping`, `applyTheme`, `rescanPlugins`, `reloadConfig`, `toggleBarTransparency`, `setPluginEnabled`, `enablePlugin`, `putBarWidget`, `moveBarWidget`, `setBarWidget`, `listPlugins`, `listShellConfig`, `debugBarGeometry`, `summon`, `hide`, `toggle`, `togglePanelAt`, `call` (`shell.qml:872-1030`). No setter for `bar.position`, `bar.centerAnchor`, or an explicit transparency value. | Position, transparency, center anchor, bar id, second instances of `allowMultiple` widgets, inline key deletion, and removal of custom entries go through the file route. `getBarState` and `applyBarConfig` upstream would remove that route; they are not a blocker. |
| IPC failure modes | `omarchy-shell` exits 1 for transport failures and for the strings `Target not found.`, `Function not found.`, `Too few/many arguments`, `Not ready to accept queries yet`; other method errors such as `unknown`, `no-bar`, `could not find widget X` come back on stdout with exit 0 (`bin/omarchy-shell:55-77`; `docs/omarchy-shell.md:128-130`). Default timeout 2 s via `OMARCHY_SHELL_IPC_TIMEOUT` (`bin/omarchy-shell:58-59`). Needs `OMARCHY_PATH` (`bin/omarchy-shell:40`). | `core/shell_ipc.py` allowlists success bodies per method and treats every other body as failure regardless of exit code. |
| Plugin listing | `omarchy plugin list --json` prints `listPlugins` unchanged (`bin/omarchy-plugin-list:28-33`). Rows are `{id, name, kinds, enabled, active, canDisable, firstParty, clonedFrom}` sorted by name (`shell.qml:962-988`). | Call `omarchy-shell shell listPlugins` directly from the backend; the wrapper adds nothing. |
| Plugin catalog | `omarchy-plugin-catalog` walks `$OMARCHY_PATH/shell/plugins` (depth 2 to 4) and `~/.config/omarchy/plugins` (depth 2) and prints `{id, name, description, kinds, firstParty, manifestPath, sourceDir, entryPoints, barWidget, bar, barWidgetPath, barPath}` with `unique_by(.id)` (`bin/omarchy-plugin-catalog:65-108`). No `version`, no `author`, no enabled state, no load errors; `firstParty` is a prefix test. | Catalog output enriches runtime rows; it is never the authority on what the shell loaded. |
| Widget settings | Manifests may carry `barWidget.schema` (field dialect `min`, `max`, `step`, `defaultValue`) or an opaque `settingsForm` name; the registry validates neither (`PluginRegistry.qml:72-78` validates only `defaultSection`). | Generic renderer for the declared dialect, explicit adapters for `spacerSettings` and `weatherSettings`, read-only otherwise. |
| Personal menu | Defaults in `$OMARCHY_PATH/default/omarchy/omarchy-menu.jsonc`, user file `~/.config/omarchy/extensions/omarchy-menu.jsonc`, both watched (`shell/plugins/README.md:102-112`). `omarchy-menu refresh` and `omarchy-menu ping` exist (`bin/omarchy-menu:4, 29`). | Write only the user file. The menu plan found that a user entry currently shadows the whole shipped entry rather than overlaying fields; see Module 3. |
| Default applications | `omarchy-default-browser`, `-terminal`, `-editor`, `-agent` exist under `bin/`; `omarchy commands --json` publishes their public choices (`bin/omarchy:522, 751`). | Four categories in the first release, delegated to the selectors. |
| Monitors | `~/.config/hypr/monitors.lua` is required after Omarchy defaults and before `default.hypr.toggles` (`config/hypr/hyprland.lua`); `omarchy-hyprland-monitor-*` helpers write toggle Lua under `~/.local/state/omarchy/toggles/hypr/`. Hyprland 0.55+ config is Lua (`~/.hyprwiki/content/Configuring/Basics/Monitors.md:8-9`). | One loader block in `monitors.lua`, generated rules in a separate file, toggles inventoried as later-loading overrides. |
| Keybindings | `bin/omarchy-menu-keybindings:275-277` parses plain `hyprctl binds` because Hyprland 0.56.0 emitted invalid JSON for binds and older versions broke on quotes. `--print` exists (`bin/omarchy-menu-keybindings:655`) but prints a display format. | Plain output is the primary inventory; JSON is enrichment after reconciliation. |
| Themes | User themes under `~/.config/omarchy/themes/<name>/`, backgrounds overlay under `~/.config/omarchy/backgrounds/<name>/` (`docs/theming.md:10-11`); `omarchy-theme-set <theme-name>` activates (`bin/omarchy-theme-set:4`). `shell.<section>.toml` replaces a whole section (`docs/omarchy-shell.md:189-194`). | Data-only generation, activation through the command, complete section fragments only. |
| Visual tokens | `Color`, `Style`, `Border` singletons in `qs.Commons` (`docs/omarchy-shell.md:203-216`); shared controls in `shell/Ui/`; a reference gallery at `shell/plugins/dev-gallery/`. | Pages use Omarchy controls and tokens. The theme composer's preview cannot use them for draft colors because they are process-wide singletons. |
| `$OMARCHY_PATH` | Sourced from `/etc/omarchy.conf` when present, otherwise `/usr/share/omarchy` (`default/bash/env-bootstrap:10-16`); the uwsm session exports it; the shell reads it from the environment (`shell.qml:27`) and injects it into plugins (`shell.qml:629`). `omarchy-restart-shell:8` recovers it from `systemctl --user show-environment` when run from a TTY. | `BackendClient` passes the injected `omarchyPath` to `ccctl` explicitly. `ccctl` falls back to `/etc/omarchy.conf`, then `/usr/share/omarchy`, when run from a terminal. |
| Python | Not listed as a package. It arrives through `python-gobject` and `nautilus-python` (`install/omarchy-base.packages:86, 106`), and Omarchy's own tools depend on it with `#!/usr/bin/python3` (`bin/omarchy-file-select:1`, `bin/omarchy-dev-font:1`). `#!/usr/bin/env python3` can resolve to a mise-managed interpreter; Omarchy patches that out of `powerprofilesctl` and `lutris` (`install/config/fix-powerprofilesctl-shebang.sh:1-3`, `bin/omarchy-install-gaming-lutris:12-14`). | `ccctl` uses `#!/usr/bin/python3`, standard library only, minimum 3.11 for `tomllib`. |
| Acceptance suite | `test/acceptance` runs inside a live Omarchy VM installed by `omarchy-iso-test` and reached over SSH (`test/acceptance:3-5`). | Graphical acceptance tests reuse that environment. |

### Evidence reviewed

`docs/omarchy-shell.md`, `docs/menu.md`, `docs/theming.md`, `shell/shell.qml`, `shell/services/PluginRegistry.qml`, `shell/plugins/README.md`, `shell/plugins/bar/README.md`, `shell/Ui/`, `shell/plugins/dev-gallery/`, `bin/omarchy-shell`, `bin/omarchy-shell-config`, `bin/omarchy-bar`, `bin/omarchy-plugin-*`, `bin/omarchy-default-*`, `bin/omarchy-menu`, `bin/omarchy-menu-keybindings`, `bin/omarchy-theme-set`, `bin/omarchy`, `config/omarchy/shell.json`, `config/omarchy/extensions/omarchy-menu.jsonc`, `config/hypr/*.lua`, `default/bash/env-bootstrap`, `install/omarchy-base.packages`, `test/acceptance`, and the eight module plans under `plans/planned/subplugins/`, which carry their own line-level citations for their areas.

## Product boundaries

In scope for the first release: runtime customization of an installed Omarchy desktop, read-only discovery before any write, drafts with a review step, atomic writes, backups and rollback for every managed file, calling existing Omarchy commands where they own the operation, one shared history, keyboard and pointer parity.

Out of scope: installer-time package choices, general package management, free-form editing of Lua, QML, shell, or TOML, replacing Omarchy's own installers and activators, secrets, continuous enforcement of any setting, hosted sync, and any write under `$OMARCHY_PATH`.

## Product principles

1. Show current state before offering a change.
2. Drafts are separate from applied state, and a draft never applies itself.
3. Every apply has a plan the user can read first.
4. Handwritten configuration outside a marked managed block is preserved byte for byte.
5. Where an Omarchy command or IPC method owns an operation, call it.
6. Installation, privilege, and destructive side effects are never behind a toggle.
7. Rollback is offered on the page that applied the change.
8. Generated files are inspectable and documented.
9. A setting is reported active only after the runtime confirms it.
10. A warning names the file, the setting, and the recovery action.

## Shared architecture

### Why this shape

Each module has the same life: read state, edit a draft, validate, plan, apply, verify, roll back on failure. The first draft of this plan gave each module its own apply and rollback code. That design fails the extension test twice over. A ninth module would have to reimplement locking, backups, and journaling, and desktop modes could not roll back a theme change and a monitor change the same way. So the contract below moves apply and rollback out of the modules entirely. A module describes what should happen as a list of operations with inverses; the core executor is the only code that touches the filesystem or spawns a process during apply. Modules stay small, testable without a desktop, and composable.

### Repository layout

```text
Omarchy-Plugin-Customization-Center/
├── manifest.json                       Omarchy plugin manifest, one overlay entry point
├── CustomizationCenter.qml             overlay root: opened, open(payloadJson), close(), hosts AppShell
├── core/                               shared QML, nothing module-specific
│   ├── AppShell.qml                    sidebar plus page host plus apply bar; routes payload {page, ...} to a module
│   ├── Sidebar.qml                     navigation list built from ModuleRegistry.modules
│   ├── ModuleRegistry.qml              calls `ccctl modules` once per open, exposes modules[] and loads Page.qml via Loader
│   ├── BackendClient.qml               spawns ccctl (Process, argv array), parses one JSON object, enforces timeouts and concurrency
│   ├── DraftStore.qml                  drafts[moduleId], dirty flags, autosave through `ccctl draft save`, restore on open
│   ├── TransactionModel.qml            history and in-flight transaction state from `ccctl history` and `ccctl transaction`
│   ├── ApplyBar.qml                    Reset, Review, Apply; drives validate, plan, confirm, apply for the active page
│   ├── ChangeList.qml                  renders Plan.operations with summaries, warnings, non-reversible badges
│   ├── ConfirmDialog.qml               named confirmation; the confirm button is disabled until the named item is typed or ticked
│   ├── DiffView.qml                    unified diff of a WriteFileAtomic or ReplaceManagedBlock operation
│   ├── ErrorBanner.qml                 stable error code to message mapping, recovery actions
│   ├── FormField.qml                   labelled control wrapper using Omarchy Style spacing tokens
│   ├── SchemaForm.qml                  renders a normalized barWidget.schema as a form of SchemaFields; used by bar and plugins
│   ├── SchemaField.qml                 one field: boolean, integer, string, path, enum, multiselect, with Omarchy Ui controls
│   ├── SearchField.qml                 shared filter box
│   ├── UndoToast.qml                   post-apply toast with Undo, backed by `ccctl rollback`
│   └── ConfirmationGate.qml            countdown for TimedConfirmation on every screen (Variants over Quickshell.screens), driven by `ccctl transaction current`
├── modules/
│   └── <module-id>/
│       ├── module.json                 id, title, icon, navOrder, page, backend, schemas, coreServices
│       ├── Page.qml                    the page; presentation and interaction only
│       ├── components/                 module-private QML
│       ├── backend/__init__.py         Python package exporting MODULE
│       ├── schemas/                    JSON schemas for this module's drafts, stored files, status, query results
│       └── tests/                      unit and integration tests for this module
├── backend/
│   ├── ccctl                           the only CLI entry point; `#!/usr/bin/python3`, disables bytecode, dispatches commands
│   ├── cc-handoff                      wrapper run inside the terminal for TerminalHandoff; runs "$@", writes the exit sentinel
│   └── customization_center/
│       ├── __init__.py
│       ├── core/
│       │   ├── result.py               Result dataclass, JSON encoder, stable error codes, warnings
│       │   ├── errors.py               CcError(code, message, data) and module-prefixed code validation
│       │   ├── paths.py                XDG and Omarchy path resolution, allowlisted roots, symlink-safe joins
│       │   ├── locking.py              fcntl exclusive lock in $XDG_RUNTIME_DIR, non-blocking, returns `locked`
│       │   ├── atomic.py               write to temp in same dir, fsync, rename, fsync dir; directory swap via rename pair
│       │   ├── backup.py               backup store keyed by transaction id; records mode, absence, sha256
│       │   ├── journal.py              transaction files, state machine, fsync at every boundary, startup recovery scan
│       │   ├── commands.py             subprocess runner: argv only, env allowlist, timeout, output cap, redaction
│       │   ├── shell_ipc.py            `omarchy-shell <target> <method> ...` with per-method success allowlist
│       │   ├── hyprctl.py              `hyprctl` JSON and plain adapters, `reload`, `configerrors` baseline diff
│       │   ├── managed_block.py        find, replace, insert, remove one marked block; collision detection
│       │   ├── jsonc.py                whole-line comment and trailing comma subset parser with duplicate-key detection
│       │   ├── lua.py                  Lua string literal serializer and `luac -p` check
│       │   ├── toml_writer.py          fixed-schema TOML serializer and tomllib reparse
│       │   ├── capabilities.py         Capabilities and Capability dataclasses, probe helpers, cache with TTL
│       │   ├── settings_schema.py      barWidget.schema dialect normalizer, validation, fingerprint, spacerSettings@1 and weatherSettings@1 adapters
│       │   ├── catalog.py              join of listPlugins with omarchy-plugin-catalog and manifest reads; shared by bar and plugins
│       │   ├── registry.py             loads modules/__init__.py list, imports each MODULE, validates module.json
│       │   ├── executor.py             runs a Plan: lock, revision check, backup, operations, verify, commit, rollback
│       │   ├── operations.py           Operation kinds, parameter validation, forward and inverse implementations
│       │   ├── drafts.py               draft persistence and asset ingestion under the drafts directory
│       │   ├── migrate.py              schemaVersion checks and Module.migrate dispatch for stored documents
│       │   └── context.py              Context assembly: paths, capabilities, commands, journal, logger, clock, registry
│       └── modules/__init__.py         `MODULES = ["bar", "plugins", "menu", "defaults", "monitors", "themes", "keybindings", "modes"]`
├── schemas/
│   ├── module-v1.json                  module.json schema
│   ├── result-v1.json                  ccctl output envelope
│   ├── plan-v1.json                    Plan and Operation as returned by `ccctl plan`
│   ├── transaction-v1.json             journal file
│   └── draft-envelope-v1.json          wrapper every module draft sits in
├── tests/
│   ├── conftest.py                     isolated HOME/XDG fixture, command stubs, fake shell IPC, fault injection
│   ├── core/                           tests for every core file
│   ├── contract/                       runs every registered module through the protocol conformance suite
│   └── fixtures/                       shell.json variants, manifests, hyprctl outputs, menu files, theme dirs
└── docs/
    ├── architecture.md
    ├── adding-a-module.md
    ├── managed-files.md
    └── recovery.md                     terminal-only recovery for every managed file and transaction state
```

Two things are deliberate. First, no file under `core/` or `backend/customization_center/core/` names a module. Second, module code lives entirely under `modules/<id>/`, including its backend package, so a module can be reviewed, deleted, or copied as one directory. The Python registry imports `modules/<id>/backend` by path, so the package does not need to live inside `customization_center`.

### Backend module protocol

`modules/<id>/backend/__init__.py` exports `MODULE`. Every method receives a `Context` and reaches the outside world only through it. A module that imports `subprocess`, `os.open`, or `pathlib.Path.write_text` fails the contract test in `tests/contract/`.

```python
from typing import Protocol, Any

class Module(Protocol):
    id: str                        # "bar", "menu", ... equals the directory name
    schema_version: int            # draft schemaVersion this module accepts

    def capabilities(self, ctx: Context) -> Capabilities: ...
    def status(self, ctx: Context) -> Status: ...
    def validate(self, ctx: Context, draft: dict, status: Status) -> ValidationResult: ...
    def plan(self, ctx: Context, draft: dict, status: Status) -> Plan: ...
    def verify(self, ctx: Context, plan: Plan, status_after: Status,
               results: dict[str, OperationResult]) -> VerifyResult: ...

    # optional
    def query(self, ctx: Context, name: str, args: dict) -> dict: ...
    def migrate(self, ctx: Context, kind: str, document: dict, from_version: int) -> dict: ...
```

Method rules:

- `capabilities` runs read-only probes (is the shell reachable, is `luac` installed, does the shell expose `patchPluginEntry`). Every unavailable capability carries a reason string the UI can show.
- `status` reads current effective state and returns a `revision`. The revision is an opaque string; the executor compares it for equality only. A module chooses what goes into it (the bar plan wants a shell-issued token, the menu plan hashes two files, the defaults plan hashes selector output plus XDG state).
- `validate` must not change anything. It receives the latest `status` because some rejections need current facts (the defaults module refuses a target that is not installed). It may run commands that the module's capabilities mark `readonly_check: true`, such as `luac -p` on a temp file or `bash -n` on stdin, because those are the only honest way to syntax-check generated Lua or a menu guard. `commands.py` refuses any argv not on that list while the context is in validate mode.
- `plan` returns operations only. It does not write, does not run the shell, and is deterministic for the same draft and status.
- `verify` is called with a fresh `status()` after the operations ran and with the per-operation results (exit code, truncated stdout and stderr, timed out) keyed by operation id, so a module can check that `omarchy-menu refresh` answered `ok`. It returns pass, fail, or pending. Pass may be `limited` with a reason (the menu module can only confirm a refresh acknowledgement today). Pending means the outcome is not observable yet, which is what a terminal handoff looks like until the user finishes in the terminal.
- `query` serves read-only, module-specific computations a page needs before planning: a theme preview model, a keybinding chord normalization, a catalog search. Same restrictions as `validate`.
- `migrate` upgrades a stored document (`kind` is `draft`, `profile`, `model`, or any name the module's `module.json` lists under `storedDocuments`) from an older `schemaVersion`. Absent `migrate` means older versions are rejected with `schema_version_unsupported`.

`apply` and `rollback` are not module methods. The executor runs them.

### Data types

All types are frozen dataclasses in `core/`, serializable to JSON with the shapes in `schemas/`.

```python
@dataclass(frozen=True)
class Context:
    module_id: str
    paths: Paths                 # home ($HOME, distinct from xdg_config_home because the shell resolves
                                 #   ~/.config/omarchy from HOME), xdg_config_home, state, cache, runtime,
                                 #   omarchy_path, module_config, module_state, drafts, exports;
                                 #   staging_dir(module_id, plan_id) under state/staging/ (0700, removed after
                                 #   commit or rollback and by startup recovery); private_tmpfile(suffix) (0600
                                 #   under $XDG_RUNTIME_DIR/omarchy-customization-center/)
    capabilities: Capabilities   # snapshot taken at the start of this ccctl invocation
    commands: CommandRunner      # run(argv, timeout_s, env_extra=None, stdin=None, capture_limit=...) -> CommandResult;
                                 #   an env_extra value of None unsets the variable
    cache: dict                  # per-process memo for probe results within one ccctl invocation
    shell: ShellIpc              # call(method, *args) -> IpcResult, ping()
    hyprctl: Hyprctl             # json(*args), plain(*args), reload(), configerrors()
    journal: JournalReader       # read-only: history(module), transaction(id)
    registry: RegistryView       # module(id) -> Module, for cross-module planning (modes)
    clock: Clock                 # now() -> datetime, monotonic()
    log: Logger                  # structured, goes to stderr, never to stdout
    mode: str                    # "read", "validate", "plan", "verify"; commands.py enforces per-mode allowlists

@dataclass(frozen=True)
class Capability:
    name: str                    # "shell_ipc", "hyprctl", "luac", "patchPluginEntry", ...
    available: bool
    reason: str                  # empty when available, otherwise why not and what to do
    readonly_check: bool = False # this capability names a command validate/query may run
    argv_prefix: tuple[str, ...] = ()   # required when readonly_check is True

@dataclass(frozen=True)
class Capabilities:
    module_id: str
    items: tuple[Capability, ...]
    probed_at: str               # RFC 3339
    def get(self, name: str) -> Capability: ...
    def require(self, *names: str) -> None: ...   # raises CcError("capability_missing")

@dataclass(frozen=True)
class Status:
    module_id: str
    revision: str
    data: dict                   # module-defined, must validate against modules/<id>/schemas/status-v*.json
    warnings: tuple[Warning, ...]
    schema_version: int

@dataclass(frozen=True)
class Warning:
    code: str                    # module-prefixed unless shared
    message: str
    path: str = ""               # file or JSON pointer the warning concerns
    recovery: str = ""           # what the user can do
    ack: bool = False            # when True on a Plan warning, apply requires --confirm <code>

@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    exit_code: int | None        # None for file operations
    stdout_head: str             # truncated to capture_limit
    stderr_head: str
    timed_out: bool
    duration_ms: int
    written_sha256: str | None   # for file operations, digest after the forward write

@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    pointer: str                 # JSON pointer into the draft, "" for whole-draft issues
    severity: str                # "error" | "warning"

@dataclass(frozen=True)
class ValidationResult:
    ok: bool                     # no issues with severity "error"
    issues: tuple[ValidationIssue, ...]
    normalized_draft: dict | None   # the draft after normalization, what plan() will receive
    details: dict = field(default_factory=dict)   # module-defined extra output (themes contrast matrix, resolved tokens)

@dataclass(frozen=True)
class Operation:
    id: str                      # "<module>.<seq>" unique within a plan, e.g. "menu.0003"
    module_id: str
    kind: str                    # one of the vocabulary below
    params: dict                 # kind-specific, validated by operations.py
    summary: str                 # one human-readable line for the review list
    inverse: "Operation | tuple[Operation, ...] | None"   # tuple runs in listed order; () means nothing to undo; None is non-reversible
    backup_paths: tuple[str, ...]       # files the executor backs up before running this op
    timeout_s: float = 30.0
    detail: dict | None = None   # optional diff or before/after for DiffView
    inverse_after: tuple[str, ...] = ()  # forward operation ids whose inverses must finish before this inverse

@dataclass(frozen=True)
class ResourceClaim:
    key: str                     # "shell.bar", "file:~/.config/hypr/bindings.lua", "theme.current", "default:browser"
    access: str                  # "exclusive" | "shared"

@dataclass(frozen=True)
class Plan:
    module_id: str               # owning module; "modes" for a composed plan
    expected_revision: str       # status().revision the plan was computed against
    operations: tuple[Operation, ...]
    claims: tuple[ResourceClaim, ...]
    summary: str
    warnings: tuple[Warning, ...]
    requires_confirmation: tuple[str, ...]    # confirmation keys: non-reversible operation ids and ack warning codes
    residual_side_effects: tuple[str, ...] = ()      # what rollback will not undo, shown in review and history
    segments: tuple["PlanSegment", ...] = ()  # non-empty only for composed plans
    plan_digest: str = ""        # sha256 of the canonical JSON of everything above; filled by core

@dataclass(frozen=True)
class PlanSegment:
    module_id: str
    expected_revision: str       # that module's own status revision at plan time
    operation_ids: tuple[str, ...]

@dataclass(frozen=True)
class VerifyResult:
    state: str                   # "pass" | "fail" | "pending"
    level: str                   # "full" | "limited"; meaningful for "pass"
    reason: str                  # required unless state is "pass" at level "full"
    code: str = ""               # error code for "fail"
    evidence: dict = field(default_factory=dict)   # module-defined, stored in the journal

@dataclass(frozen=True)
class Transaction:
    id: str                      # UUID4
    module_id: str
    state: str                   # see journal state machine
    created_at: str
    updated_at: str
    plan: Plan
    before_revision: str
    after_revision: str | None
    completed_operation_ids: tuple[str, ...]
    rolled_back_operation_ids: tuple[str, ...]
    backups: dict                # path -> {backup_id, sha256, mode, existed}
    verify: VerifyResult | None
    confirmation: dict | None    # {unit, armedAt, deadline, tokenSha256, status} for TimedConfirmation
    errors: tuple[dict, ...]     # {code, message, operation_id, at}
    rollback_errors: tuple[dict, ...]
```

### Operation vocabulary

Modules build plans from these kinds only. A module that needs another kind lists it under "Required core changes" in its plan; the core team adds it to `operations.py` with tests, and every module gets it.

| Kind | Params | Forward | Inverse | Reversible |
|---|---|---|---|---|
| `WriteFileAtomic` | `path`, `content` (str or base64 bytes), `mode` (octal string or `null` to keep) | temp file in same directory, fsync, rename, fsync directory; records sha256 of written bytes | restores the backup, or removes the file when the backup records absence | yes |
| `ReplaceManagedBlock` | `path`, `begin_marker`, `end_marker`, `body` (str, or `null` to remove the block and its separator) | replaces the bytes between markers; inserts one block at end of file when absent; fails with `unsupported_config` on zero, duplicate, nested, or reversed markers | `ReplaceManagedBlock` with the previous body (or `null` when the block was inserted) | yes |
| `EnsureDirectory` | `path`, `mode` | `mkdir -p` semantics; records whether it created the leaf | removes the leaf only when this operation created it and it is empty | yes |
| `ReplaceDirectoryAtomic` | `path`, `staged_dir` (or `null`), `allow_existing` | `path` renamed to backup, `staged_dir` renamed to `path`, parent fsync after each; creates `path` when absent; `staged_dir: null` removes the directory; a `staged_dir` on another filesystem is first copied into a sibling temporary directory of `path`; refuses symlinks and directories containing `.git` | reverse rename pair; restores the backup after a removal; removes `path` when the forward created it | yes |
| `RunCommand` | `argv`, `timeout_s`, `expect_exit` (default 0), `capture_limit`, `env_extra` (mapping; a `null` value unsets the variable, which the browser selector needs for `BROWSER`), `stdin`, `wait_policy` (`exit` or `detach`) | runs through `commands.py`; stdout and stderr captured and truncated. `detach` waits up to `timeout_s`, then leaves the process running and continues; the agent selector ends in `exec` of a terminal and never exits on its own | an explicit `RunCommand`, a `RestoreBackup`, or `None` | only when an inverse is given |
| `RestoreBackup` | `path` | inverse-only: copies the backup the executor took for `path` at the start of the transaction back into place, or unlinks the file when the backup recorded absence | not applicable | used as an inverse |
| `RemoveFile` | `path` | unlinks a regular file; refuses directories and symlinks | `RestoreBackup(path)` | yes |
| `ShellIpc` | `method`, `args`, `expect` (default `("ok",)`), `expect_json`, `backup_paths` | runs `["omarchy-shell", "shell", method, *args]` with `OMARCHY_SHELL_IPC_TIMEOUT=5s`; object args are serialized as compact JSON. Exit 1 with stderr containing `not running`, `not responding`, or `not ready` maps to `runtime_unavailable`; `Function not found.` and `Target not found.` map to `unsupported_config`; a stdout body outside `expect` is `ipc_rejected` with the body in the message; `expect_json: true` parses the reply | another `ShellIpc` | only when an inverse is given |
| `HyprctlReload` | `config_only` (default false) | refuses with `runtime_unavailable` while `omarchy-hyprland-reload-guard paused` reports paused; runs `hyprctl reload` or `hyprctl reload config-only`; diffs `hyprctl -j configerrors` against the plan-time baseline and fails on new errors | deferred: the rollback walk skips every reload inverse in place and runs one reload after the last file-restoring inverse (`config-only` only if every deferred reload was `config_only`); if any inverse restored a file under `~/.config/hypr/` and no reload was in the walk, one reload runs anyway | yes |
| `TimedConfirmation` | `seconds` | a blocking gate. The executor armed the backstop unit `omarchy-cc-confirm-<txid>` before the first backup; at the gate it runs the pre-confirmation check (`verify` for every completed segment), sets `awaiting_confirmation`, and waits for `ccctl confirm` while holding the lock. Confirmed in time: continue with the operations after the gate. Deadline passes: rollback with reason `timeout` | a fresh `TimedConfirmation(seconds)` in the inverse transaction; see the user rollback rule below | yes |
| `TerminalHandoff` | `argv`, `title`, `wrapped` (default true) | when `wrapped`, launches `omarchy-launch-floating-terminal-with-presentation` with `<absolute path to backend/cc-handoff> <txid> <argv...>` as positional parameters; `cc-handoff` runs the argv with `"$@"` and on exit writes `$XDG_STATE_HOME/omarchy/customization-center/handoffs/<txid>.json` (`{exitCode, finishedAt}`). `wrapped: false` is for commands that open their own terminal, such as the defaults selectors. The launch runs in a new session with null stdio, waits 5 s, and treats exit 0 or still running as launched. Because the launcher re-splits its arguments through `bash -c`, any argv token containing whitespace or one of `;&|<>$\`"'` is rejected at plan validation in both modes. The transaction moves to `pending_handoff` and is finished by `ccctl reconcile` | `None` | no |

Marker format for `ReplaceManagedBlock` is owned by `managed_block.py`, not by modules. A module passes a name and a version and gets `-- BEGIN OMARCHY CUSTOMIZATION CENTER <NAME> v<n>` and the matching `END` line, with the comment prefix chosen per file type (`--` for Lua, `//` for JSONC). Keybindings and monitors both use `v1`; the earlier draft of this plan showed markers without a version, which was the mistake.

Rules the executor enforces on every plan:

- `WriteFileAtomic`, `ReplaceManagedBlock`, `RemoveFile`, and `ReplaceDirectoryAtomic` may target only paths under the allowlisted roots in `paths.py` (`~/.config/omarchy`, including `~/.config/omarchy/shell.json` and `~/.config/omarchy/customization-center/exports/`, `~/.config/hypr`, `~/.local/state/omarchy`, `~/.config/xdg-terminals.list`, and each module's declared extra paths in `module.json`). Symlinked components are refused.
- Every non-reversible operation's id and every warning with `ack: true` appears in `Plan.requires_confirmation`. `ccctl apply` takes `--confirm <key>` once per key and refuses with `nonreversible_requires_confirmation` listing the missing keys otherwise. Keys are bound to the plan digest, so editing a custom command after acknowledging its warning invalidates the acknowledgement. The UI shows one named confirmation per key.
- At most one `TimedConfirmation` per plan. A plan with a gate is refused before any write with `capability_missing` (capability `timed_confirmation`) when `systemd-run --user` is unavailable.
- `TerminalHandoff` must be the last operation.
- User-initiated `ccctl rollback` of a committed transaction that contained a gate builds the inverse transaction in this order: inverses of the operations after the gate (with reload deferral), a fresh `TimedConfirmation(seconds)`, then inverses of the operations before the gate. If that gate times out, the executor re-runs the forward operations that followed the original gate, which restores the confirmed state. A rollback never leaves the user on an unconfirmed layout.
- The rollback for a `WriteFileAtomic` checks that the file's current sha256 equals the sha256 the forward operation wrote. If it differs, someone else edited the file after the apply; the executor records `rollback_conflict` for that operation, leaves the file alone, and continues with the other inverses. The monitor plan asked for this so a countdown rollback never clobbers a concurrent edit of `monitors.lua`. `ReplaceManagedBlock` inverses replace only the block, so they tolerate outside edits by construction.

### Executor algorithm

`ccctl apply <module> --draft <path> --expected-revision <rev>` runs these steps. Every state change is written to the journal with fsync before the next step.

1. Load the module through the registry. Build a `Context` in `read` mode.
2. Run startup recovery. Scan `transactions/` for any transaction in `applying`, `rolling_back`, `awaiting_confirmation` past its deadline, or `pending_handoff` with its sentinel present. Finish each (roll it back, or reconcile the handoff) before accepting new work, or return `recovery_required` when its own rollback already failed. Remove staging directories older than the newest transaction. The same scan runs at the start of every command that takes the lock and at `ccctl modules`, which the overlay calls on every open and which reports `data.recovery`; `ccctl recover` runs it on demand for the recovery docs.
3. Take the lock at `$XDG_RUNTIME_DIR/omarchy-customization-center/apply.lock` with `flock(LOCK_EX | LOCK_NB)`. Return `locked` with the holder's transaction id and module when held. One lock for every module; there is no scenario where two applies running at once is wanted.
4. Load, validate, and normalize the draft (`migrate` if its `schemaVersion` is older, `schema_version_unsupported` if newer). Return `validation_failed` on errors.
5. Call `status()`. If `status.revision != expected_revision`, return `stale_revision` with both revisions. Never retry silently; the UI offers Reload and Compare.
6. Call `plan(draft, status)`. Compute `plan_digest`. If the caller passed `--plan-digest`, require equality; otherwise the reviewed plan is the one the UI already displayed and the digests will match unless state moved, which step 5 caught.
7. Validate the plan: operation kinds and params, path allowlist, claim conflicts (`resource_conflict` when two exclusive claims share a key, which matters for composed plans), confirmation requirements, and `inverseAfter` references. Every inverse dependency names an earlier operation in the same plan, and the dependency graph must be acyclic.
8. Create the transaction file in state `applying` with `before_revision`, the plan, and empty progress, and write its id to `$XDG_RUNTIME_DIR/omarchy-customization-center/current-transaction` (removed at exit). If the plan contains a `TimedConfirmation`, arm the backstop now, before any backup: `systemd-run --user --unit omarchy-cc-confirm-<txid> --on-active=<B>s --timer-property=AccuracySec=1s -- /usr/bin/python3 <absolute ccctl path> rollback <txid> --reason timeout`, where `B` is the sum of `timeout_s` of every operation before the gate plus `seconds` plus 5. Record `confirmation: {unit, armedAt, status: "armed"}`. The absolute `ccctl` path is the one `ccctl` recorded for itself at startup, because the overlay that spawned this apply may be gone when the timer fires.
9. Back up every path in every operation's `backup_paths` plus every file a `WriteFileAtomic` or `ReplaceManagedBlock` targets. Record mode, sha256, and absence. A backup failure aborts before any write.
10. Run operations in order. After each, append its id to `completed_operation_ids` and fsync. A failure records `{code, message, operation_id}` and jumps to step 14. At a `TimedConfirmation`: run the pre-confirmation check, which is `verify` for every segment whose operations have all completed (for a single-module plan, the module's own `verify` with the partial `results` dict; operations not yet run are absent from it); `fail` jumps to step 14 without waiting. Then set `awaiting_confirmation` with `confirmation.deadline = now + seconds` and the sha256 of a random token, fsync, keep the lock, and poll every 200 ms for the token file `$XDG_RUNTIME_DIR/omarchy-customization-center/confirm/<txid>`. Token present before the deadline with a matching digest: `systemctl --user stop omarchy-cc-confirm-<txid>.timer`, delete the token file, state back to `applying`, continue with the operations after the gate. Deadline passes: state `rolling_back`, reason `timeout`, step 14; the backstop finds the record terminal when it fires and exits 0.
11. If the plan contains a `TerminalHandoff`, the transaction moves to `pending_handoff` after it launches, the lock is released, and the command returns `ok: true` with `data.pending: true`. The handoff finishes later through `ccctl reconcile`, which takes the lock and reads the sentinel `cc-handoff` wrote: exit 0 (or no sentinel for an unwrapped handoff) means run `status()` and `verify()` and move to `committed` on pass, `rolling_back` on fail, or stay pending; a non-zero exit means `rolling_back` with reason `handoff_failed` and nothing to invert; a missing sentinel for a wrapped handoff means still pending. `ccctl status <module>` lists the module's pending handoff transactions so a page can resume them on focus.
12. Call `status()` again and `verify(plan, status_after, results)` for every segment. `fail` jumps to step 14. `pending` outside a handoff is treated as `fail`. `level: "limited"` is recorded and returned as a warning, not a failure.
13. Mark `committed`, record `after_revision`, stop the backstop unit if it is still armed, remove `current-transaction`, release the lock, return. The token for a gate is returned to the caller once in `data.confirmation` together with the deadline and unit name, and is never stored in clear; `ccctl apply` itself stays blocked through the gate, so the UI reads `ccctl transaction current` to drive the countdown.
14. Rollback. State becomes `rolling_back`. Order completed operations by their validated inverse dependencies, using reverse completion order as the stable tie-breaker, then run each inverse; a tuple inverse runs in its listed order. Dependencies that name operations which did not complete are ignored for that rollback. An operation with `inverse: None` is skipped and recorded as `skipped_nonreversible`. A `WriteFileAtomic` whose file sha256 differs from `written_sha256` is skipped as `rollback_conflict`. `HyprctlReload` inverses are skipped in place and one reload runs after the last file-restoring inverse, `config-only` only if every deferred reload was `config_only`; if any inverse restored a file under `~/.config/hypr/` and no reload inverse was in the walk, one reload runs anyway. Each inverse failure is recorded in `rollback_errors` and the walk continues; stopping at the first failure would leave more damage, not less. Committed user undo uses the same ordering helper.
15. If `rollback_errors` is empty, run `status()` and compare against `before_revision`. Equal means state `rolled_back`; the result carries the original error. Not equal means the inverses ran but something outside the plan also changed; state `rolled_back` with a warning `revision_drift_after_rollback`.
16. If `rollback_errors` is not empty, state `rollback_failed`. The result is `ok: false`, code `rollback_failed`, and `data` lists every backup path, the operations that could not be reversed, and the terminal recovery command for each (`ccctl restore <txid> --path <p>` copies a backup back into place without any other side effect). The UI shows this as a pinned red panel that survives navigation and reopening until the user resolves it, and `ccctl apply` for any module returns `recovery_required` until then.

What happens when rollback itself fails is the part most designs leave vague, so to be explicit: the plugin stops writing. It does not try a second automatic rollback, it does not delete backups, and it does not let another module apply. The user gets a list of files, a list of backups, and one command per file. `docs/recovery.md` is tested against every `rollback_failed` fixture.

### Registry and module.json

Discovery is explicit. `backend/customization_center/modules/__init__.py` holds one list:

```python
MODULES = ["bar", "plugins", "menu", "defaults", "monitors", "themes", "keybindings", "modes"]
```

`registry.py` iterates that list, reads `modules/<id>/module.json`, validates it against `schemas/module-v1.json`, imports `modules/<id>/backend/__init__.py` by file path under the package name `cc_modules.<id>`, and checks that `MODULE.id == id`. No directory scanning, no import side effects, and a broken module produces one `registry` warning naming the module rather than a crash; the other modules still load.

`module.json` schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schemaVersion", "id", "title", "icon", "navOrder", "page", "backend", "draftSchema", "coreServices"],
  "additionalProperties": false,
  "properties": {
    "schemaVersion": {"const": 1},
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
    "title": {"type": "string", "minLength": 1, "maxLength": 40},
    "description": {"type": "string", "maxLength": 200},
    "icon": {"type": "string", "description": "one Nerd Font glyph"},
    "navOrder": {"type": "integer", "minimum": 0},
    "page": {"type": "string", "pattern": "^[A-Za-z0-9_./-]+\\.qml$", "description": "relative to the module directory, no .."},
    "backend": {"type": "string", "const": "backend", "description": "package directory relative to the module directory"},
    "draftSchema": {"type": "string", "description": "relative path to the draft JSON schema"},
    "statusSchema": {"type": "string"},
    "storedDocuments": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["kind", "schema", "location"],
        "properties": {
          "kind": {"type": "string"},
          "schema": {"type": "string"},
          "location": {"type": "string", "description": "path template under module_config or module_state"}
        }
      }
    },
    "extraWritablePaths": {"type": "array", "items": {"type": "string"}, "description": "absolute path templates the executor may write for this module beyond the shared roots"},
    "coreServices": {
      "type": "array",
      "items": {"enum": ["shell_ipc", "hyprctl", "managed_block", "jsonc", "lua", "toml_writer", "drafts", "registry", "timed_confirmation", "terminal_handoff", "settings_schema", "catalog", "staging"]},
      "uniqueItems": true
    },
    "queries": {"type": "array", "items": {"type": "string"}, "description": "names accepted by Module.query"},
    "hidden": {"type": "boolean", "default": false}
  }
}
```

`coreServices` is a declaration, not a capability grant. The contract test reads the module's Python imports and fails when a module imports a core service it did not declare, and it fails when the module imports anything outside `customization_center.core`. The point is that a reviewer can read `module.json` and know the module's blast radius. There is no `dependsOn`; a module never imports another module. Anything two modules both need (the widget settings schema dialect, the plugin catalog join) lives in core, and the only cross-module dependency is `modes` through `ctx.registry`. `managed_block.inspect(bytes, name, version)` returns `{state, beginLine, endLine, problems}` with states `absent`, `present`, `duplicate`, `unterminated`, `reversed`, `nested` so a module's `status` can report marker trouble without attempting a write; `jsonc.parse(bytes)` returns `(value, diagnostics)` with ordered pairs, duplicate-key reports with JSON paths, and a line map.

Example for the bar module:

```json
{
  "schemaVersion": 1,
  "id": "bar",
  "title": "Bar",
  "description": "Widget layout, position, and transparency of the shell bar",
  "icon": "󰍜",
  "navOrder": 10,
  "page": "Page.qml",
  "backend": "backend",
  "draftSchema": "schemas/draft-v1.json",
  "statusSchema": "schemas/status-v1.json",
  "coreServices": ["shell_ipc", "catalog", "settings_schema", "drafts"],
  "queries": ["catalog"]
}
```

How QML uses it: `ModuleRegistry.qml` runs `ccctl modules` once when the overlay opens. The result lists every module with its `module.json` contents, its absolute page URL (`file://<plugin dir>/modules/<id>/Page.qml`), and its capabilities. `Sidebar.qml` sorts by `navOrder`, hides `hidden` modules, and shows `title` and `icon`. `AppShell.qml` sets a `Loader.source` to the page URL of the selected module. Nothing in QML knows the list of modules.

### QML page contract

`modules/<id>/Page.qml` is loaded by `ModuleRegistry` through a `Loader`. It is an `Item` that exposes:

```qml
Item {
    property string moduleId
    property var status          // set by AppShell after `ccctl status <id>`; null while loading
    property var capabilities    // set from `ccctl modules`
    property var draft           // DraftStore.drafts[moduleId]; read-only from the page's side
    property bool busy           // true while any ccctl call for this module is in flight; disable inputs

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal draftChanged(var patch)   // page emits a JSON-merge patch; DraftStore applies it and updates `draft`
    signal requestNavigate(string moduleId, var payload)   // deep link; ModuleRegistry switches page and calls handlePayload there

    function focusFirst() { }        // keyboard entry point, called when the page becomes active
    function handlePayload(payload) { }   // optional, and the only name for it: payload from summon or requestNavigate, e.g. {"modeId": "presentation"}
}
```

Boundaries:

- The page never spawns a process, never reads or writes a file, never touches `shell` or `pluginRegistry` from the injected host properties for mutation. It may read `pluginRegistry.registryRevision` to show "catalog changed" hints.
- The page edits state by emitting `draftChanged(patch)`. `DraftStore` merges the patch, marks the module dirty, debounces an autosave through `ccctl draft save`, and reassigns `draft`. Pages that assign to `draft` directly break the binding and lose autosave; the contract test loads each page in a headless `qmltestrunner` and checks that no assignment to `draft` exists.
- Read-only module queries go through `BackendClient.query(moduleId, name, args, callback)`. This is the one backend call a page may make itself, because a preview or a chord normalization is a page concern. Validate, plan, apply, rollback, and confirm are driven by `ApplyBar` only.
- Module-private components live under `modules/<id>/components/` and import `../../core` for shared controls and `qs.Ui` and `qs.Commons` for Omarchy's.
- `CustomizationCenter.open(payloadJson)` routes `{"module": "<id>", ...}` to that page through the same `handlePayload` path that `requestNavigate` uses.

`ApplyBar` sequence for the active module: `requestPlan` triggers `ccctl validate` then `ccctl plan`; `ChangeList` shows the plan; Apply triggers `ConfirmDialog` when `requires_confirmation` is non-empty, then `ccctl apply --expected-revision <status.revision> --plan-digest <d>`. While that process runs, `BackendClient.pollTransaction` watches `ccctl transaction current`; when its state is `awaiting_confirmation`, `ConfirmationGate` appears on every screen and calls `BackendClient.confirm(txid, token)` or `BackendClient.rollback(txid, "user")`. On success `ApplyBar` refreshes `status`, clears the draft, and shows `UndoToast`.

### BackendClient

Spawning uses the same Quickshell pattern the shell uses for its own scans (`PluginRegistry.qml:618-627`):

```qml
Process {
    id: proc
    command: [ccctlPath, "status", "bar"]          // argv array, never a shell string
    environment: ({ "OMARCHY_PATH": omarchyPath, "CC_CALLER": "overlay" })
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
    onExited: function(code) { client._finish(request, code, stdout.text, stderr.text) }
}
```

- `ccctlPath` is `manifest.__sourceDir + "/backend/ccctl"`. The overlay refuses to start if the file is missing or not executable and shows the path.
- Draft JSON goes to `ccctl` on stdin (`--draft -`), never as an argument. Argument length limits and shell quoting are not problems the plugin wants.
- The result is the last line of stdout that parses as a JSON object. Everything before it is logged and ignored, because a stray `print` in a module must not break the UI; everything after it is a `malformed_output` error. Stdout is capped at 8 MiB; exceeding it kills the process and returns `malformed_output`.
- Timeouts by command: `modules`, `capabilities`, `status`, `history`, `transaction` 10 s; `validate`, `plan`, `query` 30 s; `apply` and `rollback` use the plan's own budget, the sum of `Operation.timeout_s` plus the gate's `seconds` when the plan has one, plus 15 s, with a ceiling of 15 minutes; `confirm` 10 s. Expiry kills the process with SIGTERM, then SIGKILL after 2 s, and the UI shows `timeout`. A killed `apply` leaves a transaction in `applying`, which the next `ccctl` invocation's startup recovery rolls back.
- Concurrency: reads (`status`, `validate`, `plan`, `query`, `history`, `transaction`) run at most one at a time per module; a second read for the same module replaces the queued one, so a fast typist never queues twenty validations. Mutations (`apply`, `rollback`, `reconcile`, `abandon`, `draft save`) run one at a time globally, in a FIFO queue. The backend lock would serialize them anyway, but a queued apply that returns `locked` is a worse experience than one that waits behind a progress indicator. `confirm` bypasses the queue because it must run while an `apply` is blocked at a gate; it takes no lock and only writes the token file. Reads and one mutation may overlap; the UI marks the mutating module `busy` and other pages stay browsable.
- Polling: `pollTransaction(txid, intervalMs)` repeats `ccctl transaction <txid>` (or `ccctl transaction current` when `txid` is `"current"`), and `pollStatus(moduleId, intervalMs)` repeats `ccctl status <moduleId>`; both stop through `stopPolling(handle)` and stop on their own when the overlay closes.
- `ccctl` writes structured logs to stderr. `BackendClient` keeps the last 200 lines per module in memory for a debug panel and never persists them.

`DraftStore` calls `ccctl draft load <module>` when a page is first shown and `ccctl draft save <module> --draft -` on a 750 ms debounce after `draftChanged`, and again on `close()`. Drafts live under `~/.config/omarchy/customization-center/drafts/<module>/current.json`. Because the overlay is destroyed on close (no `keepLoaded`), this is the only reason a half-edited layout survives pressing Escape. `DraftStore` also keeps an in-memory undo and redo stack of patches per module (depth 100) and binds Ctrl+Z and Ctrl+Shift+Z while a page is active, so no page has to implement its own history.

`TransactionModel` reads `ccctl history --limit 50` on open, `ccctl transaction current` while an apply is running, and `ccctl transaction <id>` for a transaction that is `pending_handoff` or `rollback_failed`. It exposes the pinned recovery state to `AppShell`, which blocks Apply on every page while any transaction is `rollback_failed`.

### ccctl CLI reference

Every command prints exactly one JSON object on the last line of stdout and exits 0 for `ok: true`, 1 for `ok: false`, 2 for usage errors (which still print the envelope). Drafts and other documents are passed with `--draft <path>` or `--draft -` for stdin.

```text
ccctl modules
    Registry listing: every module's module.json, page URL, capabilities, schema versions.
ccctl capabilities [<module>]
    Capability probes for one module or all.
ccctl status <module>
    Current effective state and revision.
ccctl validate <module> --draft <path|->
    ValidationResult. No writes.
ccctl plan <module> --draft <path|->
    Plan with plan_digest. No writes.
ccctl query <module> <name> [--args <json|->]
    Read-only module query. No writes.
ccctl apply <module> --draft <path|-> --expected-revision <rev> [--plan-digest <sha256>]
      [--confirm <key>]...
    Runs the executor and blocks until the transaction is committed, pending_handoff, rolled back,
    or rollback_failed; a gate keeps it blocked while waiting. Returns transactionId; data.state;
    data.confirmation with the token, deadline, and unit name when the plan had a gate.
ccctl confirm <transaction-id> --token <token>
    Lock-free. Refuses with confirmation_expired unless the journal state is awaiting_confirmation,
    with confirmation_invalid on a bad token. Otherwise writes the 0600 token file and returns;
    the blocked apply picks it up within 200 ms.
ccctl rollback <transaction-id> [--reason user|timeout|recovery]
    With --reason timeout (the backstop): tries the lock for up to 10 s; if the live executor holds
    it, leaves; with the lock, runs the rollback walk when the state is awaiting_confirmation or
    applying (dead executor), exits 0 when the state is terminal. With --reason user: reverses a
    committed or pending_handoff transaction as a new inverse transaction; refuses when the module's
    current revision differs from the transaction's after_revision unless --force-stale is given,
    in which case the UI has already shown the reverse diff.
ccctl transaction <transaction-id>
    Transaction record from the journal. Read-only, lock-free.
ccctl transaction current
    The record named by $XDG_RUNTIME_DIR/omarchy-customization-center/current-transaction, which
    the executor writes at start and removes at exit. Read-only, lock-free; drives the countdown.
ccctl reconcile <transaction-id>
    For pending_handoff: takes the lock and reads the handoff sentinel. Sentinel with exit 0, or
    no sentinel for an unwrapped handoff: re-run status and verify, commit on pass, roll back on
    fail, stay pending on pending. Sentinel with non-zero exit: rolling_back with reason
    handoff_failed (nothing to invert). Sentinel absent for a wrapped handoff: still pending.
ccctl recover
    Runs the startup recovery scan explicitly and reports what it finished or could not finish.
ccctl abandon <transaction-id>
    Rolls a pending_handoff transaction back with reason user. Completed reversible operations run
    their inverses; the non-reversible handoff is skipped and may continue outside the plugin.
ccctl restore <transaction-id> --path <path>
    Copies one backup back into place. Only for rollback_failed recovery. No other side effects.
ccctl history [--module <module>] [--limit N] [--state <state>]
    Transaction summaries, newest first.
ccctl draft load <module>
ccctl draft save <module> --draft <path|->
ccctl draft discard <module>
ccctl draft asset-add <module> --path <file>
    Draft persistence. asset-add copies a regular file (no symlink, size limit 64 MiB, image or
    text types only) into the draft's assets directory and returns its sha256 name.
ccctl migrate <module> --kind <kind> --document <path|->
    Runs Module.migrate and prints the upgraded document. Used by tests and by recovery docs.
ccctl doctor
    Read-only self-check: Python version, paths, lock directory, pending transactions,
    bytecode setting, plugin directory writes. Prints the same envelope.
```

There are no module-specific flags on `ccctl status`. A module that needs a different read exposes it as `ccctl query <module> <name>`.

Result envelope (`schemas/result-v1.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schemaVersion", "ok", "command", "module", "revision", "data", "warnings", "errors", "transactionId", "durationMs"],
  "properties": {
    "schemaVersion": {"const": 1},
    "ok": {"type": "boolean"},
    "command": {"type": "string"},
    "module": {"type": ["string", "null"]},
    "revision": {"type": ["string", "null"], "description": "module revision after the command, when a module is involved"},
    "data": {"type": ["object", "null"]},
    "warnings": {"type": "array", "items": {"$ref": "#/$defs/warning"}},
    "errors": {"type": "array", "items": {"$ref": "#/$defs/error"}},
    "transactionId": {"type": ["string", "null"]},
    "durationMs": {"type": "integer"}
  },
  "$defs": {
    "warning": {
      "type": "object",
      "required": ["code", "message"],
      "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "path": {"type": "string"}, "recovery": {"type": "string"}}
    },
    "error": {
      "type": "object",
      "required": ["code", "message"],
      "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "pointer": {"type": "string"}, "operationId": {"type": "string"}, "data": {"type": "object"}}
    }
  }
}
```

Stable shared error codes. The first error in `errors[]` is the primary one and `ok` is false whenever the array is non-empty.

| Code | Meaning | UI response |
|---|---|---|
| `stale_revision` | `expected_revision` differs from current | Reload, Compare |
| `validation_failed` | draft has issues with severity `error` | show issues by pointer |
| `invalid_draft` | draft is not a JSON object or fails the envelope schema | show raw error |
| `schema_version_unsupported` | document version newer than the module supports and no migration | show version, link docs |
| `runtime_unavailable` | shell, Hyprland, or a required command is not reachable | Retry, Start shell |
| `capability_missing` | a capability the plan needs is unavailable | show reason from capability |
| `permission_required` | a target path is not writable | show path |
| `unsupported_config` | existing file content the module refuses to manage (marker collision, unknown Lua) | read-only mode, link docs |
| `resource_conflict` | two exclusive claims on one key in a composed plan | show both operations |
| `nonreversible_requires_confirmation` | plan has confirmation keys that were not passed with `--confirm`; `data.missingKeys` lists them | ConfirmDialog per key |
| `locked` | another apply holds the lock | show holder, Retry |
| `timeout` | a command exceeded its budget | show command, Retry |
| `malformed_output` | a command or IPC reply could not be parsed | show truncated output |
| `ipc_rejected` | the shell answered with a body outside the operation's `expect` list; the message carries the body | show body, Retry |
| `handoff_failed` | the wrapped terminal command exited non-zero; transaction rolled back | show exit code, Retry |
| `verification_failed` | verify returned `fail`; rollback ran | show reason and rollback result |
| `rollback_failed` | at least one inverse failed | pinned recovery panel |
| `recovery_required` | a prior transaction is `rollback_failed` | pinned recovery panel |
| `transaction_not_found` | unknown id | refresh history |
| `transaction_state_invalid` | command not valid for the transaction's state | refresh |
| `confirmation_invalid` | wrong token | none |
| `confirmation_expired` | deadline passed, rollback ran or is running | show rollback result |
| `unknown_module` | id not in registry | none |
| `unknown_query` | query name not in `module.json` `queries` | none |
| `internal_error` | unhandled exception; traceback in stderr only | show id, link logs |

Modules add codes prefixed with their id and an underscore (`monitors_overlap`, `menu_unparseable`, `keybindings_managed_block_drift`). `result.py` rejects any other prefix at serialization time so a typo cannot ship.

### State directories

```text
~/.config/omarchy/customization-center/
├── settings.json                      plugin settings (schemaVersion, gate seconds, history retention)
├── drafts/<module>/current.json       autosaved draft envelope
├── drafts/<module>/assets/<sha256>.<ext>
├── exports/                           mode bundles and other user-facing exports; an allowed write root
├── <module>/                          module_config: stored documents (monitor-profiles/, desktop-modes/, keybindings.json)
└── generated/                         files loaded by Omarchy or Hyprland (monitors.lua)

~/.local/state/omarchy/customization-center/
├── transactions/<id>.json             journal, one file per transaction
├── backups/<transaction-id>/<n>       backup bodies, plus manifest.json mapping n to path, sha256, mode, existed
├── staging/<module>/<plan-id>/        0700 staging for ReplaceDirectoryAtomic; removed after commit or rollback and by recovery
├── handoffs/<transaction-id>.json     sentinel written by cc-handoff: {exitCode, finishedAt}
├── <module>/                          module_state: last-applied records (modes/last-applied.json, monitors/active.json), ownership sidecars
└── log/ccctl.log                      rotated at 2 MiB, two generations, no draft contents, no environment

~/.cache/omarchy/customization-center/
└── capabilities.json                  probe cache, 60 s TTL, safe to delete

$XDG_RUNTIME_DIR/omarchy-customization-center/
├── apply.lock
├── current-transaction                id of the running transaction; written at start, removed at exit
├── confirm/<transaction-id>           0600 token file written by `ccctl confirm`, consumed by the blocked apply
└── tmp/                               private_tmpfile() scratch, 0600
```

Generated Omarchy-native artifacts stay in their documented places and are the only files outside these trees the plugin writes: `~/.config/omarchy/shell.json` (bar module only, through its file route, followed by `ShellIpc("reloadConfig")`, never while the shell is down or the file does not parse), `~/.config/omarchy/extensions/omarchy-menu.jsonc`, `~/.config/omarchy/themes/<slug>/`, `~/.config/hypr/monitors.lua` (one block), `~/.config/hypr/bindings.lua` (one block), `~/.config/xdg-terminals.list` and `~/.local/state/omarchy/defaults/editor` and `~/.config/omarchy/defaults/agent` (rollback restores only, through the defaults module's `extraWritablePaths`).

Draft envelope (`schemas/draft-envelope-v1.json`):

```json
{
  "type": "object",
  "required": ["schemaVersion", "module", "baseRevision", "updatedAt", "draft"],
  "properties": {
    "schemaVersion": {"const": 1},
    "module": {"type": "string"},
    "baseRevision": {"type": "string", "description": "status revision the draft was started from"},
    "updatedAt": {"type": "string", "format": "date-time"},
    "draft": {"type": "object", "description": "validated against the module's draftSchema; carries its own schemaVersion"}
  }
}
```

Transaction journal (`schemas/transaction-v1.json`), abbreviated to the top level; `plan` uses `plan-v1.json`:

```json
{
  "type": "object",
  "required": ["schemaVersion", "id", "module", "state", "createdAt", "updatedAt", "plan", "beforeRevision", "completedOperationIds", "rolledBackOperationIds", "backups", "errors", "rollbackErrors"],
  "properties": {
    "schemaVersion": {"const": 1},
    "id": {"type": "string", "format": "uuid"},
    "module": {"type": "string"},
    "state": {"enum": ["applying", "awaiting_confirmation", "pending_handoff", "committed", "rolling_back", "rolled_back", "rollback_failed"]},
    "reason": {"enum": ["user", "timeout", "recovery", "verification", "operation", "handoff_failed"], "description": "why the transaction left applying, awaiting_confirmation, or pending_handoff"},
    "createdAt": {"type": "string", "format": "date-time"},
    "updatedAt": {"type": "string", "format": "date-time"},
    "plan": {"$ref": "plan-v1.json"},
    "beforeRevision": {"type": "string"},
    "afterRevision": {"type": ["string", "null"]},
    "completedOperationIds": {"type": "array", "items": {"type": "string"}},
    "rolledBackOperationIds": {"type": "array", "items": {"type": "string"}},
    "skippedInverseIds": {"type": "array", "items": {"type": "object", "properties": {"operationId": {"type": "string"}, "why": {"enum": ["nonreversible", "rollback_conflict"]}}}},
    "backups": {"type": "object", "additionalProperties": {"type": "object", "required": ["backupId", "existed"], "properties": {"backupId": {"type": "string"}, "sha256": {"type": ["string", "null"]}, "mode": {"type": ["string", "null"]}, "existed": {"type": "boolean"}}}},
    "verify": {"type": ["object", "null"]},
    "residualSideEffects": {"type": "array", "items": {"type": "string"}},
    "confirmation": {"type": ["object", "null"], "properties": {"unit": {"type": "string"}, "armedAt": {"type": "string"}, "deadline": {"type": ["string", "null"]}, "tokenSha256": {"type": ["string", "null"]}, "status": {"enum": ["armed", "confirmed", "expired", "cancelled"]}}},
    "commandLog": {"type": "array", "items": {"type": "object", "required": ["operationId", "argv", "exit", "durationMs"], "properties": {"stdoutHead": {"type": "string", "maxLength": 4096}, "stderrHead": {"type": "string", "maxLength": 4096}}}},
    "errors": {"type": "array"},
    "rollbackErrors": {"type": "array"}
  }
}
```

State machine: `applying` goes to `committed`, `awaiting_confirmation`, `pending_handoff`, or `rolling_back`. `awaiting_confirmation` goes back to `applying` (token accepted, operations after the gate continue) or to `rolling_back` (timeout, user revert, or recovery). `pending_handoff` goes to `committed` (`reconcile` passes) or to `rolling_back`. Verification failure uses reason `verification`; launcher or sentinel failure uses `handoff_failed`; `abandon` uses `user`. The rollback walk reverses completed reversible operations and skips the non-reversible handoff. `rolling_back` goes to `rolled_back` or `rollback_failed`. A `committed` record never changes state; user undo through `ccctl rollback --reason user` creates a new transaction whose plan is the inverse list (with the gate rule above when the original had one), so the original record stays intact. `rollback_failed` is terminal for the record; a later successful `ccctl restore` appends to `rollbackErrors` with `resolved: true` and clears the global block once every entry is resolved.

The journal never records environment variables, full stdout, or draft contents. `commandLog` keeps the first 4 KiB of each stream after `commands.py` redaction (patterns for `token`, `password`, `secret`, `Bearer`, and URL userinfo).

### Composed plans (desktop modes)

The `modes` module is the one module whose `plan` calls other modules. Through `ctx.registry.module("monitors").plan(ctx_for("monitors"), sub_draft, sub_status)` it obtains each owner's `Plan`, concatenates the operations in member order, unions the claims, and returns a `Plan` with `module_id: "modes"` and one `PlanSegment` per member recording that member's `expected_revision` and operation ids. Member order is monitors, themes, plugins, bar, menu, keybindings, defaults. Monitors go first because of the gate. Themes go before plugins and bar because `omarchy-theme-set` reloads Hyprland and restarts shell parts; nothing after it may assume the overlay survived, and by then the gate has already been confirmed. The last operation of a composed plan is a `WriteFileAtomic` on `{module_state}/modes/last-applied.json`, so the last-applied record lands in the same transaction. The executor treats a composed plan like any other with three additions: at step 5 it re-checks every segment's revision against that module's `status()`, at step 7 it rejects duplicate exclusive claims, and it verifies per segment, completed segments at the gate and all segments at the end. Rollback is the same reverse walk. There is no parent and child transaction; there is one transaction with segments. That is simpler to recover, and it means `ccctl rollback` on a mode is not special.

### Versioning and migration

Three independent version numbers:

- `schemaVersion` on the envelope types (`result`, `plan`, `transaction`, `module.json`, draft envelope). Bumped only by core, rarely. `ccctl` refuses to read a transaction with a newer envelope version and says so; an older one is read through a core migration table.
- `schemaVersion` inside each module's draft and stored documents. Bumped by the module. `Module.schema_version` is the current draft version. On load, `migrate.py` compares and calls `Module.migrate(ctx, kind, document, from_version)` step by step until current, then validates against the current schema. The migrated document is written back only during `draft save` or an apply that stores it; a read never rewrites a stored file.
- The plugin `version` in `manifest.json`, which the journal records per transaction so recovery docs can say which version wrote what.

Migration example: the keybindings module changes its managed model from `unbindFirst` booleans (v1) to a separate `disabled[]` array (v2). `migrate(ctx, "model", doc, 1)` returns the v2 shape; `schema_version` becomes 2; `schemas/model-v1.json` stays in the repository so old fixtures still validate; `tests/` gains one round-trip test per migration step. A module without `migrate` that bumps its version fails the contract test, which checks that every version from 1 to current has a migration path.

Compatibility with Omarchy is tracked separately through capabilities, not versions. A module probes for the specific IPC method or command flag it needs (`patchPluginEntry` present in the `omarchy-shell shell` reply, `omarchy-theme-set --json` accepted) and disables the affected action with the capability's reason. Version strings drift; probes do not.

### Testing infrastructure core provides

`tests/conftest.py` gives every module test the same four things.

1. Isolated home. A fixture creates a temporary directory and sets `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, `XDG_RUNTIME_DIR`, and `OMARCHY_PATH` (pointing at a fixture tree with `config/omarchy/shell.json`, `default/omarchy/omarchy-menu.jsonc`, `default/themed/*.tpl`, `default/hypr/bindings/*.lua`, and `shell/plugins/*/manifest.json` copied from the pinned Omarchy checkout). A guard fails the test if any file outside the temporary tree changed, using a before and after walk of `$HOME` on the real machine restricted to the plugin's allowlisted roots.
2. Command stubs. `stub_command(name, handler)` places an executable on a private `PATH` that records argv, stdin, and env to a JSON log and returns whatever the handler says: exit code, stdout, stderr, delay, or a hang past the timeout. Assertions read the log: `assert stubs.calls("omarchy-theme-set") == [["omarchy-theme-set", "ocean"]]`. Stubs exist for every command in the "Adapter contract tests" list below, with recorded real outputs as default fixtures.
3. Fake shell IPC. `fake_shell` is a stub `omarchy-shell` backed by an in-memory `shell.json` document and the registry semantics that matter (`listPlugins` shape, `listShellConfig`, `enablePlugin`, `putBarWidget`, `moveBarWidget`, `setBarWidget`, `setPluginEnabled`, `ping`, plus the proposed `getBarState` and `applyBarConfig` behind a flag). It reproduces the exit-0-with-error-body behavior so adapters are tested against the real failure mode. It can be told to be down, not ready, or slow.
4. Fault injection. The executor takes an optional `FaultPlan` from the context, only when `CC_TEST_FAULTS` names a file inside the isolated home. Hooks: `before_backup`, `after_backup`, `before_op:<id>`, `after_op:<id>`, `before_verify`, `verification_mismatch`, `before_journal_fsync:<state>`, `before_inverse:<id>`, `after_inverse:<id>`, `gate_timeout`, `gate_confirm_replay`, `handoff_exit:<code>`, `kill_process_at:<hook>` (raises `SystemExit` to simulate a crash). The production `ccctl` ignores the variable unless the file lives under the isolated home, so a stray environment variable on a real desktop cannot arm it. `tests/contract/test_executor_faults.py` runs every registered module's sample plan through every hook and asserts the transaction ends `rolled_back` with the original files byte-identical, or `rollback_failed` with a recovery command per file.

The contract suite in `tests/contract/` runs for every id in `MODULES` without module-specific code: `module.json` validates; `MODULE.id` matches; `capabilities`, `status`, `validate`, `plan` run against the module's `tests/fixtures/sample-draft.json` without writing; every operation kind and path is allowed; every non-reversible operation is in `requires_confirmation`; the module imports only declared core services; each stored document kind has a schema per version and a migration chain; `Page.qml` loads in `qmltestrunner` with the required properties and signals present.

### Adding a module

The acceptance test for this design. Suppose a ninth module, `wallpapers`, rotates the wallpaper on a timer from a chosen directory, using `omarchy-theme-bg-set <path>` to change the image and a user systemd timer to rotate.

1. Create `modules/wallpapers/module.json`:

```json
{
  "schemaVersion": 1,
  "id": "wallpapers",
  "title": "Wallpapers",
  "description": "Rotate wallpapers from a folder on a timer",
  "icon": "󰸉",
  "navOrder": 65,
  "page": "Page.qml",
  "backend": "backend",
  "draftSchema": "schemas/draft-v1.json",
  "statusSchema": "schemas/status-v1.json",
  "storedDocuments": [
    {"kind": "rotation", "schema": "schemas/rotation-v1.json", "location": "{module_config}/rotation.json"}
  ],
  "extraWritablePaths": ["{home}/.config/systemd/user/omarchy-cc-wallpapers.timer", "{home}/.config/systemd/user/omarchy-cc-wallpapers.service"],
  "coreServices": ["drafts"],
  "queries": ["list_images"]
}
```

2. Write `modules/wallpapers/backend/__init__.py`:

```python
from customization_center.core import (Module, Capabilities, Capability, Status, ValidationResult,
    ValidationIssue, Plan, Operation, ResourceClaim, VerifyResult, ops)

class Wallpapers:
    id = "wallpapers"
    schema_version = 1

    def capabilities(self, ctx):
        bg = ctx.commands.which("omarchy-theme-bg-set")
        systemd = ctx.commands.which("systemctl")
        return Capabilities(self.id, (
            Capability("theme_bg_set", bg is not None, "" if bg else "omarchy-theme-bg-set not on PATH"),
            Capability("user_systemd", systemd is not None, "" if systemd else "systemctl not on PATH"),
        ), ctx.clock.now_iso())

    def status(self, ctx):
        stored = ctx.paths.read_json(ctx.paths.module_config / "rotation.json", default=None)
        current = ctx.paths.readlink(ctx.paths.state / "omarchy/current/background")
        timer = ctx.commands.run(["systemctl", "--user", "is-active", "omarchy-cc-wallpapers.timer"], timeout_s=5)
        data = {"rotation": stored, "currentBackground": current, "timerActive": timer.stdout.strip() == "active"}
        return Status(self.id, ctx.revision_of(data), data, (), 1)

    def validate(self, ctx, draft, status):
        issues = []
        d = ctx.paths.resolve_user_path(draft.get("directory", ""))
        if d is None or not d.is_dir():
            issues.append(ValidationIssue("wallpapers_directory_missing", "Choose an existing folder", "/directory", "error"))
        if not 60 <= int(draft.get("intervalSeconds", 0)) <= 86400:
            issues.append(ValidationIssue("wallpapers_interval_range", "Interval must be 1 minute to 1 day", "/intervalSeconds", "error"))
        return ValidationResult(not any(i.severity == "error" for i in issues), tuple(issues), draft)

    def plan(self, ctx, draft, status):
        unit_dir = ctx.paths.home / ".config/systemd/user"
        service = render_service(draft)   # plain text, no user input interpolated into ExecStart; argv is fixed
        timer = render_timer(draft["intervalSeconds"])
        o = [
            ops.EnsureDirectory(ctx, unit_dir),
            ops.WriteFileAtomic(ctx, ctx.paths.module_config / "rotation.json", json_dumps(draft), "0600",
                                summary="Save rotation settings"),
            ops.WriteFileAtomic(ctx, unit_dir / "omarchy-cc-wallpapers.service", service, "0644", summary="Write rotation service"),
            ops.WriteFileAtomic(ctx, unit_dir / "omarchy-cc-wallpapers.timer", timer, "0644", summary="Write rotation timer"),
            ops.RunCommand(ctx, ["systemctl", "--user", "daemon-reload"], timeout_s=20, summary="Reload user systemd",
                           inverse=["systemctl", "--user", "daemon-reload"]),
            ops.RunCommand(ctx, ["systemctl", "--user", "enable", "--now", "omarchy-cc-wallpapers.timer"], timeout_s=20,
                           summary="Enable rotation timer",
                           inverse=["systemctl", "--user", "disable", "--now", "omarchy-cc-wallpapers.timer"]),
        ]
        return Plan(self.id, status.revision, tuple(o), (ResourceClaim("systemd.user:omarchy-cc-wallpapers", "exclusive"),),
                    f"Rotate wallpapers from {draft['directory']} every {draft['intervalSeconds']} s", (), ())

    def verify(self, ctx, plan, status_after, results):
        ok = status_after.data["timerActive"] and status_after.data["rotation"] is not None
        return VerifyResult("pass" if ok else "fail", "full", "" if ok else "timer is not active after enable",
                            "" if ok else "wallpapers_timer_inactive", status_after.data)

MODULE = Wallpapers()
```

3. Write `modules/wallpapers/Page.qml` with the page contract: a folder picker (through `BackendClient.query("wallpapers", "list_images", {directory})` for the preview grid), an interval field, `draftChanged` patches, `focusFirst()` focusing the folder field.

4. Add `modules/wallpapers/schemas/draft-v1.json`, `status-v1.json`, `rotation-v1.json`.

5. Add `modules/wallpapers/tests/` with a sample draft, a `test_plan.py` that asserts the operation list, and a `test_apply.py` using the shared `isolated_home`, `stub_command("systemctl", ...)`, and one `fault_plan` case.

6. Append `"wallpapers"` to `MODULES` in `backend/customization_center/modules/__init__.py`.

That is the whole change. `ccctl modules` lists it, the sidebar shows it at `navOrder` 65, `ApplyBar` drives it, the executor backs up and rolls back its four files, the contract suite tests it, and desktop modes can include it as a member once the modes schema defines a `members.wallpapers` shape for its draft. No file under `core/`, `schemas/`, `backend/customization_center/core/`, or `tests/core/` changed. If a future module cannot be written this way, that is a core defect to fix in core, not a reason to special-case the module.

## Module summaries

Each module has a detailed plan under `plans/planned/subplugins/`. This section records what the master plan needs from each: the boundary, the blockers, and the contract decisions. Where the module plan and this document disagree, the module plan is wrong and should be updated, because the contract is defined here.

### Module 1: Visual bar editor (`bar`)

Objective: edit the built-in bar's layout, position, transparency, center anchor, and the active full-bar plugin from a draft, with a schematic preview, and apply it as one transaction.

Integration: `omarchy-shell shell listShellConfig|listPlugins|ping`, `core/catalog.py` over `omarchy-plugin-catalog`, `core/settings_schema.py` for inline widget settings, `enablePlugin`, `moveBarWidget`, `setBarWidget`, `setPluginEnabled`, and the file route. The module is the only writer of the whole `bar` subtree of `shell.json`: `bar.id`, `position`, `transparent`, `centerAnchor`, and every `layout` entry with its inline settings. It owns the exclusive claim `shell.bar`.

Findings from the module plan: existing IPC cannot insert or remove a chosen repeated instance (`putBarWidget` returns early when the id is anywhere in the bar, `setEnabled` moves the first match; `PluginRegistry.qml:296-315, 449-542`), cannot delete an inline key, and has no setter for position, center anchor, or bar id; `omarchy bar position|use|transparent` write the file with `mv` and call `reloadConfig` (`bin/omarchy-shell-config:53-62`, `bin/omarchy-bar:142-216`). So the module has two routes. IPC operations for what IPC expresses exactly, and for the rest a `WriteFileAtomic` on `~/.config/omarchy/shell.json` that preserves every other key, followed by `ShellIpc("reloadConfig")`. The revision compares `listShellConfig` and the file hash. The file route is refused when the file does not parse or when the shell is down; the module never edits `shell.json` behind a stopped shell. A configured third-party bar that fell back to `omarchy.bar` is a verification failure, not a warning.

Contract notes: the plan orders IPC operations first, then at most one file write and one reload. Verify re-reads `listShellConfig` and `listPlugins` and polls until the configured and active bar ids agree. Apply ships in the first release; the upstream `getBarState` and `applyBarConfig` pair would remove the file route and is requested on that basis.

### Module 2: Plugin settings (`plugins`)

Objective: a catalog of what the shell discovered, with origin and trust shown plainly, enable and disable of non-bar kinds, terminal handoff for add, update, remove, and clone, and deep links into the bar editor for anything that lives in the bar.

Integration: `listPlugins` (runtime authority), `listShellConfig`, `core/catalog.py` over `omarchy-plugin-catalog` and manifest reads (enrichment only), `omarchy-plugin-validate` (read-only diagnostic), `setPluginEnabled`, and `omarchy-plugin-add|update|remove|clone` through `TerminalHandoff(wrapped=true)`. The module writes `plugins[]` and `disabledPlugins[]` only, through IPC. It does not place widgets, does not edit widget settings, and does not switch the active bar; for bar widgets and full-bar plugins it shows placement and settings read-only with "Edit in bar editor", which is `requestNavigate("bar", {select: ...})` or `{selectBar: id}`. Its claim is `shell.plugin:<id>` per plugin.

Findings from the module plan: load errors are transient signals, not queryable (`PluginRegistry.qml:31`, `shell.qml:640-650`), so the UI says "No error observed", never "Healthy". A plugin with both `bar` and `bar-widget` kinds is unsupported for mutation until Omarchy defines the semantics. Non-bar plugin entries in `plugins[]` have no settings IPC at all, so the settings tab for those renders `core/SchemaForm.qml` only when a future upstream `patchPluginEntry` exists; until then it is read-only metadata plus the deep link.

Contract notes: the schema dialect (`min`, `max`, `step`, `defaultValue`, with `minimum`, `maximum`, `default` as aliases; verified in Indicators, Agents, Dropbox, Tailscale manifests) is normalized by `core/settings_schema.py`, shared with the bar module. Terminal lifecycle actions are `TerminalHandoff` operations, never advertised as reversible, and the plan says "Clone and switch" because clone enables the copy immediately. This module's own Disable and Remove hand off to a terminal and close the overlay first.

### Module 3: Personal menu editor (`menu`)

Objective: create and edit custom entries in `~/.config/omarchy/extensions/omarchy-menu.jsonc` with a merged tree view, provenance badges, static route preview, guard syntax checks, and canonical JSONC output.

Integration: both JSONC files read-only, `omarchy-menu ping` and `omarchy-menu refresh` (`bin/omarchy-menu:29`), `bash -n` on stdin as a `readonly_check` capability for guards.

Blockers from the module plan: the runtime normalizes every omitted known field before merging, so a user entry that reuses a shipped id replaces the whole entry rather than overlaying declared fields (`shell/plugins/menu/MenuModel.js`, `normalizeItem` and `mergeMenuSources`; reproduced with a label-only override). Field-level override, hide, and per-field reset are gated on an upstream sparse-merge fix with a contract test in `test/shell.d/menu-test.sh`. The trailing-comma regex in `stripJsonc` can mutate string contents (`printf ,}` becomes `printf }`), so the backend parity-checks against the runtime transformation and refuses `menu_runtime_parser_hazard`. `refresh()` returns before the asynchronous `FileView` reload, so verification is `limited` with reason `refresh-ack-only` until an inspect IPC exists.

Contract notes: one `WriteFileAtomic` on the user file, one `RunCommand(["omarchy-menu", "refresh"])` with the same command as its inverse, verify at `limited` level. A malformed user file puts the page in a recovery state that requires named confirmation before replacement; the executor's backup keeps the malformed bytes exactly.

### Module 4: Default application manager (`defaults`)

Objective: show and set the browser, terminal, editor, and coding agent through the four `omarchy-default-*` selectors, with install-and-set handed to the selector's own visible terminal flow.

Integration: the four selectors called with no argument (read) or one canonical argument (set), `omarchy commands --json` for drift detection of the public choice lists, `xdg-settings`, `xdg-terminal-exec --print-id`, `mise where`, and the selector's own terminal handoff for a missing choice.

Findings from the module plan: `omarchy-install-terminal` exits 0 after a failed package install (its `else` branch ends in `echo`), so `omarchy-default-terminal` can write a missing terminal as the preference; the module verifies command, desktop entry, and resolver instead of trusting exit codes and the plan recommends an upstream `exit 1`. Selecting an agent runs `mise use -g` and launches the agent (`bin/omarchy-default-agent:49-65`), so the button reads "Set and launch" and desktop modes exclude agents. Handoff completion is not observable through the selector; the transaction stays `pending_handoff` and the page calls `ccctl reconcile <id>` on focus and reopen, which decides from `status` and `verify` alone because the handoff is unwrapped. Abandoning it records `rolled_back` with reason `user`.

Contract notes: a set of an installed choice is `RunCommand([selector, choice])` with `env: {"BROWSER": null}` for the browser, and with inverse `RunCommand([selector, previous])` when the previous value is a known installed choice, otherwise `RestoreBackup` of the captured state file listed under `extraWritablePaths` (rerunning the agent selector as an inverse would launch another agent). The agent selector uses `wait_policy: "detach"`. A missing choice is `TerminalHandoff([selector, choice], wrapped=false)`, since the selector itself opens the terminal; the transaction moves to `pending_handoff`. Rollback restores the selection only and lists installed software, the mise pin, and a running agent under `residual_side_effects`.

### Module 5: Monitor layout profiles (`monitors`)

Objective: named profiles with stable output identity, a logical-pixel canvas, static geometry validation, a single loader block in `~/.config/hypr/monitors.lua`, generated rules in a separate file, and a timed confirmation whose rollback survives the plugin dying.

Integration: `hyprctl monitors all -j` (plain `monitors` omits mirrors), `hyprctl -j configerrors`, `hyprctl reload`, `luac -p` as a `readonly_check`, `systemd-run --user`, and inventory of `~/.local/state/omarchy/toggles/hypr/*.lua`, which loads after the user's monitor file and can override a profile.

Findings from the module plan: the original master plan armed the rollback timer after the reload; a crash between write and arm strands the user. The executor now arms the backstop before the first backup, and the gate sits after the reload so that the pre-confirmation check sees the new topology. Description alone is not a stable identity (duplicates, blanks, embedded serials); the profile stores make, model, serial, description, and a connector fallback with a policy, and matching is a one-to-one assignment that blocks on ties. Any direct `hl.monitor` call outside the managed block other than the shipped catch-all is an ownership conflict the user resolves by hand; the module never rewrites it. Whether Hyprland accepts `desc:` as a `mirror` target is unverified; the module renders the resolved connector until a disposable-session test proves otherwise.

Contract notes: plan is `EnsureDirectory`, `WriteFileAtomic` (no-op generated file, first time only), `ReplaceManagedBlock` (loader, first time only, markers `MONITORS v1`), `WriteFileAtomic` (generated rules), `HyprctlReload`, `TimedConfirmation(30)`, `WriteFileAtomic` (active-profile pointer). `verify` polls topology until two consecutive samples match; at the gate it runs against the partial results and a `fail` rolls back without waiting. The countdown the user sees is the executor's deadline; one `seconds` value, 30 for monitors, user-settable later in `settings.json`. Toggle clearing is a separate explicit operation with its own backup. Profile deletion is `RemoveFile`. Stored document kinds `profile` and `active`.

### Module 6: Theme composer (`themes`)

Objective: build data-only themes from a semantic draft, preview them in the plugin without touching the running shell theme, save under `~/.config/omarchy/themes/<slug>/`, and activate through `omarchy-theme-set`.

Integration: `omarchy-theme-set <slug>`, `omarchy-theme-bg-set <path>`, `omarchy-theme-set-templates` in a scratch `HOME` for preview rendering (a `readonly_check` because it writes only inside the scratch tree the core creates), `~/.local/state/omarchy/current/theme.name` for verification, `omarchy-shell shell ping`.

Findings from the module plan: `Color` and `Style` are process-wide singletons, so the preview uses parameterized preview components fed by a `PreviewThemeModel` from `ccctl query themes preview`, plus a parity test suite against the real controls. `shell.<section>.toml` replaces a whole section, so every emitted fragment is complete. `omarchy-theme-set` cycles wallpapers when the current one matches, so a preferred wallpaper is set explicitly afterwards. A same-named user theme overlays only a built-in of the same slug, so a base theme is provenance, and the draft materializes resolved values.

Contract notes: save is `ReplaceDirectoryAtomic(themes/<slug>, staged)` after the module rendered into `ctx.paths.staging_dir`; activation adds `RunCommand(["omarchy-theme-set", slug])` with inverse `RunCommand(["omarchy-theme-set", previous])` and `RunCommand(["omarchy-theme-bg-set", path])` with inverse restoring the previous target. "Try in shell" is an explicit, journaled transaction of one `ShellIpc("applyTheme", [colorsB64, shellB64])` whose inverse is the same call with the currently active theme's bytes; it changes only the running shell's tokens, is offered from a button with its own confirmation, and ships in the themes plan's milestone 4. Hover preview stays forbidden. The review discloses hooks and application retints; rollback restores theme state and does not claim to undo every application's in-memory retint. Git-backed and symlinked theme directories are read-only in the first release.

### Module 7: Keybinding editor (`keybindings`)

Objective: inventory active bindings from the compositor, classify provenance honestly, add or replace or disable global keyboard command bindings through a JSON model rendered into one managed block in `~/.config/hypr/bindings.lua`.

Integration: `hyprctl binds` (primary), `hyprctl -j binds` (enrichment after reconciliation; `bin/omarchy-menu-keybindings:275-277` documents why), `hyprctl devices`, `hyprctl reload`, `hyprctl -j configerrors`, `luac -p`, optional `xkbcli` for keycode aliasing, and an inert Lua loader with stubbed `hl` and `o` tables over `$OMARCHY_PATH/default/hypr/bindings/*.lua` for the default catalog, which never loads user Lua.

Findings from the module plan: `hl.unbind` is case-sensitive, so a disable is offered only when the exact source spelling is known from the managed model or the default catalog; unknown runtime rows are read-only. Omarchy deliberately stacks two actions on `ALT + TAB` and pairs press and release on `F9` (`default/hypr/bindings/tiling.lua`, `voxtype.lua`), so "same chord" is a classified outcome, not an error. Hyprland auto-reloads on Lua changes, so backups must exist before the rename; the executor's ordering guarantees this. Provenance labels are "Managed", "Matches Omarchy default", and "Other or dynamic".

Contract notes: plan is `WriteFileAtomic` (model JSON), `ReplaceManagedBlock` (bindings.lua, markers `BINDINGS v1`), `HyprctlReload`. An empty model removes the block (`body: null`). Verify requires each managed bind to appear exactly once in the fresh inventory and each unbind target to be absent. Stored document kind `model`. Desktop modes carry a complete copy of the managed document inline, so no preset store is needed for composition.

### Module 8: Desktop modes (`modes`)

Objective: named, sparse, manually applied combinations of the other modules' state, composed into one plan and one transaction with reverse rollback and drift reporting.

Integration: none of its own. It plans through `ctx.registry` and stores `desktop-modes/<id>.json` and `modes/last-applied.json`.

Findings from the module plan: the earlier mode schema referenced presets by id that no module stored. The contract now keeps everything inline under `members.<module-id>`: for `bar` the target `bar` subtree, for `keybindings` the complete managed document, for `plugins` a map of plugin id to boolean, for `themes` `{slug}` plus optional `preferredWallpaper`, for `monitors` `{profileId}`, for `defaults` per-category option ids excluding the agent, and nothing for `menu` in the first release. Bar and plugin settings both reach `shell.json`, so plugin ids with `bar` or `bar-widget` kinds are rejected in `members.plugins` and the claim check enforces it. Coding agents are excluded because the setter launches the agent. Monitor confirmation is a transaction gate, not a dialog: the executor blocks at the `TimedConfirmation` in the monitors segment, verifies completed segments there, and runs nothing after it until `ccctl confirm`. Member order is monitors, themes, plugins, bar, menu, keybindings, defaults, for the reasons in "Composed plans".

Contract notes: one transaction with segments, no parent and child records. `last-applied.json` is written by the last operation of the same transaction and stores per-member target fingerprints; status compares only included members and reports "Drifted" and "Definition changed" independently. Import is a bounded canonical JSON envelope staged as a draft; export writes under `~/.config/omarchy/customization-center/exports/`; nothing imported runs before a separate review and apply. Triggers are `[]` in the first release.

## Required upstream Omarchy changes

Everything here was found by a module plan against `71b0887c`. None of it blocks the read-only phases. Each row names what the plugin does if upstream declines.

| Change | Where | Needed by | Fallback if declined |
|---|---|---|---|
| Shell IPC `getBarState` returning a shell-issued revision plus configured and active bar ids, and `applyBarConfig <expectedRevision> <barJsonB64>` that replaces only `.bar`, preserves other keys, calls `persistShellConfig` once, and returns `stale_revision` on mismatch | `shell/shell.qml` IPC handler, `shell/services/PluginRegistry.qml` | bar (would remove the file route), modes (bar segment) | Not a blocker. The bar module keeps its file route, the same `mv` plus `reloadConfig` mechanism `omarchy bar position` uses, with a revision check against `listShellConfig` and the file hash. |
| Shell IPC `patchPluginEntry <id> <patchJson> <deleteKeysJson> <expectedRevision>` for non-bar entries in `plugins[]` | `shell/shell.qml`, `PluginRegistry.qml` | plugins (settings tab for non-bar plugins) | Settings for non-bar plugins stay read-only metadata plus a deep link. Widget settings are the bar module's and need no upstream change. |
| Shell IPC `listPluginDiagnostics` retaining the last load error per plugin and kind | `shell/shell.qml` loader paths | plugins (health display) | UI says "No error observed this session"; transient signals captured while the overlay is open. |
| Sparse merge for user menu entries: merge raw user fields before `normalizeItem`, with a contract test | `shell/plugins/menu/MenuModel.js`, `test/shell.d/menu-test.sh` | menu (field-level override, hide, per-field reset) | Custom entries only. Optional "Shadow entire shipped entry" action that lists every pinned field; whole-entry reset only. |
| String-aware trailing-comma stripping in `stripJsonc` | `shell/plugins/menu/MenuModel.js` | menu | Backend refuses documents where the runtime transformation would change a string (`menu_runtime_parser_hazard`). |
| Menu `inspect` IPC returning loaded source revisions, parse status, and normalized rows | `shell/plugins/menu/Menu.qml` | menu (full verification) | Verification level `limited`, banner "Saved; runtime verification limited". |
| `omarchy-install-terminal` exits non-zero when the package install fails, with a regression test | `bin/omarchy-install-terminal`, `test/shell.d/default-apps-test.sh` | defaults | Module verifies command, desktop entry, and `xdg-terminal-exec --print-id`; never trusts the installer exit code. |
| Selector `--json` output, a handoff completion token, and `omarchy-default-agent --no-launch` plus an unset command | `bin/omarchy-default-*`, `bin/omarchy-launch-floating-terminal-with-presentation` | defaults (cleaner verification), modes (agent support) | Text parsing with `omarchy commands --json` drift checks; `pending_handoff` reconciliation; agents excluded from modes. |
| `omarchy-theme-set --json` or a result file with staged hashes and per-step outcomes, and an immutable staged input option | `bin/omarchy-theme-set` | themes (verification, race) | State-file and hash verification after the command; external changes during the command are reported as verification failure. |
| A non-global theme context for `qs.Ui` controls | `shell/Commons/Color.qml`, `Style.qml`, `shell/Ui/` | themes (preview fidelity) | Parameterized preview components with a parity test suite; preview labelled "representative". |

Two items are not Omarchy's to fix. Hyprland's `hyprctl -j binds` reliability across versions is handled by plain-output parsing, and whether `desc:` works as a `mirror` target is a Hyprland question answered by a test in the disposable session.

## Implementation roadmap

### Phase ordering rationale

The order below is driven by three facts. First, nothing can be tested end to end before the executor and the test fixtures exist, so core comes first and is finished before any module writes a file. Second, the modules that depend only on files and `hyprctl` (menu, keybindings, monitors, themes) exercise the executor's file operations, managed blocks, reload deferral, and the gate, which are the parts most likely to hide bugs; bar and plugin settings come after them because their adapters lean on `fake_shell`, and by then the executor is proven. Third, desktop modes is a pure consumer of the others' plans, so it is last, and its composition tests are the final proof that the contract holds.

### Phase 0: Core and test fixtures

- Manifest, overlay root with `opened`, `open`, `close`, `AppShell`, `Sidebar`, `ModuleRegistry`, `BackendClient`, `DraftStore`, `TransactionModel`, `ApplyBar`, `ChangeList`, `ConfirmDialog`, `DiffView`, `ErrorBanner`, `ConfirmationGate`.
- `ccctl` with every command in the reference, all core Python files, all envelope schemas, the executor with the full state machine, `TimedConfirmation` through `systemd-run --user`, startup recovery.
- `tests/conftest.py` with isolated home, command stubs, fake shell IPC, fault injection; `tests/core/` covering every core file; `tests/contract/` running against a `hello` sample module kept under `tests/fixtures/modules/hello/` that is not in `MODULES`.
- `docs/adding-a-module.md` written by actually adding the `hello` module following it.

Exit gate: the overlay opens and closes cleanly through `summon` and `hide`; the `hello` module applies, verifies, rolls back under every fault hook, and survives a killed process; no test writes outside its temporary home; `ccctl doctor` confirms no bytecode is written under the plugin directory.

### Phase 1: Read-only center

- `capabilities`, `status`, and `Page.qml` for all eight modules. Each page renders current state, warnings, and unsupported states, and nothing else.
- Upstream proposals from "Required upstream Omarchy changes" submitted as issues or pull requests during this phase, so the review clock starts early.

Exit gate: opening every page causes no persistent write; each page's displayed state matches the source of truth its module plan names; each module passes the contract suite.

### Phase 2: File-owned modules apply

- Menu: custom entry editing, canonical writer, refresh, limited verification, malformed-file recovery.
- Keybindings: managed model, Lua serializer, block rendering, reload, config-error diff, conflict classification, chord capture.
- Monitors: profiles, identity assignment, geometry validation, loader bootstrap, guarded apply with `TimedConfirmation`, external rollback.
- Themes: semantic drafts, TOML generation, scratch preview, save, activation, reactivation rollback.

Exit gate: each module's acceptance criteria in its plan pass on an isolated home and on the developer's live desktop; `ConfirmationGate` recovers a visible display after killing both the overlay and `ccctl` during a monitor test apply.

### Phase 3: Defaults

- Set installed choices, restore Omarchy defaults, install-and-set through the selector's terminal, `pending_handoff` reconciliation, agent disclosure.

Exit gate: current values match the four selectors; a cancelled install leaves the displayed default unchanged; the terminal-installer false-success case is caught by verification.

### Phase 4: Shell-owned modules apply

- Bar: IPC operations plus the file route, `core/catalog.py`, `core/settings_schema.py` and `SchemaForm`, configured-versus-active verification, reset to shipped layout.
- Plugin settings: enable and disable of non-bar kinds, lifecycle handoffs through `cc-handoff`, deep links into the bar editor, read-only settings for non-bar plugins.

Exit gate: a widget moves between all three sections, a second Indicators instance is added and removed without touching the first, position and center anchor change through the file route with `reloadConfig`, every change survives a shell restart, and the file route is refused with the shell stopped or the file unparsable; a clone handoff finishes through `reconcile` and the catalog shows the switch.

### Phase 5: Desktop modes

- Mode schema with inline members, editor, create from current by copying each owner's current state into the member shape, composed planning with claims, apply with the monitor gate, drift and definition-changed status, import and export.

Exit gate: a mode with monitor, theme, plugin, bar, keybinding, and default changes applies in order, and an injected failure at every operation boundary restores every module; a composed plan with a duplicate exclusive claim is rejected before any backup.

### Phase 6: Hardening and release

- Keyboard traversal and accessible labels on every page; font and spacing scale checks; performance numbers for cold open and page switch (targets 300 ms and 100 ms on the development host).
- Live verification in top, bottom, left, right bar positions, dark and light themes, one and several monitors including a scaled and a rotated one.
- The acceptance suite run in the `omarchy-iso-test` VM.
- `docs/recovery.md` executed by hand from a TTY for every `rollback_failed` fixture and for "the overlay will not open".
- Repository packaged for `omarchy plugin add`; minimum Omarchy commit and Hyprland version recorded in the README and probed by `ccctl doctor`.

Exit gate: all module acceptance criteria pass; recovery documentation tested; no open high-severity issue.

## Testing strategy

### Core unit tests

Atomic write and directory swap under crash at each step; backup and restore including absent files and mode preservation; managed block insertion, replacement, removal, and every collision shape; JSONC subset parsing with duplicate-key detection and the runtime parity check; Lua literal escaping including numeric escape adjacency and marker-like text; TOML fixed-schema serialization and reparse; lock contention and stale lock files; journal state transitions, fsync ordering, and startup recovery from every state; `commands.py` argv-only enforcement, env allowlist, timeout kill, output cap, redaction; `shell_ipc.py` success-body allowlist against recorded real replies and the exit-0 error bodies; `registry.py` with a broken module in the list.

### Contract tests

`tests/contract/` runs the same suite for every id in `MODULES`. It is the enforcement of the architecture: declared core services match imports, plans use only vocabulary operations on allowed paths, every non-reversible operation is flagged, every stored document version migrates, `Page.qml` honors the page contract, `status` and `plan` perform no writes, and the executor fault matrix ends in `rolled_back` or `rollback_failed` with recovery commands.

### Adapter contract tests

Command stubs assert exact argv, env, stdin, timeout handling, and behavior on non-zero exit, malformed output, and oversized output for `omarchy-shell` (every method used, including the proposed ones behind a flag), `omarchy-plugin-catalog`, `omarchy-plugin-validate`, `omarchy-plugin-add|update|remove|clone`, `omarchy-menu` (`refresh`, `ping`), `omarchy-default-*`, `omarchy commands --json`, `omarchy-theme-set`, `omarchy-theme-bg-set`, `omarchy-theme-set-templates`, `omarchy-launch-floating-terminal-with-presentation`, `cc-handoff`, `omarchy-hyprland-reload-guard`, `hyprctl` (`monitors all -j`, `binds`, `-j binds`, `devices`, `reload`, `reload config-only`, `-j configerrors`), `luac`, `bash -n`, `xdg-settings`, `xdg-terminal-exec`, `mise`, `systemd-run`, `systemctl`.

### Module tests

Each module's `tests/` covers its parsers, validators, and planner against fixtures, and one integration test per acceptance criterion in its plan using the shared fixtures. Module plans list their matrices.

### QML tests

`qmltestrunner` over `core/` and each `Page.qml`: page contract presence, no direct `draft` assignment, no `Process` or `FileView` instantiation outside `core/BackendClient.qml`, focus order, every state the module plan lists, no apply from selection or focus changes, `ConfirmationGate` mirroring and single-token resolution, scaling under `[font] base-size` 16 and `[spacing] scale` 1.5.

### Live and VM verification

The developer desktop for daily checks; the `omarchy-iso-test` VM for the release matrix: summon through IPC and through a menu entry, every page in dark and light themes, four bar positions, monitor topologies, shell restart with dirty drafts, Hyprland reload failures, a third-party plugin updated and removed while the plugin catalog page is open, both the overlay and `ccctl` killed during a monitor test apply.

## Security and safety requirements

1. Subprocesses take argument arrays. No form value is ever part of a shell string. `commands.py` has no `shell=True` path.
2. Generated Lua strings go through `lua.py`. Generated TOML goes through `toml_writer.py`. Generated JSONC goes through `jsonc.py`. No string concatenation into a file format.
3. Menu guards and custom commands are parsed with `bash -n` on stdin and never executed by the plugin.
4. `paths.py` refuses any target outside the allowlisted roots and any path with a symlinked component. `module.json` `extraWritablePaths` are validated at registry load, not at apply.
5. Every subprocess has a timeout and an output cap. Stdout of an IPC call is checked against an allowlist of success bodies.
6. Journals record the first 4 KiB of each stream after redaction and never record environment variables, draft bodies, or tokens in clear.
7. Plugin lifecycle actions and application installs stay in Omarchy's terminal flows through `TerminalHandoff`. The plugin never passes `--yes` or `--enable`.
8. No write under `$OMARCHY_PATH`, no write under the plugin's own directory, no bytecode.
9. The backstop for a gated apply is a `systemd-run --user` transient unit, armed before the first backup, that does not depend on the overlay or the `ccctl` that armed it.
10. Theme output is data only: `colors.toml`, complete `shell.<section>.toml` fragments, raster backgrounds. No Lua, no hooks, no symlinks, no executable bits.
11. Deleting a profile, theme, mode, custom menu entry, managed binding, or user override requires a named confirmation that states the exact item.
12. Imported mode bundles are bounded in bytes, depth, and count, schema-validated, staged as drafts, and never executed or applied without a separate review.
13. A `rollback_failed` transaction blocks every further apply until resolved. The plugin would rather stop than compound an error.

## Known risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Plugins are unsandboxed | A defect affects the whole shell session | Backend does the work in a separate short-lived process; QML never touches files; parsers are fuzzed with recorded real inputs |
| Writing bytecode into the plugin directory triggers a shell hot reload | The overlay reloads mid-apply | `sys.dont_write_bytecode = True` before imports; `ccctl doctor` and a core test assert no `__pycache__` under the plugin directory after a full test run |
| The bar file route races the shell | A widget persisting its own inline state between the read and the write is lost | Revision covers `listShellConfig` and the file hash; the write is refused when either moved, when the file does not parse, or when the shell is down; verify re-reads after `reloadConfig`; upstream `applyBarConfig` would retire the route |
| Menu sparse merge is not fixed upstream | Shipped entries cannot be overridden field by field | Custom entries only; optional explicit "Shadow entire shipped entry" with every pinned field listed |
| A monitor apply hides the UI | The user cannot confirm | Static geometry checks, `TimedConfirmation` armed before the write, visible-root verification, external unit, countdown on every screen |
| Rollback conflicts with a concurrent edit | Rollback clobbers user work | `WriteFileAtomic` checks its post-write hash. Managed-block inverses require the exact managed post-image. Directory replacement undo binds the staged, installed, raw-result, original-target, and previous-directory evidence; any mismatch preserves both versions and ends in `rollback_failed`. |
| Theme activation has side effects rollback cannot undo | Applications keep a retinted state | Disclosed in review; rollback restores authoritative theme state and says what it did not verify |
| Omarchy command output changes across versions | Adapters misparse | Probes for specific capabilities, `omarchy commands --json` drift checks in defaults, recorded-output fixtures re-recorded per supported commit, fail closed on unknown output |
| The composed-plan claim model misses a shared resource | Two segments write the same thing | Claims are part of the contract test; the modes plan rejects bar-kind ids in `plugins.states`; the global lock serializes everything else |
| A module violates the contract quietly | Core guarantees no longer hold for that module | The contract suite runs for every id in `MODULES` on every test run and inspects imports, operations, paths, and schemas |

## Decisions made in this plan

- One overlay plugin, `firstpick.customization-center`, eight internal modules, no `keepLoaded`.
- The module contract in "Shared architecture" is the definitive one. Module plans align to it.
- Apply and rollback live only in the core executor. Modules produce operations with inverses.
- One lock for all modules, in `$XDG_RUNTIME_DIR`, non-blocking.
- One transaction with segments for composed plans; no parent and child records.
- `TimedConfirmation` is a blocking gate: the backstop is armed before the first backup, the executor keeps the lock while waiting, and confirmation and timeout are mutually exclusive.
- Terminal handoffs leave a transaction `pending_handoff`; `ccctl reconcile` finishes it from the `cc-handoff` sentinel and re-verification.
- Drafts persist through `ccctl draft` because the overlay is destroyed on close.
- `ccctl` is `#!/usr/bin/python3`, standard library, Python 3.11 minimum, no bytecode.
- Discovery is the explicit `MODULES` list plus `module.json`; QML learns modules from `ccctl modules`.
- Shared error codes are fixed; module codes are prefixed with the module id.
- Bar and plugin settings apply in the first release. The bar module is the only writer of the `bar` subtree of `shell.json`, through IPC where exact and through a file write plus `reloadConfig` otherwise; the plugins module writes only `plugins[]` and `disabledPlugins[]` through IPC.
- No preset store. Desktop modes carry inline member copies.
- Coding agents are excluded from desktop modes.
- Desktop modes are manual in the first release.

## Decisions still needed before release

1. Public repository URL for `omarchy plugin add`.
2. Whether the first release tracks Omarchy `master` at a pinned commit or waits for a tagged release; the capability probes make either workable, but the README needs one answer.
3. Minimum Hyprland version (the monitor and keybinding plans assume 0.55+ Lua config and were tested on 0.56.2).
4. Whether to ship the menu module's "Shadow entire shipped entry" fallback at all, or hold field-level overrides until upstream answers.
5. Whether to submit the `getBarState` and `applyBarConfig` proposal upstream before or after the first release, given that the file route makes it a convenience rather than a need.
6. Whether the gate's `seconds` (30 for monitors) becomes user-settable in `settings.json` in the first release or later.
7. History retention: number of transactions and backup bytes kept before pruning committed transactions.
8. Whether `ccctl` should also be installed as a user-local command (`~/.local/bin/omarchy-cc`) for recovery from a TTY, or whether the docs point at the plugin directory path.

## Definition of done

The Customization Center is complete when:

- It installs with `omarchy plugin add`, is enabled with `omarchy plugin enable`, and opens through `omarchy-shell shell summon`.
- All eight modules meet the acceptance criteria in their plans.
- Every write goes through the executor with validation, backup, verification, journal, and rollback, and the contract suite proves it for every module in `MODULES`.
- Handwritten configuration outside managed blocks is byte-identical after every apply and every rollback in the test matrix.
- `shell.json` is written only by the bar module's file route through the executor, followed by `reloadConfig`, and never while the shell is down or the file does not parse; the isolated-home guard asserts that no other module and no other code path touches it.
- Monitor changes recover after the overlay and `ccctl` are killed during a test apply.
- Desktop modes compose the other modules' plans and roll back in reverse under fault injection.
- The `hello` module in `tests/fixtures/modules/` proves that adding a module touches one directory and one line.
- Automated tests cover success, stale revision, malformed input, command failure, timeout, rollback, and rollback failure for every module.
- Visual verification passes on the developer desktop and the acceptance suite passes in the VM.
- `docs/recovery.md` has been executed from a TTY for every `rollback_failed` fixture.
- This plan moves from `plans/planned/` to `plans/archive/` only after implementation and verification are finished.

Current disposition: the source and isolated test gates pass. The live desktop, VM matrix, and manual TTY recovery items above are not available in the current environment, so the definition of done is not yet fully met and the plan remains in `plans/planned/`.
