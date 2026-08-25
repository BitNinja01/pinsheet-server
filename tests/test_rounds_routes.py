"""Security/behavior-focused tests for source/routes/rounds.py.

Covers: draft CRUD, round create/update/delete/exclude, round detail and
report card rendering, cross-user authorization boundaries, and the
match_id linking side-effect of POST /api/rounds.
"""
import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
import store

@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Flask app with an isolated temp DB per test (mirrors test_routes.py).

    Route registration happens here (not at import time) and is guarded,
    since the Flask `app` object is a process-wide singleton shared with
    other test modules that may register routes first or later depending
    on collection order.
    """
    try:
        register_routes(app, limiter, csrf, User)
    except AssertionError:
        pass

    main_mod.limiter.enabled = False

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "drafts").mkdir()

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    monkeypatch.setattr(store, "_DATA_DIR", data_dir)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["DB_PATH"] = db_path

    return app


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def capture_render(monkeypatch):
    """Monkeypatch source.routes.rounds.render_template to capture the
    (template_name, context) instead of rendering Jinja, so tests can assert
    on exact computed context values rather than scraping HTML."""
    captured = {}

    def _fake_render_template(name, **kwargs):
        captured["template"] = name
        captured["ctx"] = kwargs
        return ""

    monkeypatch.setattr("source.routes.rounds.render_template", _fake_render_template)
    return captured


def _login(client, username="player1", display="Player One", password="pass1234"):
    user = store.create_user(username, display, password)
    resp = client.post("/login", data={"username": username, "password": password})
    assert resp.status_code in (302, 200)
    return user


def _make_course(client, name="Test GC", par=72, slope=120, rating=70.0):
    course_data = {
        "name": name,
        "location": {"city": "City", "state/province": "ST", "country": "Country"},
        "tees": {"White": {"yardage": "6000", "rating": str(rating), "slope": str(slope)}},
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "par": par,
    }
    resp = client.post("/api/courses", json=course_data)
    assert resp.status_code == 200
    return course_data


def _post_round(client, date="2026-06-01", gross_total="85", entry_mode="score_only",
                 course="Test GC", tees="White", holes=None, match_id=None, notes=""):
    payload = {
        "date": date,
        "course": course,
        "tees": tees,
        "holes_played": "18",
        "entry_mode": entry_mode,
        "gross_total": gross_total,
        "notes": notes,
        "holes": holes or {},
    }
    if match_id is not None:
        payload["match_id"] = match_id
    return client.post("/api/rounds", json=payload)


def _full_detailed_holes(par=4, gross=4, putts=2, fairway="H", gir="H"):
    """18 holes, uniform par/gross/putts, all fairways+greens hit."""
    return {
        str(n): {"gross": str(gross), "putts": str(putts), "fairway": fairway, "gir": gir, "penalties": "0"}
        for n in range(1, 19)
    }


# ---------------------------------------------------------------------------
# GET /rounds/new  (round_entry)
# ---------------------------------------------------------------------------

def test_round_entry_shows_empty_state_when_no_courses(client):
    _login(client)
    resp = client.get("/rounds/new")
    assert resp.status_code == 200
    assert b"No courses yet" in resp.data


def test_round_entry_hides_empty_state_when_course_exists(client):
    _login(client)
    _make_course(client, name="Pebble Beach")
    resp = client.get("/rounds/new")
    assert resp.status_code == 200
    assert b"No courses yet" not in resp.data
    assert b"Pebble Beach" in resp.data


def test_round_entry_requires_login(client):
    resp = client.get("/rounds/new", follow_redirects=False)
    assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Draft endpoints
# ---------------------------------------------------------------------------

def test_draft_round_put_get_delete_roundtrip(client):
    """A saved round draft round-trips through GET and is gone after DELETE."""
    _login(client)
    resp = client.get("/api/drafts/round")
    assert resp.status_code == 200
    assert resp.get_json() == {}

    draft = {"course": "Pebble Beach", "date": "2026-01-01"}
    resp = client.put("/api/drafts/round", json=draft)
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    resp = client.get("/api/drafts/round")
    assert resp.get_json() == draft

    resp = client.delete("/api/drafts/round")
    assert resp.get_json() == {"ok": True}

    resp = client.get("/api/drafts/round")
    assert resp.get_json() == {}


def test_draft_course_put_get_delete_roundtrip(client):
    """Course draft persistence is independent of the round draft."""
    _login(client)
    draft = {"name": "New Course", "par": "72"}
    client.put("/api/drafts/course", json=draft)
    resp = client.get("/api/drafts/course")
    assert resp.get_json() == draft

    client.delete("/api/drafts/course")
    resp = client.get("/api/drafts/course")
    assert resp.get_json() == {}

    # round draft must be untouched by course draft operations
    resp = client.get("/api/drafts/round")
    assert resp.get_json() == {}


def test_draft_round_requires_login(client):
    resp = client.get("/api/drafts/round")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# POST /api/rounds
# ---------------------------------------------------------------------------

def test_api_rounds_post_score_only_computes_expected_differential(client):
    """Differential for a score-only round must equal (113/slope) * (gross - rating),
    rounded to 1 decimal: (113/120) * (85-70) = 14.125 -> 14.1. Hand-computed
    literal (not calc_round_dif itself) so a formula bug in the calc module
    would actually be caught here."""
    _login(client)
    _make_course(client, slope=120, rating=70.0)
    resp = _post_round(client, gross_total="85", entry_mode="score_only")
    assert resp.status_code == 200
    data = resp.get_json()
    expected_diff = 14.1
    assert data["differential"] == expected_diff

    saved = store.get_all_rounds(1)
    assert len(saved) == 1
    assert saved[0].total_gross == "85"
    assert saved[0].differential == str(expected_diff)


def test_api_rounds_post_detailed_sums_hole_gross_for_total(client):
    """Detailed entry mode must total_gross = sum of each hole's gross score."""
    _login(client)
    _make_course(client)
    holes = _full_detailed_holes(gross=5)  # 18 holes * 5 = 90
    resp = _post_round(client, entry_mode="detailed", holes=holes)
    assert resp.status_code == 200

    saved = store.get_all_rounds(1)
    assert saved[0].total_gross == "90"


