from __future__ import annotations

import inspect
import json
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

sys.dont_write_bytecode = True
_REPO = Path(__file__).resolve().parents[1]
_REAL_HOME = Path(os.environ.get("HOME", "/nonexistent")).resolve()
_REAL_GUARD_ROOTS = (_REAL_HOME / ".config/omarchy", _REAL_HOME / ".config/hypr",
                     _REAL_HOME / ".local/state/omarchy", _REAL_HOME / ".config/xdg-terminals.list")


def _snapshot(paths: tuple[Path, ...]) -> dict[str, tuple[int, int, int]]:
    result: dict[str, tuple[int, int, int]] = {}
    for root in paths:
        candidates = [root]
        if root.is_dir():
            candidates.extend(root.rglob("*"))
        for path in candidates:
            try:
                info = path.lstat()
                result[str(path)] = (info.st_mode, info.st_size, info.st_mtime_ns)
            except FileNotFoundError:
                pass
    return result


@pytest.fixture(autouse=True)
def outside_write_guard() -> Any:
    before = _snapshot(_REAL_GUARD_ROOTS)
    yield
    after = _snapshot(_REAL_GUARD_ROOTS)
    assert after == before, "a test modified an allowlisted path outside its temporary home"


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    config = home / ".config"
    state = home / ".local/state"
    cache = home / ".cache"
    runtime = tmp_path / "runtime"
    omarchy = tmp_path / "omarchy"
    for path in (home, config, state, cache, runtime):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_REPO / "tests/fixtures/omarchy", omarchy)
    (config / "omarchy").mkdir(parents=True)
    shutil.copy2(omarchy / "config/omarchy/shell.json", config / "omarchy/shell.json")
    values = {"HOME": home, "XDG_CONFIG_HOME": config, "XDG_STATE_HOME": state,
              "XDG_CACHE_HOME": cache, "XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": omarchy}
    for name, value in values.items():
        monkeypatch.setenv(name, str(value))
    return home


_STUB_SCRIPT = r'''#!/usr/bin/python3
import json, os, socket, sys
request = {"name": os.path.basename(sys.argv[0]), "argv": sys.argv,
           "stdin": sys.stdin.buffer.read().decode("utf-8", "replace"), "env": dict(os.environ)}
sock = socket.socket(socket.AF_UNIX)
sock.connect(os.path.join(os.environ["XDG_RUNTIME_DIR"], "cc-stub.sock"))
sock.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
data = b""
while not data.endswith(b"\n"):
    part = sock.recv(65536)
    if not part: break
    data += part
reply = json.loads(data)
if reply.get("delay"): __import__("time").sleep(float(reply["delay"]))
if reply.get("hang"): __import__("time").sleep(float(reply.get("hangSeconds", 3600)))
sys.stdout.write(reply.get("stdout", "")); sys.stderr.write(reply.get("stderr", ""))
raise SystemExit(int(reply.get("exit_code", reply.get("exitCode", 0))))
'''


class Stubs:
    def __init__(self, directory: Path, socket_path: Path) -> None:
        self.directory = directory
        self.socket_path = socket_path
        self.handlers: dict[str, Any] = {}
        self.log: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._server = socket.socket(socket.AF_UNIX)
        self._server.bind(str(socket_path))
        self._server.listen()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def __call__(self, name: str, handler: Any) -> "Stubs":
        self.handlers[name] = handler
        path = self.directory / name
        path.write_text(_STUB_SCRIPT, encoding="utf-8")
        path.chmod(0o755)
        return self

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            with client:
                if self._stop.is_set():
                    return
                data = b""
                while not data.endswith(b"\n"):
                    part = client.recv(65536)
                    if not part:
                        break
                    data += part
                try:
                    request = json.loads(data)
                    request["argv"][0] = request["name"]
                    self.log.append(request)
                    handler = self.handlers.get(request["name"], {"exit_code": 127, "stderr": "unstubbed command\n"})
                    if callable(handler):
                        try:
                            parameters = len(inspect.signature(handler).parameters)
                        except (TypeError, ValueError):
                            parameters = 1
                        reply = handler(request) if parameters == 1 else handler(request["argv"], request["stdin"], request["env"])
                    else:
                        reply = handler
                    if isinstance(reply, tuple):
                        reply = {"exit_code": reply[0], "stdout": reply[1] if len(reply) > 1 else "",
                                 "stderr": reply[2] if len(reply) > 2 else ""}
                    client.sendall(json.dumps(reply or {}).encode() + b"\n")
                except Exception as error:
                    try:
                        client.sendall(json.dumps({"exit_code": 125, "stderr": repr(error)}).encode() + b"\n")
                    except OSError:
                        return

    def calls(self, name: str) -> list[list[str]]:
        return [entry["argv"] for entry in self.log if entry["name"] == name]

    def records(self, name: str) -> list[dict[str, Any]]:
        return [entry for entry in self.log if entry["name"] == name]

    def close(self) -> None:
        self._stop.set()
        self._server.close()
        try:
            socket.socket(socket.AF_UNIX).connect(str(self.socket_path))
        except OSError:
            pass
        self._thread.join(timeout=1)


