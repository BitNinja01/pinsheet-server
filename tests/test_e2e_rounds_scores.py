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
from store import create_user, get_all_rounds, next_round_index, recompute_handicaps_for_user
from calc.handicap import WHS_MAX_HANDICAP_INDEX

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


# --------------------------------------------------------------------------
# WHS Rule 5.2 windowing — live POST /api/rounds, >20 rounds
# --------------------------------------------------------------------------

def test_more_than_20_rounds_windows_handicap_to_recent_20_live_post(client):
    """WHS Rule 5.2 windowing regression, exercised end-to-end through the
    real HTTP POST /api/rounds endpoint (not a unit-level construction).

    5 very-low-differential ("sandbagged") rounds are posted first (oldest),
    followed by 20 more rounds with a realistic differential spread. Because
    each POST computes/persists computed_handicap by delegating to
    `recompute_handicaps_for_user` (see rounds.py), the most-recent round's
    LIVE computed_handicap must reflect ONLY the most recent 20 rounds --
    proving the 5 oldest (suspiciously good) rounds don't leak into the
    live-computed index once posted-count exceeds 20.

    This fixture also happens to have >= 20 acceptable scores AND a large
    enough HI increase to trigger WHS Rule 5.7 (Low Handicap Index) + Rule
    5.8 (soft/hard cap): the 5 sandbagged rounds anchor a very low LHI while
    they're still inside the Rule 5.2 window, and once later (much higher)
    rounds are calculated against that LHI, Rule 5.8 caps the rise. So the
    live-persisted value is the WINDOWED *and* CAPPED HI, not the raw
    windowed HI -- both effects are asserted separately below.
    """
    # 5 oldest, very good ("sandbagged") rounds -- must fall OUTSIDE the
    # most-recent-20 window once 20 more rounds are posted after them.
    for i in range(5):
        client.post("/api/rounds", json={
            "date": f"2026-08-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "72", "holes": {}})

    # 20 more recent rounds with a realistic differential spread.
    for i in range(20):
        client.post("/api/rounds", json={
            "date": f"2026-08-{6 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": str(80 + i), "holes": {}})

    all_rounds = get_all_rounds(1)  # most-recent-first
    assert len(all_rounds) == 25
    latest = all_rounds[0]
    assert latest.date == "2026-08-25"
    assert latest.computed_handicap not in (None, "", "0")

    from calc.handicap import calc_handicap_index

    live_hi = float(latest.computed_handicap)

    # Rule 5.2 windowing check (raw, uncapped): the recent-20-only window
    # excludes the 5 sandbagged rounds.
    raw_windowed_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert raw_windowed_hi is not None

    # Sanity: prove the fixture actually exercises windowing -- an
    # unwindowed best-8-of-all-25 calc must give a DIFFERENT, LOWER value,
    # since it wrongly pulls in the 5 sandbagged ~0.4 differentials that the
    # correctly-windowed recent-20 excludes.
    naive_all_25_diffs = sorted(
        float(r.differential) for r in all_rounds
        if r.differential not in ("0", "", None)
    )
    assert len(naive_all_25_diffs) == 25
    naive_best8_of_all = round(sum(naive_all_25_diffs[:8]) / 8, 1)
    assert naive_best8_of_all != raw_windowed_hi
    assert naive_best8_of_all < raw_windowed_hi

    # WHS Rule 5.7/5.8: by the time the 25th round is processed, the player
    # has long since accumulated >= 20 acceptable scores, so an LHI is
    # established (anchored low by the sandbagged rounds while they were
    # still inside the window) and the live-persisted HI is capped well
    # below the raw windowed HI.
    assert live_hi < raw_windowed_hi

    # Consistency: the live-POST-persisted (capped) value must equal what an
    # independent, explicit recompute pass produces for the same data --
    # live-save and recompute must never disagree on the capped value.
    recompute_handicaps_for_user(1)
    recomputed = get_all_rounds(1)
    assert float(recomputed[0].computed_handicap) == live_hi


# --------------------------------------------------------------------------
# WHS Rule 5.7 (Low Handicap Index) + Rule 5.8 (soft/hard cap)
# --------------------------------------------------------------------------

def test_no_cap_before_lhi_established(client):
    """WHS Rule 5.7: an LHI is only established once the player has >= 20
    acceptable scores. Before that, even a large rise in the raw Handicap
    Index must NOT be capped -- there's nothing to cap it against yet."""
    # 3 very-low-differential rounds, then 16 much-worse rounds -- 19 total,
    # one short of the Rule 5.7 threshold. The raw HI genuinely climbs a
    # long way above the low baseline (a rise that -- were an LHI already
    # active -- would clearly trigger Rule 5.8's soft/hard cap).
    for i in range(3):
        client.post("/api/rounds", json={
            "date": f"2026-10-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "60", "holes": {}})
    for i in range(16):
        client.post("/api/rounds", json={
            "date": f"2026-10-{4 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "100", "holes": {}})

    all_rounds = get_all_rounds(1)
    assert len(all_rounds) == 19

    from calc.handicap import calc_handicap_index
    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    stored_hi = float(all_rounds[0].computed_handicap)
    assert raw_hi is not None
    # No LHI yet (only 19 < 20 acceptable scores) -- raw passes through.
    assert stored_hi == raw_hi


def test_lhi_established_then_bad_run_gets_capped(client):
    """WHS Rule 5.7/5.8: once an LHI is established from 20 stable rounds,
    a subsequent run of much-worse rounds must have its Handicap Index
    increase soft/hard-capped relative to that LHI."""
    for i in range(20):
        client.post("/api/rounds", json={
            "date": f"2026-09-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "85", "holes": {}})

    established = get_all_rounds(1)  # most-recent-first, 20 rounds
    assert len(established) == 20
    # WHS Rule 5.7: LHI = lowest Handicap Index the player has HELD (i.e.
    # displayed) -- reconstruct that from the 20 established rounds.
    prior_candidates = [
        float(r.computed_handicap) for r in established
        if r.computed_handicap not in ("", None)
    ]
    expected_lhi = min(prior_candidates)

    # A run of much-worse rounds, long enough (> 20 - 8 = 12) to force the
    # Rule 5.2 best-8 window to actually include some of the bad
    # differentials -- otherwise the good rounds still already in the
    # 20-round window would dominate best-8 and mask any rise at all.
    bad_dates = [f"2026-09-{21 + i:02d}" for i in range(9)] + [f"2026-10-{1 + i:02d}" for i in range(6)]
    for d in bad_dates:
        client.post("/api/rounds", json={
            "date": d, "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "150", "holes": {}})

    all_rounds = get_all_rounds(1)
    stored_hi = float(all_rounds[0].computed_handicap)

    from calc.handicap import calc_handicap_index, apply_handicap_cap
    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert raw_hi - expected_lhi > 3.0  # confirm the cap is actually triggered
    expected_capped = apply_handicap_cap(raw_hi, expected_lhi)

    assert stored_hi == expected_capped
    assert stored_hi < raw_hi
    assert stored_hi <= expected_lhi + 5.0  # Rule 5.8 hard cap


def test_lhi_ignores_prior_hi_older_than_365_days(client):
    """WHS Rule 5.7: LHI = the lowest Handicap Index held over the 365 days
    PRECEDING the round being processed. An old, very-low displayed HI that
    falls outside that 365-day window must NOT anchor the LHI -- it must
    "age out" once enough time has passed."""
    # Old cluster: 3 very-low-differential rounds far in the past --
    # establishes a very low displayed HI that will later age out.
    for i in range(3):
        client.post("/api/rounds", json={
            "date": f"2024-01-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "50", "holes": {}})
    # New cluster: 17 more moderate rounds (3 + 17 = 20 -> LHI established),
    # clustered together in mid-2025.
    for i in range(17):
        client.post("/api/rounds", json={
            "date": f"2025-06-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "85", "holes": {}})

    established = get_all_rounds(1)
    assert len(established) == 20

    # A round more than 365 days after the old (2024) cluster, but well
    # within 365 days of the new (2025) cluster.
    client.post("/api/rounds", json={
        "date": "2026-05-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "150", "holes": {}})

    all_rounds = get_all_rounds(1)
    latest = all_rounds[0]
    assert latest.date == "2026-05-01"
    stored_hi = float(latest.computed_handicap)

    from datetime import date as _date, timedelta as _timedelta
    from calc.handicap import calc_handicap_index, apply_handicap_cap

    cutoff = _date(2026, 5, 1) - _timedelta(days=365)
    old_cluster_hi = [
        float(r.computed_handicap) for r in established
        if r.computed_handicap not in ("", None) and r.date.startswith("2024")
    ]
    assert old_cluster_hi  # sanity: the old cluster does get a displayed HI
    # The old (2024) cluster is well before the cutoff -- not merely at the
    # boundary -- so it ages out regardless of the closed/open-interval
    # boundary semantics (see test_lhi_365_day_boundary_is_inclusive in
    # test_handicap.py for the exact boundary-day case).
    assert all(_date.fromisoformat(r.date) < cutoff for r in established if r.date.startswith("2024"))

    # WHS Rule 5.7: the 365-day period preceding is a CLOSED interval -- a
    # prior HI dated exactly on the cutoff day is still IN the window (>=,
    # not >).
    candidates = [
        float(r.computed_handicap) for r in established
        if r.computed_handicap not in ("", None) and _date.fromisoformat(r.date) >= cutoff
    ]
    expected_lhi = min(candidates)
    # The old cluster's HI is far lower than anything in the 365-day window
    # -- if it wrongly leaked in, it would materially change the result.
    assert min(old_cluster_hi) < expected_lhi

    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    expected_capped = apply_handicap_cap(raw_hi, expected_lhi)
    assert stored_hi == expected_capped

    wrong_capped_with_old_lhi = apply_handicap_cap(raw_hi, min(old_cluster_hi))
    assert wrong_capped_with_old_lhi != stored_hi


def test_decrease_never_capped_once_lhi_established(client):
    """WHS Rule 5.8: there is no limit on a DECREASE -- the soft/hard cap
    only ever limits INCREASES above the Low Handicap Index. Once an LHI is
    established, a new Handicap Index that is at or below LHI + 3.0
    (including a large decrease) must pass through Rule 5.8's cap
    unchanged.

    NOTE (WHS Rule 5.9): the much-better round below is ALSO an exceptional
    score in its own right (its differential is markedly lower than the HI
    in effect when it was played), so Rule 5.9's Exceptional Score
    Reduction independently fires and further lowers the stored value below
    the raw (uncapped, un-reduced) `calc_handicap_index` figure. That
    reduction is expected and is asserted for explicitly below; the point
    of this test -- that Rule 5.8's cap does not clip a decrease -- still
    holds and is verified by confirming the ESR-adjusted value passes
    through unchanged (i.e. equals `raw_hi + reduction`, not something
    further limited by the cap)."""
    for i in range(20):
        client.post("/api/rounds", json={
            "date": f"2026-09-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "85", "holes": {}})

    # A much-better round after the LHI is established.
    client.post("/api/rounds", json={
        "date": "2026-09-21", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "60", "holes": {}})

    all_rounds = get_all_rounds(1)
    stored_hi = float(all_rounds[0].computed_handicap)
    hi_prev = float(all_rounds[1].computed_handicap)  # HI in effect when the round was played

    from calc.handicap import calc_handicap_index, exceptional_reduction
    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)

    # WHS Rule 5.9: this round's own differential is markedly lower than
    # `hi_prev`, so it is itself an exceptional score and its reduction
    # stacks on top of `raw_hi`.
    reduction = exceptional_reduction(hi_prev, float(all_rounds[0].differential))
    assert reduction < 0, (
        "fixture did not trigger Rule 5.9 -- this regression would pass "
        "vacuously without exercising the ESR/cap interaction it's meant "
        "to cover."
    )

    expected = round(raw_hi + reduction, 1)
    assert stored_hi == expected  # decrease -- Rule 5.8 cap inactive; only Rule 5.9 ESR applies


# --------------------------------------------------------------------------
# WHS Rule 5.3 — maximum issuable Handicap Index (54.0)
# --------------------------------------------------------------------------

def test_beginner_run_of_very_high_scores_clamps_to_max_54(client):
    """WHS Rule 5.3: 'The maximum Handicap Index that can be issued to a
    player is 54.0.' A beginner's first 3 rounds are so high that the raw
    Rule 5.2/5.2a calculation (best-1 average minus the 3-diff -2.0
    adjustment) lands at 67.3 -- `calc_handicap_index` itself deliberately
    returns that RAW, unclamped value (see its docstring: the 54.0 max is
    applied downstream, AFTER any Rule 5.8 cap, to preserve the cap's true
    `increase = raw - low_hi` computation). The DISPLAYED/STORED value must
    still be clamped down to 54.0, both in `computed_handicap` (live-save +
    recompute) and on the rendered round-detail page ("HI After")."""
    for i in range(3):
        resp = client.post("/api/rounds", json={
            "date": f"2026-11-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "150", "holes": {}})
        assert resp.status_code == 200

    all_rounds = get_all_rounds(1)  # most-recent-first
    assert len(all_rounds) == 3
    latest = all_rounds[0]

    from calc.handicap import calc_handicap_index
    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert raw_hi == 67.3  # calc_handicap_index returns the RAW, unclamped value

    # Live-save (POST) persisted the clamped (54.0), not raw (67.3), value.
    assert latest.computed_handicap == "54.0"

    # Explicit recompute pass agrees with the live-save value.
    recompute_handicaps_for_user(1)
    recomputed = get_all_rounds(1)
    assert recomputed[0].computed_handicap == "54.0"

    # The value is reflected on the rendered round-detail page.
    page = client.get(f"/rounds/{latest.date}/{latest.index}")
    assert page.status_code == 200
    assert b"54.0" in page.data
    assert b"67.3" not in page.data


def test_narrow_low_hi_band_clamp_applied_after_cap_not_before(client):
    """WHS Rule 5.3/5.8 ordering regression, exercised through the real
    recompute pipeline (`store.recompute_handicaps_for_user`, the same code
    the live POST path runs): 20 stable rounds (differential 50.8 each)
    establish an LHI in the ~49 band (the LHI dips slightly below 50.8
    because the WHS Rule 5.2a count-table adjustment applies while the
    record is still small -- e.g. the 3rd round's best-1-of-3 average gets
    a -2.0 adjustment -- which is itself correct WHS behavior; the exact
    LHI is read back from the data rather than hardcoded). A run of 15
    much-worse rounds (differential 69.3 each) then pushes the raw Rule 5.2
    Handicap Index to 57.7 -- ABOVE 54.0 -- so the Rule 5.8 cap's
    `increase = raw - low_hi` genuinely differs depending on whether it is
    computed against the TRUE raw value (correct WHS order: 5.2/5.2a -> 5.9
    -> 5.8 -> 5.3) or a pre-clamped-to-54.0 raw value (wrong order). This
    test proves the real pipeline matches the CORRECT (cap-then-clamp)
    order, not the wrong (clamp-then-cap) one, for this fixture."""
    for i in range(20):
        client.post("/api/rounds", json={
            "date": f"2027-01-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "129", "holes": {}})  # differential 50.8 each

    established = get_all_rounds(1)
    assert len(established) == 20
    lhi_candidates = [float(r.computed_handicap) for r in established
                       if r.computed_handicap not in ("", None)]
    expected_low_hi = min(lhi_candidates)
    # Sanity: the LHI band this test targets ("narrow low_hi ~49") -- close
    # to, but distinctly below, the 54.0 maximum.
    assert 47.0 <= expected_low_hi <= 51.0

    bad_dates = [f"2027-01-{21 + i:02d}" for i in range(10)] + [f"2027-02-{1 + i:02d}" for i in range(5)]
    assert len(bad_dates) == 15
    for d in bad_dates:
        client.post("/api/rounds", json={
            "date": d, "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "150", "holes": {}})  # differential 69.3 each

    all_rounds = get_all_rounds(1)
    stored_hi = float(all_rounds[0].computed_handicap)

    from calc.handicap import calc_handicap_index, apply_handicap_cap
    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert raw_hi == 57.7  # confirm the fixture lands in the target raw range
    assert raw_hi > WHS_MAX_HANDICAP_INDEX  # confirms this exercises the >54 boundary

    correct_order = min(apply_handicap_cap(raw_hi, expected_low_hi), WHS_MAX_HANDICAP_INDEX)
    wrong_order = apply_handicap_cap(min(raw_hi, WHS_MAX_HANDICAP_INDEX), expected_low_hi)
    assert correct_order != wrong_order  # fixture genuinely exercises the ordering difference

    assert stored_hi == correct_order  # the real pipeline matches cap-then-clamp
    assert stored_hi != wrong_order    # ... and NOT clamp-then-cap


def test_live_save_consistent_with_recompute_after_cap(client):
    """Consistency: the capped `computed_handicap` written by the live
    POST /api/rounds path must always equal what an independent, explicit
    `recompute_handicaps_for_user` pass produces for the same data -- the
    two code paths must never disagree once Rule 5.7/5.8 caps are active."""
    for i in range(20):
        client.post("/api/rounds", json={
            "date": f"2026-12-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "85", "holes": {}})
    client.post("/api/rounds", json={
        "date": "2026-12-21", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only",
        "gross_total": "160", "holes": {}})

    live_stored = float(get_all_rounds(1)[0].computed_handicap)

    recompute_handicaps_for_user(1)
    recomputed = float(get_all_rounds(1)[0].computed_handicap)

    assert live_stored == recomputed
