# Keybinding editor module plan

Module id: `keybindings`. This plan covers Module 7 of `plans/planned/customization-center-masterplan.md` and is written against the module contract (repository layout, backend module interface, core operations, `ccctl`, page contract). Verified against `omarchy-fork` at commit `71b0887c`, Hyprland 0.56.2 on this machine, the local wiki under `/home/firstpick/.hyprwiki/content/Configuring/Basics/`, and live `hyprctl` output captured on 2026-08-28.

One caveat about the live data: the Hyprland instance on this machine does not run the Omarchy config (its descriptions read "Open app launcher", "Open WhatsApp", "Lock screen", and its layout is `ch`). The record grammar, flag letters, JSON shape, keymap probes and option probes below are live observations. The correlation with Omarchy defaults was checked against source and Omarchy's own test harness, not against a live Omarchy session.

## What the module does

- Lists every binding the running compositor reports, with flags, submap, description and a source classification.
- Lets the user add an `exec` binding, replace an Omarchy default with an `exec` binding, disable an Omarchy default, and undo any of those.
- Keeps its own records in one JSON file and renders them into one marked block in `~/.config/hypr/bindings.lua`. Bytes outside the block never change.
- Reports conflicts before apply, with the category of each conflict and what an unbind would take with it.
- Applies through the core executor: write the JSON, replace the block, reload Hyprland, verify the runtime, and roll back on any failure.
- Accepts its complete managed document as a draft, which is how desktop modes drive it (see "Desktop modes" under the schema).

## What the first release refuses to do

- Parse, rewrite or adopt handwritten Lua. Anything outside the managed block is opaque.
- Author anything other than global keyboard `exec` bindings and exact unbinds. Lua function dispatchers, `hl.dsp.*` native dispatchers, submaps, `catchall`, `switch:`, `mouse:`, `mouse_up`/`mouse_down`, per-device bindings, `click`, `drag`, `long_press`, `transparent`, `ignore_mods`, `separate`, `submap_universal` and modifier-only chords are shown read-only with a reason code.
- Author a second action on a chord that already has one (a stack). Existing stacks are shown as a group.
- Disable or replace a runtime binding whose exact source spelling is unknown (anything classified `external`).
- Run a binding's command for any purpose. The master plan's "Test action" is dropped for `exec` bindings because running the command is the only way to test one.
- Edit `omarchy_default_bindings` or `omarchy_preinstalled_bindings` in `~/.config/hypr/hyprland.lua`. The page reports their observed effect.
- Capture chords through `/dev/input`, a temporary submap, a temporary bind, or any privileged path. Capture is a focused QML field and nothing else.
- Touch anything under `$OMARCHY_PATH`.

## Verified facts

Each row is something the design below depends on. Anything I could not verify is marked as such and treated as unknown by the code.

| Fact | Source |
|---|---|
| `o.bind(keys, description, dispatcher, options)` sets `opts.description = description` when description is truthy, resolves table dispatchers through `command_from`, wraps a string dispatcher in `hl.dsp.exec_cmd`, and forwards everything else untouched to `hl.bind(keys, dispatcher, opts)`. It mutates the `options` table it was given. | `default/hypr/helpers.lua:92-106`, `command_from` at `:56-82` |
| Table dispatchers resolve to exec commands: `{ omarchy = "x" }` becomes `omarchy-launch-x`, `{ launch = c }` becomes `uwsm-app -- c`, `{ webapp = url }` becomes `omarchy-launch-webapp '<url>'`, `{ tui = t }` becomes `omarchy-launch-tui '<t>'`, with `focus` variants. | `default/hypr/helpers.lua:61-79`, `:108-132` |
| Helpers load unconditionally; default binding modules load only when `_G.omarchy_default_bindings ~= false`; `applications` is optional. | `default/hypr/omarchy.lua:7`, `:12-19` |
| User overrides load after defaults: `require("default.hypr.omarchy")` then `require("hypr.bindings")`. | `config/hypr/hyprland.lua:41`, `:48` |
| `hypr.bindings` resolves through `package.path = $HOME/.local/state/?.lua;$HOME/.config/?.lua;$OMARCHY_PATH/?.lua`. The path uses `$HOME/.config`, not `$XDG_CONFIG_HOME`. | `default/hypr/bootstrap.lua:33-39` |
| The stock user file documents exactly the two forms this module renders: `o.bind("SUPER + SHIFT + R", "SSH", "alacritty -e ssh your-server")` and `hl.unbind("SUPER + SPACE")` followed by `o.bind(...)`. | `config/hypr/bindings.lua:16`, `:20-21`, `:24` |
| `hl.unbind(keys)` is case-sensitive on the key: `hl.unbind("SUPER + Tab")` does not remove `hl.bind("SUPER + TAB", ...)`. | `Binds.md:514-535` |
| Unbinding by key removes every bind on that key. Omarchy keeps per-bind handles for its selection-layer binds precisely so that `keybind:unbind()` does not take a same-key user binding with it. | `default/hypr/bindings/utilities.lua:44-48`, `:76-78` |
| `code:N` in the key position binds by XKB keycode; `SUPER + code:28` is SUPER + t. XKB keycodes are evdev codes plus 8. | `Binds.md:49-56`; `test/shell.d/hyprland-binding-conflicts-test.sh:73` |
| Flags accepted by `hl.bind`: `locked`, `release`, `click`, `drag`, `long_press`, `repeating`, `non_consuming`, `auto_consuming`, `mouse`, `transparent`, `ignore_mods`, `separate`, `description`, `bypass`, `submap_universal`, `devices`. | `Binds.md:75-94` |
| Binds resolve against the first layout in `kb_layout` unless `resolve_binds_by_sym` is set. Omarchy prepends `us,` when the configured layout cannot type Latin letters. | `Binds.md:459-472`; `Variables.md:194`; `default/hypr/input.lua:39-48` |
| Hyprland auto-reloads on config save unless `misc.disable_autoreload` is true. | `Variables.md:441`; `default/agents/skills/omarchy/hyprland.md:22-24` |
| Omarchy pauses auto-reload during package transactions by setting `misc.disable_autoreload` and `debug.suppress_errors` through `hyprctl eval`, keeps state under `/run/omarchy/hyprland-reload-guard/<signature>`, and `omarchy-hyprland-reload-guard paused` exits 0 while paused. Other Omarchy scripts skip their own reload while paused. | `bin/omarchy-hyprland-reload-guard:37`, `:85-92`, `:107`, `:119`; `bin/omarchy-hyprland-monitor-watch:52-53` |
| `hyprctl reload` accepts `config-only` to skip the monitor reload. | `hyprctl --help` on 0.56.2 |
| `hyprctl -j configerrors` prints `[""]` when there are no errors; plain `hyprctl configerrors` prints an empty line. | Live probe on 0.56.2 |
| Omarchy's menu parses plain `hyprctl binds`, not `-j`, because 0.56.0 emitted misaligned JSON and older versions broke on quotes in args. | `bin/omarchy-menu-keybindings:275-277` |
| Lua-provider binds report `dispatcher: __lua`. For `code:` binds the `key` field carries the whole source chord ("SUPER + code:20") while `modmask` carries the modifiers again. | `bin/omarchy-menu-keybindings:5-7`, `:289-291`; live probe (`key: SUPER + CTRL + code:94`, `modmask: 68`, `keycode: 0`) |
| Older Hyprland reported `code:` binds with an empty `key` and a non-zero `keycode`. | `bin/omarchy-menu-keybindings:12-14`, `:293-295`; fixture at `test/shell.d/keybindings-menu-test.sh:132-140` |
| Modmask bits: SHIFT 1, CTRL 4, ALT 8, SUPER 64. Omarchy's tables and the live output agree. CAPS 2, MOD2 16, MOD3 32, MOD5 128 follow the X11 convention and are not verified locally. | `bin/omarchy-menu-keybindings:85`, `:243-262`; live probe |
| Omarchy stacks two actions on `ALT + TAB` and `ALT + SHIFT + TAB` on purpose, binds `F9` for press and for release, binds SUPER + W and SUPER + Q to the same action, and hides `code:201` (Copilot key) from the menu. | `default/hypr/bindings/tiling.lua:47-50`; `voxtype.lua:3-4`; `tiling.lua:1-2`; `omarchy-menu-keybindings:310` |
| Omarchy writes the comma key as lowercase `comma` because `COMMA` does not match. Uppercase `SLASH`, `PERIOD`, `RETURN`, `TAB`, `SPACE`, `PRINT`, `ESCAPE`, `BACKSPACE` do work. | `default/hypr/bindings/utilities.lua:23-24`; `applications.lua:20`; `tiling.lua:97`; `utilities.lua:86` |
| `xkbcli how-to-type --keysym <name>` is case-sensitive: `Tab`, `comma`, `Return`, `Print`, `grave`, `XF86AudioPlay` resolve; `tab`, `COMMA`, `RETURN`, `PRINT`, `GRAVE`, `ESCAPE` exit 2. It defaults to the `us` layout unless given `--layout/--variant/--options`. With `--keysym 0xff09` it prints `keysym: Tab (0xff09)`. | Live probe, libxkbcommon 1.13.2 |
| `xkbcli compile-keymap` prints `xkb_keycodes` (`<TAB> = 23;`) and `xkb_symbols` (`key <TAB> { [ Tab, ISO_Left_Tab ] };`) sections; Omarchy already parses them. | `bin/omarchy-menu-keybindings:25-39`; live probe |
| `hyprctl -j devices` returns `keyboards[]` with `name`, `rules`, `model`, `layout`, `variant`, `options`, `active_layout_index`, `active_keymap`, `main`, plus `switches[]`. Omarchy keys its cache on the `active keymap:` lines. | Live probe; `bin/omarchy-menu-keybindings:531-537` |
| `luac` on this Arch install is Lua 5.5.1 (`/usr/bin/luac`), `luac5.4` is 5.4.8, and `/usr/bin/Hyprland` links both `liblua.so.5.5` and `liblua5.4.so.5.4`. Which one runs the config is not verifiable from here. | `luac -v`, `pacman -Q lua lua54`, `ldd /usr/bin/Hyprland` |
| Omarchy's own conflict check loads defaults through a stub `hl`, sorts modifiers, maps `code:N` to a keysym, appends `(release)` to the signature, and allows exactly the two `ALT+TAB` stacks. | `test/shell.d/hyprland-binding-conflicts-test.sh:15-71`, `:84-106`, `:120-123`, `:170-176` |

