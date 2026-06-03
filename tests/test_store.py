import json
import os
import sqlite3

import pytest

from database import set_db_path, init_db, get_db
from store import (
    load_settings, save_settings,
    get_courses, save_course, delete_course, rename_course,
    get_all_rounds, save_round, delete_round, update_round_handicap,
    get_slope_rating,
    save_course_draft, load_course_draft, clear_course_draft,
    save_round_draft, load_round_draft, clear_round_draft,
    get_users, get_user, get_user_by_id, create_user, verify_user,
    user_count, real_user_count,
    is_invite_code_valid, consume_invite_code, create_invite_code, get_invite_codes,
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
    for expected in ("users", "courses", "rounds", "settings", "invite_codes"):
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
        from source.store import seed_plugin_state, get_plugin_states, set_plugin_state
        seed_plugin_state("test-plugin")
        states = get_plugin_states()
        assert states["test-plugin"] is True

    def test_seed_is_idempotent(self, db):
        from source.store import seed_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        seed_plugin_state("test-plugin")
        states = get_plugin_states()
        assert states["test-plugin"] is True

    def test_set_plugin_state_disables(self, db):
        from source.store import seed_plugin_state, set_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        set_plugin_state("test-plugin", False)
        states = get_plugin_states()
        assert states["test-plugin"] is False

    def test_set_plugin_state_re_enables(self, db):
        from source.store import seed_plugin_state, set_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        set_plugin_state("test-plugin", False)
        set_plugin_state("test-plugin", True)
        states = get_plugin_states()
        assert states["test-plugin"] is True

    def test_get_plugin_states_returns_empty_dict_when_no_rows(self, db):
        from source.store import get_plugin_states
        states = get_plugin_states()
        assert states == {}
