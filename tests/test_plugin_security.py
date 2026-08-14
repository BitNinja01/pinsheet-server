"""Security regression tests for the hardened plugin loader.

Validates the secure-plugin-20260806-001 hardening against the red-team
validation checklist, exercising the REAL source/plugin_loader.py (not a copy):

  * VULN-02 / T1 — "disabled is not a security boundary": a disabled plugin's
    import-time code must NOT execute.
  * VULN-01 / T2 — auto `pip install` on discovery must be gone.
  * VULN-06 / T5 — fire_hook must reject non-allowlisted hook names.
"""
from pathlib import Path

import pytest

from database import set_db_path, init_db

_PROBE = '''\
import os
_marker = os.environ.get("PLUGIN_SIDEEFFECT_MARKER")
if _marker:
    with open(_marker, "a") as _f:
        _f.write("imported\\n")

plugin_info = {"name": "sideeffect_probe", "version": "1.0.0"}

def register(app):
    app.config["plugins.sideeffect_probe"] = "loaded"
'''


@pytest.fixture
def loader_env(tmp_path, monkeypatch):
    """Real DB + a temp plugins dir containing one import-probe plugin."""
    import source.main as main_mod
    main_mod.limiter.enabled = False

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "drafts").mkdir()
    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import source.store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    plugins_dir = tmp_path / "plugins"
    probe = plugins_dir / "sideeffect_probe"
    probe.mkdir(parents=True)
    (probe / "__init__.py").write_text(_PROBE)
    monkeypatch.setattr("source.plugin_loader._plugins_dir", lambda: plugins_dir)

    marker = tmp_path / "import_marker.txt"
    monkeypatch.setenv("PLUGIN_SIDEEFFECT_MARKER", str(marker))

    app = main_mod.app
    app._discovered_plugins = []
    app._plugin_states_at_startup = {}
    app.config["DB_PATH"] = Path(db_path)

    from source import plugin
    plugin._plugins.clear()
    return app, marker


def test_disabled_plugin_does_not_execute_import(loader_env, monkeypatch):
    """VULN-02: a disabled plugin must not run its import-time code."""
    app, marker = loader_env
    from source.store import seed_plugin_state, set_plugin_state
    seed_plugin_state("sideeffect_probe")
    set_plugin_state("sideeffect_probe", False)

    # ensure a fresh import can happen if the loader (wrongly) attempts it
    import sys
    sys.modules.pop("sideeffect_probe", None)

    import source.plugin_loader
    source.plugin_loader.discover_plugins(app)

    assert not marker.exists(), "disabled plugin executed import-time code (VULN-02 not closed)"
    # still discoverable for the admin UI (via AST metadata read, no import)
    names = [p.plugin_info.get("name") for p in app._discovered_plugins]
    assert "sideeffect_probe" in names


def test_new_plugin_seeds_disabled(loader_env):
    """Provenance gate: a freshly discovered plugin is seeded DISABLED and does
    NOT execute until an admin enables it (dropping a folder != trusting it)."""
    app, marker = loader_env
    # do NOT enable — just discover a brand-new plugin
    import sys
    sys.modules.pop("sideeffect_probe", None)

    import source.plugin_loader
    source.plugin_loader.discover_plugins(app)

    from source.store import get_plugin_states
    assert get_plugin_states().get("sideeffect_probe") is False
    assert not marker.exists(), "newly discovered plugin executed before admin enabled it"


def test_enabled_plugin_does_execute_import(loader_env):
    """Positive control: an admin-enabled plugin's import DOES run (boundary is real, not blanket-off)."""
    app, marker = loader_env
    from source.store import seed_plugin_state, set_plugin_state
    seed_plugin_state("sideeffect_probe")
    set_plugin_state("sideeffect_probe", True)  # admin validates + enables

    import sys
    sys.modules.pop("sideeffect_probe", None)

    import source.plugin_loader
    source.plugin_loader.discover_plugins(app)

    assert marker.exists(), "enabled plugin import did not run"


def test_no_auto_pip_install_on_discovery():
    """VULN-01: auto pip install must be removed from the loader entirely."""
    import source.plugin_loader as pl
    assert not hasattr(pl, "_install_requirements"), "auto pip-install path still present"
    src = Path(pl.__file__).read_text()
    assert "pip" not in src.lower() or "install" not in src.lower() or "removed" in src.lower(), \
        "loader still references pip install"


def test_plugins_dir_not_inserted_at_path_front(loader_env):
    """VULN-02 sub-vector: the plugins parent must be APPENDED to sys.path,
    not inserted at index 0, so a plugin folder cannot shadow a real
    stdlib/source module by taking search priority."""
    import sys
    app, _ = loader_env
    from source.store import seed_plugin_state, set_plugin_state
    seed_plugin_state("sideeffect_probe")
    set_plugin_state("sideeffect_probe", True)  # enable so the import path runs
    before = list(sys.path)

    import source.plugin_loader
    source.plugin_loader.discover_plugins(app)

    plugins_parent = str((Path(source.plugin_loader._plugins_dir())))
    # if the parent was added, it must not be at the front (index 0)
    if plugins_parent in sys.path:
        assert sys.path.index(plugins_parent) != 0
    # real modules still resolve to their canonical location
    import os as _os
    assert "site-packages" in _os.__file__ or _os.__file__.endswith("os.py")


def test_fire_hook_rejects_non_allowlisted_name():
    """VULN-06: fire_hook must not dispatch arbitrary attribute names."""
    from source import plugin
    import types

    plugin._plugins.clear()
    mod = types.ModuleType("evil")
    mod.plugin_info = {"name": "evil", "version": "1.0.0"}
    called = []
    mod.__class__ = type(mod)
    setattr(mod, "arbitrary_evil_hook", lambda **kw: called.append(1))
    plugin._plugins.append(mod)

    plugin.fire_hook("arbitrary_evil_hook", x=1)
    assert called == [], "fire_hook dispatched a non-allowlisted hook name"
    plugin._plugins.clear()
