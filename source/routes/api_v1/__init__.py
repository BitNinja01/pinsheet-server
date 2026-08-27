"""`register_api_v1(app, limiter, csrf)` -- wires the four `/api/v1` resource
blueprints onto the (already-`APIFlask`) app: the ADR-012 authentication
gate, ADR-002 Problem Details error handlers, Rev-2 C-1 CSRF exemption, and
ADR-006 rate-limit budgets are applied identically to all four blueprints
here, so no future route can land without them.

Rate limits are applied HERE, programmatically, AFTER `app.register_blueprint`
-- not as a `@limiter.limit(...)` decorator written textually inside each
resource module, as the plan's pseudocode shows. Disclosed deviation, with
reason: `limiter` does not exist as an importable object until `main.py`
calls `extensions.init_app(app)`; the v1 resource modules (`courses.py`/
`rounds.py`/...) are imported -- and their blueprints/routes defined -- via
this package's own imports below, which happens before that point. Wrapping
`app.view_functions[endpoint]` with `limiter.limit(budget,
key_func=api_v1_key_func)` immediately after registration produces the
IDENTICAL runtime behavior (Flask re-resolves `view_functions` on every
dispatch; verified empirically against the installed `flask-limiter==4.1.1`)
as a `@limiter.limit(...)` decorator written above `@bp.route(...)` would --
same outer (Stage-A) position in the decorator stack (§4.2), same per-route
budget, same `key_func`. This is a build-time wiring choice, not a change to
the security contract.
"""
import logging
import os

from source.extensions import api_v1_key_func
from source.routes.api_v1.courses import courses_v1
from source.routes.api_v1.errors import problem, register_v1_error_handlers
from source.routes.api_v1.rounds import rounds_v1
from source.routes.api_v1.settings import settings_v1
from source.routes.api_v1.stats import stats_v1

_log = logging.getLogger("pinsheet")

_V1_BLUEPRINTS = (courses_v1, rounds_v1, stats_v1, settings_v1)

# ADR-006 / eng-lead §4.8 -- env-tunable, per-verb-class budgets.
READ_BUDGET = os.environ.get("API_RATE_LIMIT_READ", "120 per minute")
WRITE_BUDGET = os.environ.get("API_RATE_LIMIT_WRITE", "30 per minute")
DELETE_BUDGET = os.environ.get("API_RATE_LIMIT_DELETE", "15 per minute")


def _require_authenticated_v1():
    """ADR-012 -- v1-wide authentication gate. Permanent and unconditional
    (does NOT read `API_SCOPE_ENFORCEMENT` -- that flag governs SCOPE
    enforcement only, never authentication). Accepts session users and
    resolved `psk_` bearer identities alike (`current_user.is_authenticated`
    is True for both, `main.py:81-104`); rejects everyone else with a 401
    Problem Details before any handler or scope logic runs.

    Ordering note (§4.2 Stage A): flask-limiter's own check is an app-level
    `before_request` hook that ALWAYS runs before this blueprint-level
    `before_request`, per Flask's execution order (app-level hooks run before
    any blueprint-level ones). So an anonymous, over-budget caller receives
    429 before ever reaching this 401 -- accepted and deliberate (eng-lead
    §4.2 Rev-2 M-2), not a bug, and not something decorator/hook ordering in
    this file can or should change.
    """
    from flask_login import current_user

    if not current_user.is_authenticated:
        return problem(
            401,
            "Authentication required for /api/v1.",
            title="Unauthorized",
            type="https://pinsheet/errors/unauthorized",
        )


def _budget_for(methods: set[str]) -> str:
    if "DELETE" in methods:
        return DELETE_BUDGET
    if "POST" in methods or "PUT" in methods:
        return WRITE_BUDGET
    return READ_BUDGET


def register_api_v1(app, limiter, csrf) -> None:
    for bp in _V1_BLUEPRINTS:
        bp.before_request(_require_authenticated_v1)
        register_v1_error_handlers(bp)
        # Rev-2 C-1 (mandatory, §4.9): v1 clients carry a Bearer token, never
        # a session-seeded csrf_token. Without this, every v1 write endpoint
        # 400s before auth/limiter/scope ever runs. Blueprint-level (not
        # per-view) exemption so a newly-added route can never forget it.
        #
        # SEC-4 (Revision 2, disclosed): the ADR-012 auth gate above accepts
        # SESSION-cookie identities too (`current_user.is_authenticated` is
        # True for both), so this exemption also covers a session-cookie
        # caller hitting a v1 write route directly -- normally CSRFProtect's
        # exact job. The backstop for that case is NOT this module: every v1
        # write route stacks `errors.require_json_body` (checks
        # `request.is_json`) above `@bp.input(...)`, and a genuine
        # cross-site HTML-form CSRF POST is structurally unable to arrive
        # with `Content-Type: application/json` (a `<form>` can only send
        # `application/x-www-form-urlencoded`, `multipart/form-data`, or
        # `text/plain` -- setting an arbitrary JSON content-type from
        # cross-origin JS would require a CORS preflight, which ADR-005's
        # default-deny CORS blocks for any non-allowlisted origin). So a
        # forged cross-site request against a v1 write route 415s before
        # any state-changing logic runs, for BOTH bearer and session
        # callers. See `test_v1_write_rejects_form_content_type_from_session`
        # (`tests/test_api_v1.py`).
        csrf.exempt(bp)
        app.register_blueprint(bp)

    bp_prefixes = tuple(f"{bp.name}." for bp in _V1_BLUEPRINTS)
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith(bp_prefixes):
            continue
        view = app.view_functions[rule.endpoint]
        if getattr(view, "_api_v1_rate_limited", False):
            continue  # already wrapped (defensive; normally one rule per endpoint)
        budget = _budget_for(rule.methods or set())
        wrapped = limiter.limit(budget, key_func=api_v1_key_func)(view)
        wrapped._api_v1_rate_limited = True
        app.view_functions[rule.endpoint] = wrapped

    _log.info(
        "api_v1: registered %d blueprint(s): %s",
        len(_V1_BLUEPRINTS), ", ".join(bp.name for bp in _V1_BLUEPRINTS),
    )
