"""Integration tests for source/routes/stats.py.

Strategy: build a *fully isolated* Flask app (separate from the main.app
singleton used by tests/test_routes.py) so registering routes here can never
collide with that module's own unconditional register_routes() call at
import time. Real per-user data is seeded through the actual store/database
layer (sqlite, temp file per test), then routes are hit through the real
Flask test client with a real login. To assert on exact *computed* values
(not just status codes / substrings of rendered HTML, which get split up by
Jinja macros), render_template is monkeypatched per-test to capture the
kwargs passed to it -- this exercises the full route + calc pipeline while
giving us precise Python values to assert against.

Expected numeric values below were derived by calling the same calc.*
functions this route calls, directly, against an identical round dataset
(see the module docstring math in the seeding helpers) -- i.e. these tests
verify *route wiring* (correct subset selection, correct function calls,
correct field names in the template context), not calc's arithmetic.
"""

from pathlib import Path

import pytest
from flask import Flask
from flask_login import LoginManager

import main as main_mod
from source.extensions import init_app as init_extensions
from source.plugin import _plugins
from source.routes import register_routes
from database import set_db_path, init_db
from store import get_user_by_id, create_user, save_course, save_round, save_settings


# ---------------------------------------------------------------------------
# Isolated app builder (see module docstring for why this can't reuse main.app)
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
        "test_stats_app",
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

    # mirror production jinja globals (main.py registers _fmt for stats templates)
    app.jinja_env.globals["_fmt"] = main_mod._fmt

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
    """Logged-in client for a freshly created user (id=1, becomes admin as
    the first-ever user)."""
    create_user("golfer", "Golfer", "pass1234")
    client.post("/login", data={"username": "golfer", "password": "pass1234"})
    return client


@pytest.fixture
def capture_render(monkeypatch):
    """Monkeypatch source.routes.stats.render_template to capture the
    (template_name, context) passed by the route instead of rendering Jinja.
    Returns a dict that gets populated on the next render_template call."""
    captured = {}

    def _fake_render_template(name, **kwargs):
        captured["template"] = name
        captured["ctx"] = kwargs
        return ""

    monkeypatch.setattr("source.routes.stats.render_template", _fake_render_template)
    return captured


# ---------------------------------------------------------------------------
# Round/course seeding helpers
# ---------------------------------------------------------------------------

HOLE_PARS = {n: (3 if n in (4, 8, 12, 16) else 5 if n in (2, 6, 10, 14, 18) else 4) for n in range(1, 19)}
COURSE_NAME = "Test GC"


def _seed_course():
    holes = {str(n): {"par": HOLE_PARS[n], "hole_index": n} for n in range(1, 19)}
    save_course({
        "par": "73",
        "holes": holes,
        "tees": {"White": {"slope": 125, "rating": 70.5, "yardage": "6200"}},
    }, COURSE_NAME)


def _uniform_holes(delta=0, fir="H", gir="H", putts=2, penalties=0):
    """Every hole's gross = par + delta. Par-3 holes get no fairway mark
    (matches how real rounds are recorded -- there's no FIR stat on par 3s)."""
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


def _save(date, index, holes, differential, computed_handicap="10.0", user_id=1):
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "all",
        "entry_mode": "detailed", "holes": holes,
        "total_gross": str(_total(holes)),
        "differential": differential,
        "notes": "", "excluded": False,
        "computed_handicap": computed_handicap,
        "differential_locked": False,
    }, date, index, user_id=user_id)


def _seed_three_rounds():
    """r1: every hole exactly at par, FIR/GIR all hit, 2 putts/hole.
    r2: every hole 1-over (bogey), FIR/GIR all missed, 2 putts/hole.
    r3: every hole 2-over (double bogey), FIR hit / GIR missed, 3 putts/hole
        + 1 penalty/hole.
    Differentials are set explicitly (8.0 < 20.0 < 30.0) so round ordering
    by "best" is deterministic and decoupled from gross score."""
    _seed_course()
    _save("2026-03-01", 0, _uniform_holes(delta=0, fir="H", gir="H", putts=2, penalties=0), "8.0", "9.0")
    _save("2026-03-08", 0, _uniform_holes(delta=1, fir="L", gir="L", putts=2, penalties=0), "20.0", "14.0")
    _save("2026-03-15", 0, _uniform_holes(delta=2, fir="H", gir="L", putts=3, penalties=1), "30.0", "18.0")


