# Desktop modes module plan

Module id: `modes`
Directory: `modules/modes/`
Master plan: `plans/planned/customization-center-masterplan.md`, Module 8
Contract: the master plan's "Shared architecture" section as amended by the contract amendments sheet (sections A to J). Where this plan names an executor behavior, it is restating that sheet, not proposing it.
Omarchy source checked: `/mnt/SSD_NVME_4TB/GitHub/omarchy-fork` at `71b0887c`
Other plans read: all seven under `plans/planned/subplugins/`. They were being rewritten while this plan was written; every assumption about another module's draft or status shape is listed in section 18.

## 1. What a mode is

A mode is a named, sparse bundle of per-module drafts. Applying a mode means: for each module the mode names, build that module's draft from the mode's section, ask the module for a `Plan` through `ctx.registry`, concatenate the plans into one plan with one segment per member, and hand it to the core executor. The modes module writes no bar, theme, monitor, plugin, keybinding, or default-application file itself. Its own files are the mode definitions under `~/.config/omarchy/customization-center/desktop-modes/<id>.json` and the last-applied record at `~/.local/state/omarchy/customization-center/modes/last-applied.json`.

A mode is "last applied", never enforced. After apply, the page compares the fields the mode named against each member module's current status and reports drift. Nothing reverts drift automatically.

### What the first release does

- Create, edit, duplicate, rename, delete, import, and export modes.
- Create a mode from the current state of chosen modules and fields.
- Plan and apply a mode across up to six member modules with one review, one lock, one transaction, and the core rollback walk.
- Keep the monitor confirmation gate inside the transaction, so nothing after it runs unless the user confirms the new layout.
- Detect drift field by field.
- Generate the shell command that summons the center at a mode's review page, and hand it to the keybinding or menu page as a payload.

### What the first release refuses

- Automatic triggers. `triggers` must be `[]`. Section 12 records the mechanisms a later release would use and what does not exist in Omarchy today.
- Any member plan that contains a non-reversible operation or a `TerminalHandoff`. That excludes install-and-set for default applications, every plugin lifecycle action, and the coding agent, whose setter also launches the agent (`bin/omarchy-default-agent:63-65`).
- The personal menu as a member. The member order reserves its slot; a menu entry can launch a mode, a mode does not edit the menu.
- Partial bar layouts. If a mode sets `bar.layout`, it sets all three sections.
- Merging managed keybindings. If a mode sets `keybindings.document`, it replaces the whole managed document.
- Shared presets between modes. Each mode carries its own copies. Duplicate copies the sections.
- Any write from `Page.qml`, and any command or path supplied by an imported file.

## 2. Verified integration points

Line numbers are from the commit above.

| Claim | Source | Consequence |
|---|---|---|
| The shell exposes `summon`, `hide`, `toggle` on the `shell` IPC target | `shell/shell.qml:873` (`IpcHandler { target: "shell" }`), `:1002`, `:1006`, `:1010` | A mode shortcut is `omarchy-shell shell summon firstpick.customization-center '<payload>'`. |
| A summon of an already loaded plugin still delivers the payload through `open()` | `shell/shell.qml:440-478` queues the payload; `shell/shell.qml:541-556` (`deliverIfLoaded`) calls `loader.item.open(queue[i])` for every queued payload | The overlay root routes a second summon to the modes page while it is open (section G of the sheet). |
| `summon` refuses a plugin that is not enabled and returns `false` | `shell/shell.qml:452-455` | A shortcut generated for a disabled center does nothing. The shortcut sheet warns when `plugins` status shows the center disabled. |
| `omarchy-shell` bounds IPC with `timeout --kill-after=1s` and `OMARCHY_SHELL_IPC_TIMEOUT` (default `2s`); it reports "not running" and "not ready" | `bin/omarchy-shell:58-59`, `:65`, `:75` | Handled by the core `ShellIpc` operation, which sets `OMARCHY_SHELL_IPC_TIMEOUT=5s` and maps those messages to `runtime_unavailable`. |
| Shell config is persisted by the shell with atomic writes; `omarchy-bar` commits `shell.json` directly for position, transparency, and bar id | `shell/shell.qml:108` (`persistShellConfig`), `:131-134` (`atomicWrites: true`); `bin/omarchy-shell-config:6`, `:53` (`commit()`); `bin/omarchy-bar:152,154,176,203,213,216` | The bar module uses the same file route plus `reloadConfig` for what IPC cannot express (sheet section H). Modes never calls `omarchy bar`; it consumes the bar module's plan. |
| Plugin enablement and bar placement are the same registry operation | `shell/services/PluginRegistry.qml:449` (`setEnabled(id, value, placement)`), `:282`, `:296`, `:317`, `:123`, `:141`, `:206` | A plugin with a `bar` or `bar-widget` kind is bar state. The `plugins` member rejects such ids; they belong in the `bar` section. |
| `omarchy-theme-set` takes its own lock, writes `theme.name`, pushes the palette through `shell applyTheme`, then runs `hyprctl reload` and the `theme-set` hook | `bin/omarchy-theme-set:16`, `:261-262`, `:296`, `:308`, `:316`, `:320` with `bin/omarchy-restart-hyprctl:5`, `:339` with `bin/omarchy-hook:18-28` | The theme segment reloads Hyprland, which re-reads `monitors.lua` (`config/hypr/hyprland.lua:19`). The monitor segment must be confirmed before the theme segment starts. Hook duration is unbounded; the themes module's `RunCommand` timeout covers it. |
| Hyprland loads `hypr.monitors` and `hypr.bindings` from the user config | `config/hypr/hyprland.lua:19`, `:21` | Monitor and keybinding segments both end in a reload. Two reloads in one transaction are expected. |
| Monitor identity is available as `description` from `hyprctl monitors all -j` | `bin/omarchy-hyprland-monitor-laptop:5`, `bin/omarchy-monitor-state:6`; a local `hyprctl -j monitors` returned descriptions that include the serial (two identical `VG27A` panels were distinguishable) | Drift and future monitor triggers can use descriptions. The monitors module owns matching. |
| Omarchy's monitor recovery unit only clears a toggle at session start | `default/systemd/user/omarchy-recover-internal-monitor.service`; `bin/omarchy-hw-recover-internal-monitor:7-9` | It is not a rollback mechanism. The core `TimedConfirmation` gate and its backstop unit are. |
| `systemd-run --user` is available | local: `/usr/bin/systemd-run`, systemd 261 | The core capability `timed_confirmation` still checks it at runtime; a missing binary refuses the apply with `capability_missing`. |
| Menu actions run as `bash -lc <action>` | `shell/plugins/menu/Menu.qml:137-142` and `shell/Commons/Util.qml:53-55` | A generated menu action is a shell string. Modes builds it with `shlex.quote`. |
| Default keybindings summon overlays with `omarchy-shell shell toggle <id>` | `default/hypr/bindings/utilities.lua:3`, `:97-102` | The generated shortcut uses `summon`, not `toggle`, because a toggle on an open center would close it instead of switching to the mode. |
| The coding agent setter runs `mise use -g` and then `exec omarchy-agent` | `bin/omarchy-default-agent:49`, `:63`, `:65` | Excluded from modes. |
| Hooks exist for `battery-low`, `font-set`, `post-boot`, `post-update`, `pre-refresh-pacman`, `theme-set` only | `default/agents/skills/omarchy/hooks.md`; `config/omarchy/hooks/` | No Omarchy event exists for AC change, monitor hotplug, or network change. See section 12. |
| `omarchy-hyprland-reload-guard` pauses Hyprland auto-reload during package transactions | `bin/omarchy-hyprland-reload-guard:1-15`; `bin/omarchy-hyprland-monitor-watch:52` skips reloads while paused | The core `HyprctlReload` refuses with `runtime_unavailable` while paused (sheet section B), so a mode never reloads into a half-updated package config. |

