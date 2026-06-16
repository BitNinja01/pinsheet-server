import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes

from store import (
    generate_password_reset_token,
    verify_password_reset_token,
    consume_password_reset_token,
    update_password,
    create_user,
    verify_user,
)
from database import set_db_path, init_db

register_routes(app, limiter, csrf, User)


@pytest.fixture
def store_db(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    drafts_dir = data_dir / "drafts"
    drafts_dir.mkdir()
    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    import store as store_mod
    import main as main_mod2
    main_mod2.limiter.enabled = False
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"

    return db_path


def test_generate_token_returns_string(store_db):
    user = create_user("alice", "Alice", "password123")
    token = generate_password_reset_token(user["id"])
    assert isinstance(token, str)
    assert len(token) > 20


def test_verify_valid_token_returns_user(store_db):
    user = create_user("bob", "Bob", "password123")
    token = generate_password_reset_token(user["id"])
    result = verify_password_reset_token(token)
    assert result is not None
    assert result["id"] == user["id"]
    assert result["username"] == "bob"


def test_verify_invalid_token_returns_none(store_db):
    result = verify_password_reset_token("this-is-not-a-real-token")
    assert result is None


def test_verify_consumed_token_returns_none(store_db):
    user = create_user("charlie", "Charlie", "password123")
    token = generate_password_reset_token(user["id"])
    consume_password_reset_token(token)
    result = verify_password_reset_token(token)
    assert result is None


def test_update_password_changes_hash(store_db):
    user = create_user("dave", "Dave", "oldpassword123")
    update_password(user["id"], "newpassword456")
    verified = verify_user("dave", "newpassword456")
    assert verified is not None
    old_verified = verify_user("dave", "oldpassword123")
    assert old_verified is None


def test_full_reset_flow(store_db):
    user = create_user("eve", "Eve", "originalpass1")
    token = generate_password_reset_token(user["id"])
    assert verify_password_reset_token(token) is not None
    update_password(user["id"], "resetpass123")
    consume_password_reset_token(token)
    assert verify_user("eve", "resetpass123") is not None
    assert verify_password_reset_token(token) is None


def test_admin_can_generate_reset_token(store_db):
    main_mod.limiter.enabled = False

    admin = create_user("admin1", "Admin", "adminpass123")
    create_user("userx", "User X", "userpass123")

    client = app.test_client()
    client.post("/login", data={"username": "admin1", "password": "adminpass123"})

    resp = client.post("/admin/invites", data={"reset_user_id": "2"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Reset Link Generated" in resp.data


def test_non_admin_cannot_generate_reset_token(store_db):
    main_mod.limiter.enabled = False

    create_user("admin1", "Admin", "adminpass123")
    regular = create_user("regular", "Regular", "regularpass")

    client = app.test_client()
    client.post("/login", data={"username": "regular", "password": "regularpass"})

    resp = client.post("/admin/invites", data={"reset_user_id": "1"}, follow_redirects=True)
    assert resp.status_code == 403
