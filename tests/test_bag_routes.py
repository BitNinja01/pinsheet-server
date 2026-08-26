import pytest

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from database import set_db_path, init_db
from store import (
    create_user,
    get_clubs,
    get_bag_slots,
    save_club,
    get_distinct_club_field_values,
)


@pytest.fixture
def test_app(tmp_path, monkeypatch):
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
    app.config["DB_PATH"] = db_path

    return app


@pytest.fixture
def logged_in_client(test_app):
    create_user("player", "Player", "pass1234")
    c = test_app.test_client()
    c.post("/login", data={"username": "player", "password": "pass1234"})
    return c


DRIVER = {
    "category": "Drivers",
    "club": "Driver",
    "number": "1",
    "brand": "TestBrand",
    "model": "TestModel",
    "loft": "10.5",
    "lie": "58",
    "length": "45.5",
    "shaft_flex": "Stiff",
    "shaft_brand": "ShaftCo",
    "shaft": "Tour X",
    "grip": "GripCo",
    "sw": "D2",
    "carry": 260,
}


class TestBagPage:
    def test_bag_page_loads_with_no_clubs(self, logged_in_client):
        resp = logged_in_client.get("/bag")
        assert resp.status_code == 200

    def test_bag_page_lists_saved_club_and_autocomplete_values(self, logged_in_client):
        resp = logged_in_client.post("/bag/club", json=DRIVER)
        assert resp.status_code == 200
        club_id = resp.get_json()["id"]

        resp = logged_in_client.get("/bag")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert club_id in html
        assert "TestBrand" in html

    def test_requires_login(self, test_app):
        client = test_app.test_client()
        resp = client.get("/bag", follow_redirects=True)
        assert b"login" in resp.data.lower() or b"Login" in resp.data

    def test_club_field_cannot_break_out_of_script_block(self, logged_in_client):
        # Regression for issue #71 (CWE-79): club free-text fields are embedded
        # into a <script> block as JSON. Serializing with json.dumps + |safe left
        # </script> unescaped, allowing script-context breakout. |tojson escapes
        # </ to <\/ (\u003c), so the payload can never terminate the element.
        evil = dict(DRIVER)
        evil["brand"] = "</script><script>window.__xss=1</script>"
        logged_in_client.post("/bag/club", json=evil)

        html = logged_in_client.get("/bag").get_data(as_text=True)

        # The literal breakout sequence must not survive into the response.
        assert "</script><script>" not in html
        # The payload is still present, but neutralized via unicode escaping.
        assert "\\u003c/script\\u003e" in html or "<\\/script>" in html


class TestBagSaveClub:
    def test_save_new_club_generates_id_and_persists(self, logged_in_client):
        resp = logged_in_client.post("/bag/club", json=DRIVER)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        club_id = data["id"]
        assert club_id.startswith("c")
        assert len(club_id) == 9  # "c" + 8 hex chars

        clubs = get_clubs(1)
        assert len(clubs) == 1
        saved = clubs[0]
        assert saved["id"] == club_id
        assert saved["category"] == "Drivers"
        assert saved["brand"] == "TestBrand"
        assert saved["carry"] == 260

    def test_save_with_explicit_id_updates_in_place(self, logged_in_client):
        first = logged_in_client.post("/bag/club", json=DRIVER).get_json()
        club_id = first["id"]

        updated = dict(DRIVER)
        updated["id"] = club_id
        updated["loft"] = "9.0"
        resp = logged_in_client.post("/bag/club", json=updated)
        assert resp.status_code == 200
        assert resp.get_json()["id"] == club_id

        clubs = get_clubs(1)
        # Must still be exactly one club (in-place update, not a duplicate).
        assert len(clubs) == 1
        assert clubs[0]["loft"] == "9.0"

    def test_missing_fields_default_sensibly(self, logged_in_client):
        resp = logged_in_client.post("/bag/club", json={})
        assert resp.status_code == 200
        clubs = get_clubs(1)
        assert clubs[0]["category"] == "Irons"  # documented default
        assert clubs[0]["club"] == ""

    def test_requires_login(self, test_app):
        client = test_app.test_client()
        resp = client.post("/bag/club", json=DRIVER)
        assert resp.status_code in (302, 401)
        assert get_clubs(1) == []


