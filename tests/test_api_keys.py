"""Tests for user-bound API-key authentication (UC-APIKEY-001 / GAP-024).

Coverage here is mapped to the use case's acceptance criteria (UC-APIKEY-001 §10),
not just to line counts — every AC-1..AC-16 has at least one test below.

    AC-1  issuance + one-time display     -> test_create_api_key_returns_one_time_plaintext_and_meta
                                             test_management_ui_create_lists_and_revokes
    AC-2  key format / hash-at-rest row   -> test_create_api_key_returns_one_time_plaintext_and_meta
                                             test_hash_at_rest_plaintext_never_persisted
    AC-3  hashed at rest (no plaintext)   -> test_hash_at_rest_plaintext_never_persisted
    AC-4  no secret in logs               -> test_plaintext_never_appears_in_logs
    AC-5  bearer succeeds (200)           -> test_bearer_call_non_admin_returns_200
    AC-6  session still works (no regr.)  -> test_session_auth_unaffected_by_request_loader
                                             test_unauthenticated_web_route_still_redirects
    AC-7  constant-time / unknown key     -> test_unknown_key_returns_none, test_unknown_bearer_returns_401
    AC-8  revocation immediate (401)      -> test_revoked_key_returns_none, test_revoked_bearer_returns_401
    AC-9  owner-scoped revocation         -> test_revoke_is_owner_scoped
    AC-10 expiry enforced                 -> test_expired_key_returns_none, test_expiry_accepts_space_separated_format,
                                             test_future_expiry_still_valid
    AC-11 listing excludes secrets        -> test_list_api_keys_exposes_no_secret, test_list_keys_are_per_user
    AC-12 ownership isolation             -> test_get_user_by_api_key_resolves_owner, test_revoke_is_owner_scoped
    AC-13 admin route denied via key      -> test_admin_route_denied_for_api_key,
                                             test_request_loader_forces_is_admin_false, test_store_layer_sanitizes_is_admin
    AC-14 @require_permission scaffold    -> test_require_permission_scaffold_allows_and_denies
    AC-15 dependency governance           -> test_no_new_dependencies_added
    AC-16 idempotent migration            -> test_init_db_is_idempotent

Revision (eng-qa Step 5, issue #50 / apiv1-issue50-20260814-001): two tests
below were superseded by the accepted `/api/v1` (issue #50) architecture and
are updated here, not deleted -- their SECURITY INTENT is preserved, only
the asserted contract changes:

  - `test_no_new_dependencies_added` (AC-15): the literal "zero new deps"
    assertion predates issue #50, which deliberately adds exactly 4 new
    direct dependencies (`apiflask`, `flask-cors`, `opentelemetry-api`,
    `opentelemetry-sdk` -- each individually justified/pinned/CVE-floored in
    `pyproject.toml` and `eng-lead-apiv1.md` §1). The test now pins the
    dependency-governance INVARIANT that actually matters: the set is
    EXACTLY the pre-v1 baseline 6 plus these 4 named, reviewed additions --
    not silently zero, and not silently unbounded either. A new,
    un-reviewed dependency added by a future PR still fails this test.
  - `test_require_permission_scaffold_allows_and_denies` (AC-14): the old
    `FakeUser` stub predates `auth_keys._audit_would_block` (ADR-004's
    Detect-signal audit log, which reads `current_user.id`) and never set
    `.id`, so the scope-check path raised `AttributeError` on every real
    invocation -- meaning this was the ONLY test in the suite exercising
    `require_permission`'s reject path, and it was silently broken
    (eng-devsecops-apiv1.md L1 §8, flagged P1). Fixed AND expanded to
    additionally cover the full ADR-004 permissive-pending vs.
    `API_SCOPE_ENFORCEMENT`-enforced contract (a real `User`-shaped double
    with `.id` set; asserts the flag-off path logs `scope.would_block` but
    still allows the call, and the flag-on path 403s). Deeper, behavioral
    coverage of this same contract against REAL registered `/api/v1` routes
    (not a decorator applied to a throwaway view) lives in
    `tests/test_api_v1_security.py`.
"""

import hashlib
import logging
from datetime import datetime, timedelta