Dropped from the previous plan because it did not hold at `71b0887c`: the citation of `default/agents/skills/omarchy/hyprland.md` was correct, but the previous text said Hyprland "may normalize or lose the source spelling" of keys in runtime output. The live output shows the opposite: `key` retains source spelling (`tab`, `section`, `up`, `SPACE`, `F13`). What the runtime does lose is the modifier spelling and order, which is carried only as `modmask`. The rule that follows is narrower than before: an unbind can be rendered from a runtime record's key token, but this release still only renders unbinds from catalog or managed source strings, because whether `hl.unbind` compares modifiers by mask or by text is unverified.

## Module layout

```text
modules/keybindings/
├── module.json                 # id "keybindings", title "Keybindings", icon, navOrder 70,
│                               #   page "Page.qml", backend "customization_center.modules.keybindings",
│                               #   schemas [...], coreServices ["hyprctl", "managed_block", "lua", "commands"]
├── Page.qml
├── components/
│   ├── BindingTable.qml        # rows, grouping into stacks, filters, search
│   ├── BindingDetails.qml      # drawer: flags, source, read-only reason, affected records
│   ├── ChordField.qml          # text entry + capture button + validation echo
│   ├── ChordCapture.qml        # modal capture (section "Chord capture")
│   ├── ActionPicker.qml        # curated catalog or custom command
│   ├── ConflictPanel.qml
│   └── LuaPreview.qml          # rendered block, read-only
├── backend/
│   ├── __init__.py             # exports MODULE
│   ├── inventory.py            # hyprctl binds / -j binds / devices parsing and reconciliation
│   ├── chords.py               # grammar, normalization, identity
│   ├── keymap.py               # xkbcli adapters, keycode<->keysym maps
│   ├── catalog.py              # Omarchy default catalog harness
│   ├── classify.py             # managed / omarchy-default / external
│   ├── conflicts.py
│   ├── model.py                # managed model load, validate, migrate
│   ├── render.py               # Lua literal escaping and block rendering
│   ├── luacheck.py             # luac capability and syntax check
│   ├── planner.py              # validate, plan, verify
│   └── data/
│       ├── keysym-fallback.json    # name -> keysym for ~150 common keys, used when xkbcli is missing
│       └── action-catalog.json     # curated Omarchy commands
├── schemas/
│   ├── keybindings-model-v1.json
│   ├── keybindings-draft-v1.json
│   └── keybindings-status-v1.json
└── tests/
    ├── fixtures/               # see "Test matrix"
    ├── test_inventory.py, test_chords.py, test_keymap.py, test_catalog.py, test_classify.py,
    ├── test_conflicts.py, test_model.py, test_render.py, test_luacheck.py, test_planner.py,
    ├── test_apply_integration.py
    └── qml/                    # capture mapping and state tests
```

Owned files:

- `~/.config/omarchy/customization-center/keybindings.json`: the managed model. Canonical JSON, sorted keys, two-space indent, trailing newline.
- `~/.config/hypr/bindings.lua`: one managed block. Path is `$HOME/.config/hypr/bindings.lua` regardless of `XDG_CONFIG_HOME`, because that is where `require("hypr.bindings")` looks (`bootstrap.lua:33-39`).

The core executor owns backups, journal and lock under `~/.local/state/omarchy/customization-center/`.

## Runtime inventory

### Commands

All through `ctx.commands.run(argv, timeout_s, capture_limit)` with `LC_ALL=C`, never through a shell.

| Purpose | argv | Timeout | Output limit |
|---|---|---|---|
| Plain inventory | `["hyprctl", "binds"]` | 5 s | 4 MiB |
| JSON inventory | `["hyprctl", "-j", "binds"]` | 5 s | 8 MiB |
| Keymap context | `["hyprctl", "-j", "devices"]` | 5 s | 1 MiB |
| Version | `["hyprctl", "version"]` | 5 s | 64 KiB |
| Autoreload flag | `["hyprctl", "-j", "getoption", "misc.disable_autoreload"]` | 5 s | 4 KiB |
| Layout resolution flag | `["hyprctl", "-j", "getoption", "input.resolve_binds_by_sym"]` | 5 s | 4 KiB |
| Config errors | `["hyprctl", "-j", "configerrors"]` | 5 s | 1 MiB |

`hyprctl` failing to connect returns `runtime_unavailable`. A timeout returns `timeout`. Output over the limit returns `malformed_output` with `keybindings_binds_truncated` in errors.

### Plain record grammar

Observed on 0.56.2 (88 records, every one 8 fields, tab-indented, one blank line between records):

```text
bindd
	modmask: 64
	submap: 
	key: SPACE
	keycode: 0
	catchall: false
	description: Open app launcher
	dispatcher: __lua
	arg: 6

```

Formal grammar the parser implements:

```text
output      := record*
record      := header LF field* LF          ; the terminating blank line is optional at EOF
header      := "bind" LETTER*               ; column 0, letters only, nothing else on the line
field       := TAB name ":" (" " value)? LF ; name = [a-z_]+, value may be empty
continuation:= any other non-empty line     ; appended to the previous field's value with "\n"
```

Parser rules, in order:

1. Split stdout on `\n`. Do not strip trailing whitespace from values; `description: ` with an empty value has one trailing space after the colon which the grammar consumes.
2. A line matching `^bind([a-z]*)$` opens a record. `LETTER*` is stored as a set in `headerFlags`.
3. A line matching `^\t([a-z_]+):(?: (.*))?$` inside a record sets `fields[name] = value or ""`. A repeated name in one record is a parse error for that record.
4. Any other non-empty line inside a record is a continuation of the last field; append `"\n" + line` and add warning `keybindings_binds_continuation` with the record index. Hyprland's behaviour for a description containing a newline is unverified; this rule keeps the record count right either way.
5. An empty line closes the record. A `bind` header while a record is open also closes it (missing blank line).
6. A record must have `modmask` (decimal integer), `key` (string), `keycode` (decimal integer), `dispatcher` (string). Missing or non-numeric values make the record `unparsed`; it is kept as a row with `parseError` set and counted in `warnings`. Never drop a record silently.
7. `submap`, `catchall` (`true`/`false`), `description`, `arg` are optional with defaults `""`, `false`, `""`, `""`. Unknown field names are kept in `extra`.
8. `rawText` (the exact lines of the record) and `index` (0-based order) are stored.

Header letters observed live: `d` (has description), `l` (locked), `e` (repeating). Cross-checked against the JSON for the same records: every `bindle` record has `locked: true, repeat: true`. Letters `r` (release), `m` (mouse), `n` (non_consuming), `t` (transparent), `i` (ignore_mods), `s` (separate), `p` (bypass), `o` (long_press), `c` (click), `g` (drag) are Hyprland's flag letters from the hyprlang era and were not observed on this machine. The parser maps `d`, `l`, `e` with confidence; any other letter marks the record `unsupported_flag` for editability whether or not it is in that list.

Key field interpretation (`inventory.split_key_field`):

```text
if key == "" and keycode != 0:            keyToken = "code:" + keycode        ; legacy shape
elif " + " in key:                        keyToken = key.rsplit(" + ", 1)[1]  ; 0.56.2 code: shape, modifiers already in modmask
else:                                     keyToken = key
keyFieldRaw = key                                                          ; kept verbatim
```

