from calc.putting import (
    calc_putts_per_round,
    calc_putts_per_gir,
    calc_three_putt_percent,
    calc_four_plus_putt_percent,
    calc_two_putt_percent,
    calc_one_putt_percent,
    calc_putts_by_par_type,
)


def test_putts_per_round_empty():
    assert calc_putts_per_round([]) is None


def test_putts_per_round_normal(sample_rounds):
    result = calc_putts_per_round(sample_rounds)
    assert result is not None
    assert 25 < result < 40


def test_putts_per_round_excludes_9hole(make_round):
    rounds = [make_round(gross=45, putts=16, holes_selection="front")]
    assert calc_putts_per_round(rounds) is None


def test_putts_per_gir_empty():
    assert calc_putts_per_gir([]) is None


def test_putts_per_gir_normal(sample_rounds):
    result = calc_putts_per_gir(sample_rounds)
    assert result is not None
    assert 1.0 <= result <= 3.0


def test_one_putt_percent_empty():
    assert calc_one_putt_percent([]) is None


def test_one_putt_percent_normal(sample_rounds):
    result = calc_one_putt_percent(sample_rounds)
    assert result is not None
    assert 0 <= result <= 100


def test_two_putt_percent_empty():
    assert calc_two_putt_percent([]) is None


def test_two_putt_percent_normal(sample_rounds):
    result = calc_two_putt_percent(sample_rounds)
    assert result is not None
    assert 0 <= result <= 100


def test_three_putt_percent_empty():
    assert calc_three_putt_percent([]) is None


def test_three_putt_percent_normal(sample_rounds):
    result = calc_three_putt_percent(sample_rounds)
    assert result is not None
    assert 0 <= result <= 100


def test_four_plus_putt_percent_empty():
    assert calc_four_plus_putt_percent([]) is None


def test_four_plus_putt_percent_normal(sample_rounds):
    result = calc_four_plus_putt_percent(sample_rounds)
    assert result is not None
    assert 0 <= result <= 100


def test_putts_by_par_type_empty():
    result = calc_putts_by_par_type([], {})
    assert result[3] is None
    assert result[4] is None
    assert result[5] is None


def test_putts_by_par_type_normal(make_round, make_course):
    rounds = [make_round(gross=80, putts=30)]
    courses = make_course()
    result = calc_putts_by_par_type(rounds, courses)
    assert result[3] is not None
    assert result[4] is not None
    assert result[5] is not None


def test_percentage_functions_range(make_round):
    rounds = [make_round(gross=g, putts=p) for g, p in
              [(72, 28), (75, 30), (78, 31), (80, 33), (85, 36),
               (90, 38), (95, 40), (72, 26), (76, 29), (80, 32)]]
    for fn in [calc_one_putt_percent, calc_two_putt_percent,
               calc_three_putt_percent, calc_four_plus_putt_percent]:
        result = fn(rounds)
        assert result is None or 0 <= result <= 100
