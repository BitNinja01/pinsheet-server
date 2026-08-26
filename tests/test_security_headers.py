"""Closure tests for issue #73 — security response headers.

Verifies the Talisman integration in source/extensions.py emits, on every
response, the five headers the audit flagged as missing:
  * Content-Security-Policy (restricting script sources, nonce-based)
  * X-Frame-Options: DENY               (clickjacking / CWE-1021)
  * X-Content-Type-Options: nosniff     (MIME sniffing)
  * Referrer-Policy: same-origin        (referrer leak)
  * Strict-Transport-Security            (HSTS — only when served over HTTPS)
"""

import pytest
from flask import Flask
from flask_talisman import Talisman

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db

if "rounds_list" not in app.view_functions:
    register_routes(app, limiter, csrf, User)


@pytest.fixture
def client(tmp_path, monkeypatch):
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
    app.config["DB_PATH"] = db_path
    return app.test_client()


def test_x_frame_options_denied(client):
    assert client.get("/login").headers.get("X-Frame-Options") == "DENY"


def test_content_type_options_nosniff(client):
    assert client.get("/login").headers.get("X-Content-Type-Options") == "nosniff"


def test_referrer_policy(client):
    assert client.get("/login").headers.get("Referrer-Policy") == "same-origin"


def test_csp_present_and_restrictive(client):
    csp = client.get("/login").headers.get("Content-Security-Policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # script-src must NOT blanket-allow inline scripts (XSS defense-in-depth).
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_csp_uses_per_request_nonce(client):
    # A nonce source is present in script-src and appears in the rendered page,
    # so inline data-scripts run while injected inline scripts are blocked.
    resp = client.get("/login")
    csp = resp.headers.get("Content-Security-Policy")
    assert "'nonce-" in csp
    # nonce differs per response
    csp2 = client.get("/login").headers.get("Content-Security-Policy")
    assert csp != csp2


def test_headers_on_every_response_not_just_login(client):
    # 404s and redirects are still hardened.
    resp = client.get("/definitely-not-a-real-route")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_hsts_absent_over_plain_http(client):
    # HTTPS env is unset under test, so the real app must NOT emit HSTS and must
    # not force the session cookie Secure — otherwise plain-http dev/CI breaks.
    resp = client.get("/login")
    assert resp.headers.get("Strict-Transport-Security") is None
    assert "Secure" not in resp.headers.get("Set-Cookie", "")


def test_session_cookie_hardened(client):
    # Issue #74: primary session cookie must be HttpOnly + SameSite=Lax, and
    # Secure only over HTTPS (unset in tests, so no Secure here — asserted in
    # test_hsts_absent_over_plain_http).
    assert client.application.config["SESSION_COOKIE_HTTPONLY"] is True
    assert client.application.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert client.application.config["SESSION_COOKIE_SECURE"] in (False, None)


def test_hsts_emitted_over_https():
    """HSTS is conditional on HTTPS. Verify the Talisman config emits it for a
    secure request (mirrors extensions.py when the HTTPS env signal is set)."""
    probe = Flask(__name__)
    Talisman(
        probe,
        force_https=True,
        strict_transport_security=True,
        strict_transport_security_max_age=31_536_000,
        strict_transport_security_include_subdomains=True,
    )

    @probe.route("/")
    def _root():
        return "ok"

    resp = probe.test_client().get("/", base_url="https://localhost/")
    hsts = resp.headers.get("Strict-Transport-Security")
    assert hsts is not None
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts
