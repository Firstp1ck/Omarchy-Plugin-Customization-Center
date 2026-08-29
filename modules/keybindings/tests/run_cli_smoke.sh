#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
tmp=$(mktemp -d)
trap '/usr/bin/rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home/.config/omarchy" "$tmp/home/.local/state" "$tmp/cache" "$tmp/runtime" "$tmp/bin" "$tmp/omarchy/default/hypr/bindings"
cat >"$tmp/bin/hyprctl" <<'EOF'
#!/usr/bin/python3
import json, sys
args=sys.argv[1:]
if args == ['binds']: print('', end='')
elif args == ['-j','binds']: print('[]')
elif args == ['-j','devices']: print('{"keyboards":[],"switches":[]}')
elif args == ['version']: print('Hyprland 0.56.2')
elif args == ['-j','configerrors']: print('[""]')
else: print('{}')
EOF
chmod +x "$tmp/bin/hyprctl"
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/home/.config" XDG_STATE_HOME="$tmp/home/.local/state" XDG_CACHE_HOME="$tmp/cache" XDG_RUNTIME_DIR="$tmp/runtime" OMARCHY_PATH="$tmp/omarchy" PATH="$tmp/bin"
sample="$root/modules/keybindings/tests/fixtures/sample-draft.json"
"$root/backend/ccctl" status keybindings
"$root/backend/ccctl" validate keybindings --draft "$sample"
"$root/backend/ccctl" plan keybindings --draft "$sample"
