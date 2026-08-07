import socket
import sys

import pytest
from flask import g, request

import source.main as main_mod
from source.routes import register_routes
from database import set_db_path, init_db
from store import create_user

try:
    register_routes(main_mod.app, main_mod.limiter, main_mod.csrf, main_mod.User)
except AssertionError:
    pass


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    main_mod.limiter.enabled = False

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "drafts").mkdir()

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    main_mod.app.config["TESTING"] = True
    main_mod.app.config["WTF_CSRF_ENABLED"] = False
    main_mod.app.config["SECRET_KEY"] = "test-secret-key"

    return db_path


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUser:
    def test_user_wraps_dict_fields(self):
        u = main_mod.User({"id": 7, "username": "bob", "display_name": "Bob", "is_admin": True})
        assert u.id == 7
        assert u.username == "bob"
        assert u.display_name == "Bob"
        assert u.is_admin is True
        assert u.get_id() == "7"

    def test_user_defaults_is_admin_false(self):
        u = main_mod.User({"id": 1, "username": "a", "display_name": "A"})
        assert u.is_admin is False

    def test_user_flask_login_properties(self):
        u = main_mod.User({"id": 1, "username": "a", "display_name": "A"})
        assert u.is_authenticated is True
        assert u.is_active is True
        assert u.is_anonymous is False


# ---------------------------------------------------------------------------
# _load_user (flask-login user_loader)
# ---------------------------------------------------------------------------

class TestLoadUser:
    def test_load_user_returns_user_for_valid_id(self, fresh_db):
        created = create_user("loader", "Loader", "password123")
        loaded = main_mod._load_user(str(created["id"]))
        assert isinstance(loaded, main_mod.User)
        assert loaded.username == "loader"

    def test_load_user_returns_none_for_unknown_id(self, fresh_db):
        assert main_mod._load_user("999999") is None


# ---------------------------------------------------------------------------
# _fmt template helper
# ---------------------------------------------------------------------------

class TestFmt:
    def test_none_returns_em_dash(self):
        assert main_mod._fmt(None) == "—"

    def test_default_suffix_and_precision(self):
        assert main_mod._fmt(12.345) == "12.3"
        assert main_mod._fmt(12.345, precision=2) == "12.35"

    def test_custom_suffix(self):
        assert main_mod._fmt(6200, suffix=" yds", precision=0) == "6200 yds"

    def test_percent_suffix_formats_with_percent_sign(self):
        assert main_mod._fmt(45.678, suffix="%") == "45.7%"
        assert main_mod._fmt(45.678, suffix="%", precision=0) == "46%"


# ---------------------------------------------------------------------------
# _setup_globals before_request hook
# ---------------------------------------------------------------------------

class TestSetupGlobals:
    def test_excluded_endpoint_skips_setting_flag(self, fresh_db):
        with main_mod.app.test_request_context("/login"):
            assert request.endpoint == "login_page"
            main_mod._setup_globals()
            assert not hasattr(g, "is_own_data")

    def test_unauthenticated_request_sets_flag_false(self, fresh_db):
        with main_mod.app.test_request_context("/bag"):
            main_mod._setup_globals()
            assert g.is_own_data is False

    def test_authenticated_request_sets_flag_true(self, fresh_db):
        from flask_login import login_user

        user_dict = create_user("flaguser", "Flag User", "password123")
        # Deliberately avoid test_client()/full WSGI dispatch here: this app
        # object is shared with tests/test_plugin.py, which registers extra
        # routes on it later via discover_plugins(); Flask forbids adding
        # routes once an app has served a real request, so a full request
        # cycle on this singleton would break plugin discovery tests that
        # run afterward. test_request_context + login_user exercises the
        # exact same current_user.is_authenticated branch without that
        # side effect.
        with main_mod.app.test_request_context("/bag"):
            login_user(main_mod.User(user_dict))
            main_mod._setup_globals()
            assert g.is_own_data is True


# ---------------------------------------------------------------------------
# context processors / template filter
# ---------------------------------------------------------------------------

