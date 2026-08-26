import math
from calc.handicap import (
    calc_hole_scores,
    calc_course_handicap,
    calc_playing_handicap,
    WHS_HANDICAP_ALLOWANCES,
    calc_round_dif,
    calc_expected_9hole_dif,
    calc_9hole_dif,
    count_table_n,
    count_table_adjustment,
    calc_effective_diffs,
    get_best_n_rounds,
    calc_handicap_index,
    calc_handicap_trend,
    calc_playing_to_handicap_rate,
    calc_raw_hi,
    calc_adjusted_gross_score,
    apply_handicap_cap,
    exceptional_reduction,
    round_half_up,
    WHS_HANDICAP_WINDOW,
)
from source.models import clamp_pcc, dict_to_round, effective_pcc


# ---------------------------------------------------------------------------
# Adjusted Gross Score (WHS net double bogey) — the fix for the Cedar Irons vs
# Scarecrow ranking bug (raw gross was used instead of adjusted gross).
# ---------------------------------------------------------------------------
def test_adjusted_gross_score_caps_blowup_at_net_double_bogey():
    course_holes = {str(n): {"par": 4, "index": n} for n in range(1, 19)}
    round_holes = {str(n): {"gross": 4} for n in range(1, 19)}
    round_holes["1"]["gross"] = 10  # blow-up on the hardest hole (SI 1)

    # course handicap 0 -> net double bogey cap = par + 2 = 6 (raw sum is 78)
    assert calc_adjusted_gross_score(round_holes, course_holes, 0) == 17 * 4 + 6
    # course handicap 18 -> 1 stroke on SI 1 -> cap = par + 2 + 1 = 7
    assert calc_adjusted_gross_score(round_holes, course_holes, 18) == 17 * 4 + 7


def test_adjusted_gross_score_reads_legacy_hole_index_key():
    # Older courses store the stroke index under "hole_index", not "index".
    course_holes = {"1": {"par": 5, "hole_index": 1}}
    round_holes = {"1": {"gross": 10}}
    # course handicap 0 -> cap = 5 + 2 = 7
    assert calc_adjusted_gross_score(round_holes, course_holes, 0) == 7


def test_adjusted_gross_score_none_without_hole_data():
    course_holes = {str(n): {"par": 4, "index": n} for n in range(1, 19)}
    assert calc_adjusted_gross_score({}, course_holes, 0) is None
    assert calc_adjusted_gross_score(None, course_holes, 0) is None


def test_adjusted_gross_score_handles_blank_or_bad_par_without_crash_or_deflation():
    # Course-hole par comes from client JSON — a blank or non-numeric par must
    # neither crash nor silently cap the hole against par 0. Such holes stay
    # uncapped (raw gross); a valid par still caps.
    course_holes = {
        "1": {"par": "", "index": 1},     # blank -> uncapped
        "2": {"par": "N/A", "index": 2},  # non-numeric -> uncapped (no crash)
        "3": {"par": 4, "index": 3},      # valid -> cap at par + 2 = 6
    }
    round_holes = {"1": {"gross": 9}, "2": {"gross": 8}, "3": {"gross": 10}}
    assert calc_adjusted_gross_score(round_holes, course_holes, 0) == 9 + 8 + 6


def test_calc_hole_scores_allocates_third_stroke_tier():
    # WHS gives a 3rd stroke on the hardest holes once course handicap >= SI+36.
    _, net, esc = calc_hole_scores(1, 37, 4, 15)  # SI 1, CH 37
    assert esc == 4 + 2 + 3  # net double bogey cap includes 3 strokes
    assert net == 15 - 3


def test_adjusted_gross_lowers_differential_versus_raw():
    # Reproduces the Cedar Irons case: a 10 on a par 5 inflates the raw
    # differential; capping to net double bogey lowers it.
    course_holes = {"1": {"par": 5, "index": 1}}
    round_holes = {"1": {"gross": 10}}
    ags = calc_adjusted_gross_score(round_holes, course_holes, 0)  # -> 7
    raw_diff = calc_round_dif(121, 10, 68.5)
    ags_diff = calc_round_dif(121, ags, 68.5)
    assert ags_diff < raw_diff


def test_count_table_n_all_boundaries():
    assert count_table_n(0) == 0
    assert count_table_n(2) == 0
    assert count_table_n(3) == 1
    assert count_table_n(5) == 1
    assert count_table_n(6) == 2
    assert count_table_n(8) == 2
    assert count_table_n(9) == 3
    assert count_table_n(11) == 3
    assert count_table_n(12) == 4
    assert count_table_n(14) == 4
    assert count_table_n(15) == 5
    assert count_table_n(16) == 5
    assert count_table_n(17) == 6
    assert count_table_n(18) == 6
    assert count_table_n(19) == 7
    assert count_table_n(20) == 8
    assert count_table_n(100) == 8


def test_count_table_adjustment_all_cases():
    """WHS Rule 5.2a: adjustment keyed on the number of differentials in the
    record. 3 -> -2.0, 4 -> -1.0, 6 -> -1.0, all other counts -> 0.0."""
    assert count_table_adjustment(3) == -2.0
    assert count_table_adjustment(4) == -1.0
    assert count_table_adjustment(5) == 0.0
    assert count_table_adjustment(6) == -1.0
    assert count_table_adjustment(7) == 0.0
    assert count_table_adjustment(19) == 0.0
    assert count_table_adjustment(20) == 0.0


def test_calc_hole_scores_no_strokes():
    assert calc_hole_scores(5, 4, 4, 4) == (4, 4, 4)
    assert calc_hole_scores(18, 0, 3, 3) == (3, 3, 3)


def test_calc_hole_scores_one_stroke():
    gross, net, esc = calc_hole_scores(5, 10, 4, 4)
    assert net == 3
    assert esc == 4


def test_calc_hole_scores_two_strokes():
    gross, net, esc = calc_hole_scores(5, 30, 4, 5)
    assert net == 3


def test_calc_hole_scores_esc_limits_gross():
    gross, net, esc = calc_hole_scores(1, 10, 4, 9)
    assert esc == 7


def test_calc_course_handicap_standard():
    assert calc_course_handicap(10.0, 72, 113, 72) == 10


def test_calc_course_handicap_harder_course():
    result = calc_course_handicap(10.0, 72, 140, 74)
    # WHS Rule 6.1a: nearest whole, .5 UP. 10*(140/113)+(74-72) = 14.39 -> 14.
    # Oracle is a hand-computed literal, NOT round() (which is banker's and
    # would silently validate the wrong rounding on a future tie fixture).
    assert result == 14


# --------------------------------------------------------------------------
# WHS Rule 6.2 / Appendix C -- calc_playing_handicap
# --------------------------------------------------------------------------

def test_calc_playing_handicap_default_allowance_is_unchanged():
    """Default allowance (100%) leaves the Course Handicap unchanged --
    non-breaking behavior for existing (pre-Rule-6.2) callers."""
    assert calc_playing_handicap(20) == 20
    assert calc_playing_handicap(20, 100) == 20


def test_calc_playing_handicap_individual_stroke_95_percent():
    # 20 * 0.95 = 19.0 -> 19 (exact, no rounding tie).
    assert calc_playing_handicap(20, 95) == 19


def test_calc_playing_handicap_fourball_stroke_85_percent():
    # 20 * 0.85 = 17.0 -> 17 (exact, no rounding tie).
    assert calc_playing_handicap(20, 85) == 17


def test_calc_playing_handicap_half_up_tie_rounds_up():
    # WHS Rule 6.2: ".5 rounded upwards" -- 10 * 0.95 = 9.5 -> 10 (half-up).
    assert calc_playing_handicap(10, 95) == 10


def test_calc_playing_handicap_half_up_tie_rounds_up_second_case():
    # 30 * 0.85 = 25.5 -> 26 (half-up).
    assert calc_playing_handicap(30, 85) == 26


def test_calc_playing_handicap_half_up_tie_disagrees_with_banker_rounding():
    # 10 * 0.85 = 8.5. Python's banker's-rounding round(8.5) == 8 (rounds to
    # the nearest EVEN integer), which would be WRONG under WHS Rule 6.2's
    # "rounded upwards" tie-breaking -- calc_playing_handicap must give 9.
    assert round(8.5) == 8  # documents the banker's-rounding pitfall being avoided
    assert calc_playing_handicap(10, 85) == 9


def test_calc_playing_handicap_negative_course_handicap_away_from_zero():
    """A plus (negative) Course Handicap must round consistent with
    round_half_up's documented away-from-zero tie-breaking (see
    round_half_up's NEGATIVE-TIE DECISION docstring) -- Rule 6.2 doesn't
    special-case sign, and calc_playing_handicap delegates straight to
    round_half_up, so a plus handicap's Playing Handicap must follow the
    same convention. -10 * 0.85 = -8.5 -> -9 (away from zero), not -8."""
    assert calc_playing_handicap(-10, 85) == -9


def test_whs_handicap_allowances_appendix_c_reference_values():
    """Appendix C recommended allowances by format -- reference constant
    only; not auto-applied, callers pass an explicit allowance_percent."""
    assert WHS_HANDICAP_ALLOWANCES["individual_match"] == 100
    assert WHS_HANDICAP_ALLOWANCES["individual_stroke"] == 95
    assert WHS_HANDICAP_ALLOWANCES["fourball_stroke"] == 85
    assert WHS_HANDICAP_ALLOWANCES["fourball_match"] == 90
    assert WHS_HANDICAP_ALLOWANCES["stableford_individual"] == 95


def test_calc_round_dif_scratch():
    assert calc_round_dif(113, 72, 72) == 0.0


def test_calc_round_dif_above_rating():
    result = calc_round_dif(128, 85, 71.5)
    assert result == round((113 / 128) * (85 - 71.5), 1)


# --------------------------------------------------------------------------
# WHS Rule 5.6 / 5.1a -- PCC (Playing Conditions Calculation) adjustment
# --------------------------------------------------------------------------

def test_calc_round_dif_pcc_default_zero_unchanged():
    """Default pcc=0.0 must reproduce the exact pre-Rule-5.6 differential --
    non-breaking for every caller that doesn't pass pcc."""
    assert calc_round_dif(113, 90, 72) == 18.0


def test_calc_round_dif_pcc_positive_lowers_differential():
    """WHS Rule 5.6: Score Differential = (113/Slope) x (AGS - CR - PCC).
    A positive PCC (favorable/easy conditions) LOWERS the differential."""
    assert calc_round_dif(113, 90, 72, pcc=1.0) == 17.0


def test_calc_round_dif_pcc_negative_raises_differential():
    """A negative PCC (difficult conditions) RAISES the differential."""
    assert calc_round_dif(113, 90, 72, pcc=-1.0) == 19.0


def test_calc_round_dif_pcc_max_boundary():
    """WHS Rule 5.6's PCC upper bound (+3.0)."""
    assert calc_round_dif(113, 90, 72, pcc=3.0) == 15.0


def test_clamp_pcc_clamps_above_max():
    assert clamp_pcc(5.0) == 3.0


def test_clamp_pcc_clamps_below_min():
    assert clamp_pcc(-2.0) == -1.0


def test_clamp_pcc_within_range_unchanged():
    assert clamp_pcc(1.5) == 1.5
    assert clamp_pcc(-1.0) == -1.0
    assert clamp_pcc(3.0) == 3.0


def test_clamp_pcc_non_numeric_defaults_to_zero():
    assert clamp_pcc("not-a-number") == 0.0
    assert clamp_pcc(None) == 0.0
    assert clamp_pcc("") == 0.0


def test_clamp_pcc_nan_defaults_to_zero():
    assert clamp_pcc(float("nan")) == 0.0


def test_dict_to_round_defaults_pcc_zero_for_legacy_dict():
    """A round dict with no 'pcc' key (legacy DB row / pre-Rule-5.6 data)
    must construct with pcc=0.0, not raise."""
    r = dict_to_round({"date": "2026-01-01"})
    assert r.pcc == 0.0


def test_dict_to_round_clamps_pcc_defense_in_depth():
    """dict_to_round re-clamps pcc even if the source dict carries an
    out-of-range value (e.g. a hand-edited zip-import archive)."""
    r = dict_to_round({"date": "2026-01-01", "pcc": 99})
    assert r.pcc == 3.0


