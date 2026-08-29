# Adding a module

The hello fixture at `tests/fixtures/modules/hello/` is the smallest complete module. Use it as the reference rather than copying logic into core.

## 1. Describe the module

Create `module.json`. Hello declares id `hello`, page `Page.qml`, backend directory `backend`, draft and status schemas, and its core services. Paths are relative and may not contain `..`. Add production modules by appending their id to `backend/customization_center/modules/__init__.py`. Tests load hello through `CC_EXTRA_MODULE_DIRS`, so it is not registered in production.

## 2. Define documents

Create `schemas/draft-v1.json` and `schemas/status-v1.json`. The hello draft requires:

```json
{"schemaVersion":1,"message":"Hello from the contract fixture"}
```

Keep `MODULE.schema_version` equal to the current draft version. If it rises above 1, retain old schemas and implement one `migrate(ctx, kind, document, from_version)` step for every version.

## 3. Implement the backend

`backend/__init__.py` exports one `MODULE`. Hello implements:

- `capabilities(ctx)`, which reports whether `hello-command` exists.
- `status(ctx)`, which reads `{module_config}/hello.json` and hashes canonical status data with `ctx.revision_of`.
- `validate(ctx, draft, status)`, which returns a normalized draft or a pointer-based issue.
- `plan(ctx, draft, status)`, which returns `ops.WriteFileAtomic` and `ops.RunCommand` operations plus an exclusive file claim.
- `verify(ctx, plan, status_after, results)`, which checks both the saved message and command result.

All imports come from `customization_center.core` or the Python standard library. Planning must not write or run commands.

## 4. Build operations

All operation builders accept `backup_paths: tuple[str, ...] = ()` and `detail: dict | None = None` as keyword parameters. Builders that do not otherwise take a timeout also accept `timeout_s`; its default is 30 seconds, except `ShellIpc` and `TerminalHandoff`, which default to 5 seconds. `RunCommand` already takes `timeout_s` as its third parameter.

```python
ops.WriteFileAtomic(ctx, path, content, mode, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.ReplaceManagedBlock(ctx, path, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.EnsureDirectory(ctx, path, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.ReplaceDirectoryAtomic(ctx, path, staged_dir, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.RunCommand(ctx, argv, timeout_s=30.0, ..., *, backup_paths=(), detail=None)
ops.RestoreBackup(ctx, path, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.RemoveFile(ctx, path, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.ShellIpc(ctx, method, ..., backup_paths=(), ..., *, timeout_s=5.0, detail=None)
ops.HyprctlReload(ctx, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.TimedConfirmation(ctx, seconds, ..., *, backup_paths=(), timeout_s=30.0, detail=None)
ops.TerminalHandoff(ctx, argv, title, ..., *, backup_paths=(), timeout_s=5.0, detail=None)
```

`backup_paths` identifies additional allowlisted files that the executor backs up before the operation. The builder preserves these paths and `detail` in the resulting `Operation`; validation rejects backup paths outside the allowed write roots.

## 5. Implement the page

The fixture page is an `Item` with `moduleId`, `status`, `capabilities`, `draft`, and `busy` properties. A page that needs read-only previews may also declare `property var backendClient: null`; the registry supplies it for `query` calls only, and the page must not reassign it or use it for mutations. It declares `requestPlan()`, `requestApply()`, `requestReset()`, `requestDraftPatch(var patch)`, and `requestNavigate(string moduleId, var payload)`. It implements `focusFirst()` and `handlePayload(payload)`.

Emit `requestDraftPatch` with a JSON merge patch. Never assign to `draft`, instantiate `Process` or `FileView`, or call apply directly from a page.

## 6. Add the sample and tests

Put a valid sample at `tests/fixtures/sample-draft.json` inside the module's test directory, as hello does. The contract suite validates metadata and schemas, runs the protocol without writes, validates every operation and confirmation, checks imports, and exercises executor rollback. Module tests should add parser edge cases and assertions specific to the module.

To stub commands or seed files for the isolated contract home, add `tests/fixtures/contract-stubs.json`, for example `{"hello-command":{"exit_code":0,"stdout":"","stderr":"","byArgs":[{"args":["ping"],"stdout":"ok"}]},"files":{".config/hypr/monitors.lua":"monitors.lua"}}`; command entries provide defaults, and `byArgs` matches the argv after the command name by prefix with the first match winning, while `files` copies fixture-relative sources to paths under the isolated home.

Run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
```