class TestContextProcessors:
    def test_inject_version_matches_package_version(self):
        from source import __version__
        assert main_mod.inject_version() == {"version": __version__}

    def test_inject_plugin_globals_defaults_when_unset(self):
        # main() hasn't run for this app instance, so _plugin_blocks/_plugin_nav
        # are absent; the getattr(..., default) branches must kick in.
        assert not hasattr(main_mod.app, "_plugin_blocks")
        result = main_mod.inject_plugin_globals()
        assert result["plugin_blocks"] == {}
        assert result["plugin_nav"] == []
        assert isinstance(result["plugin_info"], dict)

    def test_inject_plugin_globals_reflects_app_state(self, monkeypatch):
        monkeypatch.setattr(main_mod.app, "_plugin_blocks", {"sidebar": ["x"]}, raising=False)
        monkeypatch.setattr(main_mod.app, "_plugin_nav", [{"label": "Test"}], raising=False)
        result = main_mod.inject_plugin_globals()
        assert result["plugin_blocks"] == {"sidebar": ["x"]}
        assert result["plugin_nav"] == [{"label": "Test"}]

    def test_jinja_split_filter(self):
        assert main_mod._jinja_split("a,b,c", ",") == ["a", "b", "c"]
        assert main_mod._jinja_split("only", ",") == ["only"]


# ---------------------------------------------------------------------------
# find_free_port
# ---------------------------------------------------------------------------

class TestFindFreePort:
    def test_returns_default_port_when_available(self, monkeypatch):
        # Find a genuinely free ephemeral port and pretend it's PORT so the
        # "happy path" bind-and-return branch is exercised deterministically.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()

        monkeypatch.setattr(main_mod, "PORT", free_port)
        assert main_mod.find_free_port() == free_port

    def test_falls_back_to_os_assigned_port_when_default_taken(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", main_mod.PORT))
        blocker.listen(1)
        try:
            port = main_mod.find_free_port()
            assert port != main_mod.PORT
            assert 1 <= port <= 65535
        finally:
            blocker.close()


# ---------------------------------------------------------------------------
# _find_chrome
# ---------------------------------------------------------------------------

class TestFindChrome:
    def test_darwin_returns_hardcoded_path_when_present(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(main_mod.os.path, "isfile", lambda p: True)
        result = main_mod._find_chrome()
        assert result == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    def test_darwin_falls_back_to_which_when_path_missing(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(main_mod.os.path, "isfile", lambda p: False)
        monkeypatch.setattr(main_mod.shutil, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None)
        result = main_mod._find_chrome()
        assert result == "/usr/bin/chromium"

    def test_darwin_returns_none_when_nothing_found(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(main_mod.os.path, "isfile", lambda p: False)
        monkeypatch.setattr(main_mod.shutil, "which", lambda name: None)
        assert main_mod._find_chrome() is None

    def test_linux_checks_linux_specific_paths(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(main_mod.os.path, "isfile", lambda p: p == "/usr/bin/chromium-browser")
        result = main_mod._find_chrome()
        assert result == "/usr/bin/chromium-browser"

    def test_win32_checks_windows_specific_paths(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(main_mod.os.path, "isfile", lambda p: False)
        monkeypatch.setattr(main_mod.shutil, "which", lambda name: None)
        assert main_mod._find_chrome() is None


# ---------------------------------------------------------------------------
# main() CLI bootstrap -- only the SECRET_KEY validation branches are
# exercised here; the actual waitress.serve() call is out of scope per the
# QA test plan (never invoke the real server from tests).
# ---------------------------------------------------------------------------

class TestMainSecretKeyValidation:
    def test_exits_when_secret_key_missing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setattr(sys, "argv", ["main.py", "--data", str(tmp_path)])

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "SECRET_KEY environment variable is required" in captured.err

    @pytest.mark.parametrize("bad_key", ["REPLACE_ME_please", "dev-key-abc123", "change-me-now", "secretvalue"])
    def test_exits_when_secret_key_is_placeholder(self, tmp_path, monkeypatch, capsys, bad_key):
        monkeypatch.setenv("SECRET_KEY", bad_key)
        monkeypatch.setattr(sys, "argv", ["main.py", "--data", str(tmp_path)])

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "must not be a default/placeholder value" in captured.err

    def test_data_dir_created_from_cli_arg_before_validation(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        custom_dir = tmp_path / "custom_data_dir"
        monkeypatch.setattr(sys, "argv", ["main.py", "--data", str(custom_dir)])

        assert not custom_dir.exists()
        with pytest.raises(SystemExit):
            main_mod.main()
        # main() creates the data directory before the SECRET_KEY check runs.
        assert custom_dir.exists()