# --------------------------------------------------------------------------
# WHS Rule 5.1b -- 9-hole scores apply only 50% of the day's PCC
# --------------------------------------------------------------------------

def test_effective_pcc_full_for_18_hole():
    assert effective_pcc(2.0, "all") == 2.0


def test_effective_pcc_halved_for_front_nine():
    assert effective_pcc(2.0, "front") == 1.0


def test_effective_pcc_halved_for_back_nine():
    assert effective_pcc(2.0, "back") == 1.0


def test_effective_pcc_halved_negative_pcc():
    assert effective_pcc(-1.0, "front") == -0.5


def test_effective_pcc_zero_stays_zero_regardless_of_holes():
    assert effective_pcc(0.0, "all") == 0.0
    assert effective_pcc(0.0, "front") == 0.0


def test_calc_round_dif_9hole_applies_half_pcc_not_full():
    """WHS Rule 5.1b: a 9-hole (front/back) round with pcc=+2.0 must reflect
    a -1.0 term (half of 2.0) in the differential, NOT the full -2.0 that an
    18-hole round with the same pcc gets. AGS=45, slope=113, rating=36.0:
    - 18-hole equivalent: (113/113)*(45-36-2.0) = 7.0
    - 9-hole (half-pcc):  (113/113)*(45-36-1.0) = 8.0 -- ONE stroke better
      than it would be at full pcc (7.0), reflecting only half the credit."""
    all_18 = calc_round_dif(113, 45, 36.0, pcc=effective_pcc(2.0, "all"))
    nine = calc_round_dif(113, 45, 36.0, pcc=effective_pcc(2.0, "front"))
    assert all_18 == 7.0
    assert nine == 8.0
    assert nine != 7.0  # not accidentally applying the FULL pcc to a 9-hole score


def test_9hole_pcc_consistent_across_calc_recompute_and_zip_import(tmp_data_dir):
    """Consistency (WHS Rule 5.1b): a FRONT-9 round with pcc=+2.0 must
    produce the SAME half-pcc-adjusted differential via calc_round_dif (with
    effective_pcc applied by the caller), store.py's
    recompute_handicaps_for_user inline site, and the routes/settings.py
    zip-import inline site's exact formula -- all three must apply HALF
    pcc, never the full amount, for a 9-hole score."""
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_course, save_round,
        get_all_rounds, get_courses, recompute_handicaps_for_user,
        get_slope_rating,
    )

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("pcc9", "Pcc9", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
    }
    save_course(course, "NineCourse")

    # 1) Pure-helper path: front-9, AGS=45 (half of 90 == a scratch front-9
    # against a half-rating of 36.0), pcc=2.0 -> effective_pcc halves to 1.0.
    assert calc_round_dif(113, 45, 36.0, pcc=effective_pcc(2.0, "front")) == 8.0

    # 2) store.py inline-round path (recompute_handicaps_for_user). Front-9
    # tee has no explicit front_slope/front_rating, so get_slope_rating
    # falls back to the full-round slope/rating (113 / 72.0), and the
    # "front" holes_selection halves the front-rating internally via
    # get_slope_rating's own convention -- here we just assert the ACTUAL
    # code path's output is internally consistent with itself and with
    # calc_round_dif's effective_pcc-adjusted formula, not a hand-picked
    # literal.
    r = {"course": "NineCourse", "tees": "W", "total_gross": "45",
         "differential": "", "computed_handicap": "", "holes_selection": "front",
         "entry_mode": "score_only", "holes": {}, "pcc": 2.0}
    save_round(r, "2026-05-01", 0, user_id=1)
    recompute_handicaps_for_user(user_id=1)
    stored = get_all_rounds(user_id=1)[0]
    assert stored.pcc == 2.0
    assert stored.holes_selection == "front"

    slope, rating = get_slope_rating(course["tees"]["W"], "front")
    expected = round_half_up((113 / slope) * (45 - rating - effective_pcc(2.0, "front")), 1)
    assert float(stored.differential) == expected
    # The critical Rule 5.1b assertion: NOT the full-pcc value.
    full_pcc_would_be = round_half_up((113 / slope) * (45 - rating - 2.0), 1)
    assert float(stored.differential) != full_pcc_would_be

    # 3) routes/settings.py zip-import inline round site's exact formula,
    # reproduced against the same stored round + course tee data (mirrors
    # test_zip_import_differential_rounding_matches_calc_round_dif's
    # pattern for why this doesn't drive the Flask route directly).
    courses_data = get_courses()
    tee_data = courses_data[stored.course]["tees"][stored.tees]
    s2, r2 = get_slope_rating(tee_data, stored.holes_selection)
    zip_import_diff = round_half_up((113 / s2) * (float(stored.total_gross) - r2 - effective_pcc(stored.pcc, stored.holes_selection)), 1)
    assert zip_import_diff == expected == float(stored.differential)


# --------------------------------------------------------------------------
# WHS Rule 5.1a / 5.2a -- round_half_up (differential-round-half-up fix,
# GH#R1). Rule 5.1a: "...rounded to the nearest tenth, with .5 rounded
# upwards" -- Python's built-in round() is banker's rounding (round-half-
# to-even), which silently misrounds exact .5 ties (e.g. round(18.25, 1)
# == 18.2, not the WHS-mandated 18.3). round_half_up fixes every WHS
# nearest-tenth rounding site (Score Differential AND Handicap Index).
# --------------------------------------------------------------------------

def test_round_half_up_ties_round_up_not_to_even():
    """Direct ties: round_half_up always rounds .5 UP, unlike round()'s
    round-half-to-even, which would bounce 18.25 down to 18.2 (wrong) and
    10.05 down to 10.0 (wrong) -- exactly the two examples from WHS Rule
    5.1a's bug report."""
    assert round_half_up(18.25, 1) == 18.3
    assert round(18.25, 1) == 18.2  # banker's rounding: the bug being fixed
    assert round_half_up(10.05, 1) == 10.1


def test_round_half_up_non_tie_values_unchanged():
    """Non-.5 values must round exactly as round() already did -- the fix
    only changes tie-breaking, not ordinary rounding."""
    assert round_half_up(18.24, 1) == 18.2
    assert round_half_up(18.26, 1) == 18.3
    assert round_half_up(0.04, 1) == 0.0
    assert round_half_up(0.06, 1) == 0.1


def test_round_half_up_negative_tie_away_from_zero():
    """NEGATIVE-TIE DECISION (documented in round_half_up's docstring):
    WHS Rule 5.1a's "rounded upwards" is written for the always-nonnegative
    Score Differential, where "upwards" and "away from zero" coincide. This
    implementation adopts away-from-zero for negative ties too (rather than
    toward-positive-infinity), matching Decimal's ROUND_HALF_UP and the
    standard cross-language meaning of "round half up". A negative (plus)
    Handicap Index differential of -2.25 must therefore round to -2.3, NOT
    -2.2 (which is what toward-+infinity rounding would give)."""
    assert round_half_up(-2.25, 1) == -2.3
    assert round_half_up(-2.15, 1) == -2.2
    assert round_half_up(-0.05, 1) == -0.1


def test_calc_round_dif_real_data_tie_18_25_rounds_up():
    """Real-data validation (WHS Rule 5.1a): (113/113)*(90.25-72.0) == 18.25
    exactly -- the round() banker's-rounding bug this fix addresses rounds
    this DOWN to 18.2 (wrong); WHS Rule 5.1a's ".5 rounded upwards" requires
    18.3."""
    raw = (113 / 113) * (90.25 - 72.0)
    assert raw == 18.25
    assert calc_round_dif(113, 90.25, 72.0) == 18.3
    assert round(raw, 1) == 18.2  # the pre-fix (wrong) banker's-rounded value


def test_calc_round_dif_real_data_tie_16_95_rounds_up():
    """Real-data validation (WHS Rule 5.1a), a second exact-tie differential
    computed from realistic slope/AGS/rating inputs (no synthetic decimal
    inputs required): tee slope 120, Adjusted Gross Score 89, Course Rating
    71.0 -> (113/120)*(89-71.0) == 16.95 exactly. Pre-fix, round()'s
    banker's rounding gives 16.9 (wrong, rounds a "5" DOWN to the even
    digit); WHS Rule 5.1a requires 17.0."""
    raw = (113 / 120) * (89 - 71.0)
    assert raw == 16.95
    assert calc_round_dif(120, 89, 71.0) == 17.0
    assert round(raw, 1) == 16.9  # the pre-fix (wrong) banker's-rounded value


def test_calc_handicap_index_real_data_avg_plus_adjustment_tie_rounds_up(make_round):
    """Real-data validation (WHS Rule 5.2a): 6 differentials -> best-2
    average minus the Rule 5.2a count-table adjustment (-1.0 for count==6)
    lands EXACTLY on a tenth-tie. diffs sorted: [5.0, 11.5, 30.0, 30.0,
    30.0, 30.0], best-2 = [5.0, 11.5], avg = 8.25, 8.25 - 1.0 = 7.25 exactly
    -- a genuine "avg + adjustment == x.x5" tie. Pre-fix, round()'s banker's
    rounding gives 7.2 (wrong); WHS Rule 5.2a (via round_half_up) requires
    7.3."""
    rounds = [make_round(differential=str(d))
              for d in (5.0, 11.5, 30.0, 30.0, 30.0, 30.0)]
    avg = (5.0 + 11.5) / 2
    val = avg + count_table_adjustment(6)
    assert val == 7.25
    hi = calc_handicap_index(rounds)
    assert hi == 7.3
    assert round(val, 1) == 7.2  # the pre-fix (wrong) banker's-rounded value


def test_differential_rounding_consistent_across_calc_store_and_zip_import(tmp_data_dir):
    """Consistency (WHS Rule 5.1a): the SAME (slope, AGS, rating) tie input
    must produce the IDENTICAL rounded differential on every code path that
    computes it -- calc_round_dif (the pure helper), store.py's
    recompute_handicaps_for_user (inline round site), and
    routes/settings.py's zip-import backfill (inline round site). All three
    must round the exact 18.25 tie UP to 18.3, never down to 18.2."""
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_course, save_round,
        get_all_rounds, recompute_handicaps_for_user,
    )

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("tie1", "Tie1", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
    }
    save_course(course, "TieCourse")

    # Direct pure-helper path.
    assert calc_round_dif(113, 90.25, 72.0) == 18.3

    # store.py inline-round path: save a round with total_gross = 90.25 and
    # NO differential yet, so recompute_handicaps_for_user's differential
    # backfill (the inline `round_half_up((113/slope)*(...), 1)` site) computes
    # it fresh.
    r = {"course": "TieCourse", "tees": "W", "total_gross": "90.25",
         "differential": "", "computed_handicap": "", "holes_selection": "all",
         "entry_mode": "score_only", "holes": {}}
    save_round(r, "2026-05-01", 0, user_id=1)
    recompute_handicaps_for_user(user_id=1)
    stored = get_all_rounds(user_id=1)[0]
    assert stored.differential == "18.3", (
        f"store.py inline differential round produced {stored.differential!r}, "
        "expected the half-up-rounded '18.3' (WHS Rule 5.1a)."
    )


