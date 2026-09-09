"""Tests for the `/api/v1` REST surface (issue #50).

Coverage focus (this file, not exhaustive -- eng-qa Step 5 owns the full
~20-test acceptance matrix named in the eng-architect/eng-lead docs):

- Issue #50's own acceptance round-trip: an authenticated `psk_` key creates
  a round via `POST /api/v1/rounds`, reads it back via `GET`, and a bad
  request returns `application/problem+json` in the documented RFC 9457
  shape.
- Regression coverage for the 2 Revision-1 coordinator-flagged fixes:
  - DA-1 (course location field-name corruption): a course created via v1
    persists the literal legacy wire key `"state/province"`, not the
    marshmallow field name `state_province`.
  - PM-1 (round `id` churn on PUT): a `PUT` no longer changes the round's
    `id`, and retrying a `PUT` against the id from BEFORE the retry attempt
    does not produce a spurious 404.
- `RoundCreateInSchema` is treated as authoritative for accepted field names
  (coordinated with the frontend fix: `entry_mode`, `holes_played`, no
  `total_gross` in the request body -- `total_gross` is a STORED/computed
  field, never an input field; the input field for a manual total is
  `gross_total`).

Follows the existing repo idiom (see `test_api_keys.py`): the app is a
process-wide singleton (`main.py`'s module-level `app`), so blueprint/route
registration is guarded with `try/except AssertionError` for idempotency
across the whole pytest session.
"""
import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from source.routes.api_v1 import register_api_v1
from source.routes.api_v1.schemas import RoundCreateInSchema
from database import set_db_path, init_db
from store import create_user, create_api_key, get_courses, API_KEY_PERMISSIONS


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fresh temp DB + idempotent route/blueprint registration on the shared
    module-level app (mirrors `test_api_keys.py::test_app`)."""
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

    return app


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


def _full_scope_client(test_app, username="golfer"):
    """A user + a psk_ key granted every scope + its test client."""
    user = create_user(username, username.title(), "pass1234")
    plaintext, meta = create_api_key(user["id"], "full key", list(API_KEY_PERMISSIONS))
    client = test_app.test_client()
    return client, _bearer(plaintext), user


def _scoped_client(test_app, username, perms):
    """A user + a psk_ key granted exactly `perms` + its test client."""
    user = create_user(username, username.title(), "pass1234")
    plaintext, meta = create_api_key(user["id"], "scoped key", perms)
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
# Issue #50 acceptance round-trip
# --------------------------------------------------------------------------- #


def test_v1_round_trip_create_and_get(test_app):
    client, headers, user = _full_scope_client(test_app)

    r = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)
    assert r.status_code == 201
    assert r.mimetype == "application/json"
    created = r.get_json()
    assert created["date"] == "2026-05-01"
    assert created["course"] == "Pebble Beach"
    assert created["notes"] == "opening round"
    round_id = created["id"]

    r2 = client.get(f"/api/v1/rounds/{round_id}", headers=headers)
    assert r2.status_code == 200
    fetched = r2.get_json()
    assert fetched == created


def test_v1_bad_request_returns_problem_json_documented_shape(test_app):
    client, headers, user = _full_scope_client(test_app)

    # missing required `date` field
    r = client.post("/api/v1/rounds", json={"course": "Pebble Beach"}, headers=headers)
    assert r.status_code in (400, 422)
    assert r.mimetype == "application/problem+json"
    body = r.get_json()
    assert set(body) >= {"type", "title", "status", "detail", "instance", "traceId"}
    assert body["status"] == r.status_code
    assert body["instance"] == "/api/v1/rounds"
    assert isinstance(body["traceId"], str) and len(body["traceId"]) >= 16


def test_v1_anonymous_request_returns_401_problem_json(test_app):
    client = test_app.test_client()
    r = client.get("/api/v1/rounds")
    assert r.status_code == 401
    assert r.mimetype == "application/problem+json"
    body = r.get_json()
    assert set(body) >= {"type", "title", "status", "detail", "instance", "traceId"}


# --------------------------------------------------------------------------- #
# Revision 1 regression: DA-1 (course location field-name corruption)
# --------------------------------------------------------------------------- #


def test_location_state_province_key_roundtrip(test_app):
    """A course created via v1 must persist the literal legacy wire key
    `"state/province"` in the stored JSON blob -- NOT the marshmallow field
    name `state_province` -- so the shared legacy `course_detail.html`
    (`.get("state/province")`) and legacy JS (`courses.html:335`) keep
    reading a populated value, not a silently-corrupted blank field."""
    client, headers, user = _full_scope_client(test_app)

    course_payload = {
        "name": "Augusta National",
        "location": {"city": "Augusta", "state/province": "GA", "country": "US"},
        "holes": {},
        "par": 72,
    }
    r = client.post("/api/v1/courses", json=course_payload, headers=headers)
    assert r.status_code == 201
    body = r.get_json()
    assert body["location"]["state/province"] == "GA"
    assert "state_province" not in body["location"]

    # Assert directly against the persisted store row -- what
    # course_detail.html/courses.html actually read.
    stored = get_courses()["Augusta National"]
    assert stored["location"]["state/province"] == "GA"
    assert "state_province" not in stored["location"]


def test_location_missing_field_still_422(test_app):
    """The @post_load re-key must not bypass the `required=True` validation
    on state_province -- a body missing it is still rejected."""
    client, headers, user = _full_scope_client(test_app)
    r = client.post(
        "/api/v1/courses",
        json={"name": "X", "location": {"city": "Y", "country": "Z"}},
        headers=headers,
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Revision 1 regression: PM-1 (round id churn on PUT breaks client retries)
# --------------------------------------------------------------------------- #


def test_put_round_preserves_id_and_retry_is_safe(test_app):
    client, headers, user = _full_scope_client(test_app)

    r = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)
    assert r.status_code == 201
    original_id = r.get_json()["id"]

    r2 = client.put(f"/api/v1/rounds/{original_id}", json={"notes": "revised"}, headers=headers)
    assert r2.status_code == 200
    updated = r2.get_json()
    assert updated["id"] == original_id, "PUT must not churn the round's id (PM-1 fix)"
    assert updated["notes"] == "revised"

    # Simulate a client retry: re-PUT using the SAME (original) id after a
    # dropped response. Must reconcile to the current row, not 404.
    r3 = client.put(f"/api/v1/rounds/{original_id}", json={"notes": "revised"}, headers=headers)
    assert r3.status_code == 200, "retrying a PUT with the original id must not produce a spurious 404"
    assert r3.get_json()["id"] == original_id


def test_put_round_partial_update_preserves_unspecified_fields(test_app):
    """D-5 regression: a PUT that only sends `notes` must not blank
    `course`/`tees`/`total_gross`/etc."""
    client, headers, user = _full_scope_client(test_app)
    r = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)
    round_id = r.get_json()["id"]

    r2 = client.put(f"/api/v1/rounds/{round_id}", json={"notes": "only notes"}, headers=headers)
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["course"] == "Pebble Beach"
    assert body["tees"] == "White"
    assert body["notes"] == "only notes"


# --------------------------------------------------------------------------- #
# RoundCreateInSchema is authoritative for accepted field names
# --------------------------------------------------------------------------- #


def test_round_create_schema_accepted_fields_are_exactly_documented(test_app):
    """Coordinated with the frontend fix: the SPA sends `entry_mode`,
    `holes_played`, and no longer sends `total_gross` (a computed/stored
    field, never accepted as v1 input -- the input field for a manual score
    total is `gross_total`). This test pins the schema's exact accepted
    field set so a future accidental field rename/addition is caught here,
    not discovered by a client integration failure."""
    accepted = set(RoundCreateInSchema().fields.keys())
    assert accepted == {
        "date", "course", "tees", "holes_played", "transport",
        "entry_mode", "notes", "holes", "gross_total", "excluded",
    }
    # Privileged/computed fields must never be among them.
    assert "total_gross" not in accepted
    assert "user_id" not in accepted
    assert "id" not in accepted
    assert "computed_handicap" not in accepted
    assert "differential" not in accepted
    assert "differential_locked" not in accepted


def test_round_create_extra_and_computed_fields_dropped_not_bound(test_app):
    client, headers, user = _full_scope_client(test_app)
    payload = {
        **VALID_ROUND,
        "total_gross": "999",       # computed/stored field -- must be ignored
        "user_id": 9999,
        "computed_handicap": "5.0",
        "differential": "1.0",
        "differential_locked": True,
        "id": 555,
    }
    r = client.post("/api/v1/rounds", json=payload, headers=headers)
    assert r.status_code == 201
    body = r.get_json()
    assert body["differential_locked"] is False  # mass-assignment did NOT set True
    assert body["id"] != 555


# --------------------------------------------------------------------------- #
# Revision 2 regression: SEC-1 (course numeric-field DoS)
# --------------------------------------------------------------------------- #


def test_course_non_numeric_hole_index_rejected_422(test_app):
    """SEC-1(a) primary fix: a non-numeric hole_index must be rejected with
    422 BEFORE persist, not saved with a 201 -- `models.dict_to_course`
    unconditionally does `int(hdata.get("hole_index", 0))`, so an unvalidated
    non-numeric value would 500 every future `GET /api/v1/stats` call for
    every user (courses are a shared catalog, ADR-011)."""
    client, headers, user = _full_scope_client(test_app)
    bad_course = {
        "name": "Bad Course",
        "location": {"city": "X", "state/province": "Y", "country": "Z"},
        "holes": {"1": {"par": 4, "hole_index": "not-a-number"}},
    }
    r = client.post("/api/v1/courses", json=bad_course, headers=headers)
    assert r.status_code == 422
    assert r.mimetype == "application/problem+json"
    assert get_courses().get("Bad Course") is None, "malformed course must NOT persist"


def test_course_non_numeric_tee_slope_rejected_422(test_app):
    """Same DoS class, via `tees[*].slope`/`rating` (`dict_to_course`'s
    unconditional `float(tdata.get("rating", 72.0))` and guarded-but-still-
    crashing `int(tdata["front_slope"])`)."""
    client, headers, user = _full_scope_client(test_app)
    bad_course = {
        "name": "Bad Tees",
        "location": {"city": "X", "state/province": "Y", "country": "Z"},
        "tees": {"White": {"slope": "oops", "rating": 72.0}},
    }
    r = client.post("/api/v1/courses", json=bad_course, headers=headers)
    assert r.status_code == 422
    assert get_courses().get("Bad Tees") is None


def test_malformed_course_row_does_not_crash_stats(test_app):
    """SEC-1(b) defense-in-depth: even a pre-existing malformed course row
    (bypassing the schema entirely, e.g. written before this fix or by a
    future non-v1 path) must not 500 `GET /api/v1/stats` for anyone."""
    import store as store_mod

    client, headers, user = _full_scope_client(test_app)
    store_mod.save_course(
        {"location": {}, "tees": {}, "holes": {"1": {"par": "oops", "hole_index": 1}}, "par": 72},
        "Poisoned",
    )
    r = client.get("/api/v1/stats", headers=headers)
    assert r.status_code == 200, "a malformed course row must not 500 the whole stats endpoint"


def test_stats_handicap_index_uses_stored_capped_value(test_app):
    """Bug #135: `GET /api/v1/stats` `handicap_index` must report the stored,
    WHS-clamped `computed_handicap` (the #98 single source of truth the
    dashboard hero, round detail, trend and rankings all display) -- NOT a
    fresh RAW `calc_handicap_index()` recomputation, which skips the Rule 5.9
    Exceptional Score Reduction, the Rule 5.8 soft/hard cap, AND the Rule 5.3
    54.0 issued maximum (`handicap.py:217`).

    Fabricate a record whose RAW differentials drive `calc_handicap_index`
    ABOVE 54.0 (best-1 of three 65.0 diffs, minus the Rule 5.2a count=3
    adjustment of -2.0 => 63.0), while the stored `computed_handicap` on the
    most recent round is the capped 54.0. The buggy endpoint returns ~63.0
    (raw); the fixed endpoint returns 54.0, matching the dashboard."""
    import store as store_mod

    client, headers, user = _full_scope_client(test_app, username="capgolfer")
    for i, date in enumerate(("2026-05-03", "2026-05-02", "2026-05-01")):
        store_mod.save_round(
            {
                "course": "Pebble Beach",
                "tees": "White",
                "holes_played": "18",
                "entry_mode": "score_only",
                "total_gross": "130",
                "differential": "65.0",
                # The stored, WHS-capped HI on each round -- `current` reads the
                # most-recent one (index 0).
                "computed_handicap": "54.0",
            },
            date,
            0,
            user["id"],
        )

    r = client.get("/api/v1/stats", headers=headers)
    assert r.status_code == 200
    hi = r.get_json()["handicap_index"]
    assert hi == 54.0, (
        f"stats handicap_index must equal the stored/clamped 54.0 (Rule 5.3 "
        f"issued maximum), matching the dashboard's single-source-of-truth "
        f"read; got {hi!r} (the RAW unclamped calc_handicap_index value)"
    )


# --------------------------------------------------------------------------- #
# Revision 2 regression: SEC-2 (courses scopes enforced now, others still
# permissive-pending)
# --------------------------------------------------------------------------- #


def test_courses_write_enforced_now_even_without_scope_enforcement_flag(test_app, monkeypatch):
    """ADR-004 exception (SEC-2): `courses:write` is enforced IMMEDIATELY --
    a key lacking it gets 403, even with `API_SCOPE_ENFORCEMENT` unset
    (permissive-pending default)."""
    import source.auth_keys as auth_keys_mod

    monkeypatch.setattr(auth_keys_mod, "API_SCOPE_ENFORCEMENT", False)
    client, headers, user = _scoped_client(test_app, "limited1", ["rounds:read"])  # no courses:write
    payload = {
        "name": "Should Not Save",
        "location": {"city": "X", "state/province": "Y", "country": "Z"},
    }
    r = client.post("/api/v1/courses", json=payload, headers=headers)
    assert r.status_code == 403
    assert r.mimetype == "application/problem+json"
    assert get_courses().get("Should Not Save") is None


def test_courses_delete_enforced_now_even_without_scope_enforcement_flag(test_app, monkeypatch):
    import source.auth_keys as auth_keys_mod

    monkeypatch.setattr(auth_keys_mod, "API_SCOPE_ENFORCEMENT", False)
    owner_client, owner_headers, owner = _full_scope_client(test_app, "owner1")
    owner_client.post(
        "/api/v1/courses",
        json={"name": "Protected", "location": {"city": "X", "state/province": "Y", "country": "Z"}},
        headers=owner_headers,
    )

    limited_client, limited_headers, _ = _scoped_client(test_app, "limited2", ["courses:read"])  # no courses:delete
    r = limited_client.delete("/api/v1/courses/Protected", headers=limited_headers)
    assert r.status_code == 403
    assert r.mimetype == "application/problem+json"
    assert get_courses().get("Protected") is not None, "course must survive an unauthorized delete attempt"


def test_rounds_write_still_permissive_pending_unlike_courses(test_app, monkeypatch):
    """Control case for SEC-2: rounds/settings/stats/courses:read must stay
    permissive-pending exactly as ADR-004 specifies -- only courses:write/
    courses:delete are the enforce-now exception."""
    import source.auth_keys as auth_keys_mod

    monkeypatch.setattr(auth_keys_mod, "API_SCOPE_ENFORCEMENT", False)
    client, headers, user = _scoped_client(test_app, "limited3", ["courses:read"])  # no rounds:write
    r = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)
    assert r.status_code == 201, "rounds:write must remain permissive-pending, not enforce-now"


# --------------------------------------------------------------------------- #
# Revision 2 regression: SEC-3 (courses DELETE must catch cross-user usage)
# --------------------------------------------------------------------------- #


def test_course_delete_conflict_catches_other_users_rounds(test_app):
    """SEC-3: the DELETE conflict-check must be catalog-wide, not scoped to
    the deleting caller's own rounds -- courses are a SHARED catalog
    (ADR-011). User A deletes a course only User B has a round on -> 409."""
    client_a, headers_a, user_a = _full_scope_client(test_app, "userA")
    client_b, headers_b, user_b = _full_scope_client(test_app, "userB")

    course_payload = {
        "name": "Shared Course",
        "location": {"city": "X", "state/province": "Y", "country": "Z"},
    }
    r = client_a.post("/api/v1/courses", json=course_payload, headers=headers_a)
    assert r.status_code == 201

    r = client_b.post(
        "/api/v1/rounds",
        json={"date": "2026-05-01", "course": "Shared Course", "entry_mode": "score_only", "gross_total": "80"},
        headers=headers_b,
    )
    assert r.status_code == 201

    r = client_a.delete("/api/v1/courses/Shared Course", headers=headers_a)
    assert r.status_code == 409
    assert r.mimetype == "application/problem+json"
    assert get_courses().get("Shared Course") is not None


# --------------------------------------------------------------------------- #
# Revision 2 regression: SEC-4 (CSRF backstop for session-cookie callers)
# --------------------------------------------------------------------------- #


def test_v1_write_rejects_form_content_type_from_session(test_app):
    """SEC-4: the ADR-012 auth gate accepts session-cookie identities too,
    and v1 write routes are CSRF-exempted (bearer clients carry no
    csrf_token). The backstop for a session-cookie caller hitting a v1
    write route directly is `require_json_body`: a genuine cross-site
    HTML-form CSRF POST cannot arrive with `Content-Type: application/
    json` (a <form> can only send url-encoded/multipart/text-plain), so
    it 415s before any state-changing logic runs."""
    app.config["WTF_CSRF_ENABLED"] = False  # exercise require_json_body itself, not legacy CSRF
    create_user("sessionuser", "Session User", "pass1234")
    client = test_app.test_client()
    login = client.post("/login", data={"username": "sessionuser", "password": "pass1234"})
    assert login.status_code in (302, 303)

    r = client.post(
        "/api/v1/courses",
        data={"name": "Form Course"},
        content_type="application/x-www-form-urlencoded",
    )
    assert r.status_code == 415
    assert get_courses().get("Form Course") is None


# --------------------------------------------------------------------------- #
# Stats: handicap_trend (12-month stored-HI series, mirrors profile line graph)
# --------------------------------------------------------------------------- #


def test_stats_handicap_trend_matches_stored_computed_handicap(test_app):
    """Trend must equal the per-round STORED computed_handicap values,
    chronological (oldest -> newest), within the last 365 days."""
    import store as store_mod
    from datetime import datetime, timedelta

    client, headers, user = _full_scope_client(test_app)
    stored = []
    for days_ago, hi in ((200, "20.0"), (40, "19.5"), (10, "18.1")):
        date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        idx = store_mod.next_round_index(date, user["id"])
        store_mod.save_round(
            {"course": "Test GC", "tees": "White", "holes_played": "18",
             "entry_mode": "score_only", "notes": "", "holes": {},
             "total_gross": "85", "differential": "17.2",
             "computed_handicap": hi},
            date, idx, user["id"],
        )
        stored.append({"date": date, "value": float(hi)})

    r = client.get("/api/v1/stats", headers=headers)
    assert r.status_code == 200
    assert r.get_json()["handicap_trend"] == stored


def test_stats_handicap_trend_respects_12_month_cutoff(test_app):
    """A round older than 365 days must not appear in the trend."""
    import store as store_mod
    from datetime import datetime, timedelta

    client, headers, user = _full_scope_client(test_app)
    old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    new = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    for date in (old, new):
        idx = store_mod.next_round_index(date, user["id"])
        store_mod.save_round(
            {"course": "Test GC", "tees": "White", "holes_played": "18",
             "entry_mode": "score_only", "notes": "", "holes": {},
             "total_gross": "85", "differential": "17.2",
             "computed_handicap": "18.1"},
            date, idx, user["id"],
        )

    trend = client.get("/api/v1/stats", headers=headers).get_json()["handicap_trend"]
    assert [p["date"] for p in trend] == [new]


def test_stats_handicap_trend_includes_excluded_rounds(test_app):
    """Excluded rounds carry their stored HI into the trend, matching the
    profile page chart (no exclusion filter)."""
    import store as store_mod
    from datetime import datetime, timedelta

    client, headers, user = _full_scope_client(test_app)
    for days_ago, hi, excluded in ((20, "18.5", True), (10, "18.1", False)):
        date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        idx = store_mod.next_round_index(date, user["id"])
        store_mod.save_round(
            {"course": "Test GC", "tees": "White", "holes_played": "18",
             "entry_mode": "score_only", "notes": "", "holes": {},
             "total_gross": "85", "differential": "17.2",
             "computed_handicap": hi, "excluded": excluded},
            date, idx, user["id"],
        )

    trend = client.get("/api/v1/stats", headers=headers).get_json()["handicap_trend"]
    assert [p["value"] for p in trend] == [18.5, 18.1]


def test_stats_handicap_trend_empty_without_rounds(test_app):
    client, headers, user = _full_scope_client(test_app, username="notrend")
    body = client.get("/api/v1/stats", headers=headers).get_json()
    assert body["handicap_trend"] == []
