import math
from calc.handicap import (
    calc_hole_scores,
    calc_course_handicap,
    calc_round_dif,
    calc_expected_9hole_dif,
    count_table_n,
    count_table_adjustment,
    calc_effective_diffs,
    get_best_n_rounds,
    calc_handicap_index,
    calc_handicap_trend,
    calc_playing_to_handicap_rate,
    calc_raw_hi,
    apply_handicap_cap,
    WHS_HANDICAP_WINDOW,
)


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
    assert result == round(10 * (140 / 113) + (74 - 72))


def test_calc_round_dif_scratch():
    assert calc_round_dif(113, 72, 72) == 0.0


def test_calc_round_dif_above_rating():
    result = calc_round_dif(128, 85, 71.5)
    assert result == round((113 / 128) * (85 - 71.5), 1)


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