## 3. How modes uses the module contract

### 3.1 Member adapters

`modules/modes/backend/members/<member>.py` is the only code in the center that knows how to turn a mode section into another module's draft. One file per member: `monitors.py`, `themes.py`, `plugins.py`, `bar.py`, `keybindings.py`, `defaults.py`. Each exports:

```python
class MemberAdapter(Protocol):
    module_id: str
    order: int                      # position in the apply order, section 5.2
    def validate_section(self, section, member_status, member_caps) -> list[Problem]: ...
    def to_draft(self, section, member_status) -> dict: ...        # a draft the member module accepts
    def observe(self, section, member_status) -> dict[str, Any]: ... # comparable values for the fields the section names
    def capture(self, member_status, selection) -> dict | None: ... # "create from current"
    def summarize(self, section) -> list[str]: ...                 # one line per field for cards and review
    def external_references(self, section) -> list[Ref]: ...       # for export
```

Adapters never call `ctx.commands`, never read files, and never import another module's backend package. They only shape data. The member module's own `validate`, `plan`, and `verify` do the real checks, reached through `ctx.registry.module(id)`, the one cross-module dependency the contract permits (sheet section F). A ninth module that wants mode support adds one adapter file here; nothing in core changes.

### 3.2 What a "preset" is

The master plan named `barPreset` and `keybindingPreset`. No preset store is part of the contract (sheet section I). A preset is the member's target state, stored inline in the mode file under `members.<module-id>`, revision-free, and rebound to the current status by the adapter at plan time. There is no separate preset file and no preset id. Two modes that want the same bar layout each carry a copy. Duplicate copies. This removes the "shared preset changed under a mode" problem, and export is one file.

For the bar, the stored form is the target `bar` subtree as `shell.json` holds it (entries are `{"id": ..., ...settings}`). For keybindings, the complete managed document (`schemaVersion`, `bindings[]`, `disabled[]`). For monitors, a profile id, because the monitors module already has named profile files. For themes, a slug and an optional preferred wallpaper. Plugins and defaults are small maps.

### 3.3 Draft envelope for the modes module itself

`Page.qml` edits one draft. `ccctl validate|plan|apply modes --draft <path>` receives:

```json
{
  "schemaVersion": 1,
  "action": "save",
  "mode": { "...": "mode-v1 document, section 4" },
  "import": null,
  "export": null,
  "expected": { "modeDigest": "sha256:..." }
}
```

| Field | Type | Meaning |
|---|---|---|
| `action` | `"save" \| "delete" \| "apply" \| "import" \| "export"` | What `plan` composes. |
| `mode` | mode-v1 or `null` | Required for `save`, `apply`, `export`. For `delete` only `mode.id` is read. |
| `import` | `{ "bundle": bundle-v1, "resolutions": { ... } }` or `null` | Section 10. |
| `export` | `{ "outputName": "presentation-2026-08-28.json" }` or `null` | Written under `Paths.exports`. |
| `expected.modeDigest` | string or `null` | Digest of the stored file the edit started from; `null` for a new mode. |

`plan` for `save` produces one `WriteFileAtomic`; `delete` one `RemoveFile`. `apply` composes member plans. `import` composes member "save artifact" plans plus one mode file write. `export` produces one `WriteFileAtomic` under `Paths.exports`. Every action goes through the executor, so every action is journaled and reversible.

## 4. Mode schema v1

File: `~/.config/omarchy/customization-center/desktop-modes/<id>.json`. Schema: `modules/modes/schemas/mode-v1.json`. Canonical JSON, sorted keys, two-space indent, trailing newline.

```json
{
  "version": 1,
  "id": "presentation",
  "name": "Presentation",
  "description": "Projector, light theme, quiet bar",
  "icon": "󰐩",
  "members": {
    "monitors": { "profileId": "projector" },
    "themes": { "slug": "presentation-light", "preferredWallpaper": "stage.jpg" },
    "plugins": { "enabled": { "omarchy.notifications": false } },
    "bar": {
      "position": "top",
      "transparent": false,
      "layout": {
        "left": [ { "id": "omarchy.workspaces" } ],
        "center": [ { "id": "omarchy.clock" } ],
        "right": [ { "id": "omarchy.audio" }, { "id": "omarchy.indicators", "items": ["Dnd"] } ]
      }
    },
    "keybindings": {
      "document": { "schemaVersion": 1, "bindings": [], "disabled": [] }
    },
    "defaults": { "browser": "firefox", "terminal": "ghostty" }
  },
  "triggers": []
}
```

Top level:

| Field | Type | Rules |
|---|---|---|
| `version` | integer | Must be `1`. Any other value is `modes_unsupported_version`; the file is listed as unreadable, never rewritten. |
| `id` | string | `^[a-z0-9][a-z0-9._-]{0,63}$`, no `..`, and the file name must equal `<id>.json`. |
| `name` | string | 1 to 80 Unicode scalar values, no control characters. |
| `description` | string | 0 to 400 scalar values. Optional. |
| `icon` | string | 0 to 4 scalar values. Optional. Rendered as text. |
| `members` | object | At least one known key. Unknown keys are `modes_unknown_member`. `menu` is known but refused in the first release with `modes_member_field_refused`. |
| `triggers` | array | Must be `[]` in v1. |

Members are keyed by module id so `compose.py` can iterate the fixed order without a name mapping. Every member is optional. An absent member means "leave that module alone". Inside a member, an absent field means the same thing, with the two all-or-nothing exceptions below.

`members.monitors`

| Field | Type | Rules |
|---|---|---|
| `profileId` | string | Must match the monitors module's profile id pattern and resolve to a stored profile at plan time (`modes_missing_profile`). |

`members.themes`

| Field | Type | Rules |
|---|---|---|
| `slug` | string | `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`. Must be a theme the themes module lists as activatable, built-in or user (`modes_missing_theme`). |
| `preferredWallpaper` | string | Optional. A wallpaper file name inside that theme's backgrounds, validated by the themes module. |

`members.plugins`

| Field | Type | Rules |
|---|---|---|
| `enabled` | object, plugin id to boolean | At least one entry. Each id must exist in the plugins module's catalog (`modes_unknown_plugin`). Ids whose kinds include `bar` or `bar-widget` are `modes_bar_kind_in_plugins`. |

`members.bar`

| Field | Type | Rules |
|---|---|---|
| `id` | string | Optional. `"omarchy.bar"` or a plugin id with kind `bar`. Absent means untouched; to select the built-in bar explicitly, write `"omarchy.bar"`. |
| `position` | `"top" \| "bottom" \| "left" \| "right"` | Optional. |
| `transparent` | boolean | Optional. |
| `centerAnchor` | string | Optional. Empty string clears it. |
| `layout` | object with `left`, `center`, `right` arrays | Optional, but if present all three arrays are required. Entries are objects with a string `id` and any other JSON keys, which are widget settings. Order is significant. |

`members.keybindings`

| Field | Type | Rules |
|---|---|---|
| `document` | object | A complete keybinding managed document. Validated by `keybindings.validate`. Present means "the managed document becomes exactly this". |

`members.defaults`

| Field | Type | Rules |
|---|---|---|
| `browser`, `terminal`, `editor` | string | Each optional. Values are option ids from the defaults module's catalog. `agent` is rejected with `modes_member_field_refused`. |

A mode stores no absolute paths, no environment values, no monitor connector names, and no transaction ids. `modes.validate` enforces the shape and the id rules without touching the registry. Reference existence (profile, theme, plugin, option) is checked in `plan`, because it needs member status.

## 5. Composition

### 5.1 From mode to plan

