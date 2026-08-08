"""Security/behavior-focused tests for source/routes/matches.py.

Covers: match creation validation, participant-only authorization on
match_link_round, unlinked-round filtering, and net-score computation on
link.
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
    """Monkeypatch source.routes.matches.render_template to capture the
    (template_name, context) instead of rendering Jinja, so tests can assert
    on exact computed context values rather than scraping HTML (which can
    have unrelated fields that coincidentally render the same digits)."""
    captured = {}

    def _fake_render_template(name, **kwargs):
        captured["template"] = name
        captured["ctx"] = kwargs
        return ""

    monkeypatch.setattr("source.routes.matches.render_template", _fake_render_template)
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


def _save_course_direct(name="Test GC", par=72, slope=120, rating=70.0):
    """Save a course straight to the store, bypassing the login-required API
    endpoint (useful when the acting client is logged in as someone else)."""
    course = {
        "location": {"city": "City", "state/province": "ST", "country": "Country"},
        "tees": {"White": {"yardage": "6000", "rating": str(rating), "slope": str(slope)}},
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "par": par,
    }
    store.save_course(course, name)


def _save_round_with_handicap(user_id, date="2026-06-01", gross="85",
                               computed_handicap="14.0", course="Test GC", tees="White"):
    """Bypass the calculation-heavy POST /api/rounds route and write a round
    directly so match-linking tests don't need 20 rounds of history."""
    golf_round = {
        "course": course, "tees": tees, "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": gross,
        "differential": "10.0", "notes": "", "excluded": False,
        "computed_handicap": computed_handicap, "differential_locked": False,
    }
    round_id = store.save_round(golf_round, date, 0, user_id=user_id)
    return round_id


# ---------------------------------------------------------------------------
# GET/POST /matches/new
# ---------------------------------------------------------------------------

def test_match_new_requires_login(client):
    resp = client.get("/matches/new", follow_redirects=False)
    assert resp.status_code == 302


def test_match_new_get_lists_course_and_participant_options(client):
    user = _login(client)
    _make_course(client, name="Pebble Beach")
    resp = client.get("/matches/new")
    assert resp.status_code == 200
    assert b"Pebble Beach" in resp.data
    assert f'value="{user["id"]}"'.encode() in resp.data


def test_match_new_post_missing_course_shows_error(client):
    _login(client)
    resp = client.post("/matches/new", data={"date": "2026-06-01", "participants": ["1", "2"]})
    assert resp.status_code == 200
    assert b"Course is required." in resp.data


def test_match_new_post_missing_date_shows_error(client):
    _login(client)
    _make_course(client)
    resp = client.post("/matches/new", data={"course": "Test GC", "participants": ["1", "2"]})
    assert resp.status_code == 200
    assert b"Date is required." in resp.data


def test_match_new_post_too_few_participants_shows_error(client):
    user = _login(client)
    _make_course(client)
    resp = client.post("/matches/new", data={
        "course": "Test GC", "date": "2026-06-01", "participants": [str(user["id"])],
    })
    assert resp.status_code == 200
    assert b"At least 2 participants are required." in resp.data


def test_match_new_post_creates_match_with_players_and_redirects(client):
    user1 = _login(client, username="alice", password="alicepass")
    user2 = store.create_user("bob", "Bob", "bobpassword")
    _make_course(client, name="Test GC")

    resp = client.post("/matches/new", data={
        "course": "Test GC", "date": "2026-06-15",
        "participants": [str(user1["id"]), str(user2["id"])],
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/matches/" in resp.headers["Location"]
    match_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])

    match = store.get_match(match_id)
    assert match is not None
    assert match["course_name"] == "Test GC"
    assert match["date"] == "2026-06-15"

    players = store.get_match_players(match_id)
    player_ids = {p["user_id"] for p in players}
    assert player_ids == {user1["id"], user2["id"]}


# ---------------------------------------------------------------------------
# GET /matches/<id> (match_detail)
# ---------------------------------------------------------------------------

def test_match_detail_404_for_unknown_match(client):
    _login(client)
    resp = client.get("/matches/999999")
    assert resp.status_code == 404
    assert b"Match not found." in resp.data


