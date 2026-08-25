from __future__ import annotations

import ast
import importlib
import logging
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING

from source.store import seed_plugin_state, get_plugin_states

if TYPE_CHECKING:
    from flask import Flask

_log = logging.getLogger("pinsheet")


def _plugins_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "plugins"
    return Path(__file__).parent.parent / "plugins"


def _read_plugin_info_static(plugin_dir: Path) -> "dict | None":
    """Read the `plugin_info` dict from a plugin's __init__.py via AST
    parsing — this NEVER executes the plugin's code.

    Security rationale (VULN-01/VULN-02, T1): the loader must be able to
    list a *disabled* (or not-yet-enabled) plugin's identity (name/version/
    description) for the admin UI without importing it — import is the
    trust boundary crossing (arbitrary code execution) and must only ever
    happen for plugins the owner has explicitly enabled.
    """
    init_path = plugin_dir / "__init__.py"
    try:
        source = init_path.read_text()
        tree = ast.parse(source, filename=str(init_path))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "plugin_info" for t in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return None
        return value if isinstance(value, dict) else None
    return None


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

    static_dir_resolved = static_dir.resolve()
    route = f"/plugins/{plugin_name}/static/<path:filename>"
    endpoint = f"_plugin_{plugin_name}_static"

    if endpoint in app.view_functions:
        _log.warning("plugin %s: static route collision — %s already registered", plugin_name, route)
        return

    @app.route(route, endpoint=endpoint)
    def _serve(filename):
        # T3 hardening (ADR-04): send_from_directory() already relies on
        # Werkzeug's safe_join (blocks `../` traversal — pinned via
        # werkzeug>=3.0 in requirements.txt/pyproject.toml). safe_join does
        # NOT cover a symlink inside static_dir that points outside of it,
        # so add an explicit realpath-containment assertion as defense in
        # depth before ever touching the filesystem.
        candidate = (static_dir / filename).resolve()
        try:
            candidate.relative_to(static_dir_resolved)
        except ValueError:
            _log.warning("plugin %s: rejected out-of-tree static path %r", plugin_name, filename)
            from flask import abort
            abort(404)
        return send_from_directory(static_dir, filename)

    _log.info("plugin %s: static route registered at %s", plugin_name, route)


def _load_plugin(plugin_dir: Path) -> "object | None":
    """Import a plugin module and validate its contract.

    SECURITY: the caller MUST only invoke this for plugins that are already
    confirmed enabled in `plugin_states`. Import executes arbitrary
    top-level code in the plugin's __init__.py (VULN-02 / T1) — there must
    be no path from "plugin exists on disk" to this function running
    without an explicit owner enable-decision in between.
    """
    folder_name = plugin_dir.name

    # VULN-02 sub-vector (module shadowing): use append, NOT insert(0). A
    # plugin folder named like a stdlib/source module (e.g. `os`, `store`)
    # must NOT be able to shadow the real module by taking priority on
    # sys.path — appending keeps real modules ahead of plugin dirs.
    plugins_parent = str(plugin_dir.parent)
    if plugins_parent not in sys.path:
        sys.path.append(plugins_parent)

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
    """Discover plugins under plugins/ and load the enabled ones.

    Hardened ordering (ADR-01, closes VULN-01/VULN-02 — "disabled" was not
    previously a security boundary):

        for each plugin directory:
            1. read plugin_info STATICALLY (AST, no import) for admin listing
            2. seed/read its enable-state (new plugins seed DISABLED —
               provenance gate: an admin must validate + enable before any
               code runs; default-deny if no state row exists)
            3. if NOT enabled: stop here. Zero code executes. No import,
               no dependency install, no template wiring, no static route.
            4. only if enabled: import, wire templates/static, register()

    Automatic `pip install -r requirements.txt` has been REMOVED entirely
    (ADR-02 / VULN-01, T2 — unpinned, unverified pip install was a Critical
    supply-chain RCE vector that ran even for disabled plugins). Installing
    a plugin's dependencies is now an explicit, out-of-band owner action:

        pip install -r plugins/<name>/requirements.txt
    """
    plugins_dir = _plugins_dir()
    if not plugins_dir.exists():
        _log.info("plugins/ directory not found — skipping plugin discovery")
        return

    from source.plugin import _plugins

    plugin_states = get_plugin_states()

    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir() or not (entry / "__init__.py").exists():
            continue

        folder_name = entry.name

        # Static, import-free metadata read — safe to do for every plugin
        # directory regardless of enable-state (used for admin listing).
        static_info = _read_plugin_info_static(entry)

        # plugin_states/enable-gate is keyed by the folder name: the on-disk
        # directory is the stable identity the admin vouches for when enabling.
        # plugin_info["name"] is display metadata and may differ from the
        # folder name (e.g. cartographer), so it must not gate loading.
        seed_plugin_state(folder_name)
        app._discovered_plugins.append(
            types.SimpleNamespace(
                plugin_info=static_info or {"name": folder_name, "version": "?"},
                folder_name=folder_name,
            )
        )

        # Default-DENY: if a plugin has no explicit enabled row, treat it as
        # disabled. Combined with seed_plugin_state defaulting new rows to
        # enabled=0, a freshly dropped-in plugin never executes until an admin
        # enables it (provenance gate — admin validates before first run).
        if not plugin_states.get(folder_name, False):
            _log.info("plugin %s: not enabled — skipping import, dependency install, and wiring", folder_name)
            continue

        mod = _load_plugin(entry)  # import happens ONLY for enabled plugins
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

    app._plugin_states_at_startup = get_plugin_states()
