# Personal menu editor

Status: planned
Module id: `menu`
Master plan: `plans/planned/customization-center-masterplan.md`, Module 3
Omarchy source verified at: `/mnt/SSD_NVME_4TB/GitHub/omarchy-fork` commit `71b0887c`
Runtime checked: Quickshell 0.3.1, bash 5.3, Python 3.14, Node 22 (Node used only to reproduce shell behavior; the module does not depend on it)

## 1. What this module does

The menu module edits one file, `~/.config/omarchy/extensions/omarchy-menu.jsonc`, and asks the running shell to re-read it. It never writes `$OMARCHY_PATH/default/omarchy/omarchy-menu.jsonc`. It shows the shipped menu and the user extension merged the way `shell/plugins/menu/MenuModel.js` merges them, with a badge on every row saying where the row and each of its fields came from.

Decisions, so nobody re-derives them:

1. Ship custom entries first (add, edit, duplicate, rename, move, reorder among custom siblings, delete). This works against the current source.
2. Do not ship field-level overrides of shipped entries until the upstream merge keeps omitted fields. Section 3 shows why and gives the four-line upstream change. Until then, the page marks a shipped id that also appears in the user file as "Shadowed" and offers one operation, "Remove shadow", which reveals the shipped row again.
3. Write the whole file from a model. No partial text rewriting. Comments and formatting in the user file are replaced by a fixed header; entries, unknown fields, `aliases`, explicit `parent`, and wrapper siblings survive.
4. Never run an action or guard to validate it. The backend checks guard syntax with `bash -n` on the exact wrapper the runtime uses.
5. Verification after apply is file plus refresh acknowledgement. The shell exposes no way to read back its loaded model, so the UI never shows "Active" after a save, only "Saved, refresh acknowledged".

## 2. Verified source facts

Everything the module relies on, with where it comes from. "Repro" means I ran the shipped `MenuModel.js` in Node against the shipped default file and the stated input.

| Fact | Source |
|---|---|
| Default menu path is `$OMARCHY_PATH/default/omarchy/omarchy-menu.jsonc`. | `shell/plugins/menu/Menu.qml:50` |
| User extension path is `$HOME/.config/omarchy/extensions/omarchy-menu.jsonc`. It is built from `HOME`, not `XDG_CONFIG_HOME`. | `Menu.qml:51` |
| Both files are watched; a change triggers `reload()`, which re-parses and rebuilds. A user file that fails to load (missing) yields zero user entries and no error. | `Menu.qml:965-982` |
| Comment stripping removes only lines whose first non-whitespace characters are `//`. Inline `//` after a value breaks the parse (0 entries, repro). `/* */` breaks the parse (repro). A `//` inside a string on the same line as other JSON is kept (repro with `https://x.y/`). | `MenuModel.js:1-5` |
| Trailing commas before `}` or `]` are removed by a regex with no string awareness. The action `printf ,}` loads as `printf }` (repro). | `MenuModel.js:4` |
| A parse failure returns an empty list; the shipped menu keeps working and nothing is logged to the user. | `MenuModel.js:46-51`, `Menu.qml:969,978` (`printErrors: false`) |
| A top-level object member named `items` whose value is an object makes the document a wrapper; every other top-level member is then ignored. | `MenuModel.js:54-56` |
| Entries whose value is not a plain object are skipped silently. | `MenuModel.js:60` |
| `JSON.parse` keeps the last of duplicate keys (repro). | JavaScript semantics |
| Entry enumeration order is JavaScript property order: keys that are canonical array indices first in ascending numeric order, then the rest in insertion order. `{"zeta","10","alpha"}` enumerates as `10, zeta, alpha` (repro). | `MenuModel.js:58` |
| `normalizeItem` fills every omitted known field with `""`, `[]`, or the id (for `label`), infers `parent` from the dotted id unless an explicit `parent` is present, sets `parent` to `""` for `root`, and infers `kind` as `action` if `action` is truthy, else `link` if `target` is truthy, else `menu`. Unknown fields are dropped. | `MenuModel.js:13-40` |
| `mergeMenuSources` walks defaults then user entries; the first time an id is seen it is appended to the order; later occurrences copy every key of the normalized user entry over the prior entry. | `MenuModel.js:66-84` |
| A `root` entry is injected at position 0 when neither file declares one. A user-declared `root` is appended at the end of the order like any new id (repro, order 328). | `MenuModel.js:86-89` |
| Routes are lowercased with `_` mapped to `-`; an exact id beats an alias; `""`, `go`, `menu` mean root; app rows are never routable; unknown input is returned as a literal id. | `MenuModel.js:177-191` |
| Visibility: a failed `when` hides the row; a `menu` or `link` without a provider is hidden when no descendant is visible; recursion stops at depth 32. | `MenuModel.js:255-272` |
| `disabled` keeps the row, dims it, adds a check mark, and removes it from search. | `MenuModel.js:277-288`, `docs/menu.md:89-98` |
| Guards are batched into one script and run with `bash -lc` on every rebuild and on every open. Each guard becomes `if { <expr>; } >/dev/null 2>&1; then echo id:tag:1; else echo id:tag:0; fi`. Before that, `$(reader)` for the six commands in `GUARD_READERS` is replaced with `${__omarchy_read_N}`. The prelude defines `omarchy-pkg-present`, `omarchy-pkg-missing`, `omarchy-cmd-present`, `omarchy-cmd-missing` as shell functions. | `MenuModel.js:395-491`, `Menu.qml:996-1019` |
| If the batch exits nonzero, the whole result set is discarded and the previous answers are kept. A syntax error in one guard therefore freezes every guard in the menu. | `Menu.qml:1027-1035` |
| Actions run detached through `bash -lc <action>`. | `Menu.qml:137-141`, `shell/Commons/Util.qml:53-55` |
| Scripted providers are `fonts` (volatile) and `power-profiles`. `apps` is handled natively. Any other provider name loads nothing. | `Menu.qml:269-281`, `Menu.qml:331-341` |
| `omarchy menu refresh` and `omarchy menu ping` run `omarchy-shell shell call omarchy.menu <verb> {}`. `refresh()` calls `reload()` on both FileViews and returns `"ok"` immediately. | `bin/omarchy-menu:29-31`, `Menu.qml:38-44` |
| `omarchy-shell` exits 1 with a stderr message when the shell is not running, not ready, or does not answer within `OMARCHY_SHELL_IPC_TIMEOUT` (default `2s`). Plugin-level failures are printed to stdout with exit 0: `unknown` when the plugin is not loaded or has no such method, `error` when the method threw. | `bin/omarchy-shell:58-81`, `shell/shell.qml:567-579` |
| The menu plugin is `keepLoaded: true`, so `call` reaches it whenever the shell is up and the plugin is enabled. | `shell/plugins/menu/manifest.json:13` |
| `omarchy-refresh-config omarchy/extensions/omarchy-menu.jsonc` replaces the user file with the shipped template and leaves `<file>.bak.<epoch>` beside it. The quattro upgrade always copies the template over the user file, backing up to `<file>.omarchy-upgrade-to-quattro.<suffix>.bak`. | `bin/omarchy-refresh-config:31-40`, `bin/omarchy-upgrade-to-quattro:1621-1642` |
| The shipped template is comments only and documents `when` and `checked` but not `disabled`. | `config/omarchy/extensions/omarchy-menu.jsonc:16-17` |
| Nothing shipped uses explicit `parent`. | `docs/menu.md:25-27`, grep of the default file |
| `bash -n` accepts a wrapper containing `$(rm -rf /tmp/never)` without running it (exit 0, directory untouched) and reports a syntax error with exit 2 and a `bash: line N:` prefix. | Run locally |

One thing I could not verify from the Omarchy tree is whether Quickshell `FileView.reload()` completes before `refresh()` returns. Quickshell documents `FileView` loading as asynchronous unless `blockLoading` is set, and `Menu.qml` does not set it. Treat the acknowledgement as "reload was requested", nothing more. I also could not verify whether the inotify watch survives the atomic rename this module performs. The module calls `refresh` after every write regardless, so it does not matter.

## 3. The override blocker

`docs/menu.md:53-57` and the template at `config/omarchy/extensions/omarchy-menu.jsonc:27-28` both say a user entry that reuses a shipped id replaces only the fields it declares. The runtime does not do that. Repro with the shipped default and this user file:

```jsonc
{
  "about": {"label": "About me"},
}
```

Effective `about` after `mergeMenuSources`: `kind: "menu"`, `action: ""`, `icon: ""`, `order: 9`. The shipped action `omarchy-launch-about` and icon are gone, and the row is now an empty submenu, which `isVisible` hides because it has no children. The user wanted to rename a row and instead removed it.

Cause: `parseMenuJsonc` calls `normalizeItem` on each source before merging (`MenuModel.js:61`), and `normalizeItem` emits every known field (`MenuModel.js:23-39`). `mergeMenuSources` then copies all of them (`MenuModel.js:80`). The upstream test that covers overrides (`test/shell.d/menu-test.sh:52-58`) declares `action` in its user fixture, so it passes without exercising inheritance.

Minimal upstream change, all in `shell/plugins/menu/MenuModel.js`:

1. In `normalizeItem`, keep the raw object on the result as a non-enumerable property, so the existing deep-equality tests still pass. After building the result object, add `Object.defineProperty(result, "raw", { value: value, enumerable: false })`.
2. In `mergeMenuSources`, replace the per-key copy at lines 77-82 with a raw merge followed by one normalization:

```js
var priorRaw = nextItems[entry.id] && nextItems[entry.id].raw ? nextItems[entry.id].raw : null
var mergedRaw = {}
if (priorRaw) for (var k in priorRaw) mergedRaw[k] = priorRaw[k]
var entryRaw = entry.raw || entry
for (var k2 in entryRaw) mergedRaw[k2] = entryRaw[k2]
nextItems[entry.id] = normalizeItem(entry.id, mergedRaw)
```

3. Add a test to `test/shell.d/menu-test.sh` after line 58 that merges `normalizeItem('style.theme', { label: 'Only label' })` over `parsed` and asserts `action === 'omarchy-theme-set'` and `kind === 'action'`.

Provider rows and app rows are built from already normalized objects and never pass through `mergeMenuSources`, so they are unaffected. `swapProviderRows` and `mergeAppRows` do not change.

Until that lands, this module treats every shipped id present in the user file as a whole-entry shadow, says so, and disables field-level Override, Hide, Unhide, and per-field Reset. It does not emulate sparse overrides by copying all shipped fields into the user file. That would pin the shipped action to one Omarchy version and make every later upstream change to that row look like a user choice.

How the module knows which semantics the installed shell has: `capabilities()` hashes `$OMARCHY_PATH/shell/plugins/menu/MenuModel.js` and looks it up in `modules/menu/backend/model_versions.py`, a table of `sha256 -> {overrideSemantics, providers, guardReaders}`. Commit `71b0887c` maps to `full-shadow`. An unknown hash maps to `full-shadow` with the warning `menu_model_unrecognized`, because assuming sparse semantics on an unknown version is the failure mode that deletes actions. When the upstream fix ships, its hash is added with `sparse`.

## 4. Scope

### First release does

- Read both files, hash them, parse them, and show the merged tree with provenance. No writes on open.
- Create, edit, duplicate, rename, move, reorder (among custom siblings), and delete custom entries and subtrees.
- Kinds: submenu, command, link to an existing submenu, provider submenu using `apps`, `fonts`, or `power-profiles`.
- Fields: `icon`, `iconFont`, `label`, `title`, `description`, `action`, `target`, `provider`, `when`, `checked`, `disabled`.
- Preserve on write: `aliases`, explicit `parent`, unknown entry fields, `items` wrapper and its sibling members, entries the editor cannot interpret.
- Syntax-check guards without running them. Warn on executable text by category.
- Show route preview, generated file, and unified diff before apply.
- Apply as `WriteFileAtomic` plus `RunCommand(omarchy-menu refresh)`, with backup, revision check, journal, automatic rollback, and Undo.
- Recover from a missing, unreadable, malformed, duplicate-key, or parser-hazard user file with an explicit "Replace after backup" flow.
- Detect that Omarchy replaced the user file (`omarchy-refresh-config`, quattro upgrade) and offer to restore from the `.bak` it left.

### First release refuses to

- Write anything under `$OMARCHY_PATH`.
- Define new providers or edit provider-generated rows.
- Run an action, guard, or provider script for preview or validation.
- Edit shipped fields sparsely on a `full-shadow` shell. The button exists, disabled, with the reason.
- Reorder shipped rows or place a custom row between shipped siblings. The merge appends new ids after all shipped ids (`MenuModel.js:76`); nothing the file can say changes that.
- Add `aliases` to new entries (`docs/menu.md:46-49`).
- Preserve comments or formatting from the user file.
- Salvage a malformed file. It backs it up byte-for-byte and starts from an empty document if the user asks.
- Apply while the shell is not answering `ping`. Writing the file offline is easy; verifying it and rolling it back is not.
- Evaluate guard truth values or show live search results.

## 5. Module layout

```text
modules/menu/
├── module.json              # id "menu", title "Personal menu", icon, navOrder 3, page "Page.qml",
│                            # backend "customization_center.modules.menu", schemas [draft-v1, document-v1],
│                            # coreServices ["DraftStore", "ApplyBar", "DiffView", "ConfirmDialog", "ErrorBanner"]
├── Page.qml
├── components/
│   ├── MenuTree.qml         # flattened tree list with expansion and keyboard handling
│   ├── EntryInspector.qml   # read-only provenance panel plus the edit form
│   ├── EntryForm.qml        # kind selector and fields
│   ├── GuardField.qml       # text field with automatic-execution notice and syntax result
│   ├── RoutePreview.qml
│   ├── RecoveryPanel.qml    # malformed, hazard, unsupported document
│   └── ProvenanceBadge.qml
├── backend/
│   ├── __init__.py          # exports MODULE
│   ├── module.py            # Module protocol implementation
│   ├── jsonc_menu.py        # safe parser, runtime-parity parser, JS key order
│   ├── model.py             # normalize, merge, effective model, provenance, routes, visibility structure
│   ├── validate.py          # draft validation, ids, hierarchy, kinds, providers
│   ├── guards.py            # bash -n wrapper
│   ├── warnings.py          # command and guard heuristics
│   ├── writer.py            # canonical document
│   └── model_versions.py    # MenuModel.js hash table
├── schemas/
│   ├── menu-document-v1.json
│   └── menu-draft-v1.json
└── tests/
    ├── fixtures/            # see section 15
    ├── parity/run-node-model.js
    ├── test_parser.py
    ├── test_model.py
    ├── test_validate.py
    ├── test_guards.py
    ├── test_warnings.py
    ├── test_writer.py
    ├── test_plan_apply.py
    └── test_recovery.py
```

The backend package imports only `customization_center.core`. It uses `ctx.paths`, `ctx.commands`, `ctx.journal`, `ctx.logger`, `ctx.clock` and never `os.path.expanduser`, `subprocess`, or `open` on its own.

## 6. Paths, revision, capabilities, status

### Paths

- `default_path = ctx.paths.omarchy_path / "default/omarchy/omarchy-menu.jsonc"`. `omarchy_path` comes from `$OMARCHY_PATH`. If unset, `status` fails with `runtime_unavailable` and reason `omarchy_path_unset`.
- `user_path = ctx.paths.home / ".config/omarchy/extensions/omarchy-menu.jsonc"`. This must be `$HOME`-based to match `Menu.qml:51`; core `paths.home` is that value, distinct from `xdg_config_home`.
- `model_path = ctx.paths.omarchy_path / "shell/plugins/menu/MenuModel.js"`, read-only, for the version hash.
- Write allowlist: exactly `user_path`. The plan creates the parent directory if it is missing. If `user_path` or any component of its parent is a symlink, status reports `documentState: "unsupported"` with reason `symlink`, and plan refuses with `unsupported_config`.

### Revision

```text
revision = "menu1:" + sha256(default_bytes)[:16] + ":" + (sha256(user_bytes)[:16] if user file exists else "absent")
```

Both files are part of the revision because an Omarchy update that changes the default file changes what every user entry means. The executor's `expected_revision` check therefore blocks apply after an Omarchy update until the page reloads.

### Capabilities

`capabilities(ctx)` returns:

