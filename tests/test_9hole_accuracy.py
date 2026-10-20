"""9-hole accuracy across the recompute pipeline.

WHS Rule 5.1b: a 9-hole score is combined with an expected score to form an
18-hole equivalent Score Differential. Once a prior Handicap Index exists,
that differential is acceptable and must count toward the index of the round
itself, exactly as an 18-hole differential does.

These tests pin that behavior end to end through `recompute_handicaps_for_user`
(the single writer of every stored `computed_handicap`).

The fixtures use a scratch-level course (slope 113, rating 72 / 36 per nine)
and stay below the Rule 5.7 LHI threshold and the Rule 5.9 ESR threshold, so
the stored value must equal a direct `calc_handicap_index()` call with no
cap or reduction in play.
"""

import pytest

from calc import calc_handicap_index
from database import init_db, set_db_path
from store import (
    create_user,
    get_all_rounds,
    recompute_handicaps_for_user,
    save_course,
    save_round,
    save_settings,
)

COURSE = {
    "par": "72",
    "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
    "tees": {
        "White": {
            "slope": "113",
            "rating": "72.0",
            "front_slope": "113",
            "front_rating": "36.0",
            "back_slope": "113",
            "back_rating": "36.0",
            "yardage": "6000",
        }
    },
}


@pytest.fixture
def nine_db(tmp_data_dir):
    set_db_path(str(tmp_data_dir / "pinsheet.db"))
    init_db()
    create_user("nine", "Nine", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)
    save_course(COURSE, "NineCourse")
    return tmp_data_dir


def _round(gross, holes_played="18"):
    return {
        "course": "NineCourse",
        "tees": "White",
        "holes_played": holes_played,
        "entry_mode": "score_only",
        "total_gross": str(gross),
        "differential": "",
        "computed_handicap": "",
        "holes": {},
    }


def _seed_18(day_start=1, count=3, gross_start=90):
    for i in range(count):
        day = day_start + i
        save_round(_round(gross_start + i), f"2026-05-{day:02d}", 0, 1)


def test_9hole_round_counts_toward_its_own_handicap(nine_db):
    """The newest 9-hole round's differential must be inside its own stored
    Handicap Index, not deferred to the next round."""
    _seed_18()
    save_round(_round(40, "front"), "2026-05-04", 0, 1)
    recompute_handicaps_for_user(1)

    all_rounds = get_all_rounds(1)
    newest = all_rounds[0]
    assert newest.holes_selection == "front"
    assert newest.differential not in ("", "0")
    assert newest.computed_handicap not in ("", "0")

    direct = calc_handicap_index(all_rounds, include_9hole=True)
    assert direct is not None
    assert float(newest.computed_handicap) == direct


def test_9hole_round_excluded_when_setting_off(nine_db):
    """With include_9hole=False the 9-hole differential must not contribute
    to the index, and the stored index must match the 18-hole-only calc."""
    _seed_18()
    save_round(_round(40, "front"), "2026-05-04", 0, 1)
    recompute_handicaps_for_user(1)

    all_rounds = get_all_rounds(1)
    with_nine = calc_handicap_index(all_rounds, include_9hole=True)

    save_settings({"include_9hole": False}, user_id=1)
    recompute_handicaps_for_user(1)

    all_rounds = get_all_rounds(1)
    without_nine = calc_handicap_index(all_rounds, include_9hole=False)
    assert without_nine > with_nine, "fixture must make the 9-hole diff matter"

    eighteen = next(r for r in all_rounds if r.holes_selection == "all")
    assert float(eighteen.computed_handicap) == without_nine


def test_9hole_only_record_does_not_establish_handicap(nine_db):
    """A 9-hole differential needs a prior Handicap Index to combine against.
    Without one, the raw base is stored but no index is issued."""
    for i in range(3):
        save_round(_round(40, "front"), f"2026-05-{i + 1:02d}", 0, 1)
    recompute_handicaps_for_user(1)

    for r in get_all_rounds(1):
        assert r.differential not in ("", "0")
        assert r.computed_handicap == ""


def test_9hole_round_counts_when_prior_handicap_is_zero(nine_db):
    """A genuine 0.0 Handicap Index is not the "no index" sentinel. A 9-hole
    round played off a 0.0 index must still count."""
    # Three 18-hole rounds of gross 74 on a 72.0 rating give differential
    # 2.0 each: best 1 (2.0) minus the Rule 5.2a count-of-3 adjustment (2.0)
    # yields a 0.0 Handicap Index.
    _seed_18(gross_start=74)
    save_round(_round(40, "front"), "2026-05-04", 0, 1)
    recompute_handicaps_for_user(1)

    all_rounds = get_all_rounds(1)
    latest_prior = next(r for r in all_rounds if r.holes_selection == "all")
    assert float(latest_prior.computed_handicap) == 0.0

    newest = all_rounds[0]
    assert newest.holes_selection == "front"

    # Combined 9-hole diff: base (40 - 36) = 4.0, plus the expected-score
    # adjustment for a 0.0 index (1.197) => 5.2. Best 1 of the four diffs is
    # still 2.0, and the count-of-4 adjustment is 1.0, so the index is 1.0.
    direct = calc_handicap_index(all_rounds, include_9hole=True)
    assert direct == 1.0
    assert float(newest.computed_handicap) == 1.0
