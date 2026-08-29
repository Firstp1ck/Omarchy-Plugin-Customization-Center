# DEFAULTS-HARDEN-01 handoff

Status: implemented and validated
Run identity: isolated-worktree writer for `DEFAULTS-HARDEN-01`
Base revision: `73f48e317a011861492080b1b81a49db65800ed6`
Result commit: the single `DEFAULTS-HARDEN-01` commit containing this handoff; its SHA is reported in the worker acceptance report because a commit cannot embed its own final hash.

## Implemented

- Classified a missing `xdg-terminal-exec` as `probe_error` while preserving `none_resolvable` for an installed resolver that returns no choice.
- Corrected the editor fallback check so an absent editor state file is the effective `nvim` default.
- Projected pending handoffs and actionable transaction outcomes from the generic journal into category status: `installed_not_set`, `verify_failed`, and `rollback_failed`, including verification checks, retained paths, and recovery commands.
- Added all planned category presentation states and keyboard-focusable pointer actions for Retry, Recheck, Reload, Set/Repair, Apply, Clear, Restore default, Stop tracking, and details.
- Added keyboard-focusable per-choice details, exact selector argv, package/integration/installer facts, unknown-value source text, sanitization/truncation, and clipboard copy.
- Made the Stop tracking warning explicit that abandon rolls back completed defaults but cannot cancel or close the external terminal.
- Added page-owned pending polling at 5 seconds for the first 2 minutes, 20 seconds through 15 minutes, then stopped automatic polling. Recheck, focus/reopen status, and manual status refresh remain available.
- Added a generic page opt-out (`handlesPendingHandoffs`) so `ModuleRegistry` retains its 2-second fallback for ordinary pages but does not duplicate polling for pages that own a bounded schedule.
- Added the generic automatic-rollback reason mapping so a failed terminal launch records `handoff_failed`, while confirmation expiry remains `timeout` and other operation failures remain `operation`.
- Added real executor coverage for mixed set plus handoff, safe abandon, early handoff cancellation, installed-selector verification rollback, terminal false-success reconciliation, successful reconciliation evidence, and inverse rollback failure.
- Expanded QML tests across every planned card state, state-specific controls, polling boundaries, draft-only selection, focusable details, and unknown-value behavior.

## Saved review disposition

1. **Reconcile discards verification error — resolved by the integrated CORE-ROLLBACK-01 base and verified here.** The defaults executor test confirms `defaults_installed_not_set`, reason `verification`, and evidence survive reconciliation and appear in module status.
2. **Abandon leaves earlier sets changed — resolved by the integrated CORE-ROLLBACK-01 base and verified here.** Mixed browser-set plus terminal-handoff abandon restores the browser and records the handoff as skipped/non-reversible.
3. **Missing `xdg-terminal-exec` becomes `none_resolvable` — resolved in defaults status.** Dedicated tests distinguish executable absence from installed-resolver/no-choice.
4. **Card states and recovery actions absent — resolved.** All planned states and actions are rendered and covered by module QML tests.
5. **Permanent duplicate polling — resolved.** Defaults owns the bounded schedule and opts out of the generic fallback; shared QML tests preserve fallback behavior for non-opt-in pages.
6. **Critical executor/QML matrix absent — resolved.** New real executor and QML suites cover the requested paths.

No saved review finding remains open.

## Changed files

- `backend/customization_center/core/executor.py`
- `core/ModuleRegistry.qml`
- `modules/defaults/Page.qml`
- `modules/defaults/backend/status.py`
- `modules/defaults/components/CategoryCard.qml`
- `modules/defaults/components/ChoiceDetails.qml`
- `modules/defaults/components/ChoicePicker.qml`
- `modules/defaults/components/CurrentValue.qml`
- `modules/defaults/components/PendingHandoff.qml`
- `modules/defaults/schemas/status-v1.json`
- `modules/defaults/tests/qml/tst_page.qml`
- `modules/defaults/tests/test_apply_integration.py`
- `modules/defaults/tests/test_qml_page.py`
- `modules/defaults/tests/test_status.py`
- `tests/core/test_executor.py`
- `tests/qml/tst_core.qml`
- `reports/handoffs/defaults-harden-01.md`

## Validation

Final commands were run from the repository root.

| Command | Exit | Result |
|---|---:|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider modules/defaults/tests` | 0 | 20 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/contract -k defaults` | 0 | 3 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/qml` | 0 | shared QML suite passed with one expected skip |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider modules/defaults/tests/test_qml_page.py` | 0 | module QML suite passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider` | 0 | full suite passed with two expected skips |
| `qmllint -I /mnt/SSD_NVME_4TB/GitHub/omarchy-fork/shell -I tests/qml/imports -I . modules/defaults/Page.qml modules/defaults/components/*.qml` | 0 | no diagnostics |
| `PYTHONDONTWRITEBYTECODE=1 modules/defaults/tests/run_cli_smoke.sh` | 0 | status, validate, and plan returned successful JSON envelopes |
| `python3 -m json.tool modules/defaults/schemas/status-v1.json` | 0 | schema parsed |
| `git diff --check` | 0 | clean |
| `find . -type d \( -name __pycache__ -o -name .pytest_cache \) -print` | 0 | no cache directories found |
| `git diff --cached --quiet` | 0 | no staged files before commit preparation |

During implementation, targeted executor and QML runs initially exited 1 while test fixtures and QML test doubles were corrected. The failures were an invalid registry-view reference, one pre-correction journal-reason assertion, unavailable test-only Quickshell clipboard import, a reduced ConfirmDialog test API, and test clock/button semantics. Production changes were revalidated by every final command above.

## Omissions

- No live Omarchy desktop, real package installation, sudo prompt, or external terminal session was exercised. Those are manual/disposable-session checks from the module plan.
- No visual screenshot comparison, live light/dark theme switch, or physical clipboard inspection was performed. QML loaded against Omarchy Commons/Ui imports, `qmllint` passed, and controls/state behavior ran offscreen.
- The polling boundary was tested deterministically rather than waiting 15 real minutes.

## Deviations

- The original write boundary was expanded with supervisor approval to the smallest generic shared changes:
  - `core/ModuleRegistry.qml` and `tests/qml/tst_core.qml` for page-owned pending polling with unchanged fallback behavior.
  - `backend/customization_center/core/executor.py` and `tests/core/test_executor.py` for generic `handoff_failed` rollback-reason persistence.
- No defaults-specific logic was added to either shared core file.
- No registry, plan, schema version, module list, unrelated module, release, or deployment file changed.

## Assumptions

- `Transaction.created_at` is the pending polling epoch; it is persisted and available on reopen.
- Generic core reconcile and abandon behavior from CORE-ROLLBACK-01 remains authoritative. Defaults only projects those public journal outcomes.
- A status-schema version bump is unnecessary: the module-owned `outcome` field completes the planned v1 status shape and no stored status document is migrated.
- `TextEdit.copy()` is the Qt-native clipboard path available inside the hosted QML process.

## Residual risks

- An abandoned unwrapped terminal can still finish later and change the default; the UI now states this plainly, but the selector provides no cancellation channel.
- External terminal visibility remains a hint only; state and verification, not window count, decide transaction outcomes.
- Live shell styling, actual clipboard integration, and real terminal/package flows still need disposable-session acceptance before release claims.

## Integration notes

- Cherry-pick the single commit reported by the worker.
- The shared `handlesPendingHandoffs: true` contract is generic: only pages that declare it suppress `ModuleRegistry` fallback polling.
- Re-run the full suite after cherry-picking alongside concurrent module waves.
- Independent reviewer gate remains required; this handoff does not claim release or deployment readiness.
