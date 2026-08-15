"""Coverage-gap closure tests (eng-qa Step 5, Revision 1 -- coordinator gate
0.9110, threshold 0.94).

Adds tests for the specific `pytest --cov` "Missing" lines flagged in the
Step-5 gate feedback:

  - `courses.py` (was 61%): GET-list, GET-one (+404), PUT update (rename +
    non-rename), PUT-missing-404, PUT rename-collision-409, DELETE (204),
    DELETE-with-referencing-rounds-409 (lines 34-35, 42-45, 72-90, 96-108).
  - `stats.py` (was 71%): GET /api/v1/stats with >=1 round (real computed
    fields) and with 0 rounds (null-safe empty-stats path) (lines 38-45).
  - `settings.py` (was 83%): GET (line 22) and PUT (lines 35-37).
  - `errors.py` (was 90%): the uncaught-exception 500 path (lines 141-142,
    ADR-002 no-stack-leak control) via a monkeypatched store function that
    raises inside a real v1 handler; plus whitebox unit coverage of
    `_detail_from_apiflask_error`'s remaining branches (lines 113, 118, 124)
    that no live HTTP request naturally exercises (confirmed empirically --
    malformed-JSON bodies are caught by werkzeug's own `BadRequest` before
    ever reaching an `apiflask.HTTPError`, so the plain-string/skip-non-dict/
    fallback branches of that helper are only reachable by constructing an
    `HTTPError` directly, as apiflask itself would for error shapes this
    app's own routes/schemas never happen to produce).
"""
import logging

import pytest
from apiflask import HTTPError

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from source.routes.api_v1 import register_api_v1
from source.routes.api_v1.errors import _detail_from_apiflask_error, _GENERIC_500_DETAIL
from database import set_db_path, init_db
from store import create_user, create_api_key, API_KEY_PERMISSIONS


@pytest.fixture
def test_app(tmp_path, monkeypatch):
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


def _full_scope_client(test_app, username="covgap"):
    user = create_user(username, username.title(), "pass1234")
    plaintext, meta = create_api_key(user["id"], "full key", list(API_KEY_PERMISSIONS))
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


def _course_payload(name, city="Augusta"):
    return {
        "name": name,
        "location": {"city": city, "state/province": "GA", "country": "US"},
        "holes": {},
        "par": 72,
    }


# --------------------------------------------------------------------------- #
# courses.py -- GET list / GET one (+404) / PUT / DELETE (+409)
# --------------------------------------------------------------------------- #


def test_courses_list_returns_created_courses(test_app):
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Augusta National"), headers=headers)
    client.post("/api/v1/courses", json=_course_payload("Pebble Beach", city="Pebble Beach"), headers=headers)

    r = client.get("/api/v1/courses", headers=headers)
    assert r.status_code == 200
    names = {c["name"] for c in r.get_json()["courses"]}
    assert {"Augusta National", "Pebble Beach"} <= names


