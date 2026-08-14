"""Integration tests for source/routes/dashboard.py.

See tests/test_stats_routes.py's module docstring for the rationale behind
building an isolated Flask app here (avoids colliding with the main.app
singleton that tests/test_routes.py registers routes on) and for
monkeypatching render_template to capture exact computed context values
instead of scraping fragile, macro-split Jinja HTML output.
"""

import json
from pathlib import Path

import pytest
from flask import Flask
from flask_login import LoginManager

import main as main_mod
from source.extensions import init_app as init_extensions
from source.plugin import _plugins
from source.routes import register_routes
from database import set_db_path, init_db
from store import (
    get_user_by_id, create_user, save_course, save_round, save_settings,
    get_all_matches, get_all_challenges, create_match, add_match_player, link_round,
)


# ---------------------------------------------------------------------------
# Isolated app builder
# ---------------------------------------------------------------------------

class _TestUser:
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.display_name = user_dict["display_name"]
        self.is_admin = user_dict.get("is_admin", False)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


def _build_app():
    src_dir = Path(main_mod.__file__).parent
    app = Flask(
        "test_dashboard_app",
        root_path=str(src_dir),
        template_folder="web/templates",
        static_folder="web/static",
    )
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login_page"

    @login_manager.user_loader
    def _load_user(user_id):
        d = get_user_by_id(int(user_id))
        return _TestUser(d) if d else None

    limiter, csrf = init_extensions(app)
    limiter.enabled = False
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"

    @app.context_processor
    def _inject_plugin_globals():
        return {
            "plugin_blocks": getattr(app, "_plugin_blocks", {}),
            "plugin_nav": getattr(app, "_plugin_nav", []),
            "plugin_info": {p.plugin_info["name"]: p.plugin_info for p in _plugins if hasattr(p, "plugin_info")},
        }

    register_routes(app, limiter, csrf, _TestUser)
    return app


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "drafts").mkdir()

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    app = _build_app()
    app.config["DB_PATH"] = db_path
    return app


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def auth_client(client):
    """Logged-in client for a freshly created user (id=1)."""
    create_user("golfer", "Golfer", "pass1234")
    client.post("/login", data={"username": "golfer", "password": "pass1234"})
    return client


def _mark_welcome_shown(user_id=1):
    save_settings({"welcome_shown": True}, user_id=user_id)


@pytest.fixture
def capture_render(monkeypatch):
    """Monkeypatch source.routes.dashboard.render_template to capture the
    (template_name, context) instead of rendering Jinja."""
    captured = {}

    def _fake_render_template(name, **kwargs):
        captured["template"] = name
        captured["ctx"] = kwargs
        return ""

    monkeypatch.setattr("source.routes.dashboard.render_template", _fake_render_template)
    return captured


# ---------------------------------------------------------------------------
# Round/course seeding helpers (mirrors tests/test_stats_routes.py's dataset)
# ---------------------------------------------------------------------------

HOLE_PARS = {n: (3 if n in (4, 8, 12, 16) else 5 if n in (2, 6, 10, 14, 18) else 4) for n in range(1, 19)}
COURSE_NAME = "Test GC"


def _seed_course(name=COURSE_NAME, slope=125, rating=70.5):
    holes = {str(n): {"par": HOLE_PARS[n], "hole_index": n} for n in range(1, 19)}
    save_course({
        "par": "73",
        "holes": holes,
        "tees": {"White": {"slope": slope, "rating": rating, "yardage": "6200"}},
    }, name)


def _uniform_holes(delta=0, fir="H", gir="H", putts=2, penalties=0):
    holes = {}
    for n in range(1, 19):
        par = HOLE_PARS[n]
        gross = max(1, par + delta)
        holes[str(n)] = {
            "gross": str(gross),
            "putts": str(putts),
            "fairway": (fir if par != 3 else ""),
            "gir": gir,
            "penalties": str(penalties),
        }
    return holes


def _total(holes):
    return sum(int(h["gross"]) for h in holes.values())


def _save(date, index, holes, differential, computed_handicap="10.0", user_id=1, course=COURSE_NAME):
    save_round({
        "course": course, "tees": "White", "holes_played": "all",
        "entry_mode": "detailed", "holes": holes,
        "total_gross": str(_total(holes)),
        "differential": differential,
        "notes": "", "excluded": False,
        "computed_handicap": computed_handicap,
        "differential_locked": False,
    }, date, index, user_id=user_id)


