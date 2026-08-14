"""Additional pure-function unit tests for calc/analysis.py targeting uncovered branches."""
import pytest

from source.models import dict_to_round

from calc.analysis import (
    calc_penalty_stats,
    calc_penalty_hole_breakdown,
    calc_momentum_recovery,
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


# ---- calc_penalty_stats: real penalties, no-gross skip, no-holes skip, worst_holes ----

def test_penalty_stats_real_penalties_and_worst_holes(make_course):
    courses = make_course()
    holes_r1 = {
        "1": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "1"},  # par4, penalized
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5, clean
        "3": {"gross": "0", "putts": "0", "fairway": "", "gir": "", "penalties": "0"},    # no gross -> skipped
    }
    holes_r2 = {
        "1": {"gross": "7", "putts": "2", "fairway": "H", "gir": "H", "penalties": "2"},  # par4, penalized
    }
    r1 = _round_with_holes(holes_r1, date_="2026-01-01")
    r2 = _round_with_holes(holes_r2, date_="2026-01-02")
    empty_round = _round_with_holes({}, date_="2026-01-03")

    result = calc_penalty_stats([r1, r2, empty_round], courses)

    # empty_round skipped entirely (no rounds_totals entry) -> denominator is 2
    assert result["rate_per_round"] == pytest.approx((1 + 2) / 2)
    assert result["penalty_avg_vs_par"] == pytest.approx(((6 - 4) + (7 - 4)) / 2)
    assert result["clean_avg_vs_par"] == pytest.approx(5 - 5)
    assert result["worst_holes"][0][0] == "Test GC"
    assert result["worst_holes"][0][1] == "1"
    assert result["worst_holes"][0][2] == pytest.approx((1 + 2) / 2)


def test_penalty_stats_empty_list_returns_none():
    result = calc_penalty_stats([], {})
    assert result["rate_per_round"] is None
    assert result["penalty_avg_vs_par"] is None
    assert result["clean_avg_vs_par"] is None
    assert result["worst_holes"] == []


# ---- calc_momentum_recovery: after_bogey / after_double + all 3 continue branches ----

def test_momentum_recovery_exact_and_skip_branches(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par4 vs_par=2 (double)
        "2": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par5 vs_par=0
        "3": {"gross": "0", "putts": "0", "fairway": "", "gir": "", "penalties": "0"},    # par4, no gross
        "4": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # par3, filler last hole
    }
    r = _round_with_holes(holes)
    empty_round = _round_with_holes({})

    result = calc_momentum_recovery([r, empty_round], courses)

    # hole1 (double, vs_par=2) -> next is hole2 (vs_par=0): after_bogey.append(0), after_double.append(True)
    # hole2 (vs_par=0, not >=1) -> next is hole3, which has no gross -> continue (no append)
    # hole3 (current) has no gross -> continue immediately (no append)
    assert result["after_bogey_avg"] == pytest.approx(0.0)
    assert result["recovery_rate"] == pytest.approx(100.0)


def test_momentum_recovery_no_bogeys_returns_none(make_round, make_course):
    courses = make_course()
    # all holes at par: never triggers vs_par >= 1
    holes = {str(n): {"gross": str(p), "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"}
             for n, p in [(1, 4), (2, 5), (3, 4)]}
    r = _round_with_holes(holes)
    result = calc_momentum_recovery([r], courses)
    assert result["after_bogey_avg"] is None
    assert result["recovery_rate"] is None


def test_momentum_recovery_empty():
    result = calc_momentum_recovery([], {})
    assert result["after_bogey_avg"] is None
    assert result["recovery_rate"] is None


# ---- calc_penalty_hole_breakdown: data-driven clean/penalty/OB classification ----

def test_penalty_hole_breakdown_classifies_and_sums_100(make_course):
    courses = make_course()
    holes = {
        "1": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},    # clean
        "2": {"gross": "6", "putts": "2", "fairway": "H", "gir": "H", "penalties": "1"},    # penalty
        "3": {"gross": "7", "putts": "2", "fairway": "OBL", "gir": "H", "penalties": "2"},  # OB (fairway) — priority over penalty
        "4": {"gross": "5", "putts": "2", "fairway": "H", "gir": "OBS", "penalties": "0"},  # OB (gir)
        "5": {"gross": "0", "putts": "0", "fairway": "", "gir": "", "penalties": "0"},      # no gross -> skipped
    }
    r = _round_with_holes(holes)
    result = calc_penalty_hole_breakdown([r], courses)

    assert result["total_holes"] == 4
    assert result["clean_pct"] == pytest.approx(25.0)
    assert result["penalty_pct"] == pytest.approx(25.0)     # OB hole with penalties counts as OB, not penalty
    assert result["ob_pct"] == pytest.approx(50.0)
    assert result["clean_pct"] + result["penalty_pct"] + result["ob_pct"] == pytest.approx(100.0)


def test_penalty_hole_breakdown_penalty_on_non_ob_fairway_miss(make_course):
    # water hazard / lateral: fairway missed left (not OB), penalty stroke -> classified penalty
    courses = make_course()
    holes = {
        "1": {"gross": "6", "putts": "2", "fairway": "L", "gir": "N", "penalties": "1"},  # penalty
        "2": {"gross": "4", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},  # clean
    }
    r = _round_with_holes(holes)
    result = calc_penalty_hole_breakdown([r], courses)
    assert result["total_holes"] == 2
    assert result["penalty_pct"] == pytest.approx(50.0)
    assert result["ob_pct"] == 0.0


def test_penalty_hole_breakdown_empty_returns_none():
    result = calc_penalty_hole_breakdown([], {})
    assert result["total_holes"] == 0
    assert result["clean_pct"] is None
    assert result["penalty_pct"] is None
    assert result["ob_pct"] is None