```python
ORDER = ["monitors", "themes", "plugins", "bar", "menu", "keybindings", "defaults"]   # menu refused in v1

def plan(self, ctx, draft, status):
    envelope = parse_envelope(draft)
    if envelope.action != "apply":
        return plan_local_action(ctx, envelope, status)   # save, delete, import, export

    mode = validate_mode(envelope.mode)                    # section 4, pure
    plan = Plan(module="modes", summary=f"Apply mode {mode.id}",
                expected_revision=status.revision,
                segments=[], operations=[],
                metadata={"modeId": mode.id, "modeDigest": digest(mode), "before": {}})

    for member_id in ORDER:
        if member_id not in mode.members:
            continue
        section = mode.members[member_id]
        module = ctx.registry.module(member_id)
        adapter = MEMBERS[member_id]
        caps = module.capabilities(ctx)
        if not caps.can_apply:
            raise ModesError("modes_member_unavailable", member=member_id, reasons=caps.reasons)
        mstatus = module.status(ctx)
        problems = adapter.validate_section(section, mstatus, caps)
        if problems:
            raise ModesError("modes_section_invalid", member=member_id, problems=problems)
        plan.metadata["before"][member_id] = adapter.observe(section, mstatus)

        mdraft = adapter.to_draft(section, mstatus)
        vr = module.validate(ctx, mdraft)
        if vr.errors:
            raise ModesError("modes_member_validation_failed", member=member_id, errors=vr.errors)
        mplan = module.plan(ctx, mdraft, mstatus)
        check_composable(member_id, mplan)                 # section 5.3
        plan.operations.extend(mplan.operations)
        plan.segments.append(Segment(module=member_id, expected_revision=mstatus.revision,
                                     operation_ids=[op.id for op in mplan.operations],
                                     draft=mdraft))
        plan.warnings.extend(prefix(member_id, mplan.warnings))

    # Last segment: the modes module's own record, written by the same transaction,
    # so a failed apply never records a mode as applied.
    record = last_applied_record(mode, plan)              # section 7.1
    op = WriteFileAtomic(path=ctx.paths.module_state("modes") / "last-applied.json",
                         content=canonical_json(record), mode=0o600)
    plan.operations.append(op)
    plan.segments.append(Segment(module="modes", expected_revision=status.revision,
                                 operation_ids=[op.id], draft=None))
    plan.digest = canonical_digest(plan)
    return plan
```

`status.revision` for modes is `sha256` over canonical JSON of `{"modes": {id: fileDigest}, "lastApplied": fileDigestOrNull, "members": {id: memberRevision}}`. Because it folds in every member revision, the executor's `expected_revision` check at the start covers all members. Each segment's own `expected_revision` lets the executor report which member moved.

### 5.2 Order and why

1. `monitors`. The only member that can make the overlay invisible. Its plan ends with the gate.
2. `themes`. `omarchy-theme-set` runs `hyprctl reload` (`bin/omarchy-theme-set:320`) and repaints the shell through `applyTheme` (`:308`). Nothing after it may assume the overlay is still visible, and the reload re-reads the generated monitor rules, so the gate must already be confirmed. It is also the slowest step (parallel retints plus hooks), so it runs while the user is still watching.
3. `plugins`, then `bar`. Non-bar plugin state first so a full-bar switch in the bar segment sees the final plugin set.
4. `menu`. Reserved; refused in the first release.
5. `keybindings`. Runs after the theme segment's reload has finished, so the keybinding module's `hyprctl configerrors` baseline is not disturbed by a concurrent reload.
6. `defaults`. Selector commands with no display effect. Last so a failure here rolls back the least.
7. `modes`. The last-applied record.

Only rule 1 and the first half of rule 2 are safety rules. The rest is about clean verification and fewer reloads.

### 5.3 Composability check

`check_composable(member_id, mplan)` rejects a member plan when:

- any operation has `inverse is None` (`modes_nonreversible_member`);
- any operation is a `TerminalHandoff` (`modes_nonreversible_member`);
- `member_id != "monitors"` and the plan contains a `TimedConfirmation` (`modes_unexpected_confirmation`; the executor would also refuse two gates in one plan);
- `member_id == "monitors"`, the plan contains a `WriteFileAtomic`, `ReplaceManagedBlock`, or `HyprctlReload`, and no `TimedConfirmation` follows the last of them (`modes_monitor_gate_missing`);
- `member_id == "monitors"` and any operation follows the `TimedConfirmation` (`modes_monitor_gate_not_last`).

A monitors plan with zero operations (profile already active) passes; it has nothing to guard.

### 5.4 Adapter behavior per member

`monitors.to_draft` returns `{"action": "activate", "profileId": <id>}`. `observe` returns `{"activeProfileId": status.activeProfile.id, "verdict": status.activeProfile.verdict}` where verdict is the monitors module's own `verified | overridden | drifted` word. `capture` returns the active profile id only when verdict is `verified`; otherwise `None` with the message "Save the current layout as a profile in Monitors first".

`themes.to_draft` returns `{"action": "activate", "slug": <slug>}` plus `"preferredWallpaper"` when the section has it. `observe` returns `{"themeName": status.current.name}` and, when the section names a wallpaper, `{"background": status.current.backgroundName}`. `capture` returns the current name and, if the user ticks it, the current background name.

`plugins.to_draft` returns `{"enabled": {id: bool}}` for non-bar ids. `validate_section` rejects ids not in `status.plugins`, ids with `bar` or `bar-widget` kinds, and ids whose row reports `canDisable == false` when the target is `false`. `observe` returns `{id: status.plugins[id].state.enabled}` for the ids in the section. `capture` takes the user's selected ids.

`bar.to_draft` starts from `status.bar` (the current `bar` subtree), overlays the fields present in the section, and returns the target `bar` subtree as the bar module's draft with `baseRevision = status.revision`. The bar module decides which parts go through IPC and which through the file route (sheet section H); modes does not care. `observe` returns the present scalar fields plus, when `layout` is present, the three arrays of serialized entries, with `bar.id` omission normalized to `"omarchy.bar"`. `capture` copies the chosen fields from `status.bar`.

`keybindings.to_draft` returns the document as the keybinding module's draft, with its expected revision fields filled from status. `validate_section` refuses when status reports the managed block as anything but `present` or `absent` (`managed_block.inspect` states `duplicate`, `unterminated`, `reversed`, `nested`) or reports drift between the block and the document, because replacing a block the user edited by hand is not a mode's decision. `observe` returns `{"documentDigest": sha256(canonical(status.managed.document)), "blockState": status.managed.blockState}`. `capture` returns the current managed document.

`defaults.to_draft` returns one draft per category present, `{"category": c, "optionId": v, "mode": "set", "install": false}`; `compose.py` calls `plan` once per category and concatenates, in the fixed order browser, terminal, editor, all inside one `defaults` segment. `validate_section` refuses when the option's availability is not `available` (`modes_default_not_installed`). `observe` returns `{c: status.categories[c].current.optionId}`. `capture` returns the current option id only when the category state is `ready`.

### 5.5 Review content

`ccctl plan modes` returns the plan in `data`. The review page shows, in order:

1. One block per segment: module title, the adapter's `summarize(section)` lines, then the member plan's operation summaries verbatim.
2. A "Commands this mode binds" list when the keybindings section contains `exec` actions, each command verbatim in monospace.
3. All warnings, prefixed with the member id.
4. The gate notice: "Monitors change first. You will have 30 seconds to keep the new layout. Nothing else changes until you confirm."
5. The plan digest, which the apply call must repeat.

## 6. Executor behavior for a composed plan

This section restates the sheet's sections A, C, and I for the example mode so the test matrix in section 16 has exact expectations. Nothing here is a proposal.

### 6.1 Worked example

Presentation mode from section 4, where the profile is not yet active and the theme differs. The bar section changes position and moves one widget.

