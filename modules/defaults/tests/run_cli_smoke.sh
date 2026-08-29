#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
tmp=$(mktemp -d)
trap '/usr/bin/rm -rf "$tmp"' EXIT
/usr/bin/mkdir -p "$tmp/home/.config/omarchy" "$tmp/home/.local/state" "$tmp/cache" "$tmp/runtime" "$tmp/bin" "$tmp/omarchy"
cat >"$tmp/bin/defaults-stub" <<'EOF'
#!/usr/bin/python3
import json, os, sys
name=os.path.basename(sys.argv[0]); args=sys.argv[1:]
if name == 'omarchy-default-browser': print('chromium')
elif name == 'omarchy-default-terminal': print('foot')
elif name == 'omarchy-default-editor': print('nvim')
elif name == 'omarchy-default-agent': pass
elif name == 'xdg-settings': print('chromium.desktop')
elif name == 'xdg-mime': print('chromium.desktop')
elif name == 'xdg-terminal-exec': print('foot.desktop')
elif name == 'pacman': pass
elif name == 'mise': raise SystemExit(1)
elif name == 'hyprctl': print('[]')
elif name == 'omarchy': print(json.dumps({'ok':True,'commands':[
 {'route':'omarchy default browser','args':'[chromium|chrome|brave|brave-origin|edge|firefox|zen]'},
 {'route':'omarchy default terminal','args':'[alacritty|foot|ghostty|kitty]'},
 {'route':'omarchy default editor','args':'[code|cursor|zed|sublime_text|helix|vim|emacs|nvim]'},
 {'route':'omarchy default agent','args':'[pi|omp|opencode|ori|claude|codex|grok|agy|copilot|crush]'}]}))
EOF
/usr/bin/chmod +x "$tmp/bin/defaults-stub"
for command in omarchy-default-browser omarchy-default-terminal omarchy-default-editor omarchy-default-agent omarchy xdg-settings xdg-mime xdg-terminal-exec mise pacman hyprctl; do /usr/bin/ln -s defaults-stub "$tmp/bin/$command"; done
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/home/.config" XDG_STATE_HOME="$tmp/home/.local/state" XDG_CACHE_HOME="$tmp/cache" XDG_RUNTIME_DIR="$tmp/runtime" OMARCHY_PATH="$tmp/omarchy" PATH="$tmp/bin"
sample="$root/modules/defaults/tests/fixtures/sample-draft.json"
"$root/backend/ccctl" status defaults
"$root/backend/ccctl" validate defaults --draft "$sample"
"$root/backend/ccctl" plan defaults --draft "$sample"
