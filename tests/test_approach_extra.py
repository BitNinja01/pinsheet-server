"""Additional pure-function unit tests for calc/approach.py targeting uncovered branches."""
import pytest

from source.models import dict_to_round, HoleData

from calc.approach import (
    calc_fir_percent,
    calc_gir_percent,
    calc_scramble_percent,
    calc_fir_trend,
    calc_gir_trend,
    calc_scramble_trend,
    calc_fir_miss_tendency,
    calc_scoring_by_fairway,
    calc_scoring_by_miss_side,
    calc_gir_by_par_type,
    calc_gir_miss_direction,
    calc_gir_from_fairway_vs_rough,
    calc_scoring_by_gir,
    calc_scramble_by_miss_direction,
    calc_scramble_by_par_type,
    calc_ob_stats,
    per_round_hole_stats,
)


def _round_with_holes(holes, course="Test GC", tees="White", date_="2026-01-01",
                       total_gross="0", holes_selection="all"):
    return dict_to_round({
        "date": date_,
        "course": course,
        "tees": tees,
        "holes_selection": holes_selection,
        "total_gross": total_gross,
        "holes": holes,
    })


# ---- calc_gir_percent: "N" holes excluded from denominator ----

def test_gir_percent_skips_n(make_course):
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "N", "penalties": "0"},
        "2": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},
    }
    r = _round_with_holes(holes)
    assert calc_gir_percent([r]) == 100.0


# ---- no-holes-round skip branches across the simple percent/average helpers ----

def test_fir_gir_scramble_fairway_miss_side_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 FIR hit, GIR hit
        "2": {"gross": "8", "putts": "3", "fairway": "L", "gir": "L", "penalties": "0"},  # par5 FIR miss-L, GIR miss-L, not saved
        "3": {"gross": "4", "putts": "2", "fairway": "R", "gir": "R", "penalties": "0"},  # par4 FIR miss-R, GIR miss-R, saved (gross==par)
        "4": {"gross": "3", "putts": "1", "fairway": "",  "gir": "H", "penalties": "0"},  # par3 excluded from FIR, GIR hit
        "5": {"gross": "5", "putts": "2", "fairway": "N", "gir": "N", "penalties": "0"},  # excluded from FIR (fw N) and GIR (gir N)
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    assert calc_fir_percent([empty_round, r], courses) == pytest.approx(100 / 3)
    assert calc_gir_percent([empty_round, r]) == pytest.approx(50.0)
    assert calc_scramble_percent([empty_round, r], courses) == pytest.approx(50.0)
    fairway_result = calc_scoring_by_fairway([empty_round, r], courses)
    assert fairway_result["hit"] == pytest.approx(1.0)
    assert fairway_result["missed"] == pytest.approx(1.5)
    miss_side_result = calc_scoring_by_miss_side([empty_round, r], courses)
    assert miss_side_result["left"] == pytest.approx(3.0)
    assert miss_side_result["right"] == pytest.approx(0.0)


# ---- trend wrapper functions ----

def test_fir_gir_scramble_trend(make_course):
    courses = make_course()
    older = _round_with_holes(
        {
            "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 fir hit, gir hit
            "2": {"gross": "8", "putts": "3", "fairway": "L", "gir": "L", "penalties": "0"},  # par5 fir miss, gir miss, not saved
        },
        date_="2026-01-01",
    )
    newer = _round_with_holes(
        {
            "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 fir hit, gir hit
            "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par5 fir hit, gir miss, saved
        },
        date_="2026-01-02",
    )
    rounds = [newer, older]
    fir_trend = calc_fir_trend(rounds, courses)
    gir_trend = calc_gir_trend(rounds)
    scramble_trend = calc_scramble_trend(rounds, courses)
    assert [d for d, _ in fir_trend] == ["2026-01-01", "2026-01-02"]
    assert fir_trend[0][1] == pytest.approx(50.0)
    assert fir_trend[1][1] == pytest.approx(100.0)
    assert len(gir_trend) == 2
    assert gir_trend[0] == ("2026-01-01", pytest.approx(50.0))
    assert gir_trend[1] == ("2026-01-02", pytest.approx(50.0))
    assert len(scramble_trend) == 2
    assert scramble_trend[0] == ("2026-01-01", pytest.approx(0.0))
    assert scramble_trend[1] == ("2026-01-02", pytest.approx(100.0))


# ---- calc_fir_miss_tendency: exact L/R split + no-holes skip ----

def test_fir_miss_tendency_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "5", "putts": "2", "fairway": "L", "gir": "H", "penalties": "0"},  # par4 left miss
        "2": {"gross": "6", "putts": "2", "fairway": "R", "gir": "H", "penalties": "0"},  # par5 right miss
        "4": {"gross": "3", "putts": "1", "fairway": "L", "gir": "H", "penalties": "0"},  # par3 excluded
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_fir_miss_tendency([r, empty_round], courses)
    assert result["left"] == pytest.approx(50.0)
    assert result["right"] == pytest.approx(50.0)


