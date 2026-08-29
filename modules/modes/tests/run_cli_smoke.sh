#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
export CC_EXTRA_MODULE_DIRS="$root/modules/modes"
"$root/backend/ccctl" modules | python -c 'import json,sys; value=json.load(sys.stdin); assert value["ok"]; assert any(item["id"]=="modes" for item in value["data"]["modules"])'
