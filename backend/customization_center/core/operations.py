from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .atomic import mkdir_durable, remove_file, replace_directory_atomic, write_bytes_atomic
from .errors import CcError
from .managed_block import extract as extract_block
from .managed_block import replace as replace_block
from .types import Operation, OperationResult

_KINDS = frozenset({
    "WriteFileAtomic", "ReplaceManagedBlock", "EnsureDirectory", "ReplaceDirectoryAtomic",
    "RunCommand", "RestoreBackup", "RemoveFile", "ShellIpc", "HyprctlReload",
    "TimedConfirmation", "TerminalHandoff",
})
_PATH_KINDS = frozenset({"WriteFileAtomic", "ReplaceManagedBlock", "EnsureDirectory", "ReplaceDirectoryAtomic", "RestoreBackup", "RemoveFile"})
_UNSAFE_TOKEN = re.compile(r'''[\s;&|<>$`"']''')


def _next_id(ctx: Any) -> str:
    counters = ctx.cache.setdefault("operation_sequence", {})
    value = int(counters.get(ctx.module_id, 0)) + 1
    counters[ctx.module_id] = value
    return f"{ctx.module_id}.{value:04d}"


def _operation(ctx: Any, kind: str, params: dict[str, Any], summary: str,
               inverse: Operation | tuple[Operation, ...] | None, backup_paths: Iterable[str | Path] = (),
               timeout_s: float = 30.0, detail: dict[str, Any] | None = None) -> Operation:
    return Operation(_next_id(ctx), ctx.module_id, kind, params, summary, inverse,
                     tuple(str(Path(p).absolute()) for p in backup_paths), float(timeout_s), detail)


def _mode(value: str | int | None) -> str | None:
    if value is None:
        return None
    number = int(value, 8) if isinstance(value, str) else int(value)
    if not 0 <= number <= 0o7777:
        raise ValueError("mode is outside the octal permission range")
    return format(number, "04o")


def WriteFileAtomic(ctx: Any, path: str | Path, content: str | bytes, mode: str | int | None,
                    summary: str = "Write file", inverse: Operation | None = None) -> Operation:
    encoded: Any = content if isinstance(content, str) else {"base64": base64.b64encode(content).decode("ascii")}
    target = str(Path(path).absolute())
    operation_id = _next_id(ctx)
    inv = inverse or RestoreBackup(ctx, target)
    return Operation(operation_id, ctx.module_id, "WriteFileAtomic",
                     {"path": target, "content": encoded, "mode": _mode(mode)}, summary, inv,
                     (target,), 30.0, None)


def ReplaceManagedBlock(ctx: Any, path: str | Path, name: str | None = None, version: int = 1,
                        body: str | None = None, summary: str = "Replace managed block",
                        inverse: Operation | None = None, *, begin_marker: str | None = None,
                        end_marker: str | None = None) -> Operation:
    target = str(Path(path).absolute())
    operation_id = _next_id(ctx)
    params = {"path": target, "body": body}
    if begin_marker is not None or end_marker is not None:
        params.update({"begin_marker": begin_marker, "end_marker": end_marker})
    else:
        params.update({"name": name, "version": int(version)})
    if inverse is None:
        inverse_params = {**params, "body": None, "body_from_backup": True}
        inv = _operation(ctx, "ReplaceManagedBlock", inverse_params, "Restore managed block", ())
    else:
        inv = inverse
    return Operation(operation_id, ctx.module_id, "ReplaceManagedBlock", params, summary, inv,
                     (target,), 30.0, None)


def EnsureDirectory(ctx: Any, path: str | Path, mode: str | int = "0700", summary: str = "Ensure directory",
                    inverse: Operation | None = ()) -> Operation:
    # An empty inverse means the executor uses the created flag from the forward result.
    return _operation(ctx, "EnsureDirectory", {"path": str(Path(path).absolute()), "mode": _mode(mode)},
                      summary, inverse)  # type: ignore[arg-type]