# ---- calc_scoring_by_miss_side: exact averages ----

def test_scoring_by_miss_side_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "6", "putts": "2", "fairway": "L", "gir": "H", "penalties": "0"},   # par4 diff=2
        "2": {"gross": "7", "putts": "2", "fairway": "R", "gir": "H", "penalties": "0"},   # par5 diff=2
        "3": {"gross": "5", "putts": "2", "fairway": "OBL", "gir": "H", "penalties": "0"}, # par4 diff=1 (left)
        "4": {"gross": "3", "putts": "1", "fairway": "L", "gir": "H", "penalties": "0"},   # par3 excluded
    }
    r = _round_with_holes(holes)
    result = calc_scoring_by_miss_side([r], courses)
    assert result["left"] == pytest.approx((2 + 1) / 2)
    assert result["right"] == pytest.approx(2.0)


# ---- calc_gir_by_par_type: "N" skip + no-holes skip ----

def test_gir_by_par_type_skips_n_and_empty_rounds(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "N", "penalties": "0"},  # par4, excluded
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5, hit
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_gir_by_par_type([r, empty_round], courses)
    assert result[4] is None
    assert result[5] == 100.0


# ---- calc_gir_miss_direction: all four buckets + no-holes skip ----

def test_gir_miss_direction_all_buckets(make_course):
    holes = {
        "1": {"gross": "5", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "R", "penalties": "0"},
        "3": {"gross": "5", "putts": "2", "fairway": "H", "gir": "S", "penalties": "0"},
        "4": {"gross": "3", "putts": "1", "fairway": "H", "gir": "LO", "penalties": "0"},
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_gir_miss_direction([r, empty_round])
    for k in ("L", "R", "S", "LO"):
        assert result[k] == pytest.approx(25.0)


# ---- calc_gir_from_fairway_vs_rough: rough-hit branch + no-holes skip ----

def test_gir_from_fairway_vs_rough_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # fw hit, gir hit
        "2": {"gross": "6", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # fw hit, gir miss
        "3": {"gross": "4", "putts": "2", "fairway": "L", "gir": "H", "penalties": "0"},  # fw miss, gir hit
        "5": {"gross": "6", "putts": "2", "fairway": "L", "gir": "L", "penalties": "0"},  # fw miss, gir miss
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_gir_from_fairway_vs_rough([r, empty_round], courses)
    assert result["fairway"] == pytest.approx(50.0)
    assert result["rough"] == pytest.approx(50.0)


# ---- calc_scoring_by_gir: exact hit/missed averages + "N" skip + no-holes skip ----

def test_scoring_by_gir_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 diff=1 hit
        "2": {"gross": "7", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par5 diff=2 missed
        "3": {"gross": "4", "putts": "2", "fairway": "H", "gir": "N", "penalties": "0"},  # excluded
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_scoring_by_gir([r, empty_round], courses)
    assert result["hit"] == pytest.approx(1.0)
    assert result["missed"] == pytest.approx(2.0)


# ---- calc_scramble_by_miss_direction: exact save rates for all directions ----

def test_scramble_by_miss_direction_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par4 saved
        "2": {"gross": "7", "putts": "2", "fairway": "H", "gir": "R", "penalties": "0"},  # par5 not saved
        "3": {"gross": "3", "putts": "1", "fairway": "H", "gir": "S", "penalties": "0"},  # par3 saved
        "5": {"gross": "6", "putts": "2", "fairway": "H", "gir": "LO", "penalties": "0"}, # par4 not saved
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_scramble_by_miss_direction([r, empty_round], courses)
    assert result["L"] == pytest.approx(100.0)
    assert result["R"] == pytest.approx(0.0)
    assert result["S"] == pytest.approx(100.0)
    assert result["LO"] == pytest.approx(0.0)


def test_scramble_by_miss_direction_skips_no_gross_and_no_par(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "0", "putts": "0", "fairway": "H", "gir": "L", "penalties": "0"},  # gir in map, no gross
        "99": {"gross": "4", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par not in course
    }
    r = _round_with_holes(holes)
    result = calc_scramble_by_miss_direction([r], courses)
    assert result["L"] is None


# ---- calc_scramble_by_par_type: exact save rates by par bucket ----

def test_scramble_by_par_type_exact(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par4 saved
        "3": {"gross": "5", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par4 missed
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "S", "penalties": "0"},  # par5 saved
        "4": {"gross": "4", "putts": "2", "fairway": "H", "gir": "LO", "penalties": "0"}, # par3 missed
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})
    result = calc_scramble_by_par_type([r, empty_round], courses)
    assert result[4] == pytest.approx(50.0)
    assert result[5] == pytest.approx(100.0)
    assert result[3] == pytest.approx(0.0)


def test_scramble_by_par_type_skips_unknown_par(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "0", "putts": "0", "fairway": "H", "gir": "L", "penalties": "0"},   # no gross -> skip
        "99": {"gross": "4", "putts": "2", "fairway": "H", "gir": "L", "penalties": "0"},  # par not in {3,4,5}
    }
    r = _round_with_holes(holes)
    result = calc_scramble_by_par_type([r], courses)
    assert result[3] is None
    assert result[4] is None
    assert result[5] is None


# ---- calc_ob_stats: OB fairway/gir branches + worst-holes ranking + no-holes skip ----

def test_ob_stats_ob_branches_and_worst_holes(make_course):
    courses = make_course()
    r1 = _round_with_holes(
        {"1": {"gross": "6", "putts": "2", "fairway": "OBL", "gir": "H", "penalties": "1"}},
        date_="2026-01-01",
    )
    r2 = _round_with_holes(
        {"1": {"gross": "7", "putts": "2", "fairway": "OBR", "gir": "OBLO", "penalties": "1"}},
        date_="2026-01-02",
    )
    empty_round = _round_with_holes({}, date_="2026-01-03")

    result = calc_ob_stats([r1, r2, empty_round], courses)

    # empty_round is skipped entirely (continue before appending), so n=2 (r1, r2 only)
    # hole "1" par = 4
    assert result["fir_ob_per_round"] == pytest.approx((1 + 1) / 2)
    assert result["gir_ob_per_round"] == pytest.approx((0 + 1) / 2)
    assert result["fir_ob_avg_vs_par"] == pytest.approx(((6 - 4) + (7 - 4)) / 2)
    assert result["gir_ob_avg_vs_par"] == pytest.approx(7 - 4)
    assert result["gir_clean_avg_vs_par"] == pytest.approx(6 - 4)
    assert result["fir_worst_holes"][0] == ("Test GC", "1", 1.0)


def test_ob_stats_fairway_short_long_ob_counted(make_course):
    """Fairway OBS/OBLO (enterable via shorthand) count as fairway OB (unified _OB_CODES)."""
    courses = make_course()
    r = _round_with_holes(
        {
            "1": {"gross": "6", "putts": "2", "fairway": "OBS", "gir": "H", "penalties": "1"},   # par4
            "2": {"gross": "8", "putts": "2", "fairway": "OBLO", "gir": "H", "penalties": "1"},  # par5
        },
        date_="2026-01-01",
    )
    result = calc_ob_stats([r], courses)
    assert result["fir_ob_per_round"] == pytest.approx(2.0)


# ---- per_round_hole_stats: full function (previously untested) ----

def test_per_round_hole_stats_exact():
    holes = {
        "1": HoleData(gross=4, putts=2, penalties=0, fairway="H", gir="H"),  # par4 fir hit, gir hit
        "2": HoleData(gross=6, putts=3, penalties=0, fairway="L", gir="L"),  # par4 fir miss, gir miss/no updown
        "3": HoleData(gross=3, putts=1, penalties=0, fairway="N", gir="H"),  # par3, fir excluded, gir hit
        "4": HoleData(gross=4, putts=2, penalties=0, fairway="H", gir="S"),  # par4 fir hit, gir miss/updown ok
        "5": HoleData(gross=5, putts=2, penalties=0, fairway="H", gir="N"),  # gir "N" -> excluded from gir stats
    }
    course_holes_data = {"1": {"par": 4}, "2": {"par": 4}, "3": {"par": 3}, "4": {"par": 4}, "5": {"par": 4}}
    result = per_round_hole_stats(holes, course_holes_data)
    assert result["fir_display"] == "3/4"
    assert result["gir_display"] == "2/4"
    assert result["scr_display"] == "1/2"
    assert result["total_putts"] == 10


def test_per_round_hole_stats_empty_holes():
    result = per_round_hole_stats({}, {})
    assert result["fir_display"] is None
    assert result["gir_display"] is None
    assert result["scr_display"] is None
    assert result["total_putts"] == 0


def test_per_round_hole_stats_invalid_par_falls_back_to_99():
    holes = {"1": HoleData(gross=5, putts=2, penalties=0, fairway="H", gir="H")}
    course_holes_data = {"1": {"par": "abc"}}
    result = per_round_hole_stats(holes, course_holes_data)
    assert result["fir_display"] == "1/1"


def test_per_round_hole_stats_skips_invalid_putts():
    h = HoleData(gross=4, putts=2, penalties=0, fairway="H", gir="H")
    h.putts = None  # simulate corrupt data to exercise the except branch
    result = per_round_hole_stats({"1": h}, {"1": {"par": 4}})
    assert result["total_putts"] == 0
