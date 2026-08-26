import json
import os
import sqlite3

import pytest

from database import set_db_path, init_db, get_db
from store import (
    load_settings, save_settings,
    get_courses, save_course, delete_course, rename_course,
    get_all_rounds, save_round, delete_round, update_round_handicap,
    recompute_all_handicaps, recompute_handicaps_for_user,
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
    reshape_course_data,
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


# --- reshape_course_data: legacy TUI shape -> canonical server shape ---

LEGACY_COURSE = {
    "name": "Bellevue Municipal",
    "location": {"city": "Bellevue", "state": "WA"},
    "par": 70,
    "holes": {
        "1": {"par": 4, "hole_index": 7, "tees": {"blue": 377, "white": 362}},
        "2": {"par": 3, "index": 15, "tees": {"blue": 150, "white": 120}},
    },
    "tees": {
        "blue": {"rating": 70.5, "slope": 121, "yardage": 6100},
        "white": {"rating": 68.9, "slope": 118, "yardage": 5700},
    },
}


def test_reshape_course_data_moves_legacy_per_hole_tees_to_canonical():
    out = reshape_course_data(json.loads(json.dumps(LEGACY_COURSE)))
    assert out["holes"]["1"] == {"par": 4, "hole_index": 7}
    assert out["holes"]["2"] == {"par": 3, "hole_index": 15}
    assert out["tees"]["blue"]["yardages"] == {"1": "377", "2": "150"}
    assert out["tees"]["white"]["yardages"] == {"1": "362", "2": "120"}
    assert "tees" not in out["holes"]["1"]
    assert "tees" not in out["holes"]["2"]


def test_reshape_course_data_renames_index_to_hole_index():
    course = {
        "holes": {"1": {"par": 5, "index": 11}},
        "tees": {},
    }
    out = reshape_course_data(course)
    assert out["holes"]["1"] == {"par": 5, "hole_index": 11}


def test_reshape_course_data_is_idempotent_on_canonical():
    canonical = {
        "par": 72,
        "holes": {"1": {"par": 5, "hole_index": 11}},
        "tees": {"Husky": {"rating": 75.5, "slope": 143, "yardage": 7304,
                          "yardages": {"1": "560"}}},
    }
    out = reshape_course_data(json.loads(json.dumps(canonical)))
    assert out == canonical


def test_reshape_course_data_canonical_yardages_win_over_legacy():
    course = {
        "holes": {"1": {"par": 4, "hole_index": 3, "tees": {"blue": 377}}},
        "tees": {"blue": {"rating": 70.5, "slope": 121, "yardage": 6100,
                          "yardages": {"1": "380"}}},
    }
    out = reshape_course_data(course)
    assert out["tees"]["blue"]["yardages"]["1"] == "380"


def test_reshape_course_data_preserves_unrelated_keys():
    course = dict(LEGACY_COURSE)
    course["holes_remaining"] = {"10": {"par": 4, "hole_index": 2}}
    course["tees_remaining"] = {"blue": {"rating": 35.0, "slope": 120, "yardage": 3050}}
    out = reshape_course_data(json.loads(json.dumps(course)))
    assert "holes_remaining" in out
    assert "tees_remaining" in out
    assert out["location"] == {"city": "Bellevue", "state": "WA"}
    assert out["par"] == 70
    assert out["tees"]["blue"]["rating"] == 70.5
    assert out["tees"]["blue"]["slope"] == 121
    assert out["tees"]["blue"]["yardage"] == 6100


def test_reshape_course_data_does_not_mutate_input():
    course = json.loads(json.dumps(LEGACY_COURSE))
    reshape_course_data(course)
    assert "tees" in course["holes"]["1"]
    assert course["tees"]["blue"].get("yardages") is None


def test_differential_locked_column_exists(db):
    cols = db.execute("PRAGMA table_info(rounds)").fetchall()
    col_names = [c["name"] for c in cols]
    assert "differential_locked" in col_names
    db.close()


def test_dict_to_round_reads_differential_locked():
    from source.models import dict_to_round
    r = dict_to_round({"differential_locked": True, "differential": "21.5"})
    assert r.differential_locked is True


def test_dict_to_round_defaults_differential_locked_false():
    from source.models import dict_to_round
    r = dict_to_round({"differential": "21.5"})
    assert r.differential_locked is False


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


def test_save_and_load_round_preserves_differential_locked(db):
    create_user("golfer", "Golfer", "pass1234")
    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "85",
        "differential": "21.5", "notes": "", "excluded": False,
        "computed_handicap": "19.8", "differential_locked": True,
    }
    save_round(golf_round, "2026-01-01", 0, user_id=1)
    rounds = get_all_rounds(user_id=1)
    assert len(rounds) == 1
    assert rounds[0].differential_locked is True
    assert rounds[0].differential == "21.5"
    db.close()


