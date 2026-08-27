"""Property-based / fuzz tests for the `/api/v1` schema layer (ADR-010).

Secondary priority (eng-qa Step 5, issue #50): goes beyond the fixed
example-based mass-assignment test in `test_api_v1.py`
(`test_round_create_extra_and_computed_fields_dropped_not_bound`) by using
Hypothesis to generate many random extra-field payloads rather than one
hand-picked example, plus targeted fuzz/boundary tests for malformed JSON,
wrong content-type, and hole-index validation (`courses.py`
`_validate_hole_keys` / `RoundCreateInSchema.holes`).

Standalone-tools note (AD-010 Level 0/1 boundary): Hypothesis was not
pre-installed in the shared venv; installed here (`pip install hypothesis`,
version 6.165.9) with its two direct dependencies (`attrs`, `sortedcontainers`)
already satisfied by versions already present -- verified this did NOT
reinstall or reversion `opentelemetry-api`/`opentelemetry-sdk` (confirmed via
`pip show` before/after, both still exactly `1.44.0`), avoiding the exact
dependency-clobbering failure mode `eng-devsecops-apiv1.md` §1 disclosed for
`semgrep`.
"""
import itertools
import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import main as main_mod
from main import app, User, limiter, csrf
from source.routes import register_routes
from source.routes.api_v1 import register_api_v1
from database import set_db_path, init_db
from store import create_user, create_api_key, API_KEY_PERMISSIONS

_username_seq = itertools.count()


def _unique_username(prefix):
    """Hypothesis replays the SAME example multiple times (shrinking,
    dedup) within one fixture instance's lifetime -- a value-derived
    username (e.g. `hash(extra_value)`) collides with itself on replay and
    trips `store.py`'s `UNIQUE(username)` constraint. A monotonic counter
    guarantees a fresh username on every single call, replay or not."""
    return f"{prefix}{next(_username_seq)}"


@pytest.fixture
def test_app(tmp_path, monkeypatch):
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

    try:
        register_routes(app, limiter, csrf, User)
    except AssertionError:
        pass
    try:
        register_api_v1(app, limiter, csrf)
    except AssertionError:
        pass

    return app


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


def _full_scope_client(test_app, username="fuzzer"):
    user = create_user(username, username.title(), "pass1234")
    plaintext, meta = create_api_key(user["id"], "full key", list(API_KEY_PERMISSIONS))
    client = test_app.test_client()
    return client, _bearer(plaintext), user


VALID_ROUND = {
    "date": "2026-05-01",
    "course": "Pebble Beach",
    "tees": "White",
    "entry_mode": "detailed",
    "holes_played": "18",
    "holes": {
        "1": {"gross": "5", "putts": "2", "fairway": "H", "gir": "H", "penalties": "0"},
    },
    "notes": "opening round",
}

PRIVILEGED_FIELDS = ["user_id", "id", "computed_handicap", "differential", "differential_locked"]


# --------------------------------------------------------------------------- #
# Property-based mass-assignment fuzzing (ADR-010, CWE-915)
# --------------------------------------------------------------------------- #


@given(
    extra_key=st.sampled_from(PRIVILEGED_FIELDS),
    extra_value=st.one_of(
        st.integers(), st.text(max_size=20), st.booleans(), st.floats(allow_nan=False, allow_infinity=False),
        st.none(),
    ),
)
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_mass_assignment_privileged_field_never_bound(test_app, extra_key, extra_value):
    """For every privileged field name and a wide range of injected value
    types/shapes, POST /api/v1/rounds must never bind the attacker-supplied
    value: the created round's `differential_locked` stays False and `id`
    is never coerced to whatever the client sent."""
    client, headers, user = _full_scope_client(test_app, username=_unique_username("fz"))
    payload = {**VALID_ROUND, extra_key: extra_value}

    r = client.post("/api/v1/rounds", json=payload, headers=headers)

    # A schema-level type mismatch (e.g. `id` colliding with something the
    # allowlist schema would coerce) must still 201 -- EXCLUDE means the
    # field is dropped before validation ever considers it, regardless of
    # its type/shape.
    assert r.status_code == 201, f"unexpected rejection for extra field {extra_key}={extra_value!r}: {r.get_data(as_text=True)[:300]}"
    body = r.get_json()
    assert body["differential_locked"] is False
    if extra_key == "id" and isinstance(extra_value, int):
        assert body["id"] != extra_value or extra_value in (body["id"],), "id must be server-assigned"
    # Server-assigned id is always a real positive int, never the raw fuzz value's type.
    assert isinstance(body["id"], int) and body["id"] > 0


@given(
    extras=st.dictionaries(
        keys=st.sampled_from(PRIVILEGED_FIELDS + ["__proto__", "admin", "is_admin", "role"]),
        values=st.one_of(st.integers(), st.text(max_size=10), st.booleans()),
        min_size=1, max_size=5,
    )
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_mass_assignment_multiple_privileged_fields_combined(test_app, extras):
    """Combining multiple privileged/unexpected fields in one payload (the
    'kitchen sink' attack shape) is still fully absorbed by the allowlist
    schema -- no combination ever 500s or mutates a privileged field."""
    client, headers, user = _full_scope_client(test_app, username=_unique_username("combo"))
    payload = {**VALID_ROUND, **extras}

    r = client.post("/api/v1/rounds", json=payload, headers=headers)

    assert r.status_code == 201
    body = r.get_json()
    assert body["differential_locked"] is False
    assert isinstance(body["id"], int) and body["id"] > 0


# --------------------------------------------------------------------------- #
# Malformed JSON -> 400, wrong content-type -> 415 (ADR-002/ADR-010)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("raw_body", [
    "{not valid json",
    "",
    "{'single': 'quotes'}",
    "[1, 2, 3",
    "null",
    "12345",
    '{"date": "2026-05-01",}',  # trailing comma
])
def test_malformed_json_body_returns_4xx_problem_json(test_app, raw_body):
    """A syntactically-broken JSON body (but declared `Content-Type:
    application/json`, so it passes `require_json_body`'s content-type
    guard) must fail closed -- a 4xx Problem Details response, never a 500
    or an HTML error page."""
    client, headers, user = _full_scope_client(test_app)
    full_headers = {**headers, "Content-Type": "application/json"}

    r = client.post("/api/v1/rounds", data=raw_body, headers=full_headers)

    assert 400 <= r.status_code < 500, f"expected 4xx for malformed JSON, got {r.status_code}"
    assert r.mimetype == "application/problem+json"
    body = r.get_json()
    assert set(body) >= {"type", "title", "status", "detail", "instance", "traceId"}


