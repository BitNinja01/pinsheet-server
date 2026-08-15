import os

from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect


def init_app(app):
    limiter = Limiter(get_remote_address, app=app, default_limits=[])
    csrf = CSRFProtect(app)
    return limiter, csrf


def init_cors(app) -> None:
    """ADR-005: v1-scoped, default-deny CORS. Never app-wide -- the legacy web
    UI stays same-origin, untouched."""
    origins = [o.strip() for o in os.environ.get("API_CORS_ORIGINS", "").split(",") if o.strip()]
    CORS(app, resources={r"/api/v1/*": {
        "origins": origins,              # [] when unset -> flask-cors emits NO ACAO header (deny-all)
        "supports_credentials": False,   # bearer header, not a cookie (ADR-005) -- not env-configurable
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
    }})


def api_v1_key_func():
    """ADR-006: rate-limit key = the resolved key owner's user id (per-user,
    not raw IP) when authenticated via an API key, else remote IP (bounds
    pre-auth probing before ADR-012's 401 fires -- see eng-lead §2.2 rate-
    limit-key-granularity note re: per-key vs per-user; DEF-4 fast-follow)."""
    if getattr(current_user, "is_authenticated", False) and getattr(current_user, "via_api_key", False):
        return f"apikey:{current_user.id}"
    return get_remote_address()
