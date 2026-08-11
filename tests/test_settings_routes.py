import io
import json
import zipfile

import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import (
    create_user, load_settings, get_courses, get_all_rounds,
    save_course, save_round,
)


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Flask app with an isolated temp DB per test (mirrors test_routes.py).

    Route registration happens here (not at import time) and is guarded,
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
    app.config["DB_PATH"] = db_path

    return app


@pytest.fixture
def logged_in_client(test_app):
    create_user("player", "Player", "pass1234")
    c = test_app.test_client()
    c.post("/login", data={"username": "player", "password": "pass1234"})
    return c


def _make_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------

class TestSettingsPage:
    def test_settings_page_loads(self, logged_in_client):
        resp = logged_in_client.get("/settings")
        assert resp.status_code == 200
        assert b"Settings" in resp.data

    def test_settings_page_reflects_saved_theme(self, logged_in_client):
        resp = logged_in_client.put("/api/settings", json={"theme": "light"})
        assert resp.status_code == 200

        resp = logged_in_client.get("/settings")
        html = resp.data.decode()
        # The light-theme swatch must be marked active once persisted.
        light_swatch = html[html.index('theme-swatch-light'):html.index('theme-swatch-light') + 200]
        assert 'data-active="true"' in light_swatch


# ---------------------------------------------------------------------------
# /api/settings PUT
# ---------------------------------------------------------------------------

class TestApiSettingsPut:
    def test_put_persists_settings_for_user(self, logged_in_client):
        resp = logged_in_client.put("/api/settings", json={"theme": "light", "include_9hole": False})
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}

        saved = load_settings(1)
        assert saved["theme"] == "light"
        assert saved["include_9hole"] is False

    def test_put_merges_with_existing_settings(self, logged_in_client):
        logged_in_client.put("/api/settings", json={"theme": "light"})
        logged_in_client.put("/api/settings", json={"handicap_target": 12.5})

        saved = load_settings(1)
        # Both keys must survive -- save_settings merges rather than overwrites.
        assert saved["theme"] == "light"
        assert saved["handicap_target"] == 12.5

    def test_requires_login(self, test_app):
        client = test_app.test_client()
        resp = client.put("/api/settings", json={"theme": "light"})
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# /settings/import
# ---------------------------------------------------------------------------

