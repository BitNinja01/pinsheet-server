import pytest

from calc.milestones import (
    calc_best_single_round,
    calc_best_3round_stretch,
    calc_biggest_improvement,
    calc_first_score_milestone,
    calc_first_hi_milestone,
    calc_score_breakdown,
    calc_hole_in_ones,
    calc_most_played_course,
    calc_penalty_free_rounds,
    calc_best_gir_round,
    calc_best_fir_round,
)


class TestBestSingleRound:
    def test_empty(self):
        assert calc_best_single_round([]) is None

    def test_best_round_by_differential(self, make_round):
        rounds = [
            make_round(differential="15.0", date="2026-06-01"),
            make_round(differential="10.0", date="2026-06-02"),
            make_round(differential="12.0", date="2026-06-03"),
        ]
        result = calc_best_single_round(rounds)
        assert result is not None
        assert result.differential == "10.0"

    def test_skips_missing_differential(self, make_round):
        r = make_round()
        r.differential = None
        result = calc_best_single_round([r])
        assert result is None


class TestBest3RoundStretch:
    def test_empty(self):
        assert calc_best_3round_stretch([]) is None

    def test_less_than_3_rounds(self, make_round):
        rounds = [make_round(), make_round()]
        assert calc_best_3round_stretch(rounds) is None

    def test_best_stretch(self, make_round):
        rounds = [
            make_round(differential="15.0", date="2026-06-01"),
            make_round(differential="10.0", date="2026-06-02"),
            make_round(differential="12.0", date="2026-06-03"),
            make_round(differential="20.0", date="2026-06-04"),
            make_round(differential="18.0", date="2026-06-05"),
        ]
        result = calc_best_3round_stretch(rounds)
        assert result is not None
        avg, start, end = result
        expected_avg = (15.0 + 10.0 + 12.0) / 3
        assert avg == expected_avg

    def test_sorts_by_date(self, make_round):
        rounds = [
            make_round(differential="12.0", date="2026-06-03"),
            make_round(differential="15.0", date="2026-06-01"),
            make_round(differential="10.0", date="2026-06-02"),
        ]
        result = calc_best_3round_stretch(rounds)
        assert result is not None
        avg, start, end = result
        expected = (15.0 + 10.0 + 12.0) / 3
        assert avg == expected
        assert start == "2026-06-01"
        assert end == "2026-06-03"


class TestBiggestImprovement:
    def test_empty(self):
        assert calc_biggest_improvement([]) is None

    def test_biggest_gap(self, make_round):
        rounds = [
            make_round(differential="20.0", computed_handicap="25.0", date="2026-06-01"),
            make_round(differential="10.0", computed_handicap="18.0", date="2026-06-02"),
            make_round(differential="22.0", computed_handicap="15.0", date="2026-06-03"),
        ]
        result = calc_biggest_improvement(rounds)
        assert result is not None
        gap, r = result
        assert r.differential == "10.0"
        assert gap == 8.0  # 18.0 - 10.0

    def test_only_positive_gaps(self, make_round):
        rounds = [
            make_round(differential="25.0", computed_handicap="10.0", date="2026-06-01"),
        ]
        result = calc_biggest_improvement(rounds)
        assert result is None  # gap is -15, not positive

    def test_skips_missing_data(self, make_round):
        r = make_round()
        r.differential = None
        assert calc_biggest_improvement([r]) is None


class TestFirstScoreMilestone:
    def test_empty(self):
        assert calc_first_score_milestone([], []) is None

    def test_already_broken_all(self, make_round):
        pre = [make_round(gross=70, date="2026-01-01")]
        season = [make_round(gross=72, date="2026-06-01")]
        assert calc_first_score_milestone(season, pre) is None

    def test_new_milestone_in_season(self, make_round):
        pre = [make_round(gross=100, date="2026-01-01")]
        season = [make_round(gross=89, date="2026-06-01")]
        result = calc_first_score_milestone(season, pre)
        assert result is not None
        threshold, r = result
        assert threshold == 90
        assert r.date == "2026-06-01"

    def test_skips_partial_rounds(self, make_round):
        season = [make_round(gross=89, holes_selection="front", date="2026-06-01")]
        pre = [make_round(gross=100, date="2026-01-01")]
        result = calc_first_score_milestone(season, pre)
        assert result is None


class TestFirstHiMilestone:
    def test_empty(self):
        assert calc_first_hi_milestone([], []) is None

    def test_already_broken_all(self, make_round):
        pre = [make_round(computed_handicap="5.0", date="2026-01-01")]
        season = [make_round(computed_handicap="10.0", date="2026-06-01")]
        assert calc_first_hi_milestone(season, pre) is None

    def test_new_hi_milestone(self, make_round):
        pre = [make_round(computed_handicap="20.0", date="2026-01-01")]
        season = [make_round(computed_handicap="15.0", date="2026-06-01")]
        result = calc_first_hi_milestone(season, pre)
        assert result is not None
        threshold, r = result
        # eligible starts at 20 (first not already broken), function returns threshold-1
        assert threshold == 15
        assert r.date == "2026-06-01"

    def test_skips_missing_data(self, make_round):
        r = make_round()
        r.computed_handicap = None
        assert calc_first_hi_milestone([r], [r]) is None