def _seed_three_rounds(user_id=1):
    """Same dataset used in tests/test_stats_routes.py:
    r1 (2026-03-01): every hole at par, 2 putts/hole, all FIR/GIR hit -> gross 73
    r2 (2026-03-08): every hole +1, all FIR/GIR missed -> gross 91
    r3 (2026-03-15): every hole +2, FIR hit / GIR missed, 3 putts/hole -> gross 109
    """
    _seed_course()
    _save("2026-03-01", 0, _uniform_holes(delta=0, fir="H", gir="H", putts=2), "8.0", "9.0", user_id=user_id)
    _save("2026-03-08", 0, _uniform_holes(delta=1, fir="L", gir="L", putts=2), "20.0", "14.0", user_id=user_id)
    _save("2026-03-15", 0, _uniform_holes(delta=2, fir="H", gir="L", putts=3), "30.0", "18.0", user_id=user_id)


# ---------------------------------------------------------------------------
# Auth / welcome gating
# ---------------------------------------------------------------------------

def test_dashboard_requires_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dashboard_shows_welcome_screen_before_welcome_shown(auth_client, capture_render):
    """A brand-new user (welcome_shown unset/False) must see the welcome
    screen instead of the social dashboard, regardless of rankings data."""
    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert capture_render["template"] == "welcome.html"


def test_profile_shows_welcome_screen_before_welcome_shown(auth_client, capture_render):
    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    assert capture_render["template"] == "welcome.html"


def test_api_welcome_marks_welcome_shown(auth_client, capture_render):
    resp = auth_client.post("/api/welcome")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    # dashboard should now render the real social dashboard, not welcome.html
    resp2 = auth_client.get("/")
    assert resp2.status_code == 200
    assert capture_render["template"] == "dashboard_social.html"


# ---------------------------------------------------------------------------
# "/" dashboard rankings
# ---------------------------------------------------------------------------

def test_dashboard_rankings_no_rounds_shows_zero_rank(auth_client, capture_render):
    _mark_welcome_shown()
    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert len(ctx["rankings"]) == 1
    assert ctx["rankings"][0]["stats"]["handicap"] is None
    assert ctx["you_rank"] == 1
    assert ctx["featured_match"] is None
    assert ctx["featured_challenge"] is None


def test_dashboard_rankings_computes_expected_values_single_user(auth_client, capture_render):
    _mark_welcome_shown()
    _seed_three_rounds()
    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert len(ctx["rankings"]) == 1
    entry = ctx["rankings"][0]
    assert entry["user_id"] == 1
    # scoring average over best-8 (== all 3 rounds here): mean(73, 91, 109)
    assert entry["stats"]["score"] == 91.0
    assert entry["stats"]["fir"] == pytest.approx(66.6666, rel=1e-4)
    assert entry["stats"]["gir"] == pytest.approx(33.3333, rel=1e-4)
    assert entry["stats"]["putts"] == 42.0
    assert ctx["you_rank"] == 1
    # sole ranked player always leads on *some* stat
    assert entry["stats"]["lead_stat"] is not None


def test_dashboard_rankings_orders_two_users_by_sort_key(auth_client, capture_render):
    """Two users with distinct scoring averages: sorting by "score" ascending
    (lower is better) must put the better scorer first, and board_meta must
    reflect the min/max/avg across both users."""
    _mark_welcome_shown(user_id=1)
    _seed_three_rounds(user_id=1)  # golfer: avg score 91.0

    create_user("rival", "Rival Golfer", "pass1234")
    _mark_welcome_shown(user_id=2)
    rival_holes = _uniform_holes(delta=0)
    rival_holes["1"]["gross"] = str(int(rival_holes["1"]["gross"]) + 20)  # 73 + 20 = 93
    _save("2026-03-01", 0, rival_holes, "35.0", "20.0", user_id=2)  # gross 93, single round avg 93.0

    resp = auth_client.get("/?sort=score")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert len(ctx["rankings"]) == 2
    assert [r["user_id"] for r in ctx["rankings"]] == [1, 2]  # 91.0 < 93.0
    assert ctx["current_sort"] == "score"
    assert ctx["current_desc"] is False
    assert ctx["board_meta"]["score"]["min"] == 91.0
    assert ctx["board_meta"]["score"]["max"] == 93.0
    assert ctx["board_meta"]["score"]["avg"] == pytest.approx(92.0)


