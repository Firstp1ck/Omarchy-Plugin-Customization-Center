# Default application manager (module `defaults`)

Status: planned. Written against the module contract in the master plan revision and against Omarchy commit `71b0887c` (`/mnt/SSD_NVME_4TB/GitHub/omarchy-fork`). Every claim below that names a file was checked by opening that file. Claims that could not be checked in this session are marked "unverified".

## 1. What this module does

Four Omarchy commands own default-application state: `omarchy-default-browser`, `omarchy-default-terminal`, `omarchy-default-editor`, and `omarchy-default-agent`. Each one reports the current choice when called with no argument and sets a choice when called with one. Each one installs the application first if its command is missing, by reopening itself with `--install` inside Omarchy's floating terminal. This module puts a graphical page in front of those four commands and nothing else.

Decisions that shape everything below:

1. The four categories are browser, terminal, editor, and coding agent. No MIME roles, no file manager, no mail handler. Those have no Omarchy setter at `71b0887c` (section 3.7), and inventing one here would make the plugin the owner of state Omarchy later wants to own.
2. The backend never writes XDG state or Omarchy state files itself when setting a default. It runs the selector. The only file writes this module makes on its own are rollback restores of backups the executor took.
3. Installing a missing application is a `TerminalHandoff(argv=[<selector>, <choice>], wrapped=false)`. The selector notices the missing command and opens Omarchy's floating terminal itself, reinvoking itself with `--install` (`bin/omarchy-default-browser:43`, `bin/omarchy-default-terminal:39`, `bin/omarchy-default-editor:41`, `bin/omarchy-default-agent:46`). The backend never passes `--install`; the user sees the same terminal they would see from the menu.
4. A handoff is not a completed transaction. The executor leaves it in journal state `pending_handoff`. The module's `verify` decides later, from a fresh `status`, whether the install and set both happened.
5. Selecting a coding agent launches that agent. The selector has no set-only mode (`bin/omarchy-default-agent:64-65`). The page says "Set and launch" and the plan marks the operation as launching a program. Desktop modes exclude the agent category for this reason; see section 18.
6. "Installed" means what the selector means by it: `command -v <command>` for browser, terminal, and editor (`bin/omarchy-cmd-missing:5-9`), and `mise where <package>` for agents (`bin/omarchy-default-agent:45`). `pacman -Q` is shown as information and never gates an action.

## 2. Scope

In scope for the first release:

- Read the current value of all four categories through the selectors, and show it even when it is not one of the catalog choices.
- Show every catalog choice with its installed state, integration state, and package state.
- Set an installed choice by running the selector.
- Install and set a missing choice by terminal handoff, then reconcile.
- Restore the Omarchy default for browser (`chromium`), terminal (`foot`), and editor (`nvim`). These are ordinary set plans; see section 3.6 for where each default comes from.
- Verify against the state each selector actually reads, not only against the selector's stdout.
- Roll back the selection. Never uninstall anything.
- Expose `plan()` in a form the desktop modes module can call for browser, terminal, and editor.

Refused in the first release:

- Unsetting the coding agent. The selector has no unset verb. Rollback can restore an absent file because that is restoring a backup, but the page offers no "none" choice.
- Any argv that is not built from the catalog. The draft carries category ids and choice ids only.
- Running `omarchy-pkg-add`, `omarchy-pkg-aur-add`, `omarchy-install-*`, `yay`, `pacman`, or `mise use` directly.
- Concurrent handoffs. One pending handoff blocks new install plans until `ccctl reconcile` finishes it or the user stops tracking it (`ccctl abandon`, journal `rolled_back` with reason `user`).
- Editing `mimeapps.list`, `xdg-terminals.list`, or the state files as a way to set a default.

## 3. Source facts

### 3.1 `omarchy-default-browser`

- Query (`bin/omarchy-default-browser:13-25`): runs `env -u BROWSER xdg-settings get default-web-browser`, maps seven desktop ids to short names, prints anything else verbatim, and always exits 0. Output is one line. If `xdg-settings` prints nothing, the output is an empty line.
- Choices (`:27-39`), in source order:

| Choice id | Command probed | Desktop id written | Display name | Installer path (`bin/omarchy-install-browser`) |
|---|---|---|---|---|
| `chromium` | `chromium` | `chromium.desktop` | Chromium | `omarchy-pkg-add chromium` (`:41`), then policy dir with sudo, flags, theme |
| `chrome` | `google-chrome-stable` | `google-chrome.desktop` | Chrome | `omarchy-pkg-aur-add google-chrome` (`:50`) |
| `brave` | `brave` | `brave-browser.desktop` | Brave | `omarchy-pkg-aur-add brave-bin` (`:68`) |
| `brave-origin` | `brave-origin` | `brave-origin.desktop` | Brave Origin | `omarchy-pkg-aur-add brave-origin-bin` (`:77`) |
| `edge` | `microsoft-edge-stable` | `microsoft-edge.desktop` | Edge | `omarchy-pkg-aur-add microsoft-edge-stable-bin` (`:59`) |
| `firefox` | `firefox` | `firefox.desktop` | Firefox | `omarchy-pkg-add firefox` (`:86`), policies with sudo, Wayland env file |
| `zen` | `zen-browser` | `zen.desktop` | Zen | `omarchy-pkg-aur-add zen-browser-bin` (`:94`) |

- Unknown argument: prints usage to stdout, exit 1 (`:35-38`).
- Missing command and no `--install`: `exec omarchy-launch-floating-terminal-with-presentation omarchy-default-browser --install <choice>` (`:43`). The selector's exit status is then the launcher's.
- Missing command with `--install`: `omarchy-install-browser <choice> || exit 1` (`:45`). Every browser installer path calls `sudo` (`bin/omarchy-install-browser:9-12`, `:30`).
- Set (`:49`): `env -u BROWSER xdg-settings set default-web-browser <desktop id> || exit 1`. On this machine's xdg-utils, `XDG_CURRENT_DESKTOP=Hyprland` falls into the `generic` branch (`/usr/bin/xdg-settings:461`). `set_browser_generic` (`:1206-1221`) refuses when `BROWSER` is set, requires the desktop file to exist (`desktop_file_to_binary`, exit 2 otherwise), then calls `xdg-mime default <id>` for `text/html`, `x-scheme-handler/http`, `https`, `about`, and `unknown`. `xdg-mime default` writes `$XDG_CONFIG_HOME/mimeapps.list` (`/usr/bin/xdg-mime:1011-1015`). `get_browser_generic` (`:1156-1176`) returns `$BROWSER` mapped to a desktop file if set, else the `x-scheme-handler/http` handler. This is why the selector strips `BROWSER`.
- After the set, `omarchy-notification-send -g <glyph> "<name> is now the default browser"` (`:51`) is the last command, so the selector's exit status is the notification's. `omarchy-notification-send` runs `set -euo pipefail` and calls `busctl` (`bin/omarchy-notification-send:7`, `:195-210`). A selector can exit nonzero after a successful set.
- Not interactive on the set path. Interactive only inside the installer terminal (sudo password, yay prompts).
- Install-time default: `bin/omarchy-provision-user:112` runs `env -u BROWSER xdg-settings set default-web-browser chromium.desktop`. `bin/omarchy-remove-browser:8-19` resets to Chromium when the removed browser was current, so the value can change outside this module.

### 3.2 `omarchy-default-terminal`

- Query (`bin/omarchy-default-terminal:13-24`): `xdg-terminal-exec --print-id 2>/dev/null || true`, then strips everything from the first `:` (the tool appends an action id after a colon, per the upstream README). Maps four desktop ids to short names, prints anything else verbatim, exits 0. If `xdg-terminal-exec` is absent or finds no valid terminal, the output is an empty line.
- Choices (`:26-35`), in source order:

| Choice id | Command probed | Desktop id written | Display name | Installer (`bin/omarchy-install-terminal`) |
|---|---|---|---|---|
| `alacritty` | `alacritty` | `Alacritty.desktop` | Alacritty | `omarchy-pkg-add alacritty`, copies `default/alacritty/Alacritty.desktop` to `~/.local/share/applications/` (`:31-33`) |
| `foot` | `foot` | `foot.desktop` | Foot | `omarchy-pkg-add foot`, copies `applications/foot.desktop` to `~/.local/share/applications/` (`:34-36`) |
| `ghostty` | `ghostty` | `com.mitchellh.ghostty.desktop` | Ghostty | `omarchy-pkg-add ghostty` |
| `kitty` | `kitty` | `kitty.desktop` | Kitty | `omarchy-pkg-add kitty` |