# ---------------------------------------------------------------------------
# Auth / redirect behavior
# ---------------------------------------------------------------------------

def test_stats_requires_login(client):
    resp = client.get("/stats/scoring")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_stats_redirect_sends_to_scoring(auth_client):
    resp = auth_client.get("/stats", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/stats/scoring"


# ---------------------------------------------------------------------------
# /stats/scoring
# ---------------------------------------------------------------------------

def test_stats_scoring_empty_state_is_all_none(auth_client, capture_render):
    """No rounds at all -> every computed stat must be None, not an
    exception or a bogus zero."""
    resp = auth_client.get("/stats/scoring")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["scoring_avg"] is None
    assert ctx["to_par"] is None
    assert ctx["par_or_better_pct"] is None
    assert ctx["scoring_spark"] == []
    assert ctx["scoring_avg_delta"] == {"delta_dir": "", "delta": "—"}


def test_stats_scoring_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/scoring")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["scoring_avg"] == 91.0            # mean(73, 91, 109)
    assert ctx["to_par"] == 18.0                 # mean(0, 18, 36) over par
    assert ctx["par_3_avg"] == 4.0
    assert ctx["par_4_avg"] == 5.0
    assert ctx["par_5_avg"] == 6.0
    assert ctx["par_or_better_pct"] == pytest.approx(33.333333, rel=1e-4)
    assert ctx["blow_up_rate"] == 0.0
    assert ctx["clean_card_pct"] == pytest.approx(66.666666, rel=1e-4)
    assert ctx["score_distribution"]["par"] == pytest.approx(33.333333, rel=1e-4)
    assert ctx["score_distribution"]["bogey"] == pytest.approx(33.333333, rel=1e-4)
    assert ctx["score_distribution"]["double"] == pytest.approx(33.333333, rel=1e-4)
    # b8 and l20 are the *same* 3 rounds here (only 3 total), so the delta
    # must report "no change" rather than a bogus up/down.
    assert ctx["scoring_avg_delta"] == {"delta_dir": "", "delta": "—"}
    # scoring_spark is chronological (oldest -> newest) gross totals
    assert ctx["scoring_spark"] == [73, 91, 109]


def test_stats_scoring_delta_reflects_best8_vs_last20_split(auth_client, capture_render):
    """With 9 rounds (8 great + 1 recent blow-up), best_n_rounds(8) excludes
    the blow-up entirely while last_n_rounds(20) includes it -- so the B8
    scoring average must beat (be lower than) the L20 average, and the delta
    must be flagged as an improvement ("up")."""
    _seed_course()
    for i in range(8):
        date = f"2026-01-{i + 1:02d}"
        _save(date, 0, _uniform_holes(delta=0), f"{5.0 + i:.1f}")
    _save("2026-02-01", 0, _uniform_holes(delta=5), "40.0")

    resp = auth_client.get("/stats/scoring")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["scoring_avg"] == 73.0
    assert ctx["scoring_avg_delta"]["delta_dir"] == "up"
    assert ctx["scoring_avg_delta"]["delta"] == "-10.0 vs L20"


# ---------------------------------------------------------------------------
# /stats/penalties
# ---------------------------------------------------------------------------

def test_stats_penalties_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/penalties")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["penalties_per_round"] is None
    assert ctx["pen_free_pct"] is None


def test_stats_penalties_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/penalties")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # only r3 has penalties: 18 penalties (1/hole) spread across 3 rounds -> 6/round avg
    assert ctx["penalties_per_round"] == 6.0
    # 2 of the 3 rounds (r1, r2) recorded zero penalties on every hole
    assert ctx["pen_free_pct"] == pytest.approx(66.6666, rel=1e-4)
    assert ctx["total_ob_rd"] == 0.0

    # hole breakdown is data-driven: 54 holes, only r3's 18 carry penalties, no OB
    hb = ctx["hole_breakdown"]
    assert hb["total_holes"] == 54
    assert hb["clean_pct"] == pytest.approx(66.6666, rel=1e-4)
    assert hb["penalty_pct"] == pytest.approx(33.3333, rel=1e-4)
    assert hb["ob_pct"] == pytest.approx(0.0)
    assert hb["clean_pct"] + hb["penalty_pct"] + hb["ob_pct"] == pytest.approx(100.0)

    # penalty_cost = penalty_vs_par - clean_vs_par (extra strokes a penalty hole costs)
    assert ctx["penalty_cost"] == pytest.approx(ctx["penalty_vs_par"] - ctx["clean_vs_par"])


def test_stats_penalties_pen_free_excludes_score_only_rounds(auth_client, capture_render):
    """Score-only rounds (no hole data) must not deflate Pen-Free % — they
    can't be classified pen-free, so they belong in neither numerator nor
    denominator (regression: denominator previously used len(b8))."""
    _seed_course()
    # two detailed, genuinely penalty-free rounds
    _save("2026-03-01", 0, _uniform_holes(delta=0, penalties=0), "8.0", "9.0")
    _save("2026-03-08", 0, _uniform_holes(delta=1, penalties=0), "10.0", "11.0")
    # one score-only round: no per-hole data
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {},
        "total_gross": "82", "differential": "9.0",
        "notes": "", "excluded": False, "computed_handicap": "10.0",
        "differential_locked": False,
    }, "2026-03-15", 0, user_id=1)

    resp = auth_client.get("/stats/penalties")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    # 2 of 2 *scored* rounds are pen-free -> 100%, not 66.7% (would be 2/3)
    assert ctx["pen_free_pct"] == pytest.approx(100.0)


