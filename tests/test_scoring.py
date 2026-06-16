from calc.scoring import (
    calc_scoring_average,
    calc_scoring_trend,
    calc_scoring_avg_by_par_type,
    calc_par_or_better_percent,
    calc_score_distribution,
    calc_big_number_rate,
    calc_clean_card_percent,
    calc_scoring_consistency,
    calc_score_components,
    calc_per_hole_stats,
)
from calc.analysis import (
    calc_penalty_stats,
    calc_momentum_recovery,
)
from calc.milestones import (
    calc_personal_bests,
    calc_nemesis_best_holes,
)


def test_scoring_average_empty():
    assert calc_scoring_average([]) is None


def test_scoring_average_9hole_excluded(make_round):
    rounds = [make_round(gross=45, holes_selection="front")]
    assert calc_scoring_average(rounds) is None


def test_scoring_average_normal(make_round):
    rounds = [make_round(gross=g) for g in (72, 80, 85)]
    avg = calc_scoring_average(rounds)
    assert avg == (72 + 80 + 85) / 3


def test_scoring_average_skips_zero_total(make_round):
    rounds = [make_round(gross=80), make_round(gross=0)]
    rounds[1].total_gross = "0"
    avg = calc_scoring_average(rounds)
    assert avg == 80.0


def test_scoring_trend_empty():
    assert calc_scoring_trend([]) == []


def test_scoring_trend_returns_pairs(make_round):
    rounds = [make_round(gross=g, date=f"2026-01-{d:02d}")
              for d, g in [(3, 82), (2, 78), (1, 80)]]
    trend = calc_scoring_trend(rounds)
    assert len(trend) == 3
    assert trend[0] == ("2026-01-01", 80)
    assert trend[2] == ("2026-01-03", 82)


def test_avg_by_par_type_empty():
    result = calc_scoring_avg_by_par_type([], {})
    for p in (3, 4, 5):
        assert result[p] is None