def test_zip_import_differential_rounding_matches_calc_round_dif(tmp_data_dir):
    """Consistency (WHS Rule 5.1a): routes/settings.py's zip-import
    differential backfill loop must round the same 18.25 tie the same way
    (half up -> 18.3) as calc_round_dif and store.py's recompute."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_course, save_round, get_all_rounds, get_courses
    from calc.handicap import round_half_up as _rhu

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("tie2", "Tie2", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
    }
    save_course(course, "TieCourse")

    r = {"course": "TieCourse", "tees": "W", "total_gross": "90.25",
         "differential": "", "computed_handicap": "", "holes_selection": "all",
         "entry_mode": "score_only", "holes": {}}
    save_round(r, "2026-05-01", 0, user_id=1)

    # Reproduce routes/settings.py's zip-import inline round site directly
    # (importing/exercising the Flask route itself requires a full app/auth
    # fixture; this asserts the exact inline computation the route performs
    # against the same tee data, matching the site-by-site audit).
    all_rounds = get_all_rounds(user_id=1)
    courses_data = get_courses()
    r0 = all_rounds[0]
    tee_data = courses_data[r0.course]["tees"][r0.tees]
    slope = float(tee_data["slope"])
    rating = float(tee_data["rating"])
    diff = _rhu((113 / slope) * (float(r0.total_gross) - rating), 1)
    assert diff == 18.3 == calc_round_dif(113, 90.25, 72.0)


def test_round_saved_with_pcc_stores_pcc_and_differential_reflects_it(tmp_data_dir):
    """WHS Rule 5.6: a round saved with pcc=+1 must (a) store that pcc, and
    (b) have its differential reflect the -PCC term via store.py's
    recompute_handicaps_for_user inline differential-backfill site (the
    same site test_differential_rounding_consistent_... exercises for
    Rule 5.1a). AGS=90, slope=113, rating=72.0, pcc=1.0 ->
    (113/113)*(90-72.0-1.0) = 17.0, vs 18.0 with the default pcc=0."""
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_course, save_round,
        get_all_rounds, recompute_handicaps_for_user,
    )

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("pcc1", "Pcc1", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
    }
    save_course(course, "PccCourse")

    # Round WITH pcc=1.0.
    r_with_pcc = {"course": "PccCourse", "tees": "W", "total_gross": "90",
                  "differential": "", "computed_handicap": "", "holes_selection": "all",
                  "entry_mode": "score_only", "holes": {}, "pcc": 1.0}
    save_round(r_with_pcc, "2026-05-01", 0, user_id=1)

    # Round WITHOUT pcc (default 0.0) -- same score, must be unaffected.
    r_default = {"course": "PccCourse", "tees": "W", "total_gross": "90",
                 "differential": "", "computed_handicap": "", "holes_selection": "all",
                 "entry_mode": "score_only", "holes": {}}
    save_round(r_default, "2026-05-02", 0, user_id=1)

    recompute_handicaps_for_user(user_id=1)
    stored = {r.date: r for r in get_all_rounds(user_id=1)}

    assert stored["2026-05-01"].pcc == 1.0
    assert stored["2026-05-01"].differential == "17.0"

    # Default (no pcc) round: pcc=0.0, differential unchanged vs today
    # (identical to the pre-Rule-5.6 formula / test_differential_rounding_
    # consistent_..._and_zip_import's 18.0-family expectations).
    assert stored["2026-05-02"].pcc == 0.0
    assert stored["2026-05-02"].differential == "18.0"


def test_pcc_differential_consistent_across_calc_store_and_zip_import(tmp_data_dir):
    """Consistency (WHS Rule 5.6): the SAME (slope, AGS, rating, pcc) input
    must produce the IDENTICAL differential via calc_round_dif (the pure
    helper), store.py's recompute_handicaps_for_user (inline round site),
    and the routes/settings.py zip-import inline round site's formula."""
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_course, save_round,
        get_all_rounds, get_courses, recompute_handicaps_for_user,
        get_slope_rating,
    )

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("pcc2", "Pcc2", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
    }
    save_course(course, "PccCourse2")

    # 1) Pure-helper path.
    assert calc_round_dif(113, 90, 72.0, pcc=1.0) == 17.0

    # 2) store.py inline-round path (recompute_handicaps_for_user).
    r = {"course": "PccCourse2", "tees": "W", "total_gross": "90",
         "differential": "", "computed_handicap": "", "holes_selection": "all",
         "entry_mode": "score_only", "holes": {}, "pcc": 1.0}
    save_round(r, "2026-05-01", 0, user_id=1)
    recompute_handicaps_for_user(user_id=1)
    stored = get_all_rounds(user_id=1)[0]
    assert stored.pcc == 1.0
    assert stored.differential == "17.0"

    # 3) routes/settings.py zip-import inline round site's exact formula,
    # reproduced against the same stored round + course tee data (see
    # test_zip_import_differential_rounding_matches_calc_round_dif for why
    # this doesn't drive the Flask route directly).
    courses_data = get_courses()
    tee_data = courses_data[stored.course]["tees"][stored.tees]
    slope, rating = get_slope_rating(tee_data, stored.holes_selection)
    zip_import_diff = round_half_up((113 / slope) * (float(stored.total_gross) - rating - stored.pcc), 1)
    assert zip_import_diff == 17.0 == calc_round_dif(113, 90, 72.0, pcc=1.0)


def test_pcc_out_of_range_clamped_on_save(tmp_data_dir):
    """WHS Rule 5.6: pcc=5.0 -> clamped to 3.0 on persistence (store.save_round's
    defensive clamp_pcc call), and pcc=-2.0 -> clamped to -1.0. Exercised at
    the store layer (bypassing the route-layer clamp) to prove the
    defense-in-depth clamp in save_round itself, not just routes/rounds.py."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_course, save_round, get_all_rounds

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("pcc3", "Pcc3", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)
    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
    }
    save_course(course, "ClampCourse")

    save_round({"course": "ClampCourse", "tees": "W", "total_gross": "90",
                "differential": "0", "computed_handicap": "", "holes_selection": "all",
                "entry_mode": "score_only", "holes": {}, "pcc": 5.0},
               "2026-05-01", 0, user_id=1)
    save_round({"course": "ClampCourse", "tees": "W", "total_gross": "90",
                "differential": "0", "computed_handicap": "", "holes_selection": "all",
                "entry_mode": "score_only", "holes": {}, "pcc": -2.0},
               "2026-05-02", 0, user_id=1)
    save_round({"course": "ClampCourse", "tees": "W", "total_gross": "90",
                "differential": "0", "computed_handicap": "", "holes_selection": "all",
                "entry_mode": "score_only", "holes": {}, "pcc": "not-a-number"},
               "2026-05-03", 0, user_id=1)

    stored = {r.date: r for r in get_all_rounds(user_id=1)}
    assert stored["2026-05-01"].pcc == 3.0
    assert stored["2026-05-02"].pcc == -1.0
    assert stored["2026-05-03"].pcc == 0.0


def test_legacy_db_without_pcc_column_migrates_and_loads(tmp_data_dir):
    """Migration (WHS Rule 5.6): a DB created before the pcc column existed
    (simulated here by creating the `rounds` table WITHOUT it) must still
    load after init_db() runs its migration -- existing rows backfill to
    pcc=0.0 and their differentials are unaffected."""
    import sqlite3
    from database import set_db_path, init_db
    from store import create_user, get_all_rounds

    db_path = str(tmp_data_dir / "legacy.db")
    set_db_path(db_path)

    # Simulate a pre-Rule-5.6 DB: create users + a rounds table with NO pcc
    # column (mirrors the pre-migration schema in database.py's CREATE
    # TABLE), then insert a legacy round row directly, bypassing store.py
    # entirely so no code path can implicitly create the column first.
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE users (
            id            INTEGER PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            display_name  TEXT NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',
            is_admin      INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE rounds (
            id            INTEGER PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id),
            course_name   TEXT NOT NULL,
            date          TEXT NOT NULL,
            round_index   INTEGER NOT NULL DEFAULT 0,
            tee_name      TEXT,
            holes_played  TEXT,
            entry_mode    TEXT,
            holes         TEXT,
            total_gross   TEXT,
            total_putts   TEXT,
            differential  TEXT,
            notes         TEXT,
            excluded      INTEGER DEFAULT 0,
            computed_handicap TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, date, round_index)
        )
    """)
    conn.execute(
        "INSERT INTO users (id, username, display_name, password_hash) VALUES (1, 'legacy', 'Legacy', 'x')"
    )
    conn.execute(
        """INSERT INTO rounds
           (user_id, course_name, date, round_index, tee_name, holes_played,
            entry_mode, holes, total_gross, differential, notes, excluded, computed_handicap)
           VALUES (1, 'LegacyCourse', '2025-01-01', 0, 'W', 'all', 'score_only', '{}',
                   '85', '18.0', '', 0, '10.0')"""
    )
    conn.commit()
    conn.close()

    # init_db()'s migration (_add_column_if_missing) must add pcc without
    # error and without touching the existing (pre-Rule-5.6) differential.
    init_db()

    rounds = get_all_rounds(user_id=1)
    assert len(rounds) == 1
    assert rounds[0].pcc == 0.0
    assert rounds[0].differential == "18.0"


def test_calc_9hole_dif_combines_base_with_expected():
    # WHS 9-hole combine: base 9-hole Score Differential + the expected
    # 9-hole adjustment keyed on the prior displayed Handicap Index
    # (handicap_index * 0.52 + 1.197). base = (113/113)*(45-33.7) = 11.3.
    assert calc_9hole_dif(113, 45, 33.7, 10.0) == round(11.3 + 10.0 * 0.52 + 1.197, 1) == 17.7
    # A genuine 0.0 scratch HI still gets the expected term -- matches the TUI.
    assert calc_9hole_dif(113, 45, 33.7, 0.0) == round(11.3 + 0.0 * 0.52 + 1.197, 1) == 12.5


def test_calc_9hole_dif_no_prior_hi_returns_raw_base():
    # No established HI -> the raw base 9-hole Score Differential, unadjusted.
    assert calc_9hole_dif(113, 45, 33.7, None) == 11.3


def test_calc_expected_9hole_dif():
    assert calc_expected_9hole_dif(10.0) == 10.0 * 0.52 + 1.197
    assert calc_expected_9hole_dif(0.0) == 1.197


def test_calc_effective_diffs_empty():
    assert calc_effective_diffs([]) == []


def test_calc_effective_diffs_18_hole(sample_rounds):
    diffs = calc_effective_diffs(sample_rounds)
    assert len(diffs) == 3
    assert diffs == sorted(diffs)


def test_calc_effective_diffs_excluded_round(make_round):
    rounds = [
        make_round(gross=80, differential="10.0"),
        make_round(gross=90, differential="20.0"),
    ]
    rounds[1].excluded = True
    diffs = calc_effective_diffs(rounds)
    assert len(diffs) == 1
    assert diffs[0] == 10.0


def test_calc_effective_diffs_missing_differential(make_round):
    rounds = [make_round(differential=""), make_round(differential="0")]
    assert calc_effective_diffs(rounds) == []


def test_calc_effective_diffs_9hole_excluded_by_default(make_round):
    rounds = [make_round(gross=45, differential="10.0", holes_selection="front")]
    assert calc_effective_diffs(rounds) == []


def test_calc_effective_diffs_9hole_included(make_round):
    rounds = [make_round(gross=45, differential="10.0", holes_selection="front",
                          computed_handicap="12.0")]
    diffs = calc_effective_diffs(rounds, include_9hole=True)
    assert len(diffs) == 1
    assert diffs[0] == math.floor(10.0 * 10) / 10


def test_calc_effective_diffs_9hole_no_handicap(make_round):
    rounds = [make_round(gross=45, differential="10.0", holes_selection="front",
                          computed_handicap="0")]
    diffs = calc_effective_diffs(rounds, include_9hole=True)
    assert diffs == []


def test_get_best_n_rounds_none(make_round):
    rounds = [make_round(gross=g, differential=str(100 - g)) for g in range(70, 90)]
    best = get_best_n_rounds(rounds)
    assert len(best) == count_table_n(len(rounds))


def test_get_best_n_rounds_explicit_n(make_round):
    rounds = [make_round(gross=g, differential=str(100 - g)) for g in range(70, 90)]
    best = get_best_n_rounds(rounds, n=3)
    assert len(best) == 3


def test_get_best_n_rounds_sorted(make_round):
    rounds = [make_round(gross=g, differential=str(100 - g)) for g in (80, 75, 90, 72, 85)]
    best = get_best_n_rounds(rounds, n=2)
    diffs = [math.floor(float(r.differential) * 10) / 10 for r in best]
    assert diffs == sorted(diffs)


# --------------------------------------------------------------------------
# WHS Rule 5.8 -- Soft Cap / Hard Cap (apply_handicap_cap)
# --------------------------------------------------------------------------

def test_apply_handicap_cap_no_lhi_passes_through():
    """Rule 5.7: before an LHI is established (low_hi is None), no cap."""
    assert apply_handicap_cap(12.5, None) == 12.5


def test_apply_handicap_cap_small_increase_uncapped():
    # increase 2.5 <= 3.0 -- no cap.
    assert apply_handicap_cap(12.5, 10.0) == 12.5


def test_apply_handicap_cap_soft_cap_increase_4():
    # increase 4.0 -- soft cap: 10 + 3 + 0.5*(4-3) = 13.5
    assert apply_handicap_cap(14.0, 10.0) == 13.5