def test_courses_get_one_returns_course(test_app):
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Augusta National"), headers=headers)

    r = client.get("/api/v1/courses/Augusta National", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "Augusta National"
    assert body["location"]["city"] == "Augusta"


def test_courses_get_one_missing_returns_404_problem_json(test_app):
    client, headers, user = _full_scope_client(test_app)
    r = client.get("/api/v1/courses/Does Not Exist GC", headers=headers)
    assert r.status_code == 404
    assert r.mimetype == "application/problem+json"


def test_courses_put_update_non_rename(test_app):
    """PUT with the same name updates fields in place (no rename branch)."""
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Augusta National"), headers=headers)

    updated_payload = _course_payload("Augusta National", city="Augusta Updated")
    updated_payload["par"] = 71
    r = client.put("/api/v1/courses/Augusta National", json=updated_payload, headers=headers)

    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "Augusta National"
    assert body["location"]["city"] == "Augusta Updated"
    assert body["par"] == 71


def test_courses_put_update_with_rename(test_app):
    """PUT with a different `name` in the body renames the course."""
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Old Name GC"), headers=headers)

    renamed_payload = _course_payload("New Name GC")
    r = client.put("/api/v1/courses/Old Name GC", json=renamed_payload, headers=headers)

    assert r.status_code == 200
    assert r.get_json()["name"] == "New Name GC"

    # old name is gone, new name resolves
    r_old = client.get("/api/v1/courses/Old Name GC", headers=headers)
    assert r_old.status_code == 404
    r_new = client.get("/api/v1/courses/New Name GC", headers=headers)
    assert r_new.status_code == 200


def test_courses_put_missing_course_returns_404(test_app):
    client, headers, user = _full_scope_client(test_app)
    r = client.put(
        "/api/v1/courses/Does Not Exist GC",
        json=_course_payload("Does Not Exist GC"),
        headers=headers,
    )
    assert r.status_code == 404
    assert r.mimetype == "application/problem+json"


def test_courses_put_rename_collision_returns_409(test_app):
    """Renaming course A to an already-existing course B's name 409s."""
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Course A"), headers=headers)
    client.post("/api/v1/courses", json=_course_payload("Course B"), headers=headers)

    r = client.put("/api/v1/courses/Course A", json=_course_payload("Course B"), headers=headers)
    assert r.status_code == 409
    assert r.mimetype == "application/problem+json"


def test_courses_delete_returns_204(test_app):
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Deletable GC"), headers=headers)

    r = client.delete("/api/v1/courses/Deletable GC", headers=headers)
    assert r.status_code == 204

    r_get = client.get("/api/v1/courses/Deletable GC", headers=headers)
    assert r_get.status_code == 404


def test_courses_delete_missing_returns_404(test_app):
    client, headers, user = _full_scope_client(test_app)
    r = client.delete("/api/v1/courses/Does Not Exist GC", headers=headers)
    assert r.status_code == 404
    assert r.mimetype == "application/problem+json"


def test_courses_delete_with_referencing_round_returns_409(test_app):
    """A course still referenced by one of the caller's rounds cannot be
    deleted (courses.py:96-108, mirrors legacy self-scoped guard)."""
    client, headers, user = _full_scope_client(test_app)
    client.post("/api/v1/courses", json=_course_payload("Pebble Beach", city="Pebble Beach"), headers=headers)

    r_round = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)
    assert r_round.status_code == 201

    r = client.delete("/api/v1/courses/Pebble Beach", headers=headers)
    assert r.status_code == 409
    assert r.mimetype == "application/problem+json"

    # course must still exist (delete did not proceed)
    r_get = client.get("/api/v1/courses/Pebble Beach", headers=headers)
    assert r_get.status_code == 200


# --------------------------------------------------------------------------- #
# rounds.py -- DELETE success path (rounds.py:213-216).
#
# Revision 2 (coordinator gate 0.9275): the whole 724-test suite exercised
# DELETE /api/v1/rounds/<id> ONLY via the IDOR foreign-round 404 branch
# (`test_idor_get_put_delete_foreign_round_returns_404_no_oracle`,
# `tests/test_api_v1_security.py`) -- the actual delete-SUCCESS body
# (`_delete_round_row(...)`, `recompute_handicaps_for_user(...)`, the
# `_log.info(...)` call, and the `"", 204` return -- `rounds.py:213-216`)
# had zero coverage. Closed here.
# --------------------------------------------------------------------------- #