def test_avg_by_par_type_normal(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    result = calc_scoring_avg_by_par_type(rounds, courses)
    for p in (3, 4, 5):
        assert result[p] is not None
        assert 2 < result[p] < 8


def test_pob_percent_empty():
    assert calc_par_or_better_percent([], {}) is None


def test_pob_percent_normal(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    result = calc_par_or_better_percent(rounds, courses)
    assert result is not None
    assert 0 <= result <= 100


def test_score_dist_empty():
    result = calc_score_distribution([], {})
    for k in result:
        assert result[k] is None


def test_score_dist_normal(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    result = calc_score_distribution(rounds, courses)
    total = sum(v for v in result.values() if v is not None)
    if total > 0:
        assert abs(total - 100) < 1


def test_big_number_rate_empty():
    assert calc_big_number_rate([], {}) is None


def test_big_number_rate_normal(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    result = calc_big_number_rate(rounds, courses)
    assert result is not None
    assert 0 <= result <= 100


def test_clean_card_empty():
    assert calc_clean_card_percent([], {}) is None


def test_clean_card_9hole_excluded(make_round, make_course):
    rounds = [make_round(gross=45, holes_selection="front")]
    courses = make_course()
    assert calc_clean_card_percent(rounds, courses) is None


def test_clean_card_all_clean(make_round, make_course):
    rounds = [make_round(gross=72)]
    courses = make_course()
    result = calc_clean_card_percent(rounds, courses)
    assert result is not None
    assert 0 <= result <= 100


def test_consistency_empty():
    assert calc_scoring_consistency([], {}) is None


def test_consistency_needs_two_rounds(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    assert calc_scoring_consistency(rounds, courses) is None


def test_consistency_normal(make_round, make_course):
    rounds = [make_round(gross=g) for g in (72, 73, 72, 74, 72)]
    courses = make_course()
    result = calc_scoring_consistency(rounds, courses)
    assert result is not None
    assert result >= 0


def test_consistency_identical_scores_zero(make_round, make_course):
    rounds = [make_round(gross=72) for _ in range(5)]
    courses = make_course()
    result = calc_scoring_consistency(rounds, courses)
    assert result == 0.0


def test_score_components_empty():
    result = calc_score_components([], {})
    assert result["approach"] is None
    assert result["scramble"] is None
    assert result["putting"] is None


def test_score_components_normal(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    result = calc_score_components(rounds, courses)
    assert result["putting"] is not None


def test_score_components_excludes_n_fairway(make_course):
    from source.models import dict_to_round
    holes = {"1": {"gross": "4", "putts": "2", "fairway": "N", "gir": "H", "penalties": "0"}}
    rounds = [dict_to_round({"date": "2026-01-01", "course": "Test GC", "tees": "White",
                             "holes_selection": "all", "total_gross": "4", "holes": holes})]
    courses = make_course()
    result = calc_score_components(rounds, courses)
    assert result["approach"] is None
    assert result["scramble"] is None


def test_penalty_stats_empty():
    result = calc_penalty_stats([], {})
    assert result["rate_per_round"] is None


def test_penalty_stats_no_penalties(make_round, make_course):
    rounds = [make_round(gross=80, penalties=0)]
    courses = make_course()
    result = calc_penalty_stats(rounds, courses)
    assert result["rate_per_round"] == 0.0


def test_momentum_empty():
    result = calc_momentum_recovery([], {})
    assert result["after_bogey_avg"] is None
    assert result["recovery_rate"] is None


def test_momentum_normal(make_round, make_course):
    rounds = [make_round(gross=80)]
    courses = make_course()
    result = calc_momentum_recovery(rounds, courses)
    if result["after_bogey_avg"] is not None:
        assert isinstance(result["after_bogey_avg"], float)


def test_personal_bests_empty():
    result = calc_personal_bests([], {})
    assert result["best_gross"] is None


def test_personal_bests_normal(make_round, make_course):
    rounds = [make_round(gross=g, date=f"2026-01-{d:02d}")
              for d, g in enumerate([80, 75, 90], 1)]
    courses = make_course()
    result = calc_personal_bests(rounds, courses)
    assert result["best_gross"] == 75
    assert result["best_gross_date"] == "2026-01-02"


def test_personal_bests_excludes_par3_fairway(make_course):
    from source.models import dict_to_round
    holes = {}
    for n in range(1, 19):
        pars = {1:4,2:5,3:4,4:3,5:4,6:5,7:4,8:3,9:4,10:5,11:4,12:3,13:4,14:5,15:4,16:3,17:4,18:5}
        fw = "H" if pars[n] != 3 else "H"
        holes[str(n)] = {"gross": str(pars[n]), "putts": "2", "fairway": fw, "gir": "H", "penalties": "0"}
    rounds = [dict_to_round({"date": "2026-01-01", "course": "Test GC", "tees": "White",
                             "holes_selection": "all", "total_gross": "72", "holes": holes})]
    courses = make_course()
    result = calc_personal_bests(rounds, courses)
    assert result["most_fir"] == 14


def test_nemesis_empty():
    worst, best = calc_nemesis_best_holes([], {})
    assert worst == []
    assert best == []


def test_per_hole_stats_empty():
    result = calc_per_hole_stats([], {}, "Test GC", 1)
    assert result["rounds_played"] == 0
    assert result["avg_score"] is None
    assert result["fir_pct"] is None
    assert result["gir_pct"] is None
    assert result["avg_putts"] is None
    assert result["avg_penalties"] is None


def test_per_hole_stats_normal(make_round, make_course):
    courses = make_course()
    r1 = make_round(gross=85, fir_hits=8, gir_hits=6, penalties=2)
    r2 = make_round(gross=78, fir_hits=12, gir_hits=10, penalties=0)
    rounds = [r1, r2]

    result = calc_per_hole_stats(rounds, courses, "Test GC", 4, handicap_index=10.5)

    assert result["rounds_played"] == 2
    assert result["avg_putts"] is not None
    assert result["fir_pct"] is None


def test_per_hole_stats_fir_miss_direction(make_round, make_course):
    courses = make_course()
    r1 = make_round(gross=80)
    r2 = make_round(gross=82)
    r1.holes["1"].fairway = "L"
    r2.holes["1"].fairway = "R"
    rounds = [r1, r2]

    result = calc_per_hole_stats(rounds, courses, "Test GC", 1)
    assert result["fir_pct"] == 0.0
    assert result["fir_miss_l_pct"] == 50.0
    assert result["fir_miss_r_pct"] == 50.0


def test_per_hole_stats_gir_miss_direction(make_round, make_course):
    courses = make_course()
    r1 = make_round(gross=80)
    r2 = make_round(gross=82)
    r1.holes["1"].gir = "S"
    r2.holes["1"].gir = "LO"
    rounds = [r1, r2]

    result = calc_per_hole_stats(rounds, courses, "Test GC", 1)
    assert result["gir_pct"] == 0.0
    assert result["gir_miss_s_pct"] == 50.0
    assert result["gir_miss_lo_pct"] == 50.0
    assert result["gir_miss_l_pct"] == 0.0
    assert result["gir_miss_r_pct"] == 0.0


def test_per_hole_stats_scramble(make_round, make_course):
    courses = make_course()
    r1 = make_round(gross=80)
    r2 = make_round(gross=82)
    r1.holes["1"].gir = "S"
    r2.holes["1"].gir = "L"
    r1.holes["1"].gross = 4
    r2.holes["1"].gross = 5
    rounds = [r1, r2]

    result = calc_per_hole_stats(rounds, courses, "Test GC", 1)
    assert result["gir_pct"] == 0.0
    assert result["scramble_pct"] == 50.0


def test_per_hole_stats_wrong_course(make_round, make_course):
    courses = make_course()
    r1 = make_round(gross=80)
    rounds = [r1]
    result = calc_per_hole_stats(rounds, courses, "Other GC", 1)
    assert result["rounds_played"] == 0
    assert result["avg_score"] is None
