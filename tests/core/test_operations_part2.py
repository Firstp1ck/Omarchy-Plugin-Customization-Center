from __future__ import annotations

from types import SimpleNamespace

import pytest

from customization_center.core import ops
from customization_center.core.errors import CcError
from customization_center.core.paths import Paths


def context(paths):
    return SimpleNamespace(module_id="test", cache={}, paths=paths)


def test_builders_are_sequential_and_validate(isolated_home):
    paths = Paths.from_env()
    ctx = context(paths)
    first = ops.WriteFileAtomic(ctx, paths.module_config("test") / "one.json", "{}\n", "0600")
    second = ops.RunCommand(ctx, ["true"], 1, "Run true", inverse=["true"])
    assert first.id == "test.0001"
    assert second.id == "test.0003"
    ops.validate_operation(first, paths)
    ops.validate_operation(second, paths)


def test_handoff_rejects_shell_tokens(isolated_home):
    paths = Paths.from_env()
    operation = ops.TerminalHandoff(context(paths), ["echo", "two words"], "Unsafe")
    with pytest.raises(CcError):
        ops.validate_operation(operation, paths)