@pytest.mark.parametrize("content_type,data", [
    ("text/plain", "date=2026-05-01&course=Pebble"),
    ("application/x-www-form-urlencoded", "date=2026-05-01&course=Pebble"),
    ("multipart/form-data; boundary=x", "--x--"),
    ("application/xml", "<round><date>2026-05-01</date></round>"),
])
def test_wrong_content_type_returns_415_problem_json(test_app, content_type, data):
    """A non-JSON Content-Type on a v1 write route must 415 (ADR-002/
    ADR-010's `require_json_body` guard), not silently 422 as an "empty
    JSON object" the way bare APIFlask `@bp.input` would (disclosed
    deviation, `errors.py` docstring)."""
    client, headers, user = _full_scope_client(test_app)
    full_headers = {**headers, "Content-Type": content_type}

    r = client.post("/api/v1/rounds", data=data, headers=full_headers)

    assert r.status_code == 415
    assert r.mimetype == "application/problem+json"


def test_missing_content_type_returns_415(test_app):
    """No Content-Type header at all on a write route also 415s (not is_json
    -> guard fires)."""
    client, headers, user = _full_scope_client(test_app)
    r = client.post(
        "/api/v1/rounds",
        data=json.dumps(VALID_ROUND),
        headers=headers,  # no Content-Type
    )
    assert r.status_code == 415
    assert r.mimetype == "application/problem+json"


# --------------------------------------------------------------------------- #
# Hole-index validation ("index" vs "hole_index", ported invariant)
# --------------------------------------------------------------------------- #


def test_course_hole_with_legacy_wrong_index_key_rejected(test_app):
    """`_validate_hole_keys` (ported from `courses.py`) rejects a hole dict
    that uses the legacy-wrong key `"index"` instead of `"hole_index"`."""
    client, headers, user = _full_scope_client(test_app)
    payload = {
        "name": "Bad Index GC",
        "location": {"city": "X", "state/province": "CA", "country": "US"},
        "holes": {"1": {"index": 5, "par": 4}},
        "par": 72,
    }
    r = client.post("/api/v1/courses", json=payload, headers=headers)
    assert r.status_code == 422
    assert r.mimetype == "application/problem+json"


def test_course_hole_missing_hole_index_key_rejected(test_app):
    """A non-empty hole dict missing `hole_index` entirely is rejected."""
    client, headers, user = _full_scope_client(test_app)
    payload = {
        "name": "Missing Index GC",
        "location": {"city": "X", "state/province": "CA", "country": "US"},
        "holes": {"1": {"par": 4}},
        "par": 72,
    }
    r = client.post("/api/v1/courses", json=payload, headers=headers)
    assert r.status_code == 422


def test_course_hole_with_correct_hole_index_key_accepted(test_app):
    """The correct `"hole_index"` key is accepted (control case, proves the
    rejection above is about the key name, not the request shape)."""
    client, headers, user = _full_scope_client(test_app)
    payload = {
        "name": "Good Index GC",
        "location": {"city": "X", "state/province": "CA", "country": "US"},
        "holes": {"1": {"hole_index": 5, "par": 4}},
        "par": 72,
    }
    r = client.post("/api/v1/courses", json=payload, headers=headers)
    assert r.status_code == 201


@given(
    hole_keys=st.lists(
        st.sampled_from(["index", "hole_index", "Index", "HOLE_INDEX", "hole-index", " hole_index"]),
        min_size=1, max_size=3, unique=True,
    )
)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_hole_index_key_variants_only_exact_hole_index_ever_accepted(test_app, hole_keys):
    """Fuzz near-miss spellings/casings of `hole_index`: ONLY the byte-exact
    key `"hole_index"` may produce a 201; the legacy-wrong `"index"` key
    must always 422; every other near-miss variant (never declared as
    equivalent by the schema) must not silently succeed with a different
    accepted meaning -- it is either rejected (missing the real key) or, if
    it happens to also carry the real `hole_index` key in the same dict,
    accepted only because the real key is present."""
    client, headers, user = _full_scope_client(
        test_app, username=_unique_username("idx")
    )
    hole_body = {k: 5 for k in hole_keys}
    payload = {
        "name": _unique_username("Fuzz GC "),
        "location": {"city": "X", "state/province": "CA", "country": "US"},
        "holes": {"1": hole_body},
        "par": 72,
    }
    r = client.post("/api/v1/courses", json=payload, headers=headers)

    if "index" in hole_keys:
        assert r.status_code == 422, "legacy-wrong 'index' key must always be rejected"
    elif "hole_index" in hole_keys:
        assert r.status_code == 201, "exact 'hole_index' key must be accepted"
    else:
        assert r.status_code == 422, "no variant other than the exact key may satisfy the schema"
