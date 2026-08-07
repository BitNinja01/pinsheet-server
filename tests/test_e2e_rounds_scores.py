"""End-to-end regression tests for the round + score entry flow.

Drives the real HTTP endpoints (course -> round -> score -> handicap) through
the Flask test client against a temp DB. Locks in the fixes for four edge-case
bugs found by the e2e driver in .context/e2e_flow.py:

  1. same-date rounds must not overwrite each other (round_index auto-increment)
  2. blank gross must not 500
  3. non-numeric gross (total or per-hole) must not 500
  4. incomplete / no-score rounds must not poison the handicap (differential "0")

Each test is an independent HTTP scenario so a regression fails loudly in CI.
"""
import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import create_user, get_all_rounds, next_round_index

# The Flask `app` is a shared singleton across test modules; register once.
if "rounds_list" not in app.view_functions:
    register_routes(app, limiter, csrf, User)

# 18-hole par map: par-3s at 4/8/12/16, par-5s at 2/6/10/14/18, rest par-4.
PARS = {n: (3 if n in (4, 8, 12, 16) else 5 if n in (2, 6, 10, 14, 18) else 4)
        for n in range(1, 19)}
TOTAL_PAR = sum(PARS.values())  # 73

COURSE = {
    "name": "Test GC",
    "location": {"city": "City", "state/province": "ST", "country": "X"},
    "tees": {"White": {
        "yardage": "6200", "rating": "71.5", "slope": "128",
        "front_rating": "35.7", "front_slope": "128",
        "back_rating": "35.8", "back_slope": "128",
    }},
    "holes": {str(n): {"par": str(PARS[n]), "hole_index": str(n)} for n in range(1, 19)},
    "par": TOTAL_PAR,
}


def _holes(gross_map=None, only=None, putts="2"):
    """Build a holes payload. `only` restricts to a set of hole numbers."""
    out = {}
    for hn, par in PARS.items():
        if only is not None and hn not in only:
            continue
        g = (gross_map or {}).get(hn, par + 1)
        out[str(hn)] = {"gross": str(g), "putts": putts,
                        "fairway": ("" if par == 3 else "H"), "gir": "H", "penalties": "0"}
    return out


@pytest.fixture
def client(tmp_path, monkeypatch):
    main_mod.limiter.enabled = False
    data_dir = tmp_path / "data"
    (data_dir / "drafts").mkdir(parents=True)
    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                      SECRET_KEY="test-secret-key", DB_PATH=db_path)

    create_user("player", "Player", "pass1234")
    c = app.test_client()
    c.post("/login", data={"username": "player", "password": "pass1234"})
    c.post("/api/courses", json=COURSE)
    return c


def _rounds_on(date):
    return [r for r in get_all_rounds(1) if r.date == date]


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------

def test_score_only_round_saves_and_computes_differential(client):
    resp = client.post("/api/rounds", json={
        "date": "2026-01-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "90", "holes": {},
    })
    assert resp.status_code == 200
    assert resp.get_json()["differential"] > 0
    saved = _rounds_on("2026-01-01")
    assert len(saved) == 1 and saved[0].total_gross == "90"


def test_detailed_round_full_18_computes_positive_differential(client):
    resp = client.post("/api/rounds", json={
        "date": "2026-01-05", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes(),
    })
    assert resp.status_code == 200
    saved = _rounds_on("2026-01-05")[0]
    assert float(saved.differential) > 0