def test_dashboard_date_filter_excludes_rounds_outside_range(auth_client, capture_render):
    """The ?from=/&to= query params must scope which rounds count toward
    each user's ranking stats."""
    _mark_welcome_shown()
    _seed_three_rounds()

    # only r1 (2026-03-01) falls in this window -> scoring avg == 73.0, not 91.0
    resp = auth_client.get("/?from=2026-03-01&to=2026-03-01")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["date_from"] == "2026-03-01"
    assert ctx["date_to"] == "2026-03-01"
    assert ctx["rankings"][0]["stats"]["score"] == 73.0


def test_dashboard_season_label_reflects_current_month(auth_client, capture_render):
    _mark_welcome_shown()
    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert any(season in ctx["season_label"] for season in ("Winter", "Spring", "Summer", "Fall"))


# ---------------------------------------------------------------------------
# /profile
# ---------------------------------------------------------------------------

def test_profile_no_rounds_blank_panels(auth_client, capture_render):
    _mark_welcome_shown()
    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["panels"]["handicap"]["value"] == "--"
    assert ctx["rounds"] == []
    assert ctx["career_low"] is None


def test_profile_computes_expected_panels_and_rounds(auth_client, capture_render):
    _mark_welcome_shown()
    _seed_three_rounds()
    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # score panel value formatted as "{value:.1f}{suffix}" from calc_scoring_average(b8)
    assert ctx["panels"]["score"]["value"] == "91.0"
    assert ctx["panels"]["fir"]["value"] == "66.7%"
    assert ctx["panels"]["gir"]["value"] == "33.3%"

    assert len(ctx["rounds"]) == 3
    most_recent = ctx["rounds"][0]
    assert most_recent["date"] == "2026-03-15"
    assert most_recent["total"] == "109"
    # score_to_par = total_gross - played_par = 109 - 73 = 36
    assert most_recent["score_to_par"] == 36
    assert most_recent["fir_display"] == "14/14"   # every eligible fairway hit
    assert most_recent["gir_display"] == "0/18"    # every green missed
    assert most_recent["putts"] == 54

    best = ctx["rounds"][2]
    assert best["date"] == "2026-03-01"
    assert best["total"] == "73"
    assert best["score_to_par"] == 0
    assert best["in_handicap"] is True


def test_profile_chart_data_json_has_expected_range_keys(auth_client, capture_render):
    _mark_welcome_shown()
    _seed_three_rounds()
    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    chart_data = json.loads(ctx["chart_data_json"])
    assert set(chart_data.keys()) == {"3M", "12M", "2Y", "All"}
    # "All" uses every round's computed_handicap, chronological order (oldest -> newest)
    assert chart_data["All"]["points"][0]["v"] == "9.0"
    assert chart_data["All"]["points"][-1]["v"] == "18.0"


# ---------------------------------------------------------------------------
# /challenges/new
# ---------------------------------------------------------------------------

def test_challenge_new_get_lists_users_and_catalog(auth_client, capture_render):
    resp = auth_client.get("/challenges/new")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert len(ctx["users"]) == 1
    assert any(s["key"] == "handicap" for s in ctx["stat_catalog"])


def test_challenge_new_post_missing_title_shows_error(auth_client, capture_render):
    create_user("p2", "Player Two", "pass1234")
    resp = auth_client.post("/challenges/new", data={
        "title": "", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-02-01",
        "stat_key": "handicap",
    })
    assert resp.status_code == 200
    assert capture_render["ctx"]["error"] == "Title is required."


def test_challenge_new_post_needs_two_participants(auth_client, capture_render):
    resp = auth_client.post("/challenges/new", data={
        "title": "Solo Challenge", "participants": ["1"],
        "start_date": "2026-01-01", "end_date": "2026-02-01",
        "stat_key": "handicap",
    })
    assert resp.status_code == 200
    assert capture_render["ctx"]["error"] == "At least 2 participants are required."


