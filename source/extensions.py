import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman

# HTTPS is opt-in via env (same signal used for REMEMBER_COOKIE_SECURE in
# main.py). When set, Talisman upgrades http->https, emits HSTS, and marks the
# session cookie Secure. Off by default so local/dev and the test client (both
# plain http) are not force-redirected or denied their session cookie.
#
# Deployment note: with HTTPS=1, Talisman treats a request as secure if
# request.is_secure OR an X-Forwarded-Proto: https header is present. Only set
# HTTPS=1 when the app sits behind a reverse proxy that *overwrites* (not
# appends) X-Forwarded-Proto, so a client cannot spoof it.
_HTTPS = os.environ.get("HTTPS", "").lower() in ("1", "true", "yes")

# Content-Security-Policy. Everything the app loads is same-origin (app.js,
# flatpickr.min.js, fonts, images — no CDN, no data: URIs), so 'self' is the
# baseline. Inline <script> blocks carry server-rendered data and are allowed
# only via a per-response nonce (see content_security_policy_nonce_in), which
# is the defense-in-depth against injected inline scripts. Inline style="..."
# attributes remain widespread in the templates, so style-src keeps
# 'unsafe-inline' (styles cannot exfiltrate/execute the way scripts can).
_CSP = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'"],
    "font-src": ["'self'"],
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "frame-ancestors": "'none'",
    "form-action": "'self'",
}

# Global per-IP baseline so every route is throttled, not just auth (issue #75,
# CWE-799). Sensitive/expensive routes layer tighter caps on top via
# @limiter.limit (auth 15/min, password change + zip import 5/min, API-key
# minting 10/min). 200/min is generous for normal interactive use but stops
# unauthenticated floods and scripted abuse of the previously-unlimited routes.
DEFAULT_LIMITS = ["200 per minute"]


def init_app(app):
    limiter = Limiter(get_remote_address, app=app, default_limits=DEFAULT_LIMITS)
    csrf = CSRFProtect(app)

    # Session cookie hardening (issue #74, CWE-614/1275). Talisman (below) owns
    # Secure + HttpOnly for the session cookie; SameSite has no Talisman knob so
    # it is set here. This runs after main.py's REMEMBER_COOKIE_* block and,
    # unlike it, also covers the primary session cookie. SameSite=Lax matches
    # the remember cookie and reinforces the CSRF defense.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    Talisman(
        app,
        content_security_policy=_CSP,
        content_security_policy_nonce_in=["script-src"],
        force_https=_HTTPS,
        strict_transport_security=_HTTPS,
        strict_transport_security_max_age=31_536_000,
        strict_transport_security_include_subdomains=True,
        frame_options="DENY",
        referrer_policy="same-origin",
        # Session cookie hardening (also partially addresses cookie flags):
        # Secure tracks the HTTPS signal so plain-http dev/tests still work.
        session_cookie_secure=_HTTPS,
        session_cookie_http_only=True,
    )

    return limiter, csrf