```text
overrideSemantics:  "full-shadow" | "sparse"        # from model_versions table
modelHash:          string                           # sha256 of MenuModel.js
modelRecognized:    bool
providers:          ["apps", "fonts", "power-profiles"]
guardReaders:       [six names from GUARD_READERS]
shell:              {reachable: bool, detail: string} # ping result, see below
bashAvailable:      bool                             # for guard syntax checks
canWrite:           bool                             # parent dir writable, path not a symlink
reasons:            [{capability, reason}]           # for anything false
```

The ping is `ctx.commands.run(["omarchy-menu", "ping"], timeout_s=5, capture_limit=1024)`. `reachable` is true only if exit is 0 and stdout is exactly `ok`. Stdout `unknown` means the shell is up but the menu plugin is not loaded (disabled or failed); the detail says so. The page calls `ccctl capabilities menu` on open and again when the user presses Apply.

`omarchy-menu` is invoked directly rather than through `omarchy menu`. Both reach `bin/omarchy-menu`; the direct call removes one dispatcher from the argv and from the test stubs.

### Status

`status(ctx)` performs no writes and no subprocess calls. It returns:

```text
revision:          string
default:           SourceInfo
user:              SourceInfo
documentState:     "ok" | "absent" | "empty" | "malformed" | "hazard" | "duplicate-keys" | "unsupported"
document:          Document | null       # parsed user document (section 8), null unless ok/empty/duplicate-keys
effective:         EffectiveModel        # section 9
externalBackups:   [{path, mtime, size}] # <user_path>.bak.* and *.omarchy-upgrade-to-quattro.*.bak, newest first
diagnostics:       [Diagnostic]
```

```text
SourceInfo:
  path:      string
  exists:    bool
  size:      int
  mode:      int | null        # st_mode & 0o777
  sha256:    string | null
  parse:     "ok" | "empty" | "failed" | "hazard"
  runtimeEntryCount: int       # what the shell would load from this file (0 when failed)

Diagnostic:
  code:      string            # error code from section 10
  severity:  "error" | "warning" | "info"
  path:      string            # file path
  jsonPath:  string | null     # e.g. "$.personal.notes.action"
  line:      int | null        # 1-based, in the original file
  column:    int | null
  message:   string
```

A malformed default file sets `documentState` for the page to `unsupported` with `menu_default_unparseable` and a message pointing at `omarchy-update`. The module never compensates by editing user data.

### Queries

Read-only computations the page needs beyond `status` go through `ccctl query menu <name>`:

- `ccctl query menu route --input <text>`: a port of `resolveRoute` (`MenuModel.js:177-191`) over the current effective model. Returns `{input, resolved, via: "id" | "alias" | "literal" | "root", kind, wouldRunAction: bool}`. The page uses it for the route preview field, and `wouldRunAction` is why the preview never offers an "open" button.
- `ccctl query menu search-tokens --id <id>`: the strings the shell's search would match for a row, from `nameSearchText` and the description word split (`MenuModel.js:299-321`). Returns `{label, leafTokens, aliases, descriptionWords}`.

Both run on the same parsed sources as `status` and take no lock.

## 7. Parser

Two parsers run on every read. The safe parser produces the document the editor works with. The parity parser reproduces the shell's transformation exactly and exists only to detect inputs where the two disagree.

### 7.1 Safe parser (`jsonc_menu.parse_safe`)

Input: raw bytes. Output: `(value, diagnostics)` where `value` is an ordered structure with duplicate detection, or `None`.

1. Size check. Reject over 1 MiB with `menu_unparseable` and message `file exceeds 1 MiB`. The shipped default is 51,618 bytes.
2. Decode UTF-8 strictly. On failure, `menu_unparseable` with the byte offset and `invalid UTF-8`. Do not decode with replacement.
3. Strip a leading BOM if present and record `bom: true` (the writer never emits one).
4. Split into lines on `\n`. A line whose content after stripping leading ` \t\r\f\v` and Unicode whitespace starts with `//` is a comment line. Replace it with an empty line so line numbers in later diagnostics still refer to the original file. `\r` before `\n` is kept and stripped by the JSON decoder as whitespace.
5. Remove trailing commas with a character walk. State: `in_string`, `escape`. Outside a string, on `,`, scan forward over whitespace; if the next character is `}` or `]`, drop the comma. Inside strings nothing is touched.
6. If the result is whitespace only, return an empty document (`documentState: "empty"`). This matches `MenuModel.js:44`.
7. `json.loads(text, object_pairs_hook=hook)`. The hook returns an ordered list of pairs and records every duplicate key with its JSON path. `JSONDecodeError` becomes `menu_unparseable` with `lineno`, `colno`, and `msg`.
8. The root must be an object; otherwise `menu_unparseable` with `root is not an object`.

### 7.2 Runtime-parity parser (`jsonc_menu.parse_runtime`)

Reproduces `MenuModel.js:1-5` and `JSON.parse` semantics:

```python
text = re.sub(r"^\s*//[^\n]*(\n|$)", "", raw_text, flags=re.M)
text = re.sub(r",(\s*[}\]])", r"\1", text)
value = json.loads(text)          # last duplicate wins, like JSON.parse
```

Python's `\s` and JavaScript's `\s` agree on ASCII and on the Unicode White_Space set for practical inputs. The one case that matters, a `,` followed by whitespace and a bracket inside a string, is the reason this parser exists.

### 7.3 Parity check

After both parsers succeed, compare the safe value (with duplicates resolved last-wins, to match the runtime) to the runtime value by deep equality. Any difference is `menu_runtime_parser_hazard` with the JSON path of the first differing value and both values. If the safe parser succeeds and the runtime parser fails, or the reverse, that is also a hazard. A document with a hazard can be read and displayed (from the runtime value, since that is what the shell loads) but cannot be the base of a draft until the user fixes the string or uses Replace after backup.

### 7.4 JavaScript key order

`jsonc_menu.js_key_order(keys)` returns the runtime enumeration order: keys matching `^(0|[1-9][0-9]*)$` with value below 4294967295 first, sorted numerically, then the remaining keys in document order. Every place the module walks entries "in runtime order" uses this.

### 7.5 What "supported JSONC" means for the writer

The writer emits strict JSON plus whole-line `//` comments. It never emits trailing commas, so a document written by this module parses identically under `json.loads` with comment lines removed, under the runtime, and under the safe parser.

## 8. Document schema (`menu-document-v1.json`)

The parsed user file, before any normalization. This is what the writer consumes.

```text
Document:
  schemaVersion:    1
  shape:            "direct" | "wrapper"      # wrapper when top-level "items" is an object (MenuModel.js:54)
  bom:              bool
  entries:          [Entry]                   # in document order, not runtime order
  wrapperSiblings:  [{key: string, value: json}]   # only for shape "wrapper"; runtime ignores them; preserved verbatim
  duplicates:       [{jsonPath: string, keptIndex: int}]  # informational after resolution

Entry:
  id:               string                    # the object key, verbatim
  valueKind:        "object" | "other"        # "other" = array, scalar, null; runtime skips these (MenuModel.js:60)
  fields:           OrderedMap<string, json>  # verbatim, only when valueKind is "object"
  raw:              json                      # verbatim value when valueKind is "other"
  declared:         [string]                  # field names present, in document order
  known:            [string]                  # subset of declared that are known fields
  unknown:          [string]                  # subset of declared that are not known fields
  typeErrors:       [{field, expected, actual}]  # known field with the wrong JSON type
```

Known fields and their expected JSON types:

| Field | Type | Runtime treatment |
|---|---|---|
| `icon` | string | glyph |
| `iconFont` | string | font family |
| `label` | string | defaults to id when falsy |
| `title` | string | header when open |
| `description` | string | search subtitle |
| `action` | string | executable, `bash -lc` |
| `target` | string | submenu id to open |
| `provider` | string | must be a known provider name to load anything |
| `aliases` | array of strings, or one string | string becomes a one-element array; falsy array members dropped (`MenuModel.js:7-11`) |
| `parent` | string | overrides dotted inference (`MenuModel.js:16-18`) |
| `when` | string | executable guard |
| `checked` | string | executable guard |
| `disabled` | string | executable guard |

A known field with another type (a number for `label`, an object for `action`) is a `typeError`. The runtime would pass it through `value.label || id`, so a numeric label renders as that number and nothing crashes. The editor shows such an entry read-only with a diagnostic, and validation refuses apply with `menu_field_type` until the user fixes or removes the entry.

