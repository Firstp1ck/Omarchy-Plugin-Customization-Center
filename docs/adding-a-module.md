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

## 4. Implement the page

The fixture page is an `Item` with `moduleId`, `status`, `capabilities`, `draft`, and `busy` properties. A page that needs read-only previews may also declare `property var backendClient: null`; the registry supplies it for `query` calls only, and the page must not reassign it or use it for mutations. It declares `requestPlan()`, `requestApply()`, `requestReset()`, `requestDraftPatch(var patch)`, and `requestNavigate(string moduleId, var payload)`. It implements `focusFirst()` and `handlePayload(payload)`.

Emit `requestDraftPatch` with a JSON merge patch. Never assign to `draft`, instantiate `Process` or `FileView`, or call apply directly from a page.

## 5. Add the sample and tests

Put a valid sample at `tests/fixtures/sample-draft.json` inside the module's test directory, as hello does. The contract suite validates metadata and schemas, runs the protocol without writes, validates every operation and confirmation, checks imports, and exercises executor rollback. Module tests should add parser edge cases and assertions specific to the module.

Run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
```
