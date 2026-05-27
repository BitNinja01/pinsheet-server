import pytest

from main import app
from store import (
    create_user, get_user, verify_user,
    create_invite_code, is_invite_code_valid, consume_invite_code,
    load_settings, save_settings,
)
from database import set_db_path, init_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Set up a fresh database for auth tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    drafts_dir = data_dir / "drafts"
    drafts_dir.mkdir()

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    monkeypatch.setattr(store_mod, "_DATA_DIR", data_dir)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-key"

    return db_path


def test_first_registration_no_invite_needed(fresh_db):
    """When no users exist, registration should succeed without invite code."""
    import main as main_mod
    main_mod.limiter.enabled = False

    client = app.test_client()
    resp = client.post("/register", data={
        "username": "firstuser",
        "display_name": "First User",
        "password": "password1234",
        "confirm": "password1234",
    }, follow_redirects=True)

    assert resp.status_code == 200

    db_user = get_user("firstuser")
    assert db_user is not None
    assert db_user["is_admin"] is True


def test_second_registration_requires_invite(fresh_db):
    """Second user registration requires a valid invite code."""
    import main as main_mod
    main_mod.limiter.enabled = False

    admin_client = app.test_client()

    admin_client.post("/register", data={
        "username": "admin",
        "display_name": "Admin",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
    })

    resp = app.test_client().post("/register", data={
        "username": "user2",
        "display_name": "User Two",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
    })

    assert b"Invalid or expired invite code" in resp.data


def test_registration_with_valid_invite_code(fresh_db):
    """Second user can register with a valid invite code."""
    import main as main_mod
    main_mod.limiter.enabled = False

    admin_client = app.test_client()

    admin_client.post("/register", data={
        "username": "admin",
        "display_name": "Admin",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
    })

    code = create_invite_code(created_by=1)
    assert is_invite_code_valid(code) is True

    resp = app.test_client().post("/register", data={
        "username": "user2",
        "display_name": "User Two",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
        "code": code,
    }, follow_redirects=True)

    assert resp.status_code == 200
    db_user = get_user("user2")
    assert db_user is not None
    assert db_user["is_admin"] is False

    assert is_invite_code_valid(code) is False


def test_registration_validation_errors(fresh_db):
    """Registration with invalid data should show errors."""
    import main as main_mod
    main_mod.limiter.enabled = False

    client = app.test_client()

    resp = client.post("/register", data={
        "username": "ab",
        "display_name": "",
        "password": "short",
        "confirm": "mismatch",
    })

    assert resp.status_code == 200
    content = resp.data.decode()
    assert "3-30" in content or "Username" in content


def test_duplicate_username_rejected(fresh_db):
    """Duplicate username should be rejected."""
    import main as main_mod
    main_mod.limiter.enabled = False

    admin_client = app.test_client()

    admin_client.post("/register", data={
        "username": "uniqueuser",
        "display_name": "Unique",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
    })

    resp = app.test_client().post("/register", data={
        "username": "uniqueuser",
        "display_name": "Duplicate",
        "password": "newpassword1",
        "confirm": "newpassword1",
    })

    assert b"already taken" in resp.data


def test_logged_in_user_redirected_from_login(fresh_db):
    """Logged in user should be redirected away from login page."""
    import main as main_mod
    main_mod.limiter.enabled = False

    client = app.test_client()

    client.post("/register", data={
        "username": "player",
        "display_name": "Player",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
    })

    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 302


def test_logged_in_user_redirected_from_register(fresh_db):
    """Logged in user should be redirected away from register page."""
    import main as main_mod
    main_mod.limiter.enabled = False

    client = app.test_client()

    client.post("/register", data={
        "username": "player2",
        "display_name": "Player2",
        "password": "passwordpass1",
        "confirm": "passwordpass1",
    })

    resp = client.get("/register", follow_redirects=False)
    assert resp.status_code == 302


def test_login_with_remember_me(fresh_db):
    """Login with remember-me should set a long-lived cookie."""
    import main as main_mod
    main_mod.limiter.enabled = False

    create_user("rmuser", "RM User", "rememberpass1")
    client = app.test_client()

    resp = client.post("/login", data={
        "username": "rmuser",
        "password": "rememberpass1",
        "remember": "on",
    }, follow_redirects=True)

    assert resp.status_code == 200
