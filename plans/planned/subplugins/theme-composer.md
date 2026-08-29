# Theme composer

Module id: `themes`
Status: planned, verified against omarchy-fork commit `71b0887c`
Master plan section: Module 6

Every path below without a leading slash is relative to `/mnt/SSD_NVME_4TB/GitHub/omarchy-fork`. Line numbers refer to that commit.

## 1. What the module does

The composer builds a user theme under `~/.config/omarchy/themes/<slug>/` from a semantic draft, previews it inside the plugin, saves it, and activates it through `omarchy-theme-set`. The generated directory contains only data files that Omarchy already understands. Omarchy renders every application file (Hyprland, terminals, editors, btop, browsers) from its own templates at activation time. The composer never writes Lua, terminal configuration, or any file that names a program.

Decisions made in this plan, so nobody re-derives them:

- Two draft kinds. `compose` builds a theme directory. `activate` switches to an existing theme by slug and is what desktop modes use.
- The draft stores palette values and section values as strings in Omarchy's own syntax, validated by a grammar. Nested `{kind, value}` objects buy nothing because every consumer of the draft (the TOML writer, the QML preview, the diff view) wants the string.
- A `compose` draft always produces a complete `colors.toml` with the 26 canonical keys plus the two optional Hyprland border keys. Sparse palettes are a source of unresolved `{{ placeholders }}` in generated files, and the shell falls back to hardcoded colors when keys are missing (`shell/Commons/Color.qml:19-23`).
- Section overrides are all or nothing per section. `shell.<section>.toml` replaces the whole `[section]` (`bin/omarchy-theme-set-templates:309-358`), so the composer writes every key of a customized section and writes no file for a section left at "inherit".
- The in-plugin preview is a set of module-owned components fed by a resolver that runs in QML. It uses `BorderSurface` from `qs.Ui` for borders because that component takes a full border spec as a property. It does not use `Button`, `TextField`, or the other shared controls for draft samples because their fill alphas, widths, fonts, and spacing are bound to the global `Style` singleton.
- "Try in shell" is a separate, explicit, journaled transaction built from one `ShellIpc` operation whose inverse restores the running theme. It is not a hover preview and it is not `omarchy-theme-set`.
- Activation uses `omarchy-theme-set <slug>`. When the draft names a preferred wallpaper the command runs with `OMARCHY_THEME_SKIP_BACKGROUND=1` and `omarchy-theme-bg-set` sets the wallpaper afterwards. Otherwise Omarchy's own first-wallpaper choice applies.
- A slug equal to a built-in theme name is refused. `omarchy-theme-set` copies the built-in first and overlays the user directory on top (`bin/omarchy-theme-set:269-276`), so the result would inherit the built-in's hand-written `hyprland.lua`, `neovim.lua`, `vscode.json`, and icons. That is no longer a self-contained data-only theme.
- The first release refuses rename. Delete is supported for inactive user themes that the composer created or that are plain directories. Symlinked themes and git clones are read-only.

## 2. Verified behavior of Omarchy

### 2.1 What a shipped theme contains

All 22 directories under `themes/` contain `colors.toml`, `backgrounds/`, and `icons.theme`. Twenty-one contain `preview.png`, `preview-unlock.png`, and `unlock.png` (`themes/white` has only `preview.png`). Sixteen contain a hand-written `neovim.lua` and `vscode.json`. Five contain a hand-written `hyprland.lua` (kanagawa, last-horizon, lumon, retro-82, solitude). Four contain `btop.theme`, four contain `chromium.theme`, one contains `keyboard.rgb` (tokyo-night), and one contains a section override, `themes/tokyo-night/shell.lock.toml`.

No shipped theme contains a `shell.toml` or a `light.mode` file. Light themes declare `mode = "light"` in `colors.toml` (catppuccin-latte, flexoki-light, rose-pine, white, lupine).

`themes/tokyo-night/shell.lock.toml` has six keys (`text`, `placeholder`, `text-error`, `border`, `border-active`, `border-error`) and no `[lock]` header. It is a sparse section. The keys it omits (`background`, `background-alpha`, `border-alpha`, `selection`, `selection-alpha`) fall back to the defaults compiled into `shell/Commons/Color.qml:115-124`, which currently equal the template defaults. That coincidence is why a sparse file works today. The composer does not rely on it.

### 2.2 The `colors.toml` key set

Twenty of the 22 themes define exactly these 26 keys, in this order (`themes/tokyo-night/colors.toml:1-31`):

```text
mode
accent selection muted
background dark_background darker_background lighter_background
foreground dark_foreground light_foreground bright_foreground
red yellow orange green cyan blue magenta brown
bright_red bright_yellow bright_green bright_cyan bright_blue bright_magenta
```

`themes/white/colors.toml` omits `orange` and `brown`. Three themes add `hyprland_active_border` (hackerman, last-horizon, solitude), two add `hyprland_inactive_border` (last-horizon, solitude), and three add `active_border_color` and `active_tab_background`, which no template or shell file reads at this commit (`grep` over `default/themed` and `shell/` finds no consumer). The composer ignores those two.

Every value in a shipped theme is `#rrggbb` or `#RRGGBB` except the Hyprland border keys, which are gradients such as `rgba(26a269ee) rgba(2ec27eee) 45deg` (`themes/hackerman/colors.toml:17`).

### 2.3 How `colors.toml` is parsed

`bin/omarchy-theme-color` is the only parser. Every consumer goes through it (`bin/omarchy-theme-set-templates:381`, `bin/omarchy-theme-osc:14`, `bin/omarchy-theme-set-gnome:18`, `bin/omarchy-theme-set-tmux:55`).

- It reads line by line splitting on the first `=` (`bin/omarchy-theme-color:142`). A value may not contain `=`.
- A quoted value is the text between the first and the last quote character (`:146-149`). Inline comments after the closing quote are ignored.
- Keys must match `[A-Za-z0-9_-]+` (`:159`). Values must match `[A-Za-z0-9#(),._+/% -]*` (`:164`). Anything else is skipped with a message on stderr, and the corresponding `{{ placeholder }}` survives unrendered in every generated file.
- Alias and fallback resolution (`:176-281`) is listed per key in section 6.
- `mode` precedence (`:120-135`): `mode` key, then legacy `theme_type`, then a `light.mode` file beside `colors.toml`, then background luminance (`r+g+b > 382` is light), then `dark`.

The shell reads `colors.toml` separately with a regex (`shell/Commons/Color.qml:146`): `^\s*([A-Za-z0-9_-]+)\s*=\s*["']?(#[0-9A-Fa-f]{6})`. It takes `foreground`, `background`, `accent` (falling back to `color4`), `muted` (falling back to `color8`, then `foreground`), and `red` or `color1` as `urgent` (`:148-164`). A value that is not six hex digits is ignored by the shell even when `omarchy-theme-color` accepts it. This is why palette values in the composer are `#rrggbb` only.

### 2.4 Template rendering

`bin/omarchy-theme-set-templates` runs only when the staged theme has `colors.toml` (`:371`). It renders `~/.config/omarchy/themed/*.tpl` first, then `default/themed/*.tpl` (`:375`), and never overwrites a file that already exists in the staging directory (`:396`). So a hand-written `shell.toml` in a theme wins over the template, and a user template with the same output name wins over a built-in template.

The 17 built-in templates and the palette keys they need are in section 6. Two are Lua (`hyprland.lua.tpl`, `gum_env.lua.tpl`, and `neovim.lua.tpl` makes three); four are terminal configs; the rest are color files. All of them are generated from the palette, which is what lets a data-only theme still retint every application.

Section overrides run last (`:404`). For each `shell.<section>.toml` in the staging directory, `apply_shell_section_override` (`:309-358`) strips an optional `[section]` header from the override, removes the existing `[section]` block from the rendered `shell.toml`, and appends the override body under a fresh `[section]` header. The section name comes from the file name and must match `[A-Za-z0-9_-]+` (`:319`). Nothing merges at key level.

Placeholders in a generated file that survive rendering stay as literal `{{ name }}` text. There is no error. `test/cli:422-425` greps for this in the upstream tests, and the composer's verify step does the same.

### 2.5 The `shell.toml` parser in the shell

`shell/Commons/Color.qml:178-199` parses `shell.toml` with four regexes per line:

- section header `^\[([A-Za-z0-9_-]+)\]\s*(#.*)?$`
- quoted string `key = "…"` where the content may not contain `"` or `'`
- bare number `-?\d+(?:\.\d+)?`
- bare width list of two to four numbers
- bare word `[A-Za-z][A-Za-z0-9_-]*` (this is how `true`, `false`, and role names parse)

Values are kept as strings; readers coerce. `Style.applyShellValues` (`shell/Commons/Style.qml:384-440`) reads `[font]` with `parseInt`, `[bar]` with `parseInt` for `size-horizontal` and `size-vertical` and a boolean parser for `scale-with-font` (`:405-411`), `[spacing]` with `parseFloat`, and passes `[controls]` (or the legacy `[style]`) through as strings. No other `[bar]` key reaches `Style` even though `Style.bar` has `iconSlot`, `iconCanvas`, `iconFont`, and `statusSlot` properties (`:344-347`). Those four are not theme-controllable.

A machine-level `~/.config/omarchy/shell.toml` is parsed into `userShellValues` and merged over the theme's values on every change (`Color.qml:204-210, 242-253`). `omarchy-display-text-size` writes `[font] base-size` there (`bin/omarchy-display-text-size:26, 55-80`). A theme cannot override it.

### 2.6 Surface roles, borders, and controls

Every surface object in `Color.qml:73-133` composes a color key with its `-alpha` companion. Border tokens accept a solid color, a gradient, a bare role (`foreground`, `text`, `accent`, `urgent`, `muted`, `background`, `transparent`, `Color.qml:55-60`), or a dotted reference to another shell value such as `hyprland.active-border` (`shell/Commons/Border.qml:37-47`). `Color.<section>.border` is the first stop of a gradient (`Color.qml:43-49, 51-65`); only `Border.surfaceSpec` and `BorderSurface` render the full gradient.

Widths come from `border-width` or `<token>-width` as a CSS-style list of one to four numbers, with per-side `-width-top|right|bottom|left` overrides (`Border.qml:110-120`, `shell/Commons/BorderGeometry.js:76-110`). Negative and non-numeric entries become 0.

