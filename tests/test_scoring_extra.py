"""Additional pure-function unit tests for calc/scoring.py targeting uncovered branches."""
from datetime import date, timedelta

import pytest

from source.models import dict_to_round, dict_to_course

from calc.scoring import (
    calc_trend,
    calc_pob_trend,
    calc_clean_card_trend,
    calc_big_number_trend,
    calc_scoring_avg_by_par_type,
    calc_par_or_better_percent,
    calc_score_distribution,
    calc_big_number_rate,
    calc_scoring_consistency,
    calc_score_components,
    calc_per_hole_stats,
    calc_historical_window,
    calc_last_year_handicap,
    calc_round_vs_par,
    calc_avg_vs_par,
    calc_round_vs_rating,
    calc_avg_vs_rating,
    calc_penalties_per_round,
    calc_per_round_average,
    calc_hole_percentage,
    stat_delta,
)


def _round_with_holes(holes, course="Test GC", tees="White", date_="2026-01-01",
                       total_gross="0", holes_selection="all", computed_handicap=""):
    return dict_to_round({
        "date": date_,
        "course": course,
        "tees": tees,
        "holes_selection": holes_selection,
        "total_gross": total_gross,
        "computed_handicap": computed_handicap,
        "holes": holes,
    })


# ---- trend wrapper functions (calc_trend body + wrappers) ----

def test_pob_trend_orders_chronologically(make_round, make_course):
    courses = make_course()
    rounds = [
        make_round(gross=85, date="2026-01-03"),
        make_round(gross=80, date="2026-01-02"),
        make_round(gross=75, date="2026-01-01"),
    ]
    trend = calc_pob_trend(rounds, courses)
    assert [d for d, _ in trend] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert all(0 <= v <= 100 for _, v in trend)