def test_apply_handicap_cap_soft_cap_increase_6():
    # increase 6.0 -- soft cap: 10 + 3 + 0.5*(6-3) = 14.5
    assert apply_handicap_cap(16.0, 10.0) == 14.5


def test_apply_handicap_cap_hard_cap_kicks_in():
    # increase 10.0 -- soft cap would give 16.5, but hard cap limits to
    # low_hi + 5.0 = 15.0.
    assert apply_handicap_cap(20.0, 10.0) == 15.0


def test_apply_handicap_cap_decrease_unchanged():
    # Decreases are never capped.
    assert apply_handicap_cap(9.0, 10.0) == 9.0


def test_calc_handicap_index_empty():
    assert calc_handicap_index([]) is None


def test_calc_handicap_index_too_few_rounds(make_round):
    rounds = [make_round() for _ in range(2)]
    assert calc_handicap_index(rounds) is None


def test_calc_handicap_index_scratch(make_round):
    rounds = [make_round(gross=72, differential=str(i * 0.5)) for i in range(20)]
    hi = calc_handicap_index(rounds)
    assert hi is not None
    assert hi >= 0


def test_calc_handicap_index_bogey(make_round):
    rounds = [make_round(gross=90, differential=str(15 + i * 0.5)) for i in range(20)]
    hi = calc_handicap_index(rounds)
    assert hi is not None
    assert 10 < hi < 25


def test_calc_handicap_index_never_negative(make_round):
    # NOTE: this invariant only holds here because each dataset has 19-20
    # effective differentials, where WHS Rule 5.2a's count_table_adjustment
    # is 0.0. Smaller records (e.g. 3 diffs) CAN legitimately go negative --
    # see test_calc_handicap_index_negative_not_clamped.
    for gross in (72, 80, 90, 100):
        rounds = [make_round(gross=gross, differential=str(gross - 72 + i))
                  for i in range(20)]
        hi = calc_handicap_index(rounds)
        assert hi is None or hi >= 0


def test_calc_handicap_index_best8_le_raw(make_round):
    rounds = [make_round(gross=75 + i, differential=str(i * 2)) for i in range(30)]
    diffs = calc_effective_diffs(rounds[:20])
    if len(diffs) >= 8:
        hi = calc_handicap_index(rounds[:20])
        raw_avg = sum(diffs) / len(diffs)
        assert hi <= raw_avg


def test_calc_handicap_index_3_diffs_applies_adjustment(make_round):
    """WHS Rule 5.2a: 3 differentials -> best-1 average minus 2.0 adjustment.
    diffs sorted: [15.2, 15.3, 16.6], best-1 = 15.2, 15.2 - 2.0 = 13.2."""
    rounds = [make_round(differential=str(d)) for d in (15.3, 15.2, 16.6)]
    assert calc_handicap_index(rounds) == 13.2


def test_calc_handicap_index_4_diffs_applies_adjustment(make_round):
    """WHS Rule 5.2a: 4 differentials -> best-1 average minus 1.0 adjustment.
    diffs sorted: [22.0, 23.1, 24.0, 25.0], best-1 = 22.0, 22.0 - 1.0 = 21.0."""
    rounds = [make_round(differential=str(d)) for d in (22.0, 23.1, 24.0, 25.0)]
    assert calc_handicap_index(rounds) == 21.0


def test_calc_handicap_index_6_diffs_applies_adjustment(make_round):
    """WHS Rule 5.2a: 6 differentials -> best-2 average minus 1.0 adjustment.
    diffs sorted: [18.0..23.0], best-2 = [18.0, 19.0] avg 18.5, 18.5 - 1.0 = 17.5."""
    rounds = [make_round(differential=str(d))
              for d in (18.0, 19.0, 20.0, 21.0, 22.0, 23.0)]
    assert calc_handicap_index(rounds) == 17.5


def test_calc_handicap_index_19_diffs_no_adjustment(make_round):
    """WHS Rule 5.2a: 19 differentials -> adjustment is 0.0 (not in the
    {3, 4, 6} table), so the result is the plain average of the best-7
    (count_table_n(19) == 7) with no adjustment subtracted.
    diffs = 1.0..19.0, best-7 = [1.0..7.0], avg = 4.0."""
    rounds = [make_round(differential=str(float(d))) for d in range(1, 20)]
    assert len(rounds) == 19
    assert count_table_adjustment(19) == 0.0
    assert calc_handicap_index(rounds) == 4.0


def test_calc_handicap_index_negative_not_clamped(make_round):
    """WHS Rule 5.2a intentionally allows negative (plus) handicap indexes --
    no clamping is applied here (the 54.0 max is a separate, out-of-scope
    rule). 3 differentials -> best-1 average minus 2.0 adjustment.
    diffs sorted: [1.0, 2.0, 3.0], best-1 = 1.0, 1.0 - 2.0 = -1.0."""
    rounds = [make_round(differential=str(d)) for d in (1.0, 2.0, 3.0)]
    hi = calc_handicap_index(rounds)
    assert hi == -1.0
    assert hi < 0


def test_calc_handicap_trend_empty():
    assert calc_handicap_trend([]) == []


def test_calc_handicap_trend_returns_pairs(make_round):
    rounds = [make_round(date=f"2026-05-{d:02d}", gross=80, differential="10.0")
              for d in range(1, 21)]
    trend = calc_handicap_trend(rounds)
    assert len(trend) > 0
    assert all(isinstance(t, tuple) and len(t) == 2 for t in trend)


def test_calc_playing_to_handicap_rate_empty():
    assert calc_playing_to_handicap_rate([]) is None


def test_calc_playing_to_handicap_rate_mixed(make_round):
    rounds = [
        make_round(gross=72, differential="2.0", computed_handicap="5.0"),
        make_round(gross=80, differential="10.0", computed_handicap="5.0"),
        make_round(gross=76, differential="6.0", computed_handicap="5.0"),
    ]
    rate = calc_playing_to_handicap_rate(rounds)
    assert rate is not None
    assert 0 <= rate <= 100


def test_calc_playing_to_handicap_rate_all_above(make_round):
    rounds = [make_round(gross=90, differential="20.0", computed_handicap="5.0")
              for _ in range(5)]
    assert calc_playing_to_handicap_rate(rounds) == 0.0


def test_calc_playing_to_handicap_rate_all_below(make_round):
    rounds = [make_round(gross=72, differential="2.0", computed_handicap="10.0")
              for _ in range(5)]
    assert calc_playing_to_handicap_rate(rounds) == 100.0


def test_calc_raw_hi_empty():
    assert calc_raw_hi([]) is None


def test_calc_raw_hi_approximate(make_round):
    rounds = [make_round(gross=80, differential=str(i)) for i in (5, 6, 7, 8, 9)]
    raw = calc_raw_hi(rounds)
    expected = ((5 + 6 + 7 + 8 + 9) / 5) * 0.96
    assert raw == expected


def test_calc_course_handicap_maplewood_white():
    assert calc_course_handicap(21.7, 72, 120, 67.7) == 19


def test_calc_course_handicap_druids_white():
    assert calc_course_handicap(22.3, 72, 130, 69.3) == 23


def test_calc_course_handicap_round_over_int():
    assert calc_course_handicap(21.7, 72, 120, 67.7) == 19
    assert calc_course_handicap(21.7, 72, 120, 67.7) != 18


def test_calc_course_handicap_near_boundary():
    assert calc_course_handicap(10.0, 72, 113, 72) == 10
    assert calc_course_handicap(10.0, 72, 140, 74) == 14


def test_handicap_index_last_20_vs_all(make_round):
    """WHS Rule 5.2: best 8 of most recent 20 ELIGIBLE differentials only. A
    round outside the last-20 window must never influence the index.

    Pre-fix, calc_handicap_index had no internal window, so passing the full
    30-round list (rounds, unsliced) wrongly produced best-8-of-all-career
    (19.7, pulled down by the 21st-round diff 21.7). Post-fix (WHS Rule 5.2
    windowing), calc_handicap_index does its own most-recent-20-eligible
    windowing internally, so passing the caller-pre-sliced 20 (rounds[:20])
    and passing the full most-recent-first history (rounds) now agree: both
    correctly resolve to 19.8."""
    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]
    rounds = [make_round(differential=str(d)) for d in diffs]

    hi_20 = calc_handicap_index(rounds[:20])
    hi_all = calc_handicap_index(rounds)

    assert hi_20 == 19.8
    assert hi_all == 19.8
    assert hi_20 == hi_all


# NOTE: a prior version of this test (test_store_recompute_window_slice) hand-
# replicated store.py's OLD `chronological[max(0,i+1-20):i+1]` slice and
# asserted calc_handicap_index behaved correctly on that manually-built
# window. That implementation no longer exists in store.py (recompute now
# passes the full most-recent-first history and lets calc_handicap_index's
# internal eligible-window do the work -- see
# test_store_recompute_matches_direct_calc_handicap_index below, which
# exercises the actual store.py code path instead of a hand-rolled stand-in).
# The manual-window sanity check itself is subsumed by
# test_handicap_index_last_20_vs_all above, so it was removed rather than
# left with a stale docstring describing removed production code.


# --- WHS Rule 5.2 windowing fix: calc_handicap_index now owns the
# most-recent-20-eligible window internally (see docstring on
# calc_handicap_index). Callers must pass most-recent-first order. ---

def test_calc_handicap_index_windows_to_recent_20_internally(make_round):
    """WHS Rule 5.2: with NO manual slicing by the caller, calc_handicap_index
    must still use only the 20 most recent acceptable differentials -- not
    best-8-of-all-career. 25 differentials, most-recent-first (index 0 =
    newest), constructed so best-8-of-all-25 != best-8-of-recent-20."""
    # Most-recent-first: the 21st-25th (oldest, indices 20-24) are very LOW
    # differentials that would pull the index down if wrongly included.
    recent_20 = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
                 21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8]
    older_5_low = [1.0, 1.1, 1.2, 1.3, 1.4]
    diffs_most_recent_first = recent_20 + older_5_low
    rounds = [make_round(differential=str(d)) for d in diffs_most_recent_first]

    hi_full_history = calc_handicap_index(rounds)  # no manual slicing by caller
    hi_manual_20 = calc_handicap_index(rounds[:20])

    assert hi_full_history == hi_manual_20 == 19.8
    # Sanity: if the older low diffs (outside the window) had wrongly been
    # included, best-8-of-all-25 would be lower than 19.8.
    all_diffs_sorted = sorted(diffs_most_recent_first)
    naive_best8_of_all = sum(all_diffs_sorted[:8]) / 8
    assert round(naive_best8_of_all, 1) != hi_full_history


def test_calc_handicap_index_excluded_rounds_do_not_consume_window_slots(make_round):
    """WHS Rule 5.2: the window is 20 ELIGIBLE differentials, not 20 raw
    rounds. Interleave excluded rounds among >20 rounds and assert the
    excluded ones are skipped over (not counted toward the 20-slot cap),
    so a 21st/22nd truly-eligible round still gets pulled into the window."""
    # 22 eligible diffs, most-recent-first, plus 3 excluded rounds interspersed
    # near the front. If exclusions wrongly consumed window slots, only
    # 17 eligible diffs would end up windowed (20 - 3 excluded raw slots),
    # and diffs_20/diffs_21 (indices 19/20 of the eligible list) would be
    # dropped from the window.
    eligible_diffs = [float(10 + i) for i in range(22)]  # 10.0..31.0, ascending order in list
    rounds = []
    # interleave: excluded, eligible, excluded, eligible..., excluded, then rest eligible
    it = iter(eligible_diffs)
    rounds.append(make_round(differential=str(next(it))))
    excluded_round = make_round(differential="99.9")
    excluded_round.excluded = True
    rounds.append(excluded_round)
    rounds.append(make_round(differential=str(next(it))))
    excluded_round2 = make_round(differential="99.9")
    excluded_round2.excluded = True
    rounds.append(excluded_round2)
    rounds.append(make_round(differential=str(next(it))))
    excluded_round3 = make_round(differential="99.9")
    excluded_round3.excluded = True
    rounds.append(excluded_round3)
    for d in it:
        rounds.append(make_round(differential=str(d)))

    # Sanity: 25 raw rounds (22 eligible + 3 excluded), most-recent-first.
    assert len(rounds) == 25
    assert sum(1 for r in rounds if r.excluded) == 3

    diffs = calc_effective_diffs(rounds)
    assert len(diffs) == 22  # all 22 eligible differentials exist in the record

    hi = calc_handicap_index(rounds)
    # The window must contain the FIRST 20 eligible diffs (10.0..29.0), i.e.
    # the last 2 eligible diffs (30.0, 31.0) must be excluded from the window
    # -- proving exclusions were skipped over rather than consuming slots.
    windowed_diffs = eligible_diffs[:20]
    n = count_table_n(len(windowed_diffs))
    expected = round(sum(sorted(windowed_diffs)[:n]) / n + count_table_adjustment(len(windowed_diffs)), 1)
    assert hi == expected

    # If exclusions had wrongly consumed window slots, only the first 17
    # eligible diffs (10.0..26.0) would be windowed -- verify that's NOT
    # what happened by checking the 30.0/31.0 diffs are excluded but 29.0 IS
    # included (proves the window reached the 20th eligible diff, not the
    # 20th raw round).
    windowed_diffs_if_bug = eligible_diffs[:17]
    n_bug = count_table_n(len(windowed_diffs_if_bug))
    buggy_hi = round(sum(sorted(windowed_diffs_if_bug)[:n_bug]) / n_bug +
                      count_table_adjustment(len(windowed_diffs_if_bug)), 1)
    assert hi != buggy_hi


