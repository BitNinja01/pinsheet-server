import sys
from pathlib import Path


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