def ReplaceDirectoryAtomic(ctx: Any, path: str | Path, staged_dir: str | Path | None,
                           allow_existing: bool = False, summary: str = "Replace directory",
                           inverse: Operation | None = ()) -> Operation:
    return _operation(ctx, "ReplaceDirectoryAtomic", {
        "path": str(Path(path).absolute()),
        "staged_dir": str(Path(staged_dir).absolute()) if staged_dir is not None else None,
        "allow_existing": bool(allow_existing),
    }, summary, inverse)  # type: ignore[arg-type]


def RunCommand(ctx: Any, argv: Sequence[str], timeout_s: float = 30.0, summary: str = "Run command",
               inverse: Sequence[str] | Operation | None = None, expect_exit: int = 0,
               capture_limit: int = 65536, env_extra: Mapping[str, str | None] | None = None,
               stdin: str | None = None, wait_policy: str = "exit") -> Operation:
    operation_id = _next_id(ctx)
    inv: Operation | None
    if isinstance(inverse, Operation) or inverse is None:
        inv = inverse
    else:
        inv = _operation(ctx, "RunCommand", {"argv": list(inverse), "timeout_s": float(timeout_s),
                         "expect_exit": 0, "capture_limit": int(capture_limit), "env_extra": {},
                         "stdin": None, "wait_policy": "exit"}, f"Undo: {summary}", ())
    return Operation(operation_id, ctx.module_id, "RunCommand",
                     {"argv": list(argv), "timeout_s": float(timeout_s), "expect_exit": int(expect_exit),
                      "capture_limit": int(capture_limit), "env_extra": dict(env_extra or {}),
                      "stdin": stdin, "wait_policy": wait_policy}, summary, inv, (), float(timeout_s), None)


def RestoreBackup(ctx: Any, path: str | Path, summary: str = "Restore backup") -> Operation:
    return _operation(ctx, "RestoreBackup", {"path": str(Path(path).absolute())}, summary, ())


def RemoveFile(ctx: Any, path: str | Path, summary: str = "Remove file",
               inverse: Operation | None = None) -> Operation:
    target = str(Path(path).absolute())
    operation_id = _next_id(ctx)
    inv = inverse or RestoreBackup(ctx, target)
    return Operation(operation_id, ctx.module_id, "RemoveFile", {"path": target}, summary, inv,
                     (target,), 30.0, None)


def ShellIpc(ctx: Any, method: str, args: Sequence[Any] = (), expect: Sequence[str] = ("ok",),
             expect_json: bool = False, backup_paths: Sequence[str | Path] = (),
             inverse: Operation | None = None, summary: str = "Call shell IPC") -> Operation:
    return _operation(ctx, "ShellIpc", {"method": method, "args": list(args), "expect": list(expect),
                      "expect_json": bool(expect_json)}, summary, inverse, backup_paths, 5.0)


def HyprctlReload(ctx: Any, config_only: bool = False, summary: str = "Reload Hyprland") -> Operation:
    operation_id = _next_id(ctx)
    inverse = _operation(ctx, "HyprctlReload", {"config_only": bool(config_only)}, "Reload after rollback", ())
    return Operation(operation_id, ctx.module_id, "HyprctlReload", {"config_only": bool(config_only)},
                     summary, inverse, (), 30.0, None)


def TimedConfirmation(ctx: Any, seconds: int, summary: str = "Confirm the change") -> Operation:
    operation_id = _next_id(ctx)
    inverse = _operation(ctx, "TimedConfirmation", {"seconds": int(seconds)}, "Confirm rollback", ())
    return Operation(operation_id, ctx.module_id, "TimedConfirmation", {"seconds": int(seconds)},
                     summary, inverse, (), 30.0, None)


def TerminalHandoff(ctx: Any, argv: Sequence[str], title: str, wrapped: bool = True,
                    summary: str = "Continue in terminal") -> Operation:
    return _operation(ctx, "TerminalHandoff", {"argv": list(argv), "title": title, "wrapped": bool(wrapped)},
                      summary, None, timeout_s=5.0)


def _required(params: dict[str, Any], *names: str) -> None:
    missing = [name for name in names if name not in params]
    if missing:
        raise CcError("unsupported_config", f"Operation parameters missing: {', '.join(missing)}")


