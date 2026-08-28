# Architecture

The Customization Center is one Omarchy overlay with independent modules. QML presents state and edits drafts. `backend/ccctl` is the only backend entry point. Module backends describe changes as plans, and the core executor is the only component that applies them.

## Call flow

1. The overlay runs `ccctl modules`. The registry reads the explicit `MODULES` list, validates each `module.json`, imports its backend as `cc_modules.<id>`, and reports a warning without hiding healthy modules if one fails.
2. `ccctl status`, `validate`, and `plan` build read-only contexts. A context exposes paths, declared command probes, shell IPC, Hyprland reads, the journal, and the registry. Planning returns frozen operations and does not write.
3. The page emits `requestDraftPatch(var patch)` when an input changes. DraftStore persists the envelope through `ccctl draft save`. Pages also expose `requestPlan`, `requestApply`, `requestReset`, `requestNavigate`, `focusFirst()`, and `handlePayload(payload)`.
4. Apply recomputes status and the plan. It checks the revision, plan digest, paths, resource claims, confirmation keys, gate count, and handoff ordering while holding the global apply lock.
5. The executor journals the transaction, arms any confirmation backstop, takes backups, runs operations, verifies each plan segment, and commits. A failure walks inverses in reverse and records conflicts or recovery commands.
6. A timed gate exposes its one-time clear token only through `ccctl transaction current`. Confirmation is lock-free. A terminal handoff pauses in `pending_handoff` until `ccctl reconcile` observes its sentinel and verification passes.

## Runtime boundaries

Modules import `customization_center.core` only. They read through `Context`, return operations from `plan`, and inspect fresh state in `verify`. They do not implement apply or rollback.

State is kept under XDG configuration, state, cache, and runtime directories. Runtime code never writes into the plugin directory or `$OMARCHY_PATH`. `ccctl` disables Python bytecode before importing the package.

Transactions are durable JSON records. `applying`, expired `awaiting_confirmation`, interrupted `rolling_back`, and completed handoff records are recovered on startup. Any unresolved `rollback_failed` record blocks future applies.