- Set (`:45-49`): overwrites `~/.config/xdg-terminals.list` with two comment lines and the desktop id. The installer writes the same file (`bin/omarchy-install-terminal:45-49`) and also seeds `~/.config/<terminal>/` from `$OMARCHY_PATH/config/<terminal>` when absent (`:40-42`).
- Exit status: same notification tail as the browser (`:51`).
- Defect (verified by reading): `bin/omarchy-install-terminal:29-52` prints `Failed to install <pkg>` in the `else` branch and then reaches end of file, so the script exits 0 after a failed package install. `bin/omarchy-default-terminal:41` therefore does not `exit 1`, and `:45-49` writes the preference for a terminal that is not installed. The module must verify by command presence and `xdg-terminal-exec --print-id`, never by the installer's exit status. Upstream fix recommended: `exit 1` after the echo.
- Lookup order (upstream README, xdg-terminal-exec): `~/.config/hyprland-xdg-terminals.list`, `~/.config/xdg-terminals.list`, `/etc/xdg/hyprland-xdg-terminals.list`, `/etc/xdg/xdg-terminals.list`, then `<XDG_DATA_DIRS>/xdg-terminal-exec/{hyprland-,}xdg-terminals.list`. A desktop-specific user file shadows the file the selector writes. Omarchy ships `default/xdg-terminal-exec/hyprland-xdg-terminals.list` containing `foot.desktop` (`:3`), installed to `/usr/share/xdg-terminal-exec/hyprland-xdg-terminals.list` (`test/shell.d/config-test.sh:134`). With no user file, the effective default is Foot.
- `xdg-terminal-exec` is in `install/omarchy-base.packages:145`. It is not installed on the machine used for this session, so `--print-id` output was not observed live. The README format `entry-id.desktop[:action]` is what the selector's `%%:*` strip assumes.

### 3.3 `omarchy-default-editor`

- Query (`bin/omarchy-default-editor:13-22`): reads the first line of `~/.local/state/omarchy/defaults/editor`. Prints `nvim` when the file is absent or its first line is empty. Exits 0. Prints unknown file content verbatim.
- Choices (`:24-37`), in source order:

| Choice id | Stored and reported value | Command probed | Display name | Installer (`:43-52`) |
|---|---|---|---|---|
| `code` | `code` | `code` | VSCode | `omarchy-install-editor-vscode` (`omarchy-pkg-add visual-studio-code-bin`, writes `~/.vscode/argv.json` and `~/.config/Code/User/settings.json`, launches VS Code) |
| `cursor` | `cursor` | `cursor` | Cursor | `omarchy-pkg-add cursor-bin` |
| `zed` (alias `zeditor` accepted) | `zeditor` | `zeditor` | Zed | `omarchy-install-editor-zed` (`omarchy-pkg-add zed omazed`, `omazed setup`, launches Zed) |
| `sublime_text` | `sublime_text` | `sublime_text` | Sublime Text | `omarchy-pkg-add sublime-text-4` |
| `helix` | `helix` | `helix` | Helix | `omarchy-install-editor-helix` (`omarchy-pkg-add helix`, theme symlink, appends alias to `~/.bashrc`) |
| `vim` | `vim` | `vim` | Vim | `omarchy-pkg-add vim` |
| `emacs` | `emacs` | `emacs` | Emacs | `omarchy-install-editor-emacs` (`omarchy-pkg-aur-add omarchy-emacs && omarchy-install-emacs`, launches emacsclient). `omarchy-install-emacs` is not in `bin/` at `71b0887c`; presumably shipped by the `omarchy-emacs` package. Unverified. |
| `nvim` | `nvim` | `nvim` | Neovim | `omarchy-pkg-add neovim` |

- Set (`:56-57`): `mkdir -p` the directory and `printf '%s\n' "$editor"` into the state file. Note the stored value for the `zed` choice is `zeditor`, so the catalog needs a separate `reported` field. The menu's checked guard compares against `zeditor` (`default/omarchy/omarchy-menu.jsonc:165`).
- `omarchy-launch-editor:15-21` reads the same file and falls back to `nvim` when the stored command is missing, so a broken editor default still launches something. The page must still report it as broken; the fallback is a launcher courtesy, not a state.
- The editor selector changes nothing in `mimeapps.list`. `text/plain` stays on `nvim.desktop` from `default/applications/mimeapps.list:33`.
- Exit status: install failure exits 1 (`:52`); otherwise the notification tail (`:59`).

### 3.4 `omarchy-default-agent`

- Query (`bin/omarchy-default-agent:13-24`): reads the first line of `~/.config/omarchy/defaults/agent`. Prints nothing when the file is absent or empty (the comment at `:20-21` says Omarchy picks no agent). Exits 0. Note the path is under `.config`, not `.local/state` like the editor (`test/shell.d/default-agent-test.sh:340-341` asserts this).
- Choices (`:26-41`), in source order, with accepted aliases and mise package:

| Choice id | Aliases accepted by the selector | mise package | Display name |
|---|---|---|---|
| `pi` | none | `pi` | Pi |
| `omp` | `oh-my-pi` | `github:can1357/oh-my-pi` | Oh My Pi |
| `opencode` | `open-code` | `opencode` | OpenCode |
| `ori` | `openrouter` | `github:OpenRouterLabs/ori-releases` | Ori |
| `claude` | `claude-code` | `claude` | Claude Code |
| `codex` | none | `codex` | Codex |
| `crush` | none | `crush` | Crush |
| `grok` | none | `npm:@xai-official/grok` | Grok |
| `agy` | `antigravity`, `antigravity-cli`, `gemini`, `gemini-cli` | `antigravity-cli` | Antigravity |
| `copilot` | `github-copilot` | `copilot` | GitHub Copilot |

- Installed predicate (`:45`): `mise where <package>`. Not `command -v`. This matters because `install/user/mise.sh:1-15` installs a lazy wrapper at `~/.local/bin/<command>` for every one of these agents on first login (`bin/omarchy-mise-install:21-29`). The wrapper runs `mise use -g --quiet <package>` on first invocation. So `command -v claude` succeeds on a fresh Omarchy even though nothing is installed. PATH lookup is not evidence for agents.
- Set path (`:49-66`): `mise use -g <package>` (writes `~/.config/mise/config.toml`), then writes the state file, then `exec omarchy-agent` (a new terminal via `bin/omarchy-launch-tui:13`, which is `exec setsid uwsm-app -- xdg-terminal-exec --app-id=org.omarchy.agent -e <agent argv>`). With `--install`, it clears the screen and `exec omarchy-agent --inline` in the same terminal (`:61-63`), so the Done prompt never appears until the agent exits.
- Exit status: usage 1 (`:37-40`); `mise use -g` failure 1 with `Could not install <name> with mise` or `Could not set <name> as the default coding agent` on stderr (`:49-56`). After the file is written, `omarchy-agent` exits 1 if the agent command is missing (`bin/omarchy-agent:49-52`) or unset. That failure happens after the state file changed, so a nonzero exit does not mean "unchanged".
- Missing agent and no `--install` (`:45-47`): same handoff pattern as the others.
- There is no Omarchy default agent. `install/user/first-run/setup-agent.hook:7-10` sends a notification inviting the user to pick one.
- `omarchy-agent` changes directory to `~/Work` when launched from `$HOME` (`bin/omarchy-agent:36`). Irrelevant to this module except that the backend should not run the selector with cwd inside a project.

### 3.5 Shared helpers

