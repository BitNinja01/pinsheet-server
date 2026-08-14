"""API-key permission enforcement (UC-APIKEY-001 / GAP-029).

This module ships the ``@require_permission`` decorator and, as of issue #41, it
is wired onto the rounds / stats / courses API routes so a key is limited to the
scopes it was granted (deny-by-default function-level authZ — OWASP A01 / CWE-862).

Behaviour:
  - Session-authenticated users bypass the scope check (they have full account access).
  - API-key identities (``current_user.via_api_key is True``) must carry the required
    permission in their granted scopes, or the request is rejected with 403.

Runtime authZ layers, outermost-in: authenticated (``@login_required`` runs first, so
an unauthenticated caller gets 401/302 before any scope is evaluated) -> scoped (this
decorator) -> ownership-scoped (existing ``WHERE user_id = ?``) -> non-admin (keys are
forced ``is_admin=False`` in ``main.request_loader``).
"""

from functools import wraps

from flask import jsonify
from flask_login import current_user

# The closed set of v1 permission strings (mirrors store.API_KEY_PERMISSIONS).
VALID_PERMISSIONS = ("rounds:read", "rounds:write", "stats:read", "courses:write")


def require_permission(permission):
    """Decorator gating a route on an API-key permission.

    Apply *below* ``@login_required`` (and above ``@csrf.exempt``) so an
    unauthenticated caller is rejected before the scope is evaluated.
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