def test_handicap_index_populated_after_enough_rounds(client):
    # WHS needs >= 3 rounds before a handicap index exists.
    for i in range(5):
        g = {n: PARS[n] + (1 if i % 2 else 2) for n in PARS}
        client.post("/api/rounds", json={
            "date": f"2026-01-{10+i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "detailed", "holes": _holes(g)})
    latest = _rounds_on("2026-01-14")[0]
    assert latest.computed_handicap and float(latest.computed_handicap) > 0


def test_round_detail_and_report_pages_render(client):
    client.post("/api/rounds", json={
        "date": "2026-01-05", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes(),
    })
    assert client.get("/rounds/2026-01-05/0").status_code == 200
    assert client.get("/rounds/2026-01-05/0/report").status_code == 200


# --------------------------------------------------------------------------
# Bug 1 — same-date rounds must not overwrite each other
# --------------------------------------------------------------------------

def test_two_rounds_same_date_both_persist(client):
    a = client.post("/api/rounds", json={
        "date": "2026-02-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "80", "holes": {}})
    b = client.post("/api/rounds", json={
        "date": "2026-02-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "100", "holes": {}})
    assert a.status_code == b.status_code == 200
    assert a.get_json()["index"] == 0
    assert b.get_json()["index"] == 1
    saved = _rounds_on("2026-02-01")
    assert len(saved) == 2
    assert sorted(r.total_gross for r in saved) == ["100", "80"]


def test_next_round_index_fills_lowest_free_slot(client):
    for gross in ("80", "90", "100"):
        client.post("/api/rounds", json={
            "date": "2026-02-02", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only", "gross_total": gross, "holes": {}})
    assert len(_rounds_on("2026-02-02")) == 3
    # index 3 is next free; after deleting index 1, index 1 is reused
    assert next_round_index("2026-02-02", 1) == 3
    client.delete("/api/rounds/2026-02-02/1")
    assert next_round_index("2026-02-02", 1) == 1


# --------------------------------------------------------------------------
# Bug 2 & 3 — malformed numeric input must not 500
# --------------------------------------------------------------------------

@pytest.mark.parametrize("gross_total", ["", "abc", "  ", None])
def test_bad_score_only_gross_does_not_500(client, gross_total):
    resp = client.post("/api/rounds", json={
        "date": "2026-03-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": gross_total, "holes": {}})
    assert resp.status_code == 200


def test_non_numeric_hole_gross_does_not_500_and_parses_zero(client):
    holes = _holes()
    holes["5"]["gross"] = "x"
    resp = client.post("/api/rounds", json={
        "date": "2026-03-02", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": holes})
    assert resp.status_code == 200
    # hole 5 counted as 0 -> only 17 holes scored -> incomplete -> differential "0"
    assert _rounds_on("2026-03-02")[0].differential == "0"


def test_detail_page_renders_with_bad_stored_hole(client):
    holes = _holes()
    holes["5"]["gross"] = "x"
    client.post("/api/rounds", json={
        "date": "2026-03-02", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": holes})
    # dict_to_hole runs on the DB read path too — must not raise
    assert client.get("/rounds/2026-03-02/0").status_code == 200


# --------------------------------------------------------------------------
# Bug 4 — incomplete / no-score rounds must not poison the handicap
# --------------------------------------------------------------------------

def test_incomplete_detailed_round_gets_zero_differential(client):
    resp = client.post("/api/rounds", json={
        "date": "2026-04-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed",
        "holes": _holes(only=set(range(1, 10)))})  # only 9 of 18
    assert resp.status_code == 200
    assert _rounds_on("2026-04-01")[0].differential == "0"


def test_detailed_round_with_no_holes_gets_zero_differential(client):
    resp = client.post("/api/rounds", json={
        "date": "2026-04-02", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": {}})
    assert resp.status_code == 200
    assert _rounds_on("2026-04-02")[0].differential == "0"


def test_incomplete_round_excluded_from_handicap(client):
    # Several clean 18-hole rounds establish a real, positive handicap.
    for i in range(4):
        g = {n: PARS[n] + (1 if i % 2 else 2) for n in PARS}
        client.post("/api/rounds", json={
            "date": f"2026-05-{1+i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "detailed", "holes": _holes(g)})
    hi_before = float(_rounds_on("2026-05-04")[0].computed_handicap)
    assert hi_before > 0

    # An incomplete round (9 of 18) is stored with differential "0" and must be
    # excluded — its inclusion would drag the handicap wildly negative.
    client.post("/api/rounds", json={
        "date": "2026-05-10", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed",
        "holes": _holes(only=set(range(1, 10)))})
    # A later real round triggers the recompute cascade — the incomplete round
    # must NOT be resurrected into the handicap.
    client.post("/api/rounds", json={
        "date": "2026-05-11", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes()})
    assert _rounds_on("2026-05-10")[0].differential == "0"
    hi_after = float(_rounds_on("2026-05-11")[0].computed_handicap)
    assert hi_after > 0  # not dragged negative by the incomplete round


# --------------------------------------------------------------------------
# Robustness — missing course / tees
# --------------------------------------------------------------------------

def test_round_on_nonexistent_course_does_not_500(client):
    resp = client.post("/api/rounds", json={
        "date": "2026-06-01", "course": "Ghost Course", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "85", "holes": {}})
    assert resp.status_code == 200


def test_round_with_missing_tees_does_not_500(client):
    resp = client.post("/api/rounds", json={
        "date": "2026-06-02", "course": "Test GC", "tees": "",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "85", "holes": {}})
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# Edit (PUT) path — same guards apply
# --------------------------------------------------------------------------

def test_put_bad_gross_does_not_500(client):
    client.post("/api/rounds", json={
        "date": "2026-07-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "85", "holes": {}})
    resp = client.put("/api/rounds/2026-07-01/0", json={
        "date": "2026-07-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "", "holes": {}})
    assert resp.status_code == 200


def test_put_to_incomplete_zeroes_differential(client):
    client.post("/api/rounds", json={
        "date": "2026-07-02", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes()})
    assert float(_rounds_on("2026-07-02")[0].differential) > 0
    resp = client.put("/api/rounds/2026-07-02/0", json={
        "date": "2026-07-02", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed",
        "holes": _holes(only=set(range(1, 10)))})
    assert resp.status_code == 200
    assert _rounds_on("2026-07-02")[0].differential == "0"