def test_match_detail_marks_lowest_net_as_winner(client):
    """Player with the lower total net across linked rounds is the winner."""
    user1 = _login(client, username="alice", password="alicepass")
    user2 = store.create_user("bob", "Bob", "bobpassword")
    _make_course(client)

    match_id = store.create_match(created_by=user1["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user1["id"])
    store.add_match_player(match_id, user2["id"])

    round_a = _save_round_with_handicap(user1["id"], date="2026-06-01", gross="80")
    round_b = _save_round_with_handicap(user2["id"], date="2026-06-01", gross="90")
    store.link_round(match_id, user1["id"], round_a, net=70.0)  # lower net -> winner
    store.link_round(match_id, user2["id"], round_b, net=75.0)

    resp = client.get(f"/matches/{match_id}")
    assert resp.status_code == 200
    assert resp.data.count(b"WINNER") == 1

    players = store.get_match_players(match_id)
    winner = next(p for p in players if p["user_id"] == user1["id"])
    loser = next(p for p in players if p["user_id"] == user2["id"])
    assert winner["total_net"] == 70.0
    assert loser["total_net"] == 75.0


def test_match_detail_visible_to_participant(client):
    """A participant can view their own match (200)."""
    # First-created user is auto-admin; create a throwaway admin first so the
    # participant below is a plain non-admin whose access comes purely from
    # participation, not the admin exemption.
    store.create_user("admin", "Admin", "adminpw")
    _save_course_direct()

    user1 = _login(client, username="alice", display="Alice", password="alicepass")
    match_id = store.create_match(created_by=user1["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user1["id"])

    resp = client.get(f"/matches/{match_id}")
    assert resp.status_code == 200


def test_match_detail_hidden_from_non_participant(client):
    """A logged-in non-participant, non-admin must NOT be able to read a match
    they aren't in. Returns 404 (not 403) so the response doesn't confirm the
    resource exists -- IDOR fix, see PR #28."""
    # Auto-admin absorbed by a throwaway first user; owner is a plain user.
    store.create_user("admin", "Admin", "adminpw")
    user1 = store.create_user("alice", "Alice", "alicepass")
    _save_course_direct()
    match_id = store.create_match(created_by=user1["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user1["id"])

    _login(client, username="outsider", display="Outsider", password="outsiderpw")
    resp = client.get(f"/matches/{match_id}")
    assert resp.status_code == 404


def test_match_detail_visible_to_admin_non_participant(client):
    """An admin who is not a participant retains access (200) -- admins are
    exempt from the participant gate."""
    # First-created user is the auto-admin; log in as them.
    admin = _login(client, username="admin", display="Admin", password="adminpw")
    assert admin["is_admin"] is True

    user1 = store.create_user("alice", "Alice", "alicepass")
    _save_course_direct()
    match_id = store.create_match(created_by=user1["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user1["id"])

    resp = client.get(f"/matches/{match_id}")
    assert resp.status_code == 200


def test_match_detail_renders_per_round_gross_net_fir_gir(client, capture_render):
    """_build_round_details() computes gross/net/fir_display/gir_display per
    linked round -- exercise it with detailed hole data and a distinctive
    linked net value, and assert those exact figures land in round_details
    (capturing the route context directly, since the total_net podium column
    can coincidentally render the same digits as a per-round net figure)."""
    user = _login(client)
    _make_course(client, slope=120, rating=70.0)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])

    holes = {
        str(n): {"gross": "5", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"}
        for n in range(1, 19)
    }
    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "detailed", "holes": holes, "total_gross": "90",
        "differential": "10.0", "notes": "", "excluded": False,
        "computed_handicap": "14.0", "differential_locked": False,
    }
    round_id = store.save_round(golf_round, "2026-06-01", 0, user_id=user["id"])
    store.link_round(match_id, user["id"], round_id, net=78.0)

    resp = client.get(f"/matches/{match_id}")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert len(ctx["round_details"]) == 1
    rd = ctx["round_details"][0]
    assert rd["gross"] == 90    # sum of 18 holes @ gross=5
    assert rd["net"] == 78      # int(mr["net"]) as linked
    assert rd["fir_display"] == "18/18"  # every non-par-3 hole fairway hit
    assert rd["gir_display"] == "0/18"   # every green marked missed


# ---------------------------------------------------------------------------
# GET/POST /matches/<id>/link-round
# ---------------------------------------------------------------------------

def test_match_link_round_403_for_non_participant(client):
    user1 = store.create_user("alice", "Alice", "alicepass")
    _save_course_direct()
    match_id = store.create_match(created_by=user1["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user1["id"])

    _login(client, username="outsider", password="outsiderpw")
    resp = client.get(f"/matches/{match_id}/link-round")
    assert resp.status_code == 403
    assert b"not a participant" in resp.data


def test_match_link_round_404_for_unknown_match(client):
    _login(client)
    resp = client.get("/matches/999999/link-round")
    assert resp.status_code == 404


def test_match_link_round_get_only_lists_rounds_with_computed_handicap(client):
    """Rounds without a computed_handicap must be excluded from the
    'unlinked' selection list (route filters `if not rd.computed_handicap`)."""
    user = _login(client)
    _make_course(client)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])

    eligible_id = _save_round_with_handicap(user["id"], date="2026-06-01", gross="85", computed_handicap="14.0")
    _save_round_with_handicap(user["id"], date="2026-06-02", gross="88", computed_handicap="")  # no handicap yet

    resp = client.get(f"/matches/{match_id}/link-round")
    assert resp.status_code == 200
    assert f'value="{eligible_id}"'.encode() in resp.data
    # only one radio input should be present (the eligible round)
    assert resp.data.count(b'name="round_id"') == 1


def test_match_link_round_post_no_round_selected_shows_error(client):
    user = _login(client)
    _make_course(client)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])

    resp = client.post(f"/matches/{match_id}/link-round", data={})
    assert resp.status_code == 200
    assert b"Please select a round." in resp.data


def test_match_link_round_post_already_linked_shows_error(client):
    user = _login(client)
    _make_course(client)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])
    round_id = _save_round_with_handicap(user["id"])
    store.link_round(match_id, user["id"], round_id, net=70.0)

    resp = client.post(f"/matches/{match_id}/link-round", data={"round_id": str(round_id)})
    assert resp.status_code == 200
    assert b"already linked" in resp.data


def test_match_link_round_post_rejects_round_owned_by_another_user(client):
    """A participant cannot link a round_id that belongs to a different
    user, even if both are match participants."""
    user1 = _login(client, username="alice", password="alicepass")
    user2 = store.create_user("bob", "Bob", "bobpassword")
    _make_course(client)
    match_id = store.create_match(created_by=user1["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user1["id"])
    store.add_match_player(match_id, user2["id"])

    bobs_round_id = _save_round_with_handicap(user2["id"], date="2026-06-01", gross="85")

    resp = client.post(f"/matches/{match_id}/link-round", data={"round_id": str(bobs_round_id)})
    assert resp.status_code == 200
    assert b"Round not found." in resp.data
    assert store.get_match_rounds(match_id) == []


def test_match_link_round_post_rejects_round_without_handicap(client):
    user = _login(client)
    _make_course(client)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])
    round_id = _save_round_with_handicap(user["id"], computed_handicap="")

    resp = client.post(f"/matches/{match_id}/link-round", data={"round_id": str(round_id)})
    assert resp.status_code == 200
    assert b"Cannot link a round without a handicap index." in resp.data


def test_match_link_round_post_success_computes_net_and_redirects(client):
    user = _login(client)
    _make_course(client, slope=120, rating=70.0)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])
    round_id = _save_round_with_handicap(user["id"], gross="85", computed_handicap="14.0")

    resp = client.post(f"/matches/{match_id}/link-round", data={"round_id": str(round_id)},
                        follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/matches/{match_id}")

    links = store.get_match_rounds(match_id)
    assert len(links) == 1
    assert links[0]["round_id"] == round_id

    # Hand-computed (not via calc_course_handicap, to actually catch a
    # formula bug there): round(14.0 * (120/113) + (70.0-72)) = round(12.867..) = 13
    expected_ch = 13
    expected_net = 85 - expected_ch
    assert expected_net == 72
    assert float(links[0]["net"]) == float(expected_net)


def test_match_link_round_get_excludes_already_linked_rounds(client):
    user = _login(client)
    _make_course(client)
    match_id = store.create_match(created_by=user["id"], course_name="Test GC", date="2026-06-01")
    store.add_match_player(match_id, user["id"])
    round_id = _save_round_with_handicap(user["id"], computed_handicap="14.0")
    store.link_round(match_id, user["id"], round_id, net=70.0)

    resp = client.get(f"/matches/{match_id}/link-round")
    assert resp.status_code == 200
    assert resp.data.count(b'name="round_id"') == 0
