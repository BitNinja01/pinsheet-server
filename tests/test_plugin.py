import types
from pathlib import Path

import pytest

from source.database import set_db_path, init_db


@pytest.fixture
def plugin_app(tmp_path, monkeypatch):
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

    app = main_mod.app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["DB_PATH"] = Path(db_path)
    app.config["DATA_DIR"] = data_dir

    fixture_dir = Path(__file__).parent / "fixtures" / "plugins"
    monkeypatch.setattr("source.plugin_loader._plugins_dir", lambda: fixture_dir)

    return app


@pytest.fixture
def plugin_client(plugin_app):
    return plugin_app.test_client()


class TestPluginDiscovery:
    def test_plugins_discover_called_before_first_request(
        self, plugin_app, monkeypatch
    ):
        from source import plugin
        plugin._plugins.clear()

        import source.plugin_loader
        source.plugin_loader.discover_plugins(plugin_app)

        names = [p.plugin_info["name"] for p in plugin._plugins]
        assert "minimal" in names
        assert "with_everything" in names
        assert "broken_no_info" not in names
        assert "broken_bad_register" not in names
        assert "no_register" not in names

    def test_plugin_register_called_and_config_set(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        import source.plugin_loader
        source.plugin_loader.discover_plugins(plugin_app)

        assert plugin_app.config.get("plugins.minimal") == "loaded"
        assert plugin_app.config.get("plugins.with_everything") == "loaded"

    def test_inject_plugin_info_into_context(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        import source.plugin_loader
        source.plugin_loader.discover_plugins(plugin_app)

        assert "plugin_info" in plugin_app.jinja_env.globals

    def test_static_route_registered(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        import source.plugin_loader
        source.plugin_loader.discover_plugins(plugin_app)

        endpoint = "_plugin_with_everything_static"
        assert endpoint in plugin_app.view_functions

    def test_template_path_added(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        import source.plugin_loader
        source.plugin_loader.discover_plugins(plugin_app)

        searchpath = plugin_app.jinja_loader.searchpath
        with_everything_templates = Path(__file__).parent / "fixtures" / "plugins" / "with_everything" / "templates"
        assert str(with_everything_templates) in searchpath


class TestFireHook:
    def test_fire_hook_calls_plugin_function(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        import source.plugin_loader
        source.plugin_loader.discover_plugins(plugin_app)

        mod = types.ModuleType("test_hook_plugin")
        mod.plugin_info = {"name": "test_hook", "version": "1.0.0"}
        calls = []

        def on_round_saved(round_data, user_id, db_path):
            calls.append((round_data, user_id, str(db_path)))

        mod.on_round_saved = on_round_saved
        plugin._plugins.append(mod)

        plugin.fire_hook(
            "on_round_saved",
            round_data={"date": "2026-01-01"},
            user_id=1,
            db_path=plugin_app.config["DB_PATH"],
        )

        assert len(calls) == 1
        assert calls[0][0] == {"date": "2026-01-01"}
        assert calls[0][1] == 1

    def test_fire_hook_isolates_errors(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        mod = types.ModuleType("error_plugin")
        mod.plugin_info = {"name": "error_plugin", "version": "1.0.0"}

        def bad_hook(**kwargs):
            raise RuntimeError("boom")

        mod.on_round_saved = bad_hook
        plugin._plugins.append(mod)

        plugin.fire_hook("on_round_saved", round_data={}, user_id=1, db_path=Path("/fake/path"))
        assert "error_plugin" in [p.plugin_info["name"] for p in plugin._plugins]

    def test_fire_hook_skips_missing_function(self, plugin_app, monkeypatch):
        from source import plugin
        plugin._plugins.clear()

        mod = types.ModuleType("no_hook_plugin")
        mod.plugin_info = {"name": "no_hook", "version": "1.0.0"}
        plugin._plugins.append(mod)

        plugin.fire_hook("on_round_saved", round_data={}, user_id=1, db_path=Path("/fake/path"))