@pytest.fixture
def stub_command(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    directory = isolated_home.parent / "stubs"
    directory.mkdir()
    socket_path = Path(os.environ["XDG_RUNTIME_DIR"]) / "cc-stub.sock"
    stubs = Stubs(directory, socket_path)
    monkeypatch.setenv("PATH", str(directory))
    yield stubs
    stubs.close()


class FakeShell:
    def __init__(self, state_file: Path, stubs: Stubs) -> None:
        self.state_file = state_file
        self.stubs = stubs

    def read(self) -> dict[str, Any]:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def write(self, value: dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(value), encoding="utf-8")

    def switch(self, name: str, value: bool = True) -> None:
        state = self.read(); state[name] = value; self.write(state)

    def reject(self, method: str, body: str) -> None:
        state = self.read(); state.setdefault("rejections", {})[method] = body; self.write(state)


@pytest.fixture
def fake_shell(stub_command: Stubs, isolated_home: Path) -> FakeShell:
    manifests = []
    root = Path(os.environ["OMARCHY_PATH"]) / "shell/plugins"
    for path in sorted(list(root.rglob("manifest.json")) + list(root.rglob("*.manifest.json"))):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifests.append({"id": manifest["id"], "name": manifest.get("name", manifest["id"]),
                          "kinds": manifest.get("kinds", []), "enabled": True,
                          "active": manifest["id"] == "omarchy.bar", "canDisable": "bar" not in manifest.get("kinds", []),
                          "firstParty": True, "clonedFrom": manifest.get("omarchy", {}).get("clonedFrom", "")})
    state_file = isolated_home.parent / "fake-shell.json"
    state_file.write_text(json.dumps({"plugins": manifests,
                                      "shellConfig": json.loads((root.parent.parent / "config/omarchy/shell.json").read_text()),
                                      "down": False, "not_ready": False, "slow": False, "rejections": {}}), encoding="utf-8")
    fake = FakeShell(state_file, stub_command)

    def handler(request: dict[str, Any]) -> dict[str, Any]:
        state = fake.read()
        if state.get("slow"):
            return {"delay": 30}
        if state.get("down"):
            return {"exit_code": 1, "stderr": "omarchy-shell is not running\n"}
        if state.get("not_ready"):
            return {"exit_code": 1, "stderr": "omarchy-shell is not ready\n"}
        argv = request["argv"]
        if len(argv) < 3 or argv[1] != "shell":
            return {"exit_code": 1, "stderr": "Target not found.\n"}
        method, args = argv[2], argv[3:]
        if method in state.get("rejections", {}):
            return {"stdout": state["rejections"][method] + "\n"}
        if method == "ping": return {"stdout": "ok\n"}
        if method == "listPlugins": return {"stdout": json.dumps(state["plugins"]) + "\n"}
        if method == "listShellConfig": return {"stdout": json.dumps(state["shellConfig"]) + "\n"}
        if method in {"reloadConfig", "applyTheme"}: return {"stdout": "ok\n"}
        if method == "rescanPlugins" or method == "hide": return {"stdout": ""}
        plugin = next((item for item in state["plugins"] if args and item["id"] == args[0]), None)
        if method in {"enablePlugin", "setPluginEnabled"}:
            if plugin is None: return {"stdout": "unknown\n"}
            enabled = method == "enablePlugin" or (len(args) > 1 and args[1] == "true")
            plugin["enabled"] = enabled; fake.write(state); return {"stdout": "ok\n"}
        if method in {"putBarWidget", "moveBarWidget", "setBarWidget"}:
            if plugin is None: return {"stdout": "could not find widget " + (args[0] if args else "") + "\n"}
            layout = state["shellConfig"].setdefault("bar", {}).setdefault("layout", {"left": [], "center": [], "right": []})
            if method == "putBarWidget":
                placement = json.loads(args[1] or "{}")
                if not any((x == args[0] or isinstance(x, dict) and x.get("id") == args[0]) for section in layout.values() for x in section):
                    layout.get(placement.get("section", "right"), layout["right"]).append({"id": args[0]})
            elif method == "moveBarWidget":
                placement = json.loads(args[1] or "{}")
                entry = None
                for section in layout.values():
                    for item in list(section):
                        if item == args[0] or isinstance(item, dict) and item.get("id") == args[0]: entry = item; section.remove(item); break
                layout.get(placement.get("section", "right"), layout["right"]).insert(int(placement.get("index", 0)), entry or {"id": args[0]})
            else:
                for section in layout.values():
                    for item in section:
                        if isinstance(item, dict) and item.get("id") == args[0]: item[args[1]] = json.loads(args[2]); break
            fake.write(state); return {"stdout": "ok\n"}
        if method == "summon": return {"stdout": "ok\n" if plugin else "unknown\n"}
        return {"exit_code": 1, "stderr": "Function not found.\n"}

    stub_command("omarchy-shell", handler)
    return fake
