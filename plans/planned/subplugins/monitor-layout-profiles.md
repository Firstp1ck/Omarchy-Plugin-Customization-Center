# Monitor layout profiles

Status: planned, verified against Omarchy `71b0887c` and Hyprland 0.56.2 on 2026-08-28
Module id: `monitors`
Master plan section: `plans/planned/customization-center-masterplan.md`, Module 5

## 1. What this module does

Users save named monitor layouts (laptop only, desk, projector mirror, portrait second screen) and switch between them. The module reads the live topology from `hyprctl -j monitors all`, stores profiles as JSON, renders one generated Lua file with `hl.monitor` rules, loads it from a single managed block in `~/.config/hypr/monitors.lua`, reloads Hyprland, and asks the user on every output to keep the result. If nobody confirms within the deadline, a `systemd-run --user` timer runs `ccctl rollback`, so a black screen or a crashed overlay still recovers.

### In scope for the first release

- Read-only inventory of every output, including disabled and mirrored ones.
- Profiles stored under `~/.config/omarchy/customization-center/monitor-profiles/<id>.json`.
- Output identity by description, make, model, serial, with connector fallback and explicit ambiguity handling.
- Exact mode, logical position, scale, transform, enabled state, mirror target, bit depth, VRR.
- Static validation: overlap, invalid scale, unavailable mode, mirror graph, at least one root output, gaps as a warning.
- Generated Lua, managed loader block, `hyprctl reload`, timed confirmation, runtime verification, journal, rollback.
- Detection of handwritten `hl.monitor` calls and of Omarchy's monitor toggle files, with a clear explanation of which one wins.
- Read-only suggestions of which stored profiles fit the connected outputs.

### Refused in the first release

- Editing arbitrary Lua outside the managed block. Conflicts are reported; the user edits the file.
- Automatic profile switching on hotplug. Suggestions only.
- Replacing `omarchy-hyprland-monitor-internal`, `-internal-mirror`, `-clamshell`, `-scaling`, `-watch`, or `-modeless`. The module reads their state files and calls two of them for explicit override clearing.
- `GDK_SCALE`. `config/hypr/monitors.lua:16-22` treats it as one global value that only reaches restarted GTK apps. The page shows the current value as related, unmanaged state.
- Workspace rules, reserved areas, custom modelines, ICC, HDR, color management, brightness, text size.
- Modes for outputs that are not connected. Cached mode lists are shown as stale and never accepted as proof.
- Applying without the core `timed_confirmation` capability (a working `systemd-run --user`). The executor refuses with `capability_missing` before any write. See section 9.5.

## 2. Verified facts and where they come from

### Omarchy load order and files

| Fact | Source |
|---|---|
| `hyprland.lua` loads Omarchy defaults, then `hypr.monitors`, then `default.hypr.toggles` last | `config/hypr/hyprland.lua:14,19,26` |
| Shipped `monitors.lua` has one catch-all `hl.monitor({ output = "", mode = "preferred", position = "auto", scale = omarchy_monitor_scale })` plus `GDK_SCALE` | `config/hypr/monitors.lua:7-8,21-22` |
| Toggles directory is `$XDG_STATE_HOME/omarchy/toggles/hypr`, every `*.lua` there is `require`d in sorted order with `reload = true` | `default/hypr/toggles.lua:4-5,11-17`, `default/hypr/require_all.lua:16-37`, `default/hypr/paths.lua:20` |
| The bash tools hardcode `$HOME/.local/state/omarchy/toggles/hypr` regardless of `XDG_STATE_HOME` | `bin/omarchy-hyprland-monitor-internal:7`, `bin/omarchy-hyprland-monitor-clamshell:6`, comment at `default/hypr/disabled-input-device.lua:7-9` |
| `internal-monitor-disable.lua` content is exactly `hl.monitor({ output = "<internal>", disabled = true })`; writing it requires an active external output; the tool reloads | `bin/omarchy-hyprland-monitor-internal:38-46` |
| `internal-monitor-mirror.lua` content is exactly `hl.monitor({ output = "<external>", mode = "preferred", position = "auto", scale = 1, mirror = "<internal>" })`; the external output mirrors the internal one; the external is the first active non-internal output from plain `hyprctl monitors -j` | `bin/omarchy-hyprland-monitor-internal-mirror:12,37` |
| `internal-monitor-clamshell.lua` has the same disabled shape; written when the lid is closed and an external output is active; removed when the lid opens; the tool re-enables the panel with `hyprctl eval` using the scale it reads out of `monitors.lua` by regex | `bin/omarchy-hyprland-monitor-clamshell:237-241,173,84-108,248-252` |
| `omarchy-hyprland-monitor-watch` runs the clamshell sync on every monitor add or remove, then again after 1, 3 and 7 seconds, and every 2 seconds while docked; on `configreloaded` it runs modeless recovery, which may issue another `hyprctl reload` | `bin/omarchy-hyprland-monitor-watch:16-25,63-67,32-61,110-112` |
| Modeless means enabled with `width == 0 or height == 0` in `monitors all -j`; plain `monitors` omits mirrors | `bin/omarchy-hyprland-monitor-modeless:6-16` |
| `omarchy-hyprland-monitor-scaling` applies with `hyprctl eval` and then edits `monitors.lua` in place with `sed -i` when it still has the generic shape | `bin/omarchy-hyprland-monitor-scaling:97,102-112` |
| Clean scales are divisors of `gcd(w*120, h*120)` | `bin/omarchy-hyprland-monitor-scaling:55-67` |
| `omarchy-refresh-hyprland` replaces `monitors.lua` with the shipped default (backup as `.bak.<epoch>`); the quattro upgrade always copies it too | `bin/omarchy-refresh-hyprland:11`, `bin/omarchy-refresh-config:31-33`, `bin/omarchy-upgrade-to-quattro:1638` |
| Internal panel is any output named `eDP-*`, `LVDS-*`, `DSI-*` | `bin/omarchy-hyprland-monitor-laptop:5` |
| Omarchy imports the session environment into the user systemd manager at startup, so `systemd-run --user` units see `HYPRLAND_INSTANCE_SIGNATURE` | `default/hypr/autostart.lua:3` |
| Output names are only trusted when they match `^[A-Za-z0-9._-]+$` before being written into Lua | `bin/omarchy-hyprland-monitor-internal:33`, `test/shell.d/monitor-output-name-test.sh:63,79` |
| The user guide points people at `~/.config/hypr/monitors.lua` through Setup > Monitors in the Omarchy menu | `manual/33-monitors.md:5,41` |
| Shell plugins render one window per output with `Variants { model: Quickshell.screens }` | `shell/plugins/notifications/Service.qml:947-953`, `shell/plugins/bar/Bar.qml:952` |

### Hyprland monitor API

Wiki file: `/home/firstpick/.hyprwiki/content/Configuring/Basics/Monitors.md`.

| Fact | Lines |
|---|---|
| Rule shape `hl.monitor({ output, mode, position, scale, ... })` | 14-31 |
| Position is in logical pixels after scale and transform; 4K at scale 2 to the left of a 1080p means `1920x0` for the second, `1080x0` if rotated | 89-93 |
| Overlapping monitors produce a warning | 95-97 |
| A scale must divide the resolution into whole logical pixels; `1920x1080 / 1.5` OK, `/ 1.4` not | 99-103 |
| `output = ""` is the fallback rule when nothing else matches | 105-106 |
| Special modes `preferred`, `highres`, `highrr`, `maxwidth` | 108-113 |
| Special positions `auto`, `auto-right/left/up/down`, `auto-center-*` | 115-127 |
| `scale = "auto"` picks by PPI | 129-130 |
| `output = "desc:<description without (port)>"`; the JSON `description` field already lacks the port suffix on this host | 142-162 |
| `disabled = true` removes the output from the layout and moves its workspaces away; use the `dpms` dispatcher to only blank it | 177-189 |
| Field table with types and defaults, including `transform` 0-7, `bitdepth` 8 or 10, `vrr` integer, `mirror` is an output name | 211-234 |
| `mirror = "<output>"`; mirroring does not re-render, aspect mismatches stretch | 236-248 |
| Transform values 0-7 and their meaning | 332-342 |

Other wiki pages: `Variables.md:433` defines `vrr` as 0 off, 1 on, 2 fullscreen only, 3 fullscreen with video or game content. `Variables.md:441` documents `misc:disable_autoreload` (default false). `Start.md:23-24` says the config reloads on save and `hyprctl reload` reloads manually. `Advanced and Cool/Using-hyprctl.md:18-38,250,278-287` document `eval`, `dispatch`, `reload`, `configerrors`, and the `-j` flag.

