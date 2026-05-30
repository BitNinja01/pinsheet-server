import logging
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

try:
    from . import __version__
except ImportError:
    from __init__ import __version__

# Ensure the repo root is on sys.path so source.* imports resolve
# regardless of Python version, virtualenv setup, or CWD configuration.
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from flask import Flask, request, g

from database import set_db_path, init_db
from store import (
    get_user_by_id, get_user,
)

from source.plugin import _plugins
from source.plugin_loader import discover_plugins

_log = logging.getLogger("pinsheet")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

from flask_login import LoginManager, current_user

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.session_protection = "strong"

app.config["REMEMBER_COOKIE_SECURE"] = os.environ.get("HTTPS", "").lower() in ("1", "true", "yes")
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_DURATION"] = 30 * 24 * 60 * 60  # 30 days


class User:
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.display_name = user_dict["display_name"]
        self.is_admin = user_dict.get("is_admin", False)
        self._authenticated = True

    @property
    def is_authenticated(self):
        return self._authenticated

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def _load_user(user_id):
    user_dict = get_user_by_id(int(user_id))
    return User(user_dict) if user_dict else None


from source.extensions import init_app

limiter, csrf = init_app(app)


@app.before_request
def _load_globals():
    if request.endpoint in ("login_page", "register_page", "static"):
        return

    current_user_id = current_user.id if current_user.is_authenticated else None

    view_username = request.args.get("user")
    if view_username:
        view_user_dict = get_user(view_username)
        if view_user_dict:
            g.view_user = view_user_dict
        else:
            g.view_user = None
    else:
        if current_user.is_authenticated:
            g.view_user = get_user_by_id(current_user_id)
        else:
            g.view_user = None

    if g.view_user is None:
        return


@app.context_processor
def inject_version():
    return dict(version=__version__)


@app.context_processor
def inject_plugin_globals():
    return {
        "plugin_blocks": getattr(app, "_plugin_blocks", {}),
        "plugin_nav": getattr(app, "_plugin_nav", []),
        "plugin_info": {p.plugin_info["name"]: p.plugin_info for p in _plugins if hasattr(p, "plugin_info")},
    }


app.jinja_env.globals.setdefault("plugin_info", {})


@app.before_request
def _check_view_permission():
    if request.endpoint in ("login_page", "register_page", "static"):
        return
    if not hasattr(g, "view_user") or g.view_user is None:
        return
    g.is_own_data = current_user.is_authenticated and g.view_user["id"] == current_user.id


from source.routes import (
    register_auth_routes, register_dashboard_routes,
    register_rounds_routes, register_courses_routes,
    register_settings_routes, register_stats_routes
)

register_auth_routes(app, limiter, User)
register_dashboard_routes(app, limiter, csrf)
register_rounds_routes(app)
register_courses_routes(app)
register_settings_routes(app, csrf)
register_stats_routes(app)


PORT = 8080


def find_free_port() -> int:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", PORT))
            return PORT
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def _find_chrome() -> str | None:
    if sys.platform == "darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    elif sys.platform == "win32":
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        paths = [
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    for p in paths:
        if os.path.isfile(p):
            return p

    found = shutil.which("google-chrome-stable") or shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("chrome")
    return found


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data", default=None)
    args = parser.parse_args()

    if args.data:
        data_dir = Path(args.data)
    else:
        data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    secret_key = os.environ.get("SECRET_KEY", "")
    default_keys = ("REPLACE_ME", "dev-key-", "change-me", "secret")
    if not secret_key or secret_key == "":
        print("ERROR: SECRET_KEY environment variable is required.", file=sys.stderr)
        print("Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"", file=sys.stderr)
        sys.exit(1)
    if any(secret_key.startswith(dk) for dk in default_keys):
        print("ERROR: SECRET_KEY must not be a default/placeholder value.", file=sys.stderr)
        sys.exit(1)
    app.secret_key = secret_key

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()
    app.config["DB_PATH"] = Path(db_path)
    app.config["DATA_DIR"] = data_dir
    app._plugin_blocks = {}
    app._plugin_nav = []
    app._plugin_course_actions = []
    discover_plugins(app)

    port = args.port if args.port is not None else find_free_port()
    url = f"http://{args.host}:{port}"

    chrome_proc = None
    if args.host == "127.0.0.1" and os.environ.get("FLASK_DEBUG") != "0":
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            chrome = _find_chrome()
            if chrome:
                chrome_proc = subprocess.Popen(
                    [chrome, f"--app={url}", "--start-maximized"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                webbrowser.open(url)
        else:
            _log.info("No display found — skipping browser launch")

    if chrome_proc:
        def _watch_chrome():
            chrome_proc.wait()
            _log.info("Chrome window closed — shutting down")
            os._exit(0)
        threading.Thread(target=_watch_chrome, daemon=True).start()

    import atexit

    def _unregister_plugins():
        for plugin in _plugins:
            if hasattr(plugin, "unregister"):
                try:
                    plugin.unregister(app)
                except Exception as exc:
                    _log.warning("plugin %s: unregister() failed — %s", getattr(plugin, "plugin_info", {}).get("name", "?"), exc)
    atexit.register(_unregister_plugins)

    from waitress import serve
    print(f"PinSheet -> http://{args.host}:{port}")
    serve(app, host=args.host, port=port)


if __name__ == "__main__":
    main()
