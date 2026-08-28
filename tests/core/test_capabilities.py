from datetime import datetime, timedelta, timezone

from customization_center.core import (Capabilities, Capability, CapabilityCache, CommandRunner, Paths, ShellIpc,
                                       probe_command, standard_capabilities)


def test_probe_and_cache_ttl(stub_command, fake_shell):
    stub_command("luac", {"exit_code": 0})
    runner = CommandRunner()
    capability = probe_command(runner, "luac", readonly_check=True)
    assert capability.available and capability.argv_prefix == ("luac",)
    paths = Paths.from_env(); cache = CapabilityCache(paths)
    now = datetime.now(timezone.utc)
    caps = Capabilities("menu", (capability,), now.isoformat())
    cache.save(caps)
    assert cache.load("menu", now) == caps
    assert cache.load("menu", now + timedelta(seconds=61)) is None


def test_standard_names(stub_command, fake_shell):
    for name in ("hyprctl", "luac", "bash", "systemd-run", "omarchy-launch-floating-terminal-with-presentation"):
        stub_command(name, {"exit_code": 0})
    caps = standard_capabilities("menu", CommandRunner(), ShellIpc(CommandRunner()))
    assert {item.name for item in caps.items} == {"shell_ipc", "hyprctl", "luac", "bash_syntax", "timed_confirmation", "terminal_launcher"}
