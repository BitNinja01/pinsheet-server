import sys
from pathlib import Path

import pytest

from database import set_db_path, init_db


@pytest.fixture
def loader_env(tmp_path, monkeypatch):
    """Real DB + a temp plugins dir containing a plugin whose folder name
    differs from its plugin_info['name'] (like plugins/pinsheet-cartographer)."""
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
    mismatched = plugins_dir / "mismatched_folder"
    mismatched.mkdir(parents=True)
    (mismatched / "__init__.py").write_text(
        'plugin_info = {"name": "mismatched_name", "version": "1.0.0"}\n'
        "def register(app):\n"
        '    app.config["plugins.mismatched"] = "loaded"\n'
    )
    monkeypatch.setattr("source.plugin_loader._plugins_dir", lambda: plugins_dir)

    app = main_mod.app
    app._discovered_plugins = []
    app._plugin_states_at_startup = {}
    app.config["DB_PATH"] = Path(db_path)

    from source import plugin
    plugin._plugins.clear()
    return app


class TestPluginsDir:
    def test_returns_repo_level_plugins_when_not_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        from source.plugin_loader import _plugins_dir
        result = _plugins_dir()
        expected = Path(__file__).parent.parent / "plugins"
        assert result == expected

    def test_returns_executable_level_plugins_when_frozen(self, monkeypatch, tmp_path):
        exe_path = tmp_path / "dist" / "pinsheet"
        exe_path.parent.mkdir()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(exe_path))
        from source.plugin_loader import _plugins_dir
        result = _plugins_dir()
        expected = exe_path.parent / "plugins"
        assert result == expected


class TestLoadPluginErrors:
    def test_missing_plugin_info_is_skipped(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "plugins"
        from source.plugin_loader import _load_plugin
        result = _load_plugin(fixture_dir / "broken_no_info")
        assert result is None

    def test_broken_register_module_is_loaded(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "plugins"
        from source.plugin_loader import _load_plugin
        result = _load_plugin(fixture_dir / "broken_bad_register")
        assert result is not None
        assert result.plugin_info["name"] == "bad_register"

    def test_no_register_function_is_skipped(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "plugins"
        from source.plugin_loader import _load_plugin
        result = _load_plugin(fixture_dir / "no_register")
        assert result is None

    def test_syntax_error_plugin_is_skipped(self, monkeypatch, tmp_path):
        plugin_dir = tmp_path / "plugins" / "broken_syntax"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "__init__.py").write_text("this is not valid python @@@")
        monkeypatch.setattr("source.plugin_loader._plugins_dir", lambda: tmp_path / "plugins")
        from source.plugin_loader import _load_plugin
        result = _load_plugin(plugin_dir)
        assert result is None


class TestFolderNameStateKeying:
    def test_discovered_entries_carry_folder_name(self, loader_env):
        import source.plugin_loader
        source.plugin_loader.discover_plugins(loader_env)

        entries = [
            p for p in loader_env._discovered_plugins
            if p.plugin_info["name"] == "mismatched_name"
        ]
        assert len(entries) == 1
        assert entries[0].folder_name == "mismatched_folder"

    def test_state_seeded_and_gated_under_folder_name(self, loader_env):
        from source import plugin
        import source.plugin_loader
        from source.store import get_plugin_states, set_plugin_state

        source.plugin_loader.discover_plugins(loader_env)

        states = get_plugin_states()
        assert states.get("mismatched_folder") is False
        assert "mismatched_name" not in states
        assert "mismatched_name" not in [p.plugin_info["name"] for p in plugin._plugins]

        # enabling under plugin_info["name"] (the old buggy key) must not load it
        set_plugin_state("mismatched_name", True)
        source.plugin_loader.discover_plugins(loader_env)
        assert "mismatched_name" not in [p.plugin_info["name"] for p in plugin._plugins]

        # enabling under the folder name must load it
        set_plugin_state("mismatched_folder", True)
        source.plugin_loader.discover_plugins(loader_env)
        assert "mismatched_name" in [p.plugin_info["name"] for p in plugin._plugins]