def validate_operation(op: Operation, paths: Any, module_extra_paths: Iterable[str | Path] = ()) -> None:
    if op.kind not in _KINDS:
        raise CcError("unsupported_config", f"Unknown operation kind: {op.kind}", operation_id=op.id)
    if not re.fullmatch(rf"{re.escape(op.module_id)}\.\d{{4}}", op.id):
        raise CcError("unsupported_config", f"Invalid operation id: {op.id}")
    p = op.params
    if op.kind in _PATH_KINDS:
        _required(p, "path")
        if not paths.is_allowed_write(p["path"], module_extra_paths):
            raise CcError("permission_required", f"Path is outside writable roots or symlinked: {p['path']}",
                          {"path": p["path"]}, operation_id=op.id)
    for backup_path in op.backup_paths:
        if not paths.is_allowed_write(backup_path, module_extra_paths):
            raise CcError("permission_required", f"Backup path is outside writable roots or symlinked: {backup_path}",
                          {"path": backup_path}, operation_id=op.id)
    if op.kind == "WriteFileAtomic":
        _required(p, "content", "mode")
        if not isinstance(p["content"], (str, dict)) or (isinstance(p["content"], dict) and set(p["content"]) != {"base64"}):
            raise CcError("unsupported_config", "WriteFileAtomic content must be text or base64 bytes")
    elif op.kind == "ReplaceManagedBlock":
        if not ((p.get("name") and isinstance(p.get("version"), int)) or
                (isinstance(p.get("begin_marker"), str) and isinstance(p.get("end_marker"), str))):
            raise CcError("unsupported_config", "Managed block markers are incomplete")
        if p.get("body") is not None and not isinstance(p.get("body"), str):
            raise CcError("unsupported_config", "Managed block body must be text or null")
    elif op.kind == "EnsureDirectory":
        if not p.get("remove_if_empty"):
            _required(p, "mode")
    elif op.kind == "ReplaceDirectoryAtomic":
        _required(p, "staged_dir", "allow_existing")
        staged = p.get("staged_dir")
        if staged is not None:
            staging_root = (paths.state / "staging").absolute()
            staged_path = Path(staged).absolute()
            if not staged_path.is_relative_to(staging_root):
                raise CcError("permission_required", f"Staged directory is outside transaction staging: {staged}")
            if not paths.symlink_safe(staged_path):
                raise CcError("unsupported_config", f"Refusing symlinked staging path: {staged}")
    elif op.kind == "RunCommand":
        _required(p, "argv", "timeout_s", "expect_exit", "capture_limit", "wait_policy")
        _argv(p["argv"])
        if p["wait_policy"] not in {"exit", "detach"} or float(p["timeout_s"]) <= 0 or int(p["capture_limit"]) < 0:
            raise CcError("unsupported_config", "Invalid RunCommand policy or bounds")
    elif op.kind == "ShellIpc":
        _required(p, "method", "args", "expect", "expect_json")
        if not isinstance(p["method"], str) or not isinstance(p["args"], list):
            raise CcError("unsupported_config", "Invalid ShellIpc parameters")
    elif op.kind == "HyprctlReload":
        _required(p, "config_only")
    elif op.kind == "TimedConfirmation":
        if not isinstance(p.get("seconds"), int) or p["seconds"] <= 0:
            raise CcError("unsupported_config", "Confirmation seconds must be a positive integer")
    elif op.kind == "TerminalHandoff":
        argv = _argv(p.get("argv"))
        if any(_UNSAFE_TOKEN.search(token) for token in argv):
            raise CcError("unsupported_config", "Terminal handoff arguments may not contain whitespace or shell metacharacters")
        if not isinstance(p.get("title"), str) or not p["title"]:
            raise CcError("unsupported_config", "Terminal handoff title is required")
    for inverse in _inverse_items(op.inverse):
        validate_operation(inverse, paths, module_extra_paths)


