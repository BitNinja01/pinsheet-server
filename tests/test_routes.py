import json
import os

import pytest

import main as main_mod
from main import app, User
from database import set_db_path, init_db
from store import create_user


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Create a test Flask app with temp database."""
    main_mod.limiter.enabled = False

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
    app.config["SECRET_KEY"] = "test-secret-key"

    return app


@pytest.fixture
def client(test_app):
    return test_app.test_client()


def test_login_page_get(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_with_valid_credentials(test_app):
    create_user("player", "Player", "pass1234")
    client = test_app.test_client()
    resp = client.post("/login", data={
        "username": "player",
        "password": "pass1234",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_login_with_invalid_credentials(test_app):
    create_user("player", "Player", "pass1234")
    client = test_app.test_client()
    resp = client.post("/login", data={
        "username": "player",
        "password": "wrong",
    })
    assert resp.status_code == 200
    assert b"Invalid username or password" in resp.data


def test_register_page_get(client):
    resp = client.get("/register")
    assert resp.status_code == 200


def test_dashboard_redirects_when_not_logged_in(client):
    resp = client.get("/", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_rounds_list_redirects_when_not_logged_in(client):
    resp = client.get("/rounds", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_courses_redirects_when_not_logged_in(client):
    resp = client.get("/courses", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_stats_redirects_when_not_logged_in(client):
    resp = client.get("/stats", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_settings_redirects_when_not_logged_in(client):
    resp = client.get("/settings", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_season_redirects_when_not_logged_in(client):
    resp = client.get("/season", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_admin_redirects_when_not_logged_in(client):
    resp = client.get("/admin/invites", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_round_entry_redirects_when_not_logged_in(client):
    resp = client.get("/rounds/new", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_course_entry_redirects_when_not_logged_in(client):
    resp = client.get("/courses/new", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_logout_redirects_to_login(test_app):
    create_user("p", "P", "pass1234")
    client = test_app.test_client()
    client.post("/login", data={"username": "p", "password": "pass1234"})
    resp = client.get("/logout", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_404_for_unknown_route(client):
    resp = client.get("/nonexistent")
    assert resp.status_code == 404


def test_rounds_new_redirects_when_not_logged_in(client):
    resp = client.get("/rounds/new", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data


def test_course_list_redirects_when_not_logged_in(client):
    resp = client.get("/courses", follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower() or b"Login" in resp.data