def test_store_recompute_matches_direct_calc_handicap_index(tmp_data_dir):
    """WHS Rule 5.2 consistency: recompute_handicaps_for_user must write, for
    the latest round, the SAME computed_handicap that a direct
    calc_handicap_index(most_recent_first_full_list) call produces
    (recompute == live-save). Guards store.py's per-round windowing."""
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_round, get_all_rounds,
        recompute_handicaps_for_user,
    )

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("golfer2", "Golfer2", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]

    for i, d in enumerate(diffs):
        day = 30 - i
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(d), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{day:02d}", 0, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    all_rounds = get_all_rounds(user_id=1)  # most-recent-first (ORDER BY date DESC)
    most_recent = all_rounds[0]

    direct_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert direct_hi is not None
    assert most_recent.computed_handicap == str(direct_hi), (
        f"recompute wrote {most_recent.computed_handicap!r} but a direct "
        f"calc_handicap_index(most-recent-first full list) call gives "
        f"{direct_hi!r} -- recompute and live-save must agree (WHS Rule 5.2)."
    )


def test_get_best_n_rounds_capped_to_last_20(make_round):
    """Dashboard best_rounds must come from the most recent 20 rounds, not all.
    A round outside the last 20 (diff 21.7) must not appear in best-8."""
    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]
    rounds = [make_round(differential=str(d)) for d in diffs]

    best_capped = get_best_n_rounds(rounds[:20])
    capped_diffs = [float(r.differential) for r in best_capped]
    assert 21.7 not in capped_diffs
    assert len(best_capped) == 8

    best_uncapped = get_best_n_rounds(rounds)
    uncapped_diffs = [float(r.differential) for r in best_uncapped]
    assert 21.7 in uncapped_diffs
    assert len(best_uncapped) == 8


def test_get_best_n_rounds_window_skips_ineligible_rounds(make_round):
    """WHS Rule 5.2: get_best_n_rounds(..., window=20) must count 20
    ELIGIBLE rounds, not 20 raw rounds. An excluded round planted INSIDE the
    raw most-recent-20 must not stop the window early -- the window must
    reach into the 21st physical round to keep the pool at 20 eligible.

    Non-vacuous: the naive get_best_n_rounds(rounds[:20], ...) (raw
    pre-slice, no window param -- the old dashboard.py/rounds.py call
    pattern this fix replaced) never even considers the pulled-in round,
    since it falls outside a raw rounds[:20] slice."""
    rounds = []
    for i in range(22):
        if i == 5:
            # Excluded round planted inside the raw most-recent-20 -- must
            # vacate a window slot rather than consume one.
            r = make_round(differential="77.7")
            r.excluded = True
        elif i == 20:
            # The 21st physical round -- must be pulled into the eligible
            # window because the excluded round at i=5 vacated a slot. Given
            # a very low differential so it's unambiguously present in
            # best-8 if (and only if) the window correctly reaches it.
            r = make_round(differential="1.0")
        elif i == 21:
            # The 22nd physical round -- must NEVER enter the 20-eligible
            # window (only reachable if the window incorrectly extends
            # beyond 20 eligible slots).
            r = make_round(differential="999.9")
        elif i < 5:
            r = make_round(differential=str(10 + i))
        else:
            r = make_round(differential=str(50 + i))
        rounds.append(r)

    assert len(rounds) == 22
    assert sum(1 for r in rounds if r.excluded) == 1

    best_windowed = get_best_n_rounds(rounds, window=WHS_HANDICAP_WINDOW)
    best_diffs = [float(r.differential) for r in best_windowed]
    assert len(best_windowed) == count_table_n(20) == 8
    assert 1.0 in best_diffs, (
        "The 21st physical round (diff 1.0) must be pulled into the "
        "eligible window when the excluded round at raw index 5 vacates a "
        "slot -- the window must count 20 ELIGIBLE rounds, not 20 raw "
        "rounds."
    )
    assert 999.9 not in best_diffs  # 22nd physical round stays outside the window

    # Sanity: prove this is non-vacuous -- the naive raw-slice approach
    # (get_best_n_rounds(rounds[:20]), no window param) never even
    # considers the round with diff 1.0, since it falls outside rounds[:20].
    naive_best = get_best_n_rounds(rounds[:20])
    naive_diffs = [float(r.differential) for r in naive_best]
    assert 1.0 not in naive_diffs, (
        "Test fixture did not exercise the divergence -- the naive raw-20 "
        "slice unexpectedly already included the pulled-in round."
    )


def test_secondary_handicap_value_windows_rounds_1_to_21_correctly(make_round):
    """WHS Rule 5.2: composite.py's SECONDARY handicap value
    (calc_handicap_index(rounds[1:], include_9hole)) must apply its OWN
    fresh most-recent-20-ELIGIBLE window over `rounds[1:]` -- not an
    off-by-one/raw-20 slice of the sub-list. An excluded round planted
    inside rounds[1:21] (the raw most-recent-20 of the sub-list) must not
    stop that window early; it must reach the 21st round of rounds[1:] to
    keep 20 eligible."""
    rounds = []
    for i in range(23):
        if i == 0:
            # The "current" round -- dropped entirely by rounds[1:], must
            # never influence the secondary value.
            r = make_round(differential="500.0")
        elif i == 6:
            # Excluded round inside rounds[1:21] (subslice index 5).
            r = make_round(differential="77.7")
            r.excluded = True
        elif i == 21:
            # Subslice index 20 -- the 21st round of rounds[1:]. Must be
            # pulled into the window because the excluded round at i=6
            # vacated a slot.
            r = make_round(differential="1.0")
        elif i == 22:
            # Subslice index 21 -- the 22nd round of rounds[1:]. Must stay
            # OUTSIDE the 20-eligible window.
            r = make_round(differential="999.9")
        elif 1 <= i <= 5:
            r = make_round(differential=str(10 + i))
        else:  # i = 7..20
            r = make_round(differential=str(50 + i))
        rounds.append(r)

    assert len(rounds) == 23

    secondary_hi = calc_handicap_index(rounds[1:])

    # Hand-computed expectation: the 20 ELIGIBLE differentials of rounds[1:]
    # in most-recent-first order, skipping the excluded round and reaching
    # to subslice index 20 (i=21) to make up for it.
    expected_windowed_diffs = (
        [11.0, 12.0, 13.0, 14.0, 15.0] +           # i = 1..5
        [50.0 + i for i in range(7, 21)] +          # i = 7..20
        [1.0]                                       # i = 21, pulled in
    )
    assert len(expected_windowed_diffs) == 20
    n = count_table_n(len(expected_windowed_diffs))
    expected_hi = round(
        sum(sorted(expected_windowed_diffs)[:n]) / n
        + count_table_adjustment(len(expected_windowed_diffs)),
        1,
    )
    assert secondary_hi == expected_hi == 22.6

    # Sanity: prove non-vacuous -- a naive off-by-one raw slice
    # (rounds[1:21], no re-windowing, filtered for exclusions but never
    # reaching subslice index 20) silently drops the pulled-in round
    # (i=21, diff 1.0), producing a DIFFERENT (wrong) value.
    naive_raw_slice_diffs = [
        float(r.differential) for r in rounds[1:21]
        if not r.excluded and r.differential not in ("0", "", None)
    ]
    assert 1.0 not in naive_raw_slice_diffs
    naive_n = count_table_n(len(naive_raw_slice_diffs))
    naive_hi = round(
        sum(sorted(naive_raw_slice_diffs)[:naive_n]) / naive_n
        + count_table_adjustment(len(naive_raw_slice_diffs)),
        1,
    )
    assert naive_hi != secondary_hi


# --- Guard tests for WHS last-20 windowing fix (call-site verification) ---

