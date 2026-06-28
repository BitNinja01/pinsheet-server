import math
from calc.handicap import (
    calc_hole_scores,
    calc_course_handicap,
    calc_round_dif,
    calc_expected_9hole_dif,
    count_table_n,
    calc_effective_diffs,
    get_best_n_rounds,
    calc_handicap_index,
    calc_handicap_trend,
    calc_playing_to_handicap_rate,
    calc_raw_hi,
)


def test_count_table_n_all_boundaries():
    assert count_table_n(0) == 0
    assert count_table_n(2) == 0
    assert count_table_n(3) == 1
    assert count_table_n(5) == 1
    assert count_table_n(6) == 2
    assert count_table_n(8) == 2
    assert count_table_n(9) == 3
    assert count_table_n(11) == 3
    assert count_table_n(12) == 4
    assert count_table_n(14) == 4
    assert count_table_n(15) == 5
    assert count_table_n(16) == 5
    assert count_table_n(17) == 6
    assert count_table_n(18) == 6
    assert count_table_n(19) == 7
    assert count_table_n(20) == 8
    assert count_table_n(100) == 8


def test_calc_hole_scores_no_strokes():
    assert calc_hole_scores(5, 4, 4, 4) == (4, 4, 4)
    assert calc_hole_scores(18, 0, 3, 3) == (3, 3, 3)


def test_calc_hole_scores_one_stroke():
    gross, net, esc = calc_hole_scores(5, 10, 4, 4)
    assert net == 3
    assert esc == 4


def test_calc_hole_scores_two_strokes():
    gross, net, esc = calc_hole_scores(5, 30, 4, 5)
    assert net == 3


def test_calc_hole_scores_esc_limits_gross():
    gross, net, esc = calc_hole_scores(1, 10, 4, 9)
    assert esc == 7


def test_calc_course_handicap_standard():
    assert calc_course_handicap(10.0, 72, 113, 72) == 10


def test_calc_course_handicap_harder_course():
    result = calc_course_handicap(10.0, 72, 140, 74)
    assert result == round(10 * (140 / 113) + (74 - 72))


def test_calc_round_dif_scratch():
    assert calc_round_dif(113, 72, 72) == 0.0


def test_calc_round_dif_above_rating():
    result = calc_round_dif(128, 85, 71.5)
    assert result == round((113 / 128) * (85 - 71.5), 1)


def test_calc_expected_9hole_dif():
    assert calc_expected_9hole_dif(10.0) == 10.0 * 0.52 + 1.197
    assert calc_expected_9hole_dif(0.0) == 1.197


def test_calc_effective_diffs_empty():
    assert calc_effective_diffs([]) == []


def test_calc_effective_diffs_18_hole(sample_rounds):
    diffs = calc_effective_diffs(sample_rounds)
    assert len(diffs) == 3
    assert diffs == sorted(diffs)


def test_calc_effective_diffs_excluded_round(make_round):
    rounds = [
        make_round(gross=80, differential="10.0"),
        make_round(gross=90, differential="20.0"),
    ]
    rounds[1].excluded = True
    diffs = calc_effective_diffs(rounds)
    assert len(diffs) == 1
    assert diffs[0] == 10.0


def test_calc_effective_diffs_missing_differential(make_round):
    rounds = [make_round(differential=""), make_round(differential="0")]
    assert calc_effective_diffs(rounds) == []


def test_calc_effective_diffs_9hole_excluded_by_default(make_round):
    rounds = [make_round(gross=45, differential="10.0", holes_selection="front")]
    assert calc_effective_diffs(rounds) == []


def test_calc_effective_diffs_9hole_included(make_round):
    rounds = [make_round(gross=45, differential="10.0", holes_selection="front",
                          computed_handicap="12.0")]
    diffs = calc_effective_diffs(rounds, include_9hole=True)
    assert len(diffs) == 1
    assert diffs[0] == math.floor(10.0 * 10) / 10


def test_calc_effective_diffs_9hole_no_handicap(make_round):
    rounds = [make_round(gross=45, differential="10.0", holes_selection="front",
                          computed_handicap="0")]
    diffs = calc_effective_diffs(rounds, include_9hole=True)
    assert diffs == []


def test_get_best_n_rounds_none(make_round):
    rounds = [make_round(gross=g, differential=str(100 - g)) for g in range(70, 90)]
    best = get_best_n_rounds(rounds)
    assert len(best) == count_table_n(len(rounds))


def test_get_best_n_rounds_explicit_n(make_round):
    rounds = [make_round(gross=g, differential=str(100 - g)) for g in range(70, 90)]
    best = get_best_n_rounds(rounds, n=3)
    assert len(best) == 3