- `bin/omarchy-cmd-missing:5-11`: exit 0 if any named command is absent from PATH. `bin/omarchy-cmd-present` is the inverse.
- `bin/omarchy-launch-floating-terminal-with-presentation:8-13`: sources `omarchy-restart-gum` (exports gum colours from `~/.local/state/omarchy/current/theme/gum_env.lua`), joins its arguments with spaces into `cmd="$*"`, and `exec setsid uwsm-app -- xdg-terminal-exec --app-id=org.omarchy.terminal --title=Omarchy -e bash -c "omarchy-show-logo; $cmd; if (( $? != 130 )); then omarchy-show-done; fi"`. Two consequences. First, the argv is re-split by `bash -c`, so only whitespace-free tokens survive intact. Every token this module passes is a fixed catalog string. Second, the launcher exposes no completion channel; whether `uwsm-app` returns immediately or blocks until the terminal exits was not verified in this session.
- `bin/omarchy-show-done:7`: exits 0 immediately when `/dev/tty` cannot be opened, otherwise waits for a keypress. Inside the floating terminal there is a tty, so the window stays open after a successful install until the user presses a key.
- `bin/omarchy-pkg-add:8-22`: `sudo pacman -S --noconfirm --needed`, then `pacman -Q` per package, exit 1 if any is absent. `bin/omarchy-pkg-aur-add:6-17`: same with `yay`.
- `bin/omarchy` metadata: `omarchy commands --json` emits `{ok, commands:[{route, binary, group, name, summary, requires_sudo, hidden, args, examples, aliases, filename_route, routes}]}` (`bin/omarchy:670-686`). Running it at `71b0887c` with `OMARCHY_PATH` set gives `args` of `[chromium|chrome|brave|brave-origin|edge|firefox|zen]`, `[alacritty|foot|ghostty|kitty]`, `[code|cursor|zed|sublime_text|helix|vim|emacs|nvim]`, and `[pi|omp|opencode|ori|claude|codex|grok|agy|copilot|crush]` for the four `default` group commands. The `--install` flag and the agent aliases are not in the metadata (`agents/skills/command-metadata.md` lists only summary, args, examples, aliases, hidden, requires-sudo).

### 3.6 Where the Omarchy defaults come from

| Category | Default | Evidence |
|---|---|---|
| Browser | `chromium` | `bin/omarchy-provision-user:112`; `test/acceptance.d/system-test.sh:23` and `:40` (HTTP handler is `chromium.desktop`) |
| Terminal | `foot` | `default/xdg-terminal-exec/hyprland-xdg-terminals.list:3`; `test/acceptance.d/system-test.sh:26` |
| Editor | `nvim` | `bin/omarchy-default-editor:20`; `test/acceptance.d/system-test.sh:29` |
| Agent | none | `bin/omarchy-default-agent:20-22`; `test/shell.d/default-agent-test.sh:250` |

### 3.7 Other commands checked and excluded

`bin/` at `71b0887c` has no other `omarchy-default-*`. Commands ending in `-set` are `omarchy-audio-input-set-default`, `omarchy-audio-output-set-default`, `omarchy-channel-set`, `omarchy-font-set`, `omarchy-plymouth-set`, `omarchy-plymouth-set-by-theme`, `omarchy-powerprofiles-set`, `omarchy-theme-*-set*`. None of them selects an application for a role, so none belongs here. `default/applications/mimeapps.list` seeds `inode/directory`, images, PDF, video, `mailto`, and text types at install time, and `bin/omarchy-provision-user:113` sets `HEY.desktop` for `mailto`, but there is no query or set command for those roles and no choice list. They stay out until Omarchy adds one.

### 3.8 Menu and tests as cross-checks

- `default/omarchy/omarchy-menu.jsonc:136-169` lists every choice above with the same ids and with `checked` guards comparing the selector output. Menu order is alphabetical for agents and source order for the rest; `test/shell.d/menu-test.sh:218-262` pins both. The catalog display order follows the menu.
- `shell/plugins/menu/MenuModel.js:396-403` lists the four selectors as `GUARD_READERS`, run once per menu open. The selectors are therefore safe to call frequently.
- `test/shell.d/default-apps-test.sh` and `test/shell.d/default-agent-test.sh` are the upstream contract suites. The stub shapes in this plan (section 16) mirror theirs so a behaviour change upstream shows up in both.

## 4. Module layout

```text
modules/defaults/
├── module.json
├── Page.qml
├── components/
│   ├── CategoryCard.qml          # one per category; owns the card state machine (section 12)
│   ├── ChoicePicker.qml          # searchable list of choices with state badges
│   ├── ChoiceDetails.qml         # disclosure: command, desktop id, package, installer, side effects
│   ├── CurrentValue.qml          # current label, raw value, health badge, unknown presentation
│   └── PendingHandoff.qml        # "continue in the terminal" panel with elapsed time and recheck
├── backend/
│   ├── __init__.py               # exports MODULE
│   ├── catalog.py                # CATALOG constant plus load/validate
│   ├── probes.py                 # selector, xdg, mise, desktop-file, PATH probes
│   ├── status.py                 # classification and revision
│   ├── planner.py                # validate and plan
│   └── verify.py                 # verify and reconcile logic
├── schemas/
│   ├── catalog-v1.json
│   ├── draft-v1.json
│   └── status-v1.json
└── tests/
    ├── fixtures/                 # stub commands and fake homes (section 16)
    ├── test_catalog.py
    ├── test_probes.py
    ├── test_status.py
    ├── test_planner.py
    ├── test_verify.py
    └── test_page.qml
```

`module.json`:

```json
{
  "id": "defaults",
  "title": "Default applications",
  "icon": "",
  "navOrder": 40,
  "page": "Page.qml",
  "backend": "modules.defaults.backend",
  "schemas": ["schemas/draft-v1.json", "schemas/status-v1.json"],
  "coreServices": ["BackendClient", "DraftStore", "ApplyBar", "ConfirmDialog", "ErrorBanner", "SearchField", "UndoToast"]
}
```

The backend registers with one line in `backend/customization_center/modules/__init__.py`. Nothing in `core/` mentions this module.

## 5. Capability catalog

### 5.1 Ownership

`modules/defaults/backend/catalog.py` holds the catalog as a Python constant and validates it against `schemas/catalog-v1.json` at import time in tests. The QML page receives the catalog only as part of `status` output and never carries its own copy of ids, commands, or packages.

The catalog is pinned to an Omarchy baseline. At `capabilities()` time the backend runs `omarchy commands --json` (timeout 5 s) and compares the `args` string of each of the four `default` group entries with the catalog's choice ids joined by `|`. A mismatch marks the category `drifted`: status stays readable, `validate()` rejects changes to that category with `defaults_catalog_drift`, and the page shows which ids differ. If `omarchy commands` is missing or times out, the backend records a warning and continues; the selectors themselves are the hard requirement.

### 5.2 Schema

Category object:

| Field | Type | Meaning |
|---|---|---|
| `id` | `"browser" \| "terminal" \| "editor" \| "agent"` | Category id, also the draft key |
| `label` | string | Card title |
| `summary` | string | One sentence under the title, e.g. "Web links and the browser XDG handlers" |
| `selector` | string | Executable name: `omarchy-default-<id>` |
| `route` | string | The `omarchy commands` route to compare `args` against, e.g. `omarchy default browser` |
| `stateSource` | object | How the selector reads the current value. `kind`: `xdg-settings`, `xdg-terminal-exec`, or `file`. `path` for `file` kind, absolute after `$HOME` expansion |
| `stateFile` | string or null | The file the setter writes and the executor backs up: `~/.config/mimeapps.list`, `~/.config/xdg-terminals.list`, `~/.local/state/omarchy/defaults/editor`, `~/.config/omarchy/defaults/agent` |
| `emptyOutputMeans` | `"unset" \| "none_resolvable" \| null` | `unset` for agent, `none_resolvable` for terminal, null for browser (empty output is a probe failure) and editor (never empty) |
| `defaultChoice` | choice id or null | `chromium`, `foot`, `nvim`, null |
| `installedPredicate` | `"path" \| "mise"` | Which probe the selector uses before deciding to install |
| `setLaunches` | boolean | true for agent |
| `setTimeoutS` | integer | 30 for browser, terminal, editor; 60 for agent |
| `choices` | array | Ordered as the menu shows them |

Choice object:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Canonical argument passed to the selector. Also the value the query prints for browser, terminal, agent |
| `label` | string | Display name from the selector's `name=` |
| `aliases` | array of string | Inputs the selector also accepts. Used only to normalise stray values found in state files. The backend never emits them |
| `reported` | string | What the query prints when this choice is current. Equals `id` except editor `zed` reports `zeditor` |
| `command` | string or null | Executable the selector probes with `command -v`. Null for agents |
| `desktopId` | string or null | Desktop entry the setter writes. Browser and terminal only |
| `misePackage` | string or null | Agents only |
| `package` | object or null | `{ "name": string, "source": "pacman" \| "aur" }` for information. Null for agents (mise handles it) |
| `installer` | object | `{ "kind": "selector-install" }` always; `summary`: one line describing what the installer does, from section 3; `needsSudo`: boolean; `launchesApp`: boolean (VS Code, Zed, Emacs installers and every agent) |
| `icon` | string | Nerd Font glyph from the selector, display only |

