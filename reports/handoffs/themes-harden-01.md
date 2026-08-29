# THEMES-HARDEN-01 handoff

Status: implemented and validated

Run identity: replacement attempt `3fe46219-eda2-4932-b9c2-fc8fde9771c0`, recovered from its captured worktree patch after the managed worktree timed out and could not be resumed

Base revision: `db39f1c7a7b67d9254d2a649837718a0da143f8d`

Result: dirty working tree on the base revision, ready for parent commit

## Retry provenance

- Attempt 1, run `87be425b-98c3-4000-99be-991b93c40992`, failed with a provider `finish_reason` error before changing files. Its worktree diff was empty.
- Attempt 2, run `3fe46219-eda2-4932-b9c2-fc8fde9771c0`, implemented the workstream but reached the 30-minute runtime limit during final validation. Pi captured a 37-file patch before removing the worktree.
- Resume was attempted first and failed because the managed worktree had already been removed.
- The integration owner applied the captured patch to `db39f1c`, inspected it, completed three bounded corrections, and reran the required checks.

## Implemented

- Added generic `Paths.read_regular()` support for bounded, no-follow regular-file reads with lstat/fstat identity checks. Theme wallpaper ingestion now uses it.
- Added `inverseAfter` metadata for directory restore, previous-theme activation, and previous-wallpaper restoration. Failure rollback and committed undo now use the required order.
- Added shell-ping, exact restore payload, payload-size, and open-preview eligibility checks. Status derives the open preview from journal history.
- Added all eight activation verification checks: active slug, colors, shell sections, unresolved placeholders, custom fragments, background, shell health, and unrelated concurrent changes.
- Added a complete Python token resolver and matching QML resolver for palette roles, all twelve sections, machine overrides, masking, borders, font and spacing metrics, bar metrics, and control states.
- Expanded contrast diagnostics across palette, surfaces, selected states, controls, borders, black and white bounds, and invisible-text blockers. Warning ids are pair-specific and unaccepted contrast warnings become plan confirmations.
- Added theme import and materialization, activation, duplication, deletion, typed section editors, wallpaper controls, diagnostics, all preview scenarios, and Try-in-shell update and restore flows.
- Added absolute wallpaper-path validation, activation background-root checks, plain-theme executable/config warnings, public TOML writer use, and VP8, VP8L, and VP8X header support.
- Added backend, rollback, capability, query, resolver, verification, image, planning, QML, and integration coverage.

## Integration-owner corrections

The recovered patch passed its initial suites. Parent inspection found and fixed three remaining issues:

1. Canonicalized unrelated theme inventory ordering before the concurrent-change digest, so changing the active slug cannot create a false positive.
2. Made verification enforce that no-wallpaper activation leaves the prior background unchanged and that ordinary activation selects an existing background.
3. Made QML patch-then-plan actions defer planning until the draft patch is observable. “Update preview” now restores the previous preview and starts a new reviewed preview plan instead of only stopping the old one.

## Changed files

- `backend/customization_center/core/paths.py`
- `tests/core/test_paths.py`
- `modules/themes/backend/` including new `resolver.py`
- `modules/themes/components/` including new `InstalledThemes.qml`
- `modules/themes/module.json`
- `modules/themes/schemas/status-v1.json`
- `modules/themes/tests/` including new capability/query, resolver, rollback, verify, and QML suites
- `reports/handoffs/themes-harden-01.md`

No registry, canonical plan, unrelated module, release, or deployment file changed.

## Validation

Final commands were run from the repository root after the integration-owner corrections.

| Command | Exit | Result |
|---|---:|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/core/test_paths.py modules/themes/tests` | 0 | 37 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/contract -k themes` | 0 | 4 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/qml modules/themes/tests/test_qml_page.py` | 0 | shared and themes QML suites passed with one expected skip |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider` | 0 | full suite passed with one expected skip |
| `qmllint -I /mnt/SSD_NVME_4TB/GitHub/omarchy-fork/shell -I tests/qml/imports -I . modules/themes/Page.qml modules/themes/components/*.qml modules/themes/components/preview/*.qml` | 0 | no diagnostics |
| `PYTHONDONTWRITEBYTECODE=1 python3 modules/themes/tests/smoke_ccctl.py` | 0 | status, validate, and plan returned successful envelopes |
| `python3 -m json.tool modules/themes/module.json` | 0 | schema document parsed |
| `python3 -m json.tool modules/themes/schemas/status-v1.json` | 0 | schema document parsed |
| `git diff --check` | 0 | clean |
| cache-directory scan | 0 | no `__pycache__` or `.pytest_cache` directories |

## Deviations and assumptions

- The module uses the plan-approved in-memory shell render fallback rather than executing `omarchy-theme-set-templates` in a scratch HOME. Verification checks the resulting active files and unresolved placeholders, but no claim is made that every external template side effect was exercised.
- The generic secure-read API was a supervisor-approved core boundary expansion. It contains no theme-specific logic.
- Import resolves colors and section fragments locally from known Omarchy formats. Unknown files and keys remain visible and are not copied.

## Residual risks

- Live Omarchy activation, real hooks and retints, shell restart during Try in shell, wallpaper decoding, and visual parity still need the disposable-session acceptance pass.
- QML offscreen tests verify state and action wiring, not screenshot-level fidelity.
- Theme-set itself still reports little useful failure information. The module relies on post-activation verification as designed.
- Independent final reviewers may identify further gaps when all eight modules and desktop modes are integrated.

## Integration notes

- Commit this patch as one themes hardening change.
- Re-run the full suite after bar, plugins, and modes are integrated.
- This handoff does not satisfy the final two-reviewer or VM acceptance gates.