def test_challenge_new_post_rejects_end_before_start(auth_client, capture_render):
    create_user("p2", "Player Two", "pass1234")
    resp = auth_client.post("/challenges/new", data={
        "title": "Backwards", "participants": ["1", "2"],
        "start_date": "2026-02-01", "end_date": "2026-01-01",
        "stat_key": "handicap",
    })
    assert resp.status_code == 200
    assert capture_render["ctx"]["error"] == "End date must be after start date."


def test_challenge_new_post_rejects_unknown_stat_key(auth_client, capture_render):
    create_user("p2", "Player Two", "pass1234")
    resp = auth_client.post("/challenges/new", data={
        "title": "Bogus Stat", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-02-01",
        "stat_key": "not_a_real_stat",
    })
    assert resp.status_code == 200
    assert capture_render["ctx"]["error"] == "Invalid stat selected."


def test_challenge_new_post_success_creates_challenge_and_redirects(auth_client):
    create_user("p2", "Player Two", "pass1234")
    resp = auth_client.post("/challenges/new", data={
        "title": "Best Handicap", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "stat_key": "handicap",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/challenges/1"

    challenges = get_all_challenges()
    assert len(challenges) == 1
    assert challenges[0]["title"] == "Best Handicap"


# ---------------------------------------------------------------------------
# /challenges/<id>
# ---------------------------------------------------------------------------

def test_challenge_detail_404_for_missing_challenge(auth_client):
    resp = auth_client.get("/challenges/999")
    assert resp.status_code == 404


def test_challenge_detail_computes_leaderboard(auth_client, capture_render):
    _seed_three_rounds(user_id=1)
    create_user("p2", "Player Two", "pass1234")
    auth_client.post("/challenges/new", data={
        "title": "HI Battle", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "stat_key": "handicap",
    })

    resp = auth_client.get("/challenges/1")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["challenge"]["title"] == "HI Battle"
    board_by_user = {row["user_id"]: row for row in ctx["leaderboard"]}
    # user 1 played 3 rounds in range, computed handicap == 8.0 (see stats golden values)
    assert board_by_user[1]["value"] == 8.0
    assert board_by_user[1]["round_count"] == 3
    # user 2 never played -> no value, no rank
    assert board_by_user[2]["value"] is None
    assert board_by_user[2]["round_count"] == 0
    # the participant with an actual value must be the leader
    assert ctx["leaderboard"][0]["user_id"] == 1
    assert ctx["leaderboard"][0].get("is_leader") is True


def test_challenge_detail_leaderboard_orders_by_lower_handicap_first(auth_client, capture_render):
    """With BOTH participants holding a valid (non-None) handicap value, the
    leaderboard must be sorted with the lower (better) handicap first --
    higher_better=False for the "handicap" stat. A single-participant-with-
    a-value dataset can't distinguish correct sort direction from a flipped
    `reverse` bug; this seeds two distinct values and asserts order."""
    _seed_three_rounds(user_id=1)  # user 1: diffs [8.0, 20.0, 30.0] -> best-1 HI == 8.0
    create_user("p2", "Player Two", "pass1234")
    # user 2: worse (higher) diffs -> best-1 HI == 15.0, strictly worse than user 1's 8.0
    for i, diff in enumerate(["15.0", "16.0", "17.0"]):
        _save(f"2026-04-0{i + 1}", 0, _uniform_holes(delta=0), diff, computed_handicap="15.0", user_id=2)

    auth_client.post("/challenges/new", data={
        "title": "HI Battle", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "stat_key": "handicap",
    })

    resp = auth_client.get("/challenges/1")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    board_by_user = {row["user_id"]: row for row in ctx["leaderboard"]}
    assert board_by_user[1]["value"] == 8.0
    assert board_by_user[2]["value"] == 15.0
    # lower handicap is better -> user 1 (8.0) must rank ahead of user 2 (15.0)
    assert [row["user_id"] for row in ctx["leaderboard"]] == [1, 2]
    assert ctx["leaderboard"][0]["user_id"] == 1
    assert ctx["leaderboard"][0].get("is_leader") is True


# ---------------------------------------------------------------------------
# _featured_match / _featured_challenge (exercised through "/")
# ---------------------------------------------------------------------------

def test_dashboard_featured_match_summarizes_active_match(auth_client, capture_render):
    _mark_welcome_shown()
    _seed_course()
    round_id = None
    holes = _uniform_holes(delta=0)
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "all",
        "entry_mode": "detailed", "holes": holes, "total_gross": "73",
        "differential": "8.0", "notes": "", "excluded": False,
        "computed_handicap": "9.0", "differential_locked": False,
    }, "2026-03-01", 0, user_id=1)

    from store import get_all_rounds
    round_id = get_all_rounds(user_id=1)[0].id

    match_id = create_match(created_by=1, course_name=COURSE_NAME, date="2026-03-01")
    add_match_player(match_id, 1)
    link_round(match_id, 1, round_id, net=-2.0)

    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    fm = ctx["featured_match"]
    assert fm is not None
    assert fm["course_name"] == COURSE_NAME
    assert fm["status"] == "active"
    assert len(fm["participants"]) == 1
    assert fm["participants"][0]["net_total"] == -2.0
    assert fm["participants"][0]["is_you"] is True
    assert fm["participants"][0]["is_leader"] is True
    # 18 holes completed on the linked round / 18 max holes -> full progress
    assert fm["progress"] == 1.0


