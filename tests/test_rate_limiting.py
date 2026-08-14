"""Closure tests for issue #75 — rate limiting beyond auth routes.

The Limiter previously had `default_limits=[]`, so only login/register/reset
were throttled. These verify a global per-IP default now applies, and that the
sensitive API-key minting route carries its own tighter cap.
"""

import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import create_user


def test_global_default_limit_configured():
    # Global baseline is set (was an empty list before #75).
    defaults = [str(l) for l in limiter.limit_manager.default_limits]
    assert defaults, "Limiter has no global default_limits"
    assert any("200" in d for d in defaults)


@pytest.fixture
def rl_app(tmp_path, monkeypatch):
    """App fixture with the limiter ENABLED (most fixtures disable it)."""
    try:
        register_routes(app, limiter, csrf, User)
    except AssertionError:
        pass

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
    app.config["DB_PATH"] = db_path

    limiter.enabled = True
    try:
        yield app
    finally:
        limiter.enabled = False  # restore shared-singleton default for other tests


def test_api_key_creation_is_rate_limited(rl_app):
    # api_keys_create carries @limiter.limit("10 per minute"); the 11th POST in
    # the window must be rejected with 429. A fresh process/db means the counter
    # for this endpoint+IP starts at zero.
    create_user("player", "Player", "pass1234")
    client = rl_app.test_client()
    client.post("/login", data={"username": "player", "password": "pass1234"})

    statuses = [
        client.post("/settings/api-keys", data={"label": f"k{i}"}).status_code
        for i in range(11)
    ]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
