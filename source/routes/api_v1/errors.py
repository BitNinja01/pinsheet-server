"""RFC 9457 Problem Details (`application/problem+json`) for /api/v1 (ADR-002).

Every v1 error response is produced by `problem(...)` -- no v1 handler ever
hand-rolls `jsonify({"error": ...})`. `register_v1_error_handlers(bp)` wires
the shared exception -> Problem Details translation onto ONE v1 blueprint.

Deviation disclosed (evidence-based, verified against the installed
`apiflask==3.1.1` source, `apiflask/app.py`): this module deliberately uses
**blueprint-scoped** `errorhandler` registration, not an `app.error_processor`
override, even though eng-lead's plan (and the architecture's R4-6 finding)
describe "a handler gated on `request.path.startswith('/api/v1')`" via
`app.error_processor`. Empirically, APIFlask's `error_processor` *setter*
unconditionally calls `self._apply_error_callback_to_werkzeug_errors()`
regardless of the `json_errors` flag (see the `error_processor` docstring's
own "Version changed: 1.0 -- Apply this error processor to normal HTTP
errors even when `json_error` is set to False" note) -- i.e. registering
`app.error_processor` at all makes EVERY werkzeug HTTP exception app-wide
(including a plain `flask.abort(404)` in a legacy route, or the app-wide
"no route matched" 404) flow through that single processor function, which
would violate "legacy untouched" (AC-7) no matter how carefully the
processor's own body branches on `request.path`. Blueprint-scoped
`errorhandler` calls do not touch `error_processor`/`json_errors` at all and
structurally cannot fire for legacy routes (registered as plain
`@app.route`/`Blueprint` views that never raise `apiflask.HTTPError` or use
`apiflask.abort`). See `eng-backend-apiv1.md` build notes for the full
verification trail (test scripts run against the real installed library).

Known, accepted gap: a URL that fails to match ANY route at all (not even a
405 wrong-method on an existing rule) never enters blueprint routing context
in Flask, so an unmapped path under `/api/v1/*` falls through to the legacy
app-wide 404 (HTML), not Problem Details. This is outside the eng-lead §4.3
mandated status-code list and is disclosed, not silently dropped.
"""
import logging
from functools import wraps

from apiflask import HTTPError
from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from source.observability import current_trace_id

_log = logging.getLogger("pinsheet")

_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}

_GENERIC_500_DETAIL = "An unexpected error occurred. Reference traceId when contacting support."


def problem(status: int, detail: str, title: str | None = None, type: str | None = None, instance: str | None = None):
    """Build an RFC 9457 `application/problem+json` response.

    `detail` MUST be request-specific, non-sensitive text -- never an
    exception message, traceback, SQL fragment, file path, or another user's
    data (coding standard §4.3). Callers own that guarantee; this helper only
    shapes the envelope and always attaches a `traceId`.
    """
    resolved_title = title or _TITLES.get(status, "Error")
    body = {
        "type": type or f"https://pinsheet/errors/{resolved_title.lower().replace(' ', '-')}",
        "title": resolved_title,
        "status": status,
        "detail": detail,
        "instance": instance or request.path,
        "traceId": current_trace_id(),
    }
    resp = jsonify(body)
    resp.status_code = status
    resp.mimetype = "application/problem+json"
    return resp


def require_json_body(f):
    """Explicit Content-Type guard for v1 write routes (400/415, ADR-010).

    Deviation disclosed: empirically verified (against the installed
    `apiflask==3.1.1` + `marshmallow==4.3.1` stack) that APIFlask's
    `@bp.input(...)` does NOT reliably 415 a non-JSON body on its own -- a
    `text/plain` POST is silently treated as an empty JSON object and
    surfaces as a 422 "missing required field" instead of a 415. This
    contradicts the eng-lead plan's assumption (§4.1: "APIFlask's @app.input
    already 415s a non-JSON body by default ... do not hand-roll a separate
    check"). This guard restores the ADR-002/ADR-010-mandated 415 contract.
    Stack ABOVE `@bp.input(...)` (i.e. runs first) on every v1 write route.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not request.is_json:
            return problem(415, "Content-Type must be application/json.")
        return f(*args, **kwargs)

    return wrapper


def _detail_from_apiflask_error(error: HTTPError) -> str:
    """Flatten an APIFlask `HTTPError.detail` (a plain string for
    `HTTPError()`/`abort()` call sites, or a structured
    `{"json": {field: [msgs]}}` dict for schema-validation failures) into a
    single safe, human-readable string. Never echoes raw internals."""
    if isinstance(error.detail, str) and error.detail:
        return error.detail
    if isinstance(error.detail, dict) and error.detail:
        parts = []
        for _location, fields_ in error.detail.items():
            if not isinstance(fields_, dict):
                continue
            for field_name, msgs in fields_.items():
                msg_text = "; ".join(str(m) for m in msgs) if isinstance(msgs, list) else str(msgs)
                parts.append(f"{field_name}: {msg_text}")
        if parts:
            return "; ".join(parts)
    return error.message or _TITLES.get(error.status_code, "Validation error")


def _handle_apiflask_error(error: HTTPError):
    return problem(error.status_code, _detail_from_apiflask_error(error))


def _handle_werkzeug_exception(error: HTTPException):
    status = error.code or 500
    detail = error.description if isinstance(error.description, str) and error.description else _TITLES.get(status, "Request could not be processed.")
    return problem(status, detail)


def _handle_uncaught_exception(error: Exception):
    # Log server-side with the full exception (coding standard §4.3); the
    # client only ever sees the fixed, generic detail string below -- never
    # str(exc), never a traceback, never SQL text.
    _log.exception("v1 unhandled exception on %s %s", request.method, request.path)
    return problem(500, _GENERIC_500_DETAIL)


def register_v1_error_handlers(bp) -> None:
    """Wire the Problem Details translation onto ONE v1 `APIBlueprint`.
    Blueprint-scoped -- has zero effect on legacy routes. Call once per v1
    blueprint, BEFORE `app.register_blueprint(bp)` (see `api_v1/__init__.py`).
    """
    bp.register_error_handler(HTTPError, _handle_apiflask_error)
    bp.register_error_handler(HTTPException, _handle_werkzeug_exception)
    bp.register_error_handler(Exception, _handle_uncaught_exception)
