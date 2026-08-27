from calc import stat_arrow


def test_stat_arrow_lower_better_improvement():
    # scoring avg: primary (best-8) below secondary (L20) is good, lower is better
    d = stat_arrow(78.0, 80.0, higher_better=False)
    assert d["direction"] == "down"
    assert d["is_good"] is True
    assert d["magnitude"] == 2.0
    assert d["display"] == "2.0"


def test_stat_arrow_higher_better_improvement():
    # FIR %: primary above secondary is good, higher is better
    d = stat_arrow(62.0, 55.0, higher_better=True, suffix="%")
    assert d["direction"] == "up"
    assert d["is_good"] is True
    assert d["display"] == "7.0%"


def test_stat_arrow_higher_better_decline():
    d = stat_arrow(50.0, 58.0, higher_better=True, suffix="%")
    assert d["direction"] == "down"
    assert d["is_good"] is False


def test_stat_arrow_missing_secondary_returns_none():
    assert stat_arrow(80.0, None, higher_better=False) is None
    assert stat_arrow(None, 80.0, higher_better=False) is None


def test_stat_arrow_flat_on_equality():
    d = stat_arrow(80.0, 80.0, higher_better=False)
    assert d["direction"] == "flat"
    assert d["is_good"] is False


def test_stat_arrow_flat_within_display_precision():
    # rounds to one decimal, so a sub-0.05 difference counts as no change
    d = stat_arrow(72.34, 72.31, higher_better=False)
    assert d["direction"] == "flat"