class TestBagDeleteClub:
    def test_delete_removes_club(self, logged_in_client):
        club_id = logged_in_client.post("/bag/club", json=DRIVER).get_json()["id"]
        assert len(get_clubs(1)) == 1

        resp = logged_in_client.post(f"/bag/club/{club_id}/delete")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        assert get_clubs(1) == []

    def test_delete_removes_club_from_bag_slots(self, logged_in_client):
        club_id = logged_in_client.post("/bag/club", json=DRIVER).get_json()["id"]
        logged_in_client.post("/bag/slots", json={"slots": [club_id, "empty", "empty"]})
        assert get_bag_slots(1) == [club_id, "empty", "empty"]

        logged_in_client.post(f"/bag/club/{club_id}/delete")

        # Deleting a club must also purge it from any bag slot -- otherwise
        # the bag UI would reference a club that no longer exists.
        assert get_bag_slots(1) == ["empty", "empty"]

    def test_delete_nonexistent_club_is_a_noop(self, logged_in_client):
        resp = logged_in_client.post("/bag/club/does-not-exist/delete")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}

    def test_delete_only_affects_owning_user(self, logged_in_client, test_app):
        club_id = logged_in_client.post("/bag/club", json=DRIVER).get_json()["id"]

        create_user("other", "Other", "otherpass1")
        other_client = test_app.test_client()
        other_client.post("/login", data={"username": "other", "password": "otherpass1"})
        other_client.post(f"/bag/club/{club_id}/delete")

        # A different user deleting an id they don't own must not remove it.
        assert len(get_clubs(1)) == 1


class TestBagCrossUserSecurity:
    def test_save_club_rejects_cross_user_overwrite(self, logged_in_client):
        # Issue #69 (IDOR, CWE-639): the attacker is "player" (id 1). Seed a
        # club owned by a different user, then try to overwrite it by id.
        victim = create_user("victim", "Victim", "victimpass1")
        assert save_club({**DRIVER, "id": "cvictim01", "brand": "VictimBrand"}, victim["id"]) is True

        resp = logged_in_client.post(
            "/bag/club", json={**DRIVER, "id": "cvictim01", "brand": "Hijacked"}
        )
        assert resp.status_code == 403

        # Victim's row is untouched — still owned by victim, brand unchanged.
        victim_clubs = get_clubs(victim["id"])
        assert len(victim_clubs) == 1
        assert victim_clubs[0]["brand"] == "VictimBrand"
        # Attacker (id 1) did not acquire the club.
        assert all(c["id"] != "cvictim01" for c in get_clubs(1))

    def test_save_club_same_owner_update_still_allowed(self, logged_in_client):
        # The ownership guard must not block a user editing their own club.
        club_id = logged_in_client.post("/bag/club", json=DRIVER).get_json()["id"]
        resp = logged_in_client.post(
            "/bag/club", json={**DRIVER, "id": club_id, "brand": "Updated"}
        )
        assert resp.status_code == 200
        clubs = get_clubs(1)
        assert len(clubs) == 1 and clubs[0]["brand"] == "Updated"

    def test_autocomplete_is_scoped_to_owner(self, logged_in_client):
        # Issue #72 (CWE-200): autocomplete must expose only the caller's own
        # field values, not every user's.
        victim = create_user("victim2", "Victim2", "victimpass2")
        save_club({**DRIVER, "id": "cvic2", "brand": "VictimOnlyBrand"}, victim["id"])
        logged_in_client.post("/bag/club", json={**DRIVER, "brand": "AttackerBrand"})

        # Store layer: each user sees only their own brand.
        assert get_distinct_club_field_values("brand", 1) == ["AttackerBrand"]
        assert get_distinct_club_field_values("brand", victim["id"]) == ["VictimOnlyBrand"]

        # Route layer: the victim's brand does not leak into the attacker's page.
        html = logged_in_client.get("/bag").get_data(as_text=True)
        assert "AttackerBrand" in html
        assert "VictimOnlyBrand" not in html


class TestBagSaveSlots:
    def test_save_slots_persists_list(self, logged_in_client):
        resp = logged_in_client.post("/bag/slots", json={"slots": ["a", "b", "c"]})
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        assert get_bag_slots(1) == ["a", "b", "c"]

    def test_save_slots_missing_key_defaults_to_empty_list(self, logged_in_client):
        resp = logged_in_client.post("/bag/slots", json={})
        assert resp.status_code == 200
        assert get_bag_slots(1) == []

    def test_save_slots_overwrites_previous(self, logged_in_client):
        logged_in_client.post("/bag/slots", json={"slots": ["a", "b"]})
        logged_in_client.post("/bag/slots", json={"slots": ["x"]})
        assert get_bag_slots(1) == ["x"]

    def test_requires_login(self, test_app):
        client = test_app.test_client()
        resp = client.post("/bag/slots", json={"slots": ["a"]})
        assert resp.status_code in (302, 401)
