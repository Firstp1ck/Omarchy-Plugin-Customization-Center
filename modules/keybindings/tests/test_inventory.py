from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import CommandResult, Paths

HERE = Path(__file__).parent / "fixtures"


def test_plain_and_json_inventory(keybindings_backend):
    inventory = __import__("cc_modules.keybindings.inventory", fromlist=["inventory"])
    records, warnings = inventory.parse_plain((HERE / "binds/plain-0.56.2-lua.txt").read_text())
    assert not warnings
    assert len(records) == 3
    assert records[2]["keyToken"] == "code:94"
    records, warning = inventory.reconcile_json(records, (HERE / "binds/json-0.56.2.json").read_text())
    assert warning is None
    assert records[1]["flags"]["locked"] and records[1]["flags"]["repeating"]


@pytest.mark.parametrize("payload", ["[]", "null", '"devices"', "1", "true"])
def test_non_object_devices_output_is_invalid(keybindings_backend, payload):
    inventory = __import__("cc_modules.keybindings.inventory", fromlist=["inventory"])
    assert inventory.parse_devices(payload) == {
        "keyboard": None, "layouts": [], "multipleLayouts": False, "switches": [],
        "warning": "devices output is invalid",
    }


def test_comma_separated_and_disagreeing_layouts(keybindings_backend):
    inventory = __import__("cc_modules.keybindings.inventory", fromlist=["inventory"])
    comma = inventory.parse_devices('{"keyboards":[{"main":true,"layout":"us,ch","variant":",de","options":""}],"switches":[]}')
    disagree = inventory.parse_devices('{"keyboards":[{"main":true,"layout":"us","variant":"","options":""},{"layout":"ch","variant":"de","options":""}],"switches":[]}')
    assert comma["multipleLayouts"] is True
    assert disagree["multipleLayouts"] is True


def test_status_probes_resolve_binds_by_sym_and_publishes_layout_state(keybindings_backend, tmp_path):
    planner = __import__("cc_modules.keybindings.planner", fromlist=["planner"])
    home=tmp_path/"home"; config=home/".config"; (config/"hypr").mkdir(parents=True); (config/"hypr/bindings.lua").write_text("-- user\n")
    paths=Paths(home,config,tmp_path/"state",tmp_path/"cache",tmp_path/"runtime",tmp_path/"omarchy")
    class Commands:
        def which(self,name): return "/stub/hyprctl" if name=="hyprctl" else None
        def run(self,argv,**kwargs):
            values={
                ("hyprctl","binds"):"",
                ("hyprctl","-j","binds"):"[]",
                ("hyprctl","-j","devices"):'{"keyboards":[{"main":true,"layout":"us,ch","variant":",de","options":""}],"switches":[]}',
                ("hyprctl","version"):"Hyprland 0.56.2\n",
                ("hyprctl","-j","getoption","input.resolve_binds_by_sym"):'{"int":1}' }
            return CommandResult(tuple(argv),0,values.get(tuple(argv),"{}"),"",False,1,False)
    status=planner.build_status(SimpleNamespace(paths=paths,commands=Commands()),{"hyprctl":{"available":True,"version":"","reason":""}})
    assert status.data["capabilities"]["keymap"]["multipleLayouts"] is True
    assert status.data["capabilities"]["keymap"]["resolveBindsBySym"] is True
    assert status.data["keymapContext"]["multipleLayouts"] is True
    assert status.data["keymapContext"]["resolveBindsBySym"] is True


def test_legacy_keycode(keybindings_backend):
    inventory = __import__("cc_modules.keybindings.inventory", fromlist=["inventory"])
    records, _ = inventory.parse_plain((HERE / "binds/plain-legacy-keycode.txt").read_text())
    assert records[0]["keyToken"] == "code:49"