```text
armed  omarchy-cc-confirm-<txid>.timer, --on-active = t(01) + t(02) + 30 + 5   (before backups)
backups for every path declared by ops 01 to 14

op 01  monitors     WriteFileAtomic     ~/.config/omarchy/customization-center/generated/monitors.lua
op 02  monitors     HyprctlReload
op 03  monitors     TimedConfirmation(30)
       --- pre-confirmation check: monitors.verify (its segment is complete); then await token
op 04  themes       RunCommand          ["omarchy-theme-set", "presentation-light"]      inverse ["omarchy-theme-set", "tokyo-night"]
op 05  plugins      ShellIpc            setPluginEnabled ["omarchy.notifications", "false"] inverse [..., "true"]
op 06  bar          ShellIpc            moveBarWidget ["omarchy.audio", {...}]             inverse moveBarWidget back
op 07  bar          WriteFileAtomic     ~/.config/omarchy/shell.json (position)            inverse (restore backup, ShellIpc reloadConfig)
op 08  bar          ShellIpc            reloadConfig                                       inverse ()
op 09  keybindings  WriteFileAtomic     ~/.config/omarchy/customization-center/keybindings.json
op 10  keybindings  ReplaceManagedBlock ~/.config/hypr/bindings.lua
op 11  keybindings  HyprctlReload
op 12  defaults     RunCommand          ["omarchy-default-browser", "firefox"]             inverse ["omarchy-default-browser", "chromium"]
op 13  defaults     RunCommand          ["omarchy-default-terminal", "ghostty"]            inverse ["omarchy-default-terminal", "alacritty"]
op 14  modes        WriteFileAtomic     ~/.local/state/omarchy/customization-center/modes/last-applied.json
       --- final verify: every segment; commit; stop the timer if still armed
```

The inverse shapes on ops 06 to 08 are what the bar module is expected to declare; section 18 lists that assumption.

### 6.2 Run sequence

1. Startup recovery runs first, as it does for every lock-taking command (sheet section E). A non-terminal journal is finished or reported as `recovery_required`.
2. Take the per-user lock, non-blocking. Busy returns `locked` with the running transaction id.
3. Compare `plan.expected_revision` with `modes.status().revision`. Mismatch is `stale_revision`. Each segment's `expected_revision` is compared with its member's current revision in the same pass, so the error names the member that moved.
4. Create the journal in state `applying`, write `current-transaction`, and, because the plan contains a gate, arm the backstop unit as in section 6.1. No `systemd-run` means `capability_missing` before any write.
5. Back up every path declared by every operation in the whole plan, before op 01. This is the "snapshot all modules first" rule; it is what the contract already does.
6. Run operations in order. Each operation journals `started`, fsync, run, `done` with the bounded result, fsync.
7. At the gate, run the pre-confirmation check (section 6.3), then wait.
8. After the last operation, call `verify` for every segment with the full results, mark `committed`, fsync, stop the timer, remove `current-transaction`, release the lock, print the result.

### 6.3 The gate

`TimedConfirmation(30)` at op 03:

1. Pre-confirmation check: for every segment whose operations have all completed (here only `monitors`), call `registry.module(seg.module).verify(ctx, plan, status_after)` with the partial results. A failure goes straight to the rollback walk with reason `verification`, without waiting.
2. State `awaiting_confirmation`, `confirmation.deadline = now + 30`, fsync. The lock stays held.
3. Poll every 200 ms for `$XDG_RUNTIME_DIR/omarchy-customization-center/confirm/<txid>`. `ccctl confirm <txid> --token <t>` writes it (0600) without taking the lock; it refuses with `confirmation_expired` when the state is not `awaiting_confirmation` and `confirmation_invalid` on a bad token.
4. Token present and its sha256 matches `confirmation.tokenSha256`: `systemctl --user stop omarchy-cc-confirm-<txid>.timer`, delete the token, state `applying`, continue with op 04.
5. Deadline passes: state `rolling_back`, reason `timeout`, rollback walk. The backstop finds the journal terminal when it fires and exits 0.
6. Executor dies before or during the wait: the backstop runs `ccctl rollback <txid> --reason timeout`, which waits up to 10 s for the lock, finds `applying` or `awaiting_confirmation`, and runs the walk over every operation marked `done`.

The countdown is the core `ConfirmationGate.qml` on every screen, driven by `ccctl transaction current`. Closing the overlay does not confirm. The modes page contributes nothing to the gate except the notice in review.

### 6.4 The rollback walk

Reverse order of completed operation ids. Tuple inverses run in their listed order; an empty tuple does nothing; `HyprctlReload` inverses are skipped in place and one reload runs after the last file-restoring inverse; a `WriteFileAtomic` inverse is skipped as `rollback_conflict` when the file's sha256 differs from `written_sha256`; failures do not stop the walk.

Failure at op 10 in the example (the managed block write fails; 10 is not `done`):

```text
09⁻¹  restore backup of keybindings.json
08⁻¹  ()                                                  nothing
07⁻¹  restore backup of shell.json, then ShellIpc reloadConfig
06⁻¹  moveBarWidget omarchy.audio back
05⁻¹  setPluginEnabled omarchy.notifications true
04⁻¹  omarchy-theme-set tokyo-night                       (reloads Hyprland on its own)
03⁻¹  ()                                                  a confirmed gate has nothing to undo
02⁻¹  deferred
01⁻¹  restore backup of generated/monitors.lua
      one HyprctlReload, because 02⁻¹ was deferred and a file under ~/.config/hypr/ was restored
```

Final state `rolled_back` when every inverse ran, `rollback_failed` otherwise, with per-operation results in the journal. Op 14 never ran, so the previous last-applied record is untouched; nothing special is needed to "preserve the prior record".

The monitor restore after a confirmed gate runs without a second gate. Within one transaction that is seconds after the user confirmed the previous layout, and the restored rules are the ones that were in effect before op 01. Section 19 lists the residual risk.

### 6.5 Rolling back a committed mode

`ccctl rollback <txid> --reason user` on a committed transaction that contained a gate builds the inverse transaction in the sheet's order: inverses of ops 04 to 14 with reload deferral, then a fresh `TimedConfirmation(30)`, then inverses of ops 01 and 02. If that gate times out, the executor re-runs ops 04 to 14 forward, which restores the confirmed state. The user is never left on an unconfirmed layout.

The modes page offers this as "Roll back this mode" from the transaction's History entry. The review for it shows `metadata.before` (the adapter observations captured at plan time) so the user sees what each member returns to. Revision checks are the executor's: each segment's member must still be at the revision recorded at commit, or the rollback is refused with `stale_revision` and the page offers the comparison.

## 7. Last-applied state and drift

### 7.1 The record

`~/.local/state/omarchy/customization-center/modes/last-applied.json`, schema `modules/modes/schemas/last-applied-v1.json`. The master plan's `active-mode.json` name is superseded by the sheet (section I); the content means "last applied", nothing more.

```json
{
  "version": 1,
  "modeId": "presentation",
  "modeDigest": "sha256:...",
  "planDigest": "sha256:...",
  "plannedAt": "2026-08-28T19:40:12Z",
  "targets": {
    "monitors": { "activeProfileId": "projector" },
    "themes": { "themeName": "presentation-light", "background": "stage.jpg" },
    "plugins": { "omarchy.notifications": false },
    "bar": { "position": "top", "transparent": false, "layout": { "left": [], "center": [], "right": [] } },
    "keybindings": { "documentDigest": "sha256:..." },
    "defaults": { "browser": "firefox", "terminal": "ghostty" }
  }
}
```

`targets[member]` is exactly what `adapter.observe(section, status)` will return when the member matches. It is computed at plan time from the section, so the record is fixed before the transaction id exists. `ccctl history --module modes` maps `planDigest` to the transaction id.

### 7.2 Algorithm

`modes.status(ctx)` runs this for the recorded mode and returns `lastApplied` with a state and a field list:

