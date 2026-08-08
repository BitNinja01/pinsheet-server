"""API-key permission scaffold (UC-APIKEY-001).

This module ships the ``@require_permission`` decorator as a *functional scaffold*
only. Per the locked v1 scope, it is intentionally NOT applied to any endpoint —
per-endpoint enforcement is deferred to GAP-029. v1 runtime authZ remains
authenticated + ownership-scoped (existing ``WHERE user_id = ?``) + non-admin.

When (and only when) it is wired to a route in a future iteration, the behaviour is:
  - Session-authenticated users bypass the scope check (they have full account access).
  - API-key identities (``current_user.via_api_key is True``) must carry the required
    permission in their granted scopes, or the request is rejected with 403.
"""

from functools import wraps

from flask import jsonify
from flask_login import current_user

# The closed set of v1 permission strings (mirrors store.API_KEY_PERMISSIONS).
VALID_PERMISSIONS = ("rounds:read", "rounds:write", "stats:read", "courses:write")


def require_permission(permission):
    """Decorator scaffold gating a route on an API-key permission.

    NOTE: deferred (GAP-029) — not wired to any endpoint in v1.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Only API-key identities are scope-limited; session users pass through.
            if getattr(current_user, "via_api_key", False):
                granted = getattr(current_user, "api_permissions", None) or []
                if permission not in granted:
                    return jsonify({
                        "error": "insufficient_scope",
                        "required": permission,
                    }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
