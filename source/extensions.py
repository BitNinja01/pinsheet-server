from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Global per-IP baseline so every route is throttled, not just auth (issue #75,
# CWE-799). Sensitive/expensive routes layer tighter caps on top via
# @limiter.limit (auth 15/min, password change + zip import 5/min, API-key
# minting 10/min). 200/min is generous for normal interactive use but stops
# unauthenticated floods and scripted abuse of the previously-unlimited routes.
DEFAULT_LIMITS = ["200 per minute"]


def init_app(app):
    limiter = Limiter(get_remote_address, app=app, default_limits=DEFAULT_LIMITS)
    csrf = CSRFProtect(app)
    return limiter, csrf
