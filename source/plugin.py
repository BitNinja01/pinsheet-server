from __future__ import annotations

import logging

_log = logging.getLogger("pinsheet")

_plugins: list = []


def fire_hook(name: str, **kwargs) -> None:
    for plugin in _plugins:
        fn = getattr(plugin, name, None)
        if fn is None:
            continue
        try:
            fn(**kwargs)
        except Exception as exc:
            pi = getattr(plugin, "plugin_info", None)
            plugin_name = pi.get("name", "?") if isinstance(pi, dict) else "?"
            _log.warning("plugin %s: %s() failed — %s", plugin_name, name, exc)