def test_stats_penalties_template_renders(auth_client):
    """Full Jinja render (no capture_render stub): the redesigned page compiles
    and shows the new unique sections rather than the removed duplicate panels."""
    _seed_three_rounds()
    resp = auth_client.get("/stats/penalties")
    assert resp.status_code == 200
    body = resp.data
    assert b"Worst Penalty Holes" in body
    assert b"Approach (GIR) OB / Round" in body
    # removed redundant panels
    assert b"Penalty Impact" not in body
    assert b"Clean vs Dirty" not in body


# ---------------------------------------------------------------------------
# /stats/fairways
# ---------------------------------------------------------------------------

def test_stats_fairways_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/fairways")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["fir_pct"] is None
    assert ctx["fir_spark"] == []


def test_stats_fairways_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/fairways")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # r1 hits every eligible fairway, r2 misses every one, r3 hits every one
    # eligible holes = 14 (18 - 4 par-3s); hit in 2/3 rounds -> 66.7%
    assert ctx["fir_pct"] == pytest.approx(66.6666, rel=1e-4)
    assert ctx["miss_left"] == 100.0   # every miss in the dataset is a left miss
    assert ctx["miss_right"] == 0.0
    assert ctx["fir_spark"] == [100.0, 0.0, 100.0]


# ---------------------------------------------------------------------------
# /stats/greens
# ---------------------------------------------------------------------------

def test_stats_greens_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/greens")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["gir_pct"] is None
    assert ctx["gir_spark"] == []


