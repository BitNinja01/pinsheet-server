import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import (
    create_user, verify_user,
    generate_password_reset_token, verify_password_reset_token,
)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Route registration happens here (not at import time) and is guarded,
    since the Flask `app` object is a process-wide singleton shared with
    other test modules that may register routes first or later depending
    on collection order.
    """
    try:
        register_routes(app, limiter, csrf, User)
    except AssertionError:
        pass

    main_mod.limiter.enabled = False

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

    return db_path


@pytest.fixture
def client(fresh_db):
    return app.test_client()


# ---------------------------------------------------------------------------
# /login "next" redirect handling (open-redirect protection, auth.py:26-27)
# ---------------------------------------------------------------------------

class TestLoginNextRedirect:
    def test_valid_relative_next_is_honored(self, client):
        create_user("player", "Player", "pass1234")
        resp = client.post(
            "/login?next=/bag",
            data={"username": "player", "password": "pass1234"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/bag"

    def test_protocol_relative_next_is_rejected(self, client):
        """`//evil.com` is a classic open-redirect payload; must not be honored."""
        create_user("player", "Player", "pass1234")
        resp = client.post(
            "/login?next=//evil.com/phish",
            data={"username": "player", "password": "pass1234"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"
        assert "evil.com" not in resp.headers["Location"]

    def test_absolute_url_next_is_rejected(self, client):
        create_user("player", "Player", "pass1234")
        resp = client.post(
            "/login?next=https://evil.com/phish",
            data={"username": "player", "password": "pass1234"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"

    def test_next_without_leading_slash_is_rejected(self, client):
        create_user("player", "Player", "pass1234")
        resp = client.post(
            "/login?next=evil.com",
            data={"username": "player", "password": "pass1234"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"


# ---------------------------------------------------------------------------
# /reset-password
# ---------------------------------------------------------------------------

class TestResetPasswordGet:
    def test_no_token_shows_invalid_error_and_no_form(self, client):
        resp = client.get("/reset-password")
        assert resp.status_code == 200
        assert b"Invalid or expired reset token" in resp.data
        assert b'class="auth-form"' not in resp.data

    def test_bogus_token_shows_invalid_error(self, client):
        resp = client.get("/reset-password?token=not-a-real-token")
        assert resp.status_code == 200
        assert b"Invalid or expired reset token" in resp.data

    def test_valid_token_shows_form_with_token_embedded(self, client):
        user = create_user("resetme", "Reset Me", "originalpass1")
        token = generate_password_reset_token(user["id"])

        resp = client.get(f"/reset-password?token={token}")
        assert resp.status_code == 200
        assert b"Invalid or expired reset token" not in resp.data
        assert f'value="{token}"'.encode() in resp.data

    def test_already_authenticated_user_is_redirected_away(self, client):
        create_user("loggedin", "Logged In", "pass12345")
        client.post("/login", data={"username": "loggedin", "password": "pass12345"})

        resp = client.get("/reset-password", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"


class TestResetPasswordPost:
    def test_invalid_token_rejected(self, client):
        resp = client.post("/reset-password", data={
            "token": "garbage-token",
            "new_password": "brandnewpass1",
            "confirm": "brandnewpass1",
        })
        assert resp.status_code == 200
        assert b"Invalid or expired reset token" in resp.data

    def test_weak_password_rejected_and_password_unchanged(self, client):
        user = create_user("weakpw", "Weak PW", "originalpass1")
        token = generate_password_reset_token(user["id"])

        resp = client.post("/reset-password", data={
            "token": token,
            "new_password": "short",
            "confirm": "short",
        })
        assert resp.status_code == 200
        assert b"Password must be at least 8 characters" in resp.data

        # Original password must still work; token must still be usable.
        assert verify_user("weakpw", "originalpass1") is not None
        assert verify_password_reset_token(token) is not None

    def test_mismatched_confirmation_rejected(self, client):
        user = create_user("mismatch", "Mismatch", "originalpass1")
        token = generate_password_reset_token(user["id"])

        resp = client.post("/reset-password", data={
            "token": token,
            "new_password": "newpassword1",
            "confirm": "different1",
        })
        assert resp.status_code == 200
        assert b"Passwords do not match" in resp.data
        assert verify_user("mismatch", "originalpass1") is not None
        assert verify_password_reset_token(token) is not None

    def test_successful_reset_changes_password_and_consumes_token(self, client):
        user = create_user("succeed", "Succeed", "originalpass1")
        token = generate_password_reset_token(user["id"])

        resp = client.post("/reset-password", data={
            "token": token,
            "new_password": "brandnewpass1",
            "confirm": "brandnewpass1",
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/login"

        assert verify_user("succeed", "brandnewpass1") is not None
        assert verify_user("succeed", "originalpass1") is None
        # Token is single-use.
        assert verify_password_reset_token(token) is None

    def test_token_cannot_be_reused(self, client):
        user = create_user("reuse", "Reuse", "originalpass1")
        token = generate_password_reset_token(user["id"])

        client.post("/reset-password", data={
            "token": token,
            "new_password": "firstchange1",
            "confirm": "firstchange1",
        })
        resp = client.post("/reset-password", data={
            "token": token,
            "new_password": "secondchange1",
            "confirm": "secondchange1",
        })
        assert resp.status_code == 200
        assert b"Invalid or expired reset token" in resp.data
        # Password from the *first* (successful) reset must remain active.
        assert verify_user("reuse", "firstchange1") is not None
        assert verify_user("reuse", "secondchange1") is None