Full contents are the tables in sections 3.1 to 3.4. `needsSudo` is true for every browser, every terminal, and every editor (all go through `omarchy-pkg-add` or `omarchy-pkg-aur-add`), and false for agents. `launchesApp` is true for `code`, `zed`, `emacs`, and all ten agents.

### 5.3 Catalog tests

- Every category has exactly the choice ids the selectors' `case` arms accept, in menu order.
- `route` args match the catalog when run against the pinned Omarchy checkout (a fixture copy of the four selector headers).
- Every `desktopId` is unique within its category. Every `id` is unique within its category. No `id` contains whitespace or shell metacharacters (they are re-split by `bash -c` in the launcher).
- `reported` differs from `id` only for editor `zed`.

## 6. Detection algorithm

`status()` runs the following for each category. Every subprocess goes through `ctx.commands.run(argv, timeout_s, env_extra={"BROWSER": None})` with `shell=False`, a 64 KiB capture limit, and the session environment with `BROWSER` unset. Probes for different categories run in parallel; probes inside one category run in the order below.

1. Query the selector: `[selector]`, timeout 5 s. Record `exitCode`, `stdout` (first line, stripped of the trailing newline only), and whether stdout had more than one line. Missing executable, timeout, or nonzero exit gives `probe_error` for the category. Multi-line output gives `probe_error` with `malformed_output`.
2. Read the raw state the selector read, so the revision and the verify step do not depend on the selector's mapping:
   - browser: `["env", "-u", "BROWSER", "xdg-settings", "get", "default-web-browser"]`, plus `["xdg-mime", "query", "default", <type>]` for `text/html`, `x-scheme-handler/http`, `x-scheme-handler/https`. Record all four. Missing `xdg-settings` is `probe_error`.
   - terminal: `["xdg-terminal-exec", "--print-id"]`, strip from the first `:`. Record the full output too. Record whether `~/.config/xdg-terminals.list` exists, its sha256, and its last non-comment line. Record whether `~/.config/hyprland-xdg-terminals.list` exists; if it does, add warning `defaults_terminal_shadowed` because it takes priority over the file the selector writes. Missing `xdg-terminal-exec` is `probe_error`.
   - editor: existence and first line of `~/.local/state/omarchy/defaults/editor`.
   - agent: existence and first line of `~/.config/omarchy/defaults/agent`.
