import pytest
from database import set_db_path, init_db, get_db
from store import save_round, get_all_rounds, create_user, recompute_all_handicaps


@pytest.fixture
def db_with_user(tmp_data_dir, monkeypatch):
    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", tmp_data_dir)
    db_path = str(tmp_data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()
    create_user("testuser", "Test User", "password123")
    return get_db()


def _save_test_round(locked=False, diff="18.0"):
    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "85",
        "differential": diff, "notes": "", "excluded": False,
        "computed_handicap": "14.0", "differential_locked": locked,
    }
    save_round(golf_round, "2026-01-15", 0, user_id=1)


def test_override_sets_lock(db_with_user):
    """Saving with differential_locked=True stores the value and sets locked=True."""
    _save_test_round(locked=False, diff="18.0")
    rounds = get_all_rounds(user_id=1)
    assert rounds[0].differential_locked is False

    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "85",
        "differential": "21.5", "notes": "", "excluded": False,
        "computed_handicap": "14.0", "differential_locked": True,
    }
    save_round(golf_round, "2026-01-15", 0, user_id=1)
    rounds = get_all_rounds(user_id=1)
    assert rounds[0].differential == "21.5"
    assert rounds[0].differential_locked is True
    db_with_user.close()


def test_clear_lock_resets_to_unlocked(db_with_user):
    """Saving with differential_locked=False clears the lock."""
    _save_test_round(locked=True, diff="21.5")

    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "85",
        "differential": "18.0", "notes": "", "excluded": False,
        "computed_handicap": "14.0", "differential_locked": False,
    }
    save_round(golf_round, "2026-01-15", 0, user_id=1)
    rounds = get_all_rounds(user_id=1)
    assert rounds[0].differential_locked is False
    db_with_user.close()


def test_locked_round_preserves_diff_through_recompute(db_with_user):
    """recompute_all_handicaps does not overwrite a locked differential."""
    golf_round = {
        "course": "Test GC", "tees": "White", "holes_played": "all",
        "entry_mode": "score_only", "holes": {}, "total_gross": "0",
        "differential": "21.5", "notes": "", "excluded": False,
        "computed_handicap": "", "differential_locked": True,
    }
    save_round(golf_round, "2026-01-15", 0, user_id=1)
    recompute_all_handicaps()
    rounds = get_all_rounds(user_id=1)
    assert rounds[0].differential == "21.5"
    db_with_user.close()
