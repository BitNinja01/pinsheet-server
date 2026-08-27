"""SPA host route for the standalone `/app` client (ADR-008, issue #50).

Serves the static bundle at `source/web/static/app/` for on-course score
entry against `/api/v1`. This module owns ONLY the `/app` shell route — it
never registers an `/api/*` route and never touches auth/session state.
Loading the shell requires no login; the SPA itself authenticates its own
`/api/v1` calls with a bearer `psk_` key entered client-side.

Security notes:
  - DEF-1 (eng-lead build plan §6.2): every `/app` response carries a strict
    Content-Security-Policy header — no inline scripts, no third-party
    origins, no framing. The SPA bundle is 100% external `<script src>`/
    `<link rel=stylesheet>` with event handlers wired via addEventListener,
    so `script-src 'self'` (no `'unsafe-inline'`, no `'unsafe-eval'`) is
    satisfiable without any code changes here.
  - `send_from_directory` performs its own safe-path resolution (Werkzeug's
    `safe_join`) so a request cannot escape `SPA_DIR` even if the manual
    traversal check below were somehow bypassed; the manual check is
    defense-in-depth / fail-fast, not the sole control.
  - Client-side routing fallback: a path segment WITHOUT a `.` in its last
    component (e.g. `/app/rounds/new`) is treated as an app route and falls
    back to `index.html` so the History-API router can take over on a hard
    refresh / deep link. A path segment that DOES look like a file request
    (contains a `.`, e.g. `/app/service-worker.js`, `/app/manifest.webmanifest`)
    and does not exist on disk returns a real 404 — this SPA is explicitly
    NOT a PWA (issue #36 is separate scope), so no service worker or web
    manifest is ever served, by absence and by this 404 behavior.
"""
import os

from flask import abort, send_from_directory

# source/routes/spa.py -> source/routes -> source -> source/web/static/app
_SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPA_DIR = os.path.join(_SOURCE_DIR, "web", "static", "app")

# DEF-1 (eng-architect ADR-008 / eng-lead build plan §6.2), verbatim.
CSP_HEADER = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


def _index_response():
    resp = send_from_directory(SPA_DIR, "index.html")
    resp.headers["Content-Security-Policy"] = CSP_HEADER
    return resp


def register_spa_routes(app):
    """Register the `/app` SPA shell. No `/api/*` route is registered here."""

    @app.route("/app")
    @app.route("/app/")
    def spa_index():
        return _index_response()

    @app.route("/app/<path:subpath>")
    def spa_asset(subpath):
        # Defense-in-depth traversal guard (send_from_directory/safe_join is
        # the authoritative control; this fails fast and avoids even
        # touching the filesystem with an obviously-hostile path).
        normalized = os.path.normpath(subpath)
        if normalized.startswith("..") or os.path.isabs(normalized):
            abort(404)

        candidate = os.path.join(SPA_DIR, normalized)
        last_segment = subpath.rsplit("/", 1)[-1]
        looks_like_file_request = "." in last_segment

        if os.path.isfile(candidate):
            resp = send_from_directory(SPA_DIR, normalized)
            resp.headers["Content-Security-Policy"] = CSP_HEADER
            return resp

        if looks_like_file_request:
            # Explicit 404 for asset-shaped requests that don't exist,
            # including /app/service-worker.js and /app/manifest.webmanifest
            # (not a PWA, ADR-008 acceptance check).
            abort(404)

        # No file extension in the last segment -> client-side route
        # (e.g. /app/rounds/new). Fall back to the SPA shell.
        return _index_response()