def test_update_round_differential_skips_locked_round(db):
    from store import update_round_differential
    create_user("golfer", "Golfer", "pass1234")
    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "85",
        "differential": "21.5", "notes": "", "excluded": False,
        "computed_handicap": "19.8", "differential_locked": True,
    }
    save_round(golf_round, "2026-01-01", 0, user_id=1)
    update_round_differential("2026-01-01", 0, 18.0, user_id=1)
    rounds = get_all_rounds(user_id=1)
    assert rounds[0].differential == "21.5"  # unchanged
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


def test_slope_rating_blank_values_fall_back_to_defaults():
    # A tee saved with blank slope/rating (the edit UI sends "" for an empty
    # field) must not crash the differential calc — it falls back to defaults,
    # matching the behaviour of a wholly-absent key.
    slope, rating = get_slope_rating({"slope": "", "rating": ""}, "all")
    assert slope == 113.0
    assert rating == 72.0


def test_slope_rating_none_values_fall_back_to_defaults():
    slope, rating = get_slope_rating({"slope": None, "rating": None}, "all")
    assert slope == 113.0
    assert rating == 72.0


def test_slope_rating_blank_front_falls_through_to_18hole_value():
    # Blank front_slope/front_rating should use the 18-hole slope/rating, not
    # the hard default.
    slope, rating = get_slope_rating(
        {"front_slope": "", "front_rating": "", "slope": "118", "rating": "70.1"},
        "front",
    )
    assert slope == 118.0
    assert rating == 70.1


def test_slope_rating_blank_values_fall_back_no_crash():
    """WHS R13 follow-up: blank ("") slope/rating is explicitly allowed by
    routes/courses.py:_coerce_course_numerics ("Blank/missing values are
    left as-is"). `get_slope_rating` previously did
    `float(tee_data.get("slope", 113))` directly -- since the key IS
    present (just blank), the default never applied and float("") raised
    ValueError, crashing every round-save / differential-calc call site
    (rounds, matches, dashboard, settings). Assert blank falls back to the
    sane default instead of crashing.
    """
    slope, rating = get_slope_rating({"slope": "", "rating": ""}, "all")
    assert (slope, rating) == (113, 72.0)

    slope, rating = get_slope_rating(
        {"slope": "", "rating": "", "front_slope": "", "front_rating": ""}, "front"
    )
    assert (slope, rating) == (113, 72.0)

    # Real (non-blank) base slope/rating still used when front_/back_
    # variants are blank -- blank must fall back to the base field, not
    # skip straight to the hardcoded default.
    slope, rating = get_slope_rating(
        {"slope": 131, "rating": 76.0, "back_slope": "", "back_rating": ""}, "back"
    )
    assert (slope, rating) == (131, 76.0)


def test_slope_rating_zero_slope_never_returned():
    """CV-001 (Critical): "0" is NOT blank -- it parses to a real float, but
    slope=0 is domain-invalid (calc_round_dif divides `113 / tee_slope`,
    a ZeroDivisionError -> 500 at round-save time). `get_slope_rating`
    must never return a slope <= 0; a literal "0" (or negative) slope
    falls back the same as a missing/blank one.
    """
    slope, rating = get_slope_rating({"slope": "0", "rating": "70"}, "all")
    assert slope != 0
    assert slope == 113  # no base slope to fall back to -> hardcoded default
    assert rating == 70.0  # rating itself was valid, untouched

    slope, rating = get_slope_rating({"slope": "-5", "rating": "70"}, "all")
    assert slope > 0
    assert slope == 113

    # front_slope "0" must fall back to the (valid) base slope, not to 0.
    slope, rating = get_slope_rating({"slope": "125", "front_slope": "0", "rating": "70"}, "front")
    assert slope == 125


def test_slope_rating_zero_rating_never_returned():
    """DA-001 (Major): a rating of 0 poisons the Score Differential
    (`adjusted_gross_score - tee_rating` is hugely inflated when rating
    collapses to 0), corrupting the WHS Rule 5.2 Handicap Index -- not
    just a display stat. `get_slope_rating` must never return a rating
    <= 0.
    """
    slope, rating = get_slope_rating({"slope": "125", "rating": "0"}, "all")
    assert rating != 0
    assert rating == 72.0  # no base rating to fall back to -> hardcoded default

    # front_rating "0" must fall back to the (valid) base rating, not to 0.
    slope, rating = get_slope_rating({"slope": "125", "rating": "76.0", "front_rating": "0"}, "front")
    assert rating == 76.0