The installed stub `/usr/share/hypr/stubs/hl.meta.lua:571-595` defines `HL.MonitorSpec` with `mirror? string`, `scale? string|number`, `transform? integer|boolean`, `vrr? integer|boolean`, `bitdepth? integer|boolean`, `output string`. Line 856 declares `monitor fun(spec: HL.MonitorSpec): nil`. There is no `hl.reload`; reload goes through `hyprctl reload`.

Two things are not documented anywhere local. Whether `mirror` accepts a `desc:` selector, and whether a later `hl.monitor` call for the same output replaces an earlier one. The design below avoids depending on either.

### Live runtime on the development host

- `hyprctl version`: 0.56.2. `hyprctl -j monitors all` and `hyprctl monitors all -j` both work and return the same JSON.
- JSON fields per output: `id`, `name`, `description`, `make`, `model`, `serial`, `width`, `height`, `physicalWidth`, `physicalHeight`, `refreshRate` (float, e.g. `143.97200`), `x`, `y`, `activeWorkspace`, `specialWorkspace`, `reserved` (array of 4), `scale` (float), `transform` (int), `focused`, `dpmsStatus`, `vrr` (bool), `solitary`, `activelyTearing`, `directScanoutTo`, `disabled`, `currentFormat`, `mirrorOf` (`"none"` or a connector), `availableModes` (strings such as `"2560x1440@143.97Hz"`, with exact duplicates present), `colorManagementPreset`, `sdrBrightness`, `sdrSaturation`, `sdrMinLuminance`, `sdrMaxLuminance`, `hardwareCursorsInUse`.
- Two identical ASUS VG27A panels are connected with distinct serials, so `description` is unique because it embeds the serial. This is the `two-identical-asus` fixture.
- `hyprctl -j configerrors` returns `[""]` when there are no errors. Blank entries must be filtered.
- `hyprctl getoption misc:disable_autoreload` is false.
- Auto-reload mechanism, read from `/proc/<Hyprland pid>/fdinfo`: one inotify instance with exactly one watch per loaded Lua file (10 files on this host, all `require`d from `hyprland.lua`), mask `0x8` = `IN_CLOSE_WRITE`, on the file inode. There is no directory watch. Consequences:
  - Writing a watched file in place (as `sed -i` in `omarchy-hyprland-monitor-scaling:103` or an editor does) triggers a reload.
  - Replacing a file by rename, which is what `WriteFileAtomic` does, creates a new inode and does not trigger the watch. Hyprland then only sees the change on the next explicit or unrelated reload. Whether Hyprland re-arms watches on the new inode after that reload was not tested.
  - A file loaded with `loadfile` or `dofile` rather than `require` may or may not be watched. Not tested, and the design does not rely on it.