Colors inside gradients and border tokens are canonicalized by `BorderGeometry.js:36-74`. Accepted forms: `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb(rrggbb)`, `rgba(rrggbbaa)`, `rgb(d,d,d)`, `rgba(d,d,d,a)`, `0xaarrggbb`. An angle is a token ending in `deg` (`Border.qml:87`). A gradient is "enabled" only with two or more stops (`:91`).

`[controls]` state tokens (`Style.qml:70-92`) are `normal`, `hover-cursor`, `focus`, `selected`, each with `-color`, `-fill-alpha`, `-border`, `-border-width`, `-border-alpha`, plus `pressed-fill-alpha`, `selection-fill-alpha`, and the optional `pressed-color` and `selection-color`. `focus-*` defaults to the `hover-cursor-*` value when absent (`:74, 80, 86, 92`).

### 2.7 Activation, step by step

`bin/omarchy-theme-set <name>`:

1. Normalizes the argument by stripping `<…>` tags, lowercasing, and turning spaces into hyphens (`:242`). Rejects an empty result, a leading dot, or a slash (`:248-251`, exit 1). Rejects a name that exists neither under `$OMARCHY_PATH/themes` nor `~/.config/omarchy/themes` (`:253-256`, exit 1). These three are the only non-zero exits in the script. Everything after this point exits 0.
2. Takes `flock` on `$XDG_RUNTIME_DIR/omarchy-theme-set.lock` (`:261-262`).
3. Deletes and recreates `~/.local/state/omarchy/current/next-theme` (`:265-266`).
4. Copies the built-in theme of the same name, if any, then the user theme of the same name on top (`:269-276`). A user theme with a `.git` directory is filtered: no `*.lua`, no `alacritty.toml`, `foot.ini`, `ghostty.conf`, `kitty.conf`, `vscode.json`, and no symlinks at any depth (`:30, 138-149, 180-233`). A plain directory or a symlinked working copy is copied in full with `cp -r` (`:275`).
5. Generates `colors.toml` from `alacritty.toml` for pre-palette themes (`:279-281`).
6. Runs `omarchy-theme-set-templates` (`:284`).
7. Snapshots the current background for the transition unless headless or `OMARCHY_THEME_SKIP_BACKGROUND=1` (`:286-289`).
8. `rm -rf current/theme` then `mv next-theme current/theme` (`:292-293`). This is the atomic point. The old theme directory is gone.
9. Writes the slug plus newline to `current/theme.name` (`:296`).
10. Base64-encodes `current/theme/colors.toml` and `shell.toml` (`:300-301`) and either pushes `omarchy-shell background themeTransition …` with the chosen wallpaper or `omarchy-shell shell applyTheme <colors> <shell>` (`:302-311`, `:107-136`). Every IPC call is wrapped in `timeout 2` and its failure is ignored (`:47-49`).
11. Releases the lock (`:316`).
12. Runs 14 retint commands in parallel (`:318-336`): terminal reload, `hyprctl reload`, btop, opencode, helix, foot, tmux, GNOME settings, pi, Claude Code, browser policy files, VS Code extension, Obsidian, keyboard RGB. Their exit codes are not collected.
13. Runs `omarchy-hook theme-set <slug>` (`:339`), which executes `~/.config/omarchy/hooks/theme-set` and every file in `theme-set.d/` with bash (`bin/omarchy-hook:18-28`).
14. Preloads the theme switcher and background caches (`:344-345`).

What the command requires from a theme directory: existence. Nothing else. A directory with no `colors.toml` and no `alacritty.toml` activates "successfully" and leaves the shell on hardcoded fallback colors with no generated application files.

What proves a theme is current: `~/.local/state/omarchy/current/theme.name` contains the slug (`:296`), `~/.local/state/omarchy/current/theme/` is the rendered directory, and `~/.local/state/omarchy/current/background` is a symlink to the chosen wallpaper (`:104, 135`). `omarchy-theme-current` only pretty-prints `theme.name` (`bin/omarchy-theme-current:9`). `omarchy-theme-list` merges both theme roots and pretty-prints names (`bin/omarchy-theme-list:6-9`), so the backend reads directories directly.

### 2.8 Backgrounds

`choose_theme_background` (`bin/omarchy-theme-set:72-100`) lists images with `find -L … -maxdepth 1 -type f` over `~/.config/omarchy/backgrounds/<slug>/` and then `current/theme/backgrounds/`, accepting `jpg jpeg png gif bmp webp` case-insensitively, sorted by full path. Because `~/.config/…` sorts before `~/.local/…`, user overlay images always come first. It compares the raw `readlink` of the current link against the list. On a match it advances to the next entry; otherwise it picks the first. `omarchy-theme-bg-next` does the same (`bin/omarchy-theme-bg-next:11-46`).

The link therefore points into the staged copy, `~/.local/state/omarchy/current/theme/backgrounds/<file>`, not into the source theme. Step 8 above deletes that file on every activation, which is why the script snapshots it first.

`omarchy-theme-bg-set <path>` resolves the path with `realpath`, requires a regular file, replaces the link with `ln -nsf`, and calls `omarchy-shell -q background set <path>` (`bin/omarchy-theme-bg-set:12-25`). The background plugin also re-reads the link on its own (`shell/plugins/background/Background.qml:123-129`).

A theme with no image in either location gets a notification "No background was found for theme" and the shell keeps whatever it displayed (`:110-114`).

### 2.9 What the theme switcher shows

`omarchy-theme-switcher` uses `preview.png` (or any `preview.*` raster), else the first image in `backgrounds/` (`bin/omarchy-theme-switcher:21-37`). A theme with neither gets no menu entry at all (`:39-49, 84-99`). A composer theme must therefore ship at least one wallpaper or a generated `preview.png`. Section 8.5 covers the generated card.

### 2.10 Icon theme

`omarchy-theme-set-gnome` sets the GNOME icon theme from `icons.theme` and falls back to `Yaru-blue` when the file is absent (`bin/omarchy-theme-set-gnome:29-34`). A composer theme without the file changes the user's icon theme on activation. The draft carries an optional `iconTheme` for that reason.

### 2.11 Shell IPC and preview

`omarchy-shell shell applyTheme <colorsB64> <shellB64>` decodes both payloads and calls `Color.loadColors` and `Color.loadShell`, then schedules a `hyprctl getoption` refresh (`shell/shell.qml:879-888`). It always returns `ok`. It replaces the whole theme-side value set; `userShellValues` from the machine override survive the call (`Color.qml:204-215`). There is no per-section IPC, and there is no IPC that reads the current values back.

This means the running shell can preview a draft with exact fidelity, and the exact inverse is the same call with the current `current/theme/colors.toml` and `shell.toml`. Limits:

- `loadColors` only assigns keys it finds (`Color.qml:148-164`). Restoring from a legacy `colors.toml` that lacks `accent`, `muted`, or `red` and their `colorN` fallbacks leaves the draft's value in place. The backend checks the current file for these keys before offering "Try in shell" and otherwise disables it with a reason.
- Payloads travel as argv to `qs ipc call` (`bin/omarchy-shell:59`). `shell.toml` renders to about 9.3 KB before base64; the per-argument limit on Linux is 128 KiB. Fine, but the backend caps each payload at 64 KiB and refuses beyond that.
- Hyprland borders, the wallpaper, terminals, and every other application keep the live theme. The preview is the shell only.
- The overlay restyles itself during the preview. That is acceptable for an explicit "Try in shell" action.

`omarchy-shell shell ping` returns `ok` when the shell is up (`shell.qml:875-877`); `bin/omarchy-shell:62-77` turns connection failures and "not ready" into non-zero exits.

## 3. Minimal valid data-only theme

The smallest directory that activates cleanly, renders every template without leftovers, gives the shell a full palette, and appears in the theme switcher:

```text
~/.config/omarchy/themes/<slug>/
├── colors.toml        26 keys from section 2.2, all #rrggbb, mode = "dark" or "light"
└── backgrounds/
    └── 01-<name>.<ext>   one raster image, or preview.png instead (section 8.5)
```

Strictly, `colors.toml` with `mode`, `accent`, `background`, `foreground`, `red`, `yellow`, `green`, `cyan`, `blue`, `magenta` is enough for zero unresolved placeholders, because `omarchy-theme-color` derives the rest (section 6). The composer still writes all 26 so the derived shades are visible and editable and so `omarchy dev theme-preview` shows the ramp the user chose.

## 4. Scope of the first release

In scope:

- `compose` drafts started from the active theme, a copy of any built-in or user theme, or a seeded minimal dark or light palette.
- Palette editing, dark or light mode, the two Hyprland border gradients.
- Whole-section overrides for `bar`, `controls`, `spacing`, `font`, `popups`, `tooltip`, `notifications`, `launcher`, `menu`, `polkit`, `lock`, `image-picker`.
- Wallpapers copied into the theme from local files, with one preferred wallpaper.
- Optional `icons.theme`.
- In-plugin preview, contrast diagnostics, "Try in shell" with journaled restore.
- Save, save and activate, duplicate (save under a new slug), delete inactive composer or plain themes, activate an existing theme, rollback.

Refused in the first release, with the error code the backend returns:

- Rename (`themes_unsupported_operation`). Duplicate and delete cover it.
- Replacing a symlinked theme or a directory containing `.git` (`themes_target_readonly`). Import it and save under a new slug.
- A slug that names a built-in theme (`themes_slug_is_builtin`).
- Deleting the active theme (`themes_target_active`) or a built-in (`themes_target_builtin`).
- Writing `hyprland.lua`, `neovim.lua`, `gum_env.lua`, any terminal file, `vscode.json`, `btop.theme`, `chromium.theme`, `keyboard.rgb`, `unlock.png`, `preview-unlock.png`, symlinks, or a whole `shell.toml`. The allowlist in section 8.1 is closed.
- Writing to `~/.config/omarchy/backgrounds/<slug>/`, `~/.config/omarchy/themed/`, `~/.config/omarchy/shell.toml`, or `$OMARCHY_PATH`.
- Undoing hooks or per-application retints. Rollback reactivates the previous theme, which retints again.
- Font family. `omarchy font set` owns it (`Style.qml:269`).
- Editing `Style.bar.iconSlot` and friends. Not readable from a theme (section 2.5).
- Hover previews of any kind on the desktop.

## 5. Module layout