def test_recompute_handicaps_rating_zero_tee_does_not_poison_differential(db):
    """DA-001 end-to-end: a round played on a rating="0" tee must not
    produce an absurdly inflated Score Differential during
    recompute_handicaps_for_user -- get_slope_rating's rating<=0 fallback
    (-> base rating, else 72.0) must be honored by the recompute path
    (store.py:~413), not just by callers that re-derive slope/rating
    independently.
    """
    from store import create_user, save_course, save_round, recompute_handicaps_for_user, get_all_rounds

    user = create_user("recomputeuser", "Recompute User", "pass1234")
    course = {
        "location": {},
        "tees": {"White": {"yardage": "6000", "rating": "0", "slope": "125"}},
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "par": "72",
    }
    save_course(course, "ZeroRatingGC")
    golf_round = {
        "date": "2026-01-01",
        "course": "ZeroRatingGC",
        "tees": "White",
        "holes_played": "18",
        "holes_selection": "all",
        "total_gross": "80",
        "differential": "0",
    }
    save_round(golf_round, "2026-01-01", 0, user_id=user["id"])
    recompute_handicaps_for_user(user["id"])
    rounds = get_all_rounds(user_id=user["id"])
    diff = float(rounds[0].differential)
    # With rating correctly falling back to 72.0 (no base rating to use):
    # diff = round((113/125) * (80 - 72), 1) = 7.2 -- nowhere near the
    # absurd ~72-strokes-inflated value rating=0 would have produced
    # (round((113/125) * (80 - 0), 1) == 72.3).
    assert 0 < diff < 20


def test_recompute_handicaps_slope_zero_tee_does_not_crash_or_poison_differential(db):
    """CV-001 end-to-end: `recompute_handicaps_for_user` (store.py:~412-413)
    inlines the same `113 / tee_slope` division as `calc_round_dif`
    directly (it does NOT call `calc_round_dif`), so a slope="0" tee is
    just as capable of raising ZeroDivisionError there as at round-save
    time. This is safe ONLY because `get_slope_rating` (called
    immediately before the division, line ~412) already applies
    `safe_positive_float` and never returns slope<=0 -- prove it: no
    exception, and a sane (not ZeroDivisionError-adjacent-absurd)
    differential, mirroring the rating=0 recompute test above.
    """
    from store import create_user, save_course, save_round, recompute_handicaps_for_user, get_all_rounds

    user = create_user("reslopeuser", "Recompute Slope User", "pass1234")
    course = {
        "location": {},
        "tees": {"White": {"yardage": "6000", "rating": "70", "slope": "0"}},
        "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
        "par": "72",
    }
    save_course(course, "ZeroSlopeGC")
    golf_round = {
        "date": "2026-01-01",
        "course": "ZeroSlopeGC",
        "tees": "White",
        "holes_played": "18",
        "holes_selection": "all",
        "total_gross": "80",
        "differential": "0",
    }
    save_round(golf_round, "2026-01-01", 0, user_id=user["id"])
    # Must not raise ZeroDivisionError.
    recompute_handicaps_for_user(user["id"])
    rounds = get_all_rounds(user_id=user["id"])
    diff = float(rounds[0].differential)
    # With slope correctly falling back to 113 (no base slope to use):
    # diff = round((113/113) * (80 - 70), 1) = 10.0.
    assert diff == 10.0


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
    def test_seed_creates_disabled_row(self, db):
        # Provenance gate: a newly discovered plugin is seeded DISABLED — an
        # admin must explicitly enable (validate) it before its code runs.
        from store import seed_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        states = get_plugin_states()
        assert states["test-plugin"] is False

    def test_seed_is_idempotent(self, db):
        # seed must not re-disable a plugin an admin already enabled
        from store import seed_plugin_state, set_plugin_state, get_plugin_states
        seed_plugin_state("test-plugin")
        set_plugin_state("test-plugin", True)
        seed_plugin_state("test-plugin")  # INSERT OR IGNORE — must not reset
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

    for i, r in enumerate(rounds):
        if i < 2:
            assert r.computed_handicap in ("", None), \
                f"round {r.date} (index {i}) should be empty, got {r.computed_handicap}"
        else:
            assert r.computed_handicap not in (None, "", "0"), \
                f"round {r.date} (index {i}) has empty value ({r.computed_handicap})"
    assert rounds[-1].computed_handicap != "99.9"
    assert float(rounds[-1].computed_handicap) < 20.0