def test_get_best_n_rounds_sorted(make_round):
    rounds = [make_round(gross=g, differential=str(100 - g)) for g in (80, 75, 90, 72, 85)]
    best = get_best_n_rounds(rounds, n=2)
    diffs = [math.floor(float(r.differential) * 10) / 10 for r in best]
    assert diffs == sorted(diffs)


def test_calc_handicap_index_empty():
    assert calc_handicap_index([]) is None


def test_calc_handicap_index_too_few_rounds(make_round):
    rounds = [make_round() for _ in range(2)]
    assert calc_handicap_index(rounds) is None


def test_calc_handicap_index_scratch(make_round):
    rounds = [make_round(gross=72, differential=str(i * 0.5)) for i in range(20)]
    hi = calc_handicap_index(rounds)
    assert hi is not None
    assert hi >= 0


def test_calc_handicap_index_bogey(make_round):
    rounds = [make_round(gross=90, differential=str(15 + i * 0.5)) for i in range(20)]
    hi = calc_handicap_index(rounds)
    assert hi is not None
    assert 10 < hi < 25


def test_calc_handicap_index_never_negative(make_round):
    for gross in (72, 80, 90, 100):
        rounds = [make_round(gross=gross, differential=str(gross - 72 + i))
                  for i in range(20)]
        hi = calc_handicap_index(rounds)
        assert hi is None or hi >= 0


def test_calc_handicap_index_best8_le_raw(make_round):
    rounds = [make_round(gross=75 + i, differential=str(i * 2)) for i in range(30)]
    diffs = calc_effective_diffs(rounds[:20])
    if len(diffs) >= 8:
        hi = calc_handicap_index(rounds[:20])
        raw_avg = sum(diffs) / len(diffs)
        assert hi <= raw_avg


def test_calc_handicap_trend_empty():
    assert calc_handicap_trend([]) == []


def test_calc_handicap_trend_returns_pairs(make_round):
    rounds = [make_round(date=f"2026-05-{d:02d}", gross=80, differential="10.0")
              for d in range(1, 21)]
    trend = calc_handicap_trend(rounds)
    assert len(trend) > 0
    assert all(isinstance(t, tuple) and len(t) == 2 for t in trend)


def test_calc_playing_to_handicap_rate_empty():
    assert calc_playing_to_handicap_rate([]) is None


def test_calc_playing_to_handicap_rate_mixed(make_round):
    rounds = [
        make_round(gross=72, differential="2.0", computed_handicap="5.0"),
        make_round(gross=80, differential="10.0", computed_handicap="5.0"),
        make_round(gross=76, differential="6.0", computed_handicap="5.0"),
    ]
    rate = calc_playing_to_handicap_rate(rounds)
    assert rate is not None
    assert 0 <= rate <= 100


def test_calc_playing_to_handicap_rate_all_above(make_round):
    rounds = [make_round(gross=90, differential="20.0", computed_handicap="5.0")
              for _ in range(5)]
    assert calc_playing_to_handicap_rate(rounds) == 0.0


def test_calc_playing_to_handicap_rate_all_below(make_round):
    rounds = [make_round(gross=72, differential="2.0", computed_handicap="10.0")
              for _ in range(5)]
    assert calc_playing_to_handicap_rate(rounds) == 100.0


def test_calc_raw_hi_empty():
    assert calc_raw_hi([]) is None


def test_calc_raw_hi_approximate(make_round):
    rounds = [make_round(gross=80, differential=str(i)) for i in (5, 6, 7, 8, 9)]
    raw = calc_raw_hi(rounds)
    expected = ((5 + 6 + 7 + 8 + 9) / 5) * 0.96
    assert raw == expected


def test_calc_course_handicap_maplewood_white():
    assert calc_course_handicap(21.7, 72, 120, 67.7) == 19


def test_calc_course_handicap_druids_white():
    assert calc_course_handicap(22.3, 72, 130, 69.3) == 23


def test_calc_course_handicap_round_over_int():
    assert calc_course_handicap(21.7, 72, 120, 67.7) == 19
    assert calc_course_handicap(21.7, 72, 120, 67.7) != 18


def test_calc_course_handicap_near_boundary():
    assert calc_course_handicap(10.0, 72, 113, 72) == 10
    assert calc_course_handicap(10.0, 72, 140, 74) == 14


