#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH="$root/backend" python - "$root" <<'PY'
import importlib.util, json, pathlib, sys, types
root = pathlib.Path(sys.argv[1]); package = root / "modules/plugins/backend"
parent = types.ModuleType("cc_modules"); parent.__path__ = []; sys.modules["cc_modules"] = parent
spec = importlib.util.spec_from_file_location("cc_modules.plugins", package / "__init__.py", submodule_search_locations=[str(package)])
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
metadata = json.loads((root / "modules/plugins/module.json").read_text())
assert module.MODULE.id == metadata["id"] == "plugins"
assert metadata["queries"] == ["validate"]
assert "terminal_handoff" in metadata["coreServices"]
print("plugins CLI/module smoke: ok")
PY