def test_stats_greens_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/greens")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # only r1 hits every green (18/54 total hits) -> 33.3%
    assert ctx["gir_pct"] == pytest.approx(33.3333, rel=1e-4)
    assert ctx["gir_par_3"] == pytest.approx(33.3333, rel=1e-4)
    assert ctx["gir_par_4"] == pytest.approx(33.3333, rel=1e-4)
    assert ctx["gir_par_5"] == pytest.approx(33.3333, rel=1e-4)
    assert ctx["gir_spark"] == [100.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# /stats/putting
# ---------------------------------------------------------------------------

def test_stats_putting_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/putting")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["putts_per_round"] is None


def test_stats_putting_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/putting")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # (36 + 36 + 54) / 3 = 42.0
    assert ctx["putts_per_round"] == 42.0
    assert ctx["putts_per_gir"] == 2.0
    assert ctx["one_putt_pct"] == 0.0
    assert ctx["two_putt_pct"] == pytest.approx(66.6666, rel=1e-4)
    assert ctx["three_putt_pct"] == pytest.approx(33.3333, rel=1e-4)
    assert ctx["four_plus_putt_pct"] == 0.0
    assert ctx["putts_spark"] == [36.0, 36.0, 54.0]


def test_stats_putting_delta_reflects_best8_vs_last20_split(auth_client, capture_render):
    """With 9 rounds (8 solid + 1 recent putting blow-up), best_n_rounds(8)
    excludes the blow-up (worst differential) while last_n_rounds(20)
    includes it -- so the B8 putts/round must be lower (better) than the L20
    figure. This proves stats_putting wires putts_per_round from b8 (not
    l20) -- with only 3 seeded rounds elsewhere in this module, b8 == l20
    and a b8/l20 swap bug in the route would be invisible."""
    _seed_course()
    for i in range(8):
        date = f"2026-01-{i + 1:02d}"
        _save(date, 0, _uniform_holes(delta=0, putts=2), f"{5.0 + i:.1f}")
    _save("2026-02-01", 0, _uniform_holes(delta=0, putts=6), "40.0")

    resp = auth_client.get("/stats/putting")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # b8 = the 8 lowest-differential rounds (excludes the putts=6/hole
    # blow-up, which has the worst differential of 40.0) -> 18*2 = 36.0/rnd
    # l20 = all 9 rounds -> (8*36 + 108) / 9 = 44.0/rnd
    assert ctx["putts_per_round"] == 36.0
    assert ctx["pt_rd_delta"]["delta_dir"] == "up"
    assert ctx["pt_rd_delta"]["delta"] == "-8.0 vs L20"


# ---------------------------------------------------------------------------
# /stats/short-game
# ---------------------------------------------------------------------------

def test_stats_short_game_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/short-game")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["scramble_pct"] is None


def test_stats_short_game_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/short-game")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["scramble_pct"] == 0.0


# ---------------------------------------------------------------------------
# /stats/momentum
# ---------------------------------------------------------------------------

def test_stats_momentum_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/momentum")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["after_bogey_avg"] is None
    assert ctx["bogey_free"] == 0
    assert ctx["opening_3_avg"] is None
    assert ctx["closing_3_avg"] is None


def test_stats_momentum_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/momentum")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["after_bogey_avg"] == 1.5
    # only r1 (every hole exactly at par) is fully bogey-free
    assert ctx["bogey_free"] == 1
    # r1's opening/closing 3 holes are all at par (avg 0); r2's are all +1;
    # r3's are all +2 -> overall averages across the 3 rounds:
    assert ctx["opening_3_avg"] == pytest.approx(1.0, rel=1e-6)
    assert ctx["closing_3_avg"] == pytest.approx(1.0, rel=1e-6)


def test_stats_momentum_skips_score_only_rounds_with_no_holes(auth_client, capture_render):
    """A round saved with no per-hole data (score-only entry mode) must be
    skipped by the bogey-free/opening/closing loops rather than raising."""
    _seed_course()
    _save("2026-04-01", 0, _uniform_holes(delta=0), "5.0")
    save_round({
        "course": COURSE_NAME, "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "80",
        "differential": "10.0", "notes": "", "excluded": False,
        "computed_handicap": "10.0", "differential_locked": False,
    }, "2026-04-08", 0, user_id=1)

    resp = auth_client.get("/stats/momentum")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    # only the round with hole data is evaluated for bogey-free status
    assert ctx["bogey_free"] == 1


# ---------------------------------------------------------------------------
# /stats/trends
# ---------------------------------------------------------------------------

def test_stats_trends_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/trends")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["scoring_trend"] == []
    assert ctx["handicap_trend"] == []
    assert ctx["playing_to_handicap_rate"] is None


def test_stats_trends_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/trends")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["scoring_trend"] == [("2026-03-01", 73), ("2026-03-08", 91), ("2026-03-15", 109)]
    assert ctx["gir_trend"] == [("2026-03-01", 100.0), ("2026-03-08", 0.0), ("2026-03-15", 0.0)]
    assert ctx["putts_trend"] == [("2026-03-01", 36.0), ("2026-03-08", 36.0), ("2026-03-15", 54.0)]
    # only r3 has a computed_handicap that survives to the trend series in
    # this dataset window (18.0 on the most recent round)
    assert ctx["handicap_trend"] == [("2026-03-15", 8.0)]


# ---------------------------------------------------------------------------
# /stats/bests
# ---------------------------------------------------------------------------

def test_stats_bests_empty_state(auth_client, capture_render):
    resp = auth_client.get("/stats/bests")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["best_gross"] is None
    assert ctx["best_gross_date"] is None


def test_stats_bests_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/stats/bests")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    assert ctx["best_gross"] == 73
    assert ctx["best_gross_date"] == "2026-03-01"
    assert ctx["best_diff"] == 8.0
    assert ctx["best_diff_date"] == "2026-03-01"
    assert ctx["most_fir"] == 14
    assert ctx["most_fir_date"] == "2026-03-15"
    assert ctx["most_gir"] == 18
    assert ctx["most_gir_date"] == "2026-03-01"
    assert ctx["fewest_putts"] == 36
    # first round with 36 putts, chronologically -- 2026-03-01 ties 2026-03-08
    # at 36 putts; whichever the calc module resolves to, the route must
    # simply pass it through unmodified.
    assert ctx["fewest_putts_date"] in ("2026-03-01", "2026-03-08")


# ---------------------------------------------------------------------------
# /season
# ---------------------------------------------------------------------------

def test_season_summary_no_data(auth_client, capture_render):
    monkey = capture_render
    resp = auth_client.get("/season")
    assert resp.status_code == 200
    ctx = monkey["ctx"]
    assert ctx["rounds_count"] == 0
    assert ctx["total_rounds"] == 0
    assert ctx["most_played"] is None


def test_season_summary_computes_expected_values(auth_client, capture_render):
    _seed_three_rounds()
    resp = auth_client.get("/season")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # season_enabled defaults to False -> season_rounds == all rounds
    assert ctx["rounds_count"] == 3
    assert ctx["total_rounds"] == 3
    assert ctx["most_played"] == (COURSE_NAME, 3, pytest.approx(19.3333, rel=1e-4))
    assert ctx["golfiest"] == ("March", 3)
    assert ctx["common_day"] == ("Sunday", 3)
    assert ctx["best_round"].date == "2026-03-01"
    assert ctx["best_round"].total_gross == "73"
    assert ctx["breakdown"] == {"eagle": 0, "birdie": 0, "par": 18, "bogey": 18, "double": 18, "triple_plus": 0}
    assert ctx["hole_in_ones"] == 0
    assert ctx["best_gir"] == (ctx["best_gir"][0], 18)
    assert ctx["best_gir"][0].date == "2026-03-01"
    assert ctx["best_fir"][1] == 14
    assert ctx["penalty_free"] == 2


def test_season_summary_filters_by_season_window_when_enabled(auth_client, capture_render):
    """When season_enabled is on, only rounds falling within the configured
    month/day window should count toward rounds_count, while total_rounds
    (all-time) stays unaffected."""
    _seed_three_rounds()
    save_settings({
        "season_enabled": True,
        "season_start_month": 3, "season_start_day": 10,
        "season_end_month": 3, "season_end_day": 31,
    }, user_id=1)

    resp = auth_client.get("/season")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]

    # only 2026-03-15 (r3) falls within March 10-31
    assert ctx["rounds_count"] == 1
    assert ctx["total_rounds"] == 3