def test_handicap_index_last_20_vs_all(make_round):
    """WHS: best 8 of most recent 20 only. A round outside the last-20 window
    must never influence the index. This regression test encodes real data
    where the 21st-round diff 21.7 would wrongly lower the index to 19.7."""
    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]
    rounds = [make_round(differential=str(d)) for d in diffs]

    hi_20 = calc_handicap_index(rounds[:20])
    hi_all = calc_handicap_index(rounds)

    assert hi_20 == 19.8
    assert hi_all == 19.7
    assert hi_20 != hi_all


def test_store_recompute_window_slice(make_round):
    """recompute_all_handicaps must window to the most recent 20 rounds in
    chronological order. chronological[max(0,i+1-20):i+1] excludes rounds
    beyond the last 20."""
    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]
    rounds = [make_round(differential=str(d)) for d in diffs]
    chronological = list(reversed(rounds))

    i_last = len(chronological) - 1
    window = chronological[max(0, i_last + 1 - 20):i_last + 1]

    assert len(window) == 20
    window_diffs = [float(r.differential) for r in window]
    assert 21.7 not in window_diffs

    old_window = chronological[:i_last + 1]
    assert len(old_window) == 30
    assert 21.7 in [float(r.differential) for r in old_window]

    hi = calc_handicap_index(window)
    assert hi == 19.8


def test_get_best_n_rounds_capped_to_last_20(make_round):
    """Dashboard best_rounds must come from the most recent 20 rounds, not all.
    A round outside the last 20 (diff 21.7) must not appear in best-8."""
    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]
    rounds = [make_round(differential=str(d)) for d in diffs]

    best_capped = get_best_n_rounds(rounds[:20])
    capped_diffs = [float(r.differential) for r in best_capped]
    assert 21.7 not in capped_diffs
    assert len(best_capped) == 8

    best_uncapped = get_best_n_rounds(rounds)
    uncapped_diffs = [float(r.differential) for r in best_uncapped]
    assert 21.7 in uncapped_diffs
    assert len(best_uncapped) == 8


# --- Guard tests for WHS last-20 windowing fix (call-site verification) ---

def test_recompute_handicaps_uses_last_20_window(tmp_data_dir):
    """recompute_all_handicaps must window to the most recent 20 rounds.
    With 30 rounds, the most-recent round must have HI 19.8 (last-20 correct),
    NOT 19.7 (all-rounds, which wrongly includes diff 21.7 from outside the
    last 20). Guards store.py: chronological[max(0,i+1-20):i+1]."""
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_round, get_all_rounds, recompute_all_handicaps

    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    create_user("golfer", "Golfer", "pass1234")
    save_settings({"include_9hole": True}, user_id=1)

    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]

    for i, d in enumerate(diffs):
        day = 30 - i
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(d), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{day:02d}", 0, user_id=1)

    recompute_all_handicaps()

    rounds = get_all_rounds(user_id=1)
    most_recent = rounds[0]
    assert most_recent.computed_handicap == "19.8", (
        f"Most-recent round should have last-20 HI 19.8, got {most_recent.computed_handicap}"
    )


def test_profile_hi_insight_eight_of_twenty(tmp_path, monkeypatch):
    """_build_profile_context must report '8 of your last 20' because all
    best-8 rounds come from within the last 20 (after the dashboard.py fix
    that caps best_rounds to rounds[:20]). The old uncapped code would report
    '7' because the round at index 20 (diff 21.7) was in best-8 overall but
    missed the eligible_20 window. Guards dashboard.py:
    get_best_n_rounds(rounds[:20], ...)."""
    from main import app, User as UserClass
    from database import set_db_path, init_db
    from store import create_user, save_settings, save_course, save_round, get_user_by_id
    from flask_login import login_user

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "drafts").mkdir()
    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["DB_PATH"] = db_path

    create_user("p", "P", "pass1234")
    save_settings({"welcome_shown": True, "include_9hole": True}, user_id=1)

    course = {
        "par": "72",
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "tees": {"W": {"slope": "120", "rating": "70.0", "yardage": "6000"}},
    }
    save_course(course, "GC")

    diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
             21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
             21.7, 25.3, 37.1, 25.6, 33.6, 28.4, 29.8, 29.5, 35.7, 29.0]

    for i, d in enumerate(diffs):
        day = 30 - i
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(d), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{day:02d}", 0, user_id=1)

    with app.test_request_context():
        user_dict = get_user_by_id(1)
        login_user(UserClass(user_dict))

        from source.routes.dashboard import _build_profile_context
        ctx = _build_profile_context()
        assert ctx is not None, "_build_profile_context returned None (welcome_shown?)"

        hi_insight = ctx.get("hi_insight")
        assert hi_insight is not None, "No hi_insight in profile context"
        assert "8 of your last 20" in hi_insight, (
            f"Expected '8 of your last 20', got: {hi_insight}"
        )