`dispatcher: __lua` with a numeric `arg` is the shape for every Lua-provider bind. The `arg` is a handler id assigned at load; it must not be part of any identity that is compared across a reload. `dispatcher: exec` with a command in `arg` is the hyprlang shape and still gets a fixture.

### JSON reconciliation

`hyprctl -j binds` on 0.56.2 returns a list of objects with exactly these keys: `locked`, `mouse`, `release`, `repeat`, `longPress`, `non_consuming`, `auto_consuming`, `has_description` (booleans), `modmask`, `keycode` (integers), `submap`, `key`, `description`, `dispatcher`, `arg` (strings), `catch_all` (boolean), `allow_input_capture` (boolean), and `submap_universal` as the string `"true"`/`"false"`, not a boolean. Note `catch_all` versus plain `catchall`.

Accept the JSON only when all of these hold:

1. It parses and is a list.
2. `len(json) == len(plain_records)`.
3. For every index `i`: `json[i].modmask == plain[i].modmask`, `json[i].key == plain[i].key`, `json[i].keycode == plain[i].keycode`, `json[i].submap == plain[i].submap`, `json[i].dispatcher == plain[i].dispatcher`.
4. Every boolean field above is a JSON boolean; `submap_universal` is parsed from its string form.

On acceptance, copy `locked`, `release`, `repeat` (stored as `repeating`), `longPress`, `non_consuming`, `auto_consuming`, `mouse`, `submap_universal`, `catch_all`, `allow_input_capture` onto the record and set `flagSource = "json"`. On rejection, keep the plain records, derive `locked`, `repeating`, `hasDescription` from header letters, set `flagSource = "header"`, and add warning `keybindings_binds_json_untrusted` with the reason. JSON is never the primary source.

There is no JSON field for `transparent`, `ignore_mods`, `separate`, `bypass`, `click`, `drag` or `devices`. Those can only be inferred from header letters. A record whose header contains an unmapped letter is read-only.

### Keymap context

From `hyprctl -j devices`: take `keyboards[]`, pick the entry with `main: true` if any, else the first; record `layout`, `variant`, `options`, `rules`, `model`, `active_layout_index`, `active_keymap`, and the set of distinct `(layout, variant, options)` tuples across keyboards (a warning is raised when they differ). Record `switches[].name` for display of `switch:` bindings. `input.resolve_binds_by_sym` is read once and stored on status.

Keymap maps, built by `keymap.py` when `xkbcli` is present:

- `keycode_to_level1_keysym`: run `["xkbcli", "compile-keymap", "--layout", L, "--variant", V, "--options", O]` with stdin closed (Omarchy notes the `</dev/null` requirement at `omarchy-menu-keybindings:24`), parse `<NAME> = N;` lines under `xkb_keycodes` and `key <NAME> { [ first, ... ] }` lines under `xkb_symbols`, join by NAME. Only the first group's first level is used. Empty `--variant`/`--options` are omitted from argv.
- `keysym_name_to_code`: `["xkbcli", "how-to-type", "--keysym", name]` returns `keysym: <canonical> (0x....)` on line 1; parse both. Exit 2 means unknown name.
- Cache both per `(layout, variant, options, xkbcli version)` in `ctx.cache` for the session.

Without `xkbcli`: `data/keysym-fallback.json` supplies name and case-fold data for common keys, keycode aliasing is unavailable, and status carries `keybindings_keymap_unavailable`. Every keycode relationship then degrades to `possible_alias`.

### Revision

`status().revision = "sha256:" + sha256(` plain `hyprctl binds` bytes, accepted JSON bytes or `"-"`, `hyprctl version` first line, the keyboard tuples, `bindings.lua` bytes or `"-"` if absent, `keybindings.json` bytes or `"-"`, catalog digest `)`. The apply path re-derives it and refuses on mismatch with `stale_revision`.

## Chord model

Three representations exist for every binding and they are never substituted for each other:

- `sourceKeys`: the exact string that goes into `o.bind(...)` or `hl.unbind(...)`. For managed bindings the renderer produces it. For Omarchy defaults it is the `keys` argument recorded verbatim by the catalog harness. It is the only thing ever rendered into Lua.
- `identity`: a structured value used for comparison. Never rendered.
- `display`: UI text, for example `SUPER + SHIFT + R` or `SUPER + ~`.

### Grammar for editable chords

```text
chord     := (modifier WS* "+" WS*)* key
modifier  := name matched case-insensitively against MOD_NAMES
key       := "code:" DIGITS | "mouse:" DIGITS | keysymName
keysymName:= [A-Za-z0-9_]+                 ; validated by resolution, not by regex
```

`MOD_NAMES` = `{ "SUPER": SUPER, "WIN": SUPER, "LOGO": SUPER, "MOD4": SUPER, "CTRL": CTRL, "CONTROL": CTRL, "ALT": ALT, "SHIFT": SHIFT }`. Omarchy's own parser recognizes `SHIFT`, `CTRL`, `CONTROL`, `ALT`, `SUPER` (`omarchy-menu-keybindings:85`); the `WIN`/`LOGO`/`MOD4` aliases come from Hyprland's modifier parser and are accepted on input only. The editor always emits `SUPER`, `CTRL`, `ALT`, `SHIFT`. Anything else in a modifier position (`CAPS`, `MOD2`, `MOD3`, `MOD5`, `ALTGR`) is rejected with `keybindings_unsupported_modifier`.

### Normalization algorithm

```text
normalize(text, keymap) -> Chord | Error
  1. text = strip(text); reject if any char < 0x20 or == 0x7f       -> keybindings_chord_grammar
  2. parts = split on "+", each stripped; reject empty part          -> keybindings_chord_grammar
     ("SUPER + + A", "+A", "A +" are all rejected)
  3. key = parts.pop(); mods = parts
  4. modmask = 0
     for m in mods:
        bit = MOD_NAMES.get(upper(m)); reject if None                -> keybindings_unsupported_modifier
        reject if bit already set (duplicate)                        -> keybindings_chord_grammar
        modmask |= bit
  5. if key matches ^code:(\d+)$:
        code = int; reject if code < 8 or code > 255                 -> keybindings_chord_grammar
        keyKind = "code"; keyValue = code
        keysym = keymap.keycode_to_level1_keysym.get(code)           ; may be None
        keyToken = "code:" + code                                    ; render spelling
     elif key matches ^mouse:(\d+)$ or key in {mouse_up, mouse_down, mouse_left, mouse_right}
          or key starts with "switch:" or key == "catchall":
        keyKind = "pointer" | "switch" | "catchall"; not editable     -> keybindings_unsupported_key
     else:
        resolved = resolve_keysym(key, keymap)                        ; see below
        reject if None                                               -> keybindings_unknown_keysym
        keyKind = "keysym"; keyValue = resolved.canonicalName
        keyToken = render_spelling(resolved)
  6. identity = (modmask, keyKind, casefold(keyValue) if keysym else keyValue)
  7. sourceKeys = " + ".join(canonical mod names in order SUPER, CTRL, ALT, SHIFT for set bits) + " + " + keyToken
     (no leading " + " when modmask == 0)
  8. display = sourceKeys with keyToken replaced by DISPLAY_ALIASES.get(keyValue, keyToken)

resolve_keysym(name, keymap):
  try in order: name, lower(name), capitalize(name) ("Return", "Tab", "Print", "Home"),
                "XF86" + name[4:] if name lower-starts with "xf86"
  first that xkbcli (or the fallback table) accepts wins; return its canonical name and code.

render_spelling(resolved):
  if canonicalName is a single Latin letter a-z: upper(canonicalName)     ; "W", the Omarchy convention
  else: canonicalName                                                     ; "Return", "comma", "grave", "XF86AudioPlay"
```

Why canonical xkbcommon names for non-letters: Hyprland accepts `RETURN` and `TAB` but not `COMMA` (`utilities.lua:23`), and the reason is not documented. The canonical name is what every lookup tries first, so it is the one spelling that cannot fail. Letters stay uppercase because every Omarchy default is written that way and users read `SUPER + W` faster than `SUPER + w`.

`DISPLAY_ALIASES` = `{ "grave": "~", "comma": ",", "period": ".", "slash": "/", "minus": "-", "equal": "=", "space": "Space", "Return": "Enter", "BackSpace": "Backspace", "Prior": "Page Up", "Next": "Page Down" }`. Omarchy's menu makes the same `grave` to `~` choice (`omarchy-menu-keybindings:44`, `:314`).

The `SUPER + code:10` versus `SUPER + 1` relation: when `keymap.keycode_to_level1_keysym[10] == "1"` the two identities are declared equal for conflict purposes with `aliasConfidence = "exact_current_keymap"`. Without a keymap the relation is `possible_alias`. Omarchy's test treats it as a collision (`hyprland-binding-conflicts-test.sh:178-183`); so does this module.

### Runtime record identity