def test_dashboard_featured_match_partial_round_yields_half_progress(auth_client, capture_render):
    """A linked round with only 9 recorded holes must yield progress==0.5
    (completed/max_holes), not the always-1.0 result of the full-18 case --
    this exercises the min(completed/max_holes, 1.0) denominator rather than
    only ever hitting the clamp."""
    _mark_welcome_shown()
    _seed_course()
    nine_holes = {
        str(n): {
            "gross": str(HOLE_PARS[n]), "putts": "2",
            "fairway": "H" if HOLE_PARS[n] != 3 else "", "gir": "H", "penalties": "0",
        }
        for n in range(1, 10)
    }
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "front9",
        "entry_mode": "detailed", "holes": nine_holes, "total_gross": "36",
        "differential": "8.0", "notes": "", "excluded": False,
        "computed_handicap": "9.0", "differential_locked": False,
    }, "2026-03-01", 0, user_id=1)

    from store import get_all_rounds
    round_id = get_all_rounds(user_id=1)[0].id

    match_id = create_match(created_by=1, course_name=COURSE_NAME, date="2026-03-01")
    add_match_player(match_id, 1)
    link_round(match_id, 1, round_id, net=-2.0)

    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    fm = ctx["featured_match"]
    assert fm is not None
    # 9 holes completed / 18 max holes -> 0.5
    assert fm["progress"] == 0.5


def test_dashboard_featured_challenge_summarizes_active_challenge(auth_client, capture_render):
    _mark_welcome_shown(user_id=1)
    _seed_three_rounds(user_id=1)
    create_user("p2", "Player Two", "pass1234")

    auth_client.post("/challenges/new", data={
        "title": "Featured HI Battle", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "stat_key": "handicap",
    })

    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    fc = ctx["featured_challenge"]
    assert fc is not None
    assert fc["title"] == "Featured HI Battle"
    assert fc["submitted_count"] == 1
    board_by_name = {row["display_name"]: row for row in fc["leaderboard"]}
    assert board_by_name["Golfer"]["value"] == 8.0
    assert board_by_name["Golfer"]["is_you"] is True
    assert board_by_name["Golfer"].get("is_leader") is True


def test_dashboard_featured_challenge_leaderboard_orders_by_lower_handicap_first(auth_client, capture_render):
    """With BOTH participants holding a valid handicap value, the featured
    challenge leaderboard must sort the lower (better) handicap first. A
    single-participant-with-a-value dataset (as above) can't catch a flipped
    `reverse=higher_better` sort bug; this seeds two distinct values."""
    _mark_welcome_shown(user_id=1)
    _seed_three_rounds(user_id=1)  # user 1: best-1 HI == 8.0
    create_user("p2", "Player Two", "pass1234")
    # user 2: worse (higher) diffs -> best-1 HI == 15.0
    for i, diff in enumerate(["15.0", "16.0", "17.0"]):
        _save(f"2026-04-0{i + 1}", 0, _uniform_holes(delta=0), diff, computed_handicap="15.0", user_id=2)

    auth_client.post("/challenges/new", data={
        "title": "Featured HI Battle", "participants": ["1", "2"],
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "stat_key": "handicap",
    })

    resp = auth_client.get("/")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    fc = ctx["featured_challenge"]
    assert fc is not None
    assert fc["submitted_count"] == 2
    board_by_name = {row["display_name"]: row for row in fc["leaderboard"]}
    assert board_by_name["Golfer"]["value"] == 8.0
    assert board_by_name["Player Two"]["value"] == 15.0
    # lower handicap is better -> "Golfer" (8.0) must rank ahead of "Player Two" (15.0)
    assert [row["display_name"] for row in fc["leaderboard"]] == ["Golfer", "Player Two"]
    assert fc["leaderboard"][0].get("is_leader") is True


