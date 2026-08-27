import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import create_user, get_courses, save_course


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
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def logged_in_client(test_app):
    create_user("player", "Player", "pass1234")
    c = test_app.test_client()
    c.post("/login", data={"username": "player", "password": "pass1234"})
    return c


@pytest.fixture
def non_admin_client(test_app):
    """A logged-in, non-admin user. The first-created user is auto-admin, so an
    admin is created first to force the second user (the one we log in) to be a
    regular player."""
    create_user("owner", "Owner", "pass1234")   # first user -> admin
    create_user("guest", "Guest", "pass1234")   # second user -> non-admin
    c = test_app.test_client()
    c.post("/login", data={"username": "guest", "password": "pass1234"})
    return c


VALID_COURSE = {
    "name": "Pebble Valley",
    "location": {"city": "Testville", "state/province": "TS", "country": "Testland"},
    "tees": {"White": {"yardage": "6200", "rating": "70.5", "slope": "125"}},
    "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
    "par": 72,
}


# ---------------------------------------------------------------------------
# /api/courses POST (create)
# ---------------------------------------------------------------------------

class TestApiCoursesPost:
    def test_create_course_persists_to_store(self, logged_in_client):
        resp = logged_in_client.post("/api/courses", json=VALID_COURSE)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"ok": True, "name": "Pebble Valley"}

        courses = get_courses()
        assert "Pebble Valley" in courses
        assert courses["Pebble Valley"]["location"]["city"] == "Testville"
        assert courses["Pebble Valley"]["tees"]["White"]["slope"] == "125"

    def test_missing_name_rejected(self, logged_in_client):
        payload = dict(VALID_COURSE)
        payload["name"] = "   "
        resp = logged_in_client.post("/api/courses", json=payload)
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "Name is required"}
        assert get_courses() == {}

    def test_missing_location_city_rejected(self, logged_in_client):
        payload = dict(VALID_COURSE)
        payload["location"] = {"state/province": "TS", "country": "Testland"}
        resp = logged_in_client.post("/api/courses", json=payload)
        assert resp.status_code == 400
        assert "City, state/province, and country" in resp.get_json()["error"]
        assert get_courses() == {}

    def test_location_not_a_dict_rejected(self, logged_in_client):
        payload = dict(VALID_COURSE)
        payload["location"] = "Somewhere, TS"
        resp = logged_in_client.post("/api/courses", json=payload)
        assert resp.status_code == 400
        assert get_courses() == {}

    def test_requires_login(self, client):
        resp = client.post("/api/courses", json=VALID_COURSE)
        assert resp.status_code in (302, 401)
        assert get_courses() == {}


# ---------------------------------------------------------------------------
# /api/courses/<name> DELETE
# ---------------------------------------------------------------------------

