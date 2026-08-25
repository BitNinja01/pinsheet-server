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


# --------------------------------------------------------------------------
# WHS Rule 12 / Rule 3 (Net Double Bogey): live-save vs recompute must agree
# on the ESC-adjusted Score Differential for a detailed round with a
# blow-up hole (source/store.py recompute_handicaps_for_user must not fall
# back to raw total_gross when per-hole data is available).
# --------------------------------------------------------------------------

def test_live_and_recompute_agree_on_esc_adjusted_differential_with_blowup_hole(client):
    """A detailed round with a blow-up hole (par 5, gross 10, on the
    HIGHEST-stroke-index hole -- i.e. genuinely "no stroke received" for a
    bogey-level course handicap) must produce the SAME Score Differential
    whether it is scored live (POST /api/rounds, which applies the Net
    Double Bogey/ESC cap inline via calc_adjusted_gross_score) or later
    reprocessed by recompute_handicaps_for_user (source/store.py). Before
    the R12 fix, the recompute path derived the differential from raw
    total_gross and diverged from the live-saved value for any round with a
    hole over Net Double Bogey.

    A real (non-zero, non-fallback) prior Handicap Index is established
    first from 3 warm-up rounds, so the blow-up round's course_handicap --
    and therefore its ESC cap -- comes from an ACTUAL prior HI, exercising
    the same code path live-entry and recompute both take once a player has
    playing history (not just the course_handicap==0/no-prior-HI edge
    case)."""
    from calc.handicap import calc_handicap_index, calc_course_handicap, calc_adjusted_gross_score, calc_round_dif

    # 3 warm-up score-only rounds (bogey-level golfer, ~90 raw gross on this
    # par-73 course) establish a real prior Handicap Index.
    for i in range(3):
        client.post("/api/rounds", json={
            "date": f"2026-04-{1 + i:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only",
            "gross_total": "90", "holes": {}})

    prior_rounds = get_all_rounds(1)  # most-recent-first, the 3 warm-up rounds
    assert len(prior_rounds) == 3

    # Blow-up hole: gross 10 on hole 18 (par 5, hole_index 18 -- the HIGHEST
    # stroke index on this course, so the last hole to receive a stroke).
    gross_map = {n: PARS[n] + 1 for n in PARS}
    gross_map[18] = 10

    resp = client.post("/api/rounds", json={
        "date": "2026-04-04", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes(gross_map)})
    assert resp.status_code == 200
    live_differential = resp.get_json()["differential"]

    # Independently derive the expected course handicap / ESC-adjusted
    # differential from the SAME prior record, using the production
    # functions directly (not by re-reading the app's own output) -- this is
    # the real-data cross-check, not a tautology.
    current_hi = calc_handicap_index(prior_rounds, include_9hole=True)
    assert current_hi is not None
    course_handicap = calc_course_handicap(current_hi, TOTAL_PAR, 128, 71.5)
    assert course_handicap < 18, "fixture must NOT award hole 18 a stroke (genuine no-stroke blow-up)"

    raw_total = sum(gross_map[n] for n in PARS)
    hole_gross = {str(n): {"gross": str(gross_map[n])} for n in PARS}
    esc_total = calc_adjusted_gross_score(hole_gross, COURSE["holes"], course_handicap)
    assert esc_total < raw_total, "fixture must actually trigger the Net Double Bogey cap"

    esc_differential = calc_round_dif(128, esc_total, 71.5)
    raw_differential = calc_round_dif(128, raw_total, 71.5)
    assert esc_differential != raw_differential

    assert live_differential == esc_differential, (
        "live path (rounds.py) must apply the Net Double Bogey/ESC cap, not raw total_gross"
    )

    recompute_handicaps_for_user(1)
    recomputed = get_all_rounds(1)[0]
    assert float(recomputed.differential) == live_differential, (
        f"recompute produced {recomputed.differential!r} but live-save "
        f"produced {live_differential!r} for the SAME round -- WHS Rule 3 "
        f"(Net Double Bogey) / Rule 12 violation. (raw-total_gross formula "
        f"would have given {raw_differential!r})"
    )
    assert float(recomputed.differential) != raw_differential


# --------------------------------------------------------------------------
# WHS Rule 12 path-agreement — live-save == recompute regardless of the
# player's HI state (regression guards for the two divergences the C4
# adversary gate surfaced: new-player pre-establishment, and cap/ESR active).
# --------------------------------------------------------------------------

def test_esc_live_equals_recompute_new_player_first_detailed_round(client):
    """A brand-new player's very first detailed round (no HI established yet)
    must get the same ESC-adjusted differential from live-save as from a
    recompute pass. Pre-fix, live skipped ESC (raw gross) while recompute
    applied it with course_handicap=0 -> divergence."""
    blow = {18: 10}  # par-5 hole 18, big blow-up -> Net Double Bogey caps it
    resp = client.post("/api/rounds", json={
        "date": "2026-08-01", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes(blow)})
    live = resp.get_json()["differential"]
    recompute_handicaps_for_user(1)
    stored = _rounds_on("2026-08-01")[0].differential
    assert str(live) == str(stored)
    # non-vacuous: the blow-up hole was actually capped (ESC < raw)
    raw_total = sum(int(h["gross"]) for h in _holes(blow).values())
    assert float(live) < round((113 / 128) * (raw_total - 71.5), 1)