```text
modules/themes/
├── module.json
├── Page.qml
├── components/
│   ├── PaletteEditor.qml          swatch grid, mode toggle, hex fields, ramp view
│   ├── SectionEditor.qml          one section: inherit toggle plus typed fields
│   ├── GradientField.qml          stops list, angle, alpha, live swatch
│   ├── WidthField.qml             1 to 4 values, per-side toggle
│   ├── WallpaperList.qml          add, remove, reorder, mark preferred
│   ├── DiagnosticsPanel.qml       contrast matrix, masked values, warnings
│   ├── PreviewCanvas.qml          scenario switcher and viewport
│   ├── preview/
│   │   ├── PreviewResolver.js     draft to resolved token model (section 9.2)
│   │   ├── PreviewBar.qml
│   │   ├── PreviewControls.qml    button, text field, toggle, dropdown row in 4 states
│   │   ├── PreviewPopup.qml       popup card and tooltip
│   │   ├── PreviewNotification.qml
│   │   ├── PreviewMenu.qml        menu and launcher rows
│   │   ├── PreviewLock.qml        idle, active, error
│   │   ├── PreviewPolkit.qml
│   │   ├── PreviewImagePicker.qml
│   │   └── PreviewType.qml        type scale and spacing ruler
│   └── TryInShellBanner.qml
├── backend/
│   ├── __init__.py                exports MODULE
│   ├── module.py                  ThemesModule: capabilities, status, validate, plan, verify
│   ├── palette.py                 key table, fallbacks, hex and gradient grammar
│   ├── sections.py                section schema table generated from shell.toml.tpl
│   ├── writer.py                  colors.toml and shell.<section>.toml serializer
│   ├── contrast.py                WCAG ratios and the pair list
│   ├── images.py                  signature and dimension readers, preview.png encoder
│   ├── inventory.py               theme roots, classification, revision
│   └── render.py                  scratch run of omarchy-theme-set-templates
├── schemas/
│   ├── draft-v1.json
│   └── sidecar-v1.json
└── tests/
    ├── fixtures/                  section 13
    ├── test_palette.py
    ├── test_writer.py
    ├── test_sections.py
    ├── test_contrast.py
    ├── test_images.py
    ├── test_inventory.py
    ├── test_plan.py
    ├── test_verify.py
    ├── test_integration.py
    └── qml/                       PreviewResolver parity and page state tests
```

`module.json`:

```json
{
  "id": "themes",
  "title": "Theme composer",
  "icon": "󰏘",
  "navOrder": 60,
  "page": "Page.qml",
  "backend": "modules.themes.backend",
  "schemas": ["schemas/draft-v1.json", "schemas/sidecar-v1.json"],
  "coreServices": ["DraftStore", "BackendClient", "ApplyBar", "ChangeList", "ConfirmDialog", "DiffView", "ErrorBanner", "UndoToast", "staging"]
}
```

## 6. Palette keys

### 6.1 Template consumers

Keys read by `default/themed/*.tpl` (extracted with `grep -oE '\{\{[^}]+\}\}'` over all 17 templates):

| Key | Read by |
|---|---|
| `background`, `foreground`, `accent` | every template except `chromium.theme.tpl` (which reads `background_rgb`) and `hyprland.lua.tpl` |
| `red`, `green`, `yellow`, `blue`, `magenta`, `cyan` | all terminal, editor, agent, and btop templates |
| `bright_red`, `bright_green`, `bright_yellow`, `bright_blue`, `bright_magenta`, `bright_cyan` | terminal templates, `neovim.lua.tpl`, `pi.json.tpl`, `vscode-theme.json.tpl`, `hyprland-preview-share-picker.css.tpl` (`bright_blue`) |
| `bright_foreground` | terminals, `gum_env.lua.tpl`, `btop.theme.tpl`, `helix.toml.tpl`, `neovim.lua.tpl`, `pi.json.tpl`, `vscode-theme.json.tpl` |
| `muted` | terminals, `gum_env.lua.tpl`, `btop.theme.tpl`, `helix.toml.tpl`, `neovim.lua.tpl`, `obsidian.css.tpl`, `pi.json.tpl`, `vscode-theme.json.tpl`, `claude.json.tpl`, share picker |
| `selection` | `btop.theme.tpl`, `neovim.lua.tpl` |
| `selection_background`, `selection_foreground` | derived; terminals, `gum_env.lua.tpl`, `helix.toml.tpl`, `neovim.lua.tpl`, `obsidian.css.tpl`, `pi.json.tpl`, `vscode-theme.json.tpl`, `claude.json.tpl` |
| `lighter_background`, `light_foreground`, `dark_foreground` | `btop.theme.tpl`, `neovim.lua.tpl`, `vscode-theme.json.tpl` (`dark_foreground`), share picker (`lighter_background`) |
| `dark_background`, `darker_background`, `orange`, `brown` | `neovim.lua.tpl` (`orange` also in `vscode-theme.json.tpl`) |
| `theme_type` | derived from `mode`; `claude.json.tpl`, `vscode-theme.json.tpl` |
| `purple_strip` | derived alias of `magenta`; `foot.ini.tpl` |
| `hyprland_active_border`, `hyprland_inactive_border` | `hyprland.lua.tpl` via `hypr_gradient`, `shell.toml.tpl` via `shell_gradient` |
| `mix a b n%` forms | `shell.toml.tpl` (`mix foreground background 34%`), `claude.json.tpl`, `pi.json.tpl`; both inputs must be `#rrggbb` (`bin/omarchy-theme-set-templates:220`) |

### 6.2 Required and optional keys with fallbacks

"Omarchy fallback" is what `bin/omarchy-theme-color` does when the key is absent. "Composer seed" is what the composer fills in when a user starts a minimal draft or imports a theme that lacks the key. The composer writes every key, so at save time nothing is absent.

| Key | Required in draft | Omarchy fallback (`bin/omarchy-theme-color`) | Composer seed |
|---|---|---|---|
| `mode` | yes | `theme_type`, `light.mode`, luminance, `dark` (`:120-135`) | luminance of `background` |
| `background` | yes | `color0`, else unresolved (`:197`) | none |
| `foreground` | yes | `color7`, else unresolved (`:198`) | none |
| `accent` | yes | none in `theme-color`; shell uses `color4` (`Color.qml:163`) | `blue` |
| `red` `green` `yellow` `blue` `magenta` `cyan` | yes | `color1..6` (`:203-219`), `magenta` also `purple` (`:220`) | none |
| `muted` | no | `color8`, else `dark_foreground` (`:228`) | `mix(foreground, background, 50%)` |
| `selection` | no | `selection_background`, `color8`, `color0`, `background` (`:229`) | `mix(background, foreground, 15%)` |
| `dark_background` | no | `mix(background, #000000, 25%)` (`:236`) | same |
| `darker_background` | no | `mix(background, #000000, 50%)` (`:237`) | same |
| `lighter_background` | no | `color0`, which is `background` (`:199, 226`) | `mix(background, foreground, 8%)` |
| `dark_foreground` | no | `color8`, else `foreground` (`:227`) | `mix(foreground, background, 40%)` |
| `light_foreground` | no | `color7`, which is `foreground` (`:200, 223`) | `mix(foreground, #ffffff, 8%)` for dark, `mix(foreground, #000000, 20%)` for light |
| `bright_foreground` | no | `color15`, else `foreground` (`:224`) | `mix(foreground, #ffffff, 15%)` for dark, `foreground` for light |
| `orange` | no | `yellow` (`:232`) | `mix(yellow, red, 40%)` |
| `brown` | no | `mix(orange, #000000, 50%)` (`:233`) | same |
| `bright_*` (6) | no | `mix(base, #ffffff, 20%)` (`:238-243`) | same |
| `hyprland_active_border` | no | template fallback `accent` (`hyprland.lua.tpl:1`, `shell.toml.tpl:23-24`) | absent (omitted from output) |
| `hyprland_inactive_border` | no | template literal `rgba(595959aa)` (`hyprland.lua.tpl:2`) | absent |

`mix(a, b, p)` is the integer-rounded linear blend in `bin/omarchy-theme-set-templates:20-60`. The composer ports it exactly (`round(a*(1-p) + b*p + 0.5)` per channel, truncated) so the seeds equal what Omarchy would derive.

Never written by the composer: `bg`, `fg`, `dark_bg`, `darker_bg`, `lighter_bg`, `dark_fg`, `light_fg`, `bright_fg`, `color0..15`, `purple`, `bright_purple`, `theme_type`, `cursor`, `selection_background`, `selection_foreground`, `active_border_color`, `active_tab_background`. All are derived or legacy (`bin/omarchy-theme-color:182-277`). `test/cli:445-448` fails if any shipped theme defines `cursor`.

## 7. Draft schema

`schemas/draft-v1.json` describes this document. Field types are JSON types. Every string field that holds a color or a gradient is validated by the grammar in section 7.3.

```json
{
  "schemaVersion": 1,
  "kind": "compose",
  "slug": "ocean-focus",
  "displayName": "Ocean Focus",
  "origin": { "type": "builtin", "slug": "tokyo-night", "revision": "sha256:…" },
  "palette": {
    "mode": "dark",
    "accent": "#7aa2f7", "selection": "#292e42", "muted": "#414868",
    "background": "#1a1b26", "dark_background": "#13141c", "darker_background": "#0e0e14", "lighter_background": "#24283b",
    "foreground": "#a9b1d6", "dark_foreground": "#565f89", "light_foreground": "#b4bee6", "bright_foreground": "#c0caf5",
    "red": "#f7768e", "yellow": "#e0af68", "orange": "#eb927b", "green": "#9ece6a", "cyan": "#449dab", "blue": "#7aa2f7", "magenta": "#ad8ee6", "brown": "#75493d",
    "bright_red": "#ff7a93", "bright_yellow": "#ff9e64", "bright_green": "#b9f27c", "bright_cyan": "#0db9d7", "bright_blue": "#7da6ff", "bright_magenta": "#bb9af7",
    "hyprland_active_border": "rgba(7aa2f7ee) rgba(bb9af7ee) 45deg",
    "hyprland_inactive_border": null
  },
  "sections": {
    "bar": null,
    "controls": {
      "normal-color": "foreground", "normal-fill-alpha": 0.04, "normal-border": "foreground", "normal-border-width": "1", "normal-border-alpha": 0.4,
      "hover-cursor-color": "accent", "hover-cursor-fill-alpha": 0.08, "hover-cursor-border": "accent", "hover-cursor-border-width": "1", "hover-cursor-border-alpha": 0.25,
      "focus-color": "accent", "focus-fill-alpha": 0.08, "focus-border": "rgba(7aa2f7ee) rgba(bb9af7ee) 45deg", "focus-border-width": "2 2 2 4", "focus-border-alpha": 0.25,
      "selected-color": "foreground", "selected-fill-alpha": 0.18, "selected-border": "foreground", "selected-border-width": "0", "selected-border-alpha": 1.0,
      "pressed-fill-alpha": 0.22, "selection-fill-alpha": 0.35
    },
    "spacing": null, "font": null, "popups": null, "tooltip": null, "notifications": null,
    "launcher": null, "menu": null, "polkit": null, "lock": null, "image-picker": null
  },
  "wallpapers": [
    { "sourcePath": "/home/u/Pictures/ocean.webp", "outputName": "01-ocean.webp" },
    { "sourcePath": "/home/u/Pictures/dawn.jpg", "outputName": "02-dawn.jpg" }
  ],
  "preferredWallpaper": "01-ocean.webp",
  "iconTheme": null,
  "acceptedWarnings": ["themes_contrast_low:menu.selected-text/menu.selected-background"]
}
```