class TestApiCoursesDelete:
    def test_delete_existing_course(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        assert "Pebble Valley" in get_courses()

        resp = logged_in_client.delete("/api/courses/Pebble Valley")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        assert "Pebble Valley" not in get_courses()

    def test_delete_blocked_when_rounds_exist(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        round_data = {
            "date": "2026-06-01",
            "course": "Pebble Valley",
            "tees": "White",
            "holes_played": "18",
            "entry_mode": "score_only",
            "gross_total": "85",
            "holes": {},
        }
        create_resp = logged_in_client.post("/api/rounds", json=round_data)
        assert create_resp.status_code == 200

        resp = logged_in_client.delete("/api/courses/Pebble Valley")
        assert resp.status_code == 409
        assert resp.get_json() == {"error": "Cannot delete course with existing rounds"}
        # Course must still exist since deletion was blocked.
        assert "Pebble Valley" in get_courses()


# ---------------------------------------------------------------------------
# /api/courses/<name> PUT (update / rename)
# ---------------------------------------------------------------------------

class TestApiCoursesPut:
    def test_put_course_not_found(self, logged_in_client):
        resp = logged_in_client.put("/api/courses/DoesNotExist", json=VALID_COURSE)
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "Course not found"}

    def test_put_missing_name_rejected(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["name"] = ""
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "Name is required"}

    def test_put_rename_conflict_rejected(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        other = dict(VALID_COURSE)
        other["name"] = "Other GC"
        logged_in_client.post("/api/courses", json=other)

        payload = dict(VALID_COURSE)
        payload["name"] = "Other GC"
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 409
        assert "already exists" in resp.get_json()["error"]
        # Neither course should have been mutated.
        courses = get_courses()
        assert "Pebble Valley" in courses
        assert "Other GC" in courses

    def test_put_updates_in_place_without_rename(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["location"] = {"city": "Newtown", "state/province": "TS", "country": "Testland"}
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Pebble Valley"

        courses = get_courses()
        assert "Pebble Valley" in courses
        assert courses["Pebble Valley"]["location"]["city"] == "Newtown"

    def test_put_missing_location_rejected(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["location"] = {"city": "", "state/province": "TS", "country": "Testland"}
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "City, state/province, and country are required"}
        # Store must be left unmutated: original location is still in place.
        courses = get_courses()
        assert courses["Pebble Valley"]["location"]["city"] == "Testville"

    def test_put_rejects_non_positive_slope(self, logged_in_client):
        """CV-001 write-path guard applies to PUT (course edit) same as
        POST (course create) -- api_courses_put calls the same
        `_coerce_course_numerics`. slope "0" -> 400, nothing persisted
        (the course's original valid slope/rating survive unmutated)."""
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["tees"] = {"White": {"yardage": "6200", "rating": "70.5", "slope": "0"}}
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 400
        courses = get_courses()
        assert courses["Pebble Valley"]["tees"]["White"]["slope"] == "125"  # unmutated

        payload["tees"] = {"White": {"yardage": "6200", "rating": "-1", "slope": "125"}}
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 400
        courses = get_courses()
        assert courses["Pebble Valley"]["tees"]["White"]["rating"] == "70.5"  # unmutated


# ---------------------------------------------------------------------------
# /api/courses hole-key validation (canonical stroke-index key is "hole_index")
# ---------------------------------------------------------------------------

class TestApiCoursesHoleKeyValidation:
    @staticmethod
    def _bad_holes():
        return {str(n): {"par": "4", "index": str(n)} for n in range(1, 19)}

    def test_post_rejects_wrong_index_key(self, logged_in_client):
        payload = dict(VALID_COURSE)
        payload["holes"] = self._bad_holes()
        resp = logged_in_client.post("/api/courses", json=payload)
        assert resp.status_code == 400
        assert "hole_index" in resp.get_json()["error"]
        assert get_courses() == {}

    def test_put_rejects_wrong_index_key_and_leaves_store_unchanged(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["holes"] = self._bad_holes()
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 400
        assert "hole_index" in resp.get_json()["error"]
        courses = get_courses()
        assert "Pebble Valley" in courses
        holes = courses["Pebble Valley"]["holes"]
        assert all("hole_index" in h for h in holes.values())
        assert all("index" not in h for h in holes.values())

    def test_post_valid_course_with_hole_index_still_succeeds(self, logged_in_client):
        resp = logged_in_client.post("/api/courses", json=VALID_COURSE)
        assert resp.status_code == 200
        assert "Pebble Valley" in get_courses()

    def test_put_edit_form_payload_with_hole_index_succeeds(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["location"] = {"city": "Editville", "state/province": "TS", "country": "Testland"}
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 200
        courses = get_courses()
        assert courses["Pebble Valley"]["location"]["city"] == "Editville"
        holes = courses["Pebble Valley"]["holes"]
        assert all("hole_index" in h for h in holes.values())
        assert all("index" not in h for h in holes.values())

    def test_post_holes_null_rejected_cleanly(self, logged_in_client):
        payload = dict(VALID_COURSE)
        payload["holes"] = None
        resp = logged_in_client.post("/api/courses", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "holes must be an object"
        assert get_courses() == {}

    def test_put_rename_with_bad_holes_rejected_before_rename(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        payload = dict(VALID_COURSE)
        payload["name"] = "Renamed GC"
        payload["holes"] = self._bad_holes()
        resp = logged_in_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 400
        courses = get_courses()
        assert "Pebble Valley" in courses
        assert "Renamed GC" not in courses


# ---------------------------------------------------------------------------
# /courses (list) and /courses/<name> (detail)
# ---------------------------------------------------------------------------

class TestCourseList:
    def test_empty_course_list(self, logged_in_client):
        resp = logged_in_client.get("/courses")
        assert resp.status_code == 200

    def test_course_list_sorted_case_insensitively_with_play_counts(self, logged_in_client):
        # "Banana GC" starts with an uppercase 'B' (66) and "apple GC" starts
        # with a lowercase 'a' (97). A raw (case-sensitive) sort would put
        # "Banana GC" *before* "apple GC", which is the wrong alphabetical
        # order -- only .lower()-keyed sorting produces apple, Banana, cherry.
        for name in ("cherry GC", "Banana GC", "apple GC"):
            payload = dict(VALID_COURSE)
            payload["name"] = name
            logged_in_client.post("/api/courses", json=payload)

        # Play "apple GC" once so play_count/last_played show up.
        round_data = {
            "date": "2026-06-01",
            "course": "apple GC",
            "tees": "White",
            "holes_played": "18",
            "entry_mode": "score_only",
            "gross_total": "85",
            "holes": {},
        }
        logged_in_client.post("/api/rounds", json=round_data)

        resp = logged_in_client.get("/courses")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Case-insensitive alphabetical sort: apple, Banana, cherry
        assert html.index("apple GC") < html.index("Banana GC") < html.index("cherry GC")


class TestCourseDetail:
    def test_course_not_found_returns_404(self, logged_in_client):
        resp = logged_in_client.get("/courses/NoSuchCourse")
        assert resp.status_code == 404
        assert b"Course not found" in resp.data

    def test_course_detail_shows_hole_yardage_fallback(self, logged_in_client):
        # Tee has no per-hole "yardages" map -> route must fall back to
        # the hole's own "tees" yardage dict (courses.py lines 76-78).
        course = {
            "location": {"city": "C", "state/province": "S", "country": "Ctry"},
            "tees": {"White": {"yardage": "6000", "rating": "70.0", "slope": "120"}},
            "holes": {
                "1": {"par": 4, "hole_index": 1, "tees": {"White": "355"}},
                "2": {"par": 5, "hole_index": 2, "tees": {"White": "512"}},
            },
            "par": 72,
        }
        save_course(course, "FallbackGC")

        resp = logged_in_client.get("/courses/FallbackGC")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "355" in html
        assert "512" in html

    def test_course_detail_sorts_holes_numerically_not_lexically(self, logged_in_client):
        course = {
            "location": {"city": "C", "state/province": "S", "country": "Ctry"},
            "tees": {},
            "holes": {
                "10": {"par": 4, "hole_index": 10},
                "2": {"par": 5, "hole_index": 2},
                "1": {"par": 4, "hole_index": 1},
            },
            "par": 72,
        }
        save_course(course, "NumericSortGC")

        resp = logged_in_client.get("/courses/NumericSortGC")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Numeric sort => hole "2" must render before hole "10".
        assert html.index(">2<") < html.index(">10<")

    def test_course_detail_edit_mode_flag(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        resp = logged_in_client.get("/courses/Pebble Valley?edit=1")
        assert resp.status_code == 200
        assert b'id="btn-save-course"' in resp.data

        resp2 = logged_in_client.get("/courses/Pebble Valley")
        assert b'id="btn-save-course"' not in resp2.data
        assert b'id="btn-edit-course"' in resp2.data

    def test_course_detail_tracks_play_count_and_dates(self, logged_in_client):
        logged_in_client.post("/api/courses", json=VALID_COURSE)
        for date in ("2026-05-01", "2026-06-01"):
            round_data = {
                "date": date,
                "course": "Pebble Valley",
                "tees": "White",
                "holes_played": "18",
                "entry_mode": "score_only",
                "gross_total": "85",
                "holes": {},
            }
            resp = logged_in_client.post("/api/rounds", json=round_data)
            assert resp.status_code == 200

        resp = logged_in_client.get("/courses/Pebble Valley")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Times Played</span> 2</div>' in html
        assert "2026-05-01" in html
        assert "2026-06-01" in html


class TestCourseEntry:
    def test_course_entry_page_loads(self, logged_in_client):
        resp = logged_in_client.get("/courses/new")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin-only course management (issue #37)
# ---------------------------------------------------------------------------

class TestCourseAdminGate:
    def test_non_admin_post_forbidden_and_store_unchanged(self, non_admin_client):
        resp = non_admin_client.post("/api/courses", json=VALID_COURSE)
        assert resp.status_code == 403
        assert get_courses() == {}

    def test_non_admin_put_forbidden_and_store_unchanged(self, non_admin_client):
        save_course({
            "location": {"city": "Testville", "state/province": "TS", "country": "Testland"},
            "tees": {}, "holes": {}, "par": 72,
        }, "Pebble Valley")
        payload = dict(VALID_COURSE)
        payload["location"] = {"city": "Hacked", "state/province": "TS", "country": "Testland"}
        resp = non_admin_client.put("/api/courses/Pebble Valley", json=payload)
        assert resp.status_code == 403
        # Course must be untouched.
        assert get_courses()["Pebble Valley"]["location"]["city"] == "Testville"

    def test_non_admin_delete_forbidden_and_store_unchanged(self, non_admin_client):
        save_course({
            "location": {"city": "Testville", "state/province": "TS", "country": "Testland"},
            "tees": {}, "holes": {}, "par": 72,
        }, "Pebble Valley")
        resp = non_admin_client.delete("/api/courses/Pebble Valley")
        assert resp.status_code == 403
        assert "Pebble Valley" in get_courses()

    def test_non_admin_courses_new_redirects_to_list(self, non_admin_client):
        resp = non_admin_client.get("/courses/new")
        assert resp.status_code == 302
        assert "/courses" in resp.headers["Location"]

    def test_non_admin_cannot_enter_edit_mode(self, non_admin_client):
        save_course({
            "location": {"city": "Testville", "state/province": "TS", "country": "Testland"},
            "tees": {}, "holes": {}, "par": 72,
        }, "Pebble Valley")
        resp = non_admin_client.get("/courses/Pebble Valley?edit=1")
        assert resp.status_code == 200
        # Editor controls must not render for a non-admin, even with ?edit=1.
        assert b'id="btn-save-course"' not in resp.data
        assert b'id="btn-edit-course"' not in resp.data

    def test_non_admin_course_list_hides_add_button(self, non_admin_client):
        resp = non_admin_client.get("/courses")
        assert resp.status_code == 200
        assert b"/courses/new" not in resp.data

    def test_admin_post_still_succeeds(self, logged_in_client):
        # logged_in_client's "player" is the first user -> admin.
        resp = logged_in_client.post("/api/courses", json=VALID_COURSE)
        assert resp.status_code == 200
        assert "Pebble Valley" in get_courses()


# ---------------------------------------------------------------------------
# Stored-XSS regression (finding U1 / GH#68): course_detail.html must never
# render a stored tee/hole numeric field as raw HTML.
# ---------------------------------------------------------------------------

class TestCourseDetailStoredXss:
    def test_html_payload_in_tee_yardage_rejected_at_write_path(self, logged_in_client):
        payload = dict(VALID_COURSE)
        payload["tees"] = {"White": {"yardage": "<img src=x onerror=alert(1)>", "rating": "70.5", "slope": "125"}}
        resp = logged_in_client.post("/api/courses", json=payload)
        assert resp.status_code == 400
        assert get_courses() == {}

    def test_stored_html_is_escaped_not_executed_on_detail_page(self, logged_in_client):
        # Bypass the API validation to simulate pre-existing/legacy stored
        # HTML (e.g. imported data), and confirm the template renders it
        # inert regardless of the write-path guard.
        course = {
            "location": {"city": "C", "state/province": "S", "country": "Ctry"},
            "tees": {"White": {"yardage": "<img src=x onerror=alert(1)>", "rating": "70.5", "slope": "125"}},
            "holes": {str(n): {"par": "4", "hole_index": str(n)} for n in range(1, 19)},
            "par": 72,
        }
        save_course(course, "XssGC")

        resp = logged_in_client.get("/courses/XssGC")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "&lt;img" in html
        assert "<img src=x onerror" not in html
