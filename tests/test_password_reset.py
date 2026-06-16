import pytest

from store import (
    generate_password_reset_token,
    verify_password_reset_token,
    consume_password_reset_token,
    update_password,
    create_user,
    verify_user,
)
from database import set_db_path, init_db


@pytest.fixture
def store_db(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()
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