3. Map the selector output to a choice: find the choice whose `reported` equals the output. If none and the output is empty, apply `emptyOutputMeans`. If none and the output is non-empty, the category is `unknown` with `current.raw` set (section 13). For editor and agent, additionally try `aliases` against the raw file line; a match is reported as `current.choice` with `current.normalisedFromAlias: true` (the selector's own query would print the alias verbatim, so this is display help, and verify still compares raw values).
4. For every choice, compute three independent facts:
   - `runnable`: for `installedPredicate: path`, `shutil.which(command, path=env["PATH"])` is not None. For `mise`, `["mise", "where", misePackage]` exits 0 (timeout 5 s; `mise` missing gives `runnable: null` and a category warning). This is the fact that decides between `RunCommand` and `TerminalHandoff`, because it is what `bin/omarchy-cmd-missing` and `bin/omarchy-default-agent:45` test.
   - `integration`: for choices with a `desktopId`, the first existing file among `$XDG_DATA_HOME/applications/<desktopId>` (default `~/.local/share/applications`) and `<dir>/applications/<desktopId>` for each entry of `$XDG_DATA_DIRS` (default `/usr/local/share:/usr/share`). Record the path found or null. For agents, `integration` is whether `~/.local/bin/<id>` exists and contains the line `mise use -g --quiet "<misePackage>"` (a lazy wrapper), recorded as `wrapper: true|false`. Editors have no integration fact.
   - `package`: `["pacman", "-Q", package.name]` exit 0, for choices with `package`. One `pacman -Qq` call per status, parsed into a set, instead of 19 forks. Display only.
5. Choice state:
   - `available`: `runnable` and (`integration` satisfied or not applicable). For the browser, a missing desktop file makes `xdg-settings set` fail with exit 2, so a browser with a command but no desktop file is `degraded`, not `available`.
   - `degraded`: `runnable` but a required `desktopId` file is missing. Plan refuses `set` for a degraded browser (`defaults_desktop_entry_missing`); allows it for a degraded terminal with a warning, because the selector will write the file anyway and `xdg-terminal-exec` will then not resolve it, which verify catches.
   - `missing`: not `runnable`. Install and set is the only action.
   - `unprobed`: `runnable` is null (mise absent).
6. Category state from the current choice: `ready` when the current choice is `available`; `broken` when the current choice is known but `missing` or `degraded`; `unknown`, `unset`, `none_resolvable`, or `probe_error` as above.
7. Precedence when facts disagree: `runnable` decides the action; `integration` decides `available` versus `degraded`; `package` never changes state. A choice installed outside pacman (a manual binary on PATH with a desktop file) is `available` with `package.installed: false`, and the details panel says "not from a package".

Cost: four selector runs, one `xdg-settings get`, three `xdg-mime query`, one `xdg-terminal-exec`, one `pacman -Qq`, ten `mise where`, plus file stats. Around 20 forks. The menu's guard batch runs the same four selectors on every open, so this is within what Omarchy already does interactively.

## 7. Status output

`ccctl status defaults` returns `data` shaped by `schemas/status-v1.json`:

```json
{
  "catalogBaseline": "omarchy-71b0887c",
  "drift": [],
  "warnings": [],
  "categories": [
    {
      "id": "browser",
      "label": "Browser",
      "state": "ready",
      "default": "chromium",
      "current": {
        "choice": "zen",
        "reported": "zen",
        "raw": {"defaultWebBrowser": "zen.desktop", "textHtml": "zen.desktop", "http": "zen.desktop", "https": "zen.desktop"},
        "normalisedFromAlias": false
      },
      "checks": [
        {"id": "selector", "ok": true, "expected": "zen", "actual": "zen"},
        {"id": "xdg_default_web_browser", "ok": true, "expected": "zen.desktop", "actual": "zen.desktop"},
        {"id": "xdg_http", "ok": true, "expected": "zen.desktop", "actual": "zen.desktop"},
        {"id": "xdg_https", "ok": true, "expected": "zen.desktop", "actual": "zen.desktop"},
        {"id": "command", "ok": true, "expected": "zen-browser", "actual": "/usr/bin/zen-browser"},
        {"id": "desktop_entry", "ok": true, "expected": "zen.desktop", "actual": "/usr/share/applications/zen.desktop"}
      ],
      "choices": [
        {"id": "chromium", "label": "Chromium", "state": "available", "runnable": true, "commandPath": "/usr/bin/chromium", "desktopEntryPath": "/usr/share/applications/chromium.desktop", "package": {"name": "chromium", "source": "pacman", "installed": true}, "installer": {"summary": "...", "needsSudo": true, "launchesApp": false}}
      ],
      "pending": null
    }
  ]
}
```

`pending` is filled from the journal when a transaction for this category is in state `pending_handoff` (section 10). It carries `transactionId`, `choice`, `startedAt`, `argv`, and `lastReconciledAt`.

Revision: `sha256` over the canonical JSON of, per category, the selector's first line and exit code, the raw state values from step 2, the state file sha256 or `null`, and the sorted list of `runnable` values per choice. Package and desktop-entry facts are excluded so an unrelated `pacman -Syu` does not invalidate a draft; a package change that makes a choice runnable does change the revision, which is the case that matters for planning.

## 8. Draft and validation

`schemas/draft-v1.json`:

```json
{
  "schemaVersion": 1,
  "changes": {
    "browser": {"choice": "firefox", "install": false},
    "agent": {"choice": "claude", "install": true}
  }
}
```

`changes` has at most one entry per category. `choice` is a catalog id. `install` is the user's explicit consent to a terminal handoff if the choice is missing; the page sets it only after the confirmation dialog.

`validate(ctx, draft)` is pure and returns errors with these codes:

| Condition | Code | Blocking |
|---|---|---|
| Unknown category key or unknown choice id | `validation_failed` | yes |
| Choice id equals an alias rather than the canonical id | `validation_failed` (message names the canonical id) | yes |
| Category is `drifted` | `defaults_catalog_drift` | yes |
| Category is `probe_error` | `runtime_unavailable` | yes |
| Choice is `missing` and `install` is false | `defaults_target_missing` | yes |
| Choice is `missing`, `install` is true, and another change in the draft also needs install | `validation_failed` ("one install per apply") | yes |
| Choice is `missing`, `install` is true, and a pending handoff exists for any category | `defaults_handoff_pending` | yes |
| Browser choice is `degraded` | `defaults_desktop_entry_missing` | yes |
| Terminal choice is `degraded` | warning `defaults_desktop_entry_missing` | no |
| Choice is already current and the category is `ready` | warning `defaults_no_change` (plan is empty for that category) | no |
| Category is `agent` | warning `defaults_launches_agent` | no |
| Category is `unknown` | warning `defaults_replaces_unknown` with the raw value | no |

`validate(ctx, draft, status)` receives the last status, which is where the installed facts come from.

## 9. Plan

`plan(ctx, draft, status)` emits operations in this order: every `set` change first, ordered browser, terminal, editor, agent; then at most one `install_and_set`. Each operation carries `summary`, `backup_paths` (backed up by the executor before it runs), and `inverse`. The plan carries `residual_side_effects`, which is empty except for the agent.

### 9.1 Set an installed choice

```text
RunCommand(
  argv=["omarchy-default-browser", "firefox"],
  timeout_s=30,
  expect_exit=0,
  capture_limit=65536,
  env={"BROWSER": None},              # null unsets
  backup_paths=["~/.config/mimeapps.list"],
  summary="Set default browser to Firefox (firefox.desktop)",
  sideEffects=["notification"]
)
```

Per category:

| Category | argv | timeout | backup_paths | sideEffects |
|---|---|---|---|---|
| browser | `[omarchy-default-browser, <id>]` | 30 s | `~/.config/mimeapps.list` | notification |
| terminal | `[omarchy-default-terminal, <id>]` | 30 s | `~/.config/xdg-terminals.list` | notification |
| editor | `[omarchy-default-editor, <id>]` | 30 s | `~/.local/state/omarchy/defaults/editor` | notification |
| agent | `[omarchy-default-agent, <id>]` | 60 s, `wait_policy: detach` | `~/.config/omarchy/defaults/agent`, `~/.config/mise/config.toml` | launches_agent_terminal, mise_global_pin |

The agent op uses `wait_policy: detach`: the executor waits up to 60 s, and if the process is still alive it leaves it running and proceeds to verify. The selector ends in `exec omarchy-agent`, which ends in `exec setsid uwsm-app`, and I could not verify whether `uwsm-app` returns before the terminal closes. Killing it on timeout could kill the agent the user just asked for.

Inverse:

- If `status.current.choice` is a known choice whose state is `available` and the category is not agent: `RunCommand([selector, previousChoice])` with the same shape. This reruns Omarchy's own setter, which also re-sends the notification, so the user sees the revert.
- Otherwise (previous value unknown, previous choice missing, previous state unset, or category is agent): `RestoreBackup(stateFile)`. For the browser this restores `~/.config/mimeapps.list` wholesale, which is correct within one transaction because nothing else should have written it in between; the executor's revision check makes that assumption explicit. Restoring an absent file means deleting the one the setter created.
- The agent inverse never reruns the selector, because that would launch the previous agent. `~/.config/mise/config.toml` is backed up for the journal but not restored. The agent plan lists `mise_global_pin` and `running_agent` in `residual_side_effects` so the apply result and the history entry say what a rollback leaves behind.

`requiresConfirmation` is true for the agent (it launches a program) and for any change that replaces an `unknown` current value.

### 9.2 Install and set a missing choice

```text
TerminalHandoff(
  argv=["omarchy-default-editor", "zed"],
  title="Install Zed and set it as the default editor",
  wrapped=false,
  backup_paths=["~/.local/state/omarchy/defaults/editor"],
  summary="Open the Omarchy terminal to install Zed (packages zed, omazed via sudo pacman), then set it as the default editor. Zed opens when the install finishes.",
  sideEffects=["opens_terminal", "sudo", "launches_app"],
  inverse=None
)
```

`wrapped=false` because the selector opens its own terminal: with the target command missing and no `--install` flag, it `exec`s `omarchy-launch-floating-terminal-with-presentation omarchy-default-editor --install zed` (`bin/omarchy-default-editor:41`). Core runs the argv the same way as a detached `RunCommand` (new session, null stdio, wait at most 5 s) and does not wrap it in `cc-handoff`, so there is no sentinel file. `ccctl reconcile` decides from `status` and `verify` alone (section 10). The `--install` flag is never on an argv this module emits; test `plan_never_passes_install_flag` pins that.

A plan containing a `TerminalHandoff` ends there. The executor leaves the journal in `pending_handoff` once the selector has returned or 5 s have passed (section 10). `inverse` is `None`, which the core treats as non-reversible and which forces the confirmation dialog. There is nothing to reverse: until the terminal finishes, nothing has changed, and after it finishes, software has been installed that this module refuses to remove.

For the agent, the summary says the terminal will keep running the agent after installation (`bin/omarchy-default-agent:61-63`) and the Done prompt appears only after the user quits the agent.

### 9.3 Restore Omarchy default

A `set` plan with `choice` equal to `defaultChoice`. If the default is `missing` (Chromium uninstalled), it becomes an `install_and_set` plan and needs the same consent. The agent card has no restore action.

## 10. Terminal handoff flow

1. The user picks a `missing` choice. The card shows "Install and set". Clicking opens `ConfirmDialog` with the installer summary, the package names and source, whether sudo will prompt, whether an application window will open, and the sentence "The install runs in an Omarchy terminal window. This page will show the result when it can see the change." Confirming sets `install: true` in the draft.
2. `ApplyBar` runs validate, plan, review. The review shows the argv.
3. `ccctl apply defaults --draft ... --expected-revision ... --confirm-nonreversible`. The executor takes the lock, re-checks the revision, backs up `backup_paths`, runs earlier `RunCommand` sets, then runs the `TerminalHandoff` with `wrapped=false`: spawn `[selector, choice]` in a new session with null stdio and wait at most 5 s. Exit 0 within 5 s, or still running at 5 s, means the selector handed off to its terminal. Exit nonzero within 5 s means the shared code `handoff_failed`; the executor records reason `handoff_failed`, rolls back the earlier sets, and ends in `rolled_back`.
4. On a successful launch the executor writes the journal entry with state `pending_handoff`, `startedAt`, the argv, and the pre-state snapshot, releases the lock, and returns `{"ok": true, "transactionId": ..., "data": {"pendingHandoff": true}}`.
5. The page moves the card to `pending_handoff` and shows `PendingHandoff.qml`: choice, elapsed time, "Recheck", "Stop tracking". While the page is visible it calls `BackendClient.pollStatus("defaults", intervalMs)` with 5000 ms for the first 2 minutes, 20000 ms until 15 minutes, then `stopPolling` and rechecks only on focus, on reopen, or on Recheck. Each status result that lists a pending handoff transaction makes the page call `BackendClient.reconcile(transactionId)`; Recheck does the same immediately. The interval is not tied to terminal closure because the terminal stays open at the Done prompt (`bin/omarchy-show-done:16-17`) and, for agents, for as long as the agent runs.
6. `ccctl reconcile <transactionId>` takes the lock, runs `status()`, and calls `verify(ctx, plan, status_after)`. Because the handoff is unwrapped there is no sentinel file; `verify` answers from state alone:
   - `{"state": "pass"}`: the target choice is `available` and every check in section 11 passes for it. The executor moves the journal to `committed`.
   - `{"state": "fail", "level": "error", "code": "defaults_installed_not_set"}`: the target is `available` but the current value is unchanged. This is the `omarchy-install-terminal` defect shape, or an install that finished after the selector's own set failed. Nothing was changed, so the rollback walk has nothing to invert; the journal ends `rolled_back` with reason `verification` and the code in the record. The page shows "Installed, not set" and offers a plain Set, which is now an ordinary `RunCommand` plan.
   - `{"state": "pending"}`: neither of the above and no failure evidence. The journal stays `pending_handoff`.
   - `{"state": "fail", "level": "error", "code": "defaults_changed_unexpectedly"}`: the current value is neither the previous nor the target. Journal `rolled_back` with reason `verification`; the page shows both values and offers nothing automatic.
7. As a hint only, the page asks `ccctl query defaults terminal_windows`, which runs `hyprctl -j clients` and counts windows with `class == "org.omarchy.terminal"`. If the count is zero, the state is still `pending_handoff`, and more than 30 s have passed since launch, the page shows "The terminal is closed and nothing changed. The install was probably cancelled or failed." with Retry and Stop tracking. The window count is never treated as proof, because a user can have other Omarchy terminals open and `hyprctl` can be unavailable.
8. "Stop tracking" calls `BackendClient.abandon(transactionId)`, which runs `ccctl abandon <transactionId>`. The journal ends `rolled_back` with reason `user`; nothing is reverted because the previous default was never changed. The page then allows new install plans again.
9. Closing the overlay does not lose the entry. On the next open, `ccctl status defaults` lists the pending handoff transaction under `pending` and the page resumes `pollStatus`. Startup recovery leaves `pending_handoff` records alone because unwrapped handoffs have no sentinel.

For a pending agent handoff, `pass` means the state file names the target and `mise where` succeeds. The inline agent may still be running in the terminal; the page says so and does not wait for it.

## 11. Verify

`verify(ctx, plan, status_after)` compares, for each changed category, the checks below against `status_after`. All must pass. The check list is the same one `status()` publishes for the current choice, so the card can show exactly which check failed after an apply.

| Category | Check id | Expected | Actual from |
|---|---|---|---|
| browser | `selector` | `choice.reported` | selector stdout |
| browser | `xdg_default_web_browser` | `choice.desktopId` | `env -u BROWSER xdg-settings get default-web-browser` |
| browser | `xdg_text_html` | `choice.desktopId` | `xdg-mime query default text/html` |
| browser | `xdg_http` | `choice.desktopId` | `xdg-mime query default x-scheme-handler/http` |
| browser | `xdg_https` | `choice.desktopId` | `xdg-mime query default x-scheme-handler/https` |
| browser | `command` | `choice.command` on PATH | `shutil.which` |
| browser | `desktop_entry` | file exists | XDG data dir search |
| terminal | `selector` | `choice.reported` | selector stdout |
| terminal | `xdg_terminal_exec` | `choice.desktopId` | `xdg-terminal-exec --print-id`, before the first `:` |
| terminal | `preference_file` | `choice.desktopId` | last non-comment line of `~/.config/xdg-terminals.list` |
| terminal | `command` | `choice.command` on PATH | `shutil.which` |
| terminal | `desktop_entry` | file exists | XDG data dir search |
| editor | `selector` | `choice.reported` | selector stdout |
| editor | `state_file` | `choice.reported` | first line of the editor state file |
| editor | `command` | `choice.command` on PATH | `shutil.which` |
| agent | `selector` | `choice.id` | selector stdout |
| agent | `state_file` | `choice.id` | first line of the agent state file |
| agent | `mise_where` | exit 0 | `mise where <misePackage>` |

The browser checks match what `xdg-settings check default-web-browser <id>` tests in the generic branch (`/usr/bin/xdg-settings:1180-1203`: http handler, `text/html`, https handler). The module runs the individual queries instead of `check` so the failing one can be named. `about` and `unknown` scheme handlers are also set by `set_browser_generic` but are not verified; they do not affect link opening and older `mimeapps.list` files often lack them.

The terminal `preference_file` check exists to detect the shadowing case: when `xdg_terminal_exec` fails but `preference_file` passes, the page says "Omarchy wrote the preference but xdg-terminal-exec resolves a different terminal" and names `~/.config/hyprland-xdg-terminals.list` if it exists.

`verify` returns `{"state": "pass"}`, `{"state": "fail", "level": "error", "code": ...}`, or `{"state": "pending"}`. A `fail` after a `RunCommand` set makes the executor run the inverses. After a `TerminalHandoff`, `pending` is the normal answer until the install shows up in status; the codes for the two failure shapes are in section 10 step 6.

## 12. Category card state machine

Each `CategoryCard.qml` derives its state from `status`, `draft`, `capabilities`, and the apply progress the shell reports. States and the actions available in each:

| State | Entered when | Card shows | Actions |
|---|---|---|---|
| `loading` | page opened, status not yet received | skeleton | none |
| `ready` | `status.state == ready` and no draft change | current label, green badge | pick another choice, Restore default (if not current) |
| `unset` | agent, `state == unset` | "No coding agent selected" | pick |
| `none_resolvable` | terminal, `state == none_resolvable` | "xdg-terminal-exec finds no terminal" and the last preference line if any | pick |
| `broken` | `state == broken` | current label, amber badge, failed checks listed | Install and set for the current choice ("Repair"), pick another |
| `unknown` | `state == unknown` | raw value (section 13), grey badge | pick (with replace warning) |
| `probe_error` | `state == probe_error` or category `drifted` | error code, command, stderr excerpt | Retry (re-run status); picking disabled |
| `drafted` | draft has a change for this category | before and after, "unapplied" tag | change pick, clear |
| `applying` | shell reports apply in progress | spinner, current operation summary | none |
| `pending_handoff` | `status.pending` lists a `pending_handoff` transaction for this category | `PendingHandoff.qml` | Recheck, Stop tracking |
| `installed_not_set` | last reconcile returned that code | "Installed, not set" | Set (plain plan) |
| `verify_failed` | apply result has `verify` failure and rollback succeeded | expected versus actual for each failed check, "restored previous default" | Retry, Recheck |
| `rollback_failed` | apply result has `rollback_failed` | paths of retained backups and the manual command to run | Recheck |
| `stale` | apply returned `stale_revision` | "Changed outside this page" | Reload (keeps the intended choice as a draft) |

Transitions: `loading` goes to any probe-derived state. Any probe-derived state goes to `drafted` on pick and back on clear. `drafted` goes to `applying` on apply, then to `ready` (after a successful status refresh), `pending_handoff`, `verify_failed`, `rollback_failed`, or `stale`. `pending_handoff` goes to `ready` on `pass`, to `installed_not_set`, to a probe-derived state after abandon (`rolled_back`, reason `user`), or stays. `installed_not_set` goes to `drafted` when the user clicks Set. Every state except `applying` and `loading` allows opening the details disclosure and the history view.

Global rule: while any card is `applying` or `pending_handoff`, other cards can still be drafted and applied with `set` plans, but no card offers Install and set. The validation code `defaults_handoff_pending` enforces the same rule in the backend.

## 13. Presenting an unknown current value

An unknown value is a selector output that is non-empty and matches no `reported` value. The card shows:

- Headline: "Not an Omarchy choice".
- The raw value, escaped, truncated to 120 characters with an ellipsis, control characters replaced by `U+FFFD`, in a monospace field with a copy button.
- Where it came from: "xdg-settings reports `zen-browser-beta.desktop`", "xdg-terminal-exec resolves `org.wezfurlong.wezterm.desktop`", "`~/.local/state/omarchy/defaults/editor` contains `micro`", "`~/.config/omarchy/defaults/agent` contains `aider`".
- For browser and terminal, if the desktop file resolves in the XDG data dirs, its `Name=` value labelled "from the desktop file". This is display only; the module still does not know how to launch, verify, or restore it beyond the backup.
- The sentence "Choosing an Omarchy choice replaces this. Rollback restores the file as it is now."

Picking a choice from an `unknown` card adds the `defaults_replaces_unknown` warning to validation, which `ApplyBar` shows in the review step. The inverse is always `RestoreBackup(stateFile)` in this case (section 9.1).

## 14. Page contract

`modules/defaults/Page.qml` follows the shared page contract: `moduleId: "defaults"`, `status`, `draft`, `capabilities`, `requestPlan()`, `requestApply()`, `requestReset()`, `requestNavigate()`, `focusFirst()`, and `handlePayload(payload)`. The payload is `{"module": "defaults", "category": "<id>"}`, optionally with `"choice": "<id>"`; the page scrolls to that card, focuses its picker, and, when `choice` is present and valid, drafts it without applying. Desktop modes uses this for "Edit in module". It lays out four `CategoryCard` instances in a single column (two columns above 1400 px logical width), in the order browser, terminal, editor, agent. `focusFirst()` focuses the browser card's picker. Picker rows are keyboard-navigable; Enter drafts; Escape clears search. Each card's details disclosure shows command, desktop id or mise package, package and source, installer summary, sudo and launch flags, and the exact argv the plan will run.

The page never calls `ccctl`. It edits `draft.changes[category]`, and `ApplyBar` does the rest. While a handoff is pending the page uses `BackendClient.pollStatus("defaults", intervalMs)` and `stopPolling`, and calls `BackendClient.reconcile(transactionId)` and `BackendClient.abandon(transactionId)` as described in section 10.

## 15. Error codes

Shared codes used: `stale_revision`, `validation_failed`, `runtime_unavailable` (selector, `xdg-settings`, or `xdg-terminal-exec` missing), `locked`, `timeout`, `malformed_output`, `rollback_failed`, `nonreversible_requires_confirmation`, `handoff_failed` (the selector exited nonzero within 5 s of the unwrapped handoff).

Module codes:

| Code | Meaning |
|---|---|
| `defaults_catalog_drift` | `omarchy commands --json` args differ from the catalog for this category |
| `defaults_target_missing` | choice is not runnable and the draft did not consent to install |
| `defaults_desktop_entry_missing` | browser choice has no desktop file, so `xdg-settings set` would fail |
| `defaults_handoff_pending` | another handoff is pending; install refused |
| `defaults_installed_not_set` | reconcile found the target installed but the current value unchanged |
| `defaults_changed_unexpectedly` | reconcile found a third value |
| `defaults_terminal_shadowed` | warning: `~/.config/hyprland-xdg-terminals.list` exists |
| `defaults_launches_agent` | warning attached to any agent change |
| `defaults_replaces_unknown` | warning attached to a change on an `unknown` category |
| `defaults_no_change` | warning: the chosen value is already current |

## 16. Test matrix

All backend tests run with an isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_DATA_HOME`, and a `PATH` whose first entry is a fixture bin directory. Fixture stubs live under `modules/defaults/tests/fixtures/bin/` and are shaped like the upstream stubs in `test/shell.d/default-apps-test.sh:20-106` and `test/shell.d/default-agent-test.sh:24-75`: each stub logs its argv NUL-separated to a file named by an environment variable and behaves according to a small set of environment switches.

Stubs:

| Stub | Behaviour |
|---|---|
| `omarchy-default-browser` | no args: prints `$FX_BROWSER_QUERY` (may be empty or multi-line) and exits `$FX_BROWSER_QUERY_EXIT` (default 0); with arg: logs argv; if the target command is absent from the fixture bin, execs the launcher stub with `--install <arg>` like the real selector; otherwise exits `$FX_BROWSER_SET_EXIT` and writes `$FX_BROWSER_QUERY` file if `$FX_BROWSER_SET_APPLIES=1` |
| `omarchy-default-terminal`, `omarchy-default-editor`, `omarchy-default-agent` | same pattern; the editor stub writes the real state file when applying, the agent stub writes its state file and honours `$FX_AGENT_MISE_FAIL` |
| `xdg-settings` | `get` prints `$FX_XDG_BROWSER`; `set` logs; `check` unused |
| `xdg-mime` | `query default <type>` prints from `$FX_XDG_<TYPE>` |
| `xdg-terminal-exec` | `--print-id` prints `$FX_TERMINAL_ID` (may include `:action`), exit `$FX_TERMINAL_EXIT` |
| `mise` | `where <pkg>` exits 0 if `<pkg>` is in `$FX_MISE_INSTALLED` (space separated) |
| `pacman` | `-Qq` prints `$FX_PACMAN_INSTALLED` one per line |
| `omarchy` | `commands --json` prints `fixtures/commands-71b0887c.json`, or the drifted variant when `$FX_COMMANDS_DRIFT=1`, or exits 127 when `$FX_COMMANDS_MISSING=1` |
| `omarchy-launch-floating-terminal-with-presentation` | logs argv, exits `$FX_LAUNCHER_EXIT`, sleeps `$FX_LAUNCHER_SLEEP` seconds first |
| `hyprctl` | `-j clients` prints `$FX_HYPR_CLIENTS` |
| fake commands `chromium`, `firefox`, `zen-browser`, `foot`, `kitty`, `nvim`, `zeditor`, `code` | present only when the test creates them in the fixture bin |

Desktop files: `fixtures/applications/` holds `chromium.desktop`, `firefox.desktop`, `zen.desktop`, `foot.desktop`, `kitty.desktop`, copied into the fake `XDG_DATA_HOME/applications` per test.

Cases (name, setup, expected):

Catalog and capabilities:

- `catalog_matches_selector_headers`: parse `args` from the four fixture headers; equals catalog ids in order.
- `capabilities_drift_blocks_category`: `FX_COMMANDS_DRIFT=1` adds `wezterm` to terminal args; status readable, validate returns `defaults_catalog_drift` for terminal only.
- `capabilities_without_omarchy_command`: `FX_COMMANDS_MISSING=1`; warning present, no drift, mutations allowed.

Status:

- `status_ready_all_four`: query outputs `zen`, `kitty`, `nvim`, `claude`; matching XDG, file, mise fixtures; all four `ready`, revision stable across two calls.
- `status_editor_absent_file_is_nvim`: no editor file; selector prints `nvim`; state `ready`, `current.raw.exists == false`.
- `status_agent_absent_file_is_unset`: selector prints empty; state `unset`; no warning.
- `status_terminal_empty_is_none_resolvable`: `FX_TERMINAL_ID=""` and `FX_TERMINAL_EXIT=1`; selector prints empty; state `none_resolvable`.
- `status_browser_empty_is_probe_error`: `FX_XDG_BROWSER=""`; state `probe_error`.
- `status_unknown_browser`: selector prints `zen-browser-beta.desktop`; state `unknown`, raw preserved, Name from a fixture desktop file when present.
- `status_editor_alias_in_file`: file contains `zeditor`; selector prints `zeditor`; current choice `zed`, `reported == "zeditor"`.
- `status_agent_alias_in_file`: file contains `gemini`; selector prints `gemini`; current choice `agy` with `normalisedFromAlias: true`, and verify would still compare raw.
- `status_broken_current`: selector prints `kitty`, `kitty` binary absent; state `broken`, `command` check fails.
- `status_browser_degraded`: `firefox` on PATH, no `firefox.desktop`; choice state `degraded`.
- `status_agent_wrapper_only`: `~/.local/bin/claude` wrapper present, `mise where` fails; choice `missing`, `wrapper: true`.
- `status_terminal_shadowed`: `~/.config/hyprland-xdg-terminals.list` exists; warning `defaults_terminal_shadowed`.
- `status_multiline_selector_output`: `FX_BROWSER_QUERY` has two lines; `probe_error` with `malformed_output`.
- `status_selector_timeout`: stub sleeps 10 s; `probe_error` with `timeout`; other categories unaffected.
- `status_path_predicate_matches_cmd_missing`: for each catalog command present or absent in the fixture bin, `shutil.which` result equals the exit of the real `bin/omarchy-cmd-missing` run with the same PATH.
- `revision_changes_on_runnable_change`: adding `foot` to the fixture bin changes the revision; changing `FX_PACMAN_INSTALLED` alone does not.

Validate and plan:

- `plan_set_installed_browser`: one `RunCommand` with argv `["omarchy-default-browser", "firefox"]`, env with `BROWSER` unset, `backup_paths` containing `mimeapps.list`, inverse `RunCommand([..., "zen"])`.
- `plan_set_from_unknown_uses_restore`: current unknown; inverse is `RestoreBackup`.
- `plan_agent_set`: `RunCommand` with `wait_policy: detach`, `requiresConfirmation: true`, inverse `RestoreBackup(agent file)`, `residual_side_effects` lists `mise_global_pin` and `running_agent`, warning `defaults_launches_agent`.
- `plan_missing_without_consent`: `defaults_target_missing`.
- `plan_missing_with_consent`: single `TerminalHandoff` with argv `["omarchy-default-editor", "zed"]`, `wrapped: false`, `inverse: None`.
- `plan_never_passes_install_flag`: over every valid draft, no argv contains `--install`.
- `plan_two_installs_rejected`: two missing choices with consent; `validation_failed`.
- `plan_install_while_pending_rejected`: journal fixture with a pending entry; `defaults_handoff_pending`.
- `plan_orders_sets_before_handoff`: browser set plus terminal install; ops in that order.
- `plan_degraded_browser_rejected`: `defaults_desktop_entry_missing`.
- `plan_restore_default_terminal`: draft `foot`; plain set when `foot` is on PATH; handoff plan when it is not.
- `plan_alias_id_rejected`: draft choice `claude-code`; `validation_failed` naming `claude`.
- `plan_never_emits_install_helpers`: over every valid draft, no argv starts with `omarchy-install-`, `omarchy-pkg-`, `pacman`, `yay`, or `mise`.

Apply and verify (through the core executor with the stubs):

- `apply_set_browser_success`: stubs apply; verify passes on all seven checks; journal committed.
- `apply_set_browser_selector_nonzero_notification`: `FX_BROWSER_SET_EXIT=1` but `FX_BROWSER_SET_APPLIES=1`; executor runs inverse; final state equals previous; test documents that a notification failure reverts (accepted behaviour).
- `apply_set_terminal_xdg_disagrees`: preference file updated but `FX_TERMINAL_ID` still `foot.desktop`; verify fails on `xdg_terminal_exec`; inverse runs; journal `rolled_back`.
- `apply_set_agent_detach`: agent stub sleeps 90 s after writing the file; executor proceeds at 60 s; verify passes; process left alive.
- `apply_set_agent_mise_failure`: `FX_AGENT_MISE_FAIL=1`; exit 1 before the file write; verify sees the old value; no inverse needed; error surfaced.
- `apply_handoff_launch_ok_pending`: selector stub execs the launcher stub, which exits 0; journal `pending_handoff`; `ccctl status defaults` lists the transaction under the category's `pending`; the selector log shows no `--install` from the backend.
- `apply_handoff_launcher_fails`: `FX_LAUNCHER_EXIT=1`; shared code `handoff_failed`; journal `rolled_back` with reason `handoff_failed`; earlier sets in the same plan rolled back.
- `apply_handoff_launcher_blocks`: `FX_LAUNCHER_SLEEP=30`; treated as launched after 5 s.
- `reconcile_pass`: after apply, add `zeditor` to the fixture bin and set the editor state file; `verify` returns `pass`; journal `committed`.
- `reconcile_installed_not_set`: add `kitty` binary, leave preference on `foot`; `verify` returns `fail` with `defaults_installed_not_set`; journal `rolled_back`, reason `verification`; a following plain set plan succeeds.
- `reconcile_pending_then_abandon`: nothing changes; `verify` returns `pending`; `ccctl abandon` ends the journal `rolled_back` with reason `user` and clears `status.pending`.
- `reconcile_survives_restart`: run reconcile in a fresh process against the journal directory; same result.
- `reconcile_agent_inline_running`: agent state file set, `mise where` ok, launcher still alive; `pass`.
- `reconcile_changed_unexpectedly`: current becomes a third value; `fail` with `defaults_changed_unexpectedly`; journal `rolled_back`, reason `verification`.
- `rollback_restores_absent_file`: previous editor file absent; apply set; rollback deletes the file; selector prints `nvim`.
- `rollback_agent_keeps_mise_pin`: rollback restores the agent file, leaves `mise/config.toml`, and the history entry carries the plan's `residual_side_effects`.
- `stale_revision_runs_nothing`: revision mismatch; no stub logged any call.
- `concurrent_apply_locked`: second apply while the lock is held returns `locked`.

QML tests (`test_page.qml`, run with the shared QML test runner):

- Four cards render with labels and the current choice from a status fixture.
- Picking a row changes `draft` and does not call `BackendClient`.
- Each of the thirteen card states renders its actions exactly as in section 12.
- The agent card's primary action reads "Set and launch"; the install confirmation for an agent mentions the inline launch.
- Search filters rows by label and id; arrow keys and Enter work; `focusFirst()` lands on the browser picker.
- Unknown value with control characters renders escaped and truncated.
- Pending card resumes `pollStatus` after a simulated overlay close and reopen, and `handlePayload({"module": "defaults", "category": "editor"})` focuses the editor card.

Live checks on a disposable Omarchy session (manual, recorded in `docs/`):

1. Set an installed choice in each category; confirm the notification and, for the agent, the terminal.
2. Install a missing terminal; watch the sudo prompt; confirm the card completes only after the terminal shows Done, and that `xdg-terminal-exec --print-id` matches.
3. Inject the installer defect: make `omarchy-pkg-add` fail; confirm the card reports `installed_not_set` or stays pending rather than showing success.
4. Cancel an install with Ctrl-C; confirm the card offers Retry and the previous default is intact.
5. Install a missing agent; confirm the card completes while the agent is still running inline.
6. Confirm whether `uwsm-app` returns immediately, and record it here to replace the "unverified" note in section 3.5.

## 17. Core services used

All of these exist in the amended contract; none is a request.

- `validate(ctx, draft, status)` with the last status as the third argument.
- `ctx.commands.run(argv, timeout_s, env_extra, stdin, capture_limit)`; `env_extra={"BROWSER": None}` unsets the variable for browser probes and sets.
- `RunCommand(argv, timeout_s, expect_exit, capture_limit, env, stdin, wait_policy)`; `wait_policy: detach` for the agent selector, `exit` for the rest. `backup_paths` on every operation.
- `RestoreBackup(path)` as the inverse when the prior value cannot be re-set through a selector (unknown value, absent file, agent).
- `TerminalHandoff(argv, title, wrapped=false)` for installs; argv token validation at plan time.
- Journal state `pending_handoff` with `ccctl reconcile <txid>` and `ccctl abandon <txid>` (abandon ends `rolled_back`, reason `user`); `ccctl status defaults` lists pending handoff transactions.
- `verify` returning `state: pass | fail | pending` with `level` and `code`.
- `Plan.residual_side_effects` for the agent's mise pin and running agent.
- `ccctl query defaults terminal_windows` for the terminal-window hint.
- `BackendClient.pollStatus`, `stopPolling`, `reconcile`, `abandon`; page `handlePayload(payload)` and `requestNavigate`.

## 18. Contract notes for other modules

- Desktop modes stores `members.defaults` as per-category option ids, excluding the agent, for example `{"browser": "firefox", "terminal": "kitty"}`. Modes submits that to this module as the draft below, with `install` always false, so every category is a plain `set` of an installed choice:

```json
{
  "schemaVersion": 1,
  "changes": {
    "browser": {"choice": "firefox", "install": false},
    "terminal": {"choice": "kitty", "install": false}
  }
}
```

  `choice` carries the option id. `validate` returns `defaults_target_missing` if the choice is not runnable and `validation_failed` if `agent` appears; modes treats both as blocking. Modes must not include a category whose state is `probe_error`, `unknown`, or `drifted`; the same validation codes cover that. The defaults segment is last in a composed plan (amendment I), after themes and bar, which suits this module because nothing here reloads Hyprland or restarts the shell.
- Rollback of a modes transaction uses this module's inverses from section 9.1 through the ordinary rollback walk. When the prior value is unknown, the inverse is a `RestoreBackup`.
- The defaults segment's `expected_revision` is this module's revision from section 7, since `omarchy-remove-browser` and the menu can change these values at any time.

## 19. Recommendations to upstream Omarchy

Not blockers. Listed so the reason for each defensive check in this plan is recorded.

1. `bin/omarchy-install-terminal`: `exit 1` after `Failed to install`, and a regression case in `test/shell.d/default-apps-test.sh`.
2. `omarchy-default-agent --no-launch` or a separate set verb, so a graphical setter and desktop modes can select an agent without opening a terminal.
3. A `--json` query for the four selectors that prints canonical choice, raw value, and whether the choice's command is present. This would remove the need for the raw-state probes in section 6 step 2.
4. `omarchy-launch-floating-terminal-with-presentation` writing a completion marker, or accepting a `--unit` name, so callers can wait on the transient unit instead of polling state.
