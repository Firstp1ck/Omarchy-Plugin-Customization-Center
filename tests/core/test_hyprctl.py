import json

import pytest

from customization_center.core import CcError, CommandRunner, Hyprctl


def test_hyprctl_adapters_and_diff(stub_command):
    def hypr(req):
        if req["argv"][1:3] == ["-j", "configerrors"]:
            return {"stdout": json.dumps([{"message": "new"}])}
        return {"stdout": "ok\n"}
    stub_command("hyprctl", hypr)
    hyprctl = Hyprctl(CommandRunner())
    assert hyprctl.configerrors() == [{"message": "new"}]
    assert hyprctl.reload() == "ok\n"
    assert hyprctl.configerrors_diff([], [{"message": "new"}]) == [{"message": "new"}]


def test_reload_guard_refusal(stub_command):
    stub_command("hyprctl", {"stdout": "ok"})
    stub_command("omarchy-hyprland-reload-guard", {"stdout": "paused\n"})
    with pytest.raises(CcError): Hyprctl(CommandRunner()).reload(config_only=True)
