from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .chords import ChordError, normalize

_CALL = re.compile(r'^\s*o\.(bind|bind_toggle)\(\s*("(?:[^"\\]|\\.)*")\s*,\s*(nil|"(?:[^"\\]|\\.)*")\s*,\s*(.*)$')
_QUOTED = re.compile(r'^\s*("(?:[^"\\]|\\.)*")')


def _literal(value: str) -> str:
    return json.loads(value)


def _paths(root: Path) -> list[Path]:
    directory = root / "default/hypr/bindings"
    return sorted(directory.glob("*.lua")) if directory.is_dir() else []


def _digest(paths: list[Path]) -> str:
    payload = []
    for path in paths:
        try:
            payload.append(path.name + "\0" + path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "sha256:" + hashlib.sha256("\n".join(payload).encode()).hexdigest()


def _harness(paths: list[Path]) -> str:
    files = ",".join(json.dumps(str(path)) for path in paths)
    return r'''
local function quote(value)
  if value == nil then return "null" end
  value = tostring(value)
  value = value:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
  return '"' .. value .. '"'
end
local function boolean(value) return value and "true" or "false" end
local function proxy(path)
  local value = { __native = path }
  return setmetatable(value, {
    __index = function(_, key) return proxy(path .. "." .. tostring(key)) end,
    __call = function(_, ...) return proxy(path .. "()") end
  })
end
local function command_from(value)
  if type(value) == "string" then return "exec", value end
  if type(value) == "function" then return "function", nil end
  if type(value) ~= "table" then return "native", nil end
  if value.__native then return "native", nil end
  if value.omarchy then return "exec", "omarchy-launch-" .. value.omarchy end
  if value.launch then return "exec", "uwsm-app -- " .. value.launch end
  if value.webapp then return "exec", "omarchy-launch-webapp '" .. value.webapp .. "'" end
  if value.tui then return "exec", "omarchy-launch-tui '" .. value.tui .. "'" end
  return "native", nil
end
local o = {}
function o.bind(keys, description, dispatcher, options)
  options = options or {}
  local kind, command = command_from(dispatcher)
  local info = debug.getinfo(options.__sourceLevel or 2, "Sl") or {}
  local source = tostring(info.source or ""):gsub("^@", "")
  local module = source:match("/([^/]+)%.lua$") or "unknown"
  io.write("{" ..
    '"keys":' .. quote(keys) ..
    ',"description":' .. quote(description or "") ..
    ',"dispatcherKind":' .. quote(kind) ..
    ',"command":' .. (command and quote(command) or "null") ..
    ',"locked":' .. boolean(options.locked) ..
    ',"release":' .. boolean(options.release) ..
    ',"repeating":' .. boolean(options.repeating) ..
    ',"nonConsuming":' .. boolean(options.non_consuming) ..
    ',"autoConsuming":' .. boolean(options.auto_consuming) ..
    ',"bypass":' .. boolean(options.bypass) ..
    ',"module":' .. quote(module) ..
    ',"sourceFile":' .. quote(source) ..
    ',"sourceLine":' .. tostring(info.currentline or 0) .. "}\n")
  return proxy("bind")
end
function o.bind_toggle(keys, description, name, options)
  options = options or {}
  options.__sourceLevel = 3
  local result = o.bind(keys, description, "omarchy-toggle-" .. name, options)
  options.__sourceLevel = nil
  return result
end
function o.cmd_present(_) return true end
function o.preinstalled_bindings_enabled() return true end
local hl = {
  dsp = proxy("hl.dsp"),
  on = function(...) return proxy("on") end,
  timer = function(...) return proxy("timer") end,
  dispatch = function(...) return proxy("dispatch") end,
  config = function(...) return proxy("config") end,
  exec_cmd = function(value) return value end,
  get_config = function(...) return 1 end,
  bind = function(...) return proxy("bind") end
}
local env = {
  o=o, hl=hl, ipairs=ipairs, pairs=pairs, next=next, type=type, tostring=tostring,
  tonumber=tonumber, table=table, string=string, math=math, setmetatable=setmetatable,
  select=select, pcall=pcall, error=error
}
env._G = env
local files = {''' + files + r'''}
for _, path in ipairs(files) do
  local chunk, load_error = loadfile(path, "t", env)
  if not chunk then error(load_error) end
  local ok, run_error = pcall(chunk)
  if not ok then error(path .. ": " .. tostring(run_error)) end
end
'''


def load_default_catalog(ctx: Any) -> tuple[list[dict[str, Any]], str, str]:
    paths = _paths(ctx.paths.omarchy_path)
    digest = _digest(paths)
    if not paths:
        return [], digest, "catalog files are missing"
    if ctx.commands.which("lua") is None:
        return [], digest, "lua is unavailable; the default catalog is untrusted"
    result = ctx.commands.run(["lua"], timeout_s=10, env_extra={"LC_ALL": "C"}, stdin=_harness(paths), capture_limit=2 * 1024 * 1024)
    if result.timed_out or result.exit_code != 0 or result.truncated:
        reason = "catalog harness timed out" if result.timed_out else (result.stderr.strip() or "catalog harness failed")
        return [], digest, reason
    entries: list[dict[str, Any]] = []
    try:
        for line in result.stdout.splitlines():
            value = json.loads(line)
            try:
                chord = normalize(value["keys"])
            except ChordError:
                continue
            flags = {name: bool(value[name]) for name in ("locked", "release", "repeating", "nonConsuming", "autoConsuming", "bypass")}
            entries.append({"keys": value["keys"], "identity": chord["identity"], "display": chord["display"],
                            "phase": "release" if flags["release"] else "press", "description": value["description"],
                            "dispatcherKind": value["dispatcherKind"], "command": value["command"], "flags": flags,
                            "module": value["module"], "sourceFile": value["sourceFile"],
                            "sourceLine": int(value["sourceLine"]), "conditional": False})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [], digest, "catalog harness output is malformed: " + str(error)
    return entries, digest, ""


def read_default_catalog(root: Path) -> tuple[list[dict[str, Any]], str]:
    paths = _paths(root)
    entries: list[dict[str, Any]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            match = _CALL.match(line)
            if not match:
                continue
            kind, keys_raw, description_raw, rest = match.groups()
            command_match = _QUOTED.match(rest)
            command = _literal(command_match.group(1)) if command_match else None
            keys = _literal(keys_raw)
            try:
                chord = normalize(keys)
            except ChordError:
                continue
            description = "" if description_raw == "nil" else _literal(description_raw)
            flags_text = rest[command_match.end():] if command_match else rest
            flags = {"locked": bool(re.search(r"\blocked\s*=\s*true", flags_text)),
                     "release": bool(re.search(r"\brelease\s*=\s*true", flags_text)),
                     "repeating": bool(re.search(r"\brepeating\s*=\s*true", flags_text)),
                     "nonConsuming": bool(re.search(r"\bnon_consuming\s*=\s*true", flags_text)),
                     "autoConsuming": bool(re.search(r"\bauto_consuming\s*=\s*true", flags_text)),
                     "bypass": bool(re.search(r"\bbypass\s*=\s*true", flags_text))}
            if kind == "bind_toggle" and command:
                command = "omarchy-toggle-" + command
            entries.append({"keys": keys, "identity": chord["identity"], "display": chord["display"],
                            "phase": "release" if flags["release"] else "press", "description": description,
                            "dispatcherKind": "exec" if command is not None else ("function" if "function" in rest else "native"),
                            "command": command, "flags": flags, "module": path.stem,
                            "sourceFile": str(path), "sourceLine": line_number, "conditional": False})
    return entries, _digest(paths)


def search_actions(static_entries: list[dict[str, Any]], defaults: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    needle = text.casefold().strip()
    combined = [*static_entries]
    combined.extend({"id": "default:" + entry["module"] + ":" + str(entry["sourceLine"]),
                     "title": entry["description"] or entry["keys"], "command": entry["command"],
                     "category": "Omarchy default", "module": entry["module"],
                     "sourceFile": entry["sourceFile"], "sourceLine": entry["sourceLine"]}
                    for entry in defaults if entry.get("command"))
    if needle:
        combined = [item for item in combined if needle in (str(item.get("title", "")) + " " + str(item.get("command", ""))).casefold()]
    return combined[:50]
