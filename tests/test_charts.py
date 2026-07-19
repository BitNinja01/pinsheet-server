"""Unit tests for source/web/charts.py chart-data builder functions.

These call sparkline_svg() and make_chart_data() directly with known
inputs and assert the exact output structure/values (path strings,
point coordinates, and labels), per the module's hand-rolled SVG math.
"""

from source.web.charts import sparkline_svg, make_chart_data


class _Hole:
    """Minimal stand-in for HoleData -- only .gross is read by sparkline_svg."""

    def __init__(self, gross):
        self.gross = gross


# ---------------------------------------------------------------------------
# sparkline_svg
# ---------------------------------------------------------------------------

def test_sparkline_svg_none_for_no_holes():
    assert sparkline_svg(None) is None


def test_sparkline_svg_none_for_empty_dict():
    assert sparkline_svg({}) is None


def test_sparkline_svg_none_when_fewer_than_two_valid_scores():
    """Only one hole has a truthy gross value -> not enough points to draw."""
    holes = {"1": _Hole("4"), "2": _Hole(""), "3": _Hole(None)}
    assert sparkline_svg(holes) is None


def test_sparkline_svg_skips_holes_with_falsy_gross():
    """Falsy (empty-string / None) gross values are excluded from the score list,
    but numeric holes are still sorted by integer hole number and used."""
    holes = {"1": _Hole("4"), "2": _Hole(""), "3": _Hole("5")}
    result = sparkline_svg(holes)
    assert result == {
        "path": "M2.0 26.0 L208.0 2.0",
        "final_x": "208.0",
        "final_y": "2.0",
    }


def test_sparkline_svg_computes_exact_path_and_endpoint():
    """3 holes, scores [4, 5, 3] (lo=3, hi=5) sorted numerically by hole key."""
    holes = {"1": _Hole("4"), "2": _Hole("5"), "3": _Hole("3")}
    result = sparkline_svg(holes)
    assert result == {
        "path": "M2.0 14.0 L105.0 2.0 L208.0 26.0",
        "final_x": "208.0",
        "final_y": "26.0",
    }


def test_sparkline_svg_sorts_by_numeric_hole_key_not_string_order():
    """Hole keys "10" and "2" must sort as 2 < 10 (int), not string order "10" < "2"."""
    holes = {"10": _Hole("6"), "2": _Hole("4")}
    result = sparkline_svg(holes)
    # scores in numeric-key order: hole "2" (4) then hole "10" (6)
    # lo=4, hi=6, rng=2, n=1
    # j=0 s=4: x=2.0, y=2+(1-(4-4)/2)*24=26.0
    # j=1 s=6: x=208.0, y=2+(1-(6-4)/2)*24=2.0
    assert result["path"] == "M2.0 26.0 L208.0 2.0"
    assert result["final_x"] == "208.0"
    assert result["final_y"] == "2.0"


def test_sparkline_svg_flat_scores_uses_rng_fallback_of_one():
    """When all scores are equal, hi==lo so the function must fall back to
    rng=1 rather than dividing by zero."""
    holes = {"1": _Hole("4"), "2": _Hole("4"), "3": _Hole("4")}
    result = sparkline_svg(holes)
    # lo=hi=4 -> rng falls back to 1, so (s-lo)/rng == 0 for every point and
    # all y-coordinates collapse to the top of the drawable area (sp_pad).
    assert result == {
        "path": "M2.0 26.0 L105.0 26.0 L208.0 26.0",
        "final_x": "208.0",
        "final_y": "26.0",
    }


# ---------------------------------------------------------------------------
# make_chart_data
# ---------------------------------------------------------------------------

def test_make_chart_data_empty_chart_for_no_values():
    chart = make_chart_data([])
    assert chart == {
        "path": "", "area": "", "points": [],
        "label_x": "", "label_y": "", "label_v": "",
    }


def test_make_chart_data_empty_chart_for_single_value():
    """A single data point can't draw a line -- same empty-chart shape as []."""
    chart = make_chart_data([12.3])
    assert chart == {
        "path": "", "area": "", "points": [],
        "label_x": "", "label_y": "", "label_v": "",
    }


def test_make_chart_data_computes_exact_path_area_points_and_labels():
    chart = make_chart_data([10.0, 8.0, 9.0])
    assert chart["path"] == "M36.0 66.5 L510.0 155.5 L984.0 111.0"
    assert chart["area"] == "M36.0 66.5 L510.0 155.5 L984.0 111.0 L984.0 200.0 L36.0 200.0 Z"
    assert chart["points"] == [
        {"x": "36.0", "y": "66.5", "v": "10.0"},
        {"x": "510.0", "y": "155.5", "v": "8.0"},
        {"x": "984.0", "y": "111.0", "v": "9.0"},
    ]
    # labels are derived from the *last* point (most recent handicap value)
    assert chart["label_x"] == "976.0"
    assert chart["label_y"] == "99.0"
    assert chart["label_v"] == "9.0"


def test_make_chart_data_flat_values_does_not_divide_by_zero():
    """min == max: the +/-1.0 padding on lo/hi must prevent a ZeroDivisionError."""
    chart = make_chart_data([7.0, 7.0])
    assert chart["path"] == "M36.0 111.0 L984.0 111.0"
    assert chart["points"] == [
        {"x": "36.0", "y": "111.0", "v": "7.0"},
        {"x": "984.0", "y": "111.0", "v": "7.0"},
    ]
    assert chart["label_v"] == "7.0"


def test_make_chart_data_last_value_drives_label_even_if_not_extreme():
    """label_v/label_x/label_y always reflect hi_values[-1], regardless of
    whether it's the min, max, or somewhere in between."""
    chart = make_chart_data([5.0, 20.0, 12.0])
    assert chart["points"][-1]["v"] == "12.0"
    assert chart["label_v"] == "12.0"
