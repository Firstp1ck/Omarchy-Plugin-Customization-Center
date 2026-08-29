from types import SimpleNamespace

from customization_center.core import Operation, Plan, Status
from modules.defaults.backend.verify import verify_plan


def handoff_plan(previous="foot"):
    operation = Operation("defaults.0001", "defaults", "TerminalHandoff", {"argv": ["omarchy-default-terminal", "kitty"]}, "install", None, (), 5,
                          {"category": "terminal", "choice": "kitty", "previous": previous})
    return Plan("defaults", "r", (operation,), (), "install", (), (operation.id,))


def test_handoff_remains_pending_until_target_is_runnable():
    status = Status("defaults", "r", {"categories": [{"id": "terminal", "current": {"choice": "foot"}, "checks": [], "choices": [{"id": "kitty", "runnable": False, "state": "missing"}]}]}, (), 1)
    assert verify_plan(None, handoff_plan(), status, {}).state == "pending"


def test_handoff_detects_installed_not_set():
    status = Status("defaults", "r", {"categories": [{"id": "terminal", "current": {"choice": "foot"}, "checks": [], "choices": [{"id": "kitty", "runnable": True, "state": "available"}]}]}, (), 1)
    result = verify_plan(None, handoff_plan(), status, {})
    assert result.state == "fail" and result.code == "defaults_installed_not_set"