class _FakeConn:
    """Minimal connection stub whose execute() raises, to prove link_round/unlink_round
    always close the connection (try/finally) even when the SQL fails."""
    def __init__(self):
        self.closed = False

    def execute(self, *a, **k):
        raise sqlite3.OperationalError("boom")

    def commit(self):
        pass

    def close(self):
        self.closed = True


def test_link_round_closes_connection_on_error(monkeypatch):
    import store as store_mod
    fake = _FakeConn()
    monkeypatch.setattr(store_mod, "get_db", lambda: fake)
    with pytest.raises(sqlite3.OperationalError):
        link_round(1, 1, 1, 70.0)
    assert fake.closed is True


def test_unlink_round_closes_connection_on_error(monkeypatch):
    import store as store_mod
    fake = _FakeConn()
    monkeypatch.setattr(store_mod, "get_db", lambda: fake)
    with pytest.raises(sqlite3.OperationalError):
        unlink_round(1, 1, 1)
    assert fake.closed is True


# --------------------------------------------------------------------------
# WHS Rule 12 / Rule 3 (Net Double Bogey): recompute_handicaps_for_user must
# derive the Score Differential from the ESC-adjusted gross for detailed
# rounds, not raw total_gross -- otherwise a blow-up hole is over-counted
# relative to the SAME round entered live (source/routes/rounds.py).
# --------------------------------------------------------------------------

# 18-hole par map matching the fixture used by test_e2e_rounds_scores.py --
# par-3s at 4/8/12/16, par-5s at 2/6/10/14/18, rest par-4. TOTAL_PAR == 73.
_R12_PARS = {n: (3 if n in (4, 8, 12, 16) else 5 if n in (2, 6, 10, 14, 18) else 4)
             for n in range(1, 19)}
_R12_TOTAL_PAR = sum(_R12_PARS.values())  # 73


def _r12_course():
    return {
        "par": str(_R12_TOTAL_PAR),
        "holes": {str(n): {"par": _R12_PARS[n], "hole_index": n} for n in range(1, 19)},
        "tees": {"White": {"slope": 128, "rating": 71.5}},
    }


def _r12_holes_with_blowup(blowup_hole="1", blowup_gross=10):
    """Bogey (par+1) on every hole except `blowup_hole`, which gets
    `blowup_gross` -- a detailed round with one blow-up hole and no strokes
    received (course_handicap 0, no prior HI)."""
    holes = {}
    for n, par in _R12_PARS.items():
        hn = str(n)
        gross = blowup_gross if hn == blowup_hole else par + 1
        holes[hn] = {"gross": str(gross), "putts": "2"}
    return holes