# ---------------------------------------------------------------------------
# _build_profile_context: front/back holes_selection and last-year subtitle
# ---------------------------------------------------------------------------

def test_profile_front_nine_round_computes_played_par_and_net_score(auth_client, capture_render):
    """A front-9 round with detailed hole data must derive played_par from
    only the holes actually played (not the full 18), and must compute a
    net score from the course handicap formula."""
    _mark_welcome_shown()
    _seed_course()
    front_holes = {
        str(n): {"gross": str(HOLE_PARS[n]), "putts": "2", "fairway": "H" if HOLE_PARS[n] != 3 else "", "gir": "H", "penalties": "0"}
        for n in range(1, 10)
    }
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "front9",
        "entry_mode": "detailed", "holes": front_holes, "total_gross": "36",
        "differential": "5.0", "notes": "", "excluded": False,
        "computed_handicap": "10.0", "differential_locked": False,
    }, "2026-05-01", 0, user_id=1)

    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    rd = ctx["rounds"][0]
    assert rd["score_to_par"] == 0     # played_par == 36 == total_gross(36)
    # net_score = total_gross - course_handicap; course_handicap = round(5.0 * (125/113) + (70.5-36)) = 40
    assert rd["net"] == -4
    assert rd["net_to_par"] == -40


def test_profile_back_nine_score_only_round_uses_course_half_split(auth_client, capture_render):
    """A back-9 round saved without per-hole data must fall back to summing
    par across the course's back-9 hole definitions."""
    _mark_welcome_shown()
    _seed_course()
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "back9",
        "entry_mode": "score_only", "holes": {}, "total_gross": "37",
        "differential": "6.0", "notes": "", "excluded": False,
        "computed_handicap": "", "differential_locked": False,
    }, "2026-05-08", 0, user_id=1)

    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    rd = ctx["rounds"][0]
    # back-9 pars (holes 10-18): 5+4+3+4+5+4+3+4+5 = 37
    assert rd["score_to_par"] == 0
    assert rd["net"] is None  # no computed_handicap -> net score calc is skipped


def test_profile_last_year_handicap_subtitle_when_round_near_one_year_old(auth_client, capture_render):
    from datetime import date, timedelta
    _mark_welcome_shown()
    _seed_three_rounds()
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "all",
        "entry_mode": "detailed", "holes": _uniform_holes(delta=0), "total_gross": "73",
        "differential": "8.0", "notes": "", "excluded": False,
        "computed_handicap": "16.0", "differential_locked": False,
    }, year_ago, 0, user_id=1)

    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["panels"]["handicap"].get("subtitle") == "1y 16.0"


# ---------------------------------------------------------------------------
# Regression: issue #47 — the "Recent rounds" round-type filter chips were
# unwired static <span>s that did nothing on click. They were removed until a
# per-round round-type dimension exists (blocked on #46). This test renders the
# real profile HTML (no capture_render stub) and locks in that the dead chips
# stay gone while the separately-wired chart-card range chips remain.
# ---------------------------------------------------------------------------

def test_profile_has_no_unwired_roundtype_filter_chips(auth_client):
    _mark_welcome_shown()
    _seed_three_rounds()
    resp = auth_client.get("/profile")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # The dead round-type chips must not be reintroduced (#47). Covers the full
    # original 5-chip set: the "All" active chip plus all four type labels.
    for label in ("Normal", "Tournament", "Qualifying", "Practice"):
        assert f'<span class="ps-chip">{label}</span>' not in html
    assert '<span class="ps-chip is-on">All</span>' not in html

    # The chart-card range chips (a different, wired .ps-filters block) must
    # remain — guards against an over-broad removal of all chips.
    assert 'data-range="12M"' in html
    assert 'class="ps-chart-card"' in html
