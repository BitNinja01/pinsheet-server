from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

_log = logging.getLogger("pinsheet")


def _plugins_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "plugins"
    return Path(__file__).parent.parent / "plugins"


def _wire_template_path(app: "Flask", plugin_name: str, plugin_path: Path) -> None:
    templates_dir = plugin_path / "templates"
    if not templates_dir.exists():
        return
    search_path = getattr(app.jinja_loader, "searchpath", None)
    if search_path is not None:
        search_path.append(str(templates_dir))
        _log.info("plugin %s: template path added", plugin_name)


def _wire_static_route(app: "Flask", plugin_name: str, plugin_path: Path) -> None:
    from flask import send_from_directory

    static_dir = plugin_path / "static"
    if not static_dir.exists():
        return

    route = f"/plugins/{plugin_name}/static/<path:filename>"
    endpoint = f"_plugin_{plugin_name}_static"

    if endpoint in app.view_functions:
        _log.warning("plugin %s: static route collision — %s already registered", plugin_name, route)
        return

    @app.route(route, endpoint=endpoint)
    def _serve(filename):
        return send_from_directory(static_dir, filename)

    _log.info("plugin %s: static route registered at %s", plugin_name, route)


def _load_plugin(plugin_dir: Path) -> "object | None":
    folder_name = plugin_dir.name

    plugins_parent = str(plugin_dir.parent)
    if plugins_parent not in sys.path:
        sys.path.insert(0, plugins_parent)

    try:
        mod = importlib.import_module(folder_name)
    except Exception as exc:
        _log.warning("plugin %s: import failed — %s", folder_name, exc)
        return None

    plugin_info = getattr(mod, "plugin_info", None)
    if not isinstance(plugin_info, dict):
        _log.warning("plugin %s: plugin_info missing or not a dict — skipping", folder_name)
        return None
    if not plugin_info.get("name") or not plugin_info.get("version"):
        _log.warning("plugin %s: plugin_info missing required 'name' or 'version' — skipping", folder_name)
        return None
    if plugin_info["name"] != folder_name:
        _log.warning(
            "plugin %s: plugin_info['name'] is '%s', expected '%s' — loading anyway",
            folder_name, plugin_info["name"], folder_name,
        )

    if not hasattr(mod, "register"):
        _log.warning("plugin %s: no register() function — skipping", folder_name)
        return None

    return mod


def discover_plugins(app: "Flask") -> None:
    plugins_dir = _plugins_dir()
    if not plugins_dir.exists():
        _log.info("plugins/ directory not found — skipping plugin discovery")
        return

    from source.plugin import _plugins

    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir() or not (entry / "__init__.py").exists():
            continue

        mod = _load_plugin(entry)
        if mod is None:
            continue

        _wire_template_path(app, mod.plugin_info["name"], entry)
        _wire_static_route(app, mod.plugin_info["name"], entry)

        try:
            mod.register(app)
        except Exception as exc:
            _log.warning("plugin %s: register() failed — %s", mod.plugin_info["name"], exc)
            continue

        if mod not in _plugins:
            _plugins.append(mod)
            _log.info("plugin loaded: %s v%s", mod.plugin_info["name"], mod.plugin_info["version"])
