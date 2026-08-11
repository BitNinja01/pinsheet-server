from __future__ import annotations

import logging

_log = logging.getLogger("pinsheet")

_plugins: list = []

# T5 / VULN-06 mitigation: fire_hook only dispatches names in this fixed
# allowlist. Without this, `getattr(plugin, name, None)` would invoke ANY
# attribute matching an arbitrary hook name, which is incidental attack
# surface amplification on top of the plugin-load trust boundary (T1/T2).
# Add new hook names here — and only here — when the core adds a new
# lifecycle hook call site.
ALLOWED_HOOKS = frozenset({
    "on_round_saved",
    "on_course_saved",
})


def fire_hook(name: str, **kwargs) -> None:
    if name not in ALLOWED_HOOKS:
        _log.warning("fire_hook: rejected non-allowlisted hook name %r", name)
        return
    for plugin in _plugins:
        fn = getattr(plugin, name, None)
        if fn is None or not callable(fn):
            continue
        try:
            fn(**kwargs)
        except Exception as exc:
            pi = getattr(plugin, "plugin_info", None)
            plugin_name = pi.get("name", "?") if isinstance(pi, dict) else "?"
            _log.warning("plugin %s: %s() failed — %s", plugin_name, name, exc)
