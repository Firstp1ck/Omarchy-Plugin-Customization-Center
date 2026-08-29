from . import bar, defaults, keybindings, monitors, plugins, themes

ORDER = (monitors, themes, plugins, bar, keybindings, defaults)
BY_ID = {member.module_id: member for member in ORDER}

__all__ = ["ORDER", "BY_ID"]