def test_api_rounds_post_requires_login(client):
    resp = _post_round(client)
    assert resp.status_code in (302, 401)


def test_api_rounds_post_links_round_to_match_when_computed_handicap_present(client):
    """When >=3 rounds exist a handicap is computed; supplying match_id must
    create a match_rounds link with the correctly-derived net score."""
    user = _login(client)
    _make_course(client, slope=120, rating=70.0)

    # Two prior rounds inserted directly so the 3rd POST has enough history
    # for calc_handicap_index to return a value (needs >= 3 differentials).
    for i, diff in enumerate(["10.0", "12.0"]):
        store.save_round(
            {
                "course": "Test GC", "tees": "White", "holes_played": "all",
                "entry_mode": "score_only", "holes": {}, "total_gross": "80",
                "differential": diff, "notes": "", "excluded": False,
                "computed_handicap": "", "differential_locked": False,
            },
            f"2026-05-0{i + 1}", 0, user_id=user["id"],
        )

    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])

    resp = _post_round(client, date="2026-06-10", gross_total="85", match_id=match_id)
    assert resp.status_code == 200

    links = store.get_match_rounds(match_id)
    assert len(links) == 1
    assert links[0]["user_id"] == user["id"]

    # Verify the round now has a computed handicap and the net matches the
    # expected course-handicap derived value. Hand-derived (not via
    # calc_course_handicap, to actually catch a formula bug there):
    #   new round diff = round((113/120) * (85-70), 1) = 14.1
    #   effective diffs sorted = [10.0, 12.0, 14.1]; count_table_n(3) = 1
    #   -> best 1 = 10.0
    #   WHS Rule 5.2a: 3 differentials -> -2.0 adjustment -> handicap index = 8.0
    #   (was 10.0 pre-fix)
    #   course_handicap = round(8.0 * (120/113) + (70.0-72)) = round(6.4956...) = 6
    #   (was 9 pre-fix)
    #   net = 85 - 6 = 79 (was 76 pre-fix)
    saved = [r for r in store.get_all_rounds(user["id"]) if r.date == "2026-06-10"]
    assert len(saved) == 1
    hi = float(saved[0].computed_handicap)
    assert hi == 8.0
    expected_ch = 6
    expected_net = 85 - expected_ch
    assert expected_net == 79
    assert float(links[0]["net"]) == float(expected_net)