def _argv(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value or any(not isinstance(x, str) or "\0" in x for x in value):
        raise CcError("unsupported_config", "argv must be a non-empty string array")
    return tuple(value)


def _inverse_items(value: Any) -> tuple[Operation, ...]:
    if isinstance(value, Operation):
        return (value,)
    return tuple(value) if isinstance(value, tuple) else ()


def _result(op: Operation, started: float, *, exit_code: int | None = None, stdout: str = "",
            stderr: str = "", timed_out: bool = False, digest: str | None = None) -> OperationResult:
    return OperationResult(op.id, exit_code, stdout, stderr, timed_out,
                           int((time.monotonic() - started) * 1000), digest)


def _content_bytes(content: Any) -> bytes:
    if isinstance(content, str):
        return content.encode()
    try:
        return base64.b64decode(content["base64"], validate=True)
    except Exception as error:
        raise CcError("unsupported_config", "Invalid base64 file content") from error


def _raw_marked_extract(data: bytes, begin: str, end: str) -> str | None:
    text = data.decode("utf-8")
    if begin not in text and end not in text:
        return None
    if text.count(begin) != 1 or text.count(end) != 1 or text.index(end) < text.index(begin):
        raise CcError("unsupported_config", "Managed block marker collision")
    start = text.index(begin) + len(begin)
    finish = text.index(end, start)
    return text[start:finish].strip("\r\n")


def _backup_bytes(exec_ctx: Any, path: str) -> bytes:
    manifest = exec_ctx.backups.read_manifest(exec_ctx.txid)
    found = next(((key, value) for key, value in manifest.items()
                  if value.get("path") == str(Path(path).absolute())), None)
    if found is None or not found[1].get("existed"):
        return b""
    return (exec_ctx.backups._dir(exec_ctx.txid) / found[0]).read_bytes()


def _raw_marked_replace(data: bytes, begin: str, end: str, body: str | None) -> bytes:
    text = data.decode("utf-8")
    begins, ends = text.count(begin), text.count(end)
    if begins != ends or begins > 1:
        raise CcError("unsupported_config", "Managed block marker collision")
    if begins == 0:
        if body is None:
            return data
        separator = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        return (text + separator + begin + "\n" + body.rstrip("\n") + "\n" + end + "\n").encode()
    start, finish = text.index(begin), text.index(end)
    if finish < start:
        raise CcError("unsupported_config", "Managed block markers are reversed")
    finish += len(end)
    if body is None:
        return (text[:start].rstrip("\n") + ("\n" if text[finish:].lstrip("\n") else "") + text[finish:].lstrip("\n")).encode()
    return (text[:start] + begin + "\n" + body.rstrip("\n") + "\n" + end + text[finish:]).encode()


def run_forward(op: Operation, exec_ctx: Any) -> OperationResult:
    started = time.monotonic()
    p = op.params
    if op.kind == "WriteFileAtomic":
        data = _content_bytes(p["content"])
        write_bytes_atomic(p["path"], data, int(p["mode"], 8) if p.get("mode") else None)
        return _result(op, started, digest=hashlib.sha256(data).hexdigest())
    if op.kind == "ReplaceManagedBlock":
        path = Path(p["path"])
        try:
            before = path.read_bytes()
        except FileNotFoundError:
            before = b""
        body = p.get("body")
        if p.get("body_from_backup"):
            original = _backup_bytes(exec_ctx, p["path"])
            body = (extract_block(original, p["name"], p["version"]) if p.get("name")
                    else _raw_marked_extract(original, p["begin_marker"], p["end_marker"]))
        if p.get("name"):
            prefix = "--" if path.suffix == ".lua" else "//"
            after = replace_block(before, p["name"], p["version"], body, prefix)
        else:
            after = _raw_marked_replace(before, p["begin_marker"], p["end_marker"], body)
        write_bytes_atomic(path, after, None)
        return _result(op, started, digest=hashlib.sha256(after).hexdigest())
    if op.kind == "EnsureDirectory":
        path = Path(p["path"])
        if p.get("remove_if_empty"):
            try:
                path.rmdir()
            except FileNotFoundError:
                pass
            return _result(op, started)
        created = not path.exists()
        mkdir_durable(path, int(p["mode"], 8))
        os.chmod(path, int(p["mode"], 8))
        return _result(op, started, stdout=json.dumps({"created": created}))
    if op.kind == "ReplaceDirectoryAtomic":
        replacement = replace_directory_atomic(p["path"], p["staged_dir"], p["allow_existing"])
        exec_ctx.cache.setdefault("directory_replacements", {})[op.id] = replacement
        details = {"previous": str(replacement.previous) if replacement.previous else None,
                   "installed": replacement.installed}
        return _result(op, started, stdout=json.dumps(details))
    if op.kind == "RunCommand":
        result = exec_ctx.commands.run(p["argv"], timeout_s=p["timeout_s"], env_extra=p.get("env_extra"),
                                       stdin=p.get("stdin"), capture_limit=p["capture_limit"],
                                       wait_policy=p.get("wait_policy", "exit"))
        if result.timed_out and p.get("wait_policy") != "detach":
            raise CcError("timeout", f"Command exceeded {p['timeout_s']:g} seconds", operation_id=op.id)
        if result.exit_code is not None and result.exit_code != p["expect_exit"]:
            raise CcError("unsupported_config", result.stderr.strip() or f"Command exited {result.exit_code}",
                          {"exitCode": result.exit_code}, operation_id=op.id)
        return OperationResult(op.id, result.exit_code, result.stdout, result.stderr, result.timed_out,
                               result.duration_ms, None)
    if op.kind == "RestoreBackup":
        exec_ctx.backups.restore(exec_ctx.txid, p["path"])
        return _result(op, started)
    if op.kind == "RemoveFile":
        remove_file(p["path"])
        return _result(op, started)
    if op.kind == "ShellIpc":
        value = exec_ctx.shell.call(p["method"], *p["args"], expect=tuple(p["expect"]), expect_json=p["expect_json"])
        return _result(op, started, exit_code=0, stdout=value.body)
    if op.kind == "HyprctlReload":
        baseline = exec_ctx.cache.get("hyprctl_configerrors_baseline", [])
        output = exec_ctx.hyprctl.reload(p["config_only"])
        new_errors = exec_ctx.hyprctl.configerrors_diff(baseline, exec_ctx.hyprctl.configerrors())
        if new_errors:
            raise CcError("verification_failed", "Hyprland reported new configuration errors", {"errors": new_errors})
        return _result(op, started, exit_code=0, stdout=output)
    if op.kind == "TimedConfirmation":
        return _result(op, started)
    if op.kind == "TerminalHandoff":
        argv = list(p["argv"])
        if p["wrapped"]:
            wrapper = Path(exec_ctx.ccctl_path).parent / "cc-handoff"
            argv = ["omarchy-launch-floating-terminal-with-presentation", str(wrapper), exec_ctx.txid, *argv]
        launched = exec_ctx.commands.run(argv, timeout_s=5, capture_limit=0, wait_policy="detach")
        if launched.exit_code not in {None, 0}:
            raise CcError("handoff_failed", f"Terminal launcher exited {launched.exit_code}",
                          {"exitCode": launched.exit_code})
        return _result(op, started, exit_code=launched.exit_code)
    raise CcError("unsupported_config", f"Unknown operation kind: {op.kind}")


def build_inverse(op: Operation, exec_ctx: Any, result: OperationResult | None = None) -> tuple[Operation, ...]:
    if op.kind == "EnsureDirectory":
        if result and json.loads(result.stdout_head or "{}").get("created"):
            params = {"path": op.params["path"], "remove_if_empty": True}
            return (Operation(op.id + ".inverse", op.module_id, "EnsureDirectory", params, "Remove created directory", (), (), 30),)
        return ()
    if op.kind == "ReplaceDirectoryAtomic":
        explicit = tuple(_inverse_items(op.inverse))
        if explicit:
            return explicit
        details = json.loads(result.stdout_head or "{}") if result else {}
        previous = details.get("previous")
        if previous or details.get("installed"):
            params = {"path": op.params["path"], "staged_dir": previous, "allow_existing": True}
            inverse = Operation(op.id + ".inverse", op.module_id, "ReplaceDirectoryAtomic", params,
                                "Restore directory", (), (), 30)
            return (inverse,)
        return ()
    return _inverse_items(op.inverse)


__all__ = sorted(_KINDS) + ["validate_operation", "run_forward", "build_inverse"]
