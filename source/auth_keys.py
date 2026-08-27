"""API-key permission enforcement (UC-APIKEY-001 / ADR-004).

This module ships the ``@require_permission`` decorator, wired onto the
legacy rounds / stats / courses API routes (issue #41 work, shipped) AND onto
every /api/v1 endpoint.

Behaviour:
  - Session-authenticated users bypass the scope check (they have full account access).
  - API-key identities (``current_user.via_api_key is True``) must carry the required
    permission in their granted scopes, or the request is rejected with 403.

Runtime authZ layers, outermost-in: authenticated (``@login_required`` / the
v1 gate runs first, so an unauthenticated caller is rejected before any scope
is evaluated) -> scoped (this decorator) -> ownership-scoped (existing
``WHERE user_id = ?``) -> non-admin (keys are forced ``is_admin=False`` in
``main.request_loader``).

Enforcement semantics (resolved at merge audit 2026-08-26, #121):
  - DEFAULT = ENFORCED. A key lacking the required scope is rejected with 403
    unconditionally. This is what keeps the issue #41 wiring on the legacy
    routes (rounds/stats/courses, shipped earlier) airtight -- the #121 PR
    originally defaulted to permissive-pending, which would have silently
    gutted that shipped enforcement on merge.
  - The v1 surface's "permissive-pending" window (until #41 lands) is opt-in
    per endpoint via ``permissive_pending=True`` (used ONLY by the v1
    rounds:/settings:/stats:read/courses:read endpoints). While the
    ``API_SCOPE_ENFORCEMENT`` env flag is off, a missing scope on those
    endpoints is logged (``_audit_would_block``) but the handler still runs.
  - ``API_SCOPE_ENFORCEMENT`` (env, default off) forces enforcement on EVERY
    endpoint -- flipping it at #41 requires zero endpoint edits.
  - ``enforce_now=True`` (ADR-004 exception, SEC-2 -- v1
    ``courses:write``/``courses:delete`` ONLY, see docstrings in
    source/routes/api_v1/courses.py): a missing scope is rejected with 403
    IMMEDIATELY, regardless of ``API_SCOPE_ENFORCEMENT``.

The `contract` parameter selects only the REJECTION BODY shape:
  - `contract="legacy"` (default): `{"error": "insufficient_scope", "required": ...}`
    403 -- preserved verbatim for the non-v1 call sites.
  - `contract="problem"` (every v1 call site): RFC 9457
    `application/problem+json`.

This assumes the request is already authenticated (login_required / the v1
authentication gate); it does not itself check `current_user.is_authenticated`.
"""
import logging
import os
from datetime import date
from functools import wraps

from flask import jsonify
from flask_login import current_user

from store import API_KEY_PERMISSIONS as VALID_PERMISSIONS  # single source of truth (dedup, was duplicated)

_log = logging.getLogger("pinsheet")

# Read once at import time (module-level constant, not re-read per-request) --
# consistent with how main.py reads HTTPS once for REMEMBER_COOKIE_SECURE.
API_SCOPE_ENFORCEMENT = os.environ.get("API_SCOPE_ENFORCEMENT", "0").lower() in ("1", "true", "yes")
_SUNSET_VERSION = "0.12.0"  # named per ADR-004 forcing function; bump only alongside #41 status review
_SUNSET_DATE = date(2026, 11, 1)


def require_permission(permission, contract="legacy", enforce_now=False, permissive_pending=False):
    """Decorator gating a route on an API-key permission.

    - Session-authenticated users bypass the scope check (full account trust).
    - API-key identities (`current_user.via_api_key is True`) must carry the
      required permission in their granted scopes.
    - Default: a missing scope is rejected with 403 (shaped per `contract`) --
      this is what keeps the shipped legacy route wiring (rounds/stats/
      courses, issue #41 work) enforced.
    - `permissive_pending=True` (v1 lenient endpoints ONLY, see module
      docstring): while `API_SCOPE_ENFORCEMENT` is False, a missing scope is
      logged (`_audit_would_block`) but the handler is still called. Once
      `API_SCOPE_ENFORCEMENT` is True, a missing scope is rejected with 403.
    - `enforce_now=True` (v1 `courses:write`/`courses:delete` ONLY, SEC-2):
      a missing scope is rejected with 403 IMMEDIATELY, regardless of
      `API_SCOPE_ENFORCEMENT`.
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "via_api_key", False):
                return f(*args, **kwargs)  # session user = full-account trust
            granted = getattr(current_user, "api_permissions", None) or []
            if permission in granted:
                return f(*args, **kwargs)
            if enforce_now or API_SCOPE_ENFORCEMENT or not permissive_pending:
                return _reject(permission, contract)
            _audit_would_block(permission, granted)  # record only, DO NOT reject
            return f(*args, **kwargs)

        return wrapper

    return decorator


def _reject(permission, contract):
    if contract == "problem":
        from source.routes.api_v1.errors import problem

        return problem(
            403,
            f"Key lacks required scope '{permission}'.",
            title="Insufficient scope",
            type="https://pinsheet/errors/insufficient-scope",
        )
    return jsonify({"error": "insufficient_scope", "required": permission}), 403


def _audit_would_block(permission, granted):
    """Detect signal (ADR-004 PM-001) for the permissive-pending window.
    Every field here is either a non-secret identifier or a scope string --
    never the `psk_` plaintext, never the sha256 hash (coding standard §4.4).
    `ts` is intentionally omitted as a message field: the logging formatter
    already timestamps every record (`%(asctime)s`), so no duplicated field
    is needed. `api_key_id` (the api_keys row id) is not available on
    `current_user` in this build -- `prefix` is the non-secret per-key
    correlator instead (`getattr` degrades safely to "?" if absent)."""
    from flask import request

    _log.warning(
        "scope.would_block user_id=%s api_key_prefix=%s endpoint=%s method=%s path=%s "
        "required_scope=%s granted_scopes=%s enforcement=pending",
        current_user.id, getattr(current_user, "prefix", "?"), request.endpoint,
        request.method, request.path, permission, granted,
    )


def _version_at_least(current: str, target: str) -> bool:
    """Numeric (not lexicographic-string) dotted-version comparison.

    Plain Python string `>=` on dotted version strings is NOT monotonic
    (`"0.9.0" >= "0.12.0"` evaluates `True` lexicographically -- `'9' > '1'`
    at the second component -- a false "past sunset" positive for a version
    that is actually earlier). This parses both strings as dotted integer
    tuples for a correct numeric comparison, falling back to the original
    string compare only if either value fails to parse (never raises).
    """
    try:
        cur_parts = tuple(int(p) for p in current.split("."))
        tgt_parts = tuple(int(p) for p in target.split("."))
        return cur_parts >= tgt_parts
    except (ValueError, AttributeError):
        return current >= target


def check_scope_enforcement_sunset():
    """Boot-time forcing function (ADR-004 PM-001). Called once from `main.main()`."""
    try:
        from source import __version__
    except ImportError:
        from __init__ import __version__
    if API_SCOPE_ENFORCEMENT:
        return
    if _version_at_least(__version__, _SUNSET_VERSION) or date.today() > _SUNSET_DATE:
        _log.warning(
            "v1 API scope enforcement still PENDING past sunset (version=%s, date=%s) -- see issue #41",
            __version__, date.today(),
        )