An `activate` draft, the shape desktop modes quotes for `members.themes`:

```json
{ "schemaVersion": 1, "kind": "activate", "slug": "tokyo-night", "preferredWallpaper": null }
```

`preferredWallpaper` here is an absolute path or null; see section 7.1.

### 7.1 Field reference

| Field | Type | Rules |
|---|---|---|
| `schemaVersion` | integer | must be 1 |
| `kind` | `"compose"` or `"activate"` | selects the plan shape (section 11) |
| `slug` | string | `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`, no `--`; not a built-in name; the directory name and the argument to `omarchy-theme-set`. Never normalized after validation. `omarchy-theme-set` would lowercase and hyphenate for us (`:242`); relying on that means the directory we wrote and the name it stages could differ, so the composer does the normalization once, in the slug field, before the user confirms it |
| `displayName` | string | 1 to 64 characters, any Unicode, shown in the page only. Omarchy shows the slug title-cased (`bin/omarchy-theme-current:9`) |
| `origin` | object or null | provenance only. `type` is `active`, `builtin`, `user`, or `minimal`; `slug` names the source; `revision` is the source directory revision at import. The page uses it to offer "Refresh from source" and to show a diff. Nothing at runtime inherits from it, because `omarchy-theme-set` only overlays a user directory onto a built-in of the same slug (`:269-276`) |
| `palette.mode` | `"dark"` or `"light"` | written first in `colors.toml`; read by `omarchy-theme-set-gnome:18-26`, `omarchy-theme-set-tmux:43`, and the `theme_type` placeholder |
| `palette.<26 keys>` | string | `#rrggbb` lowercase after normalization; section 7.3 form H |
| `palette.hyprland_active_border`, `palette.hyprland_inactive_border` | string or null | form G or form S; null means omitted from `colors.toml` |
| `sections.<name>` | object or null | null means inherit the generated default; an object must contain every key listed for that section in section 8.2 and nothing else |
| `wallpapers[]` | array, 0 to 12 entries | `sourcePath` is an absolute path to a regular file; `outputName` matches `^[0-9]{2}-[a-z0-9][a-z0-9._-]{0,100}\.(jpg|jpeg|png|gif|bmp|webp)$` and is unique case-insensitively; the two-digit prefix is the list position and the writer renumbers on save |
| `preferredWallpaper` | string or null | must equal one `outputName`; for `activate` drafts it is an absolute path that must exist under the target theme's `backgrounds/` or `~/.config/omarchy/backgrounds/<slug>/` |
| `iconTheme` | string or null | `^[A-Za-z0-9._-]{1,64}$`; a warning if no directory of that name exists under `/usr/share/icons`, `~/.local/share/icons`, or `~/.icons` |
| `acceptedWarnings` | array of strings | warning ids the user accepted in review; validation still reports them but the ApplyBar does not block on them |

### 7.2 What the draft does not store

- No TOML text. The writer is the only producer.
- No `shell.toml` machine override values. They are read-only context shown in the page.
- No template hashes or revisions except `origin.revision`. Revision checking is the executor's job through `status().revision`.
- No copied wallpaper bytes. The plan copies from `sourcePath` at plan time (section 11.3).

### 7.3 Value grammar

Tokens, matched after trimming and with the whole string anchored:

- H, palette hex: `#[0-9a-f]{6}`. Input accepts uppercase and normalizes to lowercase.
- S, stop color: `rgba\([0-9a-f]{8}\)` or `rgb\([0-9a-f]{6}\)`. This is the intersection of what Hyprland accepts (Variables.md, "Colors" note, `#`, `rgba()`, `rgb()`, `0x`) and what the shell canonicalizes (`BorderGeometry.js:52-71`). The composer does not emit `#rrggbbaa` in gradients because `omarchy-theme-set-templates:203` only computes `_rgb` for six-digit hex and because the Hyprland Lua string is passed verbatim.
- A, angle: `-?[0-9]{1,3}(\.[0-9]{1,2})?deg`, numeric value in [-360, 360].
- G, gradient: two to eight S tokens separated by single spaces, optionally followed by one A token. One stop is written as a bare S token (form S), never as a one-stop gradient.
- R, role: one of `foreground`, `text`, `accent`, `urgent`, `muted`, `background`, `transparent` (`Color.qml:55-60`; `Style.resolveStateColor` accepts the same minus `muted`, `Style.qml:119-123`; `Border.cssColor` the same minus `muted`, `Border.qml:71-75`). Because `[controls]` values go through `Style` and `Border`, `muted` is not allowed in `[controls]`.
- D, dotted reference: `hyprland.active-border` or `hyprland.active-border-foreground` (`shell.toml.tpl:23-24`). Resolved by `Border.resolveValueRef` (`Border.qml:37-47`) and `Color.flatColor` (`Color.qml:54`). Only border-valued keys accept D.
- W, width: one to four integers in [0, 64] separated by single spaces. Serialized bare when one value (`1`), quoted when more (`"2 2 2 4"`), because `parseShell` reads a bare list only when unquoted and a quoted list through the string rule (`Color.qml:189-191`); both work, and one value bare matches the template's own style.
- F, alpha: decimal in [0, 1] with one to three fraction digits, always with a leading digit (`1.0`, `0.04`). Never exponent notation; `parseShell` requires `-?\d+(?:\.\d+)?` (`Color.qml:190`).
- N, integer: `[0-9]{1,4}`.
- B, boolean: `true` or `false`, bare (`Style.qml:304-310`).

Which forms each key accepts is in section 8.2.

Rejected everywhere: quotes, backslash, `|`, `&`, `=`, `{{`, `}}`, control characters, non-ASCII. `omarchy-theme-color:164` would drop the key, and `omarchy-theme-set-templates:200` uses the value as sed replacement text with `|` as the delimiter.

## 8. Generated output

### 8.1 Allowlist

```text
~/.config/omarchy/themes/<slug>/
├── colors.toml                     always
├── shell.bar.toml                  when sections.bar is an object
├── shell.controls.toml             when sections.controls is an object
├── shell.spacing.toml
├── shell.font.toml
├── shell.popups.toml
├── shell.tooltip.toml
├── shell.notifications.toml
├── shell.launcher.toml
├── shell.menu.toml
├── shell.polkit.toml
├── shell.lock.toml
├── shell.image-picker.toml
├── icons.theme                     when iconTheme is set; one line, no trailing spaces
├── preview.png                     only when wallpapers is empty (section 8.5)
└── backgrounds/
    └── NN-<name>.<ext>             one per wallpapers[] entry
```

Files are mode `0644`, directories `0755`. No file is executable, no entry is a symlink, and the writer refuses any path outside this list. `shell.hyprland.toml` is not generated; `[hyprland]` derives from the two palette keys through the template (`shell.toml.tpl:19-24`).

Directory ownership sidecar, kept outside the theme so the theme stays plain data: `~/.local/state/omarchy/customization-center/themes/<slug>.json` with `schemaVersion`, `slug`, `transactionId`, `savedAt`, and `files` as `{relpath: sha256}`. `status()` classifies a directory as `managed` when every file in the sidecar exists with the recorded hash and no extra file exists, `managed-modified` when the sidecar exists but the inventory differs, `plain` when there is no sidecar and the directory is neither a symlink nor contains `.git`, `git` and `symlink` otherwise, and `builtin` for `$OMARCHY_PATH/themes/<name>`.

### 8.2 Section schemas

Values and key order copy `default/themed/shell.toml.tpl`. Line references are into that file. "Default" is the template value with palette placeholders resolved; the resolver in section 9.2 uses the same table.

`[bar]` (`:5-17`)

| Key | Form | Default |
|---|---|---|
| `background` | H or R | `background` |
| `background-alpha` | F | `1.0` |
| `text` | H or R | `foreground` |
| `active` | H or R | `red` |
| `scale-with-font` | B | `true` |
| `size-horizontal` | N in [1, 512] | `26` |
| `size-vertical` | N in [1, 512] | `28` |

`[controls]` (`:26-65`). Twenty-two keys. For each state `S` in `normal`, `hover-cursor`, `focus`, `selected`: `S-color` (H or R without `muted`), `S-fill-alpha` (F), `S-border` (H, S, G, or R), `S-border-width` (W), `S-border-alpha` (F). Then `pressed-fill-alpha` (F) and `selection-fill-alpha` (F). Defaults: color and border `foreground` for all four states; fill alphas `0.04`, `0.08`, `0.08`, `0.18`; widths `1`, `1`, `1`, `0`; border alphas `0.4`, `0.25`, `0.25`, `1.0`; pressed `0.22`, selection `0.35`.

`[spacing]` (`:67-99`)

| Key | Form | Default |
|---|---|---|
| `scale` | decimal in [0.25, 4] | `1.0` |
| `scale-with-font` | B | `true` |
| 25 token keys `xxs xs sm md lg xl xxl xxxl huge control-gap control-padding-x control-padding-y input-padding-y control-height popup-row-height row-gap row-padding-x label-gap panel-gap panel-padding popup-padding dropdown-width searchable-dropdown-width number-field-width searchable-popup-min-height` | N or null | null (omitted; `Style.spacingToken` then computes `space(fallback)`, `Style.qml:225-229`) |

Token defaults, for the preview: 2 3 4 6 8 10 12 14 18, 8 10 6 7 28 28 8 12 4 14 18 14 240 260 120 220 (`Style.qml:235-260`). A pinned token is written as a bare integer and is not scaled (`:228`).

`[font]` (`:101-120`)

