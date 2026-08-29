# BAR-IMPLEMENT-01 handoff

## Identity and status

- Workstream: `BAR-IMPLEMENT-01`
- Role: isolated-worktree writer
- Status: implemented and locally validated; review required
- Base commit: `882faee418d548c3c6672d107f93fc0587e5b4f0`
- Result commit: the single commit containing this handoff; authoritative SHA is reported in the worker acceptance report because a commit cannot contain its own final SHA.

## Changed files

All implementation files are under `modules/bar/`: module metadata; backend model/status/validation/planning/verification; draft, status, and preset schemas; page and seven private QML components; backend and QML tests; fixtures; and CLI smoke script. This handoff is the only changed file outside that directory and is within the assigned boundary.

## Implementation notes

- Reads `ping`, `listShellConfig`, `listPlugins`, the public core catalog join, normalized widget settings schemas, user `shell.json`, and shipped defaults.
- Models occurrences independently of widget ids and preserves repeated `allowMultiple` instances, string entries, unknown entry settings, and unknown bar keys.
- Uses one exclusive `shell.bar` resource claim.
- Chooses IPC only where selectors and inverses are expressible exactly. Position, transparency, center anchor, bar id, repeated insertion, key deletion, clone relationships, custom removal, and extra-key changes select the file route.
- The file route writes a copy of the effective shell document with only `bar` replaced, surrounds the atomic write with `reloadConfig`, and refuses down-shell, malformed, non-v1, scanning, and stale states.
- IPC operations carry exact occurrence selectors, shell-file backup claims, and explicit inverses. Newly introduced settings keys are identified as approximate rollback because current IPC can only restore them to `null`.
- Verification requires shell availability, file/config convergence, exact configured bar state, and configured-versus-active bar agreement.
- The QML page uses Omarchy `qs.Commons` tokens and `qs.Ui` controls, supports pointer and keyboard selection/edit actions, visible focus, repeated-instance selection, and deep links. Selection-only payloads are tested to emit no draft mutation.

## Validation

Commands were run from the isolated worktree with `PYTHONDONTWRITEBYTECODE=1` and pytest cache disabled where applicable.

| Command | Exit | Result |
|---|---:|---|
| `pytest -q -p no:cacheprovider modules/bar/tests` | 0 | backend, planner, inverse, preservation, verification, QML controls, and payload tests passed |
| `pytest -q -p no:cacheprovider tests/qml` | 0 | shared QML boundaries and repository qmllint test passed; one environment-dependent test skipped |
| `pytest -q -p no:cacheprovider modules/bar/tests tests/qml` | 0 | combined relevant suite: `10 passed, 1 skipped` |
| `qmllint -I tests/qml/imports -I /mnt/SSD_NVME_4TB/GitHub/omarchy-fork/shell -I . modules/bar/Page.qml modules/bar/components/*.qml` | 0 | no diagnostics |
| `modules/bar/tests/run_cli_smoke.sh` | 0 | backend module import and module metadata smoke passed |
| Python JSON parse over `module.json` and `schemas/*.json` | 0 | five documents parsed |
| `git diff --check` | 0 | clean |
| cache scan under `modules/bar` | 0 | no bytecode or pytest caches found |

## Omissions and deviations

- The canonical registry intentionally was not edited because it is outside this writer boundary. Consequently canonical `tests/contract` cannot discover `bar` in this worktree. Module contract-relevant behavior is covered locally, but the integration owner must run the canonical contract suite after adding the registry line. No shared API was found missing.
- The CLI smoke imports the module through the same isolated package shape rather than invoking `ccctl status bar`, because the canonical registry does not yet include bar.
- Live disposable-VM checks, rendered screenshot comparison, and a real third-party bar fallback timing check remain integration tasks.
- Preset schemas are shipped, but preset persistence UI is not implemented because it would require a new query/mutation path not exposed by the approved generic core APIs. No module-local file writer was introduced.

## Assumptions and residual risks

- Current pinned Omarchy IPC behavior matches the plan: no whole-bar CAS endpoint and no exact inline-key deletion.
- A same-id concurrent swap in the narrow interval after revision checking remains indistinguishable to selector validation.
- IPC rollback of a newly added setting writes `null`; review warns about this approximation.
- Verification consumes the fresh status supplied by the executor. It does not sleep inside the module; bounded polling belongs to the executor/integration caller in the current public contract.
- Full behavior with the canonical registry and transaction executor must be rechecked after cherry-pick.

## Integration notes

1. Cherry-pick the implementation commit reported by the worker.
2. Add `bar` to the canonical module registry in the integration-owner change.
3. Run targeted and full contract suites, executor fault tests, shared QML, and full pytest.
4. Exercise file creation/removal rollback, malformed/down-shell refusal, repeated instances, catalog drift, and third-party fallback in the disposable Omarchy VM.
