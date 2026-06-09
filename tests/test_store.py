import json
import os
import sqlite3

import pytest

from database import set_db_path, init_db, get_db
from store import (
    load_settings, save_settings,
    get_courses, save_course, delete_course, rename_course,
    get_all_rounds, save_round, delete_round, update_round_handicap,
    recompute_all_handicaps,
    get_slope_rating,
    save_course_draft, load_course_draft, clear_course_draft,
    save_round_draft, load_round_draft, clear_round_draft,
    get_users, get_user, get_user_by_id, create_user, verify_user,
    user_count, real_user_count,
    is_invite_code_valid, consume_invite_code, create_invite_code, get_invite_codes,
    create_match, get_match, get_all_matches, complete_match,
    add_match_player, remove_match_player,
    link_round, unlink_round, get_match_rounds, get_match_players,
    create_challenge, get_challenge, get_all_challenges,
    add_challenge_participant, remove_challenge_participant,
    get_challenge_participants, complete_challenge,
)


@pytest.fixture
def db(tmp_data_dir, monkeypatch):
    """Set up a fresh SQLite database in temp directory."""
    db_path = str(tmp_data_dir / "pinsheet.db")
    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", tmp_data_dir)
    set_db_path(db_path)
    init_db()
    return get_db()


def test_init_db_creates_tables(db):
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = [t[0] for t in tables]
    for expected in ("users", "courses", "rounds", "settings", "invite_codes",
                     "plugin_states", "matches", "match_players", "match_rounds",
                     "challenges", "challenge_participants"):
        assert expected in names
    db.close()


def test_create_and_get_user(db):
    u = create_user("testuser", "Test User", "password123")
    assert u["username"] == "testuser"
    assert u["id"] == 1
    assert u["is_admin"] is True

    found = get_user("testuser")
    assert found is not None
    assert found["id"] == 1
    db.close()


def test_user_count(db):
    assert user_count() == 0
    assert real_user_count() == 0
    create_user("admin", "Admin", "pass1234")
    assert user_count() == 1
    assert real_user_count() == 1
    db.close()


def test_verify_user(db):
    create_user("player", "Player", "secret12")
    result = verify_user("player", "secret12")
    assert result is not None
    assert result["username"] == "player"
    assert verify_user("player", "wrong") is None
    assert verify_user("nobody", "x") is None
    db.close()


def test_first_user_is_admin(db):
    create_user("admin1", "Admin One", "pass1234")
    u = get_user("admin1")
    assert u["is_admin"] is True
    create_user("user2", "User Two", "pass5678")
    u2 = get_user("user2")
    assert u2["is_admin"] is False
    db.close()


def test_settings_save_and_load(db):
    create_user("admin", "Admin", "pass1234")
    data = {"theme": "dark", "season_start_month": 4}
    save_settings(data, user_id=1)
    loaded = load_settings(user_id=1)
    assert loaded["theme"] == "dark"
    assert loaded["season_start_month"] == 4
    db.close()


def test_settings_merge_on_save(db):
    create_user("admin", "Admin", "pass1234")
    save_settings({"theme": "dark", "welcome_shown": True}, user_id=1)
    save_settings({"theme": "light"}, user_id=1)
    loaded = load_settings(user_id=1)
    assert loaded["theme"] == "light"
    assert loaded["welcome_shown"] is True
    db.close()


def test_settings_defaults(db):
    loaded = load_settings(user_id=99)
    assert loaded["season_start_month"] == 1
    assert loaded["season_end_month"] == 12
    db.close()


def test_save_and_get_course(db):
    course = {"par": "72", "tees": {"White": {"slope": 128, "rating": 71.5}}}
    save_course(course, "Test GC")
    courses = get_courses()
    assert "Test GC" in courses
    assert courses["Test GC"]["par"] == "72"
    db.close()


def test_delete_course(db):
    save_course({"par": "72"}, "Gone GC")
    delete_course("Gone GC")
    courses = get_courses()
    assert "Gone GC" not in courses
    db.close()


def test_rename_course(db):
    save_course({"par": "72"}, "Old Name")
    rename_course("Old Name", "New Name")
    courses = get_courses()
    assert "Old Name" not in courses
    assert "New Name" in courses
    db.close()