| Key | Form | Default |
|---|---|---|
| `base-size` | N in [1, 128] | `12` |
| `caption body-small body subtitle title heading display display-large icon-small icon icon-large` | N in [1, 256] or null | null (derived from `base-size` with multipliers 0.833, 0.917, 1.0, 1.083, 1.167, 1.333, 2.0, 2.333, bodySmall, title, 1.5; `Style.qml:327-338`) |

The shell only floors `base-size` at 1 (`Style.qml:430`). The composer warns outside [8, 48] and blocks outside [1, 128].

`[popups]` (`:122-132`): `background` (H, R) `background`; `background-alpha` (F) `1.0`; `text` (H, R) `foreground`; `border` (H, S, G, R, D) `hyprland.active-border`; `border-alpha` (F) `1.0`; `border-width` (W or null) null.

`[tooltip]` (`:134-141`): same five keys as popups without `border-width`; `background-alpha` default `0.97`; `border` default `hyprland.active-border-foreground`.

`[notifications]` (`:143-152`): popups keys plus `countdown` (H, R) `accent`; `border` default `hyprland.active-border`.

`[launcher]` (`:154-170`) and `[menu]` (`:172-187`), same 12 keys: `background` (H, R); `background-alpha` (F, launcher `0.95`, menu `1.0`); `text` (H, R); `border` (H, S, G, R, D) `hyprland.active-border-foreground`; `border-alpha` (F) `1.0`; `scrim` (H, R) `background`; `scrim-alpha` (F) `0.5`; `selected-background` (H, R) `foreground`; `selected-background-alpha` (F) `0.08`; `selected-text` (H, R) `accent`; `selected-border` (H, S, G, R, D) `hyprland.active-border-foreground`; `selected-border-alpha` (F) `0.25`. Optional `border-width` and `selected-border-width` (W or null).

`[polkit]` (`:189-205`): `background`, `background-alpha` `1.0`, `text`, `text-error` (H, R) `red`, `border` (D) `hyprland.active-border`, `border-error` (H, S, G, R) `red`, `border-alpha` `1.0`, `scrim`, `scrim-alpha` `0.5`, `accent` (H, R) `accent`. Optional `border-width`.

`[lock]` (`:207-224`): `background`, `background-alpha` `0.8`, `text`, `placeholder` (H, R) `mix(foreground, background, 34%)`, `text-error` `red`, `border` `hyprland.active-border`, `border-active` `hyprland.active-border`, `border-error` `red`, `border-alpha` `1.0`, `selection` (H, R) `accent`, `selection-alpha` (F) `0.45`. Optional `border-width`, `border-active-width`, `border-error-width`.

`[image-picker]` (`:226-237`): `scrim` `background`, `scrim-alpha` `0.5`, `text` `foreground`, `selected-border` (H, S, G, R) `accent`, `selected-border-alpha` `1.0`, `unselected-border` (H, S, G, R) `foreground`, `unselected-border-alpha` `0.28`. Optional `selected-border-width`, `unselected-border-width`.

When a user turns a section from inherit to custom, the page fills it with these defaults with palette roles left as role words (`foreground`, not the hex). Roles keep the section correct if the user later changes the palette. The template writes literal hex for `{{ foreground }}` placeholders; the composer writes the role word instead, which every consumer resolves (`Color.qml:55-60`, `Style.qml:119-123`, `Border.qml:71-75`). Exception: `[lock] placeholder` is a mix and is written as hex, recomputed from the palette on every save.

`sections.py` carries the table above as data plus the sha256 of `shell.toml.tpl` it was derived from. `capabilities()` compares that hash with the installed template and reports `themes_template_drift` when they differ, which disables section editing (palette editing and activation still work) until the table is updated.

### 8.3 `colors.toml` writer

```text
mode = "<dark|light>"
<blank>
accent = "#…"
selection = "#…"
muted = "#…"
<blank>
background = "#…"
dark_background = "#…"
darker_background = "#…"
lighter_background = "#…"
<blank>
foreground = "#…"
dark_foreground = "#…"
light_foreground = "#…"
bright_foreground = "#…"
<blank>
red = "#…"
yellow = "#…"
orange = "#…"
green = "#…"
cyan = "#…"
blue = "#…"
magenta = "#…"
brown = "#…"
<blank>
bright_red = "#…"
bright_yellow = "#…"
bright_green = "#…"
bright_cyan = "#…"
bright_blue = "#…"
bright_magenta = "#…"
[<blank>
hyprland_active_border = "…"]
[hyprland_inactive_border = "…"]
```

Rules: one space around `=`, double quotes, lowercase hex, LF line endings, one trailing LF, UTF-8 with no BOM, no comments, no header. The optional block is written only when at least one Hyprland key is set, and only the set keys are written. The output matches `themes/tokyo-night/colors.toml` byte for byte when the draft was imported from it unchanged; `test_writer.py::test_roundtrip_tokyo_night` asserts that.

### 8.4 `shell.<section>.toml` writer

```text
[<section>]
<key> = <value>
…
```

The header is written even though the file name decides the section (`bin/omarchy-theme-set-templates:316-318, 293-307`), because a human reading the file should not need to know that rule. Keys follow the order in section 8.2. Value serialization by form: H, S, G, R, D as double-quoted strings; W with one value bare, otherwise quoted; F as a decimal with at least one fraction digit and at most three, trailing zeros trimmed except the one required digit (`1.0`, `0.25`, `0.045`); N bare; B bare. Keys whose value is null are omitted. No alignment padding, one space around `=`.

Reparse check: after writing, the writer runs Python `tomllib.loads` on every file, then runs the module's port of `Color.parseShell` and asserts every key parsed with the intended value. Both must pass or the plan fails with `themes_writer_selfcheck_failed`.

### 8.5 Generated `preview.png`

Only when `wallpapers` is empty. A 480 by 270 RGB PNG: `background` fill, a 16-swatch row of `background dark_background darker_background lighter_background foreground dark_foreground light_foreground bright_foreground red yellow orange green cyan blue magenta brown` at y 200 to 250, and an `accent` bar 0 to 8 px at the top. Encoded with `zlib` and `struct` (IHDR, one IDAT with filter byte 0 per row, IEND). About 2 KB. `images.py::encode_swatch_png` is 40 lines and has no dependency. The switcher reads it (`bin/omarchy-theme-switcher:25-32`) and the shell's image picker can decode it.

### 8.6 Wallpaper ingestion

For each `wallpapers[]` entry, at plan time:

1. `os.lstat(sourcePath)`; must be a regular file, not a symlink, not on a path that traverses a symlink under `$HOME` (each component is `lstat`ed).
2. Open with `O_RDONLY | O_NOFOLLOW | O_CLOEXEC`; `fstat` and compare `st_dev, st_ino` with the `lstat` result.
3. Size in [1, 25 MiB]; total across entries at most 200 MiB; count at most 12.
4. Signature check against the extension in `outputName`: PNG `89 50 4E 47 0D 0A 1A 0A`; JPEG `FF D8 FF`; GIF `GIF87a` or `GIF89a`; BMP `BM`; WebP `RIFF????WEBP`. Mismatch is `themes_wallpaper_signature`.
5. Dimensions from headers only, no decode: PNG IHDR, JPEG SOF0/SOF2 scan, GIF logical screen, BMP `biWidth/biHeight`, WebP `VP8 `/`VP8L`/`VP8X` chunks. Width and height must be in [16, 16384]. Failure to find a header is `themes_wallpaper_unreadable`.
6. Copy into the staging directory as `backgrounds/<outputName>` with mode `0644`, then `fsync`.

Thumbnails in the page come from QML `Image` with `sourceSize` set to the tile size and `asynchronous: true`, reading the source path directly. That is a read, not a write, and it keeps decoding out of the backend.

## 9. Preview

### 9.1 Why not the shared controls

`Button`, `TextField`, `Toggle`, `Dropdown`, and `CursorSurface` take `foreground` and `accent` properties (`shell/Ui/Button.qml:35-37`, `TextField.qml:21-22`, `Toggle.qml:31-32`, `Dropdown.qml:25-28`, `CursorSurface.qml:22-23`) but derive fills, border specs, widths, fonts, and padding from the global `Style` and `Border` singletons (`Button.qml:79-84`, `TextField.qml:37`). A draft that changes `[controls]`, `[font]`, or `[spacing]` cannot be shown through them without mutating the singletons, which restyles the whole shell (section 2.11). So the preview canvas is module-owned.

Two things from `qs` are safe to reuse and give exact parity:

- `BorderSurface` and `BorderOverlay` render whatever spec object they are given (`shell/Ui/BorderSurface.qml:10-38`). A spec is `{color, widths: {top,right,bottom,left}, gradient: {colors, angle, enabled}}`.
- `Border.resolvedGradient(rawString, fallbackHex, alpha)` and `Border.withWidth(spec, widthString)` build those objects from strings (`Border.qml:79-92, 228-231`). Role words inside would resolve against the live palette, so the resolver substitutes hex for roles before calling them. With only hex, `rgb()`, and `rgba()` tokens the result depends on nothing global.

### 9.2 Resolver

`components/preview/PreviewResolver.js` exports `resolve(draft, machineOverride, options) -> tokens`. It runs on every draft change after a 120 ms debounce, in QML, because a round trip through `ccctl` per keystroke costs a Python start plus a template render and would make color dragging unusable.

Steps:

1. Palette: apply section 6.2 seeds for any null optional key; produce `palette` as hex strings and `urgent = red`.
2. For every section, take the draft object or the defaults table from section 8.2 with roles left as words.
3. Merge `machineOverride` values on top when `options.effective` is true (default). Every key overridden is listed in `tokens.masked[]` with section, key, draft value, and override value.
4. Resolve values: role words to palette hex (`text` and `foreground` to `foreground`; `urgent` to `red`; `transparent` to `#00000000`); D references to the resolved `[hyprland]` values, which are `hyprland_active_border` or `accent`, and `hyprland_active_border` or `foreground` (`shell.toml.tpl:23-24`); mixes for `[lock] placeholder`.
5. Compose: for every `<key>`/`<key>-alpha` pair produce a QML color with alpha applied to the first stop (`Color.composed`, `Color.qml:69-71`). For border-valued keys produce a spec through `Border.resolvedGradient` and `Border.withWidth`, applying `-alpha` to every stop (`Border.qml:88`).
6. Metrics: `fontScale = max(1/12, baseSize/12)`; `font.<token> = override || max(1, round(baseSize * mult))`; `spacing.effective = scale * (scaleWithFont ? fontScale : 1)`; `spacing.<token> = override != null ? round(override) : max(1, round(default * effective))`; `bar.sizeHorizontal = max(1, round((override || 26) * (barScaleWithFont ? fontScale : 1)))` (`Style.qml:284-302, 211-229`).
7. Controls: per state, `fill = alpha(stateColor, fillAlpha)`, `borderSpec` from `S-border` with `S-border-alpha` and `S-border-width`, with `focus-*` defaulting to `hover-cursor-*` when a key is null (`Style.qml:74-92`).

