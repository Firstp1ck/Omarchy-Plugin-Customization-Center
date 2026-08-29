# PLUGINS-IMPLEMENT-01 handoff

## Identity and status

- Workstream: `PLUGINS-IMPLEMENT-01`
- Role: isolated-worktree writer
- Base commit: `6dc6cdcb8b97b6dcad186e9d81a5752dde974f53`
- Result commit: this handoff is part of the result commit; its SHA is reported in the worker acceptance report because a commit cannot embed its own object id without changing that id.
- Status: implemented and locally validated within the assigned boundary; ready for parent cherry-pick and registry integration.

## Implemented

- Runtime-authoritative plugin discovery through public `core.catalog`, with static catalog enrichment only and static-only rows retained as non-actionable diagnostics.
- Provenance classification for Omarchy-shipped, installed, clone, git, directory, and symlink sources; credential/secret redaction for displayed remotes; exact unsandboxed-code wording without trust or health claims.
- Read-only settings metadata through public `core.settings_schema`, including adapters, extension metadata, invalid-schema diagnostics, and a permanently read-only non-bar write capability because public `patchPluginEntry` is absent.
- Non-bar enable/disable through exact `ShellIpc(setPluginEnabled, [id, "true"|"false"])` operations and inverses. No module code writes `shell.json`; bar and bar-widget rows are never mutated.
- Wrapped `TerminalHandoff` operations for Add, Update, Remove, Clone, and Clone-and-edit. No lifecycle argv contains `--yes` or `--enable`. Every handoff operation id and acknowledgement warning code is a confirmation key.
- Reconciliation verification for add/update/remove/clone, with lifecycle success recorded at `limited` verification level (`terminal-command-and-catalog-only`) rather than overstating health or update contents.
- Exact bar deep-link payloads: `{selectBar: id}`, `{select: {section, index}}`, and `{addWidget: id}`.
- Pending-handoff status, dismiss/abandon signal, stale/runtime/catalog-degraded wording, bar fallback display, provenance tabs, read-only placement/settings/diagnostics, searchable filters, keyboard row navigation, Shift+F10/Menu action surface, and read-only schema rendering.
- Draft/status schemas, contract stubs, unit/integration/adapter/handoff/QML tests, and CLI/module smoke.

## Changed files

- `modules/plugins/module.json`
- `modules/plugins/Page.qml`
- `modules/plugins/backend/__init__.py`
- `modules/plugins/backend/catalog.py`
- `modules/plugins/backend/kinds.py`
- `modules/plugins/backend/messages.py`
- `modules/plugins/backend/module.py`
- `modules/plugins/components/DetailDiagnostics.qml`
- `modules/plugins/components/DetailOverview.qml`
- `modules/plugins/components/DetailPlacement.qml`
- `modules/plugins/components/DetailSettings.qml`
- `modules/plugins/components/HandoffStrip.qml`
- `modules/plugins/components/OriginChip.qml`
- `modules/plugins/components/PluginRow.qml`
- `modules/plugins/components/StateChip.qml`
- `modules/plugins/components/TrustBanner.qml`
- `modules/plugins/schemas/draft-v1.json`
- `modules/plugins/schemas/status-v1.json`
- `modules/plugins/tests/conftest.py`
- `modules/plugins/tests/fixtures/contract-stubs.json`
- `modules/plugins/tests/fixtures/sample-draft.json`
- `modules/plugins/tests/qml/tst_page.qml`
- `modules/plugins/tests/run_cli_smoke.sh`
- `modules/plugins/tests/test_catalog.py`
- `modules/plugins/tests/test_handoff.py`
- `modules/plugins/tests/test_integration.py`
- `modules/plugins/tests/test_kinds.py`
- `modules/plugins/tests/test_plan.py`
- `modules/plugins/tests/test_qml_page.py`
- `modules/plugins/tests/test_validate.py`
- `modules/plugins/tests/test_verify.py`
- `reports/handoffs/plugins-implement-01.md`

## Validation

All successful Python checks used `PYTHONDONTWRITEBYTECODE=1`; pytest checks disabled the cache provider.