def test_delete_own_round_returns_204_then_get_404_and_count_decrements(test_app):
    """The caller deletes a round it OWNS: 204 (no body), the round is then
    genuinely gone (a follow-up GET on the same id 404s, Problem Details),
    the round no longer appears in the list (count decremented), and the
    handicap recompute cascade (`recompute_handicaps_for_user`, called
    unconditionally on the success path) ran without error against the
    caller's remaining rounds."""
    client, headers, user = _full_scope_client(test_app)

    r1 = client.post("/api/v1/rounds", json=VALID_ROUND, headers=headers)
    assert r1.status_code == 201
    keep_id = r1.get_json()["id"]

    r2 = client.post("/api/v1/rounds", json={**VALID_ROUND, "date": "2026-05-02"}, headers=headers)
    assert r2.status_code == 201
    delete_id = r2.get_json()["id"]

    r_list_before = client.get("/api/v1/rounds", headers=headers)
    assert len(r_list_before.get_json()["rounds"]) == 2

    r_del = client.delete(f"/api/v1/rounds/{delete_id}", headers=headers)
    assert r_del.status_code == 204
    assert r_del.get_data() == b""  # 204 -- no response body

    # gone: a follow-up GET on the deleted id 404s, Problem Details shape,
    # identical to the IDOR no-existence-oracle contract on a missing round.
    r_get_deleted = client.get(f"/api/v1/rounds/{delete_id}", headers=headers)
    assert r_get_deleted.status_code == 404
    assert r_get_deleted.mimetype == "application/problem+json"

    # the OTHER (kept) round is unaffected -- delete_round only ever
    # touches the single owner-checked row it was called with.
    r_get_kept = client.get(f"/api/v1/rounds/{keep_id}", headers=headers)
    assert r_get_kept.status_code == 200

    # round count decremented: 2 -> 1, and the surviving round is the
    # one that was kept, not a stale/duplicate entry.
    r_list_after = client.get("/api/v1/rounds", headers=headers)
    remaining = r_list_after.get_json()["rounds"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == keep_id

    # recompute_handicaps_for_user (rounds.py:214) ran without error against
    # the caller's now-1-round history -- confirmed indirectly: the stats
    # endpoint (which reads the same post-recompute rows) still 200s and
    # reports the correct post-delete round count, not a stale 2 or a 500.
    r_stats = client.get("/api/v1/stats", headers=headers)
    assert r_stats.status_code == 200
    assert r_stats.get_json()["rounds_total"] == 1


# --------------------------------------------------------------------------- #
# stats.py -- GET /api/v1/stats with rounds and with none (null-safe)
# --------------------------------------------------------------------------- #


def test_stats_with_rounds_returns_real_computed_fields(test_app):
    """`recompute_handicaps_for_user` (store.py:362-402) only computes a
    non-zero `differential` -- and `best_n_rounds` only treats a round as
    handicap-ELIGIBLE (`calc/composite.py:10`: `not r.excluded and
    r.differential and r.differential != "0"`) -- when (a) a matching course
    with `tees[<tee_name>]` slope/rating data exists, and (b) the round
    isn't "incomplete" (`_is_incomplete_round`: a detailed round with fewer
    scored holes than its `holes_played` selection). This test therefore
    creates the referenced course first and uses `entry_mode="score_only"`
    (no per-hole data at all, so `_is_incomplete_round` short-circuits
    `False` via its own `not holes` branch) -- both required for a
    non-null, real `scoring_average`/`gir_percent`/etc., matching how a
    real client's "quick score entry" flow works."""
    client, headers, user = _full_scope_client(test_app, username="statsuser")
    course_payload = {
        "name": "Pebble Beach",
        "location": {"city": "Pebble Beach", "state/province": "CA", "country": "US"},
        "tees": {"White": {"slope": 128, "rating": 71.5, "yardage": "6200"}},
        "holes": {},
        "par": 72,
    }
    r_course = client.post("/api/v1/courses", json=course_payload, headers=headers)
    assert r_course.status_code == 201

    for i in range(1, 4):
        payload = {
            "date": f"2026-05-0{i}",
            "course": "Pebble Beach",
            "tees": "White",
            "entry_mode": "score_only",
            "holes_played": "18",
            "gross_total": "85",
            "notes": "",
        }
        r = client.post("/api/v1/rounds", json=payload, headers=headers)
        assert r.status_code == 201

    r = client.get("/api/v1/stats", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["rounds_total"] == 3
    # With real, handicap-eligible rounds entered, these must be actual
    # numbers, not null.
    assert isinstance(body["scoring_average"], (int, float))
    assert body["scoring_average"] == 85.0
    assert isinstance(body["handicap_index"], (int, float))


def test_stats_with_zero_rounds_is_null_safe(test_app):
    """A user with no rounds gets 200 with a null-safe empty-stats body, not
    a 500 from a division-by-zero or similar in the calc.* helpers."""
    client, headers, user = _full_scope_client(test_app, username="norounds")

    r = client.get("/api/v1/stats", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["rounds_total"] == 0
    # StatsOutSchema declares these allow_none=True -- confirm the handler
    # actually returns None (not e.g. a NaN or an unhandled exception) for
    # an empty round set.
    assert body["handicap_index"] is None
    assert body["scoring_average"] is None


# --------------------------------------------------------------------------- #
# settings.py -- GET (line 22) and PUT (lines 35-37)
# --------------------------------------------------------------------------- #


def test_settings_get_returns_defaults(test_app):
    client, headers, user = _full_scope_client(test_app)
    r = client.get("/api/v1/settings", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert "include_9hole" in body
    assert "season_enabled" in body


def test_settings_put_updates_and_persists(test_app):
    client, headers, user = _full_scope_client(test_app)

    r = client.put("/api/v1/settings", json={"include_9hole": False, "season_enabled": True}, headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["include_9hole"] is False
    assert body["season_enabled"] is True

    # persisted -- a follow-up GET reflects the same values (store.py merge).
    r2 = client.get("/api/v1/settings", headers=headers)
    assert r2.get_json()["include_9hole"] is False
    assert r2.get_json()["season_enabled"] is True


# --------------------------------------------------------------------------- #
# errors.py -- uncaught-exception 500 path (ADR-002 no-stack-leak control)
# --------------------------------------------------------------------------- #


def test_uncaught_exception_returns_500_generic_no_leak(test_app, monkeypatch, caplog):
    """Force a real v1 handler to raise a generic (non-HTTPException)
    Exception with a sensitive-looking message, and confirm the CLIENT
    response is the fixed generic detail string -- never the exception
    message, a traceback, or any hint of the underlying cause -- while the
    full exception IS logged server-side (`_log.exception`, coding standard
    §4.3 / ADR-002)."""
    import source.routes.api_v1.rounds as rounds_mod

    sensitive_message = "SQLITE_CORRUPT: table users column password_hash unique constraint at /secret/db/path.db"

    def _boom(*args, **kwargs):
        raise RuntimeError(sensitive_message)

    monkeypatch.setattr(rounds_mod, "get_all_rounds", _boom)

    client, headers, user = _full_scope_client(test_app)

    with caplog.at_level(logging.ERROR, logger="pinsheet"):
        r = client.get("/api/v1/rounds", headers=headers)

    assert r.status_code == 500
    assert r.mimetype == "application/problem+json"
    body = r.get_json()
    assert body["detail"] == _GENERIC_500_DETAIL
    assert sensitive_message not in body["detail"]
    assert "RuntimeError" not in str(body)
    assert sensitive_message not in r.get_data(as_text=True)
    assert set(body) >= {"type", "title", "status", "detail", "instance", "traceId"}
    assert body["status"] == 500

    # Server-side log DOES capture the real exception -- confirms the
    # detail is sanitized at the RESPONSE layer, not lost entirely.
    assert any(
        sensitive_message in rec.message or (rec.exc_info and sensitive_message in str(rec.exc_info[1]))
        for rec in caplog.records
    ), "the real exception must still be logged server-side (coding standard §4.3)"


# --------------------------------------------------------------------------- #
# errors.py -- whitebox unit coverage of `_detail_from_apiflask_error`'s
# remaining branches (lines 113, 118, 124), not naturally reachable via any
# live HTTP request this app's own routes/schemas produce (confirmed
# empirically: malformed-JSON bodies raise werkzeug's own `BadRequest`
# before ever constructing an `apiflask.HTTPError`).
# --------------------------------------------------------------------------- #


def test_detail_from_apiflask_error_plain_string_branch():
    """Line 113: a non-empty string `.detail` is returned verbatim."""
    err = HTTPError(400, detail="A plain, human-readable detail string.")
    assert _detail_from_apiflask_error(err) == "A plain, human-readable detail string."


def test_detail_from_apiflask_error_skips_non_dict_location_value():
    """Line 118: a `.detail` dict whose value for one location isn't itself
    a dict (an unexpected/malformed shape) is skipped, not KeyError'd."""
    err = HTTPError(422, detail={
        "query": "not-a-dict-value-should-be-skipped",
        "json": {"date": ["Missing data for required field."]},
    })
    result = _detail_from_apiflask_error(err)
    assert "date: Missing data for required field." in result
    assert "not-a-dict-value-should-be-skipped" not in result


def test_detail_from_apiflask_error_falls_back_to_message():
    """Line 124: an empty `.detail` dict falls back to `.message`."""
    err = HTTPError(400, message="Fallback message from HTTPError.message")
    err.detail = {}
    assert _detail_from_apiflask_error(err) == "Fallback message from HTTPError.message"


def test_detail_from_apiflask_error_falls_back_to_title_when_no_message():
    """Line 124 (second half): no `.detail`, no `.message` -> falls back to
    the status-code title map."""
    err = HTTPError(400)
    err.detail = None
    err.message = None
    assert _detail_from_apiflask_error(err) == "Bad Request"
