# CORE-ROLLBACK-01 handoff

Status: implemented and validated
Run identity: worker continuation run for `CORE-ROLLBACK-01`
Base revision: `0073fec0ed7b097bb6d05c463e3a1e06af57e529`
Result: dirty working tree on the base revision, intentionally uncommitted for parent integration

## Implemented

- Added `Operation.inverse_after` with camel-case `inverseAfter` serialization and plan-schema support. The field defaults to an empty tuple, so existing plan documents still load without a schema-version change.
- Added `inverse_after` to every public operation builder.
- Added generic plan validation for missing, duplicate, cyclic, forward, and confirmation-boundary-crossing inverse dependencies.
- Added one stable topological ordering helper. It uses reverse completion order when dependencies do not constrain an operation, ignores dependencies whose forward operations did not complete, and is used by automatic rollback, crash recovery, and committed user undo.
- Preserved the existing timed-confirmation undo partition. Plans that would require an inverse dependency to cross that safety boundary now fail validation rather than silently violating either contract.
- Changed failed handoff reconciliation to store the complete `VerifyResult`, append its exact code, reason, and evidence to transaction errors, and roll back with reason `verification`.
- Changed `abandon` to run the normal rollback walk. Completed reversible setters are undone, the terminal handoff is recorded as skipped and non-reversible, and inverse failure returns `rollback_failed`.

## Changed files

- `backend/customization_center/core/types.py`: operation field and JSON round trip.
- `backend/customization_center/core/operations.py`: builder passthrough and field validation.
- `backend/customization_center/core/executor.py`: dependency validation and ordering, reconcile persistence, safe abandon.
- `schemas/plan-v1.json`: optional `inverseAfter` operation property.
- `tests/core/test_types.py`: camel-case round trip.
- `tests/core/test_operations.py`: all-builder passthrough coverage.
- `tests/core/test_executor.py`: validation, stable ordering, partial completion, composed plans, digest participation, failure rollback, crash recovery, committed undo, verification persistence, abandon, and rollback-failure coverage.
- `reports/handoffs/core-rollback-01.md`: this handoff.

## Validation

- Initial targeted run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/core/test_types.py tests/core/test_operations.py tests/core/test_executor.py` exited 1. One new assertion accidentally constructed a cycle while testing forward-reference rejection. The implementation was unchanged; the test fixture was corrected to isolate the intended case.
- Final targeted run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/core/test_types.py tests/core/test_operations.py tests/core/test_executor.py` exited 0.
- Contract run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/contract` exited 0.
- Full run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider` exited 0 with one expected skip.
- The final three commands were rerun in sequence after the confirmation-boundary regression test was added. All exited 0.
- `python3 -m json.tool schemas/plan-v1.json` exited 0.
- `git diff --check` exited 0.
- Cache scan found no `__pycache__` or `.pytest_cache` directories.
- `git diff --cached --quiet` exited 0. No files are staged.

## Deviations and assumptions

- No transaction schema or schema version changed. Transaction records embed `plan-v1`, and `Operation.from_json` defaults a missing `inverseAfter` to an empty tuple.
- No module-specific logic was added.
- Existing timed-confirmation undo ordering remains authoritative. A dependency that crosses that rollback boundary is rejected during plan validation.
- No checks were omitted.

## Residual risks

- Current plans do not use cross-boundary inverse dependencies. They are rejected because satisfying them would conflict with the confirmed-layout undo gate.
- The themes module must explicitly attach its approved directory, activation, and wallpaper dependencies in `THEMES-HARDEN-01`; this workstream only provides and tests the generic contract.

## Integration notes

- Review `executor.py` dependency semantics before committing.
- After integration, the defaults hardening worker can rely on reconciliation and abandon behavior without core edits.
- The themes hardening worker should pass `inverse_after` through `ops.RunCommand` for activation and wallpaper operations.
- Parent review remains required. This handoff does not claim the feature review gate is satisfied.