```python
def drift(ctx, record):
    mode_file = load_mode(record.modeId)                     # may be missing or changed
    findings, indeterminate = [], []
    for member_id, target in record.targets.items():
        module = ctx.registry.module(member_id)
        caps = module.capabilities(ctx)
        if not caps.can_read:
            indeterminate.append((member_id, caps.reasons)); continue
        try:
            mstatus = module.status(ctx)
        except CcError as e:
            indeterminate.append((member_id, e.code)); continue
        observed = MEMBERS[member_id].observe_from_targets(target, mstatus)
        for field, expected in flatten(target).items():
            got = flatten(observed).get(field, MISSING)
            if got is MISSING:
                indeterminate.append((member_id, field))
            elif not equal(expected, got):
                findings.append(Finding(member_id, field, expected, got))
    definition_changed = mode_file is None or digest(mode_file) != record.modeDigest
    state = ("indeterminate" if indeterminate
             else "drifted" if findings else "applied")
    return DriftReport(state, findings, indeterminate, definition_changed)
```

`flatten` turns nested targets into dotted field names (`bar.layout.right`, `plugins.omarchy.notifications`, `defaults.browser`). `equal` is structural JSON equality after each adapter's normalization (bar entries compared as canonical JSON, `bar.id` omission equal to `"omarchy.bar"`). Layout arrays are compared whole; a single moved widget reports the section as drifted with both arrays in the finding.

Per-member observation sources:

| Member | Observed from | Notes |
|---|---|---|
| monitors | `status.activeProfile.id` and verdict | Verdict `drifted` or `overridden` from the monitors module makes the field drifted even if the id matches. |
| themes | `status.current.name`, `status.current.backgroundName` | The themes module reads `theme.name` and the background link. |
| plugins | `status.plugins[id].state.enabled` | A plugin no longer installed is indeterminate, not drifted. |
| bar | `status.bar.*` | Shell unreachable is indeterminate. |
| keybindings | digest of `status.managed.document`; `blockState` | Block state other than `present` makes the member indeterminate with the module's message. |
| defaults | `status.categories[c].current.optionId` | State `unknown` or `probe_error` is indeterminate. |

States shown on the card:

- Never applied. No record, or the record names another mode.
- Applied. State `applied`, `definition_changed` false.
- Drifted. Findings listed as "Bar position: mode says top, now bottom".
- Definition changed. Mode file or its digest differs from the record. Coexists with any of the above.
- Indeterminate. At least one member could not be read. The card shows which, and never says "applied" on partial evidence.

Cost: `status` calls up to six member `status()` methods, some of which run subprocesses; `ctx.cache` memoizes probes within the call. The page shows a skeleton while it runs. If measured cold status exceeds 1.5 s on the reference VM, move drift to `ccctl query modes drift` and let the list render first.

## 8. Journal shape

The executor writes the journal; modes only reads it through `ccctl transaction <txid>` and `ccctl history`. For a composed plan the record has `segments` (sheet section I) and `confirmation` (section A). The shape modes expects:

```json
{
  "version": 1,
  "transactionId": "01J...",
  "module": "modes",
  "action": "apply",
  "state": "committed",
  "reason": null,
  "createdAt": "RFC3339",
  "updatedAt": "RFC3339",
  "planDigest": "sha256:...",
  "expectedRevision": "sha256:...",
  "metadata": { "modeId": "presentation", "modeDigest": "sha256:...", "before": { "themes": { "themeName": "tokyo-night" } } },
  "backups": [ { "path": "~/.config/hypr/bindings.lua", "backupId": "b-0007", "existed": true } ],
  "segments": [
    { "module": "monitors", "expectedRevision": "sha256:...", "operationIds": ["op-01", "op-02", "op-03"],
      "verify": { "atGate": { "ok": true }, "final": { "ok": true } }, "rollback": null }
  ],
  "operations": [
    { "id": "op-01", "kind": "WriteFileAtomic", "summary": "Write generated monitor rules", "state": "done",
      "startedAt": "...", "finishedAt": "...", "writtenSha256": "sha256:...", "result": { "exit": null, "stdoutBytes": 0 } }
  ],
  "confirmation": { "unit": "omarchy-cc-confirm-01J...", "armedAt": "...", "deadline": "RFC3339", "tokenSha256": "sha256:...", "status": "confirmed" },
  "completedOperationIds": ["op-01", "op-02"],
  "errors": [],
  "rollbackErrors": []
}
```

States: `applying`, `awaiting_confirmation`, `committed`, `rolling_back`, `rolled_back`, `rollback_failed`. Reasons: `user`, `timeout`, `recovery`, `verification`, `operation`. Operation states: `pending`, `started`, `done`, `failed`, `reversed`, `reverse_failed`, `rollback_conflict`, `skipped_nonreversible`.

## 9. Create from current state

Flow on the page:

1. The user names the mode and ticks members. For `plugins` and `defaults` the page shows a picker for individual ids and categories, because pinning every plugin would make the mode a second full configuration.
2. Capture is read-only. `ccctl query modes captureable` returns a map of member id to what `capture` would produce now, or the reason it cannot.
3. The page fills the mode draft from that map for the ticked members and shows each captured section with an "Untouched" label on everything not ticked.
4. Save goes through the normal `save` action.

Refusals, all shown inline with the member's message:

- monitors: no verified active profile. Message links to the Monitors page through `requestNavigate("monitors", {})`.
- keybindings: managed block state other than `present` or `absent`, or block drift.
- defaults: category state is not `ready`.
- plugins: bar-kind ids are not offered in the picker.
- bar: shell unreachable.

Update mode from current does the same, restricted to members and fields already present in the mode. It never adds a member the mode did not have.

## 10. Import and export

### 10.1 Bundle

One JSON document, schema `modules/modes/schemas/mode-bundle-v1.json`.

```json
{
  "bundleVersion": 1,
  "exportedBy": { "application": "firstpick.customization-center", "version": "0.1.0" },
  "exportedAt": "RFC3339",
  "mode": { "...": "mode-v1" },
  "artifacts": [
    { "module": "monitors", "kind": "monitor-profile", "id": "projector", "digest": "sha256:...", "data": { "...": "monitor-profile-v1" } }
  ],
  "externalReferences": [
    { "module": "themes", "kind": "theme", "id": "presentation-light" },
    { "module": "plugins", "kind": "plugin", "id": "omarchy.notifications" },
    { "module": "defaults", "kind": "option", "category": "browser", "id": "firefox" }
  ]
}
```

Bar layout and keybinding document travel inside `mode`. Monitor profiles are separate files owned by the monitors module, so they travel as artifacts; the monitors adapter strips `connectorFallback` values before export when the profile carries descriptions, and marks the artifact `machineSpecific: true` otherwise. Themes are directories with many files and possibly templates, so they are references only. Plugins and default options are references.

Limits, checked before schema validation: 1 MiB total, nesting depth 12, 10000 array items in any array, 65536 bytes in any string, 16 artifacts. Violations are `modes_import_limit`.

Export writes to `Paths.exports / "<mode-id>-<YYYYMMDD-HHMMSS>.json"` through a `WriteFileAtomic`. The page shows the path with a copy button. Any other destination is outside the allowed write roots.

### 10.2 Import

Import is two separate actions with a review between them.

Stage. `ccctl validate modes --draft {action: "import", import: {bundle}}` parses within limits, validates the bundle and the embedded mode with the same rules as a saved mode, validates each artifact through its member module's `validate`, and returns the review in `ValidationResult.details`:

```json
{
  "mode": { "id": "presentation", "collision": "exists" },
  "artifacts": [ { "kind": "monitor-profile", "id": "projector", "collision": "same-digest" } ],
  "externalReferences": [ { "kind": "theme", "id": "presentation-light", "resolved": false } ],
  "commands": [ { "source": "keybindings.bindings[3]", "chord": "SUPER + SHIFT + P", "command": "obs --startrecording" } ],
  "machineSpecific": [ "monitor-profile:projector" ]
}
```