For a runtime record: `modmask` from the record, `keyToken` from `split_key_field`, then steps 5 to 6 above with `resolve_keysym` allowed to fail (unresolvable tokens keep `keyKind = "unknown"` and compare by casefolded text). `phase` is `release` if the release flag is set, `long_press`, `click`, `drag` likewise, else `press`. `scope` is `(submap, submap_universal, devices)`, with `devices` always unknown from runtime output. The full runtime identity is `(domain, identity, phase, submap)` where `domain` is `keyboard`, `pointer`, `switch` or `catchall`.

## Omarchy default catalog

`catalog.py` runs the package-owned default bindings through a stub `hl`, the same technique as `test/shell.d/hyprland-binding-conflicts-test.sh:15-71`, and records every `hl.bind` call. It runs `["lua5.4"]` if present, else `["lua"]`, timeout 10 s, output limit 2 MiB, with the real `HOME` and `PATH` so that `o.preinstalled_bindings_enabled()` (`helpers.lua:84-90`) and `o.cmd_present("voxtype")` (`voxtype.lua:1`) see the same state the compositor does. Only `default.hypr.omarchy` is required. The user's `hyprland.lua` and `bindings.lua` are never loaded. `hl.on`, `hl.timer`, `hl.dispatch`, `hl.config`, `hl.exec_cmd` are no-ops; `hl.dsp` is a recording proxy so that native dispatchers surface as `{ kind = "native", expr = "hl.dsp.window.close()" }` and `hl.dsp.exec_cmd("x")` as `{ kind = "exec", command = "x" }`, exactly as `omarchy-menu-keybindings:169-185` does. Each recorded call carries `keys` (verbatim), `description`, `dispatcherKind` (`exec` | `native` | `function`), `command` when exec, `flags` (the options table minus description), and `sourceFile`/`sourceLine` from `debug.getinfo(2, "Sl")` inside the `hl.bind` stub.

Side effects this harness has and accepts: `require_all.files` runs `find` through `io.popen` (`default/hypr/require_all.lua:74`), `o.cmd_present` opens files on `PATH`, and `o.preinstalled_bindings_enabled` opens one state file. It executes package code only.

Catalog output is a list of `CatalogEntry { keys, identity, phase, description, dispatcherKind, command, flags, module ("tiling" | "utilities" | ...), sourceFile, sourceLine, conditional (bool) }` plus a digest. The dynamic selection-layer binds created inside `hl.on("layer.opened", ...)` (`utilities.lua:52-70`) never fire in the harness and are therefore absent from the catalog; if they appear at runtime they classify as `external` with reason `dynamic`, which is correct.

Failure of the harness (missing `lua`, `$OMARCHY_PATH` unreadable, timeout, Lua error) sets `keybindings_catalog_unavailable` and the page shows every non-managed record as `external`. It never hides runtime rows.

## Classification

For each runtime record, in this order:

1. `managed`: exactly one enabled managed binding has the same `(identity, phase)` and the same `description`. The runtime `arg` is ignored. Record `managedId`.
2. `disabled_default` (synthetic row, no runtime record): a managed disable whose catalog target still exists and whose identity has no runtime record. Shown so the user can restore it.
3. `omarchy_default`: exactly one catalog entry has the same `(identity, phase)` and description. Confidence `exact` when the JSON flags were accepted and match the entry's flags, `probable` otherwise. The badge text is "matches Omarchy default", because an identical user-authored copy is indistinguishable.
4. `external`: everything else, with `reason` from `{ "no_match", "ambiguous_match", "dynamic", "submap", "unknown_modmask" }`. Two candidates in step 1 or 3 give `ambiguous_match`.

Editability per row (`editable.disable`, `editable.replace`, `editable.edit`) is computed after classification:

- `managed`: edit and remove allowed.
- `omarchy_default` with `dispatcherKind in {exec, native, function}` and `domain == keyboard`, `submap == ""`, editable modifiers only: disable and replace allowed. The catalog `keys` string is the unbind spelling. Native and function defaults can be disabled or replaced because the unbind does not care what the dispatcher was; they cannot be cloned.
- Anything else: read-only with `readOnlyReason` from `{ lua_function, native_dispatcher, dynamic, submap, device_scoped, mouse, switch, catchall, unknown_exact_source, unsupported_flag, unsupported_modifier, stack_member }`.

A row that shares its full runtime identity with another row is a `stack` member. Stacks are grouped in the table with `stackSize`. A stack whose members are all `omarchy_default` can be disabled as a group (one unbind removes all of them) and the confirmation lists every member. A stack containing an `external` member is read-only.

## Conflict classifier

Input: the runtime inventory, the draft's desired managed model, and the simulated effect of the draft's unbinds. Simulation: for each disable in the draft, every runtime record with the same `(domain, identity)` in submap `""` is marked `removed` regardless of phase, because unbind is by key (`utilities.lua:47-48`). Then each desired managed binding is matched against the remaining records plus the other desired bindings.

Each finding has `category`, `severity` (`blocker` | `warning` | `note`), `subjectId` (draft binding id), `affected[]` (runtime record indices or draft ids), `reason`, and `remedies[]` from `{ choose_another_chord, replace_affected, keep_both_not_allowed, confirm_overlap, use_physical_key, use_symbol_key }`.

| Category | Rule | Severity |
|---|---|---|
| `draft_duplicate` | Two desired managed bindings share `(identity, phase)`. | blocker |
| `exact_conflict` | A desired binding shares `(keyboard, identity, press)` with a remaining runtime record in submap `""`. | blocker |
| `alias_conflict` | A desired `code:N` binding and a remaining keysym record, or the reverse, resolve to the same level-1 keysym on the current keymap (`exact_current_keymap`). | blocker |
| `possible_alias` | Same as above but the keymap is unavailable, or the compositor has more than one layout configured and `resolve_binds_by_sym` is false, or the keyboards disagree on layout. | warning, `confirm_overlap` |
| `stack_collateral` | A draft disable removes more than one runtime record. Lists all of them. | warning, shown in the confirmation |
| `phase_pair` | A desired press binding lands on a key that has only a release binding, or the reverse (Voxtype `F9` shape). Not a conflict, but replacing either half removes both. | note |
| `submap_shadow` | Same identity exists in a non-empty submap, or a `submap_universal` record. | warning |
| `wildcard_overlap` | A remaining record with `ignore_mods`, `separate`, or `catchall` in submap `"" ` matches the key regardless of modifiers. Only header letters can reveal this; when the letter is present the warning fires. | warning |
| `device_scope_unknown` | A remaining exact match has an unmapped header letter, so it may be device-scoped. Treated as `exact_conflict` (blocker) because unknown scope must not read as free. | blocker |
| `layout_dependent` | The desired key is a keysym that is not a Latin letter, digit, function key, navigation key or XF86 key, and more than one layout is configured. | warning, `use_physical_key` |
| `shifted_digit` | The desired chord includes SHIFT and a digit keysym. On layouts where digits need SHIFT this will not fire. | warning, `use_physical_key` |
| `unbind_target_missing` | A draft disable's identity has no runtime record and no catalog entry. | blocker (`keybindings_unbind_target_missing`) |
| `pointer_or_switch_unrelated` | Not a finding. Pointer and switch domains never conflict with keyboard identities even when text looks alike (`mouse:272` versus `272`). Documented so nobody adds it. | none |

A blocker disables the apply bar. A warning requires the user to tick the confirmation in the review step (`ApplyBar` already supports required confirmations for non-reversible operations; this reuses the same control). Notes are informational.

## Managed model schema

`schemas/keybindings-model-v1.json`, `additionalProperties: false` at every level.

```text
Model
  schemaVersion   integer, const 1
  bindings        Binding[]      ids unique across bindings and disabled
  disabled        Disable[]

Binding
  id              string, UUID v4, lowercase
  enabled         boolean
  chord           Chord
  description     string, 1..160 code points, no code point < 0x20 or == 0x7f
  action          Action
  flags           Flags

Chord
  sourceKeys      string, 1..128, the rendered spelling; validate() re-derives it from
                  modifiers + key and rejects a mismatch (keybindings_chord_grammar)
  modifiers       array of enum ["SUPER","CTRL","ALT","SHIFT"], unique, any order on disk;
                  rendered in the canonical order
  key             { "kind": "keysym", "value": string }     canonical xkbcommon name, or
                  { "kind": "code",   "value": integer 8..255 }

Action
  type            const "exec"
  command         string, 1..4096 bytes UTF-8, no NUL, no code point < 0x20 except tab
  catalogId       string | null      informational only; the command is frozen at creation

Flags            all booleans, all required
  locked, release, repeating, nonConsuming, autoConsuming, bypass
  constraint: not (nonConsuming and autoConsuming)     keybindings_flag_combination

Disable
  id              string, UUID v4
  sourceKeys      string, the exact `keys` string from the catalog entry or managed binding
                  being disabled; rendered verbatim into hl.unbind()
  target          { "kind": "omarchy_default" | "managed",
                    "module": string (catalog module name or ""),
                    "description": string,
                    "identity": string (serialized identity, for display and drift checks) }
  reason          enum ["disabled", "replaced"]
  replacedBy      string (Binding id) | null
```

