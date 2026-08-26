import io
import json
import zipfile

import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import create_user, load_settings, get_courses, get_all_rounds


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

    def test_import_rejects_oversized_entry(self, logged_in_client):
        # A member that decompresses far past the per-entry cap is a zip bomb;
        # it compresses tiny but must be rejected before json.loads eats memory.
        big = "A" * (11 * 1024 * 1024)
        zip_bytes = _make_zip({"courses.json": big})
        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "bomb.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"too large" in resp.data
        # Nothing should have been persisted.
        assert get_courses() == {}

    def test_import_rejects_too_many_entries(self, logged_in_client):
        entries = {f"rounds/{i}.json": "{}" for i in range(1001)}
        zip_bytes = _make_zip(entries)
        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "many.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"too many entries" in resp.data

    def test_max_content_length_configured(self):
        # Upstream body cap must exist so oversized uploads are rejected (413)
        # before the route reads them into memory.
        assert app.config.get("MAX_CONTENT_LENGTH")

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

    def test_import_reshapes_legacy_tui_course_to_canonical(self, logged_in_client):
        course_payload = {
            "TuiGC": {
                "par": "72",
                "location": {"city": "Testville", "state": "WA", "country": "USA"},
                "holes": {
                    "1": {"par": 4, "hole_index": 7, "tees": {"blue": 377, "white": 362}},
                    "2": {"par": 3, "index": 15, "tees": {"blue": 150}},
                },
                "tees": {
                    "blue": {"slope": 120, "rating": 70.0, "yardage": "6000"},
                    "white": {"slope": 118, "rating": 68.9, "yardage": "5700"},
                },
            }
        }
        zip_bytes = _make_zip({"courses.json": json.dumps(course_payload)})
        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        courses = get_courses()
        saved = courses["TuiGC"]
        assert saved["holes"]["1"] == {"par": 4, "hole_index": 7}
        assert saved["holes"]["2"] == {"par": 3, "hole_index": 15}
        assert saved["tees"]["blue"]["yardages"] == {"1": "377", "2": "150"}
        assert saved["tees"]["white"]["yardages"] == {"1": "362"}

    def test_import_with_pcc_computes_differential_reflecting_pcc(self, logged_in_client):
        """WHS Rule 5.6: a zip-import round dict carrying 'pcc' must persist
        that pcc and have its recomputed differential (the settings.py
        inline backfill site) reflect the -PCC term -- same formula as
        calc_round_dif and store.py's recompute, exercised end-to-end
        through the actual /settings/import route this time (not the
        formula reproduced against stored data, as in test_handicap.py's
        consistency test)."""
        course_payload = {
            "ImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": "113", "rating": "72.0", "yardage": "6000"}},
            }
        }
        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "ImportGC",
                    "tees": "White",
                    "holes_selection": "all",
                    "total_gross": "90",
                    "differential": "0",
                    "computed_handicap": "",
                    "holes": {},
                    "pcc": 1.0,
                }
            },
            "2026-06-02": {
                "0": {
                    "course": "ImportGC",
                    "tees": "White",
                    "holes_selection": "all",
                    "total_gross": "90",
                    "differential": "0",
                    "computed_handicap": "",
                    "holes": {},
                }
            },
        }

        zip_bytes = _make_zip({
            "courses.json": json.dumps(course_payload),
            "rounds/2026.json": json.dumps(rounds_payload),
        })

        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "pcc_export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Imported 1 courses and 2 rounds." in resp.data

        rounds = {r.date: r for r in get_all_rounds(1)}
        # (113/113)*(90-72.0-1.0) = 17.0
        assert rounds["2026-06-01"].pcc == 1.0
        assert rounds["2026-06-01"].differential == "17.0"
        # (113/113)*(90-72.0-0.0) = 18.0 -- unaffected/default.
        assert rounds["2026-06-02"].pcc == 0.0
        assert rounds["2026-06-02"].differential == "18.0"

    def test_import_9hole_pcc_applies_half_not_full(self, logged_in_client):
        """WHS Rule 5.1b: a zip-imported 9-hole (front) round with pcc=+2.0
        must have its recomputed differential reflect only HALF the pcc
        (-1.0), not the full -2.0 -- same effective_pcc halving as the
        POST/PUT routes and store.py's recompute, now exercised through the
        settings.py import inline site end-to-end. AGS=45, slope=113,
        rating=36.0 -> half-pcc diff = (113/113)*(45-36-1.0) = 8.0, full-pcc
        would be 7.0."""
        course_payload = {
            "NineImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": "113", "rating": "36.0", "yardage": "6000"}},
            }
        }
        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "NineImportGC",
                    "tees": "White",
                    "holes_selection": "front",
                    "total_gross": "45",
                    "differential": "0",
                    "computed_handicap": "",
                    "holes": {},
                    "pcc": 2.0,
                }
            },
        }

        zip_bytes = _make_zip({
            "courses.json": json.dumps(course_payload),
            "rounds/2026.json": json.dumps(rounds_payload),
        })

        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "nine_pcc_export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Imported 1 courses and 1 rounds." in resp.data

        rounds = get_all_rounds(1)
        assert len(rounds) == 1
        assert rounds[0].holes_selection == "front"
        assert rounds[0].pcc == 2.0
        assert rounds[0].differential == "8.0"
        assert rounds[0].differential != "7.0"  # would be 7.0 at the (wrong) full pcc

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

    def test_import_recompute_slope_zero_legacy_course_does_not_crash(self, logged_in_client):
        """CV-001 zip-import path: settings.py's post-import recompute loop
        (~line 120-121) inlines the same `113 / tee_slope` division as
        store.py's recompute_handicaps_for_user and calc_round_dif -- it
        does NOT call calc_round_dif directly, so it would be just as
        vulnerable to a ZeroDivisionError on a slope="0" tee if it divided
        BEFORE calling get_slope_rating. Verified by reading the code:
        `slope, rating = get_slope_rating(tee_data, r.holes_selection)`
        (line 120) runs immediately before `113 / slope` (line 121), so
        `get_slope_rating`'s `safe_positive_float` fallback already
        protects this call site -- prove it end-to-end.

        The bad-slope course is seeded via `store.save_course` directly
        (bypassing courses.json import, which would otherwise sanitize
        slope="0" to "" via `_coerce_course_numerics(strict=False)` before
        this recompute loop ever runs) to simulate legacy/pre-fix data
        that predates the write-time guard, then only rounds.json is
        imported against it.
        """
        from store import save_course

        save_course(
            {
                "location": {},
                "tees": {"White": {"slope": "0", "rating": "70", "yardage": "6000"}},
                "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
                "par": "72",
            },
            "LegacyZeroSlopeGC",
        )

        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "LegacyZeroSlopeGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "80", "differential": "0", "computed_handicap": "", "holes": {},
                },
            }
        }
        zip_bytes = _make_zip({"rounds/2026.json": json.dumps(rounds_payload)})

        # Must not 500 (ZeroDivisionError) -- a clean 200 import response.
        resp = logged_in_client.post(
            "/settings/import",
            data={"zipfile": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rounds = get_all_rounds(1)
        assert len(rounds) == 1
        diff = float(rounds[0].differential)
        # slope correctly falls back to 113 (no base slope to use):
        # diff = round((113/113) * (80 - 70), 1) = 10.0 -- sane, not a
        # ZeroDivisionError and not an absurd inflated value.
        assert diff == 10.0

    def test_import_requires_login(self, test_app):
        client = test_app.test_client()
        resp = client.get("/settings/import", follow_redirects=True)
        assert b"login" in resp.data.lower() or b"Login" in resp.data

    def test_import_windows_handicap_to_recent_20_for_more_than_20_rounds(self, logged_in_client):
        """WHS Rule 5.2 windowing regression via the /settings/import path.

        settings.py's per-round handicap computation must window to the most
        recent 20 ELIGIBLE differentials -- neither the old unbounded
        oldest-first `chronological[:i+1]` bug, nor a raw <=20 slice. 25
        rounds with distinct, already-nonzero differentials (so the
        differential-recompute branch is a no-op and this isolates the
        windowing behavior); assert the most-recent round's persisted
        computed_handicap matches a direct
        calc_handicap_index(most-recent-first full list) call."""
        course_payload = {
            "ImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": 120, "rating": 70.0, "yardage": "6000"}},
            }
        }
        diffs = [17.1, 27.1, 20.8, 21.9, 15.3, 23.8, 18.0, 23.8, 22.6, 25.3,
                 21.1, 29.8, 21.5, 23.8, 23.2, 23.2, 31.1, 22.6, 25.7, 24.8,
                 21.7, 25.3, 37.1, 25.6, 33.6]  # 25 distinct differentials
        rounds_payload = {}
        for i, d in enumerate(diffs):
            day = 25 - i  # i=0 -> day 25 (most recent), i=24 -> day 1 (oldest)
            date_str = f"2026-06-{day:02d}"
            rounds_payload[date_str] = {
                "0": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": "85", "differential": str(d),
                    "computed_handicap": "", "holes": {},
                },
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
        assert b"Imported 1 courses and 25 rounds." in resp.data

        rounds = get_all_rounds(1)  # most-recent-first (ORDER BY date DESC)
        assert len(rounds) == 25

        from calc.handicap import calc_handicap_index
        expected_hi = calc_handicap_index(rounds, include_9hole=True)
        assert expected_hi is not None
        assert rounds[0].computed_handicap == str(expected_hi)

        # Sanity: prove the fixture exercises windowing -- an unwindowed
        # (old-bug-style) calc over the full 25 gives a DIFFERENT value
        # (19.7 best-8-of-all-25 vs 19.8 windowed best-8-of-recent-20).
        unwindowed_hi = calc_handicap_index(rounds, include_9hole=True, window=None)
        assert unwindowed_hi != expected_hi

    def test_import_recomputes_esc_adjusted_differential_for_blowup_hole(self, logged_in_client):
        """WHS Rule 3 (Net Double Bogey) / Rule 12: a zip-imported detailed
        round with a blow-up hole (par 4, gross 10, no stroke received) must
        have its Score Differential recomputed from the ESC-adjusted gross
        (that hole capped to par+2 == 6), NOT raw total_gross. Before the
        fix, /settings/import wrote the raw-total_gross differential (23.5);
        after the fix it writes the ESC-adjusted differential (19.8), using
        the course_handicap==0 "no prior HI established yet" fallback since
        this is the only (first) round in the import. See
        tests/test_e2e_rounds_scores.py::
        test_live_and_recompute_agree_on_esc_adjusted_differential_with_blowup_hole
        for the live-vs-recompute equality check once a real prior Handicap
        Index exists."""
        course_payload = {
            "ImportGC": {
                "par": "72",
                "holes": {str(n): {"par": 4, "hole_index": n} for n in range(1, 19)},
                "tees": {"White": {"slope": 120, "rating": 70.0, "yardage": "6000"}},
            }
        }
        holes = {str(n): {"gross": "5", "putts": "2"} for n in range(1, 19)}
        holes["1"] = {"gross": "10", "putts": "2"}  # blow-up hole, no stroke received
        raw_total = sum(int(h["gross"]) for h in holes.values())
        assert raw_total == 95  # bogey-all-18 (90) minus hole-1 bogey (5) plus blowup (10)

        rounds_payload = {
            "2026-06-01": {
                "0": {
                    "course": "ImportGC", "tees": "White", "holes_selection": "all",
                    "total_gross": str(raw_total), "differential": "0",
                    "computed_handicap": "", "holes": holes,
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
        assert b"Imported 1 courses and 1 rounds." in resp.data

        rounds = get_all_rounds(1)
        assert len(rounds) == 1
        imported_round = rounds[0]

        raw_differential = round((113 / 120) * (raw_total - 70.0), 1)
        esc_total = raw_total - 10 + 6  # hole 1 blowup (10) capped to par+2 (6)
        esc_differential = round((113 / 120) * (esc_total - 70.0), 1)

        assert raw_differential == 23.5
        assert esc_differential == 19.8
        assert imported_round.differential == str(esc_differential), (
            f"import wrote raw-total_gross differential "
            f"{imported_round.differential!r} (raw would be "
            f"{raw_differential!r}) instead of the ESC-adjusted "
            f"{esc_differential!r} -- WHS Rule 3 (Net Double Bogey) / "
            f"Rule 12 violation."
        )
        assert imported_round.differential != str(raw_differential)