def test_clean_card_and_big_number_trend(make_course):
    courses = make_course()
    older = _round_with_holes(
        {
            "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=0
            "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 diff=0
        },
        date_="2026-01-01",
    )
    newer = _round_with_holes(
        {
            "1": {"gross": "8", "putts": "3", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=4, clean-breaking + big number (boundary)
            "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 diff=0
        },
        date_="2026-01-02",
    )
    rounds = [newer, older]
    clean_trend = calc_clean_card_trend(rounds, courses)
    big_trend = calc_big_number_trend(rounds, courses)
    assert len(clean_trend) == 2
    assert len(big_trend) == 2
    assert clean_trend[0] == ("2026-01-01", pytest.approx(100.0))
    assert clean_trend[1] == ("2026-01-02", pytest.approx(0.0))
    assert big_trend[0] == ("2026-01-01", pytest.approx(0.0))
    assert big_trend[1] == ("2026-01-02", pytest.approx(50.0))


# ---- iter_holes / per-round "no holes" skip branches ----

def test_per_hole_stats_skips_rounds_without_holes(make_course):
    courses = make_course()
    empty_round = _round_with_holes({})
    result = calc_per_hole_stats([empty_round], courses, "Test GC", 1)
    assert result["rounds_played"] == 0
    assert result["avg_score"] is None


def test_avg_by_par_type_skips_empty_holes_round(make_course):
    courses = make_course()
    empty_round = _round_with_holes({})
    holes = {
        "1": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4
        "3": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4
        "4": {"gross": "3", "putts": "1", "fairway": "",  "gir": "H", "penalties": "0"},  # par3
        "8": {"gross": "5", "putts": "2", "fairway": "",  "gir": "H", "penalties": "0"},  # par3
        "2": {"gross": "7", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5
    }
    normal = _round_with_holes(holes)
    result = calc_scoring_avg_by_par_type([empty_round, normal], courses)
    assert result[4] == pytest.approx(5.0)
    assert result[3] == pytest.approx(4.0)
    assert result[5] == pytest.approx(7.0)


def test_par_or_better_percent_skips_empty_holes_round(make_course):
    courses = make_course()
    empty_round = _round_with_holes({})
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 gross==par -> par-or-better
        "2": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 gross>par -> worse
    }
    normal = _round_with_holes(holes)
    result = calc_par_or_better_percent([empty_round, normal], courses)
    assert result == pytest.approx(50.0)


def test_par_or_better_percent_exact_boundary(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4, gross==par -> par-or-better (boundary)
        "3": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4, gross>par -> worse
        "2": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5, gross<par -> par-or-better
        "4": {"gross": "4", "putts": "1", "fairway": "",  "gir": "H", "penalties": "0"},  # par3, gross>par -> worse
    }
    r = _round_with_holes(holes)
    result = calc_par_or_better_percent([r], courses)
    # 2 of 4 holes qualify: hole "1" (gross==par, boundary) and hole "2" (gross<par)
    assert result == pytest.approx(50.0)


def test_calc_trend_filter_fn_excludes_rounds(make_round, make_course):
    courses = make_course()
    rounds = [
        make_round(gross=80, holes_selection="front", date="2026-01-02"),
        make_round(gross=72, holes_selection="all", date="2026-01-01"),
    ]
    trend = calc_trend(
        rounds, calc_par_or_better_percent, courses,
        filter_fn=lambda r: r.holes_selection == "all",
    )
    assert len(trend) == 1
    assert trend[0][0] == "2026-01-01"


# ---- calc_score_distribution: all six buckets + both skip branches ----

def test_score_distribution_all_buckets(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "2", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=-2 eagle
        "2": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 diff=-1 birdie
        "3": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=0 par
        "4": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par3 diff=1 bogey
        "5": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=2 double
        "6": {"gross": "9", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 diff=4 triple_plus
        "7": {"gross": "0", "putts": "0", "fairway": "", "gir": "", "penalties": "0"},    # no gross -> skipped
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_score_distribution([r, empty_round], courses)
    for k in ("eagle", "birdie", "par", "bogey", "double", "triple_plus"):
        assert result[k] == pytest.approx(100 / 6)


# ---- calc_big_number_rate: hit + skip branches ----

def test_big_number_rate_counts_and_skips(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "8", "putts": "3", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=4 -> hit
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 diff=0 -> not hit
        "3": {"gross": "0", "putts": "0", "fairway": "", "gir": "", "penalties": "0"},    # no gross -> skipped
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_big_number_rate([r, empty_round], courses)
    assert result == pytest.approx(50.0)


# ---- calc_scoring_consistency: all continue branches ----

def test_consistency_skips_zero_9hole_missing_course_and_no_par(make_round, make_course):
    courses = make_course()
    zero_round = make_round(gross=0)
    nine_hole_round = make_round(gross=45, holes_selection="front")
    no_course_round = make_round(gross=80, course="Unknown GC")
    normal1 = make_round(gross=72)
    normal2 = make_round(gross=74)
    result = calc_scoring_consistency(
        [zero_round, nine_hole_round, no_course_round, normal1, normal2], courses
    )
    # only normal1 (diff 0) and normal2 (diff 2) count -> mean=1, variance=1, std=1.0
    assert result == pytest.approx(1.0)


def test_consistency_skips_course_without_par(make_round):
    courses = {"NoParGC": dict_to_course("NoParGC", {"par": "", "holes": {}, "tees": {}})}
    r1 = make_round(gross=80, course="NoParGC")
    r2 = make_round(gross=82, course="NoParGC")
    assert calc_scoring_consistency([r1, r2], courses) is None


# ---- calc_score_components: no-holes skip and missing-field skip ----

def test_score_components_skips_no_holes_round_and_missing_putts(make_course):
    courses = make_course()
    empty_round = _round_with_holes({})
    holes = {"1": {"gross": "4", "putts": "0", "fairway": "H", "gir": "H", "penalties": "0"}}
    r = _round_with_holes(holes)
    result = calc_score_components([empty_round, r], courses)
    assert result["approach"] is None
    assert result["scramble"] is None
    assert result["putting"] is None


# ---- calc_per_hole_stats: gir=="N", gir="R" branch, penalties, handicap exception ----

def test_per_hole_stats_gir_n_and_r_and_penalties(make_round, make_course):
    courses = make_course()
    r1 = make_round(gross=80)
    r2 = make_round(gross=82)
    r1.holes["1"].gir = "N"
    r2.holes["1"].gir = "R"
    r2.holes["1"].penalties = 2

    result = calc_per_hole_stats([r1, r2], courses, "Test GC", 1)
    assert result["gir_pct"] == 0.0
    assert result["gir_miss_r_pct"] == 100.0
    assert result["avg_penalties"] == pytest.approx(2.0)


def test_per_hole_stats_handicap_calc_handles_invalid_slope(make_round):
    course_dict = {
        "par": "72",
        "holes": {"1": {"par": 4, "hole_index": 5}},
        "tees": {"White": {"slope": "invalid", "rating": "70", "yardage": "6000"}},
    }
    courses = {"Test GC": dict_to_course("Test GC", course_dict)}
    r = make_round(gross=80, course="Test GC")
    result = calc_per_hole_stats([r], courses, "Test GC", 1, handicap_index=10.5)
    assert result["rounds_played"] == 1
    assert result["expected"] is None


# ---- calc_historical_window ----

def test_historical_window_filters_by_date(make_round):
    rounds = [make_round(date=f"2026-01-{d:02d}") for d in range(1, 26)]
    window = calc_historical_window(rounds, "2026-01-15")
    assert all(r.date <= "2026-01-15" for r in window)
    assert len(window) == 15


def test_historical_window_caps_at_20(make_round):
    rounds = [make_round(date=f"2026-01-{d:02d}") for d in range(1, 26)]
    window = calc_historical_window(rounds, "2026-12-31")
    assert len(window) == 20
    assert window[0].date == "2026-01-01"
    assert window[-1].date == "2026-01-20"


# ---- calc_last_year_handicap ----

def test_last_year_handicap_needs_3_rounds(make_round):
    assert calc_last_year_handicap([make_round(), make_round()], True) is None


def test_last_year_handicap_skips_missing_and_bad_dates(make_round):
    target = date.today() - timedelta(days=365)
    good_date = (target + timedelta(days=5)).isoformat()
    r_valid = make_round(date=good_date, computed_handicap="12.3")
    r_missing_date = make_round(date="", computed_handicap="9.9")
    r_bad_date = make_round(date="not-a-date", computed_handicap="9.9")
    result = calc_last_year_handicap([r_valid, r_missing_date, r_bad_date], True)
    assert result == pytest.approx(12.3)


def test_last_year_handicap_beyond_60_days_returns_none(make_round):
    target = date.today() - timedelta(days=365)
    far_date = (target + timedelta(days=100)).isoformat()
    rounds = [make_round(date=far_date, computed_handicap="10.0") for _ in range(3)]
    assert calc_last_year_handicap(rounds, True) is None


def test_last_year_handicap_zero_handicap_returns_none(make_round):
    target = date.today() - timedelta(days=365)
    rounds = [
        make_round(date=(target - timedelta(days=200)).isoformat(), computed_handicap="15.0"),
        make_round(date=(target - timedelta(days=100)).isoformat(), computed_handicap="15.0"),
        make_round(date=target.isoformat(), computed_handicap="0"),
    ]
    assert calc_last_year_handicap(rounds, True) is None


def test_last_year_handicap_invalid_float_returns_none(make_round):
    target = date.today() - timedelta(days=365)
    rounds = [make_round(date=target.isoformat(), computed_handicap="abc") for _ in range(3)]
    assert calc_last_year_handicap(rounds, True) is None


def test_last_year_handicap_valid_returns_float(make_round):
    target = date.today() - timedelta(days=365)
    rounds = [
        make_round(date=(target - timedelta(days=i)).isoformat(), computed_handicap=str(10 + i))
        for i in range(3)
    ]
    result = calc_last_year_handicap(rounds, True)
    assert result == pytest.approx(10.0)


# ---- calc_round_vs_par / calc_avg_vs_par ----

def test_round_vs_par_normal(make_round, make_course):
    courses = make_course()
    r = make_round(gross=80)
    # course par pattern: 4 holes par3 (12) + 5 holes par5 (25) + 9 holes par4 (36) = 73
    assert calc_round_vs_par(r, courses) == 80 - 73


def test_round_vs_par_zero_total_returns_none(make_round, make_course):
    courses = make_course()
    r = make_round(gross=0)
    assert calc_round_vs_par(r, courses) is None


def test_round_vs_par_no_actual_par_returns_none(make_round):
    r = make_round(gross=80, course="Unknown GC")
    assert calc_round_vs_par(r, {}) is None


def test_avg_vs_par_normal_and_skips(make_round, make_course):
    courses = make_course()
    zero_round = make_round(gross=0)
    r1 = make_round(gross=80)
    r2 = make_round(gross=75)
    no_par_round = make_round(gross=80, course="Unknown GC")
    result = calc_avg_vs_par([zero_round, r1, r2, no_par_round], courses)
    assert result == pytest.approx(((80 - 73) + (75 - 73)) / 2)


def test_avg_vs_par_empty():
    assert calc_avg_vs_par([], {}) is None


# ---- calc_round_vs_rating / calc_avg_vs_rating ----

def test_round_vs_rating_all(make_round, make_course):
    courses = make_course()
    r = make_round(gross=80, holes_selection="all")
    assert calc_round_vs_rating(r, courses) == pytest.approx(80 - 71.5)


def test_round_vs_rating_front_back_missing_field_returns_none(make_round, make_course):
    """When the tee carries no front/back rating, front/back rounds can't be rated -> None."""
    courses = make_course()
    r_front = make_round(gross=40, holes_selection="front")
    r_back = make_round(gross=40, holes_selection="back")
    assert calc_round_vs_rating(r_front, courses) is None
    assert calc_round_vs_rating(r_back, courses) is None


def test_round_vs_rating_front_back_uses_mapped_9hole_rating():
    """When the course DOES store front_rating/back_rating, they map onto TeeData
    and drive the vs-rating value for 9-hole rounds (regression for the previously
    unmapped field bug)."""
    course_dict = {
        "par": "72",
        "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
        "tees": {"White": {
            "slope": 128, "rating": 71.5, "yardage": "6200",
            "front_rating": 35.8, "back_rating": 36.1,
        }},
    }
    courses = {"Test GC": dict_to_course("Test GC", course_dict)}
    r_front = dict_to_round({
        "date": "2026-05-15", "course": "Test GC", "tees": "White",
        "holes_selection": "front", "total_gross": "40", "holes": {},
    })
    r_back = dict_to_round({
        "date": "2026-05-15", "course": "Test GC", "tees": "White",
        "holes_selection": "back", "total_gross": "41", "holes": {},
    })
    assert calc_round_vs_rating(r_front, courses) == pytest.approx(40 - 35.8)
    assert calc_round_vs_rating(r_back, courses) == pytest.approx(41 - 36.1)


def test_round_vs_rating_zero_total_returns_none(make_round, make_course):
    courses = make_course()
    r = make_round(gross=0)
    assert calc_round_vs_rating(r, courses) is None


def test_round_vs_rating_missing_tee_returns_none(make_round, make_course):
    courses = make_course()
    r = make_round(gross=80, tees="Blue")
    assert calc_round_vs_rating(r, courses) is None


def test_avg_vs_rating_normal_and_skips(make_round, make_course):
    courses = make_course()
    zero_round = make_round(gross=0)
    r1 = make_round(gross=80)
    r2 = make_round(gross=75)
    missing_tee_round = make_round(gross=80, tees="Blue")
    result = calc_avg_vs_rating([zero_round, r1, r2, missing_tee_round], courses)
    assert result == pytest.approx(((80 - 71.5) + (75 - 71.5)) / 2)


def test_avg_vs_rating_empty():
    assert calc_avg_vs_rating([], {}) is None


# ---- calc_penalties_per_round ----

def test_penalties_per_round_normal(make_round):
    r1 = make_round(gross=80, penalties=3)
    r2 = make_round(gross=80, penalties=1)
    assert calc_penalties_per_round([r1, r2]) == pytest.approx(2.0)


def test_penalties_per_round_skips_no_holes_round(make_round):
    empty_round = _round_with_holes({})
    r1 = make_round(gross=80, penalties=2)
    assert calc_penalties_per_round([empty_round, r1]) == pytest.approx(2.0)


def test_penalties_per_round_empty():
    assert calc_penalties_per_round([]) is None


# ---- calc_per_round_average / calc_hole_percentage ----

def test_per_round_average_exact(make_course):
    courses = make_course()
    holes = {"1": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"}}  # par4 diff=2
    r = _round_with_holes(holes)
    result = calc_per_round_average([r], courses, lambda g, p: g - p >= 1)
    assert result == pytest.approx(1.0)


def test_per_round_average_empty_rounds_returns_none():
    assert calc_per_round_average([], {}, lambda g, p: True) is None


def test_hole_percentage_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=2 qualifies
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 diff=0
    }
    r = _round_with_holes(holes)
    result = calc_hole_percentage([r], courses, lambda g, p: g - p >= 1)
    assert result == pytest.approx(50.0)


def test_hole_percentage_empty():
    assert calc_hole_percentage([], {}, lambda g, p: True) is None


# ---- stat_delta ----

def test_stat_delta_none_or_equal_values():
    assert stat_delta(None, 80) == ("", "—", "")
    assert stat_delta(80, None) == ("", "—", "")
    assert stat_delta(80, 80) == ("", "—", "")


def test_stat_delta_higher_better_improvement():
    cls, text, cell_cls = stat_delta(85, 80, higher_better=True)
    assert cls == "is-up"
    assert cell_cls == "is-improved"
    assert text == "+5.0 vs L20"


def test_stat_delta_higher_better_decline():
    cls, text, cell_cls = stat_delta(75, 80, higher_better=True)
    assert cls == "is-down"
    assert cell_cls == "is-declined"
    assert text == "-5.0 vs L20"


def test_stat_delta_lower_better_improvement_with_precision_and_suffix():
    cls, text, cell_cls = stat_delta(75, 80, higher_better=False, precision=0, suffix=" pts")
    assert cls == "is-up"
    assert cell_cls == "is-improved"
    assert text == "-5 pts vs L20"