import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db, get_db
from store import (
    create_user,
    create_api_key,
    list_api_keys,
    revoke_api_key,
    get_user_by_api_key,
)


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fresh Flask app + temp DB. Route registration is idempotent (order-safe)."""
    main_mod.limiter.enabled = False

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "drafts").mkdir()

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["DB_PATH"] = db_path

    try:
        register_routes(app, limiter, csrf, User)
    except AssertionError:
        pass

    return app


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


def _login(test_app, username="player", password="pass1234", display="Player"):
    """Create a user and return a session-authenticated client."""
    user = create_user(username, display, password)
    client = test_app.test_client()
    client.post("/login", data={"username": username, "password": password})
    return client, user


# --------------------------------------------------------------------------- #
# 1. Issuance
# --------------------------------------------------------------------------- #

def test_create_api_key_returns_one_time_plaintext_and_meta(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, meta = create_api_key(user["id"], "Export script", ["rounds:read"])

    assert plaintext.startswith("psk_")
    assert len(plaintext) > 20
    assert meta["prefix"] == plaintext[:12]
    assert meta["label"] == "Export script"
    assert meta["permissions"] == ["rounds:read"]
    assert meta["user_id"] == user["id"]


def test_create_filters_unknown_permissions(test_app):
    user = create_user("alice", "Alice", "pass1234")
    _, meta = create_api_key(user["id"], "k", ["rounds:read", "bogus:scope"])
    assert meta["permissions"] == ["rounds:read"]


# --------------------------------------------------------------------------- #
# 2. Hash-at-rest (plaintext never stored)
# --------------------------------------------------------------------------- #

def test_hash_at_rest_plaintext_never_persisted(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, meta = create_api_key(user["id"], "k", ["rounds:read"])

    db = get_db()
    row = db.execute("SELECT * FROM api_keys WHERE id = ?", (meta["id"],)).fetchone()
    db.close()

    expected_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    assert row["key_hash"] == expected_hash
    # The plaintext appears in no stored column.
    for value in dict(row).values():
        assert value != plaintext
    # Only the non-secret 12-char prefix is stored for display.
    assert row["prefix"] == plaintext[:12]


def test_list_api_keys_exposes_no_secret(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, _ = create_api_key(user["id"], "k", ["rounds:read"])
    keys = list_api_keys(user["id"])
    assert len(keys) == 1
    k = keys[0]
    assert "key_hash" not in k
    assert plaintext not in k.values()
    assert set(k.keys()) == {
        "id", "label", "prefix", "permissions",
        "created_at", "last_used_at", "expires_at", "revoked_at",
    }


# --------------------------------------------------------------------------- #
# 3. Resolution / revocation / expiry / unknown
# --------------------------------------------------------------------------- #

def test_get_user_by_api_key_resolves_owner(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, _ = create_api_key(user["id"], "k", ["rounds:read", "stats:read"])
    resolved = get_user_by_api_key(plaintext)
    assert resolved is not None
    assert resolved["id"] == user["id"]
    assert resolved["permissions"] == ["rounds:read", "stats:read"]


def test_unknown_key_returns_none(test_app):
    create_user("alice", "Alice", "pass1234")
    assert get_user_by_api_key("psk_not_a_real_key") is None
    assert get_user_by_api_key("") is None
    assert get_user_by_api_key("nobearer") is None


def test_revoked_key_returns_none(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, meta = create_api_key(user["id"], "k", ["rounds:read"])
    assert get_user_by_api_key(plaintext) is not None
    assert revoke_api_key(meta["id"], user["id"]) is True
    assert get_user_by_api_key(plaintext) is None


def test_expired_key_returns_none(test_app):
    user = create_user("alice", "Alice", "pass1234")
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    plaintext, _ = create_api_key(user["id"], "k", ["rounds:read"], expires_at=past)
    assert get_user_by_api_key(plaintext) is None


# --------------------------------------------------------------------------- #
# 4. Ownership isolation
# --------------------------------------------------------------------------- #

def test_revoke_is_owner_scoped(test_app):
    user_a = create_user("alice", "Alice", "pass1234")   # first user -> admin
    user_b = create_user("bob", "Bob", "pass1234")
    plaintext_b, meta_b = create_api_key(user_b["id"], "b-key", ["rounds:read"])

    # Alice cannot revoke Bob's key.
    assert revoke_api_key(meta_b["id"], user_a["id"]) is False
    # Bob's key still works.
    assert get_user_by_api_key(plaintext_b) is not None


def test_list_keys_are_per_user(test_app):
    user_a = create_user("alice", "Alice", "pass1234")
    user_b = create_user("bob", "Bob", "pass1234")
    create_api_key(user_a["id"], "a-key", [])
    create_api_key(user_b["id"], "b-key", [])
    assert len(list_api_keys(user_a["id"])) == 1
    assert list_api_keys(user_a["id"])[0]["label"] == "a-key"


# --------------------------------------------------------------------------- #
# Integration — bearer auth over the live route stack
# --------------------------------------------------------------------------- #

def test_bearer_call_non_admin_returns_200(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, _ = create_api_key(user["id"], "k", ["rounds:read"])
    client = test_app.test_client()
    resp = client.get("/api/drafts/round", headers=_bearer(plaintext))
    assert resp.status_code == 200


def test_revoked_bearer_returns_401(test_app):
    user = create_user("alice", "Alice", "pass1234")
    plaintext, meta = create_api_key(user["id"], "k", ["rounds:read"])
    revoke_api_key(meta["id"], user["id"])
    client = test_app.test_client()
    resp = client.get("/api/drafts/round", headers=_bearer(plaintext))
    assert resp.status_code == 401


def test_unknown_bearer_returns_401(test_app):
    create_user("alice", "Alice", "pass1234")
    client = test_app.test_client()
    resp = client.get("/api/drafts/round", headers=_bearer("psk_bogus"))
    assert resp.status_code == 401


def test_admin_route_denied_for_api_key(test_app):
    # First user is auto-admin; a key derived from that admin must still be denied.
    admin = create_user("admin", "Admin", "pass1234")
    plaintext, _ = create_api_key(admin["id"], "k", [])
    client = test_app.test_client()
    resp = client.post(
        "/api/admin/plugin-state",
        json={"plugin_name": "x", "enabled": True},
        headers=_bearer(plaintext),
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# 5. Session-still-works regression
# --------------------------------------------------------------------------- #

def test_session_auth_unaffected_by_request_loader(test_app):
    client, _ = _login(test_app)
    # Same endpoint, but via session cookie and no bearer header.
    resp = client.get("/api/drafts/round")
    assert resp.status_code == 200


def test_unauthenticated_web_route_still_redirects(test_app):
    # No bearer header -> the web UI keeps its 302 -> login behaviour (not 401).
    client = test_app.test_client()
    resp = client.get("/api/drafts/round")
    assert resp.status_code == 302


# --------------------------------------------------------------------------- #
# Management UI (session-only)
# --------------------------------------------------------------------------- #

def test_management_ui_create_lists_and_revokes(test_app):
    client, user = _login(test_app)

    # Create
    resp = client.post("/settings/api-keys", data={"label": "CI", "permissions": "rounds:read"})
    assert resp.status_code == 200
    assert b"psk_" in resp.data           # one-time plaintext shown

    # List
    resp = client.get("/settings/api-keys")
    assert resp.status_code == 200
    keys = list_api_keys(user["id"])
    assert len(keys) == 1
    assert keys[0]["label"] == "CI"

    # Revoke
    resp = client.post(f"/settings/api-keys/{keys[0]['id']}/revoke")
    assert resp.status_code in (302, 200)
    assert list_api_keys(user["id"])[0]["revoked_at"] is not None


def test_management_ui_requires_login(test_app):
    client = test_app.test_client()
    resp = client.get("/settings/api-keys")
    assert resp.status_code == 302   # redirect to login


# --------------------------------------------------------------------------- #
# Hardening (post-adversary): admin denial, expiry-format robustness
# --------------------------------------------------------------------------- #

def test_request_loader_forces_is_admin_false(test_app):
    import flask
    admin = create_user("admin", "Admin", "pass1234")   # first user -> admin
    plaintext, _ = create_api_key(admin["id"], "k", [])
    with test_app.test_request_context(headers={"Authorization": f"Bearer {plaintext}"}):
        user = main_mod._load_user_from_request(flask.request)
        assert user is not None
        assert user.is_admin is False
        assert user.via_api_key is True


def test_store_layer_sanitizes_is_admin(test_app):
    admin = create_user("admin", "Admin", "pass1234")   # admin in DB
    plaintext, _ = create_api_key(admin["id"], "k", [])
    resolved = get_user_by_api_key(plaintext)
    assert resolved["is_admin"] is False   # sanitized even in the raw dict


def test_expiry_accepts_space_separated_format(test_app):
    user = create_user("alice", "Alice", "pass1234")
    past = (datetime.utcnow() - timedelta(days=1)).isoformat().replace("T", " ")
    plaintext, _ = create_api_key(user["id"], "k", [], expires_at=past)
    assert get_user_by_api_key(plaintext) is None   # space-separated expiry honored


def test_future_expiry_still_valid(test_app):
    user = create_user("alice", "Alice", "pass1234")
    future = (datetime.utcnow() + timedelta(days=30)).isoformat()
    plaintext, _ = create_api_key(user["id"], "k", [], expires_at=future)
    assert get_user_by_api_key(plaintext) is not None


# --------------------------------------------------------------------------- #
# AC-4 / AC-14 / AC-15 / AC-16 — criteria that need dedicated, UC-mapped tests
# --------------------------------------------------------------------------- #

def test_plaintext_never_appears_in_logs(test_app, caplog):
    """AC-4: no log line (creation or auth attempt) contains the plaintext key."""
    user = create_user("alice", "Alice", "pass1234")
    with caplog.at_level(logging.DEBUG, logger="pinsheet"):
        plaintext, _ = create_api_key(user["id"], "k", ["rounds:read"])
        get_user_by_api_key(plaintext)          # successful auth
        get_user_by_api_key("psk_wrong_key")    # failed auth
    assert plaintext not in caplog.text


def test_require_permission_scaffold_allows_and_denies(test_app, monkeypatch, caplog):
    """AC-14 (ADR-004 permissive-pending + enforced contract, updated per
    eng-devsecops-apiv1.md L1 §8 P1 finding): the decorator is functional in
    isolation -- passes when the permission is present, session (non-key)
    identities always bypass, and the reject-path behavior depends on
    `API_SCOPE_ENFORCEMENT`:
      - flag OFF (permissive-pending, the default): a missing scope is
        AUDITED (`scope.would_block`) but the call still succeeds.
      - flag ON (enforced): a missing scope is rejected with 403.

    `FakeUser` sets `.id` and `.prefix` (unlike the pre-fix stub) so the
    `_audit_would_block` audit-log call -- which reads both -- does not
    raise; this is the fix for the AttributeError that left this test's
    reject-path assertion silently non-functional against real objects."""
    import auth_keys

    @auth_keys.require_permission("rounds:read")
    def view():
        return "ok"

    class FakeUser:
        pass

    granted = FakeUser(); granted.via_api_key = True; granted.api_permissions = ["rounds:read"]
    granted.id = 1; granted.prefix = "psk_test1234"
    missing = FakeUser(); missing.via_api_key = True; missing.api_permissions = ["stats:read"]
    missing.id = 2; missing.prefix = "psk_test5678"
    session_user = FakeUser()  # no via_api_key attr -> treated as session user

    with test_app.test_request_context():
        monkeypatch.setattr(auth_keys, "current_user", granted)
        assert view() == "ok"                       # key has the scope

        monkeypatch.setattr(auth_keys, "current_user", session_user)
        assert view() == "ok"                       # session users bypass the scaffold

        # --- permissive-pending (flag OFF, the default) ---
        monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", False)
        monkeypatch.setattr(auth_keys, "current_user", missing)
        with caplog.at_level(logging.WARNING, logger="pinsheet"):
            result = view()                          # key lacks the scope, but flag is off
        assert result == "ok", "permissive-pending must never reject on a missing scope"
        assert any("scope.would_block" in rec.message for rec in caplog.records)
        caplog.clear()

        # --- enforced (flag ON) ---
        monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", True)
        body, status = view()                        # key lacks the scope, flag is on
        assert status == 403

        # enforced mode still allows a key that DOES have the scope
        monkeypatch.setattr(auth_keys, "current_user", granted)
        assert view() == "ok"


def test_no_new_dependencies_added(test_app):
    """AC-15 (dependency governance, updated for issue #50): the pre-v1
    baseline was 6 direct dependencies (stdlib + Flask-Login only). Issue
    #50 (/api/v1) deliberately adds exactly 4 more -- `apiflask`,
    `flask-cors` (CVE-floored >=6.0.0, see eng-lead-apiv1.md §1), and the
    exact-pinned `opentelemetry-api`/`opentelemetry-sdk` no-op tracing pair
    (ADR-003). This test now pins the FULL, exact expected dependency set
    (baseline + the 4 reviewed additions) rather than asserting zero
    growth -- any OTHER new, un-reviewed dependency added by a future PR
    still fails this test, preserving the original security intent
    (no silent dependency-supply-chain growth) without contradicting the
    accepted v1 architecture."""
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text())
    names = sorted(
        d.split(">")[0].split("=")[0].split("[")[0].strip().lower()
        for d in data["project"]["dependencies"]
    )
    # dev added werkzeug (#76 request-size bounding); #50 adds the 4 v1 deps.
    baseline = ["flask", "werkzeug", "waitress", "bcrypt", "flask-login", "flask-limiter", "flask-wtf"]
    apiv1_additions_4 = ["apiflask", "flask-cors", "opentelemetry-api", "opentelemetry-sdk"]
    assert names == sorted(baseline + apiv1_additions_4)


def test_init_db_is_idempotent(test_app):
    """AC-16: re-running init_db() does not error and the api_keys table persists."""
    from database import init_db, get_db
    init_db()  # second run on an already-initialised DB
    db = get_db()
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'"
    ).fetchone()
    db.close()
    assert row is not None