Load rules: a file with `schemaVersion` greater than 1 is refused with `unsupported_config` and the page becomes read-only; there is no best-effort rewrite. A missing file is an empty model. Any schema violation returns `validation_failed` with the JSON pointer of the first failing field. Commands are shown verbatim in the review diff with a "runs as your user, plain text in your config" note; the module never runs them.

Draft schema (`keybindings-draft-v1.json`): `{ "schemaVersion": 1, "expectedRevision": string, "model": Model }`. The draft is the whole desired model. The page edits `draft.model` and the planner diffs it against the stored model.

Desktop modes: a mode file holds a complete copy of this Model inline under `members.keybindings`. When a mode applies, the modes module submits `{ "schemaVersion": 1, "expectedRevision": <this module's revision>, "model": members.keybindings }` as this module's draft, which is a whole-document replacement handled by the same `validate`, `plan` and `verify` as a page edit. There is no preset store and no reference by id.

## Lua rendering

### Block layout

```lua
-- BEGIN OMARCHY CUSTOMIZATION CENTER BINDINGS v1
-- Rendered from ~/.config/omarchy/customization-center/keybindings.json by the
-- Customization Center. Edit there; this block is rewritten on every apply.
-- cc:b51ebad9-3854-4fd6-8904-d2986d9bd24c
hl.unbind("SUPER + SPACE")
-- cc:8b56c5e2-2dce-4d27-9681-7d47d6a3f6ee
o.bind("SUPER + SHIFT + R", "Open project terminal", "xdg-terminal-exec")
-- cc:2f3b6d7c-0f4e-4a4d-9d1a-6f0a4d8f3c21
o.bind("F9", "Stop dictation", "voxtype record stop", { release = true })
-- END OMARCHY CUSTOMIZATION CENTER BINDINGS v1
```

Rules:

1. All unbinds first, then all enabled binds. Disabled bindings (`enabled: false`) are not rendered. Order within each group: by `sourceKeys` then by `id`, so output is deterministic and independent of JSON array order.
2. Each statement is preceded by `-- cc:<id>`. The comment is never parsed back; the JSON is canonical.
3. `o.bind` argument order is `keys, description, command[, opts]`. `opts` is emitted only when at least one flag is true, with keys in this fixed order and Lua names: `locked`, `release`, `repeating`, `non_consuming`, `auto_consuming`, `bypass`. Each is `name = true`.
4. `o.bind` rather than `hl.bind`: helpers are loaded before the user file regardless of `omarchy_default_bindings` (`omarchy.lua:7`), and `o.bind` is the form the stock file teaches (`config/hypr/bindings.lua:16`).
5. An empty model (no enabled bindings and no disables) removes the block and the single blank line the center added before it, so a user who undoes everything gets their file back byte for byte. Core's `ReplaceManagedBlock(..., body=None)` does the removal.
6. Markers are matched as whole lines. Zero pairs: append `"\n" + block` if the file does not end with a newline, `block` otherwise, always ensuring exactly one blank line between existing content and `BEGIN`. Exactly one `BEGIN` followed by exactly one `END`: replace from the `BEGIN` line through the `END` line inclusive. Anything else (`BEGIN` without `END`, `END` first, two `BEGIN`s, a `v2` marker) is `keybindings_markers_ambiguous` with line numbers; apply is blocked until the user fixes the file by hand.
7. Drift: the expected block is rendered from the stored JSON and compared byte for byte with the block found in the file. A mismatch is `keybindings_managed_drift`; the page offers "Rewrite block from JSON" (a normal plan whose only change is the block) or "Forget managed records" (back up and delete the JSON, leaving the file alone). Nothing is merged.

### Lua string literal

```python
def lua_string(value: str) -> str:
    if "\x00" in value:
        raise RenderError("keybindings_control_character")
    out = ['"']
    for ch in value:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or o == 0x7F:
            out.append("\\%03d" % o)      # always three digits so a following digit is never absorbed
        elif 0xD800 <= o <= 0xDFFF:
            raise RenderError("keybindings_invalid_unicode")
        else:
            out.append(ch)                # raw UTF-8 on write; Lua strings are byte strings
    out.append('"')
    return "".join(out)
```

Double-quoted literals only. Long brackets are not used because choosing a non-colliding level is one more thing to test. Validation already rejects control characters in descriptions and chords and everything except tab in commands, so the numeric escape branch exists for completeness and is unit-tested anyway. The file is written as UTF-8 with `\n` line endings; a `bindings.lua` that contains `\r\n` is left as it is outside the block and the block itself uses `\n` (Lua accepts mixed endings; a test covers it).

## Syntax check

### Capability

`luacheck.capability(ctx)` looks for, in order, `luac5.4`, `luac`, and records `{ available, argv, versionLine }` from `[cmd, "-v"]`. Reason for the order: `/usr/bin/Hyprland` links both `liblua5.4` and `liblua.so.5.5`; 5.4 is the stricter parser for the constructs this module emits, so a 5.4 pass is the safer preflight. If neither exists, `capabilities.edit.available` is false with reason `luac_missing` and the page is read-only. The syntax check is a preflight; `hyprctl reload` plus `configerrors` is the real verdict.

### Flow

```text
check_candidate(ctx, candidate_bytes):
  1. tmp = ctx.paths.private_tmpfile(suffix=".lua")      ; core: 0600 under $XDG_RUNTIME_DIR/omarchy-customization-center/
  2. write candidate_bytes; fsync
  3. result = ctx.commands.run(luac_argv + ["-p", "--", tmp], timeout_s=5, capture_limit=64 KiB)
  4. unlink tmp (also on exception)
  5. exit 0            -> ok
     exit != 0         -> keybindings_lua_syntax, with stderr rewritten so the temp path reads as
                          "bindings.lua" and the line number is preserved
     timeout           -> timeout
```

The candidate is the complete future `bindings.lua`, not just the block, so a handwritten unterminated string above the block is caught too, and reported as "outside the managed block" when the failing line is above `BEGIN` or below `END`. `luac -p` parses only; it never executes the user's file. The backend never calls `dofile` or `lua` on the user's file.

## Backend module interface

`MODULE.id = "keybindings"`, `MODULE.schema_version = 1`.

### capabilities(ctx)

```json
{
  "hyprctl": { "available": true, "version": "0.56.2" },
  "inventory": { "available": true, "jsonTrusted": true },
  "keymap": { "available": true, "layout": "ch", "variant": "de_nodeadkeys", "options": "numpad:pc", "layouts": 1, "resolveBindsBySym": false },
  "catalog": { "available": true, "lua": ["lua5.4"], "omarchyPath": "/usr/share/omarchy", "digest": "sha256:..." },
  "luac": { "available": true, "argv": ["luac5.4"], "version": "Lua 5.4.8" },
  "bindingsFile": { "present": true, "path": "/home/u/.config/hypr/bindings.lua", "markers": "absent" },
  "edit": { "available": true, "reasons": [] }
}
```