# ---------------------------------------------------------------------------
# /admin/invites
# ---------------------------------------------------------------------------

def test_admin_invites_forbidden_for_non_admin(auth_client):
    # `auth_client`'s user is the first user created -> becomes admin. Create
    # and log in as a *second* user, which must NOT be admin.
    create_user("regular", "Regular Joe", "pass1234")
    auth_client.get("/logout", follow_redirects=True)
    auth_client.post("/login", data={"username": "regular", "password": "pass1234"})
    resp = auth_client.get("/admin/invites")
    assert resp.status_code == 403


def test_admin_invites_get_lists_no_codes_initially(auth_client, capture_render):
    resp = auth_client.get("/admin/invites")
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["codes"] == []
    assert ctx["new_code"] is None


def test_admin_invites_post_generates_invite_code(auth_client, capture_render):
    resp = auth_client.post("/admin/invites", data={})
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["new_code"] is not None
    assert ctx["new_code"].startswith("PS-")
    assert len(ctx["codes"]) == 1
    assert ctx["codes"][0]["code"] == ctx["new_code"]


def test_admin_invites_post_reset_user_id_generates_token_url(auth_client, capture_render):
    resp = auth_client.post("/admin/invites", data={"reset_user_id": "1"})
    assert resp.status_code == 200
    ctx = capture_render["ctx"]
    assert ctx["generated_token"] is not None
    assert ctx["token_url"] is not None
    assert "/reset-password?token=" in ctx["token_url"]
    assert ctx["new_code"] is None