## 9. Effective model

A port of `normalizeItem` and `mergeMenuSources` with provenance added. `model.build_effective(default_doc, user_doc, semantics)`.

```text
EffectiveModel:
  semantics:   "full-shadow" | "sparse"
  order:       [string]            # ids in runtime order, root first
  rows:        Map<string, Row>

Row:
  id:          string
  order:       int
  origin:      "shipped" | "custom" | "shadowed" | "injected-root"
  kind:        "menu" | "action" | "link"
  parent:      string              # "" for root
  fields:      NormalizedFields    # what the shell sees
  base:        NormalizedFields | null       # normalized shipped entry, if any
  user:        NormalizedFields | null       # normalized user entry, if any
  userDeclared: [string]           # fields the user file actually wrote
  provenance:  Map<field, "default" | "user" | "cleared" | "inferred">
  children:    [string]            # ids whose parent is this id, in runtime order
  route:       string              # id lowercased with "_" -> "-"; equals id when routable
  routable:    bool                # route == id
  depth:       int                 # depthFor port
  structurallyHidden: bool         # menu/link with no provider and no static descendants
  problems:    [Diagnostic]        # orphan parent, link to non-menu, depth, cycle

NormalizedFields: parent, kind, icon, iconFont, label, title, target, description, action, provider, aliases, when, checked, disabled
```

Pseudocode:

```text
normalize(id, fields):                                   # MenuModel.js:13-40
  aliases = normalize_aliases(fields.get("aliases"))
  parent  = fields["parent"] if "parent" in fields
            else (id.rsplit(".", 1)[0] if "." in id else "root")
  if id == "root": parent = ""
  kind = "action" if truthy(fields.get("action"))
         else "link" if truthy(fields.get("target")) else "menu"
  return {parent, kind,
          icon: fields.get("icon") or "", iconFont: ... or "",
          label: fields.get("label") or id, title: ... or "", target: ... or "",
          description: ... or "", action: ... or "", provider: ... or "",
          aliases, when: ... or "", checked: ... or "", disabled: ... or ""}
  # truthy() follows JavaScript: "", 0, null, false are falsy; everything else truthy.

build_effective(default_doc, user_doc, semantics):
  rows = ordered map
  for (source, doc) in [("default", default_doc), ("user", user_doc)]:
    for entry in doc.entries ordered by js_key_order, last duplicate wins:
      if entry.valueKind != "object": continue                  # MenuModel.js:60
      n = normalize(entry.id, entry.fields)
      if entry.id not in rows:
        rows[entry.id] = Row(id, order=len(rows), origin=("shipped" if source=="default" else "custom"),
                             base=None, user=None, fields={}, provenance={})
      row = rows[entry.id]
      if source == "default":
        row.base = n
        row.fields = copy(n)
        row.provenance = {f: "default" for f in n}
        for f in ("parent","kind","label") if f not derived from a declared field: provenance[f] = "inferred"
      else:
        row.user = n
        row.userDeclared = entry.known
        if row.base is not None: row.origin = "shadowed"
        if semantics == "full-shadow":                          # MenuModel.js:77-82 today
          row.fields = copy(n)                                   # every key overwritten
          for f in n:
            row.provenance[f] = "user" if f in entry.declared or f in ("parent","kind") else "cleared"
        else:                                                    # after the upstream fix
          merged_raw = (row.base_raw or {}) | entry.fields       # user keys win
          row.fields = normalize(entry.id, merged_raw)
          for f in row.fields:
            row.provenance[f] = "user" if f in entry.declared else ("default" if row.base else "inferred")
  if "root" not in rows:                                         # MenuModel.js:86-89
    insert Row("root", origin="injected-root", label="Go", parent="") at index 0
  reassign order = index in rows
  for row in rows: row.children = [id for id in rows if rows[id].parent == row.id]
  for row in rows: compute route, routable, depth (loop with guard 32), structurallyHidden, problems
  return EffectiveModel
```

`cleared` is the provenance that matters for the UI on a `full-shadow` shell. A shadowed row with `provenance.action == "cleared"` lost its shipped action. The inspector lists cleared fields under "Cleared by this shadow" with the shipped value beside each.

`structurallyHidden` is the part of `isVisible` that does not depend on guards: a `menu` or `link` with no provider whose subtree contains no `action` and no provider submenu is hidden by the shell no matter what. The tree shows such rows with a "Hidden: no children" badge. Guard-dependent hiding is not predicted.

## 10. Draft schema (`menu-draft-v1.json`)

```text
Draft:
  schemaVersion:      1
  module:             "menu"
  baseRevision:       string              # status().revision at draft creation
  semantics:          "full-shadow" | "sparse"   # copied from capabilities; plan rejects if it changed
  shape:              "direct" | "wrapper"
  bom:                false
  entries:            [DraftEntry]        # document order to write
  wrapperSiblings:    [{key, value}]      # carried unchanged
  recovery:           null | {mode: "replace-after-backup", backupOfRevision: string}

DraftEntry:
  draftId:            string (uuid4)      # stable across renames
  id:                 string
  originalId:         string | null       # id at draft creation; null for new entries
  origin:             "custom" | "shadowed" | "preserved"
                      # preserved = valueKind "other", type error, or reserved id; carried verbatim, not editable
  kind:               "submenu" | "command" | "link" | "provider"   # ignored for preserved
  fields:             OrderedMap<string, json>   # authored fields; blanks removed by the page before validate
  passthrough:        OrderedMap<string, json>   # unknown fields plus aliases and parent, carried verbatim
  raw:                json | null         # for preserved entries with valueKind "other"
  deleted:            bool                # true = omit on write; kept in draft so the review can list it
```

Rules the page enforces before sending a draft:

- `fields` holds only known editable fields with non-empty string values. The page removes empty strings. The backend also strips them, so a stale page cannot serialize `"icon": ""`.
- `aliases` and `parent` live in `passthrough`. The page shows them read-only under "Advanced" with a "Remove" action for `parent` (explicit normalization) and no add action for either.
- A `shadowed` entry's only editable operation on a `full-shadow` shell is `deleted = true` ("Remove shadow"). On a `sparse` shell it is editable like a custom entry, and `fields` holds only the fields the user wants to override.
- The page never edits `preserved` entries. It can only delete them, and the delete confirmation shows the raw value.

Draft persistence is core `DraftStore`. The page never writes files.

## 11. Validation

`validate(ctx, draft)` is pure. It returns `ValidationResult {ok, errors: [Diagnostic], warnings: [Warning]}`. Errors block plan. Every error has a code, a `draftId`, and a `field` where applicable.

Order of checks, stopping per entry at the first structural failure but continuing across entries:

1. `stale_revision` if `draft.baseRevision != status.revision`. Checked again by the executor, but the page wants it early.
2. `menu_semantics_changed` if `draft.semantics != capabilities.overrideSemantics`. The draft must be rebuilt; a draft made on a `sparse` shell would delete fields on a `full-shadow` one.
3. Id grammar for every non-preserved entry with `id != originalId` (new or renamed):
   - `menu_invalid_id`: must match `^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*$`, at most 128 bytes. Lowercase because routes are lowercased (`MenuModel.js:178`) and an uppercase id can never be summoned. No leading, trailing, or double dots.
   - `menu_reserved_id`: whole id or any segment equal to a canonical array index (`^(0|[1-9][0-9]*)$`), because such keys enumerate first regardless of document order; whole id equal to `root`; whole id equal to `items` in a direct document (would turn the file into a wrapper); whole id equal to any own property name of `Object.prototype` (`constructor`, `hasOwnProperty`, `isPrototypeOf`, `propertyIsEnumerable`, `toLocaleString`, `toString`, `valueOf`, `__proto__`, `__defineGetter__`, `__defineSetter__`, `__lookupGetter__`, `__lookupSetter__`), because `nextItems[id]` in `mergeMenuSources` would hit the prototype.
   - The module preserves existing ids that violate the grammar and shows the warning `menu_legacy_id`. They become errors only when renamed.
