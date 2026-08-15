"""API-key permission enforcement (UC-APIKEY-001 / ADR-004).

Wired to every v1 endpoint. Enforcement is permissive-pending
(`API_SCOPE_ENFORCEMENT` env flag, default off) until #41 lands; flipping the
flag hard-enforces with zero endpoint edits. Session users always bypass
(full-account trust) -- this decorator governs SCOPE only; AUTHENTICATION is
`source.routes.api_v1._require_authenticated_v1` (ADR-012), which runs first
and unconditionally on every v1 request regardless of this module's flag.

The `contract` parameter selects only the REJECTION BODY shape:
  - `contract="legacy"` (default): `{"error": "insufficient_scope", "required": ...}`
    403 -- preserved verbatim for any future non-v1 call site.
  - `contract="problem"` (every v1 call site): RFC 9457
    `application/problem+json`.

ADR-004 exception (Revision 2, SEC-2, coordinator-approved hardening):
`courses:write`/`courses:delete` are enforced IMMEDIATELY (`enforce_now=True`),
regardless of `API_SCOPE_ENFORCEMENT` -- every other v1 scope
(`rounds:*`/`settings:*`/`stats:read`/`courses:read`) stays permissive-pending
exactly as ADR-004 specifies, until #41 lands. Rationale: `rounds`/`settings`
are owner-scoped at the STORE layer (`WHERE user_id = ?`) even if the scope
check were somehow bypassed -- a real defense-in-depth backstop. The shared,
global `courses` table (ADR-011, `store.py:72-107`) has NO such backstop: a
`courses:write`/`courses:delete`-lacking key that slipped through the
permissive-pending window during this window could mutate or delete data
every user of this closed, invite-gated instance shares and sees -- blast
radius is the whole catalog, not just the caller's own rows. `courses:read`
is left permissive-pending (read-only, no integrity/availability blast
radius) alongside `rounds`/`settings`/`stats`.

This assumes ADR-012's v1 authentication gate has already run; it does not
itself check `current_user.is_authenticated`.
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
# consistent with how main.py:45 reads HTTPS once for REMEMBER_COOKIE_SECURE.
API_SCOPE_ENFORCEMENT = os.environ.get("API_SCOPE_ENFORCEMENT", "0").lower() in ("1", "true", "yes")
_SUNSET_VERSION = "0.12.0"  # named per ADR-004 forcing function; bump only alongside #41 status review
_SUNSET_DATE = date(2026, 11, 1)


def require_permission(permission, contract="legacy", enforce_now=False):
    """Decorator gating a route on an API-key permission.

    - Session-authenticated users bypass the scope check (full account trust).
    - API-key identities (`current_user.via_api_key is True`) must carry the
      required permission in their granted scopes.
    - `enforce_now=False` (default -- rounds/settings/stats/courses:read):
      while `API_SCOPE_ENFORCEMENT` is False (permissive-pending, until #41),
      a missing scope is logged (`_audit_would_block`) but the handler is
      ALWAYS still called -- this decorator never rejects during the pending
      window. Once `API_SCOPE_ENFORCEMENT` is True, a missing scope is
      rejected with 403, shaped per `contract`.
    - `enforce_now=True` (ADR-004 exception, SEC-2 -- `courses:write`/
      `courses:delete` ONLY, see module docstring): a missing scope is
      rejected with 403 IMMEDIATELY, regardless of `API_SCOPE_ENFORCEMENT`.
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "via_api_key", False):
                return f(*args, **kwargs)  # session user = full-account trust
            granted = getattr(current_user, "api_permissions", None) or []
            if permission in granted:
                return f(*args, **kwargs)
            if enforce_now or API_SCOPE_ENFORCEMENT:
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
    already timestamps every record (`%(asctime)s`, an eng-infra logging-
    config requirement, not duplicated here). `api_key_id` (the api_keys row
    id) is not available on `current_user` in this build -- `prefix` is the
    non-secret per-key correlator instead (`getattr` degrades safely to "?"
    if absent)."""
    from flask import request

    _log.warning(
        "scope.would_block user_id=%s api_key_prefix=%s endpoint=%s method=%s path=%s "
        "required_scope=%s granted_scopes=%s enforcement=pending",
        current_user.id, getattr(current_user, "prefix", "?"), request.endpoint,
        request.method, request.path, permission, granted,
    )


def _version_at_least(current: str, target: str) -> bool:
    """Numeric (not lexicographic-string) dotted-version comparison.

    Disclosed correction vs. the plan's literal pseudocode
    (`__version__ >= _SUNSET_VERSION`): plain Python string `>=` on dotted
    version strings is NOT monotonic (`"0.9.0" >= "0.12.0"` evaluates `True`
    lexicographically -- `'9' > '1'` at the second component -- a false
    "past sunset" positive for a version that is actually earlier). This
    parses both strings as dotted integer tuples for a correct numeric
    comparison, falling back to the original string compare only if either
    value fails to parse (never raises).
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