def test_esc_live_equals_recompute_when_cap_active(client):
    """With a Rule 5.8 cap active, the ESC course handicap must come from the
    displayed (capped) HI on both paths. Pre-fix, live used a fresh raw
    calc_handicap_index (uncapped) -> divergence once the cap bit."""
    for i in range(20):
        client.post("/api/rounds", json={
            "date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "course": "Test GC", "tees": "White", "holes_played": "18",
            "entry_mode": "score_only", "gross_total": "79", "holes": {}})
    client.post("/api/rounds", json={  # spike to trigger the cap
        "date": "2025-12-15", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "115", "holes": {}})
    resp = client.post("/api/rounds", json={
        "date": "2026-08-02", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes({18: 10})})
    live = resp.get_json()["differential"]
    recompute_handicaps_for_user(1)
    stored = _rounds_on("2026-08-02")[0].differential
    assert str(live) == str(stored)


def test_esc_live_equals_recompute_backdated_round(client):
    """A backdated detailed round (dated BEFORE existing rounds) must use the
    HI in effect at ITS date, not a later round's HI. Regression for the
    date-ordering bug: _prior_displayed_hi must filter to strictly-prior rounds."""
    for i in range(5):  # establish some 2026-03 history
        client.post("/api/rounds", json={
            "date": f"2026-03-{i + 1:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only", "gross_total": "80", "holes": {}})
    resp = client.post("/api/rounds", json={  # backdated to January
        "date": "2026-01-15", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes({18: 10})})
    live = resp.get_json()["differential"]
    recompute_handicaps_for_user(1)
    stored = _rounds_on("2026-01-15")[0].differential
    assert str(live) == str(stored)


def test_esc_live_equals_recompute_on_edit_put(client):
    """Editing a detailed round (PUT) must produce the same ESC differential a
    recompute would -- PUT uses the same prior-displayed-HI basis as POST."""
    for i in range(4):
        client.post("/api/rounds", json={
            "date": f"2026-06-{i + 1:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only", "gross_total": "82", "holes": {}})
    client.post("/api/rounds", json={
        "date": "2026-06-10", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes()})
    # edit it to add a blow-up hole
    resp = client.put("/api/rounds/2026-06-10/0", json={
        "date": "2026-06-10", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes({18: 10})})
    assert resp.status_code == 200
    live = _rounds_on("2026-06-10")[0].differential
    recompute_handicaps_for_user(1)
    stored = _rounds_on("2026-06-10")[0].differential
    assert str(live) == str(stored)


def test_esc_live_equals_recompute_same_date_index_gap(client):
    """next_round_index gap-fills the lowest free slot, so a same-date round can
    reuse a freed LOWER index than an existing sibling. The ESC prior-HI basis
    must use the round's TRUE index (not a sentinel that assumes append), so
    live == recompute. Regression for the same-date index-gap divergence."""
    for i in range(4):  # establish HI
        client.post("/api/rounds", json={
            "date": f"2026-09-{i + 1:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only", "gross_total": "81", "holes": {}})
    # two rounds on the same date D: indices 0 and 1
    client.post("/api/rounds", json={"date": "2026-09-20", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "80", "holes": {}})
    client.post("/api/rounds", json={"date": "2026-09-20", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "84", "holes": {}})
    # delete index 0 -> frees the lower slot
    client.delete("/api/rounds/2026-09-20/0")
    # new detailed round on D reuses freed index 0 (lower than sibling index 1)
    resp = client.post("/api/rounds", json={"date": "2026-09-20", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes({18: 10})})
    assert resp.status_code == 200
    live = _rounds_on("2026-09-20")[0].differential if _rounds_on("2026-09-20")[0].index == 0 \
        else [r for r in _rounds_on("2026-09-20") if r.index == 0][0].differential
    recompute_handicaps_for_user(1)
    stored = [r for r in _rounds_on("2026-09-20") if r.index == 0][0].differential
    assert str(live) == str(stored)


def test_esc_live_equals_recompute_put_date_change_index_gap(client):
    """PUT that MOVES a detailed round onto a date with a freed/gapped lower
    index must use the round's real target slot for the ESC prior-HI basis, so
    live == recompute. Covers the PUT + date-change + index-gap combination."""
    for i in range(4):  # establish HI
        client.post("/api/rounds", json={
            "date": f"2026-10-{i + 1:02d}", "course": "Test GC", "tees": "White",
            "holes_played": "18", "entry_mode": "score_only", "gross_total": "83", "holes": {}})
    # target date D with two rounds (0,1), then free index 0
    client.post("/api/rounds", json={"date": "2026-10-20", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "80", "holes": {}})
    client.post("/api/rounds", json={"date": "2026-10-20", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "score_only", "gross_total": "85", "holes": {}})
    client.delete("/api/rounds/2026-10-20/0")
    # a detailed round on a DIFFERENT date, then move it onto D (lands on freed idx 0)
    client.post("/api/rounds", json={"date": "2026-10-25", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes({18: 10})})
    resp = client.put("/api/rounds/2026-10-25/0", json={
        "date": "2026-10-20", "course": "Test GC", "tees": "White",
        "holes_played": "18", "entry_mode": "detailed", "holes": _holes({18: 10})})
    assert resp.status_code == 200
    moved = [r for r in _rounds_on("2026-10-20") if r.entry_mode == "detailed"][0]
    live = moved.differential
    recompute_handicaps_for_user(1)
    stored = [r for r in _rounds_on("2026-10-20") if r.entry_mode == "detailed"][0].differential
    assert str(live) == str(stored)
