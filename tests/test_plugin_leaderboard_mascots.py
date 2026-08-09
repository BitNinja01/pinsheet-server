"""Tests for the bundled leaderboard_mascots plugin.

The plugin is pure client-side: register() only appends a stylesheet link and a
script tag to the core head/foot template blocks, and its static assets are
served by the loader. These tests exercise the Python contract; the DOM
behaviour of mascot.js is covered separately.
"""
import types
from pathlib import Path

import pytest

from source.plugin_loader import _load_plugin

PLUGIN_DIR = Path(__file__).parent.parent / "plugins" / "leaderboard_mascots"


def _fake_app(head="", foot=""):
    app = types.SimpleNamespace()
    app._plugin_blocks = {}
    if head:
        app._plugin_blocks["head"] = head
    if foot:
        app._plugin_blocks["foot"] = foot
    return app


class TestPluginMetadata:
    def test_loads_with_valid_plugin_info(self):
        mod = _load_plugin(PLUGIN_DIR)
        assert mod is not None
        assert mod.plugin_info["name"] == "leaderboard_mascots"
        assert mod.plugin_info["version"]

    def test_static_assets_exist(self):
        assert (PLUGIN_DIR / "static" / "mascot.js").is_file()
        assert (PLUGIN_DIR / "static" / "mascot.css").is_file()


class TestRegister:
    def test_register_injects_head_and_foot(self):
        mod = _load_plugin(PLUGIN_DIR)
        app = _fake_app()
        mod.register(app)
        assert "mascot.css" in app._plugin_blocks["head"]
        assert "leaderboard_mascots/static/mascot.css" in app._plugin_blocks["head"]
        assert "mascot.js" in app._plugin_blocks["foot"]
        assert "leaderboard_mascots/static/mascot.js" in app._plugin_blocks["foot"]

    def test_register_appends_and_does_not_clobber(self):
        mod = _load_plugin(PLUGIN_DIR)
        app = _fake_app(head="<meta name='x'>", foot="<script src='/other.js'></script>")
        mod.register(app)
        assert app._plugin_blocks["head"].startswith("<meta name='x'>")
        assert "/other.js" in app._plugin_blocks["foot"]
        assert "mascot.js" in app._plugin_blocks["foot"]

    def test_register_is_idempotent(self):
        mod = _load_plugin(PLUGIN_DIR)
        app = _fake_app()
        mod.register(app)
        mod.register(app)
        # The link/script tag must appear exactly once, not duplicated.
        assert app._plugin_blocks["head"].count("mascot.css") == 1
        assert app._plugin_blocks["foot"].count("mascot.js") == 1


class TestUnregister:
    def test_unregister_is_clean_roundtrip(self):
        mod = _load_plugin(PLUGIN_DIR)
        app = _fake_app(head="<meta name='x'>", foot="<script src='/other.js'></script>")
        mod.register(app)
        mod.unregister(app)
        assert app._plugin_blocks["head"] == "<meta name='x'>"
        assert app._plugin_blocks["foot"] == "<script src='/other.js'></script>"

    def test_unregister_tolerates_missing_blocks(self):
        mod = _load_plugin(PLUGIN_DIR)
        app = types.SimpleNamespace()  # no _plugin_blocks
        mod.unregister(app)  # must not raise
