import math
from calc.handicap import (
    calc_hole_scores,
    calc_course_handicap,
    calc_round_dif,
    calc_expected_9hole_dif,
    count_table_n,
    calc_effective_diffs,
    get_best_n_rounds,
    calc_handicap_index,
    calc_handicap_trend,
    calc_playing_to_handicap_rate,
    calc_raw_hi,
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
