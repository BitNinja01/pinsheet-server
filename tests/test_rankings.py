import pytest
from database import set_db_path, init_db, get_db
from store import create_user, save_round, save_course, get_users, get_all_rounds
from calc.rankings import compute_rankings, STAT_META, BOARD_STATS


@pytest.fixture
def db(tmp_data_dir, monkeypatch):
    db_path = str(tmp_data_dir / "pinsheet.db")
    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", tmp_data_dir)
    set_db_path(db_path)
    init_db()
    return get_db()


def _add_round(user_id, gross, date="2026-06-01", diff="10.0", course="Test GC"):
    r = {"course": course, "tees": "W", "total_gross": str(gross),
         "differential": diff, "computed_handicap": diff,
         "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r, date, 0, user_id=user_id)


def test_rankings_empty_returns_empty_list(db):
    rankings = compute_rankings()
    assert rankings == []
    db.close()


def test_rankings_single_user_no_rounds(db):
    create_user("p1", "Player1", "pass")
    rankings = compute_rankings()
    assert len(rankings) == 1
    assert rankings[0]["display_name"] == "Player1"
    for key in BOARD_STATS:
        assert rankings[0]["stats"][key] is None
    db.close()


def test_rankings_single_user_with_rounds(db):
    create_user("p1", "Player1", "pass")
    _add_round(1, 80, diff="8.0", date="2026-06-01")
    _add_round(1, 82, diff="10.0", date="2026-06-02")
    _add_round(1, 78, diff="6.0", date="2026-06-03")
    rankings = compute_rankings()
    assert len(rankings) == 1
    stats = rankings[0]["stats"]
    assert stats["score"] is not None
    assert stats["score"] == 80.0
    db.close()


def test_rankings_multiple_users_sorted_by_handicap(db):
    create_user("p1", "Player1", "pass")
    create_user("p2", "Player2", "pass")
    for uid in (1, 2):
        for i in range(5):
            diff = 5.0 if uid == 1 else 15.0
            _add_round(uid, 70 + i, diff=str(diff + i * 0.5),
                       date=f"2026-06-{i + 1:02d}")
    rankings = compute_rankings(sort_key="handicap", sort_desc=False)
    assert len(rankings) == 2
    assert rankings[0]["display_name"] == "Player1"
    assert rankings[0]["stats"]["handicap"] < rankings[1]["stats"]["handicap"]
    db.close()


def test_rankings_sorted_descending(db):
    create_user("p1", "Player1", "pass")
    create_user("p2", "Player2", "pass")
    for uid in (1, 2):
        for i in range(5):
            diff = 5.0 if uid == 1 else 15.0
            _add_round(uid, 70 + i, diff=str(diff + i * 0.5),
                       date=f"2026-06-{i + 1:02d}")
    rankings = compute_rankings(sort_key="handicap", sort_desc=True)
    assert rankings[0]["display_name"] == "Player2"
    assert rankings[0]["stats"]["handicap"] > rankings[1]["stats"]["handicap"]
    db.close()


def test_rankings_fir_sorted_higher_better(db):
    create_user("p1", "Player1", "pass")
    create_user("p2", "Player2", "pass")
    save_course({"par": "72", "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                 "tees": {"W": {"slope": 113, "rating": 72.0}}}, "Test GC")
    scores_p1 = {"1": {"gross": "4", "putts": "2", "fairway": "H"},
                 "2": {"gross": "4", "putts": "2", "fairway": "H"},
                 "3": {"gross": "3", "putts": "1", "fairway": ""},
                 "4": {"gross": "4", "putts": "2", "fairway": "H"}}
    scores_p2 = {"1": {"gross": "4", "putts": "2", "fairway": "L"},
                 "2": {"gross": "4", "putts": "2", "fairway": "R"},
                 "3": {"gross": "3", "putts": "1", "fairway": ""},
                 "4": {"gross": "4", "putts": "2", "fairway": "L"}}
    for uid, holes in ((1, scores_p1), (2, scores_p2)):
        r = {"course": "Test GC", "tees": "W", "total_gross": "80",
             "differential": "10.0", "computed_handicap": "10.0",
             "holes_selection": "all", "entry_mode": "detailed", "holes": holes}
        save_round(r, "2026-06-01", 0, user_id=uid)
    rankings = compute_rankings(sort_key="fir", sort_desc=False)
    assert rankings[0]["display_name"] == "Player1"
    db.close()


def test_rankings_date_filter(db):
    create_user("p1", "Player1", "pass")
    _add_round(1, 80, date="2026-05-01")
    _add_round(1, 90, date="2026-06-15")
    _add_round(1, 85, date="2026-07-01")
    rankings_all = compute_rankings()
    assert rankings_all[0]["stats"]["score"] == 85.0
    rankings_june = compute_rankings(date_start="2026-06-01", date_end="2026-06-30")
    assert rankings_june[0]["stats"]["score"] == 90.0
    rankings_may = compute_rankings(date_start="2026-05-01", date_end="2026-05-31")
    assert rankings_may[0]["stats"]["score"] == 80.0
    db.close()


def test_rankings_users_with_no_rounds_at_bottom(db):
    create_user("p1", "Player1", "pass")
    create_user("p2", "Player2", "pass")
    create_user("p3", "Player3", "pass")
    for i in range(5):
        _add_round(1, 80 + i, diff=f"{10.0 + i}", date=f"2026-06-{i + 1:02d}")
        _add_round(3, 75 + i, diff=f"{5.0 + i}", date=f"2026-06-{i + 1:02d}")
    rankings = compute_rankings(sort_key="handicap", sort_desc=False)
    assert len(rankings) == 3
    ranked_names = [r["display_name"] for r in rankings]
    assert ranked_names[0] == "Player3"
    assert ranked_names[1] == "Player1"
    assert ranked_names[2] == "Player2"
    db.close()


def test_rankings_invalid_sort_key_defaults_to_handicap(db):
    create_user("p1", "Player1", "pass")
    _add_round(1, 80, diff="10.0")
    rankings = compute_rankings(sort_key="nonexistent")
    assert len(rankings) == 1
    db.close()


def test_board_stats_list_contains_six_keys(db):
    assert len(BOARD_STATS) == 6
    for key in ("handicap", "score", "fir", "gir", "putts", "scramble"):
        assert key in BOARD_STATS
    db.close()


def test_stat_meta_has_all_board_stats(db):
    for key in BOARD_STATS:
        assert key in STAT_META
        assert "label" in STAT_META[key]
        assert "higher_better" in STAT_META[key]
    db.close()


def test_rankings_includes_streak(db):
    create_user("p1", "Player1", "pass")
    for i in range(5):
        _add_round(1, 80, diff="10.0", date=f"2026-06-{i+1:02d}")
    rankings = compute_rankings()
    assert len(rankings) == 1
    stats = rankings[0]["stats"]
    assert "streak" in stats
    assert stats["streak"] >= 0
    db.close()


def test_rankings_includes_form(db):
    create_user("p1", "Player1", "pass")
    for i in range(10):
        diff_val = 5.0 + i * 0.5
        _add_round(1, 70 + i, diff=str(diff_val), date=f"2026-06-{i+1:02d}")
    rankings = compute_rankings()
    stats = rankings[0]["stats"]
    assert "form" in stats
    assert len(stats["form"]) <= 6
    assert isinstance(stats["form"], list)
    if len(stats["form"]) >= 2:
        assert stats["form_svg"] is not None
        assert "path" in stats["form_svg"]
    db.close()


def test_rankings_includes_lead_stat(db):
    create_user("p1", "Player1", "pass")
    create_user("p2", "Player2", "pass")
    for i in range(5):
        _add_round(1, 70 + i, diff="5.0", date=f"2026-06-{i+1:02d}")
        _add_round(2, 80 + i, diff="15.0", date=f"2026-06-{i+1:02d}")
    rankings = compute_rankings()
    for entry in rankings:
        assert "lead_stat" in entry["stats"]
    db.close()