def test_api_rounds_post_non_numeric_match_id_does_not_crash_save(client):
    """A non-numeric match_id must not error out the round save — the route
    catches ValueError from int(match_id) and just skips linking."""
    user = _login(client)
    _make_course(client, slope=120, rating=70.0)
    for i, diff in enumerate(["10.0", "12.0"]):
        store.save_round(
            {
                "course": "Test GC", "tees": "White", "holes_played": "all",
                "entry_mode": "score_only", "holes": {}, "total_gross": "80",
                "differential": diff, "notes": "", "excluded": False,
                "computed_handicap": "", "differential_locked": False,
            },
            f"2026-05-0{i + 1}", 0, user_id=user["id"],
        )

    resp = _post_round(client, date="2026-06-10", gross_total="85", match_id="not-a-number")
    assert resp.status_code == 200
    saved = [r for r in store.get_all_rounds(user["id"]) if r.date == "2026-06-10"]
    assert len(saved) == 1  # round itself still saved despite bad match_id


def test_edit_date_preserves_match_link_and_round_identity(client):
    """Editing a round's date must keep the round's id, so its match_rounds
    link survives and the round is still reachable at the new date. A previous
    bug deleted + re-inserted the round on a date change, minting a new id and
    orphaning the match link (round vanished behind a 404)."""
    user = _login(client)
    _make_course(client, slope=120, rating=70.0)
    for i, diff in enumerate(["10.0", "12.0"]):
        store.save_round(
            {"course": "Test GC", "tees": "White", "holes_played": "all",
             "entry_mode": "score_only", "holes": {}, "total_gross": "80",
             "differential": diff, "notes": "", "excluded": False,
             "computed_handicap": "", "differential_locked": False},
            f"2026-05-0{i + 1}", 0, user_id=user["id"],
        )

    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])

    resp = _post_round(client, date="2026-06-10", gross_total="85", match_id=match_id)
    assert resp.status_code == 200
    links = store.get_match_rounds(match_id)
    assert len(links) == 1
    original_round_id = links[0]["round_id"]

    # Edit the date of the linked round.
    resp = client.put("/api/rounds/2026-06-10/0", json={
        "date": "2026-06-12", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "85", "notes": "", "holes": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["date"] == "2026-06-12"

    # Match link survives and still points at the same round id.
    links_after = store.get_match_rounds(match_id)
    assert len(links_after) == 1
    assert links_after[0]["round_id"] == original_round_id

    # Round now lives at the new date; the old date is gone.
    saved = [r for r in store.get_all_rounds(user["id"]) if r.date == "2026-06-12"]
    assert len(saved) == 1
    assert saved[0].id == original_round_id
    assert not any(r.date == "2026-06-10" for r in store.get_all_rounds(user["id"]))

    # New URL resolves; old one 404s.
    assert client.get(f"/rounds/2026-06-12/{body['index']}").status_code == 200
    assert client.get("/rounds/2026-06-10/0").status_code == 404


def test_edit_date_to_occupied_day_does_not_clobber_existing_round(client):
    """Moving a round onto a date that already has a round must pick a free
    index rather than overwrite the sitting round."""
    user = _login(client)
    _make_course(client)
    _post_round(client, date="2026-07-01", gross_total="90")  # sitting round, idx 0
    _post_round(client, date="2026-07-05", gross_total="85")  # round to move, idx 0

    resp = client.put("/api/rounds/2026-07-05/0", json={
        "date": "2026-07-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "85", "notes": "", "holes": {},
    })
    assert resp.status_code == 200

    on_day = [r for r in store.get_all_rounds(user["id"]) if r.date == "2026-07-01"]
    assert len(on_day) == 2  # both rounds coexist, none clobbered
    grosses = sorted(r.total_gross for r in on_day)
    assert grosses == ["85", "90"]


def test_edit_rejects_malformed_date(client):
    """A non-ISO date must be rejected with 400 and never reach the DB / the
    client-side redirect that builds a round URL from it."""
    _login(client)
    _make_course(client)
    _post_round(client, date="2026-08-01", gross_total="85")
    resp = client.put("/api/rounds/2026-08-01/0", json={
        "date": "not-a-date", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "85", "notes": "", "holes": {},
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /rounds/<date>/<index>  (round_detail)
# ---------------------------------------------------------------------------

def test_round_detail_404_for_unknown_round(client):
    _login(client)
    resp = client.get("/rounds/2099-01-01/0")
    assert resp.status_code == 404
    assert b"Round not found" in resp.data


def test_round_detail_computes_100pct_fir_and_gir_for_perfect_round(client):
    """All 18 holes hit fairway ('H') and green ('H') with par gross must
    yield 100.0% FIR/GIR and a total score equal to par."""
    _login(client)
    _make_course(client)
    holes = _full_detailed_holes(par=4, gross=4, putts=2, fairway="H", gir="H")
    resp = _post_round(client, entry_mode="detailed", holes=holes)
    assert resp.status_code == 200

    resp = client.get("/rounds/2026-06-01/0")
    assert resp.status_code == 200
    body = resp.data
    assert body.count(b"100.0%") >= 2  # FIR and GIR stat blocks
    assert b'"rd-hero">72<' in body  # total.gross == par (72)
    assert b'"rd-stat-value">36<' in body  # 18 holes * 2 putts = 36


def test_round_detail_score_only_round_has_no_par_total(client):
    """Score-only rounds should not compute a hole-level par total."""
    _login(client)
    _make_course(client)
    resp = _post_round(client, gross_total="90", entry_mode="score_only")
    assert resp.status_code == 200

    resp = client.get("/rounds/2026-06-01/0")
    assert resp.status_code == 200
    body = resp.data
    assert b'"rd-hero">90<' in body  # total.gross rendered from gross_total
    assert b'rd-to-par-value is-ink-3">\n          --' in body  # total.diff is None (no par total for score_only)


def test_round_detail_cannot_view_other_users_round(client):
    """A round belonging to user A must 404 when requested by user B."""
    user_a = _login(client, username="alice", password="alicepass")
    _make_course(client)
    _post_round(client, date="2026-06-01", gross_total="85")
    client.get("/logout")

    _login(client, username="bob", password="bobpassword")
    resp = client.get("/rounds/2026-06-01/0")
    assert resp.status_code == 404


def test_round_detail_computes_net_total_from_course_handicap(client, capture_render):
    """With enough prior round history for a non-None handicap index, the
    rendered net_total/net_diff must reflect course_handicap = round(hi *
    (slope/113) + (rating - par)), net_total = total.gross - course_handicap.
    Hand-derived (not by calling calc_course_handicap/calc_handicap_index
    from the test itself):
      3 prior score-only rounds with differentials [10.0, 12.0, 14.0] ->
        count_table_n(3) = 1 -> best-1 = 10.0
      WHS Rule 5.2a: 3 differentials -> -2.0 adjustment -> hi_before = 8.0
      (was 10.0 pre-fix)
      course_handicap = round(8.0 * (120/113) + (70.0-72)) = round(6.4956..) = 6
      (was 9 pre-fix)
      total_gross (18 holes @ gross=4, par=4) = 72 -> net_total = 72 - 6 = 66
      (was 63 pre-fix)
      total_par = 72 -> net_diff = 66 - 72 = -6 (was -9 pre-fix)
    """
    user = _login(client)
    _make_course(client, slope=120, rating=70.0, par=72)

    for i, diff in enumerate(["10.0", "12.0", "14.0"]):
        store.save_round(
            {
                "course": "Test GC", "tees": "White", "holes_played": "all",
                "entry_mode": "score_only", "holes": {}, "total_gross": "80",
                "differential": diff, "notes": "", "excluded": False,
                "computed_handicap": "", "differential_locked": False,
            },
            f"2026-05-0{i + 1}", 0, user_id=user["id"],
        )

    holes = _full_detailed_holes(par=4, gross=4, putts=2, fairway="H", gir="H")
    resp = _post_round(client, date="2026-06-01", entry_mode="detailed", holes=holes)
    assert resp.status_code == 200

    resp = client.get("/rounds/2026-06-01/0")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["hi_before"] == 8.0
    assert ctx["course_handicap"] == 6
    assert ctx["total"]["net_total"] == 66
    assert ctx["total"]["net_diff"] == -6


# ---------------------------------------------------------------------------
# GET /rounds/<date>/<index>/report  (report_card)
# ---------------------------------------------------------------------------

def test_report_card_404_for_unknown_round(client):
    _login(client)
    resp = client.get("/rounds/2099-01-01/0/report")
    assert resp.status_code == 404


def test_report_card_renders_for_existing_round(client):
    _login(client)
    _make_course(client)
    _post_round(client, gross_total="85")
    resp = client.get("/rounds/2026-06-01/0/report")
    assert resp.status_code == 200
    assert b"Score vs Par" in resp.data


# ---------------------------------------------------------------------------
# GET /rounds  (rounds_list)
# ---------------------------------------------------------------------------

def test_rounds_list_empty_state_does_not_error(client):
    _login(client)
    resp = client.get("/rounds")
    assert resp.status_code == 200


def test_rounds_list_shows_score_to_par_for_each_round(client):
    """A round with gross=85 on a par-72 course must display '+13'."""
    _login(client)
    _make_course(client, par=72)
    _post_round(client, gross_total="85")
    resp = client.get("/rounds")
    assert resp.status_code == 200
    assert b"+13" in resp.data


def test_rounds_list_requires_login(client):
    resp = client.get("/rounds", follow_redirects=False)
    assert resp.status_code == 302


def test_rounds_list_computes_net_field_from_course_handicap(client, capture_render):
    """A round carrying a stored computed_handicap must have its `net` /
    `net_to_par` fields derived via course_handicap = round(hi *
    (slope/113) + (rating - par)); net = total_gross - course_handicap.
    Hand-derived: course_handicap = round(10.0 * (120/113) + (70.0-72)) = 9;
    net = 72 - 9 = 63; net_to_par = 63 - 72 = -9."""
    user = _login(client)
    _make_course(client, slope=120, rating=70.0, par=72)

    store.save_round(
        {
            "course": "Test GC", "tees": "White", "holes_played": "all",
            "entry_mode": "score_only", "holes": {}, "total_gross": "72",
            "differential": "8.0", "notes": "", "excluded": False,
            "computed_handicap": "10.0", "differential_locked": False,
        },
        "2026-06-01", 0, user_id=user["id"],
    )

    resp = client.get("/rounds")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert len(ctx["rounds"]) == 1
    rd = ctx["rounds"][0]
    assert rd["net"] == 63
    assert rd["net_to_par"] == -9


# ---------------------------------------------------------------------------
# PUT /api/rounds/<date>/<index>
# ---------------------------------------------------------------------------

def _put_round(client, url_date, index, **overrides):
    payload = {
        "date": url_date, "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "85", "notes": "", "holes": {},
    }
    payload.update(overrides)
    return client.put(f"/api/rounds/{url_date}/{index}", json=payload)


def test_api_rounds_put_404_for_unknown_round(client):
    _login(client)
    _make_course(client)
    resp = _put_round(client, "2099-01-01", 0)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Round not found"


def test_api_rounds_put_updates_notes_and_recomputes_differential(client):
    _login(client)
    _make_course(client, slope=120, rating=70.0)
    _post_round(client, gross_total="85")

    resp = _put_round(client, "2026-06-01", "0", gross_total="90", notes="Updated")
    assert resp.status_code == 200
    # Hand-computed: round((113/120) * (90-70), 1) = round(18.8333.., 1) = 18.8
    expected_diff = 18.8
    assert resp.get_json()["differential"] == expected_diff

    saved = store.get_all_rounds(1)
    assert saved[0].notes == "Updated"
    assert saved[0].total_gross == "90"
    assert saved[0].differential_locked is False


def test_api_rounds_put_manual_override_locks_differential(client):
    _login(client)
    _make_course(client)
    _post_round(client, gross_total="85")

    resp = _put_round(client, "2026-06-01", "0", differential_override=9.9)
    assert resp.status_code == 200
    assert resp.get_json()["differential"] == 9.9

    saved = store.get_all_rounds(1)
    assert saved[0].differential == "9.9"
    assert saved[0].differential_locked is True


def test_api_rounds_put_clearing_override_unlocks_and_recomputes(client):
    _login(client)
    _make_course(client, slope=120, rating=70.0)
    _post_round(client, gross_total="85")
    _put_round(client, "2026-06-01", "0", differential_override=9.9)

    resp = _put_round(client, "2026-06-01", "0", gross_total="85", differential_override=None)
    assert resp.status_code == 200
    # Hand-computed: round((113/120) * (85-70), 1) = round(14.125, 1) = 14.1
    expected_diff = 14.1
    assert resp.get_json()["differential"] == expected_diff

    saved = store.get_all_rounds(1)
    assert saved[0].differential_locked is False


def test_api_rounds_put_preserves_lock_when_override_key_absent(client):
    """If the client omits differential_override entirely, an existing lock
    must be preserved and the differential must NOT be recomputed."""
    _login(client)
    _make_course(client, slope=120, rating=70.0)
    _post_round(client, gross_total="85")
    _put_round(client, "2026-06-01", "0", differential_override=9.9)

    # Change gross to something that WOULD produce a very different diff if
    # recomputed, but omit differential_override entirely.
    resp = _put_round(client, "2026-06-01", "0", gross_total="120")
    assert resp.status_code == 200
    assert resp.get_json()["differential"] == 9.9

    saved = store.get_all_rounds(1)
    assert saved[0].differential == "9.9"
    assert saved[0].differential_locked is True


def test_api_rounds_put_date_change_moves_round(client):
    """Changing the date must delete the old date/index row and create a
    new one at the new date with the same index."""
    _login(client)
    _make_course(client)
    _post_round(client, date="2026-06-01", gross_total="85")

    resp = _put_round(client, "2026-06-01", "0", date="2026-07-04", gross_total="85")
    assert resp.status_code == 200

    all_rounds = store.get_all_rounds(1)
    dates = [r.date for r in all_rounds]
    assert "2026-06-01" not in dates
    assert "2026-07-04" in dates
    assert len(all_rounds) == 1


def test_api_rounds_put_cannot_edit_other_users_round(client):
    _login(client, username="alice", password="alicepass")
    _make_course(client)
    _post_round(client, date="2026-06-01", gross_total="85")
    client.get("/logout")

    _login(client, username="bob", password="bobpassword")
    resp = _put_round(client, "2026-06-01", "0", notes="hacked")
    assert resp.status_code == 404

    # confirm alice's round was untouched
    alice_rounds = store.get_all_rounds(1)
    assert alice_rounds[0].notes == ""


# ---------------------------------------------------------------------------
# POST /api/rounds/<date>/<index>/exclude
# ---------------------------------------------------------------------------

def test_api_rounds_exclude_404_for_unknown_round(client):
    _login(client)
    resp = client.post("/api/rounds/2099-01-01/0/exclude", json={"excluded": True})
    assert resp.status_code == 404


def test_api_rounds_exclude_sets_flag_and_recomputes_handicap(client):
    _login(client)
    _make_course(client)
    _post_round(client, gross_total="85")

    resp = client.post("/api/rounds/2026-06-01/0/exclude", json={"excluded": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["excluded"] is True

    saved = store.get_all_rounds(1)
    assert saved[0].excluded is True

    # un-exclude
    resp = client.post("/api/rounds/2026-06-01/0/exclude", json={"excluded": False})
    assert resp.get_json()["excluded"] is False
    saved = store.get_all_rounds(1)
    assert saved[0].excluded is False


def test_api_rounds_exclude_response_handicap_is_stored_value(client):
    """The exclude response's `handicap` must be the STORED displayed HI
    (WHS Rule 5.7/5.8 capped + Rule 5.9 ESR-adjusted) that recompute just
    wrote -- not a fresh raw calc_handicap_index() recalculation, which
    bypasses both. Under an active Exceptional Score Reduction the two
    diverge (raw 11.0 vs stored 10.0 below), so this test fails against
    the old raw-response implementation and passes with the stored value.
    """
    _login(client)
    _make_course(client)
    # 20 rounds at gross 83 -> diff 12.2, baseline HI 12.2 (LHI 10.2 from
    # the Rule 5.2a-adjusted rounds 3-4).
    for i in range(20):
        _post_round(client, date=f"2026-07-{1 + i:02d}", gross_total="83")
    # Exceptional round: diff 2.8, gap 9.4 vs HI-in-effect 12.2 -> -1.0 ESR.
    _post_round(client, date="2026-08-01", gross_total="73")

    resp = client.post("/api/rounds/2026-07-10/0/exclude", json={"excluded": True})
    assert resp.status_code == 200
    data = resp.get_json()

    stored_hi = None
    for r in store.get_all_rounds(1):
        if r.computed_handicap and r.computed_handicap != "0":
            stored_hi = float(r.computed_handicap)
            break
    assert stored_hi is not None
    assert data["handicap"] == stored_hi

    from calc.handicap import calc_handicap_index
    raw = calc_handicap_index(store.get_all_rounds(1), True)
    assert raw is not None and raw != stored_hi


# ---------------------------------------------------------------------------
# DELETE /api/rounds/<date>/<index>
# ---------------------------------------------------------------------------

def test_api_rounds_delete_removes_round(client):
    _login(client)
    _make_course(client)
    _post_round(client, gross_total="85")
    assert len(store.get_all_rounds(1)) == 1

    resp = client.delete("/api/rounds/2026-06-01/0")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert len(store.get_all_rounds(1)) == 0


def test_api_rounds_delete_scoped_to_own_user_only(client):
    """DELETE is only scoped by the caller's own user_id in the SQL WHERE
    clause with no prior ownership check — verify another user's round
    that happens to share date/index survives untouched."""
    alice = _login(client, username="alice", password="alicepass")
    _make_course(client)
    _post_round(client, date="2026-06-01", gross_total="85")
    client.get("/logout")

    _login(client, username="bob", password="bobpassword")
    resp = client.delete("/api/rounds/2026-06-01/0")
    assert resp.status_code == 200  # route reports ok regardless

    alice_rounds = store.get_all_rounds(alice["id"])
    assert len(alice_rounds) == 1  # bob did not actually delete alice's round


# ---------------------------------------------------------------------------
# GET /rounds  — handicap highlight window (best 8 of most recent 20)
# ---------------------------------------------------------------------------
def test_rounds_list_handicap_highlight_uses_recent_20_window(client, capture_render):
    """A best-differential round that falls outside the most-recent-20 window
    must NOT be marked in_handicap; only the recent window can light up.

    Regression: the highlight previously scanned all rounds, so an all-time
    best round older than the last 20 was wrongly flagged as counting toward
    the current index.
    """
    _login(client)
    _make_course(client, slope=120, rating=70.0)

    # Oldest round: lowest differential all-time, but outside the recent 20.
    _post_round(client, date="2025-01-01", gross_total="71")  # diff ~0.9
    # 20 recent, higher-differential rounds that form the actual window.
    for i in range(1, 21):
        _post_round(client, date="2026-03-%02d" % i, gross_total="100")  # diff ~28.2

    resp = client.get("/rounds")
    assert resp.status_code == 200

    rounds = capture_render["ctx"]["rounds"]
    assert len(rounds) == 21

    ancient = [r for r in rounds if r["date"] == "2025-01-01"]
    assert ancient and ancient[0]["in_handicap"] is False

    counted = [r for r in rounds if r["in_handicap"]]
    assert len(counted) == 8  # count_table_n(20) == 8
    assert all(r["date"].startswith("2026-03") for r in counted)


# ---------------------------------------------------------------------------
# Issue #80 (CWE-20): server-side bounds on round score fields
# ---------------------------------------------------------------------------

class TestScoreBounds:
    """Issue #80: absurd/negative scores are clamped in place, not rejected —
    the app tolerates malformed input (must not 500) but must not let it poison
    the handicap. Per-hole gross clamps to [0, 20]; score-only total to
    [0, 20 * holes]."""

    def _setup(self, client):
        _login(client)
        _make_course(client)

    def _round_on(self, date):
        return next(r for r in store.get_all_rounds(1) if r.date == date)

    def test_negative_hole_gross_clamped_to_zero(self, client):
        self._setup(client)
        holes = _full_detailed_holes(gross=4)
        holes["1"]["gross"] = "-3"
        resp = _post_round(client, date="2026-06-01", entry_mode="detailed", holes=holes)
        assert resp.status_code == 200
        r = self._round_on("2026-06-01")
        assert r.holes["1"].gross == 0          # negative clamped to 0
        assert r.total_gross == str(17 * 4)          # 68, not 68-3

    def test_absurd_hole_gross_clamped_to_max(self, client):
        self._setup(client)
        holes = _full_detailed_holes(gross=4)
        holes["7"]["gross"] = "99"
        resp = _post_round(client, date="2026-06-02", entry_mode="detailed", holes=holes)
        assert resp.status_code == 200
        r = self._round_on("2026-06-02")
        assert r.holes["7"].gross == 20         # clamped to MAX_HOLE_GROSS
        assert r.total_gross == str(17 * 4 + 20)     # 88, not 167

    def test_absurd_score_only_total_clamped(self, client):
        self._setup(client)
        resp = _post_round(client, date="2026-06-03", entry_mode="score_only", gross_total="9999")
        assert resp.status_code == 200
        # 18 holes * 20 = 360 ceiling
        assert self._round_on("2026-06-03").total_gross == "360"

    def test_valid_scores_pass_through_unchanged(self, client):
        self._setup(client)
        assert _post_round(client, date="2026-06-04", entry_mode="score_only", gross_total="85").status_code == 200
        assert self._round_on("2026-06-04").total_gross == "85"
        holes = _full_detailed_holes(gross=5)
        assert _post_round(client, date="2026-06-05", entry_mode="detailed", holes=holes).status_code == 200
        assert self._round_on("2026-06-05").total_gross == str(18 * 5)

    def test_edit_path_is_also_clamped(self, client):
        # The PUT edit path shares the sanitizer.
        self._setup(client)
        assert _post_round(client, date="2026-06-06", entry_mode="score_only", gross_total="85").status_code == 200
        bad_holes = _full_detailed_holes(gross=4)
        bad_holes["1"]["gross"] = "-1"
        resp = client.put("/api/rounds/2026-06-06/0", json={
            "date": "2026-06-06", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "detailed", "notes": "",
            "gross_total": "", "holes": bad_holes,
        })
        assert resp.status_code == 200
        assert self._round_on("2026-06-06").holes["1"].gross == 0
