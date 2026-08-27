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

from flask import request, g, jsonify, redirect, url_for
from apiflask import APIFlask

from database import set_db_path, init_db
from store import (
    get_user_by_id,
    get_user_by_api_key,
)

from source.plugin import _plugins
from source.plugin_loader import discover_plugins
from source.routes import register_routes

_log = logging.getLogger("pinsheet")
# %(asctime)s added (was: "%(levelname)s: %(message)s") so every log record --
# including the ADR-004 `scope.would_block` audit entries (auth_keys.py) --
# carries a timestamp from the formatter itself, rather than needing `ts` as
# a duplicated message field (eng-lead §2.2 disclosed deviation; flagged as a
# required backend change by eng-infra's env-config notes).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ADR-001: the root app must BE an APIFlask instance for /api/v1's OpenAPI
# spec collection (Swagger/Redoc) to work at all -- APIFlask subclasses
# flask.Flask, so every existing extension binding below (login_manager,
# CSRFProtect, Limiter, all legacy @app.route/Blueprint views) is unaffected.
# json_errors=False is NOT optional: at the APIFlask default (True), its
# error_processor JSON-ifies every route's HTTP errors app-wide, including
# legacy Jinja/`/api/*` 404s/405s/500s -- False keeps that legacy behavior
# byte-identical (AC-7); v1's own Problem Details handling is wired
# separately, per-blueprint, in source/routes/api_v1 (see errors.py).
app = APIFlask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
    title="PinSheet API",
    version="1",
    spec_path="/api/v1/openapi.json",
    docs_path="/api/v1/docs",
    json_errors=False,
)

from flask_login import LoginManager, current_user, login_required

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.session_protection = "strong"

app.config["REMEMBER_COOKIE_SECURE"] = os.environ.get("HTTPS", "").lower() in ("1", "true", "yes")
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_DURATION"] = 30 * 24 * 60 * 60  # 30 days

# Cap the raw request/upload body to bound memory use and reject zip-bomb
# uploads before they are read (CWE-400). Configurable via env; default 16 MB.
app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
)


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


@login_manager.request_loader
def _load_user_from_request(req):
    """Resolve `Authorization: Bearer psk_...` to a User (UC-APIKEY-001).

    Additive: returns None on any missing/invalid key so Flask-Login falls
    through to the session user_loader. Session cookies always take precedence
    (Flask-Login only calls this when no session user is present), so existing
    web-UI auth is unchanged. The key-derived identity is forced non-admin so a
    key — even an admin user's key — can never reach an admin route.
    """
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    key = auth_header[len("Bearer "):].strip()
    if not key.startswith("psk_"):
        return None
    user_dict = get_user_by_api_key(key)
    if not user_dict:
        return None
    user = User(user_dict)
    user.is_admin = False              # keys are never admin (admin stays session-only)
    user.via_api_key = True
    user.api_permissions = user_dict.get("permissions", [])
    user.prefix = user_dict.get("prefix")  # non-secret display fragment (store.py:1010) -- audit correlator (M-1)
    return user


@login_manager.unauthorized_handler
def _unauthorized():
    """Return a true 401 for bearer (API) callers; preserve the 302 -> login
    redirect for the web UI. Without this, a revoked/expired key would receive
    the HTML login redirect instead of a 401."""
    if request.headers.get("Authorization", "").startswith("Bearer psk_"):
        return jsonify({"error": "unauthorized"}), 401
    return redirect(url_for("login_page", next=request.path))


from source.extensions import init_app, init_cors

limiter, csrf = init_app(app)

init_cors(app)  # ADR-005: /api/v1-scoped, default-deny CORS; never app-wide.

from source.observability import init_tracing

init_tracing(app)  # ADR-003: no-op default, no exporter (see observability.py).

# Revision 1 (PM-3, coordinator-flagged): AC-5 requires Swagger UI AND ReDoc.
# APIFlask 3.1.1's constructor only mounts ONE `docs_ui` template at
# `docs_path` (default `swagger-ui`); it ships a `redoc` template
# (`apiflask.ui_templates.ui_templates["redoc"]`) but has no second
# constructor arg to mount it at a second path. Register it directly: the
# template's own `Redoc.init(...)` call reads `url_for('openapi.spec')`
# (the same spec_path already configured above), and its Jinja `config.*`
# lookups (`REDOC_STANDALONE_JS`, `DOCS_FAVICON`, etc.) resolve against
# APIFlask's own default config values (`apiflask/settings.py`) -- no extra
# config needed.
from apiflask.ui_templates import ui_templates
from flask import render_template_string


@app.route("/api/v1/redoc")
@app.doc(hide=True)  # a docs-UI route shouldn't list itself as an API operation
def api_v1_redoc():
    return render_template_string(ui_templates["redoc"], title=app.title, version=app.version)