def test_recompute_uses_esc_adjusted_gross_not_raw_total(db):
    """A detailed round with a blow-up hole (par 4, gross 10, no stroke
    received) must have its Score Differential computed from the
    ESC-adjusted gross (that hole capped to Net Double Bogey == par+2 == 6),
    NOT the raw total_gross. This is the R12 bug: before the fix, this
    round's recompute-path differential was 21.6 (raw); after the fix it is
    18.1 (ESC, using the course_handicap==0 "no prior HI established yet"
    fallback -- there is no round before this one in the fixture).

    NOTE: this is a store.py-unit-level check of that fallback specifically,
    not a live-vs-recompute equality check -- the live POST /api/rounds path
    only attempts the ESC adjustment once calc_handicap_index can return a
    value (WHS needs >= 3 acceptable scores), so it skips ESC entirely (not
    even a course_handicap==0 cap) for a player's first 1-2 rounds. See
    tests/test_e2e_rounds_scores.py::
    test_live_and_recompute_agree_on_esc_adjusted_differential_with_blowup_hole
    for the true live-vs-recompute equality check, exercised once a real
    prior Handicap Index exists (the common case R12 targets)."""
    create_user("golfer", "Golfer", "pass1234")
    save_course(_r12_course(), "GC")

    holes = _r12_holes_with_blowup()
    raw_total = sum(int(h["gross"]) for h in holes.values())
    assert raw_total == 96  # bogey-all-18 (91) minus hole-1 bogey (5) plus blowup (10)

    r = {"course": "GC", "tees": "White", "total_gross": str(raw_total),
         "differential": "0", "computed_handicap": "",
         "holes_selection": "all", "entry_mode": "detailed", "holes": holes}
    save_round(r, "2026-05-01", 0, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    saved = get_all_rounds(user_id=1)[0]
    raw_differential = round((113 / 128) * (raw_total - 71.5), 1)
    esc_total = raw_total - 10 + 6  # hole 1 blowup (10) capped to par+2 (6)
    esc_differential = round((113 / 128) * (esc_total - 71.5), 1)

    assert raw_differential == 21.6
    assert esc_differential == 18.1
    assert saved.differential == str(esc_differential), (
        f"recompute wrote raw-total_gross differential {saved.differential!r} "
        f"(raw would be {raw_differential!r}) instead of the ESC-adjusted "
        f"{esc_differential!r} -- WHS Rule 3 (Net Double Bogey) / Rule 12 "
        f"violation."
    )
    assert saved.differential != str(raw_differential)


def test_recompute_score_only_round_still_uses_raw_total(db):
    """A score-only round (no per-hole data) has nothing to ESC-cap -- the
    recompute path must keep using raw total_gross as the Adjusted Gross
    Score, unchanged by the R12 fix."""
    create_user("golfer", "Golfer", "pass1234")
    save_course(_r12_course(), "GC")

    r = {"course": "GC", "tees": "White", "total_gross": "96",
         "differential": "0", "computed_handicap": "",
         "holes_selection": "all", "entry_mode": "score_only", "holes": {}}
    save_round(r, "2026-05-01", 0, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    saved = get_all_rounds(user_id=1)[0]
    expected = round((113 / 128) * (96 - 71.5), 1)
    assert saved.differential == str(expected)


# --------------------------------------------------------------------------
# WHS 9-hole Score Differential combine: recompute_handicaps_for_user must
# fill a missing ("0") 9-hole differential with the base 9-hole differential
# plus the expected 9-hole adjustment keyed on the prior displayed HI
# (handicap_index * 0.52 + 1.197), matching the TUI's expected-score
# equation.
# --------------------------------------------------------------------------


def _r12_course_with_front():
    """_r12_course plus front-9 tee slope/rating so get_slope_rating("front")
    resolves to 128 / 35.7 instead of falling back to the 18-hole values."""
    course = _r12_course()
    course["tees"]["White"]["front_slope"] = 128
    course["tees"]["White"]["front_rating"] = 35.7
    return course


def test_recompute_backfills_9hole_round_with_combine(db):
    """A 9-hole score-only round with the "0" differential sentinel must be
    backfilled with base + prior_hi * 0.52 + 1.197, where prior_hi is the
    computed_handicap the recompute assigns to the last chronologically-prior
    round (read AFTER recompute -- the recompute may adjust it). base =
    round((113/128)*(45-35.7), 1) = 8.2."""
    create_user("golfer", "Golfer", "pass1234")
    save_course(_r12_course_with_front(), "GC")

    for d, diff, ch in (("2026-05-01", "10.0", "10.0"),
                        ("2026-05-02", "12.0", "12.0"),
                        ("2026-05-03", "11.0", "11.0")):
        save_round({"course": "GC", "tees": "White", "total_gross": "90",
                    "differential": diff, "computed_handicap": ch,
                    "holes_selection": "all", "entry_mode": "score_only", "holes": {}},
                   d, 0, user_id=1)

    save_round({"course": "GC", "tees": "White", "total_gross": "45",
                "differential": "0", "computed_handicap": "",
                "holes_selection": "front", "entry_mode": "score_only", "holes": {}},
               "2026-06-01", 0, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    saved = get_all_rounds(user_id=1)
    nine_hole = next(r for r in saved if r.holes_selection == "front")
    prior = next(r for r in saved if r.date < "2026-06-01")

    base = round((113 / 128) * (45 - 35.7), 1)
    assert base == 8.2
    assert float(prior.computed_handicap) > 0, "the fixture must establish a HI"
    expected = round(base + float(prior.computed_handicap) * 0.52 + 1.197, 1)
    assert nine_hole.differential == str(expected)
    assert nine_hole.differential != "0"


def test_recompute_backfills_9hole_round_without_prior_hi_uses_raw_base(db):
    """No prior rounds -> no established HI -> the 9-hole differential is the
    raw base 9-hole Score Differential (no combine term)."""
    create_user("golfer", "Golfer", "pass1234")
    save_course(_r12_course_with_front(), "GC")

    save_round({"course": "GC", "tees": "White", "total_gross": "45",
                "differential": "0", "computed_handicap": "",
                "holes_selection": "front", "entry_mode": "score_only", "holes": {}},
               "2026-06-01", 0, user_id=1)

    recompute_handicaps_for_user(user_id=1)

    saved = get_all_rounds(user_id=1)[0]
    base = round((113 / 128) * (45 - 35.7), 1)
    assert saved.differential == str(base)