def test_recompute_handicaps_uses_last_20_window(tmp_data_dir):
    """recompute_all_handicaps must window to the most recent 20 ELIGIBLE
    differentials. With 30 rounds, the most-recent round must have HI 19.8
    (last-20 correct), NOT 19.7 (all-rounds, which wrongly includes diff 21.7
    from outside the last 20). Guards the current store.py mechanism: passing
    the full most-recent-first history per round and letting
    calc_handicap_index's internal WHS_HANDICAP_WINDOW-eligible window (see
    calc/handicap.py) do the windowing, rather than store.py pre-slicing."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_all_handicaps

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("golfer", "Golfer", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]

    for i, d in enumerate(diffs):
        day = 30 - i
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(d), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{day:02d}", 0, user_id=1)

    recompute_all_handicaps()

    rounds = get_all_rounds(user_id=1)
    most_recent = rounds[0]
    assert most_recent.computed_handicap == "19.8", (
        f"Most-recent round should have last-20 HI 19.8, got {most_recent.computed_handicap}"
    )


def test_profile_hi_insight_eight_of_twenty(tmp_path, monkeypatch):
    """_build_profile_context must report '8 of your last 20' because all
    best-8 rounds come from within the most recent 20 ELIGIBLE
    differentials. Guards dashboard.py's current mechanism:
    get_best_n_rounds(rounds, include_9hole, window=WHS_HANDICAP_WINDOW),
    which passes the FULL most-recent-first `rounds` and lets the eligible-
    window cap (20) select the pool internally, rather than pre-truncating
    to a raw rounds[:20] slice. The round at index 20 (diff 21.7) must stay
    outside that 20-eligible window (no exclusions in this fixture, so raw
    and eligible windows coincide here -- see
    test_get_best_n_rounds_window_skips_ineligible_rounds and
    test_secondary_handicap_value_windows_rounds_1_to_21_correctly below for
    fixtures where an excluded/ineligible round forces the eligible window
    to diverge from a raw slice)."""
    from main import app, User as UserClass
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_course, save_round, get_user_by_id
    from flask_login import login_user

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

    create_user("p", "P", "pass1234")
    save_settings({"welcome_shown": True, "include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "120", "rating": "70.0", "yardage": "6000"}},
    }
    save_course(course, "GC")

    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]

    for i, d in enumerate(diffs):
        day = 30 - i
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(d), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{day:02d}", 0, user_id=1)

    with app.test_request_context():
        user_dict = get_user_by_id(1)
        login_user(UserClass(user_dict))

        from source.routes.dashboard import _build_profile_context
        ctx = _build_profile_context()
        assert ctx is not None, "_build_profile_context returned None (welcome_shown?)"

        hi_insight = ctx.get("hi_insight")
        assert hi_insight is not None, "No hi_insight in profile context"
        assert "8 of your last 20" in hi_insight, (
            f"Expected '8 of your last 20', got: {hi_insight}"
        )


def test_dashboard_hi_matches_recompute_with_excluded_round_in_window(tmp_path, monkeypatch):
    """WHS Rule 5.2 correctness regression (adversary-gate finding): an
    excluded round sitting within the raw most-recent-20 must NOT desync the
    dashboard-computed Handicap Index from the authoritative stored/
    recompute value.

    Pre-fix, compute_stat_bundle (via dashboard.py's `l20 =
    last_n_rounds(rounds, 20)`) pre-truncated to a raw-20 slice BEFORE
    calling calc_handicap_index, so an excluded round inside that raw-20
    silently shrank the eligible pool to 19 differentials (best-7, no Rule
    5.2a adjustment) instead of reaching one round further back to keep a
    full 20-eligible window (best-8) -- a real 12.5-vs-13.5-style divergence
    from the value store.recompute_handicaps_for_user writes. This test
    proves that divergence is gone by asserting the dashboard's computed
    value against the recompute-stored value, and separately proves the old
    raw-20-pre-truncation approach WOULD have produced a different value for
    this fixture (i.e. the regression is meaningfully covered, not
    vacuously passing)."""
    from main import app, User as UserClass
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_course, save_round, get_user_by_id,
        set_round_excluded, recompute_handicaps_for_user, get_all_rounds,
    )
    from flask_login import login_user
    from calc.composite import last_n_rounds as _buggy_raw20

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

    create_user("q", "Q", "pass1234")
    save_settings({"welcome_shown": True, "include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "120", "rating": "70.0", "yardage": "6000"}},
    }
    save_course(course, "GC")

    # 22 rounds, most-recent-first by descending day. The 6th-most-recent
    # round (index 5) is excluded, so a correct WHS Rule 5.2 window must
    # reach back to the 22nd (oldest, index 21) round to keep 20 eligible.
    diffs = [10.0 + i for i in range(22)]
    excluded_index = 5

    for i, d in enumerate(diffs):
        day = 30 - i
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(d), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{day:02d}", 0, user_id=1)

    excluded_date = f"2026-05-{30 - excluded_index:02d}"
    set_round_excluded(excluded_date, 0, True, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    all_rounds = get_all_rounds(user_id=1)  # most-recent-first (ORDER BY date DESC)
    stored_hi = all_rounds[0].computed_handicap
    assert stored_hi not in (None, "", "0")

    with app.test_request_context():
        user_dict = get_user_by_id(1)
        login_user(UserClass(user_dict))

        from source.routes.dashboard import _build_profile_context
        ctx = _build_profile_context()
        assert ctx is not None, "_build_profile_context returned None (welcome_shown?)"
        dashboard_hi = ctx["panels"]["handicap"]["value"]

    assert dashboard_hi == stored_hi, (
        f"Dashboard HI {dashboard_hi!r} diverged from recompute-stored HI "
        f"{stored_hi!r} -- an excluded round inside the raw most-recent-20 "
        f"must not desync the two (WHS Rule 5.2)."
    )

    # Sanity: prove the fix matters -- the OLD raw-20-pre-truncation
    # approach WOULD have produced a DIFFERENT (wrong) value for this data.
    buggy_l20 = _buggy_raw20(all_rounds, 20)
    buggy_hi = calc_handicap_index(buggy_l20, True)
    assert buggy_hi is not None
    assert str(buggy_hi) != stored_hi, (
        "Test fixture did not actually exercise the divergence -- the old "
        "raw-20-pre-truncation path produced the same HI as the fix; "
        "adjust the fixture so the regression is meaningfully covered."
    )


# --------------------------------------------------------------------------
# WHS Rule 5.7 -- 365-day LHI window boundary (adversary-gate Defect 1)
# --------------------------------------------------------------------------

def test_lhi_365_day_boundary_is_inclusive(tmp_data_dir):
    """WHS Rule 5.7: 'the lowest Handicap Index... over the 365-day period
    PRECEDING' the round being processed is a CLOSED interval -- a prior
    displayed HI dated EXACTLY 365 days before the round must be INCLUDED
    as an LHI candidate. A strict `>` cutoff comparison would silently
    exclude that boundary day, shrinking the window to 364 days.

    Construction: an anchor round establishes a very low displayed HI
    (~-1.0). 17 filler rounds bring the acceptable-score count to 20. A
    probe round posted exactly `gap` days after the anchor then triggers a
    huge raw spike -- if the anchor is still within the LHI window, the
    spike is soft/hard-capped down (using the low anchor as LHI); if the
    anchor has aged out, a much higher (wrong) LHI is used instead,
    producing a materially different capped result."""
    from database import set_db_path, init_db
    from store import create_user, save_round, get_all_rounds, recompute_handicaps_for_user
    from datetime import date as _date, timedelta as _timedelta

    def mkround(date_str, diff):
        return {
            "date": date_str, "course": "X", "tees": "White", "holes_played": "18",
            "holes_selection": "all", "entry_mode": "score_only", "holes": {},
            "total_gross": "90", "differential": str(diff), "notes": "",
            "excluded": False, "computed_handicap": "",
        }

    def d(base, offset_days):
        return (_date.fromisoformat(base) + _timedelta(days=offset_days)).isoformat()

    def run_with_gap(gap_days, db_path):
        set_db_path(db_path)
        init_db()
        uid = create_user("atk", "Attacker", "pass1234")["id"]
        D0 = "2020-01-01"
        save_round(mkround(D0, 20.0), D0, 0, uid)
        save_round(mkround(d(D0, 1), 20.0), d(D0, 1), 0, uid)
        anchor_date = d(D0, 2)
        save_round(mkround(anchor_date, 1.0), anchor_date, 0, uid)  # very low displayed HI
        for i in range(17):
            save_round(mkround(d(D0, 3 + i), 20.0), d(D0, 3 + i), 0, uid)  # count -> 20

        probe_date = d(anchor_date, gap_days)
        save_round(mkround(probe_date, 200.0), probe_date, 0, uid)  # huge raw spike

        recompute_handicaps_for_user(uid)
        rounds = {r.date: r for r in get_all_rounds(uid)}
        return float(rounds[probe_date].computed_handicap)

    probe_364 = run_with_gap(364, str(tmp_data_dir / "gap364.db"))
    probe_365 = run_with_gap(365, str(tmp_data_dir / "gap365.db"))
    probe_366 = run_with_gap(366, str(tmp_data_dir / "gap366.db"))

    # Exactly 365 days back is the boundary day of the closed 365-day
    # window -- it must still be INCLUDED, so gap=365 must behave the same
    # as gap=364 (anchor still counted as an LHI candidate).
    assert probe_365 == probe_364, (
        f"gap=365 days (probe HI {probe_365}) diverged from gap=364 days "
        f"(probe HI {probe_364}) -- the 365-day boundary day was wrongly "
        f"excluded from the LHI candidate pool (off-by-one)."
    )
    # 366 days back is genuinely outside the window -- the anchor must age
    # out, producing a different (higher) LHI and thus a different capped
    # result than the 364/365-day cases.
    assert probe_366 != probe_365, (
        "Test fixture did not actually exercise the 365/366-day boundary -- "
        "gap=366 produced the same result as gap=365, so aging-out isn't "
        "meaningfully covered by this fixture."
    )


# --------------------------------------------------------------------------
# WHS Rule 5.7/5.8 -- dashboard hero / rankings must show the CAPPED,
# stored HI, not a fresh raw recalculation (adversary-gate Defect 2)
# --------------------------------------------------------------------------

def _establish_lhi_then_bad_run(user_id=1):
    """Shared fixture builder: 20 stable rounds (differential 10.0, with one
    dip to 8.0) establish LHI=8.0, then a run of very-bad rounds (diff
    100.0) forces the raw HI to spike well past LHI + 5.0 -- guaranteeing
    Rule 5.8's hard cap is active for the most recent round. No course
    record is needed since every round's differential is supplied directly
    (recompute's differential-backfill path only runs for "0"/empty
    differentials)."""
    from store import save_round

    def mk(date_str, diff):
        return {
            "course": "GC", "tees": "W", "total_gross": "85",
            "differential": str(diff), "computed_handicap": "",
            "holes_selection": "all", "entry_mode": "score_only", "holes": {},
        }

    for i in range(20):
        diff = 8.0 if i in (17, 18) else 10.0  # a couple of dips -> LHI = 8.0
        save_round(mk(f"2026-05-{1 + i:02d}", diff), f"2026-05-{1 + i:02d}", 0, user_id)

    bad_dates = [f"2026-05-{21 + i:02d}" for i in range(10)] + [f"2026-06-{1 + i:02d}" for i in range(5)]
    for dstr in bad_dates:
        save_round(mk(dstr, 100.0), dstr, 0, user_id)


def test_dashboard_hero_hi_matches_recompute_when_cap_active(tmp_path, monkeypatch):
    """Adversary-gate Defect 2 regression: once WHS Rule 5.7 (LHI) + Rule
    5.8 (soft/hard cap) are active, the dashboard hero HI panel
    (`_build_profile_context()["panels"]["handicap"]["value"]`) must equal
    the stored, capped `computed_handicap` -- NOT a fresh raw
    `calc_handicap_index(rounds, ...)` recalculation, which would show the
    much higher pre-cap value and desync from every other HI display
    (round detail, trend, round list, rankings)."""
    from main import app, User as UserClass
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, get_user_by_id, get_all_rounds,
        recompute_handicaps_for_user,
    )
    from flask_login import login_user
    from calc.handicap import calc_handicap_index

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

    create_user("q", "Q", "pass1234")
    save_settings({"welcome_shown": True, "include_9hole": True}, user_id=1)

    _establish_lhi_then_bad_run(user_id=1)
    recompute_handicaps_for_user(user_id=1)

    all_rounds = get_all_rounds(user_id=1)
    stored_hi = all_rounds[0].computed_handicap
    assert stored_hi not in (None, "", "0")

    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert raw_hi is not None
    # Sanity: prove the cap is genuinely active for this fixture -- the raw
    # (uncapped) value must differ from the stored (capped) value.
    assert str(raw_hi) != stored_hi, (
        "Fixture did not actually trigger Rule 5.8's cap -- raw and stored "
        "HI coincide, so this test would pass vacuously even with the bug."
    )

    with app.test_request_context():
        user_dict = get_user_by_id(1)
        login_user(UserClass(user_dict))

        from source.routes.dashboard import _build_profile_context
        ctx = _build_profile_context()
        assert ctx is not None, "_build_profile_context returned None (welcome_shown?)"
        dashboard_hi = ctx["panels"]["handicap"]["value"]

    assert dashboard_hi == stored_hi, (
        f"Dashboard hero HI {dashboard_hi!r} diverged from the stored, "
        f"capped recompute HI {stored_hi!r} -- the dashboard must not show "
        f"a fresh raw (uncapped) recalculation once Rule 5.7/5.8 is active."
    )
    assert dashboard_hi != f"{raw_hi:.1f}", (
        f"Dashboard hero HI {dashboard_hi!r} matches the RAW uncapped value "
        f"{raw_hi:.1f} -- this is exactly the Defect 2 bug (dashboard "
        f"showing the pre-cap HI)."
    )


def test_rankings_handicap_stat_matches_recompute_when_cap_active(tmp_data_dir):
    """Adversary-gate Defect 2 regression (rankings.py leaderboard): the
    "handicap" stat in `compute_rankings()` must reflect the stored, capped
    HI -- not a fresh raw `calc_handicap_index()` call -- once Rule 5.7/5.8
    is active, mirroring the dashboard hero fix."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, get_all_rounds, recompute_handicaps_for_user
    from calc.handicap import calc_handicap_index
    from calc.rankings import compute_rankings

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("q", "Q", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    _establish_lhi_then_bad_run(user_id=1)
    recompute_handicaps_for_user(user_id=1)

    all_rounds = get_all_rounds(user_id=1)
    stored_hi = float(all_rounds[0].computed_handicap)
    raw_hi = calc_handicap_index(all_rounds, include_9hole=True)
    assert raw_hi != stored_hi, (
        "Fixture did not actually trigger Rule 5.8's cap -- raw and stored "
        "HI coincide, so this test would pass vacuously even with the bug."
    )

    rankings = compute_rankings(include_9hole=True)
    assert len(rankings) == 1
    board_hi = rankings[0]["stats"]["handicap"]

    assert board_hi == stored_hi, (
        f"Leaderboard handicap stat {board_hi!r} diverged from the stored, "
        f"capped recompute HI {stored_hi!r}."
    )
    assert board_hi != raw_hi, (
        f"Leaderboard handicap stat {board_hi!r} matches the RAW uncapped "
        f"value {raw_hi!r} -- this is the Defect 2 bug in rankings.py."
    )


# --------------------------------------------------------------------------
# WHS Rule 5.9 -- Exceptional Score Reduction (exceptional_reduction)
# --------------------------------------------------------------------------

def test_exceptional_reduction_gap_below_threshold_no_reduction():
    """gap < 7.0 -> no reduction."""
    assert exceptional_reduction(20.0, 13.1) == 0.0  # gap 6.9


def test_exceptional_reduction_gap_exactly_7_reduces_1():
    assert exceptional_reduction(20.0, 13.0) == -1.0  # gap 7.0


def test_exceptional_reduction_gap_9_9_reduces_1():
    assert exceptional_reduction(20.0, 10.1) == -1.0  # gap 9.9


def test_exceptional_reduction_gap_exactly_10_reduces_2():
    assert exceptional_reduction(20.0, 10.0) == -2.0  # gap 10.0


def test_exceptional_reduction_large_gap_reduces_2():
    assert exceptional_reduction(20.0, 5.0) == -2.0  # gap 15.0


def test_exceptional_reduction_negative_gap_no_reduction():
    """differential higher than HI in effect (gap negative) -> no reduction."""
    assert exceptional_reduction(10.0, 15.0) == 0.0


def test_exceptional_reduction_none_hi_no_reduction():
    """No HI established yet -- the round cannot be exceptional."""
    assert exceptional_reduction(None, 5.0) == 0.0


def test_exceptional_reduction_float_epsilon_at_exactly_7():
    """Robustness: `8.2 - 1.2` is a REALISTIC pair of tenth-rounded HIs
    (both are legitimate WHS_HANDICAP display values) whose true gap is
    exactly 7.0, but IEEE 754 binary floating point represents the raw
    subtraction as 6.999999999999999 -- one ULP shy of 7.0. Without
    rounding the gap back to a tenth before the threshold comparison, this
    would be wrongly bucketed as "no reduction" (gap < 7.0) instead of the
    correct -1.0."""
    assert 8.2 - 1.2 != 7.0  # confirms the float representation quirk exists
    assert exceptional_reduction(8.2, 1.2) == -1.0


def test_exceptional_reduction_float_epsilon_at_exactly_10():
    """Robustness: `16.4 - 6.4` is a realistic tenth-rounded HI pair whose
    true gap is exactly 10.0, but raw float subtraction yields
    9.999999999999998 -- which would be wrongly bucketed as -1.0 (gap <
    10.0) instead of the correct -2.0 without rounding the gap first."""
    assert 16.4 - 6.4 != 10.0  # confirms the float representation quirk exists
    assert exceptional_reduction(16.4, 6.4) == -2.0


# --------------------------------------------------------------------------
# WHS Rule 5.9 -- Exceptional Score Reduction integration (recompute)
# --------------------------------------------------------------------------

def _save_diff_rounds(save_round, diffs, user_id=1, start_date="2026-05-01"):
    """Save rounds oldest-first (one per calendar day, starting at
    `start_date`) so `diffs[0]` is played first. Returns the list of
    (date, differential) in the same order."""
    from datetime import date as _date, timedelta as _timedelta

    base = _date.fromisoformat(start_date)
    saved = []
    for i, d in enumerate(diffs):
        date_str = (base + _timedelta(days=i)).isoformat()
        r = {
            "course": "GC", "tees": "W", "total_gross": "85",
            "differential": str(d), "computed_handicap": "",
            "holes_selection": "all", "entry_mode": "score_only", "holes": {},
        }
        save_round(r, date_str, 0, user_id=user_id)
        saved.append((date_str, d))
    return saved


def test_esr_worked_oracle_single_reduction_and_dilution(tmp_data_dir):
    """WHS Rule 5.9 worked oracle from the rule spec:

    20 rounds each differential 20.0 -> HI 20.0 at round 20; LHI 20.0.
    Round 21 differential 12.0: HI_prev 20.0, gap 8.0 -> -1.0 reduction.
    Window(rounds 2..21) = 19x20.0 + 12.0; best-8 = [12, 20x7], avg 19.0;
    minus 1.0 ESR = 18.0; no cap needed (18-20 < 0) -> displayed 18.0.
    Round 22 differential 20.0: HI_prev 18.0, gap 18-20 < 0, not exceptional;
    round 21's 12.0 is still in the window -> still 18.0 displayed.
    Dilution: once round 21 ages out of the most-recent-20-eligible window,
    its reduction stops applying and the HI returns toward 20.0.
    """
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_handicaps_for_user

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("esr1", "ESR1", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    diffs = [20.0] * 20 + [12.0] + [20.0]
    saved = _save_diff_rounds(save_round, diffs, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}

    date_20, _ = saved[19]
    assert rounds_by_date[date_20].computed_handicap == "20.0"

    date_21, _ = saved[20]
    assert rounds_by_date[date_21].computed_handicap == "18.0", (
        f"Round 21 (exceptional, gap 8.0 -> -1.0) expected 18.0, got "
        f"{rounds_by_date[date_21].computed_handicap!r}"
    )

    date_22, _ = saved[21]
    assert rounds_by_date[date_22].computed_handicap == "18.0", (
        "Round 22: not itself exceptional, but round 21's -1.0 reduction "
        "is still active (round 21 is still within the most-recent-20-"
        "eligible window) -- HI should remain 18.0."
    )

    # Dilution: append enough further 20.0-differential rounds that round
    # 21 (the exceptional round) ages out of the most-recent-20-eligible
    # window. Once diluted out, the HI must return to 20.0 (no exceptional
    # score left in the window).
    more_diffs = [20.0] * 20
    _save_diff_rounds(save_round, more_diffs, user_id=1, start_date="2026-05-23")
    recompute_handicaps_for_user(user_id=1)

    all_rounds = get_all_rounds(user_id=1)  # most-recent-first
    most_recent = all_rounds[0]
    assert most_recent.computed_handicap == "20.0", (
        f"After round 21 ages out of the most-recent-20-eligible window, "
        f"the ESR reduction must dilute out and HI must return to 20.0; "
        f"got {most_recent.computed_handicap!r}"
    )


def test_esr_gap_10_or_more_reduces_2(tmp_data_dir):
    """WHS Rule 5.9: gap >= 10.0 -> -2.0 reduction."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_handicaps_for_user

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("esr2", "ESR2", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    # 20 rounds establish HI 20.0, then one round with differential 8.0
    # (gap 20.0 - 8.0 = 12.0 >= 10.0 -> -2.0 reduction).
    diffs = [20.0] * 20 + [8.0]
    saved = _save_diff_rounds(save_round, diffs, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}
    date_21, _ = saved[20]

    # Window(rounds 2..21) = 19x20.0 + 8.0 (20 windowed diffs); best-8 of
    # that sorted window = [8.0, 20.0x7], avg = 148/8 = 18.5 (Rule 5.2a
    # adjustment for 20 diffs is 0.0). HI_prev (round 20's displayed HI) =
    # 20.0, gap = 20.0 - 8.0 = 12.0 >= 10.0 -> -2.0 ESR. 18.5 - 2.0 = 16.5.
    # Rule 5.8 cap: by round 21, acceptable_count >= 20 so LHI is
    # established; LHI = 18.0 here (round 3 -- a 3-differential record of
    # all-20.0s -- dips to 18.0 under Rule 5.2a's -2.0 adjustment for a
    # 3-diff record, the lowest HI ever displayed in this fixture). The
    # cap only limits INCREASES (Rule 5.8): 16.5 - 18.0 = -1.5 is a
    # decrease, so it passes through uncapped -> 16.5.
    assert rounds_by_date[date_21].computed_handicap == "16.5", (
        f"Round 21 (exceptional, gap 12.0 -> -2.0) expected 16.5, got "
        f"{rounds_by_date[date_21].computed_handicap!r}"
    )


def test_esr_cumulative_multiple_exceptional_scores(tmp_data_dir):
    """WHS Rule 5.9: 'Reductions for multiple exceptional scores are
    cumulative.' Two exceptional rounds within the same most-recent-20-
    eligible window must have their reductions summed."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_handicaps_for_user

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("esr3", "ESR3", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    # 20 rounds of 20.0 establish HI 20.0. Round 21: differential 12.0
    # (gap 8.0 -> -1.0). Round 22: differential 20.0 again (HI_prev now
    # 18.0, gap 18-20 < 0, NOT exceptional) so the window's only two
    # exceptional-eligible candidates come from round 21 (-1.0) and a
    # further round 23 with a large gap (-2.0) measured against the then-
    # current HI_prev, giving a cumulative -3.0 while both are in-window.
    diffs = [20.0] * 20 + [12.0, 20.0, 5.0]
    saved = _save_diff_rounds(save_round, diffs, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}
    date_23, _ = saved[22]

    # Before round 23: HI_prev (round 22) = 18.0 (round 21's -1.0 still
    # active). gap = 18.0 - 5.0 = 13.0 >= 10.0 -> -2.0 for round 23.
    # Window(rounds 4..23) = 17x20.0 + 12.0 + 20.0 + 5.0; best-8 =
    # [5.0, 12.0, 20.0x6], avg = (5+12+20*6)/8 = 17.125 -> raw_hi rounds to
    # 17.1 (WHS floors each diff to a tenth before averaging, so this is
    # computed directly against the stored value rather than hand-derived
    # further to avoid float-rounding drift); cumulative active reduction
    # = -1.0 (round21) + -2.0 (round23) = -3.0.
    displayed = float(rounds_by_date[date_23].computed_handicap)

    from calc.handicap import calc_handicap_index
    all_rounds = get_all_rounds(user_id=1)
    idx = [r.date for r in all_rounds].index(date_23)
    raw_hi = calc_handicap_index(all_rounds[idx:], include_9hole=True)

    assert round(raw_hi - 3.0, 1) == displayed, (
        f"Round 23 with two cumulative active exceptional reductions "
        f"(-1.0 + -2.0 = -3.0) expected raw_hi - 3.0 = "
        f"{round(raw_hi - 3.0, 1)}, got {displayed}"
    )


def test_esr_dilution_sharp_boundary_round_40_vs_41(tmp_data_dir):
    """WHS Rule 5.9 dilution boundary, back-to-back: round 21's -1.0
    reduction stays active through round 40 (round 21 is still among the
    most-recent-20-ELIGIBLE differentials for round 40's window -- window
    40-19=21) and is gone by round 41 (window 41-19=22 excludes round 21).
    Verified exactly (not just "eventually diluted") by asserting round 40
    == 18.0 (still reduced) and round 41 == 20.0 (fully diluted) in the
    SAME test, back-to-back."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_handicaps_for_user

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("esr5", "ESR5", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    diffs = [20.0] * 20 + [12.0] + [20.0] * 20  # 41 rounds total
    saved = _save_diff_rounds(save_round, diffs, user_id=1)
    assert len(saved) == 41

    recompute_handicaps_for_user(user_id=1)
    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}

    date_40, _ = saved[39]
    date_41, _ = saved[40]

    assert rounds_by_date[date_40].computed_handicap == "18.0", (
        "Round 40: round 21's -1.0 reduction must still be active (round "
        "21 is still within the most-recent-20-eligible window ending at "
        "round 40)."
    )
    assert rounds_by_date[date_41].computed_handicap == "20.0", (
        "Round 41: round 21 has just aged out of the most-recent-20-"
        "eligible window (window now starts at round 22) -- the reduction "
        "must be fully gone, not partially diluted."
    )


def test_esr_three_simultaneous_exceptional_scores_staggered_aging_out(tmp_data_dir):
    """WHS Rule 5.9: three separate exceptional scores can be simultaneously
    active (cumulative -1.0 each = -3.0) when their windows overlap, and
    then age out one at a time (staggered), decreasing the active sum
    stepwise: -3.0 -> -2.0 -> -1.0 -> 0.0 -- NOT all at once.

    Design: round 21 (diff 12.0, gap 8.0 vs HI_prev 20.0 -> -1.0), round 26
    (diff 10.0, gap 8.0 vs HI_prev 18.0 -> -1.0), round 31 (diff 8.0, gap
    7.3 vs HI_prev 15.8 -> -1.0) -- each independently exceptional against
    the HI *in effect when it was played* (which itself reflects the prior
    rounds' active reductions, per Rule 5.9's own definition). All three
    are within the most-recent-20-eligible window for rounds 31-40 (sum
    -3.0). Round 21 ages out at round 41 (sum -2.0), round 26 ages out at
    round 46 (sum -1.0), round 31 ages out at round 51 (sum 0.0) -- each
    verified as an exact back-to-back boundary, and all displayed values
    below were independently verified by direct execution of the recompute
    algorithm (not hand-derived) to avoid arithmetic-mistake risk on a
    3-way cumulative/dilution interaction."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_handicaps_for_user

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("esr6", "ESR6", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    diffs = (
        [20.0] * 20            # rounds 1-20: establish baseline HI 20.0
        + [12.0] + [20.0] * 4  # round 21 (exceptional), rounds 22-25 filler
        + [10.0] + [20.0] * 4  # round 26 (exceptional), rounds 27-30 filler
        + [8.0]                # round 31 (exceptional) -- 3 simultaneous
        + [20.0] * 25          # rounds 32-56: filler through all 3 dilutions
    )
    assert len(diffs) == 56
    saved = _save_diff_rounds(save_round, diffs, user_id=1)

    recompute_handicaps_for_user(user_id=1)
    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}

    def hi_at(round_num):
        date_str, _ = saved[round_num - 1]
        return rounds_by_date[date_str].computed_handicap

    # Rounds 31-40: all three exceptional reductions active simultaneously
    # (cumulative -3.0 vs. the raw window average). The window-31 raw
    # best-8 average lands exactly on a tenth-tie (16.25); WHS Rule 5.1a's
    # "rounded to the nearest tenth, with .5 rounded upwards" (applied via
    # round_half_up to Rule 5.2a's Handicap Index rounding too) resolves
    # this UP to 16.3, not banker's-rounding's 16.2 -- so 16.3 - 3.0 = 13.3
    # (was "13.2" pre-fix, when round() banker-rounded the 16.25 tie down).
    assert hi_at(31) == "13.3"
    assert hi_at(40) == "13.3"
    # Round 41: round 21 ages out of the window -- sum steps to -2.0. The
    # window-41 raw best-8 average also lands on a tie (17.25 -> 17.3 half
    # up, not 17.2), so 17.3 - 2.0 = 15.3 (was "15.2" pre-fix).
    assert hi_at(41) == "15.3"
    assert hi_at(45) == "15.3"
    # Round 46: round 26 ages out -- sum steps to -1.0. No tie in this
    # window's raw average, so the half-up fix does not change this value.
    assert hi_at(46) == "16.9"
    assert hi_at(50) == "16.9"
    # Round 51: round 31 ages out -- sum steps to 0.0, fully diluted. The
    # window-51 raw best-8 average lands on a tie (18.15 -> 18.2 half up,
    # not 18.1), so this is 18.2 (was "18.1" pre-fix).
    assert hi_at(51) == "18.2"
    assert hi_at(56) == "18.2"


def test_esr_excluded_round_neither_exceptional_nor_consumes_window_slot(tmp_data_dir):
    """WHS Rule 5.9: the ESR window is the SAME most-recent-20-ELIGIBLE
    window `calc_handicap_index` uses -- an excluded round must neither be
    flagged as exceptional itself (it never contributes a differential) NOR
    consume a slot in that window (an excluded round sitting between the
    baseline and the true exceptional round must not shift the eligible-
    round offsets used for the ESR dilution boundary).

    Construction: 20 eligible rounds @20.0, then one EXCLUDED round with an
    extreme differential (99.9 -- would look exceptional if wrongly
    counted, and would poison the window if wrongly included), then the
    TRUE exceptional round (diff 12.0), then 19 more eligible filler
    rounds. If the excluded round wrongly consumed an eligible window slot,
    the ESR dilution boundary would land ONE ROUND EARLIER than in the
    no-exclusion baseline (test_esr_dilution_sharp_boundary_round_40_vs_41:
    boundary at eligible round 40/41). This test proves the boundary is
    unchanged in ELIGIBLE-round terms (still the 40th/41st ELIGIBLE round,
    now landing at PHYSICAL rounds 41/42 because of the one interleaved
    excluded round)."""
    from database import set_db_path, init_db
    from store import (
        create_user, save_settings, save_round, get_all_rounds,
        recompute_handicaps_for_user, set_round_excluded,
    )

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("esr7", "ESR7", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    # physical: 20 eligible @20.0, 1 EXCLUDED @99.9, 1 exceptional @12.0,
    # 19 eligible filler @20.0 -- 41 physical rounds total.
    diffs = [20.0] * 20 + [99.9] + [12.0] + [20.0] * 19
    excluded_physical_idx = 20  # 0-based: the 21st physical round
    saved = _save_diff_rounds(save_round, diffs, user_id=1)
    assert len(saved) == 41

    excluded_date, _ = saved[excluded_physical_idx]
    set_round_excluded(excluded_date, 0, True, user_id=1)

    recompute_handicaps_for_user(user_id=1)
    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}

    exceptional_date, _ = saved[excluded_physical_idx + 1]
    assert rounds_by_date[exceptional_date].computed_handicap == "18.0", (
        "The true exceptional round (diff 12.0, physically right after the "
        "excluded round) must still get its -1.0 Rule 5.9 reduction."
    )
    assert rounds_by_date[excluded_date].excluded is True

    # 3 more eligible filler rounds, appended after the initial 41
    # physical rounds, to land on the eligible-round-40/41 dilution
    # boundary (physically one round LATER than the no-exclusion baseline,
    # since the excluded round occupies a physical slot without consuming
    # an eligible one).
    from datetime import date as _date, timedelta as _timedelta
    next_day = (_date.fromisoformat(saved[-1][0]) + _timedelta(days=1)).isoformat()
    more_saved = _save_diff_rounds(save_round, [20.0] * 3, user_id=1, start_date=next_day)

    recompute_handicaps_for_user(user_id=1)
    rounds_by_date = {r.date: r for r in get_all_rounds(user_id=1)}

    # Physical rounds 41 and 42 (the 40th and 41st ELIGIBLE rounds, since
    # physical round 21 was excluded and consumed no eligible slot) are the
    # dilution boundary -- mirroring the no-exclusion baseline's eligible
    # round 40/41 boundary exactly, just shifted one PHYSICAL position
    # later. Physical round 41 is `saved[40]` (the last of the original 41
    # physical rounds); physical round 42 is `more_saved[0]` (the first of
    # the 3 appended filler rounds).
    date_phys_41, _ = saved[40]
    date_phys_42, _ = more_saved[0]
    assert rounds_by_date[date_phys_41].computed_handicap == "18.0", (
        "Physical round 41 (40th ELIGIBLE round) must still carry the "
        "active -1.0 reduction -- the excluded round must not have pulled "
        "the dilution boundary one round earlier."
    )
    assert rounds_by_date[date_phys_42].computed_handicap == "20.0", (
        "Physical round 42 (41st ELIGIBLE round) is where the exceptional "
        "round finally ages out of the eligible window."
    )


def test_esr_live_save_matches_recompute(tmp_path, monkeypatch):
    """R9 consistency: the live-save path (POST /api/rounds, which internally
    calls `recompute_handicaps_for_user` after every save -- see
    routes/rounds.py) must produce EXACTLY the same ESR-adjusted
    computed_handicap as an explicit `recompute_handicaps_for_user()` call
    over the resulting full history. Exercises the actual production save
    path (not just `store.save_round` in isolation) so ESR is verified
    consistent everywhere it's reachable, per the task's R9 requirement."""
    import main as main_mod
    from main import app, User, limiter, csrf
    from source.routes import register_routes
    from database import set_db_path, init_db
    import store

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

    client = app.test_client()
    store.create_user("esr4", "ESR4", "pass1234")
    resp = client.post("/login", data={"username": "esr4", "password": "pass1234"})
    assert resp.status_code in (302, 200)

    store.save_settings({"include_9hole": True}, user_id=1)

    # slope=113, rating=70.0 -> differential == gross_total - 70.0 exactly,
    # so exceptional-gap arithmetic can be reasoned about directly from the
    # posted gross score.
    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"White": {"slope": "113", "rating": "70.0", "yardage": "6000"}},
    }
    store.save_course(course, "GC")

    # 20 stable rounds (gross 90 -> differential 20.0) establish HI 20.0,
    # then one exceptional round (gross 82 -> differential 12.0, gap 8.0 ->
    # -1.0 reduction).
    grosses = [90] * 20 + [82]
    dates = []
    for i, g in enumerate(grosses):
        day = 1 + i
        date_str = f"2026-05-{day:02d}"
        dates.append(date_str)
        payload = {
            "date": date_str,
            "course": "GC",
            "tees": "White",
            "holes_played": "18",
            "entry_mode": "score_only",
            "gross_total": str(g),
            "notes": "",
            "holes": {},
        }
        resp = client.post("/api/rounds", json=payload)
        assert resp.status_code == 200, resp.get_json()

    live_saved = {r.date: r.computed_handicap for r in store.get_all_rounds(user_id=1)}

    # An explicit full recompute over the exact same final history must
    # agree exactly -- ESR must not diverge between the live-save funnel
    # and a bare recompute pass.
    store.recompute_handicaps_for_user(user_id=1)
    recomputed = {r.date: r.computed_handicap for r in store.get_all_rounds(user_id=1)}

    assert live_saved == recomputed, (
        f"Live-save (POST /api/rounds -> recompute funnel) diverged from "
        f"an explicit recompute_handicaps_for_user() call: "
        f"live={live_saved!r} recomputed={recomputed!r}"
    )
    # Sanity: the exceptional round's -1.0 reduction actually fired via the
    # live-save path (non-vacuous check).
    assert live_saved[dates[-1]] == "18.0", (
        f"Exceptional round (gap 8.0 -> -1.0) expected computed_handicap "
        f"18.0 via live-save, got {live_saved[dates[-1]]!r}"
    )


def test_handicap_trend_from_stored_skips_excluded_rounds():
    """WHS display consistency: the trend must not emit a point for an
    excluded round (it carries a forward-filled computed_handicap but is not
    an acceptable score), matching calc_handicap_trend's eligibility gate."""
    from calc.composite import handicap_trend_from_stored
    from types import SimpleNamespace as NS

    # most-recent-first (contract)
    rounds = [
        NS(date="2026-03-03", computed_handicap="12.0", excluded=False),
        NS(date="2026-03-02", computed_handicap="12.0", excluded=True),   # excluded -> skip
        NS(date="2026-03-01", computed_handicap="11.0", excluded=False),
    ]
    trend = handicap_trend_from_stored(rounds)
    assert trend == [("2026-03-01", 11.0), ("2026-03-03", 12.0)]
    assert all(d != "2026-03-02" for d, _ in trend)


def test_apply_handicap_cap_soft_cap_tie_rounds_half_up():
    """WHS Rule 5.1a half-up applies to the soft-cap output too: the
    0.5*(increase-3.0) term can create a genuine .x5 tie. LHI 10.0, raw 13.1
    -> increase 3.1 -> capped = 10+3+0.5*0.1 = 13.05 -> half-up 13.1 (banker's
    round() would give 13.0)."""
    assert apply_handicap_cap(13.1, 10.0) == 13.1
    # sanity: a non-tie soft-cap still correct
    assert apply_handicap_cap(14.0, 10.0) == 13.5


def test_calc_course_handicap_rounds_half_up_not_bankers():
    """WHS Rule 6.1a: Course Handicap rounds to the nearest whole with .5 UP.
    slope 113 + rating==par makes CH == HI exactly, so a .5 HI is an exact tie."""
    # 10.5 -> 11 (banker's round() gives 10), 2.5 -> 3 (banker's gives 2)
    assert calc_course_handicap(10.5, 72, 113, 72.0) == 11
    assert calc_course_handicap(2.5, 72, 113, 72.0) == 3
    # non-tie unaffected: HI 10, slope 128, CR 71.5, par 72 -> 10*128/113-0.5 = 10.84 -> 11
    assert calc_course_handicap(10.0, 72, 128, 71.5) == 11
    # negative (plus handicap) tie: -0.5 -> -1 (away from zero)
    assert calc_course_handicap(-0.5, 72, 113, 72.0) == -1