# ADR-013: gate the OpenAPI docs/spec/redoc routes by environment. Open in
# dev (FLASK_DEBUG truthy, or an explicit API_DOCS_PUBLIC=1); require an
# authenticated caller (session or valid psk_ key) in prod (default) so the
# OpenAPI document -- a machine-readable map of every v1 resource/scope --
# isn't free reconnaissance for an anonymous caller (T-15). The openapi
# blueprint's `spec`/`docs` views are already registered by the APIFlask
# constructor above (spec_path/docs_path); `api_v1_redoc` was just added.
_API_DOCS_PUBLIC = os.environ.get("API_DOCS_PUBLIC", "").lower() in ("1", "true", "yes")
_DEV_MODE = os.environ.get("FLASK_DEBUG", "") not in ("", "0")
if not (_DEV_MODE or _API_DOCS_PUBLIC):
    for _docs_endpoint in ("openapi.spec", "openapi.docs", "api_v1_redoc"):
        _docs_view = app.view_functions.get(_docs_endpoint)
        if _docs_view is not None:
            app.view_functions[_docs_endpoint] = login_required(_docs_view)


# Revision 1 (found while verifying PM-2/PM-3, disclosed): APIFlask's spec
# collection picks up EVERY `app.route`-registered view by default, not just
# `APIBlueprint`-wrapped ones -- ADR-001's "regular Blueprints are skipped
# from spec" claim (verified true) doesn't cover the legacy `register_*_
# routes(app, ...)` functions, which bind directly on the APIFlask instance
# via bare `@app.route(...)` (no Blueprint wrapper at all -- confirmed,
# `source/routes/courses.py` etc.). Left alone, the generated
# `/api/v1/openapi.json`/Swagger/Redoc would list every legacy Jinja/`/api/*`
# route alongside the 13 real v1 endpoints. `spec_processor` only
# post-processes the generated spec DICT at doc-request time -- it never
# touches routing or request handling, so it cannot affect "legacy
# untouched" (verified: filtering here does not remove or alter any
# `app.view_functions`/`url_map` entry, only what `spec_processor` reports).
@app.spec_processor
def _scope_spec_to_v1(spec):
    if isinstance(spec, dict) and "paths" in spec:
        spec["paths"] = {p: v for p, v in spec["paths"].items() if p.startswith("/api/v1")}
    return spec


@app.before_request
def _setup_globals():
    if request.endpoint in ("login_page", "register_page", "static"):
        return
    if current_user.is_authenticated:
        g.is_own_data = True
    else:
        g.is_own_data = False


def _fmt(val, suffix="", precision=1):
    if val is None:
        return "\u2014"
    if suffix == "%":
        return f"{val:.{precision}f}%"
    return f"{val:.{precision}f}{suffix}"


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
app.jinja_env.globals["_fmt"] = _fmt

@app.template_filter("split")
def _jinja_split(value, separator):
    return value.split(separator)



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

    from source.auth_keys import check_scope_enforcement_sunset
    check_scope_enforcement_sunset()  # ADR-004 PM-001: loud boot warning if permissive-pending has run past its sunset

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()
    from store import recompute_all_handicaps
    recompute_all_handicaps()
    app.config["DB_PATH"] = Path(db_path)
    app.config["DATA_DIR"] = data_dir
    app._plugin_blocks = {}
    app._plugin_nav = []
    app._plugin_course_actions = []
    app._discovered_plugins = []
    app._plugin_states_at_startup = {}
    discover_plugins(app)

    register_routes(app, limiter, csrf, User)

    @app.after_request
    def _set_csp(response):
        # Defense-in-depth for finding U1 / GH#68 (stored XSS via course
        # catalog fields). The actual XSS control is Jinja autoescape in the
        # templates; this CSP is a secondary layer.
        #
        # Shipped as Report-Only (NOT enforcing) on purpose: the app has
        # inline <script> blocks in course_detail.html, bag.html,
        # round_detail.html, round_entry.html, welcome.html, and
        # stats/macros.html. A strict "script-src 'self'" would BREAK those
        # (a functional regression), so enforcing it now would trade an XSS
        # fix for broken UI. Report-Only collects violation reports without
        # breaking anything. Flipping to the enforcing "Content-Security-
        # Policy" header requires first externalizing/noncing those inline
        # scripts — tracked under #73 (security-headers) and #71 (bag |tojson).
        response.headers["Content-Security-Policy-Report-Only"] = (
            "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'"
        )
        return response

    from source.routes.api_v1 import register_api_v1
    register_api_v1(app, limiter, csrf)

    # eng-frontend (Step 3, parallel) owns source/routes/spa.py -- guarded so
    # this backend build stays independently importable/runnable regardless
    # of merge order between the two parallel Step-3 workstreams. Once
    # source/routes/spa.py lands, this behaves identically to an
    # unconditional `from source.routes.spa import register_spa_routes;
    # register_spa_routes(app)` call (disclosed deviation from the plan's
    # literal unconditional call -- see build notes).
    try:
        from source.routes.spa import register_spa_routes
    except ImportError:
        _log.warning("source.routes.spa not found -- /app SPA route not registered (eng-frontend build pending)")
    else:
        register_spa_routes(app)

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