The backend has the same resolver in Python (`module.py::resolve_tokens`) and returns it in `validate().details.tokens`. `tests/qml/resolver-parity` feeds the fixture drafts through both and compares every color to within 1/255 per channel and every metric exactly. A parity failure is a test failure, not a runtime condition.

### 9.3 Canvas scenarios

`PreviewCanvas.qml` shows one scenario at a time, chosen by a tab strip, at a user-selectable zoom of 1x, 1.5x, or 2x:

- Bar, horizontal and vertical, with workspace pills, a clock, an "active" indicator, and a tooltip.
- Controls: button, text field with placeholder and selection, toggle, dropdown trigger, each in normal, hover-cursor, focus, selected, and pressed.
- Popup card and tooltip over a wallpaper crop.
- Notification with title, body, and countdown stripe.
- Menu: card over scrim with normal, selected, and disabled rows; launcher variant with its alpha.
- Lock field: idle, active, error, with placeholder and a selection sample.
- Polkit card: normal and error.
- Image picker: three slices, one selected, over the scrim.
- Type scale and spacing ruler: every font token at its computed size, the 25 spacing tokens as bars.
- Palette: neutral ramp `background -> bright_foreground` in mode order and the 16 ANSI slots, matching `omarchy dev theme-preview`.

Every sample paints on a backdrop chosen by a control: theme `background`, the preferred wallpaper crop, black, or white. Text that would overflow its box at the current font or spacing shows a clip badge instead of being cut silently.

The canvas header says "Representative preview. Use Try in shell for the live shell." The label is not decoration; it sets the expectation that spacing inside real panels can differ.

### 9.4 Try in shell

An explicit button. It builds and applies a plan of one operation:

```text
ShellIpc("applyTheme", [colorsB64, shellB64], expect=("ok",))
  inverse: ShellIpc("applyTheme", [currentColorsB64, currentShellB64], expect=("ok",))
```

`shellB64` encodes the scratch-rendered `shell.toml` from section 11.3, obtained through `BackendClient.query("themes", "preview", {draft})`, which runs the render and returns the two payloads plus the resolved tokens. The inverse payloads are read from `~/.local/state/omarchy/current/theme/` at plan time. Core runs `omarchy-shell shell applyTheme …` and classifies the result: a shell that is down, not responding, or not ready is `runtime_unavailable`, a missing method is `unsupported_config`, and any reply other than `ok` is `ipc_rejected` (contract amendment B). The transaction commits as applied; the page shows `TryInShellBanner` with "Stop preview", which runs `ccctl rollback <transactionId> --reason user`. A user-initiated rollback of a committed transaction is a legal journal history, and that is the whole mechanism. If the plugin dies, `ccctl history --module themes` lists the transaction and the same rollback restores it; `omarchy-theme-refresh` also restores it, at the cost of running hooks.

`capabilities()` reports `tryInShell: false` with a reason when the shell does not answer `ping`, when `current/theme/colors.toml` lacks any of `foreground`, `background`, `accent` or `color4`, `muted` or `color8`, `red` or `color1` (section 2.11), when either payload exceeds 64 KiB, or when a preview transaction is already open.

Editing the draft while a preview is active does not re-push. The banner offers "Update preview", which rolls back and applies a new transaction, so the journal always holds one open preview at most.

## 10. Contrast diagnostics

### 10.1 Algorithm

WCAG 2.1 relative luminance and contrast ratio:

```text
lin(c) = c/12.92 if c <= 0.04045 else ((c + 0.055)/1.055) ** 2.4     # c in [0,1]
L(rgb) = 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b)
ratio(a, b) = (max(La, Lb) + 0.05) / (min(La, Lb) + 0.05)
```

Alpha is composited before measuring: `over(fg, alpha, bg) = fg*alpha + bg*(1-alpha)` per channel. A surface with `background-alpha < 1` is composited over the backdrop; text is then measured against the composited surface. Gradients are measured at every stop and the worst ratio is reported with the stop index. Backdrops: the theme `background` (the common case, a tiled window) plus black and white as bounds when a surface's effective alpha is below 0.9. The wallpaper itself is not sampled; the backend has no image decoder and the bounds cover the worst case.

### 10.2 Pairs and thresholds

| Pair | Warn below | Block below |
|---|---|---|
| `foreground` on `background` | 4.5 | 1.1 |
| `muted` on `background` | 3.0 | none |
| `accent` on `background` | 3.0 | none |
| `red` on `background` | 3.0 | none |
| `bar.text` on composited `bar.background` | 4.5 | 1.1 |
| `bar.active` on composited `bar.background` | 3.0 | none |
| `<surface>.text` on composited `<surface>.background` for popups, tooltip, notifications, launcher, menu, polkit, lock | 4.5 | 1.1 |
| `notifications.countdown` on composited card | 3.0 | none |
| `menu.selected-text` and `launcher.selected-text` on `selected-background` composited over the card | 4.5 | 1.1 |
| `lock.placeholder`, `lock.text-error`, `polkit.text-error` on their composited card | 3.0 | none |
| `image-picker.text` on `image-picker.scrim` composited over black and white | 4.5 | none |
| each `[controls]` state fill composited over `background`, versus `foreground` | 4.5 | none |
| each border spec first stop composited with its alpha over its surface | 3.0 | none |

A block (`themes_contrast_invisible`) also fires when the effective alpha of a required text color is at most 0.05. Every warning carries `pairId`, both resolved colors, the composited backdrop, the ratio to two decimals, the scenario in the canvas that shows it, and the nearest palette key whose substitution would pass. Warnings are accepted by id in `acceptedWarnings`.

## 11. Backend behavior

### 11.1 `capabilities(ctx)`

Returns booleans with reasons:

- `compose`: `OMARCHY_PATH` is set, `$OMARCHY_PATH/default/themed/shell.toml.tpl` and `$OMARCHY_PATH/bin/omarchy-theme-set-templates` are readable.
- `activate`: `omarchy-theme-set` resolves on `PATH`.
- `wallpaper`: `omarchy-theme-bg-set` resolves on `PATH`.
- `sections`: `shell.toml.tpl` hash matches `sections.py`; otherwise `themes_template_drift` with both hashes.
- `tryInShell`: section 9.4.
- `themeSwitcherVisible`: informational, always true when `compose` is true, because the writer guarantees a preview image.

### 11.2 `status(ctx)`

Read-only. Returns:

```json
{
  "revision": "sha256:…",
  "active": { "slug": "tokyo-night", "source": "builtin", "background": "/home/u/.local/state/omarchy/current/theme/backgrounds/1-scenery.jpg", "hasColors": true, "hasShell": true },
  "themes": [
    { "slug": "tokyo-night", "source": "builtin", "path": "…", "hasPreviewImage": true, "wallpapers": 3 },
    { "slug": "ocean-focus", "source": "user", "classification": "managed", "path": "…", "sidecar": { "transactionId": "…", "savedAt": "…" }, "wallpapers": 2, "unsupportedFiles": [] },
    { "slug": "mine", "source": "user", "classification": "plain", "unsupportedFiles": ["hyprland.lua"] }
  ],
  "machineOverride": { "present": true, "values": { "font.base-size": "16" } },
  "userTemplates": ["shell.toml.tpl"],
  "wallpaperSources": [ { "label": "Pictures", "path": "/home/u/Pictures", "files": ["…"] }, … ],
  "iconThemes": ["Yaru-blue", "Papirus", …],
  "openPreviewTransaction": null
}
```

`revision` is sha256 over a canonical JSON of: `theme.name` content; sha256 of `current/theme/colors.toml` and `shell.toml` (or `absent`); `readlink` of `current/background`; sha256 of `~/.config/omarchy/shell.toml` or `absent`; sha256 of `shell.toml.tpl`; names and sha256 of `~/.config/omarchy/themed/*.tpl`; for every user theme, its slug, `lstat` type, presence of `.git`, and the sorted list of `(relpath, size, mtime_ns)`; the sidecar file hashes. Wallpaper bytes are not hashed; size and mtime are enough to detect a change and cheap for 25 MB files.

Import of an existing theme (`origin.type` `builtin` or `user`) runs `omarchy-theme-color --file <dir>/colors.toml --all` through `ctx.commands` and maps the resolved keys into the palette, and parses any `shell.toml` and `shell.<section>.toml` with the `parseShell` port into sections. Keys the section schema does not know are listed in `unsupportedKeys` and dropped on save after the page shows them. Files the allowlist does not know are listed in `unsupportedFiles` and never copied. Importing is `status` data plus a page action; it writes nothing.

### 11.3 `plan(ctx, draft, status)`

`compose` draft:

1. Validate (section 12). Any error aborts with `validation_failed`.
2. Materialize the candidate into `ctx.paths.staging_dir("themes", plan_id)`: write `colors.toml`, section files, `icons.theme`, `preview.png`, and copy wallpapers per section 8.6. Renumber `outputName` prefixes by list position.
3. Scratch render: create `<staging>/.render/home/.local/state/omarchy/current/next-theme/` containing a copy of the candidate, symlink nothing, copy `~/.config/omarchy/themed/*.tpl` into `<scratch home>/.config/omarchy/themed/` (size-capped at 256 KiB each), and run `ctx.commands.run(["omarchy-theme-set-templates"], env_extra={"HOME": scratch_home, "OMARCHY_PATH": real}, timeout_s=20)`. Then check every rendered file for `{{` and parse the rendered `shell.toml` with the `parseShell` port. Failures are `themes_render_failed` with the file and the first unresolved token. Keep the rendered `shell.toml` and `colors.toml` bytes for verify and for Try in shell. Delete `.render` before returning.
4. Classify the target `~/.config/omarchy/themes/<slug>`: absent, `managed`, `managed-modified`, `plain`, `git`, `symlink`. `git` and `symlink` abort with `themes_target_readonly`. `plain` and `managed-modified` require `draft.acceptedWarnings` to contain `themes_replace_unmanaged:<slug>`; the warning text lists every file that will be replaced.
5. Emit operations:

```text
EnsureDirectory(~/.config/omarchy/themes)
ReplaceDirectoryAtomic(~/.config/omarchy/themes/<slug>, <staging>/theme)
WriteFileAtomic(~/.local/state/omarchy/customization-center/themes/<slug>.json, sidecar, 0644)
```

and, when the user chose "Save and apply" (the page sets `draft.activate = true` on the copy it sends to the ApplyBar, a boolean the schema allows only at the top level and which the writer ignores):

```text
RunCommand(["env", "OMARCHY_THEME_SKIP_BACKGROUND=1", "omarchy-theme-set", "<slug>"], timeout_s=120, expect_exit=0, capture_limit=65536)
  inverse: RunCommand(["env", "OMARCHY_THEME_SKIP_BACKGROUND=1", "omarchy-theme-set", "<previous slug>"], …)   when status.active.slug exists, else None
RunCommand(["omarchy-theme-bg-set", "<HOME>/.local/state/omarchy/current/theme/backgrounds/<preferredWallpaper>"], timeout_s=10, expect_exit=0)
  inverse: RunCommand(["omarchy-theme-bg-set", "<status.active.background>"], …)   when that file still exists after reactivation, else None
```

Without a preferred wallpaper the `env` prefix is dropped and the `bg-set` operation is omitted; Omarchy picks the first image (section 2.8). With a preferred wallpaper the `env` prefix stops `omarchy-theme-set` from choosing and transitioning to a different image first; the shell still receives the palette through `applyTheme` (`bin/omarchy-theme-set:307-308`), and `bg-set` then pushes the wallpaper (`bin/omarchy-theme-bg-set:25`). The argument to `bg-set` is the staged path, not the source path, because the cycling code compares raw link text against the staged listing (section 2.8).

Plan summaries shown in the review: "Create theme ocean-focus (3 files, 2 wallpapers, 14.2 MB)", "Activate ocean-focus with omarchy-theme-set. This reloads Hyprland, restarts or retints terminals, btop, editors, browsers, GNOME settings, and runs your theme-set hooks (2 files found in ~/.config/omarchy/hooks/theme-set.d)", "Set wallpaper 01-ocean.webp". Hooks are listed by name from the hooks directory so the user sees what will run.

`activate` draft:

```text
RunCommand(["omarchy-theme-set", "<slug>"], …)   or the env form when preferredWallpaper is set
  inverse as above
[RunCommand(["omarchy-theme-bg-set", "<preferredWallpaper>"], …)]
```

The slug must exist in `status.themes`. A `plain` user theme with `unsupportedFiles` gets a warning naming them ("this theme ships hyprland.lua, which Hyprland will execute"); the composer did not write it and does not block it.

Delete (page action "Delete theme", which builds a `compose`-kind draft with `delete: true`; the schema allows the boolean only with `kind: compose` and requires no other content):

```text
ReplaceDirectoryAtomic(~/.config/omarchy/themes/<slug>, null)
WriteFileAtomic(sidecar path, absent)
```

Refused for `builtin`, `git`, `symlink`, and for the active slug.

### 11.4 `verify(ctx, plan, status_after)`

For every plan that contained `ReplaceDirectoryAtomic`: the target directory exists, contains exactly the sidecar's files with matching hashes, no symlinks, and no executable bits.

For every plan that contained the `omarchy-theme-set` operation:

1. `~/.local/state/omarchy/current/theme.name` stripped equals the slug.
2. `~/.local/state/omarchy/current/theme/colors.toml` bytes equal the candidate's `colors.toml` (`omarchy-theme-set` copies with `cp -r`, `:275`, and templates never overwrite, `omarchy-theme-set-templates:396`).
3. `current/theme/shell.toml` parsed with the `parseShell` port has, for each section the draft customized, exactly the fragment's keys and values, and for every other section the values from the scratch render of step 3 in section 11.3. A user template would change both sides identically, which is why the scratch render includes user templates.
4. No file under `current/theme/` matching the 17 template output names contains `{{`.
5. `current/theme/shell.<section>.toml` exists for every customized section.
6. The background link: when a preferred wallpaper was set, `readlink` equals the staged path and the file exists; otherwise the link resolves to an existing file, or the plan carried the warning `themes_no_wallpaper` and the link is unchanged.
7. If `status.capabilities.shell` was reachable before apply, `omarchy-shell shell ping` prints `ok` afterwards. A shell that was down before is a warning, not a failure.
8. `status_after.revision` differs from the plan's expected revision only in the fields the plan changed. Any other difference is `themes_concurrent_change` and fails verification, because `omarchy-theme-set` has no way to take an immutable input and another caller can run it between our directory write and our command.

Failure of any check returns `verification_failed` with the check number and the observed values; the executor then runs the inverses in reverse order.

### 11.5 Rollback semantics

The executor restores the directory backup, runs the inverse `omarchy-theme-set <previous>`, then runs the inverse `bg-set`. The order matters in the same-slug case: the directory must be restored before `omarchy-theme-set` runs again, or rollback reactivates the new bytes. Reverse operation order does not provide that sequence. The activation operation declares `inverseAfter` on the directory replacement, and the wallpaper operation declares `inverseAfter` on activation. Activation-only plans keep the latter dependency. The generic executor validates these references and uses the same dependency ordering for failure rollback and committed user undo.

What rollback does not do, and the review says so: it does not undo `theme-set` hooks, and it does not restore application state that a retint changed in a way the second retint does not reverse (a browser policy file is rewritten, a VS Code extension is reinstalled with the old colors, but a hook that sent a notification has already sent it).

When the inverse `omarchy-theme-set` itself fails, the executor reports `rollback_failed`. The page pins a banner with the three terminal commands that recover:

```text
cp -r ~/.local/state/omarchy/customization-center/backups/<txid>/themes/<slug> ~/.config/omarchy/themes/<slug>   # only when a backup exists
omarchy-theme-set <previous slug>
omarchy-theme-bg-set <previous background>
```

## 12. Validation rules and error codes

`validate(ctx, draft)` is pure. Errors block; warnings block unless their id is in `acceptedWarnings`.

| Code | Kind | Condition |
|---|---|---|
| `validation_failed` | error | schema violation; `errors[].path` names the JSON pointer |
| `themes_slug_invalid` | error | regex in section 7.1 |
| `themes_slug_is_builtin` | error | `$OMARCHY_PATH/themes/<slug>` exists |
| `themes_palette_missing` | error | a required key from section 6.2 is null |
| `themes_value_syntax` | error | value fails its form; message names the key, the value, and the allowed forms |
| `themes_section_incomplete` | error | a customized section lacks a required key or has an unknown key |
| `themes_range` | error | number outside its block range (section 8.2) |
| `themes_wallpaper_missing`, `themes_wallpaper_symlink`, `themes_wallpaper_signature`, `themes_wallpaper_unreadable`, `themes_wallpaper_too_large`, `themes_wallpaper_too_many`, `themes_wallpaper_name` | error | section 8.6 |
| `themes_preferred_unknown` | error | `preferredWallpaper` matches no entry |
| `themes_contrast_invisible` | error | section 10.2 block threshold |
| `themes_contrast_low:<pairId>` | warning | section 10.2 warn threshold |
| `themes_range_unusual:<key>` | warning | `base-size` outside [8, 48], `spacing.scale` outside [0.5, 2.0], bar sizes outside [16, 96], width above 8 |
| `themes_masked:<section>.<key>` | warning | the machine override sets this key; the draft value will not take effect on this machine |
| `themes_no_wallpaper` | warning | `wallpapers` empty; explains that `preview.png` is generated and that Omarchy will keep the previous wallpaper on activation |
| `themes_icon_theme_missing` | warning | `iconTheme` set but not found |
| `themes_replace_unmanaged:<slug>` | warning | target is `plain` or `managed-modified`; lists files |
| `themes_unsupported_keys` | warning | imported section keys dropped on save |
| `themes_template_drift` | warning | section 8.2; sections are still written from the module's table |
| `themes_target_readonly`, `themes_target_active`, `themes_target_builtin`, `themes_unsupported_operation` | error | section 4 |
| `themes_render_failed`, `themes_writer_selfcheck_failed` | error | plan time |
| `themes_concurrent_change` | error | verify time |

## 13. Page and UI states

### 13.1 Layout

Left rail inside the page: Palette, Surfaces, Type and spacing, Bar, Wallpapers, Diagnostics, Themes. Center: the editor for the selected item. Right: `PreviewCanvas` with the scenario tabs, backdrop control, zoom, and the "Effective on this machine / Theme alone" switch. Bottom: the shared `ApplyBar`.

The Themes item lists `status.themes` with source and classification badges, the active marker, and per-row actions: Activate (builds an `activate` draft), Open in composer (import), Duplicate (import with a new slug), Delete.

### 13.2 State machine

Page:

```text
loading -> ready | unavailable(reason) | error(code)
ready: on status refresh -> ready; on stale_revision from ApplyBar -> stale
stale -> ready after Reload; the draft is kept and re-validated
```

Editor (within ready):

```text
clean <-> dirty on any draft change
validation: pending -> valid | warnings(n) | errors(n), recomputed after the 120 ms debounce
preview: current | stale (during debounce) | unavailable (resolver threw; shows the message and keeps the last good canvas)
```

Try in shell:

```text
off -> applying -> on(txid) -> restoring -> off
on(txid) + draft change -> on(txid, outdated) with "Update preview"
any failure -> off with an ErrorBanner; an open transaction stays listed in History
```

Apply flow is the shared ApplyBar's: validate, plan, review, apply, verifying, then `applied(txid)` with an UndoToast, or `failed(rolled back)` with the original error, or `failed(rollback_failed)` with the pinned recovery banner.

Confirmation dialogs (shared `ConfirmDialog`, named action): replacing an unmanaged directory lists every file; deleting names the slug and path; activating states that hooks and retints will run and lists the hook files.

### 13.3 Page contract

`Page.qml` exposes the properties, signals, and `focusFirst()` from the module contract, and `handlePayload(payload)`. Accepted payloads: `{"slug": "…"}` opens that theme in the composer (import into a `compose` draft); `{"activate": "…"}` selects the Themes item with that row focused and its Activate action ready; `{"tab": "diagnostics"}` selects a rail item. Unknown keys are ignored. The page calls `ccctl` only through `BackendClient`; the preview channel is `BackendClient.query("themes", "preview", {draft, portable})`, which the page uses for Try in shell payloads and for the parity check, while keystroke-latency preview stays in `PreviewResolver.js`.