4. `menu_duplicate_id`: two non-deleted entries with the same `id`.
5. Kind consistency (`menu_ambiguous_kind`): `command` must have `action` and no `target` or `provider`; `link` must have `target` and no `action` or `provider`; `provider` must have `provider` and no `action` or `target`; `submenu` has none of the three. The runtime would resolve `action` plus `target` in favor of `action` (`MenuModel.js:21`); the editor refuses the ambiguity instead.
6. `menu_unknown_provider`: `provider` not in `capabilities.providers` for a new or changed provider field. An existing unknown provider is a warning.
7. Field content (`menu_field_content`): every string field must not contain NUL or C0 control characters other than tab and newline; `label` and `title` must not contain newline; `id`-referencing fields (`target`, `parent`) must be non-empty strings.
8. Hierarchy, computed on the projected effective model (draft applied over the shipped default under `draft.semantics`):
   - `menu_orphan_parent`: effective parent id does not exist and is not `root`. The page offers "Create parent submenu" which inserts a `submenu` entry before the child.
   - `menu_cycle`: following `parent` returns to the start, or following `target` from a link reaches a link chain back to itself. Explicit `parent` is the only way a dotted id can cycle.
   - `menu_depth_exceeded`: `depth >= 32` (the shell stops walking at 32, `MenuModel.js:202`, `261-262`).
   - `menu_invalid_target`: `target` does not resolve to a row of kind `menu` (validation refuses a link to an action or to another link; the runtime follows one link, and a link to an action would run it on open, `Menu.qml:895-905`).
   - `menu_shipped_position`: a draft entry ordered before a shipped id in the write order. Cannot happen through the page, but a hand-edited draft could try.
9. Guards (`menu_guard_syntax_failed`): section 12, only for entries whose guard field changed relative to the status document, so unchanged guards in a large file are not re-checked on every keystroke. The plan step re-checks all changed guards once more.
10. Preserved entries: still present unchanged, or deleted. A preserved entry with a modified `raw` is `menu_preserved_modified`.

Warnings (never block, but require acknowledgement in review when marked `ack: true`):

| Code | When | ack |
|---|---|---|
| `menu_normalization` | First managed write of a file that contains any comment line other than the module header, any trailing comma, or non-canonical formatting | yes |
| `menu_shadow_present` | Draft still contains a shadowed shipped id (full-shadow shell) | no |
| `menu_legacy_id` | Existing id outside the grammar | no |
| `menu_explicit_parent` | Entry carries explicit `parent` | no |
| `menu_unknown_field` | Entry carries fields the runtime ignores | no |
| `menu_alias_string` | `aliases` is a string; the writer keeps it as a string (the runtime accepts both), no canonicalization | no |
| `menu_model_unrecognized` | MenuModel.js hash unknown | no |
| `menu_slow_guard` | Guard matches the slow pattern set in section 13 | yes |
| `menu_exec_*` | Command and guard categories, section 13 | per category |

## 12. Guard grammar and syntax check

The shell defines a guard only by where it puts the text. A guard is a bash command list `E` that must be valid in

```bash
if { E; } >/dev/null 2>&1; then echo ID:T:1; else echo ID:T:0; fi
```

run under `bash -lc` with a prelude that defines four functions (`omarchy-pkg-present`, `omarchy-pkg-missing`, `omarchy-cmd-present`, `omarchy-cmd-missing`) and after every literal `$(omarchy-channel-current)`, `$(omarchy-default-agent)`, `$(omarchy-default-browser)`, `$(omarchy-default-editor)`, `$(omarchy-default-terminal)`, `$(omarchy-dns)` has been replaced by `${__omarchy_read_N}` (`MenuModel.js:462-467`). There is no further grammar. Consequences the editor states in the help text:

- The expression is not quoted or escaped. An unbalanced `}` or a stray `fi` breaks the batch, and a broken batch freezes every guard in the menu at its previous values (`Menu.qml:1032`). On a fresh shell start that means every `when` row shows and no row is checked.
- The expression runs on every shell rebuild and every menu open, before the user selects anything. Cost and side effects both apply on that schedule.
- Exit status is all that matters. Output is discarded.
- `$(omarchy-default-browser)` and the other readers are evaluated once per batch, not per guard. A guard that expects a fresh value on each evaluation gets the batch value.

Syntax check (`guards.check(expression)`):

1. Reject before calling bash: NUL, C0 controls other than tab and newline, length over 4096 bytes. Code `menu_field_content`.
2. Apply the reader substitution exactly as `substituteGuardReaders` does, so the check sees what the shell will parse.
3. Build the script `if { <E>; } >/dev/null 2>&1; then :; else :; fi\n`.
4. `ctx.commands.run(["bash", "--noprofile", "--norc", "-n"], stdin=script, timeout_s=5, capture_limit=4096, env_extra={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "BASH_ENV": None})`. A `None` value unsets the variable.
5. Exit 0 is a pass. Otherwise `menu_guard_syntax_failed` with the first stderr line, the `bash: line N:` prefix removed, and column unknown (bash does not report one).
6. `-n` parses without executing, including command substitutions and here-documents. Verified locally with `$(rm -rf /tmp/never)`. No environment from the shell session is inherited, so `BASH_ENV` cannot run code.

Actions get the same check with the script `<action>\n` (no wrapper), because `runAction` passes the string to `bash -lc` as-is. A syntax error in an action is `menu_action_syntax_failed`, also blocking. Passing means bash can parse it. It says nothing about what it does.

## 13. Command and guard warnings

`warnings.classify(field, text)` returns zero or more `Warning {code, severity, field, match, message, ack}`. Patterns are Python regexes applied to the raw string. Each warning carries the matched substring so the review can highlight it.

| Code | Severity | ack | Pattern (case-sensitive unless noted) | Message |
|---|---|---|---|---|
| `menu_exec_action` | info | no | any non-empty `action` | Runs as `bash -lc` when selected |
| `menu_exec_guard` | warning | yes for new or changed guards | any non-empty `when`, `checked`, `disabled` | Runs on every shell reload and menu open without selecting the row |
| `menu_exec_elevated` | warning | yes | `(^|[\s;&|(])(sudo|doas|pkexec|su)(\s|$)` ; `\bsystemctl\b(?!\s+--user)` ; `\b(pacman|yay|paru)\s+-[A-Za-z]*[SRU]` ; `\b(chown|chmod)\s+(-[A-Za-z]*R|--recursive)` ; `(^|[\s>])/(etc|usr|boot|var/lib)/` | Needs privileges or writes system paths |
| `menu_exec_destructive` | warning | yes | `\brm\s+(-[A-Za-z]*[rRf]\b|--recursive|--force)` ; `\b(mkfs(\.\w+)?|dd|shred|wipefs|fdisk|sfdisk|parted|cryptsetup)\b` ; `\b(shutdown|reboot|poweroff|halt)\b` ; `systemctl\s+(poweroff|reboot|halt|kexec|suspend|hibernate)` ; `omarchy-system-(factory-reset|reboot|shutdown|logout)` ; `\b(killall|pkill\s+-9|kill\s+-9)\b` ; `>\s*/dev/(sd|nvme|vd|mmcblk)` ; `:\s*\(\)\s*\{` | Can delete data, power off, or kill processes |
| `menu_exec_remote_code` | warning | yes | `\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba)?sh\b` ; `\beval\b` ; `(^|[\s;&|])(source|\.)\s+\S` | Executes downloaded or evaluated text |
| `menu_exec_complex` | info | no | any of `;`, `|`, `&&`, `||`, `&`, `>`, `<`, `$(`, backtick, `<(`, `>(`, `${`, `$[A-Za-z_]`, newline | Contains pipes, redirects, substitutions, or multiple commands |
| `menu_slow_guard` | warning | yes | in a guard only: `\b(sleep|curl|wget|ping|ssh|scp|rsync|git\s+(pull|fetch|clone)|pacman\s+-S[yu]|yay|paru|flatpak\s+(update|install)|docker\s+(pull|run))\b` | Looks slow or network-bound; the menu waits on this on every reload |
| `menu_guard_writes` | warning | yes | in a guard only: `(^|[^<>])>{1,2}\s*[^&\s]` (a redirect that is not `>&2` or `>/dev/null`) ; `\b(rm|mv|cp|touch|mkdir|tee|sed\s+-i)\b` | A guard that changes files runs on every reload |

Rules:

- Heuristics warn. They never block, and nothing in the UI says "safe". They will miss things (`r''m -rf` style obfuscation, a script named innocently) and they will flag things that are fine. That is acceptable for a warning and unacceptable for a gate, which is why they are not a gate. The review shows the exact text in a monospace block with matches highlighted.
- Acknowledgements are keyed by `sha256(draftId + field + text)` and stored in the plan, not the draft. Editing the text produces a new key and clears the acknowledgement.
- The classifier runs on the effective value the shell would run. For a `full-shadow` shadow of a shipped row it runs on the user text only.

## 14. Canonical writer

`writer.render(draft) -> bytes`. Deterministic: the same draft yields the same bytes.

Layout for `shape: "direct"`:

```jsonc
{
  // Omarchy menu extension. Written by Customization Center (firstpick.customization-center).
  // Editing by hand is fine; the next save from the center rewrites the file and drops
  // comments and formatting. Entries and unknown fields are kept. Format: docs/menu.md.
  // Backups: ~/.local/state/omarchy/customization-center/backups/

  // personal
  "personal": {"icon":"","label":"Personal"},
  "personal.notes": {"icon":"󰎞","label":"Notes","action":"omarchy-launch-editor ~/notes"},

  // about
  "about": {"icon":"","label":"About","action":"omarchy-launch-about"}
}
```

Rules:

1. Encoding UTF-8, no BOM, `\n` line endings, final newline, no trailing whitespace.
2. Header is the four fixed comment lines above, inside the braces, followed by one blank line. Header text lives in one constant; the parser recognizes a file as "already canonical" when its comment lines are exactly the header plus group lines, which is how `menu_normalization` is suppressed on later saves.
3. Entries in draft order, deleted entries omitted, one entry per line, two-space indent. Before each entry whose first dotted segment differs from the previous entry's, emit a blank line (except before the first entry) and `  // <segment>`.
4. Entry values are rendered with `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))`, matching the compact style of the shipped default. Key order inside an entry: `icon`, `iconFont`, `label`, `title`, `description`, `aliases`, `parent`, `provider`, `target`, `when`, `checked`, `disabled`, `action`, then unknown fields in their authored order. `action` is last because it is the longest and the field most often read in diffs.
5. The writer omits known fields whose value is an empty string. It writes unknown fields whatever their value.
6. The writer emits `aliases` as it was read (string or array), and `parent` likewise.
7. The writer emits preserved entries with `valueKind: "other"` using `json.dumps(raw, ensure_ascii=False, separators=(",", ":"))` on one line.
8. Entries are separated by `,` and the last entry has none. No trailing commas anywhere.
9. For `shape: "wrapper"`: the header, then `"items": {` with the entries indented four spaces, `}`, then each wrapper sibling as `"key": <json.dumps(value, ensure_ascii=False, indent=2)>` re-indented by two spaces, comma-separated.
10. A draft with no entries writes the header inside `{}`. The runtime parses `{}` as no entries.
11. `json.dumps` escapes control characters in strings (`\n`, `\t`, ``). Non-ASCII, including Nerd Font glyphs in the private use area, comes out literally.
12. File mode: keep the existing file's mode when it is `0o600` or `0o644`; otherwise, and for a new file, `0o600`. Actions sometimes carry URLs with tokens and nothing but the user's shell needs to read the file.

After rendering, the writer re-parses its own output with both parsers and compares to the draft's authored entries. A mismatch is a bug and fails plan with `menu_writer_mismatch`. This is the check that keeps the string-comma hazard from ever being written: a draft containing `printf ,}` fails here, and validation already refused it as `menu_runtime_parser_hazard`.

## 15. Plan, apply, verify, rollback

### Plan

`plan(ctx, draft, status)`:

1. `validate`; any error returns `validation_failed`.
2. Render bytes. Re-parse. Build the projected effective model.
3. Compute the diff: unified diff of current file bytes (or empty) against rendered bytes, plus a semantic change list: added ids, removed ids, changed fields per id (from `userDeclared` before and after), shadows removed, route changes, and any row that becomes `structurallyHidden`.
4. Collect warnings needing acknowledgement, with keys.
5. Return:

```text
Plan:
  expectedRevision:  status.revision
  planHash:          sha256(expectedRevision + sha256(bytes) + json(operations) + sorted ack keys)
  operations:        [Operation]
  summary:           [string]            # one line per operation
  changes:           SemanticChanges
  diff:              string
  warnings:          [Warning]
  verification:      "file-and-refresh-ack"
  nonReversible:     false
```

Operations, in order:

```text
1. EnsureDirectory(path=user_path.parent)
   inverse: core removes it only if it created it
2. WriteFileAtomic(path=user_path, content=bytes, mode=<rule 12 in section 14>)
   inverse: core restores the backup; when the file did not exist the inverse unlinks it
3. RunCommand(argv=["omarchy-menu", "refresh"], timeout_s=10, expect_exit=0, capture_limit=4096)
   inverse: RunCommand(argv=["omarchy-menu", "refresh"], timeout_s=10, expect_exit=0, capture_limit=4096)
```

The refresh inverse is a second refresh, so the shell reloads whatever the file inverse restored. `nonReversible` is false, so no extra confirmation is forced beyond the acknowledgements.

### Apply

Core executor, per contract: lock, re-check `expected_revision` against a fresh `status().revision`, back up `user_path`, run the three operations, call `verify`, journal. The module adds nothing here. The page passes `--expected-revision` from the plan and one `--confirm <key>` per acknowledged warning. The executor refuses with `nonreversible_requires_confirmation` and lists the missing keys in `data.missingKeys` when a warning with `ack: true` has no matching key.

Before calling apply, the page re-runs `ccctl capabilities menu` and refuses to continue with `runtime_unavailable` if `shell.reachable` is false. The plan itself is unchanged by this check.

### Verify

`verify(ctx, plan, status_after)` with operation results attached by the executor:

1. `status_after.user.sha256 == sha256(plan bytes)`; else `menu_verify_bytes`.
2. `status_after.user.parse == "ok"` or `"empty"`, no hazard; else `menu_verify_parse`.
3. Effective model built from `status_after` equals the plan's projected model on `order`, `kind`, `parent`, `fields` for every non-provider row; else `menu_verify_model`.
4. Operation 3 result: exit 0 and stdout stripped equals `ok`. Stdout `unknown` gives `menu_refresh_failed` with detail `plugin not loaded`; `error` gives `menu_refresh_failed` with detail `refresh() threw`; timeout gives `timeout`; nonzero exit gives `menu_refresh_failed` with the first stderr line (`omarchy-shell is not running` or `not responding`).
5. Result: `VerifyResult {ok, level: "file-and-refresh-ack", problems}`.

Any failure makes the executor run inverses in reverse: refresh, restore file, remove directory if created. The journal records both the failure and the rollback result. If the rollback refresh also fails, the UI shows "File restored. The shell did not confirm the reload. Run `omarchy-menu refresh` or restart the shell."

### What would make verification stronger

An IPC method on the menu plugin, for example `inspect()`, returning the loaded revision of each source file, parse status, item order, and normalized static rows without guard results. With it, `verify` would compare the loaded user revision to the written hash and the loaded rows to the projected model, and the page could show "Active". Until then the page shows "Saved. Refresh acknowledged." and never a green verified state.

### Rollback from history

`ccctl rollback <transaction-id>` is core. The module's only contribution is that `status().revision` at rollback time must equal the transaction's after-revision; otherwise the core reports `stale_revision` and the page offers Compare. Backups of malformed files are byte-exact, so rolling back a "Replace after backup" transaction restores the malformed bytes, which is what the user asked for. If the user edited the file by hand after the apply, the core skips the file inverse as `rollback_conflict` because the sha256 no longer matches `written_sha256`; the page then shows the file as changed on disk and offers Compare.

## 16. Page and interaction model

### Layout

Left, the tree. Right, the inspector for the selected row, which becomes the form when editing. Bottom, the shared `ApplyBar`. A banner strip above the tree carries the document state and the `capabilities` summary ("Shell reachable", "Override semantics: full-shadow").

### Tree

A flat `ListView` over the effective `order`, filtered by expansion state. Each row: indent by depth, expander glyph for rows with children, icon, label, badges, and a right-aligned route. Provider submenus show one synthetic child row "Rows loaded by the <name> provider at runtime", not selectable for editing.