Review. The page shows every command verbatim, one checkbox each; Commit stays disabled until all are ticked, and the commit draft carries `resolutions.commandsReviewed: true`, without which `plan` returns `modes_import_unreviewed`. Collisions get a choice each: `rename` (new id, references rewritten), `replace` (backup taken by the executor), `reuse` (only offered for `same-digest`), `cancel`. Unresolved external references do not block import; they block apply later with `modes_missing_theme` and friends.

Commit. `ccctl plan|apply modes --draft {action: "import", import: {bundle, resolutions}}` composes: for each artifact, the member module's save draft (for monitors, `{"action": "save-profile", "profile": data}`) planned through the registry; then one `WriteFileAtomic` for the mode file. No runtime operation is allowed in an import plan; `check_composable` runs with an extra rule that rejects `RunCommand`, `ShellIpc`, `HyprctlReload`, and `TimedConfirmation` (`modes_import_runtime_op`). Apply is a separate action with its own review.

Nothing from a bundle becomes argv. Ids are validated by pattern and joined to paths only by the core `paths` helper, which refuses traversal and symlinked parents.

## 11. Launching a mode from a keybinding or the menu

The center is an overlay. `open(payloadJson)` is the only entry (`docs/omarchy-shell.md:44-45`). The command that opens the modes page at a mode's review step:

```bash
omarchy-shell shell summon firstpick.customization-center '{"module":"modes","modeId":"presentation","action":"review"}'
```

`summon` rather than `toggle`, because `toggle` hides an open center (`shell/shell.qml:510-513`). A second summon while open still calls `open()` with the new payload (`shell/shell.qml:541-556`); `CustomizationCenter.open` routes `{"module": "modes", ...}` to the page's `handlePayload(payload)` (sheet section G).

`handlePayload` on the modes page accepts `{modeId, action}` with `action` one of `review` (default) or `edit`. It navigates to the mode, runs plan, and lands on review. The user still presses Apply. Hidden apply would skip stale checks and the gate.

Shortcut generation is a hand-off, not a transaction of this module:

- Keybinding. The page emits `requestNavigate("keybindings", {"addBinding": {"chord": <captured>, "description": "Mode: Presentation", "action": {"type": "exec", "command": <the command above, built with shlex.quote>}}})`. Conflict checks and apply happen there.
- Menu entry. The page emits `requestNavigate("menu", {"addEntry": {"parent": "modes", "label": "Presentation", "action": <same command>}})`.

Both need the shell to have the center enabled; `summon` returns `false` otherwise (`shell/shell.qml:452-455`). The sheet warns when the plugins status shows the center disabled. Whether the keybindings and menu pages accept those payload keys is an assumption in section 18.

## 12. Later: triggers

Not in the first release. Recorded here so the schema reservation (`triggers: []`) has a known future and nobody invents a trigger runner from scratch.

What exists in Omarchy at `71b0887c`:

- Monitor hotplug. `bin/omarchy-hyprland-monitor-watch:5` reads Hyprland's `.socket2.sock` and reacts to `monitoradded`, `monitorremoved`, `configreloaded` (`:95-114`). It is launched from `default/hypr/autostart.lua:9`. A trigger daemon would read the same socket. Physical connection without Hyprland: `bin/omarchy-hw-external-monitors:5-11` scans `/sys/class/drm/card*-*/status`.
- AC and battery. `bin/omarchy-power-present:5-14` reads `/sys/class/power_supply/*/type` and `online` for `Mains` or `USB`; `bin/omarchy-battery-present` reads `BAT*/present`. There is no event; Omarchy probes once at start through `omarchy-powerprofiles-init` (`default/hypr/autostart.lua:8`). No udev rule ships for it (`default/udev/` contains only `framework16-qmk-hid.rules`). A trigger would poll sysfs or subscribe to UPower on D-Bus; neither is verified as an Omarchy dependency.
- Lid. `bin/omarchy-hw-laptop-closed:6-8` reads `/proc/acpi/button/lid/*/state`.
- Network identity. `bin/omarchy-network-status:22-49` prints `wifi\t<ssid>\t<signal>\t<freq>`, `ethernet\t<dev>`, or `disconnected`, using `ip route get`, `nmcli`, and `iw`. No event; `nmcli monitor` would provide one.
- Hooks. Only `battery-low`, `font-set`, `post-boot`, `post-update`, `pre-refresh-pacman`, `theme-set` (`default/agents/skills/omarchy/hooks.md`). None fire on the events above.

Rules a trigger release must keep: one mode per trigger, no merging of modes; the trigger process runs `ccctl plan` and then notifies or summons the review page, it never runs `ccctl apply` unattended; the same lock and the same gate apply; triggers import disabled; rate limit of one evaluation per 10 s per mode with coalescing by mode id.

## 13. ccctl usage and error codes

All through the contract commands; no modes-specific verbs.

```text
ccctl status modes                                  # modes list, last-applied record, drift
ccctl query modes captureable                       # section 9
ccctl query modes drift                             # only if drift moves out of status for speed
ccctl validate modes --draft d.json                 # schema, ids, import staging review in details
ccctl plan modes --draft d.json                     # composed plan (apply), or local plan (save, delete, import, export)
ccctl apply modes --draft d.json --expected-revision <rev>
ccctl confirm <txid> --token <t>                    # from ConfirmationGate.qml
ccctl transaction current | <txid>                  # progress while apply blocks
ccctl rollback <txid> --reason user
ccctl history --module modes
ccctl recover
```

Error codes added by this module, all prefixed `modes_`:

| Code | When |
|---|---|
| `modes_unsupported_version` | Mode or bundle `version` is not 1. |
| `modes_invalid_id` | Id pattern or file name mismatch. |
| `modes_unknown_member` | `members` has a key that is not a registered adapter. |
| `modes_empty` | `members` has no entries. |
| `modes_section_invalid` | Adapter `validate_section` problems; details carry field paths. |
| `modes_member_field_refused` | `defaults.agent`, `members.menu`, or any field the first release refuses. |
| `modes_bar_kind_in_plugins` | A bar or bar-widget id in `plugins.enabled`. |
| `modes_missing_profile`, `modes_missing_theme`, `modes_unknown_plugin`, `modes_default_not_installed` | Reference resolution at plan time. |
| `modes_member_unavailable` | Member `capabilities().can_apply` is false; reasons are passed through. |
| `modes_member_validation_failed` | Member `validate` returned errors; passed through with member prefix. |
| `modes_nonreversible_member`, `modes_unexpected_confirmation`, `modes_monitor_gate_missing`, `modes_monitor_gate_not_last` | Composability, section 5.3. |
| `modes_import_limit`, `modes_import_runtime_op`, `modes_import_unreviewed` | Import, section 10. |
| `modes_triggers_unsupported` | `triggers` is not `[]`. |

Shared codes used unchanged: `stale_revision`, `validation_failed`, `runtime_unavailable`, `capability_missing`, `locked`, `timeout`, `malformed_output`, `ipc_rejected`, `confirmation_expired`, `confirmation_invalid`, `rollback_failed`, `nonreversible_requires_confirmation` (never expected, because composition refuses such plans first).

## 14. Page.qml

Exposes the contract properties, signals, `focusFirst()`, and `handlePayload(payload)`. `status` carries `modes[]`, `lastApplied`, `memberCapabilities`. `draft` is the envelope from section 3.3. The page owns no timers and no process handles; progress comes from `BackendClient.pollTransaction`.

Components under `modules/modes/components/`: `ModeCard.qml`, `ModeEditor.qml`, `MemberSection.qml` (one per member, with an "Untouched" state), `PluginPicker.qml`, `DefaultsPicker.qml`, `PlanReview.qml`, `DriftPanel.qml`, `ImportReview.qml`, `ShortcutSheet.qml`.