`edit.available` requires `hyprctl.available`, `bindingsFile.present`, `luac.available`, and `markers in {"absent", "present"}` (from core's `managed_block.inspect(bytes, "BINDINGS", 1)`). The module does not probe the Omarchy reload guard; core's `HyprctlReload` refuses with `runtime_unavailable` while `omarchy-hyprland-reload-guard paused` reports paused, and the page shows that as a retry-later banner. A missing `bindings.lua` is `unsupported_config` with the remedy text "run `omarchy-refresh-config hypr/bindings.lua`", because `hyprland.lua:48` requires it unconditionally and the config is already broken without it.

### status(ctx)

`schemas/keybindings-status-v1.json`:

```text
revision            string
capabilities        (as above)
records[]           RuntimeRecord { index, headerFlags[], modmask, keyFieldRaw, keyToken, keycode, submap,
                    catchall, description, dispatcher, arg, flags{locked, release, repeating, longPress,
                    nonConsuming, autoConsuming, mouse, submapUniversal, allowInputCapture, unknownLetters[]},
                    flagSource "json"|"header", domain, identity, phase, display, parseError|null,
                    classification "managed"|"omarchy_default"|"external", confidence, managedId|null,
                    catalog { module, sourceFile, sourceLine, keys, dispatcherKind, command|null }|null,
                    externalReason|null, stackId|null, stackSize, editable { edit, disable, replace },
                    readOnlyReason|null }
disabledDefaults[]  synthetic rows for managed disables whose target still exists in the catalog
orphanedDisables[]  managed disables whose target no longer exists (after an Omarchy upgrade)
model               the stored Model (or empty)
managedBlock        { "state": "absent"|"present"|"duplicate"|"unterminated"|"reversed"|"nested" (core managed_block.inspect),
                      "drift": bool, "beginLine", "endLine", "problems"[] }
switches[]          from hyprctl devices
warnings[]          keybindings_binds_json_untrusted, keybindings_catalog_unavailable, keybindings_keymap_unavailable, ...
```

Status never writes. It reads the two owned files, runs the probes above, runs the catalog harness (cached per `omarchyPath` mtime and digest), classifies, and groups stacks.

### validate(ctx, draft)

Pure. Steps: schema-check the draft; re-derive every `chord.sourceKeys` and compare; resolve every keysym through the keymap snapshot in `ctx`; check flag combinations; run the conflict classifier against `ctx`'s inventory snapshot; render the block and run `lua_string` on every field to surface render errors early. Returns `{ ok, blockers[], warnings[], notes[], normalizedDraft, renderedBlock }`. It does not run `luac` (that needs a file) and does not touch the filesystem.

### plan(ctx, draft, status)

1. `validate`; any blocker returns `validation_failed` with the findings.
2. Compare `draft.model` with `status.model`. If equal and the block is not drifted, return an empty plan with `noop: true`.
3. Render `keybindings.json` bytes (canonical) and the block.
4. Splice into the current `bindings.lua` bytes (in memory) and run `check_candidate`. Failure returns `validation_failed` with `keybindings_lua_syntax`.
5. Capture `baselineConfigErrors` from `hyprctl -j configerrors`; core's `HyprctlReload` diffs against it.
6. Build the operation list:

```text
1. EnsureDirectory(~/.config/omarchy/customization-center)
2. WriteFileAtomic(~/.config/omarchy/customization-center/keybindings.json, json_bytes, 0o644)
3. ReplaceManagedBlock(~/.config/hypr/bindings.lua, begin, end, body)
                                                    ; begin/end from core managed_block.markers("BINDINGS", 1);
                                                    ; body = None when the model is empty
4. HyprctlReload(config_only=True)                  ; bindings only; skips the monitor pass
```

Every operation carries a human summary ("Add SUPER + SHIFT + R: Open project terminal", "Disable Omarchy default SUPER + SPACE: Omarchy menu, also removes: ..."). The plan also returns `fileDiff` (unified diff of `bindings.lua`), `affected[]` (runtime record indices the verify step will check), `expectedAfter` (list of `(identity, phase, description)` that must exist and list that must not), `baselineConfigErrors`, `confirmations[]` (the warnings the user must acknowledge), and `expected_revision`.

### verify(ctx, plan, status_after)

Runs after the executor has performed the operations. `status_after` is a fresh `status()`.

```text
verify(ctx, plan, status_after):
  1. core's HyprctlReload already failed the transaction on a new config error; re-read hyprctl -j configerrors
     once more and fail keybindings_config_errors if a new entry appeared since (auto-reload after the write)
  2. block in status_after: state must be "present" (or "absent" when body was None), drift must be false,
     bytes outside the block must equal the pre-apply bytes outside the block
                                                     -> fail keybindings_block_mismatch
  3. for each (identity, phase, description) in plan.expectedAfter.present:
       count records in status_after with that identity+phase+description in submap ""
       count != 1                                    -> fail keybindings_runtime_mismatch
  4. for each identity in plan.expectedAfter.absent:
       any record with that identity in submap ""    -> fail keybindings_runtime_mismatch
       (targets re-bound by a managed binding are in "present", not "absent")
  5. records not in plan.affected are not compared; unrelated changes (a Voxtype install, a
     selection layer opening) are reported as warnings, never as failure
  6. ok with status_after.revision
```

Steps 3 and 4 poll up to 5 times, 200 ms apart, before declaring failure, in case `hyprctl reload` returns before the new binds are registered. Whether reload is synchronous from the client's point of view is unverified.

On failure the executor runs the inverses: `HyprctlReload` (see the core change below), restore `bindings.lua`, restore or delete `keybindings.json`, then reload again, then the module's `verify` runs once more against the pre-apply `expectedAfter` (which the plan stores as `expectedBefore`). A second failure is `rollback_failed` with the backup paths.

### Reload and the auto-reload race

Hyprland reloads on its own when it sees the file change (`Variables.md:441`), so the new block may be live before `HyprctlReload` runs, and a broken candidate could be live before the executor reaches verification. The module handles this in order:

1. Core's `HyprctlReload` refuses with `runtime_unavailable` while `omarchy-hyprland-reload-guard paused` reports paused. An Omarchy update is mid-flight; its resume hook will reload anyway and would race with this transaction. The executor's rollback walk then restores both files.
2. The candidate is syntax-checked before any write, so the worst case of an early auto-reload is a semantically wrong binding, never a parse error that blanks the config.
3. The executor backs up both files before the first write (contract), so restoration never depends on anything written during the transaction.
4. `HyprctlReload` runs after the write whether or not auto-reload already fired. Two reloads are harmless; the explicit one is what verification waits on.
5. The module does not toggle `misc.disable_autoreload`. That would require restoring the user's value on every exit path, including a crashed backend, and the reload guard already owns that flag during updates.
6. On rollback, restoring `bindings.lua` triggers auto-reload again; the executor skips the reload inverse in place and runs exactly one `HyprctlReload` after the last file-restoring inverse (amendment B), which makes the restored state definite even when auto-reload is disabled.

## Chord capture

`components/ChordCapture.qml` is a modal item inside the page with `focus: true` and `Keys.onPressed`/`Keys.onReleased` handlers. It does nothing outside the page: no backend calls, no submap, no temporary bind. What it records per key press is `{ qtKey, text, modifiers, nativeScanCode, nativeVirtualKey, isAutoRepeat }`.

Behaviour:

1. On open, show "Press the shortcut" with live modifier chips. Standalone modifier presses (`Qt.Key_Shift`, `Key_Control`, `Key_Alt`, `Key_Meta`, `Key_Super_L/R`, `Key_Hyper_L/R`, `Key_AltGr`, `Key_CapsLock`, `Key_NumLock`) update chips and never commit.
2. `event.isAutoRepeat` events are ignored.
3. `Escape` with no other modifier cancels. `Backspace` with no modifier clears. Both are stated on screen, and both are therefore not capturable; the manual field accepts them.
4. The first non-modifier key press commits `{ modifiers: from event.modifiers, keyName: mapped, keycode: nativeScanCode, keysym: nativeVirtualKey }` into the draft chord. Only SUPER (`Qt.MetaModifier`), CTRL (`Qt.ControlModifier`), ALT (`Qt.AltModifier`), SHIFT (`Qt.ShiftModifier`) map. `Qt.KeypadModifier` is ignored. `Qt.GroupSwitchModifier` (AltGr) makes the capture fail with reason `unsupported_modifier`.
5. The committed value goes to `ChordField` as `sourceKeys` text plus hidden `keycode` and `keysym`. `validate` (through the normal draft round trip) resolves `keysym` via `xkbcli how-to-type --keysym 0x<hex>` and prefers that canonical name over the QML table when both exist. When `keycode > 0`, the level-1 keysym of that keycode on the active keymap is what is proposed, because that is how Omarchy's own shifted chords are written (`SUPER + SHIFT + F`, `applications.lua:4`). The shifted keysym is shown as an alternative in the details.
6. A "Use physical key (code:N)" toggle appears when `keycode >= 8`. It writes `code:<keycode>` as the key. The toggle carries the note that the binding then ignores layout.
7. If no key event arrives within 10 s, the field shows "Hyprland kept that shortcut. Type it instead." with a link to the manual field and `wev` mentioned by name.
8. Before capture starts, the dialog says that pressing a shortcut Hyprland already owns will run that shortcut, because the compositor handles global binds before the overlay sees anything.

Qt to Hyprland name table (the fallback when the keysym cannot be resolved; a unit test asserts every entry resolves through `xkbcli`):

| Qt key | Name emitted |
|---|---|
| `Qt.Key_A` .. `Qt.Key_Z` | `A` .. `Z` |
| `Qt.Key_0` .. `Qt.Key_9` | `0` .. `9` (with the `shifted_digit`/`layout_dependent` warnings when applicable) |
| `Qt.Key_F1` .. `Qt.Key_F35` | `F1` .. `F35` |
| `Key_Space`, `Key_Return`, `Key_Enter`, `Key_Tab`, `Key_Backtab`, `Key_Escape`, `Key_Backspace`, `Key_Delete`, `Key_Insert` | `space`, `Return`, `KP_Enter`, `Tab`, `ISO_Left_Tab`, `Escape`, `BackSpace`, `Delete`, `Insert` |
| `Key_Home`, `Key_End`, `Key_PageUp`, `Key_PageDown`, `Key_Left`, `Key_Right`, `Key_Up`, `Key_Down` | `Home`, `End`, `Prior`, `Next`, `Left`, `Right`, `Up`, `Down` |
| `Key_Print`, `Key_ScrollLock`, `Key_Pause`, `Key_Menu` | `Print`, `Scroll_Lock`, `Pause`, `Menu` |
| `Key_Comma`, `Key_Period`, `Key_Slash`, `Key_Semicolon`, `Key_Apostrophe`, `Key_BracketLeft`, `Key_BracketRight`, `Key_Backslash`, `Key_Minus`, `Key_Equal`, `Key_QuoteLeft` | `comma`, `period`, `slash`, `semicolon`, `apostrophe`, `bracketleft`, `bracketright`, `backslash`, `minus`, `equal`, `grave` |
| `Key_VolumeUp`, `Key_VolumeDown`, `Key_VolumeMute`, `Key_MicMute`, `Key_MediaPlay`, `Key_MediaPause`, `Key_MediaTogglePlayPause`, `Key_MediaNext`, `Key_MediaPrevious`, `Key_MediaStop` | `XF86AudioRaiseVolume`, `XF86AudioLowerVolume`, `XF86AudioMute`, `XF86AudioMicMute`, `XF86AudioPlay`, `XF86AudioPause`, `XF86AudioPlay`, `XF86AudioNext`, `XF86AudioPrev`, `XF86AudioStop` |
| `Key_MonBrightnessUp`, `Key_MonBrightnessDown`, `Key_KeyboardBrightnessUp`, `Key_KeyboardBrightnessDown`, `Key_Calculator`, `Key_PowerOff`, `Key_Eject`, `Key_TouchpadToggle` | `XF86MonBrightnessUp`, `XF86MonBrightnessDown`, `XF86KbdBrightnessUp`, `XF86KbdBrightnessDown`, `XF86Calculator`, `XF86PowerOff`, `XF86Eject`, `XF86TouchpadToggle` |
| anything else | no table name; the backend resolves `nativeVirtualKey`, and if that fails the field shows "unrecognized key, type its name" |

Assumption to confirm on first run, with a QML test that presses Tab and expects `nativeVirtualKey == 0xff09` and `nativeScanCode == 23`: on Qt Wayland, `nativeVirtualKey` is the XKB keysym and `nativeScanCode` is the XKB keycode (evdev + 8), which is the number `code:` expects.

Not capturable in this release: any chord Hyprland already binds globally (the compositor consumes it first; this includes every Omarchy default, so replacing a default always goes through the manual field or the row's own Replace action, which pre-fills the chord); mouse buttons and wheel; switches; long press, click and drag phases; chords involving AltGr or Caps as modifiers; keys on a specific keyboard (Qt gives no device identity); `Escape` and `Backspace` alone. The keyboard-shortcuts-inhibit protocol would let the overlay receive bound chords (Hyprland's `bypass` flag exists to defeat it, `Binds.md:92`), but neither Quickshell nor Qt exposes a way to request it that I could verify, so it is out.

## Page

`modules/keybindings/Page.qml` implements the page contract: `moduleId`, `status`, `draft`, `capabilities`, `requestPlan()`, `requestApply()`, `requestReset()`, `requestNavigate()`, `focusFirst()`, and `handlePayload(payload)`. It never calls `ccctl`; reads go through `BackendClient`.

`handlePayload` accepts `{ "select": "<chord text or managed id>" }` (scroll to and open the matching row, resolved through the `normalize_chord` query below) and `{ "action": "add", "chord": "<text>", "command": "<text>" }` (open the add form pre-filled, nothing applied). Unknown keys are ignored.

Queries the page uses through `BackendClient.query`, all read-only and lock-free:

- `ccctl query keybindings normalize_chord --text "<chord>"`: returns `{ sourceKeys, identity, display, keyKind, findings[] }` or the grammar error. `ChordField` calls it, debounced, on every edit.
- `ccctl query keybindings catalog_search --text "<query>"`: returns matching entries from `data/action-catalog.json` and the Omarchy default catalog (title, command, module, source line). `ActionPicker` calls it.

Layout: search field; filter chips (`All`, `Omarchy defaults`, `Managed`, `Other`, `Media`, `Pointer and switches`, `Read-only`, `Conflicts`); the table (chord, description, action or dispatcher kind, source badge, flags, editability); a details drawer; the shared apply bar. Row actions: `Add binding` (toolbar), `Edit`, `Remove`, `Disable default`, `Replace default`, `Restore default`, `Copy details`, `Open bindings.lua` (through the terminal handoff of the defaults module, not a direct exec), `View source` (path and line from the catalog).

State machine:

| State | Entered when | Apply bar | Row actions |
|---|---|---|---|
| `loading` | page opened, `status` is null | hidden | none |
| `unsupported` | `capabilities.hyprctl.available == false` or model `schemaVersion > 1` | hidden | copy details |
| `read_only` | `capabilities.edit.available == false` (luac missing, file missing, markers ambiguous, guard paused) | hidden, reason banner | copy, view source |
| `drift` | `managedBlock.drift == true` | shows "Rewrite block" and "Forget managed records" only | read-only |
| `clean` | status loaded, draft equals stored model | disabled | all per `editable` |
| `dirty` | draft differs | enabled when no blocker; blocker list shown | all |
| `reviewing` | `requestPlan()` returned; the shared review dialog shows the diff, affected rows, confirmations | apply enabled once every confirmation is ticked | none |
| `applying` | apply in flight | disabled, progress | none |
| `applied` | journal state `committed` | reset to `clean` after status refresh; toast with transaction id and Undo | all |
| `failed_restored` | journal state `rolled_back` with reason `operation` or `verification` | banner with the failing step and "Show journal" | all |
| `rollback_failed` | journal state `rollback_failed` | persistent banner with backup paths; page read-only until status shows a sane file | copy details |
| `stale` | apply returned `stale_revision` | "Reload and keep draft" / "Discard draft" | none |

The add and edit forms: `ChordField` (manual text with the `normalize_chord` echo and a Capture button), `ActionPicker` (curated entry from `data/action-catalog.json` or a custom command, the latter with the trust note), description, and the six flag toggles with one-line explanations from `Binds.md:79-92`. Replace pre-fills the chord from the default and creates a `Disable{reason: "replaced", replacedBy}` plus a `Binding`. Disable creates a `Disable{reason: "disabled"}`. Restore removes the `Disable`; it never copies the default into a managed bind.

`data/action-catalog.json` entries: `{ id, title, command, category, mirrors: "default/hypr/bindings/utilities.lua:1" }`. The initial list mirrors the exec commands in the default files (`omarchy-menu toggle <name>`, `omarchy-shell shell toggle omarchy.<panel>`, `omarchy-capture-screenshot`, `omarchy-capture-text`, `omarchy-system-lock`, `omarchy-toggle-<name>`, `omarchy-launch-<app>`, `omarchy-menu-keybindings`, and the audio and brightness commands). A test checks that every command's first word exists under the fixture snapshot's `bin/` or is on an allowlist (`pkill`, `eject`, `hyprpicker`, `omacalc`).

## Error codes

Shared: `stale_revision`, `validation_failed`, `runtime_unavailable`, `unsupported_config`, `rollback_failed`, `locked`, `timeout`, `malformed_output`, `nonreversible_requires_confirmation` (not produced by this module; every operation here has an inverse).

Module codes, all prefixed `keybindings_`: `binds_unparseable`, `binds_truncated`, `binds_continuation` (warning), `binds_json_untrusted` (warning), `catalog_unavailable` (warning), `keymap_unavailable` (warning), `bindings_file_missing`, `markers_ambiguous`, `managed_drift`, `chord_grammar`, `unknown_keysym`, `unsupported_modifier`, `unsupported_key`, `flag_combination`, `control_character`, `invalid_unicode`, `draft_duplicate`, `exact_conflict`, `alias_conflict`, `unbind_target_missing`, `lua_syntax`, `config_errors`, `block_mismatch`, `runtime_mismatch`.

## Test matrix

Fixtures live in `modules/keybindings/tests/fixtures/`. Command stubs record argv and environment and are the only way tests reach `hyprctl`, `xkbcli`, `lua`, `luac`, `omarchy-hyprland-reload-guard`. Every test runs with isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_RUNTIME_DIR`.

| Area | Fixture | Asserts |
|---|---|---|
| Plain parser | `binds/plain-0.56.2-lua.txt` (the 88-record live capture) | 88 records, field values, `bindle` and `bindld` letters, `key: SUPER + CTRL + code:94` splits to `code:94` with modmask 68 |
| Plain parser | `binds/plain-legacy-keycode.txt` (from `keybindings-menu-test.sh:132-140`) | empty key + keycode 49 becomes `code:49` |
| Plain parser | `binds/plain-exec-dispatcher.txt` | `dispatcher: exec`, `arg` with commas and quotes preserved |
| Plain parser | `binds/plain-empty.txt`, `binds/plain-truncated-eof.txt`, `binds/plain-missing-blank-line.txt` | zero records versus parse error; last record closed at EOF; back-to-back headers |
| Plain parser | `binds/plain-continuation.txt`, `binds/plain-unknown-field.txt`, `binds/plain-unknown-letters.txt` (`bindrmn`) | continuation warning; `extra` retained; unknown letters make the row read-only |
| Plain parser | `binds/plain-submap-catchall-switch.txt` | domains `switch`, `catchall`, non-empty submap classified read-only |
| JSON | `binds/json-0.56.2.json` | accepted against its plain twin; `submap_universal` string parsed; `repeat` copied as `repeating` |
| JSON | `binds/json-count-mismatch.json`, `binds/json-misaligned.json`, `binds/json-wrong-types.json`, `binds/json-invalid.txt` | rejected with `binds_json_untrusted`; plain rows intact; header flags used |
| Keymap | `keymap/us.xkb`, `keymap/ch-de_nodeadkeys.xkb`, `devices/devices-0.56.2.json`, `devices/devices-two-layouts.json` | keycode 10 maps to `1` on us; `section` on keycode 49 on ch; two layouts raise the warning; main keyboard chosen |
| Keymap | `xkbcli/how-to-type-Tab.txt`, `xkbcli/how-to-type-unknown.txt` | canonical name and number parsed; exit 2 handled |
| Chords | table-driven in `test_chords.py` | every case in "Normalization algorithm": aliases, duplicates, empty parts, `code:` bounds, `mouse:`/`switch:`/`catchall` refusal, `tab`/`TAB`/`Tab` resolving to the same identity, `COMMA` resolving to `comma`, render spelling `W`, `Return`, `comma`, display `~` |
| Catalog | `omarchy-default-hypr-71b0887c/` (snapshot of `default/hypr`) with `PATH` stubs for `voxtype` present and absent, and `preinstalls-removed` present and absent | every module represented; loops expand (`SUPER + code:10` .. `code:19`); `F9` press and release; `ALT + TAB` twice; table dispatchers resolve to `omarchy-launch-terminal`; `sourceFile:sourceLine` present; selection-layer binds absent |
| Classification | `status/managed-and-defaults.json` | managed unique match ignores `arg`; default `exact` versus `probable`; identical copy labelled "matches"; ambiguous pairs `ambiguous_match`; `code:201` shown, not hidden |
| Conflicts | `conflicts/*.json` one per category | each category fires exactly once with the documented severity; `pointer_or_switch_unrelated` never fires; the two `ALT+TAB` stacks and `F9` pair from Omarchy's test produce `stack_collateral`/`phase_pair` and no blocker; `SUPER + 1` versus `SUPER + code:10` is `alias_conflict` on us and `possible_alias` without a keymap (ported from `hyprland-binding-conflicts-test.sh:178-189`) |
| Model | `model/v1-minimal.json`, `model/v1-full.json`, `model/v2-future.json`, `model/duplicate-ids.json`, `model/bad-flags.json`, `model/sourcekeys-mismatch.json`, `model/control-chars.json` | load, refuse, pointer paths |
| Render | golden `render/full.lua`, `render/unbinds-only.lua`, `render/empty.lua` | deterministic order; opts order; block removal on empty |
| Lua literal | table in `test_render.py` | quotes, backslashes, `\n`, `\r`, `\t`, `\001` followed by `2`, DEL, `é`, emoji, marker text inside a description, lone surrogate rejected, NUL rejected |
| Markers | `bindings/stock.lua` (the packaged file), `no-markers-no-trailing-newline.lua`, `one-block.lua`, `two-begins.lua`, `end-before-begin.lua`, `begin-only.lua`, `v2-marker.lua`, `edited-block.lua`, `crlf.lua` | append separator rules; replace range; ambiguity errors with line numbers; drift detection; property test that every byte outside the range is unchanged for 1000 random files |
| luac | stub returning success, syntax error at line N, timeout | path rewriting, line attribution inside/outside the block, `timeout` |
| Planner | draft cases | noop plan; operation order and arguments exact; `body: null` for empty model; `expectedAfter` present/absent sets; a modes-shaped draft (`model` copied from `members.keybindings`) plans identically to a page draft |
| Verify | `verify/after-ok.json`, `after-config-error.json`, `after-missing-bind.json`, `after-unbind-still-present.json`, `after-unrelated-drift.json`, `after-block-changed.json` | each result; polling count; unrelated drift is a warning |
| Integration | executor with stubs and a real temp `bindings.lua` | success writes both files and reloads once (plus the config-only argv when enabled); injected failure at each of: JSON write, block write, reload, configerrors, inventory after reload, verify; each restores both files byte for byte, reloads, and journals; a pre-absent JSON is deleted on rollback; a paused reload guard makes core's `HyprctlReload` refuse and the walk restores both files; `stale_revision` when `bindings.lua` changes between plan and apply |
| QML | `qml/tst_capture.qml`, `qml/tst_page_states.qml` | every Qt table entry maps; auto-repeat ignored; modifier-only never commits; Escape cancels; AltGr refused; timeout message; each page state renders its allowed actions and nothing else; no apply from selection changes |
| Live (manual, documented in `tests/manual.md`) | a real Omarchy session | add a free chord and see it after logout; replace `SUPER + SPACE` and restore it; disable a `code:` default and verify it is gone (this is the check that `hl.unbind` on a `code:` string works, which is unverified); break the block by hand and confirm drift; edit above the block and confirm the bytes survive; run with `hyprctl -j binds` stubbed to garbage; run under `omarchy-hyprland-reload-guard pause` and confirm refusal |

## Delivery order

1. K0: schemas, error codes, fixtures from the live capture and Omarchy tests, `inventory.py` and `chords.py` with their tests. Exit: the 88-record fixture round-trips and JSON rejection keeps every row.
2. K1: `keymap.py`, `catalog.py`, `classify.py`; `status()` end to end; read-only page. Exit: the page matches `hyprctl binds` on a live Omarchy session and every default row shows its source file and line.
3. K2: `model.py`, `render.py`, `luacheck.py`, marker handling on top of core `managed_block`. Exit: golden renders and the outside-block property test pass.
4. K3: `conflicts.py`, `validate()`, `plan()`, forms, capture, conflict panel, Lua preview. Exit: every conflict category has a fixture and a distinct UI presentation.
5. K4: `verify()`, executor integration, rollback fault injection. Exit: every injected failure restores byte-identical files and a verified runtime, or reports `rollback_failed` with paths.
6. K5: accessibility, manual live checks, `docs/recovery.md` section for this module (how to remove the block by hand and where the backups are).

## Core services used

All of these exist in core per the contract amendments; the module adds nothing to core.

- `HyprctlReload(config_only=True)`: forward refuses while the Omarchy reload guard is paused, diffs `configerrors` against the plan baseline; inverse is deferred and run once after the last file-restoring inverse.
- `ReplaceManagedBlock(path, begin, end, body)` with `body=None` for removal, `managed_block.markers("BINDINGS", 1)` for the marker lines, and `managed_block.inspect(bytes, "BINDINGS", 1)` for status-time diagnosis.
- `WriteFileAtomic`, `EnsureDirectory`, the executor's backups, journal, lock, and startup recovery.
- `Context.cache` for keymap and catalog memoization within one `ccctl` invocation, and `ctx.paths.home` for `$HOME/.config/hypr/bindings.lua`.
- `ctx.paths.private_tmpfile(".lua")` for the `luac -p` candidate.
- `ctx.commands.run(argv, timeout_s, env_extra={"LC_ALL": "C"}, capture_limit=...)` for every subprocess.
- `ccctl query keybindings <name>` for the two page queries.

Adding this module is the `modules/keybindings/` directory plus one line in `backend/customization_center/modules/__init__.py`.

## Contract notes

- Desktop modes hold the complete managed document inline under `members.keybindings` and submit it as this module's draft (amendment I). This module has no preset store and no id-based reference; the modes segment for `keybindings` carries this module's `expected_revision` and operation ids.
- The master plan's "Test action" for bindings is not implemented for `exec` actions; see "What the first release refuses to do".
- The master plan's flat binding schema is replaced by the typed model above. A per-binding "unbind first" flag cannot express "restore the default without deleting my binding", so disables are separate records.
- The master plan's owned-file list is unchanged: managed block in `~/.config/hypr/bindings.lua`, model under `~/.config/omarchy/customization-center/`.

## Open items

- Whether `hl.unbind` compares modifiers by mask or by text, and whether it works for `code:` keys at all, is unverified. The live check in K4 settles it. Until then, disable and replace are only offered where the exact catalog or managed spelling exists, and verification treats a still-present target as failure.
- Whether Hyprland 0.56.2 prints continuation lines for multi-line descriptions is unverified; the parser tolerates both.
- Which Lua the compositor embeds (5.4 or 5.5) is unverified; `luac5.4` is preferred as the stricter preflight and `configerrors` is the verdict.
- Qt Wayland's `nativeVirtualKey`/`nativeScanCode` semantics are assumed and asserted by a first-run test.
- Header flag letters other than `d`, `l`, `e` are assumed from Hyprland's hyprlang-era flags; the parser treats any unknown letter as read-only, so a wrong assumption costs editability, not correctness.