Badges: Shipped, Custom, Shadowed, Draft (any entry with unsaved changes), Deleted (draft), Hidden: no children, Preserved, Root. A `Shadowed` row on a `full-shadow` shell also shows "n fields cleared".

Keyboard, with the tree focused:

| Key | Action |
|---|---|
| Up, Down | Move selection |
| Right | Expand, or move to first child if already expanded |
| Left | Collapse, or move to parent if already collapsed |
| Home, End | First, last visible row |
| Enter | Focus the inspector form for a custom row; opens the read-only inspector for others |
| Ctrl+N | Add child under selection (or root when nothing is selected) |
| Ctrl+D | Duplicate custom row |
| F2 | Rename (id) custom row |
| Ctrl+M | Move custom row (opens a parent picker) |
| Alt+Up, Alt+Down | Reorder among custom siblings; no-op with a status message when the neighbor is shipped |
| Delete | Delete custom row or remove shadow, with confirmation |
| Ctrl+F or `/` | Focus the filter field |
| Esc | Clear filter, then return focus to the tree |
| Ctrl+Enter | Review changes (same as ApplyBar) |
| Ctrl+Z, Ctrl+Shift+Z | Draft undo and redo, provided by DraftStore |

Pointer: click selects, double-click edits, drag reorders among custom siblings only. A drag over a shipped sibling or into a shipped submenu's shipped children shows a "Custom rows append after shipped rows" tooltip and refuses the drop. Drag into a submenu at the end of its custom children is allowed and is a Move.

`focusFirst()` focuses the tree with the first row selected, or the recovery panel's primary button when the page is in a recovery state.

`handlePayload(payload)` accepts `{select: "<id>"}` (expand ancestors, select, scroll into view) and `{route: "<text>"}` (run the route query, then select the resolved id). Unknown payload keys are ignored. `CustomizationCenter.open('{"module":"menu","select":"personal"}')` reaches the page through this function.

### Inspector

Read-only for shipped rows: every effective field with its provenance badge, the route, the shipped source line ("default/omarchy/omarchy-menu.jsonc:205"), and for shadowed rows two columns, shipped and user, with cleared fields marked. Buttons: Add child, Remove shadow (shadowed only), Override (disabled with reason on `full-shadow`).

Form for custom rows: kind selector (Submenu, Command, Link, Provider submenu), id (local segment plus read-only parent prefix), icon with a glyph picker limited to entering a character, iconFont, label, title, description, then per kind: action, target (picker of effective `menu` rows), provider (dropdown from capabilities). Guards `when`, `checked`, `disabled` under a "Conditions" group with the automatic-execution notice above the group and the syntax result below each field. "Advanced" disclosure shows `aliases`, `parent`, and unknown fields read-only, with "Remove explicit parent".

Validation runs through `BackendClient.validate` debounced at 300 ms after the last edit and on field blur. Errors attach to fields. Warnings show as a count in the ApplyBar and in full in review.

### States

| State | Entry | Shown | Exit |
|---|---|---|---|
| Loading | Page opened or Reload pressed | Spinner | status and capabilities returned |
| Ready | status ok or empty, no draft changes | Tree, banner | any edit |
| Editing | Draft differs from status | Tree with Draft badges, ApplyBar enabled when valid | Review, Reset, or Reload |
| Invalid | validate returned errors | Errors on fields, Review disabled | errors fixed |
| Reviewing | Plan returned | Shared review dialog with change list, diff, warnings with ack checkboxes | Apply or Back |
| Applying | Apply in flight | Progress with the three operations | result |
| Saved | Apply ok, verify ok | Banner "Saved. Refresh acknowledged." with Undo | timeout of banner or next edit |
| Rolled back | Apply failed, inverses ok | Banner with the failure code and "Previous file restored" | dismiss |
| Rollback failed | Inverses failed | Blocking panel with paths and manual steps | Reload after user action |
| Stale | status revision changed since draft creation (detected on validate, plan, or focus regain) | Banner "Changed on disk" with Reload, Compare, Keep editing; if `externalBackups` gained a newer file, add "Restore from Omarchy backup" | user choice |
| Recovery: malformed | documentState malformed or hazard | RecoveryPanel: path, diagnostic with line and column, "the shell currently loads no user entries from this file" (or "loads it with an altered string" for hazard), buttons Show raw, Copy diagnostic, Open externally, Replace after backup | Replace, or file fixed externally and Reload |
| Recovery: duplicates | documentState duplicate-keys | Panel listing each duplicate with the kept occurrence, button "Keep last occurrences and continue" which creates a draft from the resolved document | draft created |
| Unsupported | symlink path, default file unparseable, `OMARCHY_PATH` unset | Panel with reason; tree still shown when the effective model could be built | external fix and Reload |
| Runtime unavailable | capabilities.shell.reachable false at apply time | Banner with the ping detail and Retry; editing continues | ping succeeds |

"Replace after backup" creates a draft with `recovery.mode = "replace-after-backup"` and no entries. The review for such a draft shows the full raw file as "removed" and requires the user to type `replace` in the confirmation. The apply is the same three operations; the backup the executor takes is the malformed file, byte-exact.

## 17. Test matrix

Fixtures live in `modules/menu/tests/fixtures/`. `default-71b0887c.jsonc` is a copy of the shipped default at the verified commit; `template.jsonc` is the shipped extension template. Tests run with isolated `HOME`, `OMARCHY_PATH`, and `XDG_STATE_HOME`, and a stub `omarchy-menu` on `PATH` controlled by `MENU_STUB=ok|unknown|error|not-running|not-responding|slow` that appends its argv to `$MENU_STUB_LOG`.

### Parser (`test_parser.py`)

| Case | Fixture | Expect |
|---|---|---|
| Template parses as empty | `template.jsonc` | documentState empty, 0 entries |
| Shipped default parses | `default-71b0887c.jsonc` | 328 entries, parity ok, no diagnostics |
| Indented and blank-line comments | `user-comments-indented.jsonc` | entries intact |
| Inline comment fails both parsers | `user-inline-comment.jsonc` | `menu_unparseable`, line and column point at the comment |
| Block comment fails | `user-block-comment.jsonc` | `menu_unparseable` |
| Trailing commas everywhere | `user-trailing-commas.jsonc` | parses; parity ok |
| Comma before bracket inside string | `user-comma-in-string.jsonc` (`"action": "printf ,}"`) | safe parse ok, parity hazard `menu_runtime_parser_hazard` at `$.x.action` |
| URL in string | `user-url.jsonc` | `//` retained |
| Duplicate keys at two levels | `user-duplicate-keys.jsonc` | documentState duplicate-keys, both paths listed, resolved document keeps last |
| Integer-like keys | `user-integer-keys.jsonc` | runtime order `10, zeta, alpha`; document order preserved separately |
| Wrapper shape with siblings | `user-items-wrapper.jsonc` | shape wrapper, siblings preserved, only `items` members are entries |
| Non-object entries | `user-non-object-entry.jsonc` | entries with valueKind other, preserved, diagnostic info |
| Wrong field types | `user-field-types.jsonc` | typeErrors listed, `menu_field_type` on validate |
| Invalid UTF-8 | `user-invalid-utf8.bin` | `menu_unparseable` with byte offset |
| Over 1 MiB | generated | `menu_unparseable` |
| BOM | `user-bom.jsonc` | parses, `bom: true`, writer output has none |

### Effective model (`test_model.py`, parity via `parity/run-node-model.js` when `node` is present, otherwise the checked-in `expected/*.json` produced by that runner)

| Case | Fixture | Expect |
|---|---|---|
| Default only | `default-71b0887c.jsonc` | order and every normalized field equal to Node output |
| Custom append | `user-basic-custom.jsonc` | `personal`, `personal.notes` at the end, origin custom |
| Label-only shadow, full-shadow | `user-label-only-override.jsonc` | `about.kind == "menu"`, `action == ""`, provenance.action cleared, origin shadowed, order 9 |
| Label-only shadow, sparse | same, semantics sparse | `about.action == "omarchy-launch-about"`, provenance.action default |
| User root | `user-root-override.jsonc` | no injected root, root order at end, label overridden |
| Explicit parent | `user-explicit-parent.jsonc` | parent honored, `menu_explicit_parent` warning |
| Route normalization | `user-uppercase-id.jsonc` | `routable false`, legacy id warning |
| Structural hiding | `user-empty-submenu.jsonc` | `structurallyHidden true` for the empty submenu |
| Depth | `user-depth-32.jsonc`, `user-depth-33.jsonc` | 32 ok, 33 `menu_depth_exceeded` |

