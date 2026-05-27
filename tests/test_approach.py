from calc.approach import (
    calc_fir_percent,
    calc_gir_percent,
    calc_scramble_percent,
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
)


def test_fir_percent_empty():
    assert calc_fir_percent([], {}) is None


def test_fir_percent_normal(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=8)]
    courses = make_course()
    result = calc_fir_percent(rounds, courses)
    assert result is not None
    assert 0 <= result <= 100


def test_fir_percent_all_hit(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=14)]
    courses = make_course()
    result = calc_fir_percent(rounds, courses)
    assert result == 100.0


def test_fir_percent_all_missed(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=0)]
    courses = make_course()
    result = calc_fir_percent(rounds, courses)
    assert result == 0.0


def test_gir_percent_empty():
    assert calc_gir_percent([]) is None


def test_gir_percent_normal(sample_rounds):
    result = calc_gir_percent(sample_rounds)
    assert result is not None
    assert 0 <= result <= 100


def test_gir_percent_cannot_exceed_100(make_round):
    rounds = [make_round(gross=80, gir_hits=18)]
    result = calc_gir_percent(rounds)
    assert result is not None
    assert result <= 100.0


def test_scramble_percent_empty():
    assert calc_scramble_percent([], {}) is None


def test_scramble_percent_normal(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=8, gir_hits=6)]
    courses = make_course()
    result = calc_scramble_percent(rounds, courses)
    assert result is not None
    assert 0 <= result <= 100


def test_fir_miss_empty():
    result = calc_fir_miss_tendency([], {})
    assert result["left"] is None
    assert result["right"] is None


def test_fir_miss_sums_to_100(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=4)]
    courses = make_course()
    result = calc_fir_miss_tendency(rounds, courses)
    if result["left"] is not None and result["right"] is not None:
        assert abs(result["left"] + result["right"] - 100) < 0.1


def test_scoring_by_fairway_empty():
    result = calc_scoring_by_fairway([], {})
    assert result["hit"] is None
    assert result["missed"] is None


def test_scoring_by_fairway_normal(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=8)]
    courses = make_course()
    result = calc_scoring_by_fairway(rounds, courses)
    assert result["hit"] is not None
    assert result["missed"] is not None


def test_scoring_by_miss_side_empty():
    result = calc_scoring_by_miss_side([], {})
    assert result["left"] is None
    assert result["right"] is None


def test_gir_by_par_type_empty():
    result = calc_gir_by_par_type([], {})
    assert result[3] is None
    assert result[4] is None
    assert result[5] is None


def test_gir_by_par_type_normal(make_round, make_course):
    rounds = [make_round(gross=80, gir_hits=6)]
    courses = make_course()
    result = calc_gir_by_par_type(rounds, courses)
    for p in (3, 4, 5):
        assert result[p] is not None
        assert 0 <= result[p] <= 100


def test_gir_miss_direction_empty():
    result = calc_gir_miss_direction([])
    for k in ("L", "R", "S", "LO"):
        assert result[k] is None


def test_gir_miss_direction_normal(sample_rounds):
    result = calc_gir_miss_direction(sample_rounds)
    if result["L"] is not None:
        assert 0 <= result["L"] <= 100


def test_gir_fw_vs_rough_empty():
    result = calc_gir_from_fairway_vs_rough([], {})
    assert result["fairway"] is None
    assert result["rough"] is None


def test_gir_fw_vs_rough_normal(make_round, make_course):
    rounds = [make_round(gross=80, fir_hits=8, gir_hits=6)]
    courses = make_course()
    result = calc_gir_from_fairway_vs_rough(rounds, courses)
    assert result["fairway"] is not None
    assert result["rough"] is not None
    assert 0 <= result["fairway"] <= 100
    assert 0 <= result["rough"] <= 100


def test_scoring_by_gir_empty():
    result = calc_scoring_by_gir([], {})
    assert result["hit"] is None
    assert result["missed"] is None


def test_scramble_by_miss_empty():
    result = calc_scramble_by_miss_direction([], {})
    for d in ("L", "R", "S", "LO"):
        assert result[d] is None


def test_scramble_by_par_type_empty():
    result = calc_scramble_by_par_type([], {})
    for p in (3, 4, 5):
        assert result[p] is None


def test_ob_stats_empty():
    result = calc_ob_stats([], {})
    assert result["fir_ob_per_round"] is None
    assert result["gir_ob_per_round"] is None
    assert result["total_ob_per_round"] is None


def test_percentage_functions_range(make_round, make_course):
    rounds = [make_round(gross=g, fir_hits=f, gir_hits=gi)
              for g, f, gi in [
                  (72, 12, 14), (75, 10, 12), (78, 9, 10),
                  (80, 8, 8), (85, 6, 6), (90, 4, 4),
                  (95, 3, 3), (72, 11, 13), (76, 8, 9), (82, 7, 7),
              ]]
    courses = make_course()
    for fn in [calc_fir_percent, calc_scramble_percent]:
        result = fn(rounds, courses)
        assert result is None or 0 <= result <= 100
    result = calc_gir_percent(rounds)
    assert result is None or 0 <= result <= 100
