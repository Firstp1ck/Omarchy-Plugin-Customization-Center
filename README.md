# Omarchy Customization Center

The Customization Center is an Omarchy shell overlay for reviewing and applying desktop configuration changes through shared drafts and transactions.

## Install

```bash
omarchy plugin add https://github.com/Firstpick/Omarchy-Plugin-Customization-Center.git
omarchy plugin enable firstpick.customization-center
omarchy-shell shell summon firstpick.customization-center '{}'
```

Enabling the plugin is mandatory. `omarchy plugin add` installs third-party plugins disabled, and the shell will not summon a disabled plugin.

The minimum supported Omarchy source revision is commit `71b0887c`. Monitor and keybinding support requires Hyprland 0.55 or newer.

A module can be opened directly with a summon payload:

```bash
omarchy-shell shell summon firstpick.customization-center '{"module":"bar"}'
```

## Layout

- `CustomizationCenter.qml` implements the host overlay contract and creates one surface per screen.
- `core/` contains shared QML navigation, forms, drafts, backend calls, review, confirmation, and transaction state.
- `backend/ccctl` is the only backend entry point used by QML.
- `backend/customization_center/` contains the shared Python executor and adapters.
- `modules/<id>/` contains each module's page, backend, schemas, and tests.
- `schemas/` contains shared wire-format schemas.
- `tests/` contains Python, contract, fixture, and QML tests.

Runtime state is stored under the XDG configuration, state, cache, and runtime directories. The plugin does not write inside its own installation directory.

## Page contract

Module pages receive `draft` as read-only state and request changes by emitting `requestDraftPatch(patch)`. The name is intentionally distinct from QML's automatically generated `draftChanged()` property notifier. Pages must not assign to or mutate `draft` directly. Pages may optionally declare `property var backendClient: null` to receive the registry client for read-only `query` previews and must not reassign it or use it for mutations.

## Development

Run the QML checks from the repository root. Set `OMARCHY_SOURCE` to an Omarchy checkout at commit `71b0887c`; on the development host the tests fall back to `/mnt/SSD_NVME_4TB/GitHub/omarchy-fork` when the variable is unset.

```bash
export OMARCHY_SOURCE=/path/to/omarchy
QML2_IMPORT_PATH="$OMARCHY_SOURCE/shell" \
QML_IMPORT_PATH="$OMARCHY_SOURCE/shell" \
python3 -m pytest -q -p no:cacheprovider tests/qml
```

Run the complete test suite without creating Python bytecode or a pytest cache:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
```

`tests/qml/test_qml.py` runs `qmllint` over every repository QML file before running `qmltestrunner`.

`BackendClient` wraps all `ccctl` commands used by QML. `capabilities` and `historyFiltered` are 10-second reads; `abandon`, `restore`, `resolve`, and `draftAssetAdd` are globally queued 30-second mutations; `recover` is globally queued with the 15-minute apply timeout ceiling.

## Documentation

See `docs/architecture.md` for the shared model, `docs/adding-a-module.md` for the module contract, `docs/managed-files.md` for ownership boundaries, and `docs/recovery.md` for terminal recovery procedures.
