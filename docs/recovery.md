# Recovery

The plugin needs `omarchy plugin enable firstpick.customization-center` before its overlay can open. Recovery itself is terminal-only and does not depend on the overlay.

Run commands through the installed plugin path, for example:

```sh
~/.config/omarchy/plugins/firstpick.customization-center/backend/ccctl doctor
```

## Inspect recovery state

```sh
ccctl recover
ccctl transaction current
ccctl history --limit 50
ccctl history --state rollback_failed
ccctl transaction <transaction-id>
```

`applying` means an executor may still be running. `recover` takes the global lock and rolls back an interrupted executor when possible. `awaiting_confirmation` means a gated change is waiting; use the token shown by `transaction current` with `ccctl confirm <id> --token <token>`, or use `ccctl rollback <id> --reason user`. An expired gate is rolled back by recovery.

`pending_handoff` means a terminal action was launched. Finish the terminal command and run `ccctl reconcile <id>`. If the terminal action was abandoned, run `ccctl abandon <id>`.

`rolling_back` is resumed by `ccctl recover`. `committed` and `rolled_back` are terminal records. Undo a committed transaction with `ccctl rollback <id> --reason user`; this creates a separate inverse transaction. If state drift is intentional, review it first and add `--force-stale`.

## Resolve rollback_failed

A `rollback_failed` transaction blocks every apply. Inspect it:

```sh
ccctl transaction <id>
```

Its recovery data lists each backup path and a restore command. Restore only the listed paths, one at a time:

```sh
ccctl restore <id> --path /absolute/path/from-the-record
```

Then inspect the file and run `ccctl transaction <id>` again. A rollback failure with no affected file, such as a failed command inverse or deferred reload, cannot be repaired with a backup. After manually checking that the system is in the intended state, deliberately acknowledge that operation:

```sh
ccctl resolve <id> --operation <operation-id>
```

This acknowledgement does not run the operation. It only marks that non-file recovery item resolved. Run `ccctl recover` after every listed file and non-file item is resolved. Backups are retained. Do not copy a backup body by guessing its numbered filename because the manifest is the authority for path, mode, and digest.

If a restored file is under `~/.config/hypr`, inspect it before manually running `hyprctl reload`. For shell configuration, restart or reload the shell only after confirming that `shell.json` parses. For a theme directory, restore every path listed for that transaction before activating a theme.
