from __future__ import annotations

from customization_center.core import Status


def test_verify_configured_and_active(bar_backend):
    data = {"shell": {"available": True, "configuredBarId": "omarchy.bar", "activeBarId": "omarchy.bar"},
            "file": {"matchesShell": True}, "bar": {"id": None, "position": "top", "transparent": False,
            "centerAnchor": "", "extra": {}, "layout": {"left": [], "center": [], "right": []}},
            "rawShellConfig": {"bar": {"centerAnchor": ""}}}
    status = Status("bar", "after", data, (), 1)
    plan = type("Plan", (), {"operations": [type("Op", (), {"detail": {"expected": {"bar": {"position": "top", "transparent": False, "centerAnchor": "", "layout": {"left": [], "center": [], "right": []}}}}})()]})()
    result = bar_backend.MODULE.verify(None, plan, status, {})
    assert result.state == "pass"
    data["shell"]["activeBarId"] = "local.fallback"
    assert bar_backend.MODULE.verify(None, plan, status, {}).code == "bar_shell_fallback"