- `systemd-run` is systemd 261, `systemctl --user is-system-running` prints `running`, and `systemctl --user show-environment` contains `HYPRLAND_INSTANCE_SIGNATURE`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`.
- `luac`, `lua`, `jq`, `socat` are installed.
- This host does not run Omarchy's Hyprland config (its `hyprland.lua` requires `sources_lua/*`). Every statement about Omarchy toggles and the watcher comes from reading the scripts, not from observing them.

## 3. Ordering of write, reload and confirmation

The question that decides the apply sequence is whether a write can reload Hyprland before a failsafe exists. With rename-based writes it cannot on this Hyprland version (section 2), but the plan does not bet on that. The core executor arms the backstop before the first operation, so ordering inside the plan no longer matters for safety.

What the executor does for a plan that contains a `TimedConfirmation` (contract section A):

1. Creates the transaction record in state `applying`, then arms `omarchy-cc-confirm-<txid>` with `systemd-run --user --on-active=<B>s` running `ccctl rollback <txid> --reason timeout`, where `B = sum(timeout_s of every operation before the gate) + 30 + 5`. For the full monitors plan below that is `1 + 1 + 2 + 2 + 2 + 2 + 10 + 5 = 25`, so `B = 60` seconds. This happens before backups and before any write. A crash at any later point ends in rollback when the timer fires.
2. Runs the operations up to the gate.
3. At the gate, calls `verify` with the partial `results` (pre-confirmation check). A `fail` result goes straight to rollback without waiting.
4. Sets `awaiting_confirmation`, `deadline = now + 30 s`, and polls for the token file every 200 ms while holding the lock.
5. On confirmation, stops the timer and runs the operations after the gate; on timeout, runs the rollback walk.
6. At the end, calls `verify` again with all results and commits.

The monitors plan for `activate`, in order:

| # | Operation | timeout_s | Behaviour change |
|---|---|---|---|
| 1 | `EnsureDirectory(generated dir)` | 1 | none |
| 2 | `EnsureDirectory(profiles dir)` | 1 | none |
| 3 | `WriteFileAtomic(profile json)` when the draft carries an edited profile | 2 | none |
| 4 | `WriteFileAtomic(generated no-op)` only when the generated file is absent | 2 | none |
| 5 | `ReplaceManagedBlock(monitors.lua, "MONITORS", 1, loader body)` only when the loader is absent or modified | 2 | none until reload |
| 6 | `WriteFileAtomic(generated rules with confirmBy guard)` | 2 | none until reload |
| 7 | `HyprctlReload()` | 10 | the layout changes here |
| 8 | `RunCommand(["hyprctl", "dispatch", "hl.dsp.dpms({ action = \"enable\" })"], 5)` wakes outputs that DPMS turned off; inverse is the same command; form from `bin/omarchy-hyprland-monitor-internal:13` | 5 | wakes screens |
| 9 | `TimedConfirmation(30)` | | the dialog on every output |
| 10 | `WriteFileAtomic(generated rules without the guard)` | 2 | none (same rules) |
| 11 | `WriteFileAtomic(active pointer)` | 2 | none |

Operations 1 to 5 are neutral, so their inverses are harmless even when a timeout rollback runs them. Operation 10 strips the reboot guard (section 9.1) after the user confirmed. Operation 11 is a normal post-gate write; `verify` at the gate must not expect it.

Thirty seconds for the gate, because the visible countdown only starts after reload and stabilization polling (up to about nine seconds) have finished, so the user sees the full thirty. The value is one gate parameter, later user-settable in `settings.json`.

## 4. Files and paths

| Purpose | Path |
|---|---|
| Profiles | `$XDG_CONFIG_HOME/omarchy/customization-center/monitor-profiles/<id>.json` |
| Generated rules | `$XDG_CONFIG_HOME/omarchy/customization-center/generated/monitors.lua` |
| Loader host | `$XDG_CONFIG_HOME/hypr/monitors.lua` |
| Active profile pointer | `$XDG_STATE_HOME/omarchy/customization-center/active-monitor-profile.json` |
| Transactions and backups | `$XDG_STATE_HOME/omarchy/customization-center/transactions/<txid>/`, `.../backups/` (core-owned) |
| Mode cache for disconnected outputs | `$XDG_CACHE_HOME/omarchy/customization-center/monitor-inventory.json` |
| Omarchy toggles (read, and cleared only through Omarchy commands) | `$HOME/.local/state/omarchy/toggles/hypr/internal-monitor-{disable,mirror,clamshell}.lua` |

`XDG_CONFIG_HOME` and `XDG_STATE_HOME` resolve as in `default/hypr/paths.lua:9-15` (empty counts as unset). The toggles path uses `$HOME/.local/state` on purpose, matching the bash tools that write there.

Repository layout for the module:

```text
modules/monitors/
├── module.json
├── Page.qml
├── components/
│   ├── OutputCard.qml
│   ├── LayoutCanvas.qml
│   ├── ModePicker.qml
│   ├── ProfileList.qml
│   └── OverrideBanner.qml
├── backend/
│   ├── __init__.py        # exports MODULE
│   ├── inventory.py       # hyprctl parsing and normalization
│   ├── identity.py        # matching
│   ├── geometry.py        # logical rectangles, overlap, gaps, scale suggestions
│   ├── profile.py         # load, validate, save
│   ├── lua_render.py      # generated file
│   ├── ownership.py       # handwritten rule scanner, toggle inventory
│   └── planner.py         # status, validate, plan, verify
├── schemas/
│   ├── monitor-profile-v1.json
│   ├── monitors-draft-v1.json
│   └── active-monitor-profile-v1.json
└── tests/
```

`module.json`:

```json
{
  "id": "monitors",
  "title": "Monitors",
  "icon": "󰍹",
  "navOrder": 50,
  "page": "Page.qml",
  "backend": "modules.monitors.backend",
  "schemas": ["schemas/monitor-profile-v1.json", "schemas/monitors-draft-v1.json", "schemas/active-monitor-profile-v1.json"],
  "coreServices": ["hyprctl", "managed_block", "lua", "atomic", "journal", "operations.TimedConfirmation"]
}
```

## 5. Profile schema

`modules/monitors/schemas/monitor-profile-v1.json`. One file per profile, canonical JSON (sorted keys, two-space indent, trailing newline), UTF-8.

| Field | Type | Rules |
|---|---|---|
| `version` | integer | must be `1` |
| `id` | string | `^[a-z0-9][a-z0-9-]{0,63}$`; equals the file stem; never derived from `name` at load time |
| `name` | string | 1 to 80 characters, any printable text |
| `description` | string | 0 to 500 characters, default `""` |
| `outputs` | array of `OutputRule` | 1 to 16 entries; `id` unique within the profile |
| `match.required` | array of string | output ids that must be connected for the profile to apply; default all output ids with `whenMissing: "block"` |
| `match.allowExtra` | boolean | `true`: connected outputs not in the profile are allowed and use `extraOutputs`; `false`: any extra output is a blocker |
| `extraOutputs` | object or null | `null`: no catch-all is generated, so Omarchy's shipped catch-all in `monitors.lua` applies. Object: `{ "mode": "preferred"\|"highres"\|"highrr"\|"maxwidth", "position": "auto"\|"auto-right"\|"auto-left"\|"auto-up"\|"auto-down", "scale": "auto" \| integer scale120 }`, rendered as one `output = ""` rule |
| `createdAt`, `updatedAt` | string | RFC 3339 UTC |

`OutputRule`:

| Field | Type | Rules |
|---|---|---|
| `id` | string | `^[a-z0-9][a-z0-9-]{0,31}$`; profile-local; the UI generates it from the model name and disambiguates with `-2`, `-3` |
| `label` | string | 1 to 60 characters; shown on cards; default `make model` |
| `identity.description` | string | value of the JSON `description` field at capture time, may be `""` |
| `identity.make`, `identity.model`, `identity.serial` | string | as reported, may be `""` |
| `identity.connector` | string | the connector at capture time, `^[A-Za-z0-9._-]+$` |
| `connectorPolicy` | enum | `"never"`, `"if-no-fingerprint"`, `"confirm"`; default `"confirm"`. Governs when the connector alone may match. See 7.2 |
| `enabled` | boolean | `false` renders `disabled = true` and nothing else |
| `mode` | object | `{ "width": int > 0, "height": int > 0, "refreshMilliHz": int > 0 }`; exact modes only in version 1 |
| `position` | object | `{ "x": int, "y": int }` in logical pixels; required when `enabled` and `mirrorOf` is null; ignored otherwise |
| `scale120` | integer | scale in 1/120 units, 30 to 960 inclusive (0.25 to 8.0). A product limit, not a Hyprland limit. Stored as an integer so JSON never carries a binary float |
| `transform` | integer | 0 to 7 |
| `mirrorOf` | string or null | id of another output in the profile |
| `bitDepth` | integer or null | `8`, `10`, or `null` meaning do not emit the field |
| `vrr` | integer or null | `0` to `3` or `null` meaning do not emit the field |
| `whenMissing` | enum | `"block"`: the profile cannot apply without this output; `"skip"`: emit no rule for it |

Unknown top-level or per-output fields are rejected with `validation_failed` and the JSON pointer. A `version` other than 1 is rejected with `unsupported_config` and the message names the file. No silent migration in version 1.

Active profile pointer, `active-monitor-profile-v1.json`:

```json
{
  "version": 1,
  "profileId": "desk",
  "profileDigest": "sha256:...",
  "transactionId": "uuid",
  "appliedAt": "RFC3339",
  "assignments": { "asus-left": "DP-1", "asus-right": "DP-2" }
}
```

`status()` reports the profile as active only when the journal entry for `transactionId` is `committed`; anything else means no active profile even if the file exists. The pointer is written after the gate, so it normally does not exist while a transaction is `awaiting_confirmation`; `status()` reports that state from `ccctl transaction current` instead.

Draft schema, `monitors-draft-v1.json`. The draft is what the page hands to `validate`, `plan`, and `apply`. The `activate` shape is also what the desktop modes module builds from its `members.monitors.profileId` (contract section I), so it is stated once here:

```json
{
  "version": 1,
  "action": "activate",
  "profileId": "desk",
  "profile": null,
  "assignments": { "asus-left": "DP-1" },
  "acknowledgedWarnings": ["monitors_layout_gap"]
}
```

| Field | Type | Meaning |
|---|---|---|
| `version` | integer | `1` |
| `action` | enum | `"activate"`, `"save-profile"`, `"delete-profile"`, `"clear-override"`, `"install-loader"` |
| `profileId` | string | required for `activate` and `delete-profile`; the stored profile to use |
| `profile` | `MonitorProfile` or null | required for `save-profile`; optional for `activate`, where it is the edited copy the page wants saved and activated in the same transaction (`profile.id` must equal `profileId`); null means activate the stored file as-is |
| `assignments` | object | optional `{ outputId: connector }` overrides that resolve an ambiguity or confirm a connector-only match |
| `override` | enum | for `clear-override`: `"internal-monitor-disable"` or `"internal-monitor-mirror"` |
| `acknowledgedWarnings` | array of string | warning codes the user accepted in the review step; informational |

Modes send `{ "action": "activate", "profileId": "<id>" }` and nothing else. The monitors planner resolves everything from the stored file and the current inventory.

## 6. Inventory

`inventory.read(ctx)` runs `["hyprctl", "-j", "monitors", "all"]` with a 3 second timeout and a 1 MiB capture cap through `ctx.commands`. Failures map to `runtime_unavailable` (non-zero exit, timeout, socket missing) or `malformed_output` (not a JSON array, missing or mistyped fields). The raw text is kept in diagnostics, truncated to 8 KiB.

Normalized output object:

```text
Output
  connector: str           # "name"
  description: str
  make: str
  model: str
  serial: str
  internal: bool           # connector matches ^(eDP|LVDS|DSI)-
  disabled: bool
  focused: bool
  dpms: bool
  mirrorOf: str | None     # None when "none"
  width: int               # physical pixels of the current mode, 0 when modeless
  height: int
  refreshMilliHz: int      # round(refreshRate * 1000)
  x: int
  y: int
  scale120: int            # round(scale * 120)
  transform: int
  modes: list[Mode]        # deduplicated by (width, height, refreshMilliHz), first occurrence kept
  rawModes: list[str]      # as reported, for diagnostics
  vrrActive: bool
```

Mode grammar, anchored: `^(\d+)x(\d+)@(\d+(?:\.\d+)?)(?:Hz)?$`. Refresh becomes `round(float * 1000)`. Anything that does not match is dropped from `modes` and listed in a `monitors_unparsed_mode` warning with the raw token.

Every `status()` also writes the cache file with `{ observedAt, outputs: [{ identity, modes }] }` for outputs that were seen. The cache lets the mode picker show a disconnected output's last known modes, marked stale. It is never used to validate an apply.

## 7. Identity and matching

### 7.1 Why description first

Connector names move. A dock swap turns `DP-2` into `DP-3` on the same panel, and two ports on the same GPU can renumber after a kernel update. The description on this host is `ASUSTek COMPUTER INC VG27A R9LMQS087695`, which embeds the serial and identifies the exact panel. So the rule is `desc:` first, connector only as a fallback that the user agreed to.

### 7.2 Algorithm

Inputs: profile outputs `P`, connected outputs `C`, optional `assignments` from the draft.

```text
def fingerprint(o):            # o is a profile identity or a connected output
    return (o.make, o.model, o.serial, o.description)

def score(p, c, assignments):
    if assignments.get(p.id) == c.connector:
        return 1000                                  # explicit user choice wins
    fp_p, fp_c = fingerprint(p.identity), fingerprint(c)
    s = 0
    if p.identity.serial and (p.identity.make, p.identity.model, p.identity.serial) == (c.make, c.model, c.serial):
        s = 100
    elif p.identity.description and p.identity.description == c.description:
        s = 80
    elif p.identity.make and p.identity.model and (p.identity.make, p.identity.model) == (c.make, c.model) \
         and not p.identity.serial and not c.serial and not p.identity.description and not c.description:
        s = 50
    if s > 0:
        if p.identity.connector == c.connector:
            s += 5                                   # tie-breaker only
        return s
    # no fingerprint agreement; connector fallback
    if p.identity.connector != c.connector:
        return 0
    if p.connectorPolicy == "never":
        return 0
    if p.connectorPolicy == "if-no-fingerprint":
        return 20 if fp_c == ("", "", "", "") else 0
    return 0                                         # "confirm": only via assignments (1000 above)

def match(P, C, assignments):
    edges = {(p.id, c.connector): score(p, c, assignments) for p in P for c in C if score(p, c, assignments) > 0}
    best, best_total = None, -1
    ties = []
    for A in one_to_one_assignments(P, C, edges):    # exhaustive with pruning; |P|, |C| <= 16, edges are sparse
        total = sum(edges[e] for e in A)
        if total > best_total:
            best, best_total, ties = A, total, []
        elif total == best_total:
            ties.append(A)
    result = MatchResult(map={}, unmatched=[], ambiguous=[], extra=[])
    if best is None:
        result.unmatched = [p.id for p in P]
        return result
    for p in P:
        c = best.get(p.id)
        if c is None:
            result.unmatched.append(p.id)
            continue
        if any(t.get(p.id) != c for t in ties):
            result.ambiguous.append((p.id, sorted({t.get(p.id) for t in ties + [best]} - {None})))
        else:
            result.map[p.id] = c
    result.extra = [c.connector for c in C if c.connector not in best.values()]
    return result
```

Rules that follow from the result:

- Any id in `ambiguous` whose `whenMissing` is `block` is the blocker `monitors_ambiguous_identity`, with the candidate connectors listed. The page then offers the assignment picker, which writes `draft.assignments`.
- Any id in `unmatched` with `whenMissing: "block"` is `monitors_output_missing`. With `"skip"` the output produces no rule and a warning.
- A connector in `extra` while `match.allowExtra` is false is `monitors_unexpected_output`.
- Two identical panels with identical descriptions and serials (rare, but some cheap displays report the same serial) produce a tie and therefore an ambiguity. The module refuses to guess which one is left. The user assigns them once; the assignment is saved in the active pointer and reused as a hint on the next status (an `assignments` hint only raises the connector tie-breaker to 5, it does not become a 1000 edge without the user).

### 7.3 Selector emitted into Lua

For a matched output `c`:

1. If `c.description` is non-empty and no other connected output has a description that equals it or contains it as a substring, emit `output = "desc:" .. description`. The substring check exists because hyprlang matched `desc:` by substring and the Lua behaviour is not documented; a prefix collision would double-match.
2. Otherwise emit the connector. The connector must match `^[A-Za-z0-9._-]+$`; anything else is the blocker `monitors_unsupported_output_name` (same policy as `bin/omarchy-hyprland-monitor-internal:33`).
3. A mirror target is always the connector, never `desc:`. The wiki only shows connector names for `mirror` (`Monitors.md:241-242`), and `bin/omarchy-hyprland-monitor-internal-mirror:37` does the same. Revisit once a disposable session proves `desc:` works there.

## 8. Geometry, validation, and warnings

### 8.1 Logical rectangle

```text
def logical(rule):                      # enabled, not a mirror
    W, H = rule.mode.width, rule.mode.height
    TW, TH = (H, W) if rule.transform in (1, 3, 5, 7) else (W, H)
    K = rule.scale120
    if (TW * 120) % K or (TH * 120) % K:
        raise InvalidScale(nearest_valid(TW, TH, K))
    return Rect(x=rule.position.x, y=rule.position.y, w=TW * 120 // K, h=TH * 120 // K)

def nearest_valid(TW, TH, K):
    g = gcd(TW * 120, TH * 120)         # same arithmetic as omarchy-hyprland-monitor-scaling:62
    lower = max(k for k in range(30, K) if g % k == 0) if any(g % k == 0 for k in range(30, K)) else None
    upper = min(k for k in range(K + 1, 961) if g % k == 0) if any(g % k == 0 for k in range(K + 1, 961)) else None
    return lower, upper
```

Rectangles are half-open. Negative coordinates are valid and are stored as-is; the canvas translates for drawing only.

### 8.2 Overlap

```text
for a, b in combinations(roots, 2):
    if max(a.x, b.x) < min(a.x + a.w, b.x + b.w) and max(a.y, b.y) < min(a.y + a.h, b.y + b.h):
        blocker("monitors_overlap", a.id, b.id, intersection)
```

Touching edges are not overlap.

### 8.3 Gaps

Hyprland allows gaps, but the cursor cannot cross one and users usually did not mean it. Gaps are a warning, `monitors_layout_gap`, listing the islands.

```text
adjacent(a, b):
    vertical_touch = (a.x + a.w == b.x or b.x + b.w == a.x) and min(a.y + a.h, b.y + b.h) - max(a.y, b.y) > 0
    horizontal_touch = (a.y + a.h == b.y or b.y + b.h == a.y) and min(a.x + a.w, b.x + b.w) - max(a.x, b.x) > 0
    return vertical_touch or horizontal_touch
components = connected components of roots under adjacent
if len(components) > 1: warning("monitors_layout_gap", components)
```

The canvas offers a snap action that moves the selected island to touch the nearest root; it only edits the draft.

### 8.4 Blockers

| Code | Condition |
|---|---|
| `monitors_no_root` | no output is enabled and non-mirrored after applying `whenMissing: "skip"` |
| `monitors_overlap` | 8.2 |
| `monitors_invalid_scale` | 8.1; the message carries the nearest lower and upper valid `scale120` |
| `monitors_mode_unavailable` | matched connected output does not report the exact `(width, height)` with a refresh within 100 milliHz |
| `monitors_output_missing` | 7.2 |
| `monitors_ambiguous_identity` | 7.2 |
| `monitors_unexpected_output` | 7.2 |
| `monitors_mirror_invalid` | `mirrorOf` names a missing id, a disabled output, an output that is itself a mirror, or itself; or a cycle |
| `monitors_unsupported_output_name` | 7.3 |
| `monitors_handwritten_rule_conflict` | section 9.3 |
| `monitors_toggle_override` | section 9.4 |
| `managed_block_collision` | `managed_block.inspect` reports `duplicate`, `unterminated`, `reversed`, or `nested` |
| `capability_missing` | core refuses the apply because `timed_confirmation` is unavailable; section 9.5 |
| `validation_failed` | schema violations, with JSON pointer |

### 8.5 Warnings

| Code | Condition |
|---|---|
| `monitors_layout_gap` | 8.3 |
| `monitors_mirror_aspect` | mirror source and target aspect ratios differ by more than 1 percent |
| `monitors_mirror_mode_differs` | mirror mode differs from target mode |
| `monitors_output_skipped` | a `whenMissing: "skip"` output is absent |
| `monitors_stale_modes` | mode list for a disconnected output came from the cache |
| `monitors_extra_uses_catchall` | extra outputs will use Omarchy's catch-all from `monitors.lua` (when `extraOutputs` is null) |
| `monitors_clamshell_override` | `internal-monitor-clamshell.lua` exists and disables an output this profile enables; the effective state will differ until the lid opens |
| `monitors_runtime_drift` | runtime differs from what the files say (typically after `omarchy-hyprland-monitor-scaling`); a reload discards runtime-only rules |
| `monitors_gdk_scale_mismatch` | the nearest integer of the focused output's scale differs from `omarchy_gdk_scale` in `monitors.lua` |
| `monitors_unparsed_mode` | section 6 |

## 9. Managed Lua

### 9.1 Generated file

Deterministic for the same profile and assignment. Header, then rules in this order: roots sorted by `(x, y, id)`, mirrors sorted by id, disabled outputs sorted by id, the catch-all last if `extraOutputs` is set.

```lua
-- Generated by Omarchy Customization Center. Do not edit; the next apply overwrites this file.
-- profile: desk
-- profileDigest: sha256:0f3c...
-- confirmBy: 1756380000
if os.time() > 1756380000 then return end
hl.monitor({ output = "desc:ASUSTek COMPUTER INC VG27A R9LMQS087695", mode = "2560x1440@143.972", position = "0x0", scale = 1, transform = 0 })
hl.monitor({ output = "desc:ASUSTek COMPUTER INC VG27A T4LMQS096150", mode = "2560x1440@143.972", position = "2560x0", scale = 1, transform = 0 })
```

The `confirmBy` guard is what makes a reboot during the countdown safe. Its value is plan time plus 180 seconds, which comfortably covers the backstop budget. If the machine restarts before confirmation, the chunk returns before defining any rule once that time has passed, and Omarchy's catch-all applies. Operation 10 in section 3, a post-gate `WriteFileAtomic`, rewrites the file without the two guard lines right after confirmation, so a committed file has no guard. If power is lost between confirmation and that write, the next boot falls back to the catch-all after 180 seconds and the page shows the profile as drifted; the user activates it again.

Rendering rules per output:

- `output = <selector>` from 7.3.
- Enabled root: `mode = "<W>x<H>@<refresh>"`, `position = "<x>x<y>"`, `scale = <s>`, `transform = <t>`, then `bitdepth = <n>` if not null, `vrr = <n>` if not null.
- Mirror: same as root but `position = "0x0"` and `mirror = "<target connector>"`. Hyprland ignores the position of a mirror, and the wiki example includes one (`Monitors.md:241`).
- Disabled: `output` and `disabled = true` only.
- Catch-all: `hl.monitor({ output = "", mode = "<mode>", position = "<position>", scale = <"auto" or number> })`.
- Refresh: `refreshMilliHz / 1000` formatted with up to three decimals, trailing zeros stripped (`60000` becomes `60`, `143972` becomes `143.972`). Hyprland picks the closest advertised refresh.
- Scale: `scale120 / 120` formatted with up to six decimals, trailing zeros stripped (`120` becomes `1`, `150` becomes `1.25`, `200` becomes `1.666667`). Verification tolerates one 1/240 unit.
- Position: `"%dx%d"`, so `-1920x0` and `0x-1080` are valid.

Lua string escaping (`core/lua.py`, `lua_string(s)`): wrap in double quotes; `\` becomes `\\`, `"` becomes `\"`, LF `\n`, CR `\r`, TAB `\t`; every other byte below 0x20 and byte 0x7F becomes `\ddd` with exactly three decimal digits; bytes 0x80 and above are emitted raw (the file is UTF-8 and Lua strings are byte strings). NUL is rejected earlier with `validation_failed`. Never use `%q`-style shortcuts or string concatenation of raw input.

No-op generated file (bootstrap and after deleting the active profile):

```lua
-- Generated by Omarchy Customization Center. No monitor profile is active.
```

Before writing, the planner runs `["luac", "-p", <staged path>]` with a 5 second timeout when `luac` exists. A failure is a bug in the renderer, reported as `unsupported_config` with the luac message. When `luac` is missing, the plan proceeds with the warning `monitors_no_lua_check`; a syntax error would still be caught by `configerrors` and rolled back.

### 9.2 Loader block

Markers, chosen to match the keybindings module's `v1` suffix so that the core `managed_block` helper treats both modules the same:

```lua
-- BEGIN OMARCHY CUSTOMIZATION CENTER MONITORS v1
-- Loads the monitor profile applied by the Customization Center. Change profiles there, not here.
do
  local config_home = os.getenv("XDG_CONFIG_HOME")
  if config_home == nil or config_home == "" then
    config_home = (os.getenv("HOME") or "") .. "/.config"
  end
  local chunk = loadfile(config_home .. "/omarchy/customization-center/generated/monitors.lua")
  if chunk then
    chunk()
  end
end
-- END OMARCHY CUSTOMIZATION CENTER MONITORS v1
```

`loadfile` instead of `dofile`, because a missing generated file is a nil chunk, not a config error, so a half-installed state cannot break the boot. The `do ... end` scope keeps `config_home` and `chunk` local.

`ReplaceManagedBlock` appends the block at the end of `monitors.lua`, preceded by exactly one blank line if the file does not already end with one. It replaces bytes between and including the markers when exactly one pair exists. Bytes outside the block are asserted identical after the write (core helper behaviour, tested in core and again in this module's tests with the shipped file as fixture).

Detection states reported by `status().loader`:

| State | Meaning | Offered action |
|---|---|---|
| `absent` | `managed_block.inspect` state `absent`; the shipped file or a handwritten one | install the loader as part of the next activate, or standalone `action: "install-loader"` |
| `present` | state `present` and the body digest equals the rendered body | none |
| `present-modified` | state `present`, body differs | activate rewrites it; the review shows the diff |
| `duplicate`, `unterminated`, `reversed`, `nested` | as reported by `managed_block.inspect` with `beginLine` and `endLine` | blocker `managed_block_collision`; the user fixes the file |
| `host-missing` | `monitors.lua` does not exist | activate creates it with only the block; warning that the shipped catch-all is absent |

Markers come from `managed_block.py` with name `MONITORS` and version 1. A later "remove integration" maintenance action would use `ReplaceManagedBlock(body=None)`; the first release does not offer it.

`omarchy-refresh-hyprland` and the quattro upgrade replace `monitors.lua` and drop the block. The next `status()` reports `absent` while `active-monitor-profile.json` names a profile; the page shows "Loader removed by an Omarchy refresh" with a one-click reinstall (`install-loader`), which is a neutral change and needs no confirmation dialog because it changes nothing until the next reload, and the reload is part of the same small plan with verification against the active profile.

### 9.3 Handwritten rules in monitors.lua

`ownership.scan(text)` removes the managed block, strips comments with a small lexer that understands `--` line comments, `--[[ ]]` and `--[==[ ]==]` block comments, and single, double and long-bracket strings, then finds every `hl.monitor(` call outside the block.

Classification of each call:

| Shape | Result |
|---|---|
| `hl.monitor({ output = "", ... })` where the table has only literal `mode`, `position`, `scale` values or the identifier `omarchy_monitor_scale` | baseline catch-all; reported as `catchAll` with its scale expression; not a conflict |
| `output = "<literal>"` where the literal, or `desc:<literal>`, matches a connected output or any profile output identity | blocker `monitors_handwritten_rule_conflict` with line number and the call text |
| `output = "<literal>"` matching nothing connected and nothing in the profile | warning `monitors_handwritten_rule_other` (for example the phantom Apple XDR output in `manual/33-monitors.md:53`) |
| `output` is an identifier, expression, or absent; the argument is not a table literal; `hl.monitor` is aliased or wrapped | blocker `unsupported_config` with line number |
| `require`, `dofile`, `loadfile` outside the block | blocker `unsupported_config`; the module cannot see what that code does to monitors |
| Lexer failure (unterminated string or comment) | blocker `unsupported_config` |

The conflict resolution flow is manual by design. The page shows the offending line, a "Copy line" button, and instructions to open `~/.config/hypr/monitors.lua` through Setup > Monitors and remove or comment the call, then "Rescan". The module never edits or deletes handwritten rules. Regex extraction is not proof of ownership; `test/shell.d/monitor-clamshell-scale-test.sh:87-208` lists valid shapes (locals, expressions, semicolons, inline block comments, nested tables) that a takeover would misread.

Why block instead of assuming that the later rule wins? The precedence between two `hl.monitor` calls for the same output is not documented for the Lua API, and even if it were, a user who wrote a rule by hand expects it to work.

### 9.4 Omarchy toggle files

`ownership.toggles()` reads the three known files. Each is classified as `absent`, `known` (content equals the exact shape from the bash tool, with the connector extracted), or `unknown` (any other content, reported as `unsupported_config` with the path). Effects on planning:

| Toggle present | Profile wants | Result |
|---|---|---|
| `internal-monitor-disable.lua` for connector X | X enabled or mirrored | blocker `monitors_toggle_override`; the page offers "Enable laptop display", which runs `clear-override` |
| `internal-monitor-disable.lua` for X | X disabled or absent | no conflict; the expected state has X disabled |
| `internal-monitor-mirror.lua` (external E mirrors internal I) | anything other than E mirroring I with `preferred`, `auto`, scale 1 | blocker `monitors_toggle_override`; the page offers "Stop mirroring", which runs `clear-override` |
| `internal-monitor-clamshell.lua` for X | X enabled | warning `monitors_clamshell_override`; expected state has X disabled; the page says "overridden by clamshell (lid closed)" |
| any `unknown` content | anything | blocker `unsupported_config` |

`clear-override` is its own plan, never part of the profile transaction:

- `internal-monitor-disable`: `RunCommand(["omarchy-hyprland-monitor-internal", "on"], timeout_s=10)`; inverse `RunCommand(["omarchy-hyprland-monitor-internal", "off"], timeout_s=10)`. The forward removes the flag, reloads, and wakes outputs (`bin/omarchy-hyprland-monitor-internal:16-23`). The inverse refuses when no external output is active (`:38-41`), which is the right behaviour.
- `internal-monitor-mirror`: `RunCommand(["omarchy-hyprland-monitor-internal-mirror", "off"])`; inverse `RunCommand([..., "on"])`.

Verification for `clear-override` re-reads the toggle directory and the topology. These commands send notifications and reload on their own; the review step says so.

The clamshell flag is never cleared by the module. It is hardware policy owned by `omarchy-hyprland-monitor-watch`, which would rewrite it within seconds.

### 9.5 Failsafe capability

Core owns the `timed_confirmation` capability (`systemd-run` on `PATH`, user manager `running` or `degraded`, `ccctl` able to name its own absolute path). The module adds two checks of its own to `capabilities()`:

1. `hyprctl -j monitors all` fails or is malformed: `runtime_unavailable`.
2. `HYPRLAND_INSTANCE_SIGNATURE` or `XDG_RUNTIME_DIR` missing from the backend's own environment: `runtime_unavailable`, reason "not inside a Hyprland session".

`capabilities().apply` is false when either check or the core capability fails. The page keeps profile editing and saving enabled and shows the reason on the Apply button. If the page sends an `activate` anyway, the executor refuses with `capability_missing` before any write.

## 10. Plan, apply, verify, rollback

### 10.1 status()

Returns:

```json
{
  "revision": "sha256:...",
  "inventory": { "outputs": [ ... ], "observedAt": "RFC3339", "configErrors": [] },
  "profiles": [ { "id", "name", "updatedAt", "fit": { "state": "applicable|missing-outputs|ambiguous|extra-outputs", "matched": {}, "problems": [] } } ],
  "active": { "profileId": "desk", "state": "verified|awaiting-confirmation|drifted|overridden|none", "transactionId": "...", "details": [] },
  "loader": { "state": "present", "path": "~/.config/hypr/monitors.lua" },
  "handwritten": { "catchAll": { "line": 8, "scale": "omarchy_monitor_scale" }, "conflicts": [], "others": [] },
  "toggles": { "internal-monitor-disable": null, "internal-monitor-mirror": null, "internal-monitor-clamshell": null },
  "related": { "gdkScale": 2, "monitorScaleLocal": "auto" },
  "capabilities": { "apply": true, "reasons": [] }
}
```

`revision` is the SHA-256 over: bytes of `monitors.lua` (or a sentinel for absent), bytes of the generated file, bytes of the active pointer, the sorted list of toggle file names and bytes, and the canonical JSON of the normalized inventory. A hotplug therefore changes the revision, and an apply planned before it fails with `stale_revision`, which is what should happen.

`active.state`:

- `verified`: the committed profile's expected topology equals the current one.
- `awaiting-confirmation`: the transaction that wrote the pointer is in journal state `awaiting_confirmation`.
- `overridden`: the difference is fully explained by a known toggle.
- `drifted`: any other difference; the page offers Reapply and Update profile from runtime.
- `none`: no committed profile.

### 10.2 plan(draft)

For `activate`, in order, under the executor's lock:

1. Validate the profile (schema, then section 8 rules that need no runtime).
2. Match (7.2) with `draft.assignments`. Collect blockers.
3. Check modes against the matched connected outputs.
4. Scan `monitors.lua` (9.3) and toggles (9.4).
5. Check capabilities (9.5).
6. Compute expected topology after apply (per matched output: connector, disabled, width, height, refreshMilliHz, x, y, scale120, transform, mirrorOf), applying clamshell overrides.
7. Render the generated file twice, once with `confirmBy = now + 180 s` and once without the guard, and run `luac -p` on both.
8. Return the operation list from section 3, each with a one-line summary, plus the diff of the generated file and of the loader block, the resolved map, the expected topology, and warnings.

`save-profile` is one `WriteFileAtomic` to the profile path, inverse restores the backup or removes the file if it did not exist. `delete-profile` is one `RemoveFile` (inverse restores the backup); it is refused with `monitors_profile_active` while the profile is active or a transaction for it is in flight. `install-loader` is steps 1 to 3 of section 3 plus `HyprctlReload` and verification against the active profile if any.

### 10.3 verify()

The executor calls `verify(ctx, plan, results)` twice for an `activate` plan. `results` maps operation ids to their outcomes; operations that have not run are absent.

At the gate (pre-confirmation check), operations 1 to 8 are present, 10 and 11 are absent:

1. Config errors are already checked by `HyprctlReload` itself, which diffs `hyprctl -j configerrors` against the plan-time baseline and fails the operation on new entries (blank entries such as `[""]` are dropped by core). `verify` does not repeat this.
2. Poll `hyprctl -j monitors all` every 500 ms for up to 8 seconds through `ctx.commands` and `ctx.clock`. Normalize each sample. Success requires two consecutive samples that both equal the expected topology from 10.2 step 6 on these fields: connector present, `disabled`, `width`, `height`, `refreshMilliHz` within 100, `x`, `y`, `scale120` within 1, `transform`, `mirrorOf`.
3. At least one enabled non-mirror output has `width > 0 and height > 0`. Anything else is modeless and fails (`bin/omarchy-hyprland-monitor-modeless:15` uses the same test).
4. Return `ok` with the final sample, or `fail` with code `monitors_verification_failed` and the last sample. `fail` makes the executor roll back without opening the dialog.

At the end (all results present): repeat step 2 with a 3 second budget (the layout must not have changed while the dialog was open), then check that the generated file on disk has no `confirmBy` line and that the active pointer parses and names `profileId` and the transaction id. Any mismatch is `monitors_verification_failed`.

Polling to stability matters because `omarchy-hyprland-monitor-watch:110-112` reacts to `configreloaded` and may reload again if it sees a modeless output, and clamshell sync fires 1, 3 and 7 seconds after a monitor add or remove.

### 10.4 Confirmation gate, monitors specifics

The mechanics are core behaviour (contract section A) and are not repeated here: the backstop unit `omarchy-cc-confirm-<txid>` (`.timer` and `.service`) armed at transaction start, the 200 ms poll for the token file under `$XDG_RUNTIME_DIR/omarchy-customization-center/confirm/<txid>`, `ccctl confirm <txid> --token <t>`, `ccctl rollback <txid> --reason timeout` run by the backstop, `ccctl transaction current` for the UI, and `core/ConfirmationGate.qml` rendered on every screen. What is specific to monitors:

- The dialog must exist on every output because the output the overlay lives on may be the one that just went black or got disabled. `ConfirmationGate.qml` uses `Variants { model: Quickshell.screens }`, and `Quickshell.screens` changes when the reload adds or removes outputs, so the set of dialogs follows the new layout without module code. The module supplies the dialog text through the plan summary: "Keep this monitor layout?", the profile name, and "Reverts automatically at <local time> if you do nothing."
- Operation 8 (dpms wake) runs before the gate so that an output the previous layout had blanked is lit when the dialog appears. Its inverse runs during a rollback walk for the same reason.
- The `confirmBy` guard in the generated file (9.1) covers the one case the backstop cannot: a reboot before the timer fires. The unit dies with the session; the guard makes the next boot ignore the unconfirmed rules, and startup recovery (contract section E) rolls the transaction back on the next `ccctl` invocation.
- Overlay closed or crashed during the countdown: the executor process is still blocked at the gate and the backstop is armed; nothing depends on the shell. When the page reopens it reads `ccctl transaction current` and shows the gate again with the executor's deadline.
- Backend (executor) crashed: the backstop fires at `B`, takes the lock, finds `applying` or `awaiting_confirmation`, and runs the rollback walk. The walk restores the generated file, skips `monitors.lua` with `rollback_conflict` if the user changed it after operation 5 (the loader is harmless with the previous generated file), and runs one deferred reload plus the dpms wake at the end.
- User-initiated rollback of a committed activation follows the contract rule: the inverse transaction runs the inverses of operations 10 and 11 (active pointer removed, guard-free rules restored to the previous bytes), then a fresh `TimedConfirmation(30)`, then the inverses of operations 1 to 8 with the reload deferred to the end. If that gate times out, the executor re-runs the forward operations 10 and 11, which puts the confirmed profile back. A user never ends up on an unconfirmed layout.
- `ccctl confirm` after the deadline returns `confirmation_expired`; the page then shows "Reverted at <time> because nobody confirmed" from the journal.

## 11. UI

### 11.1 Page layout

`modules/monitors/Page.qml` implements the page contract (`moduleId`, `status`, `draft`, `capabilities`, `requestPlan`, `requestApply`, `requestReset`, `focusFirst`). Sections top to bottom:

1. Header with the active profile name and `active.state` badge, plus the `related` line: "GDK_SCALE 2, monitor scale auto (from monitors.lua)".
2. `OverrideBanner` when `handwritten.conflicts`, `loader.state == collision|absent-with-active`, or a toggle blocks. Each banner names the file, the line, and the one action that resolves it.
3. Left column `ProfileList`: stored profiles with fit badge (`applicable`, `missing 1 output`, `ambiguous`), New from current layout, New from template (Laptop only, Extend right, Mirror, Preferred), Duplicate, Rename, Delete.
4. Center `LayoutCanvas`: one rectangle per enabled root in logical pixels, mirrors drawn stacked on their target with a badge, disabled outputs as outlined ghosts in a tray below the canvas, disconnected profile outputs as dashed ghosts. Drag with pointer; keyboard: arrows nudge 8 logical px, Shift+arrows 64, Ctrl+arrows 1. The X and Y fields in the inspector accept typed integers. A snap button aligns edges.
5. Right column inspector for the selected output: label, identity (read-only, with connector and "matched by description" or "matched by connector, confirm"), enabled, `ModePicker` (grouped by resolution, refresh list per resolution, current mode highlighted, stale badge when cached), scale (preset chips 1, 1.25, 1.5, 1.6, 2 and a free field; invalid values show the nearest valid pair as chips), transform (0 to 7 with names), mirror of (dropdown of enabled roots), advanced disclosure with bit depth and VRR (with "not set" as the default option), `whenMissing`.
6. Warning area, blockers first, each with the file or output it refers to.
7. Shared `ApplyBar` (core) with Reset draft, Review changes, Apply. The Apply label reads "Apply and confirm within 30 s". The page sets `draft.action = "activate"` and `draft.profile` to the edited copy when there are unsaved edits.

### 11.2 Page states

```text
Loading ─────► Ready ──────► Editing ──► Reviewing ──► Applying ──► AwaitingConfirmation ──► Ready(verified)
   │              │                                       │                 │
   │              ├─► ReadOnlyConflict (handwritten or collision)           ├─► Ready(rolled back, reason shown)
   │              ├─► RuntimeUnavailable (edit and save only)               └─► Ready(rollback partial/failed, recovery hint)
   │              ├─► Ambiguous (assignment picker open)
   │              ├─► AwaitingConfirmation (reopened during a countdown; shows the gate again)
   │              └─► Drifted / Overridden (badge and actions; editing allowed)
   └─► Error (malformed hyprctl output; raw diagnostics, retry)
```

Transitions: `Ready → Editing` on any draft change. `Editing → Reviewing` on Review. `Reviewing → Applying` on Apply after the core confirmation for non-reversible operations (none in the profile plan; `clear-override` has reversible `RunCommand` inverses but the review still shows that Omarchy commands will reload and notify). `Applying → AwaitingConfirmation` when `BackendClient.pollTransaction` reports journal state `awaiting_confirmation` (`ccctl apply` itself stays blocked until the gate resolves). `AwaitingConfirmation → Ready` when the apply call returns, whether committed, rolled back, or `rollback_failed`.

### 11.3 Confirmation on every output

`core/ConfirmationGate.qml` is the dialog. It is driven by `BackendClient.pollTransaction(txid, 200)` reading `ccctl transaction current`, shows the executor's deadline, and calls `BackendClient.confirm(txid, token)` on Keep (Enter, `Y`) or `BackendClient.rollback(txid, "user")` on Revert now (Escape, `N`). The monitors page adds nothing to it beyond the summary text from the plan. The reason it is core and not a module component is the one given in 10.4 and in the desktop modes plan: the dialog must appear on every screen, and modes trigger it without the monitors page being open.

## 12. Backend interface

`modules/monitors/backend/__init__.py` exports `MODULE = MonitorsModule()` with `id = "monitors"`, `schema_version = 1`, and the five protocol methods. All subprocess calls go through `ctx.commands.run(argv, timeout_s, capture_limit)`. Fixed argv used by the module:

| Purpose | argv | timeout |
|---|---|---|
| inventory | `["hyprctl", "-j", "monitors", "all"]` | 3 s |
| config errors | `["hyprctl", "-j", "configerrors"]` | 3 s |
| reload (core `HyprctlReload`) | `["hyprctl", "reload"]` | 10 s |
| wake outputs | `["hyprctl", "dispatch", "hl.dsp.dpms({ action = \"enable\" })"]` | 5 s |
| lua check | `["luac", "-p", <path>]` | 5 s |
| enable laptop display | `["omarchy-hyprland-monitor-internal", "on"]` | 10 s |
| stop mirroring | `["omarchy-hyprland-monitor-internal-mirror", "off"]` | 10 s |

`hyprctl reload` prints `ok` on success. The module checks the exit code and logs any other stdout as a warning; this was not exercised on the development host because a reload has side effects.

ccctl commands the page uses through `BackendClient`: `status monitors`, `validate monitors --draft`, `plan monitors --draft`, `apply monitors --draft --expected-revision`, `confirm <txid> --token`, `rollback <txid> --reason user`, `transaction current`, `transaction <txid>`, `history --module monitors`.

## 13. Test matrix

Fixture directory: `modules/monitors/tests/fixtures/`.

### hyprctl output fixtures (`hyprctl/*.json`)

| Fixture | Content | Used by |
|---|---|---|
| `two-identical-asus.json` | the live capture from this host: two VG27A, distinct serials, `[""]` configerrors companion | inventory, identity, geometry, renderer golden |
| `laptop-only.json` | one `eDP-1` 2880x1800, scale 2 | templates, internal detection |
| `laptop-docked-scaled.json` | `eDP-1` scale 1.6 plus `DP-3` 4K scale 1.5 | scale validity, logical geometry |
| `rotated.json` | `DP-2` transform 1 | transform geometry |
| `mirror.json` | `DP-3` with `mirrorOf: "eDP-1"` | mirror rendering and verification |
| `disabled-phantom.json` | an output with `disabled: true` | inventory includes disabled |
| `modeless.json` | enabled output with `width: 0` | verification failure, modeless check |
| `blank-description.json` | description, make, model, serial all `""` | `if-no-fingerprint` policy |
| `duplicate-description.json` | two outputs with identical description and serial | ambiguity blocker |
| `hostile-name.json` | connector `HEAD" })os.execute("calc")--` (from `test/shell.d/monitor-output-name-test.sh:79`) | unsupported output name, Lua escaping |
| `unparsed-mode.json` | an `availableModes` entry `"weird"` | mode grammar |
| `truncated.txt` | JSON cut mid-array | `malformed_output` |
| `not-json.txt` | `Couldn't connect to ...` | `runtime_unavailable` |

### monitors.lua fixtures (`monitors-lua/*.lua`)

| Fixture | Content | Expected classification |
|---|---|---|
| `shipped-default.lua` | byte copy of `config/hypr/monitors.lua` | `loader.absent`, `catchAll` at line 8 |
| `with-block.lua` | shipped plus the loader block | `present` |
| `with-modified-block.lua` | block body edited | `present-modified` |
| `two-blocks.lua` | two marker pairs | `collision` |
| `reversed-markers.lua` | END before BEGIN | `collision` |
| `explicit-rule-same-output.lua` | `hl.monitor({ output = "DP-1", ... })` with DP-1 connected | `monitors_handwritten_rule_conflict` line 11 |
| `explicit-rule-desc.lua` | `output = "desc:ASUSTek COMPUTER INC VG27A R9LMQS087695"` | conflict |
| `explicit-rule-other-output.lua` | `output = "DP-9"` | `monitors_handwritten_rule_other` |
| `commented-rule.lua` | rules only inside `--` and `--[[ ]]` comments | no findings |
| `variable-output.lua` | `output = name` | `unsupported_config` |
| `semicolon-table.lua` | from `monitor-clamshell-scale-test.sh:208` | catch-all not matched, rule with literal output classified normally |
| `dofile-extra.lua` | `dofile(...)` outside the block | `unsupported_config` |
| `unterminated-string.lua` | lexer failure | `unsupported_config` |
| `scaling-rewritten.lua` | shipped file after `omarchy-hyprland-monitor-scaling` edited scale lines | still `catchAll`, `monitorScaleLocal` numeric |

### Toggle fixtures (`toggles/`)

`disable-eDP-1.lua`, `mirror-DP-3-eDP-1.lua`, `clamshell-eDP-1.lua` with the exact bash-generated content, and `unknown.lua` with an extra field.

### Profile fixtures (`profiles/*.json`)

`desk.json` (two ASUS), `laptop.json`, `projector-mirror.json`, `portrait-right.json`, `negative-coords.json`, `invalid-scale.json` (scale120 168 on 2560x1440), `overlap.json`, `gap.json`, `mirror-cycle.json`, `missing-skip.json`, `unknown-field.json`, `version-2.json`, `bad-id.json` (`../x`).

### Unit tests (`tests/test_*.py`)

- `test_inventory.py`: every hyprctl fixture; refresh rounding (`143.97200` to `143972`); dedupe keeps first occurrence; `[""]` config errors filtered.
- `test_identity.py`: serial match, description match, make-model-only match, connector policies, swapped connectors on distinct serials still match by serial, duplicate description is ambiguous, `assignments` resolves it, extra outputs, missing outputs with both `whenMissing` values.
- `test_geometry.py`: table over transforms 0 to 7 for 2560x1440 and 2880x1800; scale120 in {120, 150, 168, 192, 200, 240}; nearest valid pair for 168 on 2560x1440 (expect 160 and 192); negative coordinates; edge touch versus overlap; gap islands; snap.
- `test_mirror.py`: self, cycle, chain, disabled target, missing target, aspect warning.
- `test_profile.py`: canonical round trip, unknown field rejected with pointer, version 2 rejected, id regex, filename derived from id only.
- `test_lua_render.py`: golden files for each profile fixture against `two-identical-asus.json`; ordering; refresh and scale formatting; escaping of every byte 0 to 255 in a label (NUL rejected); hostile connector name; `luac -p` on every golden when available.
- `test_ownership.py`: every monitors.lua fixture; bytes outside the block byte-identical after `ReplaceManagedBlock`; toggles classification.
- `test_planner.py`: operation list order for a fresh install (all eleven operations from section 3), for an existing install (operations 1, 2, 6 to 11), for `clear-override`; `capability_missing` when `timed_confirmation` is absent; `stale_revision` when the inventory changed between status and apply.

### Integration tests with command stubs (`tests/test_apply_integration.py`)

Stubs for `hyprctl`, `systemd-run`, `systemctl`, `luac`, `omarchy-hyprland-monitor-internal`, `omarchy-hyprland-monitor-internal-mirror` under an isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`. Each stub logs its argv to a file the test reads.

- activate then confirm through the token file: operation order from section 3, backstop argv with `B = 60`, guard stripped by operation 10, active pointer written by 11, journal `committed`, timer stopped.
- activate then Revert now (`rollback --reason user` from the gate): files restored, one deferred reload at the end, dpms wake, journal `rolled_back`.
- activate then deadline (clock stub): rollback walk, reason `timeout`.
- backstop run from a fresh process against a dead executor (`applying` state): rollback walk; against a terminal state: exit 0.
- `confirm` after rollback: `confirmation_expired`; bad token: `confirmation_invalid`.
- reload fails: inverses run before the gate opens, `runtime_unavailable`.
- pre-confirmation `verify` never stabilizes (stub alternates two topologies): rollback without a dialog, `monitors_verification_failed`.
- new config error after reload: `HyprctlReload` fails, rollback.
- `timed_confirmation` capability missing: `capability_missing`, no write happened.
- `monitors.lua` edited during the countdown: rollback records `rollback_conflict` for it and restores the generated file.
- `ccctl transaction current` during the countdown reports `awaiting_confirmation` and the deadline.
- past-deadline entry found by startup recovery: rolled back before the next command runs.
- rollback of a committed activation: inverse transaction order (post-gate inverses, gate, pre-gate inverses); gate timeout re-applies operations 10 and 11.
- `clear-override` forward and inverse argv.

### Live checks (manual, recorded in `tests/manual/monitors.md`)

- This host: activate `desk.json`, confirm; activate a swapped left-right version, let it time out, confirm the layout reverted and the dialog appeared on both outputs; kill `omarchy-shell` during a countdown and confirm the gate still reverts; kill the `ccctl apply` process during a countdown and confirm the backstop reverts at `B`.
- Omarchy VM with a laptop profile: lid close and open with an external display, `omarchy-hyprland-monitor-internal off` then apply a profile that enables the panel (expect the override blocker), mirror toggle, `omarchy-refresh-hyprland` followed by loader reinstall, reboot during a countdown (expect the catch-all on boot and rollback on the next `ccctl`).
- Existing `test/shell.d/monitor-*.sh` in the Omarchy tree still pass with the loader block present in `monitors.lua`.

## 14. Milestones

1. Inventory and read-only page: `inventory.py`, `status()` without profiles, canvas from runtime geometry. Exit: opening the page writes only the cache file; every fixture renders.
2. Profiles and matching: schema, CRUD through `save-profile` and `delete-profile`, identity, geometry, templates, fit badges. Exit: duplicate descriptions are never auto-assigned; invalid layouts produce no apply plan.
3. Ownership and Lua: scanner, loader, renderer, escaping, `luac`. Exit: bytes outside the block are identical in every fixture; all unsupported shapes fail closed.
4. Guarded activate: the gate, both `verify` calls, the reboot guard, rollback of a committed activation. Exit: killing the shell and the backend after the reload still restores the previous layout at the deadline.
5. Interactive canvas and overrides: drag, keyboard, snap, mode picker, scale suggestions, override banners with `clear-override`. Exit: every pointer action has a keyboard path.
6. Suggestions and hardening: fit ranking, drift detection, VM matrix, recovery documentation.

## 15. Core services used

Everything below is provided by core under the amended contract; the module only consumes it.

- `TimedConfirmation(30)` as a blocking gate, the backstop unit `omarchy-cc-confirm-<txid>` armed at transaction start, `ccctl confirm --token`, `ccctl transaction current`, `capability_missing` when `timed_confirmation` is unavailable.
- `core/ConfirmationGate.qml` on every screen, `BackendClient.pollTransaction` and `pollStatus`.
- `managed_block.py` for the `MONITORS v1` markers and `managed_block.inspect` states; `ReplaceManagedBlock`, including `body=None` for a future removal action.
- `WriteFileAtomic` with sha256-guarded inverse (`rollback_conflict`), `RemoveFile`, `EnsureDirectory`, `RunCommand`.
- `HyprctlReload` with the reload-guard check, the `configerrors` diff, and deferred inverse (one reload at the end of a rollback walk).
- `ccctl rollback --reason user|timeout|recovery`, the rollback walk, startup recovery at every locking command and at `ccctl modules`.
- `core/lua.py` `lua_string`, `core/hyprctl.py` for the JSON commands, `Paths.home` for the toggles directory.

## 16. Open items

1. Does `mirror` accept a `desc:` selector, and does a later `hl.monitor` for the same output replace an earlier one? Both need a disposable session. Until then, mirrors target connectors and handwritten rules for the same output block the activate.
2. Does Hyprland re-arm inotify watches on the new inode after a reload that followed a rename-based write? If not, a user editing `monitors.lua` in place after a Customization Center activate would not get auto-reload until the next manual reload. Test with `inotifywait` or `/proc/<pid>/fdinfo` on the VM; if confirmed, mention it in the page's help text.
3. Whether `hyprctl reload` discards rules added with `hyprctl eval`. `bin/omarchy-hyprland-monitor-scaling:100-101` persists to `monitors.lua` "so the scale survives reboots", which suggests eval state is not durable across reloads, but this was not verified. The `monitors_runtime_drift` warning assumes it is discarded.
4. Minimum Hyprland version. Gate on JSON fields (`mirrorOf`, `availableModes`, `serial`) rather than the version string. Everything here was checked on 0.56.2.
5. Whether the basic view should hide `bitDepth` and `vrr` behind the advanced disclosure or drop them from version 1. The plan keeps them behind the disclosure with "not set" as default, which emits nothing.