class TestScoreBreakdown:
    def test_empty(self):
        result = calc_score_breakdown([], {})
        for k in ("eagle", "birdie", "par", "bogey", "double", "triple_plus"):
            assert result[k] == 0

    def test_counts_correctly(self, make_round, make_course):
        courses = make_course()
        r = make_round(gross=80)
        pars = {1: 4, 2: 5, 3: 4, 4: 3, 5: 4, 6: 5,
                7: 4, 8: 3, 9: 4, 10: 5, 11: 4, 12: 3,
                13: 4, 14: 5, 15: 4, 16: 3, 17: 4, 18: 5}
        for hn in r.holes:
            r.holes[hn].gross = pars[int(hn)]
        r.holes["1"].gross = 2  # eagle on par 4
        r.holes["2"].gross = 4  # birdie on par 5
        r.holes["4"].gross = 4  # bogey on par 3
        r.holes["5"].gross = 6  # double on par 4
        r.holes["6"].gross = 9  # triple+ on par 5
        rounds = [r]
        result = calc_score_breakdown(rounds, courses)
        assert result["eagle"] == 1
        assert result["birdie"] == 1
        assert result["par"] == 13
        assert result["bogey"] == 1
        assert result["double"] == 1
        assert result["triple_plus"] == 1


class TestHoleInOnes:
    def test_empty(self):
        assert calc_hole_in_ones([], {}) == 0

    def test_no_aces(self, make_round, make_course):
        courses = make_course()
        assert calc_hole_in_ones([make_round()], courses) == 0

    def test_one_ace(self, make_round, make_course):
        courses = make_course()
        r = make_round()
        r.holes["4"].gross = 1  # par 3
        assert calc_hole_in_ones([r], courses) == 1


class TestBestGirRound:
    def test_empty(self):
        assert calc_best_gir_round([]) is None

    def test_most_gir(self, make_round):
        rounds = [
            make_round(gir_hits=10, date="2026-06-01"),
            make_round(gir_hits=14, date="2026-06-02"),
            make_round(gir_hits=8, date="2026-06-03"),
        ]
        result = calc_best_gir_round(rounds)
        assert result is not None
        r, count = result
        assert count == 14

    def test_no_gir_returns_none(self, make_round):
        r = make_round(gir_hits=0)
        assert calc_best_gir_round([r]) is None


class TestBestFirRound:
    def test_empty(self):
        assert calc_best_fir_round([], {}) is None

    def test_most_fir(self, make_round, make_course):
        courses = make_course()
        rounds = [
            make_round(fir_hits=5, date="2026-06-01"),
            make_round(fir_hits=10, date="2026-06-02"),
        ]
        result = calc_best_fir_round(rounds, courses)
        assert result is not None
        r, count = result
        assert count == 10

    def test_no_fir_returns_none(self, make_round, make_course):
        courses = make_course()
        r = make_round(fir_hits=0)
        assert calc_best_fir_round([r], courses) is None


class TestMostPlayedCourse:
    def test_empty(self):
        assert calc_most_played_course([]) is None

    def test_most_played(self, make_round):
        rounds = (
            [make_round(course="Home GC", differential="10.0") for _ in range(3)]
            + [make_round(course="Away GC", differential="15.0") for _ in range(2)]
        )
        result = calc_most_played_course(rounds)
        assert result is not None
        name, count, avg = result
        assert name == "Home GC"
        assert count == 3
        assert avg > 0

    def test_tie_resolved_by_lowest_avg_diff(self, make_round):
        rounds = (
            [make_round(course="Course A", differential="12.0") for _ in range(2)]
            + [make_round(course="Course B", differential="18.0") for _ in range(2)]
        )
        result = calc_most_played_course(rounds)
        assert result is not None
        name, count, avg = result
        assert name == "Course A"


class TestPenaltyFreeRounds:
    def test_empty(self):
        assert calc_penalty_free_rounds([]) == 0

    def test_all_penalty_free(self, make_round):
        rounds = [make_round(penalties=0) for _ in range(3)]
        assert calc_penalty_free_rounds(rounds) == 3

    def test_some_with_penalties(self, make_round):
        with_pen = make_round(penalties=2)
        without = make_round(penalties=0)
        assert calc_penalty_free_rounds([with_pen, without]) == 1

    def test_no_holes_skipped(self, make_round):
        r = make_round()
        r.holes = {}
        assert calc_penalty_free_rounds([r]) == 0