### Validation (`test_validate.py`)

| Case | Expect |
|---|---|
| New id with uppercase, dot edge, double dot, 129 bytes | `menu_invalid_id` each |
| New id `10`, `a.0.b`, `root`, `items` (direct), `__proto__`, `constructor` | `menu_reserved_id` each |
| Same ids in wrapper shape with `items` | allowed |
| action plus target, action plus provider, target plus provider | `menu_ambiguous_kind` |
| provider `foo` new, provider `foo` existing | error, warning |
| Orphan `x.y` with no `x` | `menu_orphan_parent`, Create parent fix produces a valid draft |
| Explicit parent cycle `a` -> `b` -> `a` | `menu_cycle` |
| Link to action, link to link | `menu_invalid_target` |
| Draft ordered before shipped id | `menu_shipped_position` |
| Semantics mismatch | `menu_semantics_changed` |
| Preserved entry edited | `menu_preserved_modified` |

### Guards (`test_guards.py`)

| Case | Expect |
|---|---|
| `omarchy-pkg-present foo` | pass |
| `[[ "$(omarchy-default-browser)" == "zen" ]]` | pass; substituted text contains `${__omarchy_read_2}` |
| `[[ "$(x)" == ` | fail, message from bash without prefix |
| `true; }; touch $SENTINEL; {` | fail (the wrapper closes early); sentinel absent after the check |
| `$(touch $SENTINEL)` | pass; sentinel absent after the check |
| 5000-byte expression | `menu_field_content` before bash is called (stub log empty) |
| bash missing from PATH | `runtime_unavailable` with reason `bash_missing`, apply blocked |

### Warnings (`test_warnings.py`)

One case per pattern row in section 13, positive and a near-miss negative (`sudoku` does not match elevated; `--user` after `systemctl` does not match; `>/dev/null` in a guard does not match `menu_guard_writes`). Acknowledgement key changes when text changes.

### Writer (`test_writer.py`)

| Case | Expect |
|---|---|
| Render basic custom draft | equals `expected/basic-custom.jsonc` byte for byte |
| Render twice | identical bytes |
| Round trip every fixture that parses | render, re-parse, entries and passthrough equal; parity ok |
| Wrapper shape | siblings after `items`, re-parse gives the same siblings |
| Unknown fields and string aliases | present verbatim |
| Empty draft | header inside `{}`; runtime parses to 0 entries |
| Control characters | escaped; glyphs literal |
| Canonical detection | output of the writer does not raise `menu_normalization` on the next plan |

### Plan, apply, verify (`test_plan_apply.py`)

| Case | Stub | Expect |
|---|---|---|
| Status and plan write nothing | any | no file under HOME changes mtime |
| First apply creates the file | ok | file exists, mode 0600, journal entry, stub log `["ping"]` then `["refresh"]` |
| Existing file mode 0644 kept | ok | mode unchanged |
| Stale user revision | ok | `stale_revision`, no write |
| Stale default revision | ok | `stale_revision`, no write |
| Lock held | ok | `locked` |
| Refresh stdout `unknown` | unknown | rollback, file restored, journal has both, error `menu_refresh_failed` |
| Refresh stdout `error` | error | same |
| Shell not running | not-running | `runtime_unavailable` at capabilities; apply refused before write |
| Refresh timeout | slow | `timeout`, rollback, second refresh attempted |
| Rollback refresh also fails | ok then not-running | `rollback_failed` with the manual instruction |
| New file rollback | unknown | file absent after rollback |
| Symlinked user file | ok | `unsupported_config`, no write |
| Ack missing for destructive action | ok | `nonreversible_requires_confirmation`, no write |
| Replace after backup | ok | backup bytes equal malformed input; rollback restores them |

### Live checks (disposable VM, manual)

1. Add `personal` and `personal.notes`, apply, open the menu with `omarchy menu summon personal`, see both rows without restarting the shell.
2. Rename `personal` to `mine`, apply, confirm `omarchy menu summon personal` opens nothing useful and `mine` opens the submenu.
3. Add a provider submenu for `fonts`, apply, confirm font rows appear and are not editable in the page.
4. Corrupt the user file by hand, reopen the page, see the recovery panel, Replace after backup, Undo, confirm the corrupt bytes are back.
5. Run `omarchy-refresh-config omarchy/extensions/omarchy-menu.jsonc` while the page has a draft, confirm the Stale banner offers the `.bak` restore.
6. Disable the menu plugin, press Apply, confirm the page reports the ping detail and does not write.
7. After the upstream sparse merge lands and its hash is in the table: override only the label of `about`, apply, confirm the row still launches `omarchy-launch-about`.

## 18. Core services used

All of these exist in core; the module adds no core code.

- `paths.home` for the user file (`$HOME`, not `xdg_config_home`) and `paths.omarchy_path` for the shipped files.
- `WriteFileAtomic` with absent-target backups. The first save on an installation where the template was removed is a create, and the inverse unlinks.
- `EnsureDirectory` and `RunCommand` with tuple or single inverses.
- Operation results (`exitCode`, `stdout`, `stderr` truncated to `capture_limit`, `timedOut`) passed to `verify`, used to check the refresh stdout for `ok`.
- `ccctl apply --confirm <key>` and the `nonreversible_requires_confirmation` refusal with `data.missingKeys`.
- `core/jsonc.parse(bytes) -> (value, diagnostics)` with ordered pairs, duplicate-key paths, and a line map, as the safe parser of section 7.1. The runtime-parity parser and JS key order stay in `modules/menu/backend/jsonc_menu.py` because they encode `MenuModel.js`, not JSONC.
- `ctx.commands.run(argv, timeout_s, env_extra, stdin, capture_limit)` for the `bash -n` check and the `omarchy-menu` calls.
- `DraftStore` undo and redo, bound to Ctrl+Z and Ctrl+Shift+Z in the tree.
- `ccctl query menu <name>` for the route and search-token queries.
- Journal states and reasons as defined by core (`applying`, `committed`, `rolling_back`, `rolled_back`, `rollback_failed`; reasons `user`, `timeout`, `recovery`, `verification`, `operation`). The menu plan has no gate and no handoff, so `awaiting_confirmation` and `pending_handoff` never occur for it.

Integration is `modules/menu/module.json` plus one line in `backend/customization_center/modules/__init__.py`.

## 19. Contract notes against the master plan

- Master plan Module 3 "Existing default IDs can be overridden field by field" is not true on the verified source. This plan gates that feature on the upstream change in section 3 and on the `model_versions` table.
- Master plan "Verify that the route appears in the effective menu model where a read API is available" has no read API to use. Verification level is `file-and-refresh-ack` until an `inspect()` IPC exists.
- The adapter stub and the argv are both `omarchy-menu` (`["omarchy-menu", "refresh"]`, `["omarchy-menu", "ping"]`). `omarchy menu refresh` on the command line reaches the same script.
- Master plan "Reset override action for shipped entries" is delivered as "Remove shadow" (whole entry) on `full-shadow` shells and as per-field reset on `sparse` shells.
- Master plan "Search preview" is not in the first release. The inspector shows the searchable tokens (label, last id segment with `.`, `_`, `-` as spaces, aliases, description words) so the user can see what search will match, but no ranking is simulated.
- Desktop modes does not include a menu member in the first release. It could later. The menu plan is three operations with inverses and no gate, and the composed member order already places `menu` after `bar` and before `keybindings`.

## 20. Open decisions

1. Whether to submit the section 3 upstream change now. Recommendation: yes, with the test. It is four lines and the docs already promise the behavior.
2. Whether to keep `menu_slow_guard` acknowledgements mandatory. They will annoy users who write `curl` guards on purpose. Recommendation: keep mandatory for the first release, revisit after seeing real files.
3. Whether to write `0o600` for new files or match the template's `0o644`. Recommendation: `0o600`; nothing else reads the file.
4. Whether the group comment lines (`// personal`) are worth the diff noise when a user reorders entries. Recommendation: keep; the shipped default uses the same convention and it makes hand editing easier.