def test_save_and_get_rounds(db):
    create_user("golfer", "Golfer", "pass1234")
    r = {"course": "Test GC", "tees": "White",
         "total_gross": "80", "differential": "10.0", "computed_handicap": "12.0",
         "holes_selection": "all", "entry_mode": "detailed",
         "holes": {"1": {"gross": "4", "putts": "2"}}}
    save_round(r, "2026-05-01", 0, user_id=1)

    r2 = {"course": "Other GC", "tees": "Blue",
          "total_gross": "75", "differential": "5.0", "computed_handicap": "12.0",
          "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r2, "2026-05-02", 0, user_id=1)

    all_rounds = get_all_rounds(user_id=1)
    assert len(all_rounds) == 2
    assert all_rounds[0].date == "2026-05-02"
    assert all_rounds[0].total_gross == "75"
    db.close()


def test_get_all_rounds_limit(db):
    create_user("golfer", "Golfer", "pass1234")
    for d in range(1, 6):
        r = {"course": "GC", "tees": "White", "total_gross": str(70 + d),
             "differential": str(d), "computed_handicap": "10.0",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{d:02d}", 0, user_id=1)
    result = get_all_rounds(user_id=1, limit=3)
    assert len(result) == 3
    db.close()


def test_delete_round(db):
    create_user("golfer", "Golfer", "pass1234")
    r = {"course": "GC", "tees": "White", "total_gross": "80",
         "differential": "10.0", "computed_handicap": "10.0",
         "holes_selection": "all", "entry_mode": "detailed", "holes": {}}
    save_round(r, "2026-05-01", 0, user_id=1)
    delete_round("2026-05-01", "0", user_id=1)
    assert get_all_rounds(user_id=1) == []
    db.close()


def test_update_round_handicap(db):
    create_user("golfer", "Golfer", "pass1234")
    r = {"course": "GC", "tees": "White", "total_gross": "80",
         "differential": "10.0", "computed_handicap": "",
         "holes_selection": "all", "entry_mode": "detailed", "holes": {}}
    save_round(r, "2026-05-01", 0, user_id=1)
    update_round_handicap("2026-05-01", 0, 12.5, user_id=1)
    rounds = get_all_rounds(user_id=1)
    assert rounds[0].computed_handicap == "12.5"
    db.close()


def test_slope_rating_full_18(make_course):
    course = make_course()
    tee = course["Test GC"].tees["White"]
    tee_dict = {"slope": tee.slope, "rating": tee.rating}
    slope, rating = get_slope_rating(tee_dict, "all")
    assert slope == 128
    assert rating == 71.5


def test_slope_rating_front_9_fallback(make_course):
    course = make_course()
    tee = course["Test GC"].tees["White"]
    tee_dict = {"slope": tee.slope, "rating": tee.rating}
    slope, rating = get_slope_rating(tee_dict, "front")
    assert slope == 128
    assert rating == 71.5


def test_draft_save_load_clear(db):
    draft = {"step": 1, "course": "test"}
    save_course_draft(draft, user_id=1)
    loaded = load_course_draft(user_id=1)
    assert loaded == draft
    clear_course_draft(user_id=1)
    assert load_course_draft(user_id=1) is None
    db.close()


def test_round_draft_save_load_clear(db):
    draft = {"step": 1, "selected_course": "Test GC"}
    save_round_draft(draft, user_id=1)
    loaded = load_round_draft(user_id=1)
    assert loaded == draft
    clear_round_draft(user_id=1)
    assert load_round_draft(user_id=1) is None
    db.close()


def test_invite_code_flow(db):
    create_user("admin", "Admin", "pass1234")
    code = create_invite_code(created_by=1)
    assert code.startswith("PS-")

    assert is_invite_code_valid(code) is True
    assert is_invite_code_valid("PS-FAKE-CODE") is False

    create_user("user2", "User Two", "pass5678")
    consumed = consume_invite_code(code, used_by=2)
    assert consumed is True
    assert is_invite_code_valid(code) is False

    codes = get_invite_codes()
    assert len(codes) >= 1
    assert codes[0]["code"] == code
    assert codes[0]["used_by"] == 2
    db.close()


def test_get_users(db):
    create_user("a", "A", "pass1234")
    create_user("b", "B", "pass5678")
    users = get_users()
    assert len(users) == 2
    assert users[0]["username"] in ("a", "b")
    db.close()


def test_get_user_by_id(db):
    u = create_user("x", "X", "pass1234")
    found = get_user_by_id(u["id"])
    assert found is not None
    assert found["username"] == "x"
    assert get_user_by_id(999) is None
    db.close()


def test_rounds_isolated_by_user(db):
    create_user("u1", "U1", "pass1234")
    create_user("u2", "U2", "pass5678")
    r1 = {"course": "GC1", "tees": "W", "total_gross": "80",
          "differential": "10.0", "computed_handicap": "10.0",
          "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    r2 = {"course": "GC2", "tees": "B", "total_gross": "90",
          "differential": "20.0", "computed_handicap": "20.0",
          "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r1, "2026-05-01", 0, user_id=1)
    save_round(r2, "2026-05-01", 0, user_id=2)
    assert len(get_all_rounds(user_id=1)) == 1
    assert len(get_all_rounds(user_id=2)) == 1
    db.close()


class TestPluginStates:
    def test_seed_creates_enabled_row(self, db):
        from store import seed_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        states = get_plugin_states()
        assert states["test-plugin"] is True

    def test_seed_is_idempotent(self, db):
        from store import seed_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        seed_plugin_state("test-plugin")
        states = get_plugin_states()
        assert states["test-plugin"] is True

    def test_set_plugin_state_disables(self, db):
        from store import seed_plugin_state, set_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        set_plugin_state("test-plugin", False)
        states = get_plugin_states()
        assert states["test-plugin"] is False

    def test_set_plugin_state_re_enables(self, db):
        from store import seed_plugin_state, set_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        set_plugin_state("test-plugin", False)
        set_plugin_state("test-plugin", True)
        states = get_plugin_states()
        assert states["test-plugin"] is True

    def test_get_plugin_states_returns_empty_dict_when_no_rows(self, db):
        from store import get_plugin_states
        states = get_plugin_states()
        assert states == {}


def test_create_and_get_match(db):
    create_user("host", "Host", "pass1234")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    assert mid > 0
    match = get_match(mid)
    assert match is not None
    assert match["course_name"] == "Test GC"
    assert match["status"] == "active"
    assert match["player_count"] == 0
    assert match["round_count"] == 0
    db.close()


def test_get_match_nonexistent(db):
    assert get_match(999) is None
    db.close()


def test_get_all_matches_empty(db):
    assert get_all_matches() == []
    db.close()


def test_get_all_matches_returns_all(db):
    create_user("host", "Host", "pass1234")
    create_match(created_by=1, course_name="GC1", date="2026-06-01")
    create_match(created_by=1, course_name="GC2", date="2026-06-02")
    matches = get_all_matches()
    assert len(matches) == 2
    names = [m["course_name"] for m in matches]
    assert "GC1" in names
    assert "GC2" in names
    db.close()


def test_complete_match(db):
    create_user("host", "Host", "pass1234")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    complete_match(mid)
    match = get_match(mid)
    assert match["status"] == "completed"
    db.close()


def test_add_and_remove_match_player(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    pid = add_match_player(mid, user_id=2)
    assert pid > 0
    players = get_match_players(mid)
    assert len(players) == 1
    assert players[0]["user_id"] == 2
    assert players[0]["total_net"] == 0
    assert players[0]["round_count"] == 0
    removed = remove_match_player(mid, user_id=2)
    assert removed is True
    assert get_match_players(mid) == []
    db.close()


def test_add_duplicate_match_player_is_idempotent(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    add_match_player(mid, user_id=2)
    add_match_player(mid, user_id=2)
    assert len(get_match_players(mid)) == 1
    db.close()


def test_link_and_unlink_round(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    add_match_player(mid, user_id=2)
    r = {"course": "Test GC", "tees": "W", "total_gross": "80",
         "differential": "10.0", "computed_handicap": "10.0",
         "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r, "2026-06-01", 0, user_id=2)
    lid = link_round(mid, user_id=2, round_id=1, net=72.0)
    assert lid > 0
    rounds = get_match_rounds(mid)
    assert len(rounds) == 1
    assert rounds[0]["net"] == 72.0
    assert rounds[0]["user_name"] == "Player1"
    players = get_match_players(mid)
    assert players[0]["round_count"] == 1
    assert players[0]["total_net"] == 72.0
    unlinked = unlink_round(mid, user_id=2, round_id=1)
    assert unlinked is True
    assert get_match_rounds(mid) == []
    db.close()


def test_link_duplicate_round_is_idempotent(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    add_match_player(mid, user_id=2)
    r = {"course": "Test GC", "tees": "W", "total_gross": "80",
         "differential": "10.0", "computed_handicap": "10.0",
         "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r, "2026-06-01", 0, user_id=2)
    link_round(mid, user_id=2, round_id=1, net=72.0)
    link_round(mid, user_id=2, round_id=1, net=72.0)
    assert len(get_match_rounds(mid)) == 1
    db.close()


def test_multi_round_match_aggregation(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    create_user("p2", "Player2", "pass9012")
    mid = create_match(created_by=1, course_name="Test GC", date="2026-06-01")
    add_match_player(mid, user_id=2)
    add_match_player(mid, user_id=3)
    from database import get_db
    round_ids = {2: [], 3: []}
    for player_id in (2, 3):
        for day in (1, 2, 3):
            r = {"course": "Test GC", "tees": "W", "total_gross": str(70 + day),
                 "differential": str(day), "computed_handicap": "10.0",
                 "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
            save_round(r, f"2026-06-{day:02d}", 0, user_id=player_id)
            d = get_db()
            row = d.execute("SELECT id FROM rounds WHERE user_id = ? AND date = ? AND round_index = 0",
                            (player_id, f"2026-06-{day:02d}")).fetchone()
            rid = row["id"]
            d.close()
            round_ids[player_id].append(rid)
            net = 68.0 + day * (1 if player_id == 2 else 1.5)
            link_round(mid, user_id=player_id, round_id=rid, net=net)
    players = get_match_players(mid)
    assert len(players) == 2
    for p in players:
        assert p["round_count"] == 3
    assert players[0]["total_net"] < players[1]["total_net"]
    db.close()


def test_round_shared_across_matches(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    mid1 = create_match(created_by=1, course_name="GC1", date="2026-06-01")
    mid2 = create_match(created_by=1, course_name="GC2", date="2026-06-02")
    add_match_player(mid1, user_id=2)
    add_match_player(mid2, user_id=2)
    r = {"course": "Test GC", "tees": "W", "total_gross": "80",
         "differential": "10.0", "computed_handicap": "10.0",
         "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r, "2026-06-01", 0, user_id=2)
    link_round(mid1, user_id=2, round_id=1, net=72.0)
    link_round(mid2, user_id=2, round_id=1, net=72.0)
    assert len(get_match_rounds(mid1)) == 1
    assert len(get_match_rounds(mid2)) == 1
    db.close()


def test_create_and_get_challenge(db):
    create_user("host", "Host", "pass1234")
    cid = create_challenge(created_by=1, title="Longest Drive", stat_key="fir",
                           start_date="2026-06-01", end_date="2026-06-30")
    assert cid > 0
    chal = get_challenge(cid)
    assert chal is not None
    assert chal["title"] == "Longest Drive"
    assert chal["stat_key"] == "fir"
    assert chal["status"] == "active"
    db.close()


def test_get_challenge_nonexistent(db):
    assert get_challenge(999) is None
    db.close()


def test_get_all_challenges_empty(db):
    assert get_all_challenges() == []
    db.close()


def test_get_all_challenges_returns_all(db):
    create_user("host", "Host", "pass1234")
    create_challenge(created_by=1, title="C1", stat_key="score",
                     start_date="2026-06-01", end_date="2026-06-30")
    create_challenge(created_by=1, title="C2", stat_key="gir",
                     start_date="2026-07-01", end_date="2026-07-31")
    chals = get_all_challenges()
    assert len(chals) == 2
    titles = [c["title"] for c in chals]
    assert "C1" in titles
    assert "C2" in titles
    db.close()


def test_add_and_remove_challenge_participant(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    cid = create_challenge(created_by=1, title="Test Challenge", stat_key="score",
                           start_date="2026-06-01", end_date="2026-06-30")
    add_challenge_participant(cid, user_id=2)
    participants = get_challenge_participants(cid)
    assert participants == [2]
    removed = remove_challenge_participant(cid, user_id=2)
    assert removed is True
    assert get_challenge_participants(cid) == []
    db.close()


def test_add_duplicate_participant_is_idempotent(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    cid = create_challenge(created_by=1, title="Test", stat_key="score",
                           start_date="2026-06-01", end_date="2026-06-30")
    add_challenge_participant(cid, user_id=2)
    add_challenge_participant(cid, user_id=2)
    assert get_challenge_participants(cid) == [2]
    db.close()


def test_complete_challenge(db):
    create_user("host", "Host", "pass1234")
    cid = create_challenge(created_by=1, title="Test", stat_key="score",
                           start_date="2026-06-01", end_date="2026-06-30")
    complete_challenge(cid)
    chal = get_challenge(cid)
    assert chal["status"] == "completed"
    db.close()


def test_challenge_participant_count(db):
    create_user("host", "Host", "pass1234")
    create_user("p1", "Player1", "pass5678")
    create_user("p2", "Player2", "pass9012")
    cid = create_challenge(created_by=1, title="Test", stat_key="score",
                           start_date="2026-06-01", end_date="2026-06-30")
    chal = get_challenge(cid)
    assert chal["participant_count"] == 0
    add_challenge_participant(cid, user_id=2)
    add_challenge_participant(cid, user_id=3)
    chal = get_challenge(cid)
    assert chal["participant_count"] == 2
    db.close()


def test_recompute_all_handicaps(db):
    create_user("golfer", "Golfer", "pass1234")
    settings = {"include_9hole": True, "season_start_month": 1, "season_end_month": 12}
    save_settings(settings, user_id=1)

    for i in range(6):
        r = {"course": "GC", "tees": "W", "total_gross": str(70 + i),
             "differential": str(15 - i), "computed_handicap": "99.9",
             "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
        save_round(r, f"2026-05-{i+1:02d}", 0, user_id=1)

    recompute_all_handicaps()

    rounds = get_all_rounds(user_id=1)
    rounds.sort(key=lambda r: r.date)

    for r in rounds:
        assert r.computed_handicap not in (None, "", "0"), \
            f"round {r.date} has empty value ({r.computed_handicap})"
    assert rounds[-1].computed_handicap != "99.9"
    assert float(rounds[-1].computed_handicap) < 20.0