| Command | Exit | Result |
|---|---:|---|
| `PYTHONPATH="$PWD:$PWD/backend" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q modules/plugins/tests` | 0 | 14 plugin tests passed, including exact handoff launcher argv and reconciliation. |
| Runtime-injected registration followed by `pytest -q tests/contract/test_module_contract.py tests/contract/test_qml_pages.py -k plugins` | 0 | 4 canonical contract-equivalent plugin cases passed without editing the registry. |
| `PYTHONPATH="$PWD:$PWD/backend" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider --import-mode=importlib' pytest -q` | 0 | Full repository pytest passed; one existing environment-dependent test skipped. |
| Split relevant pytest: core catalog/settings/shell IPC/operations/executor, bar tests, plugin tests, and shared QML tests | 0 | All relevant groups passed; shared QML retained one existing skip. |
| `PYTHONDONTWRITEBYTECODE=1 modules/plugins/tests/run_cli_smoke.sh` | 0 | Printed `plugins CLI/module smoke: ok`. |
| `python -m json.tool` over module metadata, schemas, and JSON fixtures | 0 | All JSON parsed. |
| `qmllint -I tests/qml/imports -I /mnt/SSD_NVME_4TB/GitHub/omarchy-fork/shell modules/plugins/Page.qml modules/plugins/components/*.qml` | 0 | No output. |
| `git diff --check` | 0 | No whitespace errors. |
| `find . -type d \( -name __pycache__ -o -name .pytest_cache \) -print` with empty-output assertion | 0 | No bytecode or pytest caches remained. |

Observed and resolved during validation:

- Initial plugin pytest exposed a QML parser error, fixture import issue, and a selection binding loop; all were corrected and the suite then passed.
- A combined multi-directory pytest command exited 2 due duplicate top-level test module basenames under pytest's default import mode. The full suite and split relevant suites passed using repository-root `PYTHONPATH`; full-suite validation also passed with `--import-mode=importlib`.
- A plain full pytest command without repository-root `PYTHONPATH` exited 2 while collecting an existing `tests.qml` namespace import. The documented successful full command above supplies the repository paths explicitly.

## Omissions and assumptions

- No live Omarchy shell, disposable VM, visual screenshot comparison, shell restart persistence check, or real lifecycle command was run in this worktree. Stubbed adapters and executor-backed handoff reconciliation cover the local contract.
- Parent registration is intentionally omitted because `backend/customization_center/modules/__init__.py` is outside this workstream's write boundary. Contract stubs are ready for immediate registration.
- `patchPluginEntry` is not in the public core shell IPC allowlist. The module reports it unavailable and keeps non-bar settings read-only; it does not attempt a mutating capability probe or invent an API.
- Lifecycle verification intentionally proves terminal completion plus catalog reconciliation, not plugin health or byte-level update contents.

## Risks and integration notes

1. **Parent integration blocker:** current `modules/bar/Page.qml` handles `select` and `selectBar` but not the planned `{addWidget: id}` payload. Per supervisor decision, plugins keeps the required payload. The integration owner must add generic `addWidget` handling in bar, ensure selection alone still does not apply, and add cross-module QML coverage.
2. Add `"plugins"` after `"bar"` in `backend/customization_center/modules/__init__.py`, then run the canonical contract suite without runtime injection.
3. The page emits `requestRefresh` and `requestAbandon`; parent integration should confirm AppShell connects these to status refresh and `ccctl abandon`, matching neighboring handoff modules.
4. Live lifecycle tests remain necessary because Omarchy command prompts, terminal presentation, inotify timing, and restart persistence cannot be proven by local stubs.
5. The plugin list uses a bounded `Flickable`; live visual review should still exercise 37+ rows, both theme branches, keyboard focus, and scale changes.

## Recommended parent sequence

1. Cherry-pick the reported result commit.
2. Register `plugins` immediately after `bar`.
3. Add the generic bar `{addWidget}` deep-link handler and cross-module QML test.
4. Run canonical contract, full pytest, qmllint, and live Add/Update/Remove/Clone plus non-bar enable/disable checks.