### 13.4 Keyboard

`focusFirst()` focuses the rail. Within the palette grid, arrows move between swatches, Enter opens the hex field, Escape returns. Every swatch has an accessible name of the form "accent, #7aa2f7, contrast 5.1 on background". The canvas is not focusable; it is output only.

## 14. Test matrix

Fixtures under `modules/themes/tests/fixtures/`:

| Fixture | Content |
|---|---|
| `themes/tokyo-night/` | copy of `themes/tokyo-night` at `71b0887c` |
| `themes/flexoki-light/` | light mode copy |
| `themes/hackerman/` | gradient `hyprland_active_border` |
| `themes/white/` | 24-key palette (no orange, brown) |
| `themes/legacy-colorn/` | `color0..15` and `bg`/`fg` only |
| `themes/sparse/` | `background`, `foreground`, `accent`, six named colors |
| `themes/with-lua/` | plain user theme with `hyprland.lua` and `vscode.json` |
| `themes/git-clone/` | user theme containing `.git/` |
| `themes/symlinked/` | symlink to `with-lua` |
| `themes/sparse-lock/` | tokyo-night plus `shell.lock.toml` with six keys |
| `drafts/minimal-dark.json`, `drafts/minimal-light.json` | seeds only |
| `drafts/full-sections.json` | every section customized |
| `drafts/gradients.json` | gradient borders in every place a G is allowed, angles -360, 0, 45.5, 360 |
| `drafts/widths.json` | W with 1, 2, 3, 4 values, zeros, 64 |
| `drafts/bad-*.json` | one violation each: slug, builtin slug, missing key, bad hex, quote in value, `{{` in value, unknown section key, incomplete section, alpha 1.5, width 65, base-size 0, eight-stop plus one gradient, `muted` in controls |
| `drafts/activate.json` | `kind: activate` |
| `drafts/delete.json` | `delete: true` |
| `wallpapers/ok.png`, `ok.jpg`, `ok.webp`, `ok.gif`, `ok.bmp` | 16 by 16 valid headers |
| `wallpapers/bad-signature.png` | text bytes |
| `wallpapers/oversize-header.png` | IHDR claims 20000 by 20000 |
| `wallpapers/link.png` | symlink to `ok.png` |
| `machine/shell.toml` | `[font] base-size = 16` |
| `templates/user-shell.toml.tpl` | user template that changes `[menu] scrim-alpha` |
| `stubs/omarchy-theme-set` | the real script from the pinned checkout, run with `OMARCHY_THEME_HEADLESS=1` like `test/shell.d/theme-staging-test.sh:22-27` |
| `stubs/omarchy-theme-set.exit1`, `.hang`, `.wrong-name` (exits 0 but writes another slug), `.no-shell` | failure variants |
| `stubs/omarchy-theme-bg-set`, `.missing-file` | link writer and failure |
| `stubs/omarchy-shell`, `.down` | `ping` answers `ok` or exits 1 |
| `stubs/omarchy-theme-color` | the real script |

Unit tests:

- `test_palette.py`: seeds equal `omarchy-theme-color --all` output for `sparse` and `legacy-colorn` (run the real script through the fixture runner); hex normalization; every `bad-*` draft yields its code; `mix` port matches `bin/omarchy-theme-set-templates` on 50 random pairs and amounts.
- `test_writer.py`: `test_roundtrip_tokyo_night` byte equality; key order; Hyprland block presence; F serialization table (`1`, `1.0`, `0.045`, `0.0400` to `0.04`); W bare versus quoted; section header; `tomllib` reparse; `parseShell` port reparse.
- `test_sections.py`: table hash equals `shell.toml.tpl` hash; every key in the table appears in the template and vice versa; defaults resolve to the template's literal output for `tokyo-night`.
- `test_contrast.py`: known WCAG vectors (`#000000/#ffffff` 21.0, `#777777/#ffffff` 4.48); alpha compositing; gradient worst stop; the block threshold at 1.1 and alpha 0.05.
- `test_images.py`: dimension readers for the five formats; signature mismatch; oversize header; symlink refusal; the PNG encoder output decodes with `zlib` and has the expected IHDR.
- `test_inventory.py`: classification of every `themes/*` fixture; revision changes when a wallpaper mtime, the machine override, a user template, or `theme.name` changes; revision unchanged by an unrelated file under `$HOME`.
- `test_plan.py`: operation lists for compose, compose with activate, activate, delete; `env` prefix present only with a preferred wallpaper; inverse is `None` when no previous theme; `themes_target_readonly` for `git-clone` and `symlinked`; `themes_replace_unmanaged` required for `with-lua`; staging directory contents and modes; scratch render leaves no `{{`; user template changes the rendered `[menu]`.
- `test_verify.py`: each of the eight checks fails on a constructed state; the `wrong-name` stub fails check 1; a `sparse-lock` current theme passes check 3 for uncustomized sections.

Integration tests (isolated `HOME`, `XDG_*`, `OMARCHY_PATH` pointing at the pinned checkout, stubs on `PATH`):

- save new, save and activate, activate existing, delete inactive, duplicate built-in, replace managed, replace plain after acceptance.
- refuse: active delete, built-in delete, git replace, symlink replace, built-in slug.
- failure injection at: before staging copy, after `ReplaceDirectoryAtomic`, `omarchy-theme-set` exit 1, hang past timeout, exit 0 with wrong `theme.name`, `bg-set` missing file, verify check 3 mismatch, inverse `omarchy-theme-set` failure. After each: target inventory, `theme.name`, background link, journal state, and backup presence are asserted.
- Try in shell: apply, rollback, apply while open is refused, `capabilities.tryInShell` false with `sparse` as the current theme.
- no write outside the isolated roots (a `find -newer` sentinel over the real `$HOME` is not possible in CI; instead the test `HOME` is the only writable directory in the sandbox).

QML tests:

- resolver parity against `validate().details.tokens` for every draft fixture.
- page states: loading, ready, unavailable, stale, dirty, warnings, errors, try-in-shell on and outdated, applied, rollback failed.
- no apply from selection, hover, zoom, backdrop, or scenario change.
- focus order and accessible names for the palette grid.
- clip badge appears at `base-size = 48` in the notification scenario.

Live checks in the disposable VM, recorded in the PR description rather than automated: dark and light drafts with and without a machine override; horizontal and vertical bars; compare each canvas scenario with the real surface; activation retints a terminal, Hyprland borders, and VS Code; kill the shell during Try in shell and confirm `ccctl rollback` restores after restart.

## 15. Milestones

1. Inventory and status. `status`, `capabilities`, classification, revision, import. Exit: opening the page writes nothing and lists every fixture theme correctly.
2. Palette and writer. Draft schema, seeds, grammar, `colors.toml` writer, `preview.png`, scratch render, save-only plan and verify. Exit: a minimal draft saves, activates by hand with `omarchy theme set`, renders no `{{`, and shows in the switcher.
3. Activation. `omarchy-theme-set` and `bg-set` operations, verify checks 1 to 8, rollback, recovery banner. Exit: every failure-injection test returns to the previous theme.
4. Preview. Resolver, canvas scenarios, parity tests, contrast diagnostics, Try in shell. Exit: editing every palette key changes only the canvas; parity suite green.
5. Sections, type, spacing, bar, wallpapers, icon theme, delete, duplicate. Exit: every exposed value survives activation and appears in `current/theme/shell.toml`.
6. Hardening. Keyboard pass, accessible names, VM checks, docs for terminal recovery.

## 16. Core services used

Names follow the contract amendments sheet.

- `ReplaceDirectoryAtomic(path, staged_dir | None, allow_existing)`: save (`allow_existing` true only after `themes_replace_unmanaged` is accepted or the target is `managed`), create-if-absent for a new slug, `staged_dir=None` for delete. Cross-filesystem staging is the executor's job.
- `ctx.paths.staging_dir("themes", plan_id)`: where `plan()` materializes the candidate and the scratch render.
- `ctx.commands.run(argv, timeout_s, env_extra=…)`: the scratch render with a different `HOME`; activation passes `env` in argv and needs no `env_extra`.
- `ValidationResult.details`: the resolved token model and the contrast matrix.
- `ShellIpc("applyTheme", args, expect=("ok",))` and the shared codes `runtime_unavailable`, `unsupported_config`, `ipc_rejected`.
- `ccctl rollback <txid> --reason user` on a committed transaction: "Stop preview".
- `ccctl query themes preview`: the preview channel behind `BackendClient.query`.
- Registration is the one line in `backend/customization_center/modules/__init__.py`.

## 17. Contract notes for other modules

- Desktop modes: `members.themes` is `{slug, preferredWallpaper?}` (amendment I). It maps one to one onto the `activate` draft in section 7, which is the shape the modes plan quotes. In a composed plan the themes segment runs after the monitors gate has been confirmed, because `omarchy-theme-set` runs `omarchy-restart-hyprctl`, which is `hyprctl reload` (`bin/omarchy-theme-set:320`, `bin/omarchy-restart-hyprctl:5`), and a reload before a confirmed layout would race the gate. The segment's rollback is the inverse `omarchy-theme-set <previous>` operation, so `status.active.slug` must be captured in the segment's expected revision before the gate.
- Master plan Module 6 lists a generated set without `bar`, `popups`, `tooltip`, `launcher`, `polkit`, `lock`, `image-picker`. This plan writes all twelve sections. The master plan's "Rename" action is dropped from the first release. The master plan says a later release "may use shell theme IPC" for preview; this plan ships it in milestone 4 as an explicit, journaled transaction because the inverse is exact and cheap, and keeps the hover prohibition.

## 18. Residual risks

- `omarchy-theme-set` exits 0 after its argument checks no matter what happens later. Verification, not the exit code, decides success. A retint that fails is invisible to us and to Omarchy.
- Another `omarchy-theme-set` can run between our directory write and our command. Verify check 8 detects it after the fact; nothing prevents it.
- The section table is a copy of `shell.toml.tpl`. An Omarchy update that adds a key to a section makes composer-written sections lose that key until the table is updated. `themes_template_drift` makes this visible and disables section editing, and palette-only themes are unaffected because they do not write section files.
- The preview is a model of the shell, not the shell. Parity tests cover the resolver; they do not cover panel layout. Try in shell exists for that.
- Wallpaper source files are re-read at apply time. If the user changes the file between review and apply, the saved bytes differ from the reviewed ones; the journal records the hash actually written.
