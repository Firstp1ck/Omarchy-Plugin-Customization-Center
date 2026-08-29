#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH="$root/backend" python - "$root" <<'PY'
import importlib.util, json, pathlib, sys, types
root = pathlib.Path(sys.argv[1]); package = root / "modules/bar/backend"
parent = types.ModuleType("cc_modules"); parent.__path__ = []; sys.modules["cc_modules"] = parent
spec = importlib.util.spec_from_file_location("cc_modules.bar", package / "__init__.py", submodule_search_locations=[str(package)])
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
assert module.MODULE.id == "bar"
assert json.loads((root / "modules/bar/module.json").read_text())["queries"] == ["catalog"]
print("bar CLI/module smoke: ok")
PY