States:

| State | Entered when | Leaves to |
|---|---|---|
| `loading` | Page shown, status pending. | `empty`, `ready`, `error`. |
| `empty` | No modes stored. | `editing` (Create, Create from current, Import). |
| `ready` | Modes listed with per-card state from section 7.2. | `editing`, `reviewing`, `importing`, `busy`. |
| `editing` | A mode draft is open. Continuous `validate` on change. | `ready` (Save applied, or Discard with confirmation). |
| `reviewing` | `plan` for `apply` returned. Shows section 5.5. | `applying` (Apply), `editing` (Back), `stale` (`stale_revision`). |
| `stale` | Any `stale_revision`. Only Refresh plan. | `reviewing`. |
| `applying` | Journal state `applying`. | `awaiting_confirmation`, `applied`, `failed`. |
| `awaiting_confirmation` | Journal state says so. `ConfirmationGate.qml` is on every screen. Closing the overlay does not confirm. | `applying`, `failed`. |
| `applied` | Journal `committed`. Shows segments, History, Roll back this mode. | `ready`. |
| `failed` | Journal `rolled_back`. Shows the failing operation, the reason, and the walk's results. | `ready`. |
| `recovery_required` | Journal `rollback_failed`, or `ccctl modules` reported unfinished recovery. Blocks apply. Lists paths, backup ids, and `ccctl recover`. | `ready` after the user resolves it in History. |
| `busy` | `locked`. Shows the running transaction from `transaction current`. | `ready`. |
| `importing` | Bundle staged, review shown. | `ready` (Commit or Cancel). |
| `error` | `status` failed. Retry. | `loading`. |

Keyboard: arrow keys between cards, Enter opens, `Ctrl+Enter` is Review, Escape backs out one state. Every destructive action (Delete, Replace on import, Discard) names the mode in its confirmation.

## 15. Files

```text
modules/modes/
├── module.json                 # id "modes", navOrder 80, page "Page.qml", backend "customization_center.modules.modes", coreServices ["registry", "staging"]
├── Page.qml
├── components/                 # section 14
├── backend/
│   ├── __init__.py             # MODULE = ModesModule()
│   ├── module.py               # Module protocol: capabilities, status, validate, plan, verify, query
│   ├── store.py                # list/load/canonicalize mode files, digests, id checks
│   ├── compose.py              # section 5
│   ├── drift.py                # section 7
│   ├── capture.py              # section 9
│   ├── bundle.py               # section 10
│   ├── shortcut.py             # section 11, command string builder
│   └── members/                # section 3.1 adapters
├── schemas/
│   ├── mode-v1.json
│   ├── mode-bundle-v1.json
│   └── last-applied-v1.json
└── tests/
```

`capabilities()` for modes reports `can_read: true` always, `can_apply` true when the core `timed_confirmation` capability is present, and a per-member map copied from each member's capabilities so the editor can grey out members before the user builds a section that cannot apply.

`verify()` for modes checks that `last-applied.json` parses, has the expected `planDigest`, and that `drift()` returns `applied` for the record just written. At the gate its segment is never complete, so it is only called at the end. Anything else fails verification, and the executor rolls the whole mode back. That is intentional: a mode that does not verify as applied immediately after apply should not be recorded as applied.

## 16. Tests