class TestSettingsImport:
    def test_import_page_get(self, logged_in_client):
        resp = logged_in_client.get("/settings/import")
        assert resp.status_code == 200
        assert b"Imported" not in resp.data

    def test_import_no_file_shows_error(self, logged_in_client):
        resp = logged_in_client.post("/settings/import", data={})
        assert resp.status_code == 200
        assert b"No file provided" in resp.data

    def test_import_invalid_zip_shows_error(self, logged_in_client):
        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(b"not a zip file"), "bad.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Invalid zip file" in resp.data

    def test_import_valid_zip_persists_courses_rounds_and_settings(self, logged_in_client):
        course_payload = {
            "ImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": 120, "rating": 70.0, "yardage": "6000"}},
            }
        }
        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "ImportGC",
                    "tees": "White",
                    "holes_selection": "all",
                    "total_gross": "85",
                    "differential": "0",
                    "computed_handicap": "",
                    "holes": {},
                }
            }
        }
        settings_payload = {"theme": "light", "include_9hole": True}

        zip_bytes = _make_zip({
            "courses.json": json.dumps(course_payload),
            "rounds/2026.json": json.dumps(rounds_payload),
            "settings.json": json.dumps(settings_payload),
        })

        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Imported 1 courses and 1 rounds." in resp.data

        courses = get_courses()
        assert "ImportGC" in courses

        rounds = get_all_rounds(1)
        assert len(rounds) == 1
        imported_round = rounds[0]
        # Differential was "0" on import -> route must recompute it from
        # slope/rating rather than leaving it at "0".
        assert imported_round.differential not in ("0", "", None)
        assert float(imported_round.differential) == pytest.approx((113 / 120) * (85 - 70.0), abs=0.05)
        # A single round is below the WHS minimum (3) for a handicap index,
        # so computed_handicap correctly stays unset -- not a bug.
        assert imported_round.computed_handicap == ""

        saved_settings = load_settings(1)
        assert saved_settings["theme"] == "light"

    def test_import_recomputes_differentials_and_feeds_handicap_calc(self, logged_in_client):
        """Regression test for the fixed settings_import differential-staleness bug.

        The recompute loop writes each freshly-computed differential to the DB
        (update_round_differential) AND refreshes the in-memory RoundData.differential
        so the handicap window below sees the new value instead of a stale "0".
        calc_effective_diffs() skips any round whose .differential is "0"; before
        the fix every freshly-imported ("0") round was filtered out of every window,
        so update_round_handicap could never fire for a legacy import. After the fix,
        once a full window exists (3 all-18 rounds -> count_table_n(3)=1) the
        most-recent round gets a computed handicap.
        """
        course_payload = {
            "ImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": 120, "rating": 70.0, "yardage": "6000"}},
            }
        }
        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "85", "differential": "0", "computed_handicap": "", "holes": {},
                },
                "1": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "88", "differential": "0", "computed_handicap": "", "holes": {},
                },
                "2": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "80", "differential": "0", "computed_handicap": "", "holes": {},
                },
            }
        }
        zip_bytes = _make_zip({
            "courses.json": json.dumps(course_payload),
            "rounds/2026.json": json.dumps(rounds_payload),
        })

        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Imported 1 courses and 3 rounds." in resp.data

        rounds = get_all_rounds(1)
        assert len(rounds) == 3
        # Differentials are correctly recomputed and persisted to DB...
        assert all(r.differential not in ("0", "", None) for r in rounds)
        # ...and the fresh in-memory differentials now feed the handicap calc,
        # so at least one round (the one with a full 3-round window) gets a
        # non-empty computed_handicap. Before the fix this was always "".
        assert any(r.computed_handicap not in ("", None) for r in rounds)

    def test_import_computes_handicap_when_source_differentials_already_nonzero(self, logged_in_client):
        """Positive case for settings.py line 86: when imported rounds already
        carry non-"0" differentials (skipping the buggy recompute block
        entirely), the in-memory objects stay fresh and calc_handicap_index
        can successfully compute + persist a handicap once 3 rounds exist.
        """
        course_payload = {
            "ImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": 120, "rating": 70.0, "yardage": "6000"}},
            }
        }
        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "85", "differential": "12.0", "computed_handicap": "", "holes": {},
                },
                "1": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "88", "differential": "14.0", "computed_handicap": "", "holes": {},
                },
                "2": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "80", "differential": "8.0", "computed_handicap": "", "holes": {},
                },
            }
        }
        zip_bytes = _make_zip({
            "courses.json": json.dumps(course_payload),
            "rounds/2026.json": json.dumps(rounds_payload),
        })

        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rounds = get_all_rounds(1)
        assert len(rounds) == 3
        # get_all_rounds orders newest-first; index 0 is round #2 (index=2),
        # the 3rd chronologically, which is the first to have a full 3-round
        # window and therefore the first to get a computed_handicap.
        assert rounds[0].computed_handicap not in ("", None)

    def test_import_requires_login(self, test_app):
        client = test_app.test_client()
        resp = client.get("/settings/import", follow_redirects=True)
        assert b"login" in resp.data.lower() or b"Login" in resp.data


# ---------------------------------------------------------------------------
# Admin: recalculate handicap scores (forced resync)
# ---------------------------------------------------------------------------

class TestAdminRecomputeHandicaps:
    def test_admin_button_renders_on_settings_page(self, logged_in_client):
        # logged_in_client's "player" is the first user -> admin.
        resp = logged_in_client.get("/settings")
        assert resp.status_code == 200
        assert b'id="btn-recompute-handicaps"' in resp.data

    def test_admin_recompute_forces_resync(self, logged_in_client):
        # Save a round with a stale differential, then correct the course; the
        # forced resync must repropagate the new slope/rating.
        save_course({"par": 72, "tees": {"W": {"slope": "113", "rating": "72"}}, "holes": {}}, "GC")
        save_round({"course": "GC", "tees": "W", "total_gross": "90", "differential": "15.0",
                    "computed_handicap": "", "holes_selection": "all",
                    "entry_mode": "score_only", "holes": {}}, "2026-05-01", 0, user_id=1)

        resp = logged_in_client.post("/api/admin/recompute-handicaps")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        # (113/113)*(90-72) = 18.0
        assert get_all_rounds(1)[0].differential == "18.0"

    def test_non_admin_recompute_forbidden(self, test_app):
        create_user("owner", "Owner", "pass1234")   # first user -> admin
        create_user("guest", "Guest", "pass1234")   # second user -> non-admin
        c = test_app.test_client()
        c.post("/login", data={"username": "guest", "password": "pass1234"})
        resp = c.post("/api/admin/recompute-handicaps")
        assert resp.status_code == 403

    def test_non_admin_settings_page_hides_button(self, test_app):
        create_user("owner", "Owner", "pass1234")
        create_user("guest", "Guest", "pass1234")
        c = test_app.test_client()
        c.post("/login", data={"username": "guest", "password": "pass1234"})
        resp = c.get("/settings")
        assert resp.status_code == 200
        assert b'id="btn-recompute-handicaps"' not in resp.data
