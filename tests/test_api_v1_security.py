"""Security regression tests for `/api/v1` (issue #50, eng-qa Step 5).

Closes the eng-devsecops P1 traceability gap (`eng-devsecops-apiv1.md` L1
§8): four §5 concern classes -- AuthZ/scopes (ADR-004), IDOR (ADR-009), CORS
(ADR-005), rate-limiting (ADR-006) -- had ZERO passing automated coverage
before this file. Each concern gets its own section below, cross-referenced
to the devsecops report row it closes.

Also implements the scopes.py-mandated regression
(`source/routes/api_v1/scopes.py` module docstring): "eng-qa's
`test_every_v1_route_has_required_scope` (Step 5) iterates `app.url_map` for
every `/api/v1/*` rule and asserts it appears [in ENDPOINT_SCOPE_MAP] exactly
once" -- closing the "new route added without a scope decorator" regression
class.

AC traceability (issue #50 / eng-lead §5, eng-lead-apiv1.md §7 acceptance
matrix):
    AuthZ/scopes permissive-pending -> test_permissive_pending_missing_scope_still_succeeds_and_audits
    AuthZ/scopes enforced-mode deny -> test_enforced_mode_missing_scope_returns_403_problem_json
    AuthZ/scopes enforced-mode allow -> test_enforced_mode_present_scope_succeeds
    AuthZ/scopes route coverage      -> test_every_v1_route_has_required_scope
    IDOR (ADR-009)                   -> test_idor_get_put_delete_foreign_round_returns_404_no_oracle
    IDOR list-scoping                -> test_idor_list_rounds_never_returns_other_users_rounds
    CORS (ADR-005)                   -> test_cors_allowed_origin_reflected_in_acao,
                                         test_cors_unset_origins_no_acao_header
    Rate limiting (ADR-006)          -> test_rate_limit_429_problem_json_on_v1_write_budget,
                                         test_rate_limit_does_not_affect_legacy_routes
"""
import logging

import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from source.routes.api_v1 import register_api_v1
from source.routes.api_v1 import scopes as scopes_mod
import source.auth_keys as auth_keys  # NOTE: must be `source.auth_keys`, not the
# bare top-level `auth_keys` module -- `pyproject.toml`'s `pythonpath =
# ["source"]` makes BOTH import spellings resolve to real, but DIFFERENT,
# `sys.modules` entries (confirmed empirically: `import auth_keys as a1;
# import source.auth_keys as a2; a1 is a2` -> `False`). The real, registered
# `/api/v1` routes are wired via `source/routes/api_v1/rounds.py`'s
# `from source.auth_keys import require_permission` -- so ONLY
# `monkeypatch.setattr(source.auth_keys, "API_SCOPE_ENFORCEMENT", ...)`
# actually affects what a live request sees; patching the bare `auth_keys`
# module (as `tests/test_api_keys.py`'s pre-existing scaffold test does) is a
# silent no-op against real routes. This was DISCOVERED, not assumed, while
# writing this file -- see the eng-qa report for the real-bug writeup.
from database import set_db_path, init_db
from store import create_user, create_api_key, API_KEY_PERMISSIONS


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fresh temp DB + idempotent route/blueprint registration (mirrors
    `test_api_v1.py::test_app`). Rate-limit tests override
    `limiter.enabled` themselves; every other test in this file disables it
    for determinism, matching repo convention."""
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
    try:
        register_api_v1(app, limiter, csrf)
    except AssertionError:
        pass

    yield app

    # Always restore the limiter to disabled + real enforcement flag to its
    # imported default, so a rate-limit test never leaks state into a test
    # in another file/module that runs later in the same session.
    main_mod.limiter.enabled = False


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


def _key_client(test_app, permissions, username="golfer"):
    """A user + a psk_ key granted exactly `permissions` + its test client."""
    user = create_user(username, username.title(), "pass1234")
    plaintext, meta = create_api_key(user["id"], "scoped key", list(permissions))
    client = test_app.test_client()
    return client, _bearer(plaintext), user


VALID_ROUND = {
    "date": "2026-05-01",
    "course": "Pebble Beach",
    "tees": "White",
    "entry_mode": "detailed",
    "holes_played": "18",
    "holes": {
        "1": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},
    },
    "notes": "opening round",
}


# --------------------------------------------------------------------------- #
# AuthZ/scopes -- ADR-004 permissive-pending + enforced-mode contract
# devsecops row: "AuthZ / scopes" -- GAP, zero passing coverage before this.
# --------------------------------------------------------------------------- #


def test_permissive_pending_missing_scope_still_succeeds_and_audits(test_app, monkeypatch, caplog):
    """Flag OFF (default): a key WITHOUT rounds:read still gets 200, and a
    `scope.would_block` audit record is emitted (ADR-004 Detect signal)."""
    monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", False)
    client, headers, user = _key_client(test_app, permissions=["courses:read"])  # no rounds:read

    with caplog.at_level(logging.WARNING, logger="pinsheet"):
        r = client.get("/api/v1/rounds", headers=headers)

    assert r.status_code == 200, "permissive-pending must never reject on a missing scope"
    assert any("scope.would_block" in rec.message for rec in caplog.records), (
        "missing scope must still be audited (ADR-004 PM-001 Detect signal), "
        "even though the request is allowed through"
    )
    would_block = next(rec for rec in caplog.records if "scope.would_block" in rec.message)
    assert "required_scope=rounds:read" in would_block.message
    assert "enforcement=pending" in would_block.message


def test_permissive_pending_present_scope_succeeds_no_audit(test_app, monkeypatch, caplog):
    """A key WITH the scope succeeds and does not spuriously audit-log."""
    monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", False)
    client, headers, user = _key_client(test_app, permissions=["rounds:read"])

    with caplog.at_level(logging.WARNING, logger="pinsheet"):
        r = client.get("/api/v1/rounds", headers=headers)

    assert r.status_code == 200
    assert not any("scope.would_block" in rec.message for rec in caplog.records)


def test_enforced_mode_missing_scope_returns_403_problem_json(test_app, monkeypatch):
    """Flag ON: a key missing the required scope is rejected -- 403,
    application/problem+json, RFC 9457 shape."""
    monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", True)
    client, headers, user = _key_client(test_app, permissions=["courses:read"])  # no rounds:read

    r = client.get("/api/v1/rounds", headers=headers)

    assert r.status_code == 403
    assert r.mimetype == "application/problem+json"
    body = r.get_json()
    assert set(body) >= {"type", "title", "status", "detail", "instance", "traceId"}
    assert body["status"] == 403
    assert body["title"] == "Insufficient scope"


def test_enforced_mode_present_scope_succeeds(test_app, monkeypatch):
    """Flag ON: a key WITH the required scope still succeeds normally."""
    monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", True)
    client, headers, user = _key_client(test_app, permissions=["rounds:read"])

    r = client.get("/api/v1/rounds", headers=headers)

    assert r.status_code == 200
    assert r.get_json() == {"rounds": []}


def test_enforced_mode_write_scope_gate_on_create_round(test_app, monkeypatch):
    """Enforced mode also gates the write path, not just reads: a key with
    only rounds:read cannot POST /api/v1/rounds."""
    monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", True)
    client, headers, user = _key_client(test_app, permissions=["rounds:read"])

    r = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)

    assert r.status_code == 403
    assert r.mimetype == "application/problem+json"


def test_session_user_bypasses_scope_check_in_enforced_mode(test_app, monkeypatch):
    """Session-authenticated (full-account trust) users are never scope-gated,
    enforced mode or not (ADR-004: `require_permission` governs API-KEY
    identities only)."""
    monkeypatch.setattr(auth_keys, "API_SCOPE_ENFORCEMENT", True)
    create_user("sessionuser", "Session User", "pass1234")
    client = test_app.test_client()
    login_resp = client.post(
        "/login", data={"username": "sessionuser", "password": "pass1234"}
    )
    assert login_resp.status_code in (200, 302), "login precondition must succeed"

    r = client.get("/api/v1/rounds")
    assert r.status_code == 200


def test_every_v1_route_has_required_scope(test_app):
    """Named regression from `scopes.py`'s own module docstring: every
    registered `/api/v1/*` rule must appear in `ENDPOINT_SCOPE_MAP` exactly
    once, so a future route can never ship without a scope decorator wired
    through `require_permission`."""
    v1_endpoints = {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/v1/")
        and rule.endpoint not in ("openapi.spec", "openapi.docs", "api_v1_redoc")
        and "static" not in rule.endpoint
    }
    assert v1_endpoints, "sanity: v1 routes must be registered for this test to mean anything"
    mapped = set(scopes_mod.ENDPOINT_SCOPE_MAP)
    missing = v1_endpoints - mapped
    stale = mapped - v1_endpoints
    assert not missing, f"v1 route(s) with no scope mapping (unscoped route regression): {missing}"
    assert not stale, f"ENDPOINT_SCOPE_MAP has stale entries for routes that no longer exist: {stale}"


# --------------------------------------------------------------------------- #
# IDOR -- ADR-009 owner-scoped rounds, no existence oracle
# devsecops row: "IDOR" -- GAP, zero passing coverage before this.
# --------------------------------------------------------------------------- #


def test_idor_get_put_delete_foreign_round_returns_404_no_oracle(test_app):
    """User A creates a round; user B's key attempts GET/PUT/DELETE on it.
    All three must 404 (Problem Details), identically to a genuinely-missing
    id -- i.e. no existence oracle leaks whether the round belongs to
    someone else vs. simply not existing."""
    client_a, headers_a, user_a = _key_client(test_app, list(API_KEY_PERMISSIONS), username="alice")
    client_b, headers_b, user_b = _key_client(test_app, list(API_KEY_PERMISSIONS), username="bob")

    r = client_a.post("/api/v1/rounds", json=VALID_ROUND, headers=headers_a)
    assert r.status_code == 201
    round_id = r.get_json()["id"]

    # Baseline: a definitely-nonexistent id, from B, as the oracle-parity control.
    nonexistent_id = round_id + 999999
    r_missing = client_b.get(f"/api/v1/rounds/{nonexistent_id}", headers=headers_b)

    # GET
    r_get = client_b.get(f"/api/v1/rounds/{round_id}", headers=headers_b)
    assert r_get.status_code == 404
    assert r_get.mimetype == "application/problem+json"
    assert r_get.get_json()["detail"] == r_missing.get_json()["detail"], (
        "foreign-owned round must be byte-identical in response body to a "
        "genuinely missing round -- no existence oracle"
    )

    # PUT
    r_put = client_b.put(f"/api/v1/rounds/{round_id}", json={"notes": "pwned"}, headers=headers_b)
    assert r_put.status_code == 404
    assert r_put.mimetype == "application/problem+json"

    # DELETE
    r_del = client_b.delete(f"/api/v1/rounds/{round_id}", headers=headers_b)
    assert r_del.status_code == 404
    assert r_del.mimetype == "application/problem+json"

    # Confirm none of B's attempts actually mutated/removed A's round.
    r_confirm = client_a.get(f"/api/v1/rounds/{round_id}", headers=headers_a)
    assert r_confirm.status_code == 200
    assert r_confirm.get_json()["notes"] == "opening round"


def test_idor_list_rounds_never_returns_other_users_rounds(test_app):
    """GET /api/v1/rounds (list) is filtered server-side by current_user.id --
    B's list must never contain A's round, even by id leakage."""
    client_a, headers_a, user_a = _key_client(test_app, list(API_KEY_PERMISSIONS), username="alice2")
    client_b, headers_b, user_b = _key_client(test_app, list(API_KEY_PERMISSIONS), username="bob2")

    r = client_a.post("/api/v1/rounds", json=VALID_ROUND, headers=headers_a)
    assert r.status_code == 201
    a_round_id = r.get_json()["id"]

    r_list_b = client_b.get("/api/v1/rounds", headers=headers_b)
    assert r_list_b.status_code == 200
    b_ids = {rnd["id"] for rnd in r_list_b.get_json()["rounds"]}
    assert a_round_id not in b_ids


# --------------------------------------------------------------------------- #
# CORS -- ADR-005 v1-scoped, default-deny
# devsecops row: "CORS" -- GAP, zero automated coverage (neither scan nor test).
# --------------------------------------------------------------------------- #


def _build_cors_probe_app(monkeypatch, origins_csv):
    """Exercise the REAL `source.extensions.init_cors` function (the exact
    code `main.py` calls) against a throwaway Flask app with stub `/api/v1/
    rounds` and `/login`-shaped routes.

    Deliberately does NOT reuse the process-wide `main.app` singleton:
    `init_cors` calls `flask_cors.CORS(app, ...)`, which registers an
    `after_request` hook -- Flask permanently forbids new setup calls
    (`app.after_request(...)`) once an app has served its first request
    (`_check_setup_finished`), and by the time this file's fixtures run in
    the full suite, `main.app` has already served requests from earlier
    test files in the same pytest session. A fresh app per test sidesteps
    that entirely while still calling the identical `init_cors(app)`
    function under test, so this remains a true test of the shipped CORS
    wiring logic, not a reimplementation of it."""
    from flask import Flask
    from source.extensions import init_cors

    if origins_csv is None:
        monkeypatch.delenv("API_CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("API_CORS_ORIGINS", origins_csv)

    probe = Flask(__name__)
    probe.config["TESTING"] = True

    @probe.route("/api/v1/rounds", methods=["GET"])
    def _v1_stub():
        return "ok"

    @probe.route("/login", methods=["GET"])
    def _legacy_stub():
        return "ok"

    init_cors(probe)
    return probe


def test_cors_allowed_origin_reflected_in_acao(monkeypatch):
    """API_CORS_ORIGINS set to an allowed origin -> a preflight OPTIONS
    request from that exact origin gets Access-Control-Allow-Origin back."""
    probe = _build_cors_probe_app(monkeypatch, "https://allowed.example.com")

    r = probe.test_client().options(
        "/api/v1/rounds",
        headers={
            "Origin": "https://allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("Access-Control-Allow-Origin") == "https://allowed.example.com"


def test_cors_disallowed_origin_no_acao_even_when_others_configured(monkeypatch):
    """A different, non-listed origin gets NO Access-Control-Allow-Origin,
    even though the allow-list is non-empty for a different origin."""
    probe = _build_cors_probe_app(monkeypatch, "https://allowed.example.com")

    r = probe.test_client().options(
        "/api/v1/rounds",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("Access-Control-Allow-Origin") is None


def test_cors_unset_origins_no_acao_header(monkeypatch):
    """API_CORS_ORIGINS unset -> default-deny: NO
    Access-Control-Allow-Origin header on a cross-origin preflight to any
    /api/v1/* route."""
    probe = _build_cors_probe_app(monkeypatch, None)

    r = probe.test_client().options(
        "/api/v1/rounds",
        headers={
            "Origin": "https://anything.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("Access-Control-Allow-Origin") is None
    assert "Access-Control-Allow-Origin" not in r.headers


def test_cors_empty_string_origins_no_acao_header(monkeypatch):
    """API_CORS_ORIGINS="" (explicitly set but empty) behaves the same as
    unset -- default-deny, not 'allow everything'."""
    probe = _build_cors_probe_app(monkeypatch, "")

    r = probe.test_client().options(
        "/api/v1/rounds",
        headers={
            "Origin": "https://anything.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("Access-Control-Allow-Origin") is None


def test_cors_not_applied_to_legacy_routes(monkeypatch):
    """ADR-005: CORS is /api/v1-scoped only (`resources={r"/api/v1/*": ...}`)
    -- a legacy route must never reflect an Access-Control-Allow-Origin
    header, even for an allow-listed v1 origin."""
    probe = _build_cors_probe_app(monkeypatch, "https://allowed.example.com")

    r = probe.test_client().options(
        "/login",
        headers={
            "Origin": "https://allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("Access-Control-Allow-Origin") is None


def test_cors_supports_credentials_false_and_no_wildcard_with_origins_set(monkeypatch):
    """ADR-005: bearer-header auth, not cookies -- `supports_credentials`
    must be False (not env-configurable) even when an allow-list is
    configured, and the allow-listed origin must be reflected literally,
    never as a `*` wildcard (which flask-cors would only emit for
    `origins="*"`, never used here)."""
    probe = _build_cors_probe_app(monkeypatch, "https://allowed.example.com")

    r = probe.test_client().options(
        "/api/v1/rounds",
        headers={
            "Origin": "https://allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("Access-Control-Allow-Origin") != "*"
    assert r.headers.get("Access-Control-Allow-Credentials") != "true"


# --------------------------------------------------------------------------- #
# Rate limiting -- ADR-006, v1-only budgets
# devsecops row: "Rate limiting" -- GAP (limiter disabled in every other
# test file, by design, for speed/determinism).
# --------------------------------------------------------------------------- #


def test_rate_limit_429_problem_json_on_v1_write_budget(test_app, monkeypatch):
    """With the limiter re-enabled and a tiny write budget monkeypatched in,
    exceeding it returns 429 application/problem+json from the v1 error
    handler (not flask-limiter's own default HTML/plain response)."""
    import source.routes.api_v1 as api_v1_pkg

    monkeypatch.setattr(api_v1_pkg, "WRITE_BUDGET", "2 per hour")
    # Route re-registration already happened in the test_app fixture using
    # the ORIGINAL WRITE_BUDGET module constant (read at register_api_v1
    # call time, not per-request) -- so re-register a throwaway limiter
    # wrapper directly on the view function to exercise the SAME budget
    # value this test controls, using the identical wiring mechanism
    # `register_api_v1` itself uses (`limiter.limit(budget, key_func=...)`
    # applied to `app.view_functions[endpoint]`).
    from source.extensions import api_v1_key_func

    endpoint = "rounds_v1.create_round"
    original_view = main_mod.app.view_functions[endpoint]
    main_mod.limiter.enabled = True
    limited_view = main_mod.limiter.limit("2 per hour", key_func=api_v1_key_func)(original_view)
    main_mod.app.view_functions[endpoint] = limited_view

    try:
        client, headers, user = _key_client(test_app, list(API_KEY_PERMISSIONS), username="burst")

        responses = [
            client.post("/api/v1/rounds", json={**VALID_ROUND, "date": f"2026-05-0{i+1}"}, headers=headers)
            for i in range(3)
        ]
        statuses = [r.status_code for r in responses]
        assert 201 in statuses, "the first request(s) within budget must still succeed"
        assert 429 in statuses, f"a 3rd request against a 2-per-hour budget must be rate-limited, got {statuses}"

        limited_resp = responses[statuses.index(429)]
        assert limited_resp.mimetype == "application/problem+json", (
            "a 429 on a v1 route must be shaped as Problem Details, not "
            "flask-limiter's default response"
        )
        body = limited_resp.get_json()
        assert body["status"] == 429
    finally:
        main_mod.app.view_functions[endpoint] = original_view
        main_mod.limiter.enabled = False


def test_rate_limit_does_not_affect_legacy_routes(test_app, monkeypatch):
    """The v1 rate-limit budgets are wired ONLY onto v1 blueprint view
    functions (`register_api_v1`'s own `bp_prefixes` filter) -- a burst of
    requests against a legacy route with no `@limiter.limit(...)` of its own
    must never 429, even with the limiter globally enabled, because
    `Limiter(..., default_limits=[])` applies no limit anywhere except
    routes explicitly wrapped.

    Uses `/` (dashboard), not `/login` -- `/login` carries its OWN
    pre-existing, legacy `@limiter.limit("15 per minute")` (`auth.py:11`,
    brute-force protection, unrelated to v1) which would 429 on its own and
    give a false read on whether v1 budgets specifically are leaking."""
    user = create_user("legacyburst", "Legacy Burst", "pass1234")
    client = test_app.test_client()
    login_resp = client.post("/login", data={"username": "legacyburst", "password": "pass1234"})
    assert login_resp.status_code in (200, 302)

    main_mod.limiter.enabled = True
    try:
        statuses = [client.get("/").status_code for _ in range(25)]
        assert all(s == 200 for s in statuses), (
            f"legacy '/' must never be rate-limited by the v1 budgets, got {set(statuses)}"
        )
    finally:
        main_mod.limiter.enabled = False