All under `modules/modes/tests/`, using the core fixture harness (isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_RUNTIME_DIR`, command stubs including `systemd-run` and `systemctl`).

### 16.1 Fixtures

- `fixtures/modes/presentation.json`, `travel.json` (monitors plus defaults), `theme-only.json`, `bar-only-position.json`, `keybindings-only.json`.
- `fixtures/modes/invalid/`: `version-2.json`, `bad-id.json`, `empty-members.json`, `unknown-member.json`, `menu-member.json`, `bar-kind-in-plugins.json`, `agent-default.json`, `partial-layout.json`, `triggers-nonempty.json`, `absolute-path-in-bar-settings.json`.
- `fixtures/last-applied/`: `applied.json`, `other-mode.json`, `missing-mode-file.json`.
- `fixtures/bundles/`: `good.json`, `oversize.json`, `deep.json`, `duplicate-artifact.json`, `digest-mismatch.json`, `traversal-id.json`, `commands.json`, `machine-specific.json`, `runtime-op-artifact.json`.
- `stubs/members/`: one stub per member implementing the `Module` protocol with scripted `capabilities`, `status`, `validate`, `plan`, `verify` results, recording every call. Stub plans use real core operation objects so the real executor runs them against stub command runners.

### 16.2 Unit

- Schema: every invalid fixture yields its named code and no other; the valid ones round-trip through canonicalization byte-for-byte.
- Adapters: `to_draft` output validates against the member's draft schema fixture; `observe` is stable across key order; `capture` refuses in each documented case.
- Composition: order matches section 5.2 for every subset of members; `check_composable` rejects each case in section 5.3 with a plan built from real operations; a monitors plan with zero ops passes; the modes segment is always last.
- Drift: applied, one scalar drift, layout array drift, plugin uninstalled (indeterminate), keybinding block state `duplicate` (indeterminate), definition changed alone, definition changed plus drift, record names another mode.
- Bundle: each invalid fixture; command extraction lists every `exec` command; commit without `commandsReviewed` is `modes_import_unreviewed`; connector fallbacks stripped on export when descriptions exist; `machineSpecific` set otherwise.
- Shortcut: the generated command parses back with `shlex.split` into exactly four argv items and the payload parses as JSON.
- Revision: modes `status().revision` changes when any member revision, any mode file, or the record changes, and only then.

### 16.3 Executor integration with stub members

Each row runs the real executor on a composed plan from `presentation.json` with all six stub members, and asserts the journal end state, the recorded call sequence, the `systemd-run` and `systemctl` stub argv, and file contents in the isolated home. Fault points are entries in the harness's `ctx.faults` set, absent from the production context.

| Fault point | Expected outcome |
|---|---|
| `stale:monitors` | `stale_revision` naming `monitors`; no backstop armed; no operation ran. |
| `capability:timed_confirmation:missing` | `capability_missing` before backups. |
| `fail:op-01` | Backstop armed then stopped; backup restored; `rolled_back`, reason `operation`; no later segment called. |
| `fail:op-02` (reload nonzero) | 01⁻¹ then one deferred reload; `rolled_back`. |
| `fail:verify:monitors:gate` | Pre-confirmation check fails; `rolled_back`, reason `verification`; no wait. |
| `confirm:timeout` | `awaiting_confirmation` then `rolling_back` reason `timeout`; ops 04 to 14 never started; timer stop recorded. |
| `confirm:bad_token` | `confirmation_invalid`; timeout path. |
| `confirm:replay` | Second token after continue is ignored and deleted. |
| `kill:before_gate` | Backstop stub runs `ccctl rollback <txid> --reason timeout`; `rolled_back`; lock released. |
| `kill:during_wait` | Same, from `awaiting_confirmation`. |
| `fail:verify:themes:final` | Walk from op 14 down; `rolled_back`. |
| `fail:op-05` (IPC body outside `expect`) | `ipc_rejected`; walk 04⁻¹, 03⁻¹, 02⁻¹ deferred, 01⁻¹, reload. |
| `fail:op-10` | Exactly the sequence in section 6.4. |
| `conflict:op-09` (file changed after write) | 09⁻¹ recorded `rollback_conflict`; walk continues; `rollback_failed`. |
| `fail:op-13` | 12⁻¹ then everything before. |
| `fail:verify:modes:final` | 14⁻¹ restores the previous record; previous mode still shows as last applied. |
| `fail:inverse:op-04` | `rollback_failed`; remaining inverses still attempted and recorded. |
| `kill:after_started:op-09`, `kill:after_done:op-09`, `kill:before_commit` | `ccctl recover` reaches `rolled_back`; a `done` op is reversed once; a `started` op's inverse runs only when the file differs from its backup. |
| `locked` | Second apply returns `locked` with the first transaction id while the first waits at the gate. |
| `external_change:bar` (between ops 05 and 06) | Op 06 fails on the bar module's revision guard; walk from 05⁻¹. |
| `rollback:committed` | `--reason user` builds inverses of 04 to 14, a gate, inverses of 01 and 02; `rollback:committed:timeout` re-runs 04 to 14 forward and ends `committed`. |

### 16.4 QML

Every state in section 14 reachable and rendered; selection never triggers `requestApply`; overlay close during `awaiting_confirmation` leaves the state and does not send confirm; the review page lists every keybinding command; Delete dialog names the mode; `handlePayload({modeId, action: "review"})` lands on review for a stored mode and shows an error card for an unknown id.

### 16.5 Live VM

Presentation mode on one and two outputs; confirm, let it expire, and close the overlay during the countdown; theme with a slow `theme-set.d` hook; disable the center and try the generated shortcut; import a bundle exported from another VM with a different connector name; roll back a committed mode and let the rollback's gate time out.

## 17. Core services used

Everything below exists in the amended contract; modes adds nothing to core.

- Executor with `Plan.segments`, per-segment `expected_revision`, segment verify at the gate and at the end, and the rollback walk (sheet sections A, C, I).
- `TimedConfirmation(seconds)` with the backstop unit `omarchy-cc-confirm-<txid>` armed at transaction start, the token file, `ccctl confirm --token`, `ccctl transaction current | <txid>`, and `ConfirmationGate.qml` on every screen (section A).
- User-initiated rollback of a committed transaction with a gate: inverses after the gate, fresh gate, inverses before the gate, forward re-run on timeout (section A).
- Operations: `WriteFileAtomic`, `RemoveFile`, `RunCommand`, `ShellIpc` with its error mapping and `ipc_rejected`, `HyprctlReload` with reload-guard check and inverse deferral (section B).
- `ctx.registry.module(id)` as the only permitted cross-module dependency (section F); `ctx.cache` for memoized probes; `ValidationResult.details` for the import review (section D).
- `Paths.exports` as a write root, `Paths.module_state("modes")`, `Paths.staging_dir` (section D).
- Startup recovery and `ccctl recover` (section E); `ccctl query <module> <name>` for `captureable` and `drift` (section J).
- Page contract: `handlePayload(payload)`, `requestNavigate(moduleId, payload)`, payload routing from `CustomizationCenter.open` (section G).

Open items, none of them blocking the first milestones:

1. `Plan.metadata` passthrough into the journal. Modes stores `modeId`, `modeDigest`, and `before` there and reads them back from `ccctl transaction`. The sheet does not say whether the executor copies plan metadata into the journal verbatim. If it does not, modes keeps a sidecar under `Paths.module_state("modes")/plans/<planDigest>.json`, which is worse because it is not journaled.
2. `Paths.module_state(module_id)` is inferred from the sheet's `{module_state}/modes/last-applied.json`; the accessor name should be confirmed.

## 18. Assumptions about other module plans

The seven other plans were mid-rewrite. These are the shapes this plan relies on. Each owning module should confirm or correct them; a mismatch is an adapter change, not a core change.

| Module | Assumed |
|---|---|
| bar | Draft is the target `bar` subtree (`id`, `position`, `transparent`, `centerAnchor`, `layout`) with `baseRevision`. Applies in the first release through IPC plus the file route with `reloadConfig` (sheet section H). The file-route write's inverse is the tuple (restore backup, `ShellIpc("reloadConfig")`) and `reloadConfig`'s own inverse is `()`, so a rollback walk restores the file before the shell re-reads it. Status carries `bar` and `revision` covering `listShellConfig` and the file hash. |
| plugins | Draft `{"enabled": {id: bool}}` for non-bar ids only; one `setPluginEnabled` per id. Status rows carry `kinds`, `state.enabled`, `state.canDisable`. |
| monitors | Drafts `{"action": "activate", "profileId"}` and `{"action": "save-profile", "profile"}`. The activate plan is `WriteFileAtomic`, `HyprctlReload`, `TimedConfirmation(30)` in that order. Status carries `activeProfile.id` and a `verified \| overridden \| drifted` verdict. |
| themes | Draft `{"action": "activate", "slug", "preferredWallpaper"?}` for an existing built-in or user theme. Status carries `current.name` and `current.backgroundName`. The activate operation's inverse reactivates the previous slug and background. |
| keybindings | The complete managed document is the draft; status carries `managed.document`, `managed.blockState` from `managed_block.inspect`, and the revision fields the draft echoes. Its plan is `WriteFileAtomic`, `ReplaceManagedBlock`, `HyprctlReload`. |
| defaults | Draft `{"category", "optionId", "mode": "set", "install": false}` per category, agent excluded. Status carries `categories[c].current.optionId`, `categories[c].state`, and per-option availability. The setter's inverse is the setter with the previous option id. |
| keybindings and menu pages | `handlePayload({"addBinding": ...})` and `handlePayload({"addEntry": ...})` merge into their drafts (section 11). If they choose other keys, `shortcut.py` changes. |

Differences from the master plan's Module 8 text, absorbed by the sheet:

- Schema keys are module ids under `members`, not `changes.monitorProfile / theme / barPreset / plugins.enable|disable / keybindingPreset`. A boolean map cannot contradict itself the way two arrays can.
- "Presets" are inline copies (section 3.2), not references.
- Apply order is monitors, themes, plugins, bar, menu, keybindings, defaults (section 5.2).
- The last-applied record is `modes/last-applied.json`, written by the last operation of the same transaction, not `active-mode.json` written after commit.

## 19. Risks

| Risk | Effect | Handling |
|---|---|---|
| Bar file route needs the shell up and `shell.json` parseable | A bar member is unavailable while the shell is down or the file is broken. | The bar module's capabilities say so; the editor greys the section with that reason. Modes never writes `shell.json` itself. |
| Theme side effects outlive rollback | Retinted applications and hooks are not reversed by `omarchy-theme-set <previous>`. | Review discloses it; verify checks only authoritative theme state; residual risk. |
| Monitor restore inside a failed transaction runs without a second gate | A rollback seconds after confirmation restores the pre-transaction rules without asking. | Those rules were in effect a minute earlier. User-initiated rollback of a committed mode does get a fresh gate (section 6.5). |
| Member status shapes change during their rewrites | Adapters break. | Adapter tests validate `to_draft` output against each member's schema fixture; the adapters are the only place that changes. |
| Six `status()` calls per page load | Slow page. | `ctx.cache`; measure; move drift to `ccctl query modes drift` if needed. |
| Executor killed between `started` and `done` | Unknown whether the op applied. | Startup recovery treats a `started` file op as applied when the file differs from its backup; command ops are re-verified through the member's `verify` before the walk decides. |
| Two identical monitors without serial in the description | Drift and profiles cannot tell them apart. | Owned by the monitors module; modes reports its verdict verbatim. |

## 20. Decisions

- Modes are bundles of member drafts keyed by module id. No preset store.
- One executor, one flattened operation list, segments for revision and verify only. Reverse rollback falls out of the flattening.
- The last-applied record is written by the transaction itself as its last operation.
- Monitors first, gate inside the transaction, nothing after the gate until `ccctl confirm`.
- Rolling back a committed mode uses `ccctl rollback --reason user`; the executor's fresh gate and forward re-run on timeout keep the user on a confirmed layout.
- Import is inert; commit is a file-only transaction; apply is separate.
- Shortcuts summon the review page; nothing applies from a payload.
- Triggers wait until the fault-injection matrix and the live VM checks pass on manual modes.
