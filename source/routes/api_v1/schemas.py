"""Marshmallow input/output schemas for /api/v1 (ADR-010).

All schemas are ALLOWLIST-ONLY (`class Meta: unknown = EXCLUDE`): an
unexpected field in a client body is silently dropped, not bound, and never
reaches a `store.py` write call. `user_id`, `id`, `computed_handicap`,
`differential`, and `differential_locked` are NEVER declared as input fields
on any schema in this module -- these are exactly the privileged fields
`store.py:121-138` exposes internally. `user_id` is bound exactly once,
server-side, in each handler (`current_user.id`) -- never from a schema
field, ever.

Built against **marshmallow 4.3.1** (confirmed via the resolved dependency
set, not the 3.x API assumed in early drafts of this plan): `load_default=`/
`dump_default=` (the 3.x `missing=`/`default=` kwargs were removed in 4.x),
`Meta.unknown = EXCLUDE` (imported from `marshmallow`, still valid in 4.x).
"""
from marshmallow import EXCLUDE, Schema, ValidationError, fields, post_load, validate, validates_schema


def _int_coercible(val) -> bool:
    """True iff `int(val)` (the exact conversion `models.dict_to_course`
    applies unconditionally to `par`/`hole_index` and, when present and
    non-empty, to `slope`/`front_slope`/`back_slope`) would succeed."""
    try:
        int(val)
        return True
    except (TypeError, ValueError):
        return False


def _float_coercible(val) -> bool:
    """True iff `float(val)` (the exact conversion `models.dict_to_course`
    applies unconditionally to `rating` and, when present and non-empty, to
    `front_rating`/`back_rating`) would succeed."""
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Courses (ADR-011 -- shared, global catalog; no user_id at all)
# ---------------------------------------------------------------------------


class LocationSchema(Schema):
    """Required course location fields, ported from `courses.py:138`. Note the
    literal legacy JSON key `"state/province"` (not a typo) on the WIRE --
    `data_key="state/province"` accepts that exact JSON key from the client
    and maps it to the Python-safe attribute name `state_province` for
    validation.

    CRITICAL (Revision 1, DA-1): `data_key` is INBOUND-only. `Schema.load()`
    returns a dict keyed by the marshmallow FIELD name (`state_province`),
    never the wire `data_key` -- confirmed empirically against the installed
    marshmallow==4.3.1 (`LocationSchema().load({"state/province": "CA", ...})`
    -> `{"state_province": "CA", ...}`, no `"state/province"` key at all).
    Without the `@post_load` hook below, `save_course` would have persisted
    `location["state_province"]` into the course JSON blob, while the
    legacy Jinja template reads `location.get("state/province")`
    (`course_detail.html:15,21`) and the legacy JS writes
    `"state/province"` (`courses.html:335`) -- every course created/edited
    via v1 would have silently corrupted State/Province for the SHARED
    (ADR-011) legacy page, permanently, for every user. `_restore_wire_key`
    re-keys `state_province` back to the literal `"state/province"` on
    load, so the dict `save_course`/`update_course` persist is byte-key-
    identical to what the legacy UI writes. See
    `test_location_state_province_key_roundtrip` (`tests/test_api_v1.py`).
    """

    class Meta:
        unknown = EXCLUDE

    city = fields.Str(required=True, validate=validate.Length(min=1))
    state_province = fields.Str(required=True, validate=validate.Length(min=1), data_key="state/province")
    country = fields.Str(required=True, validate=validate.Length(min=1))

    @post_load
    def _restore_wire_key(self, data, **kwargs):
        """Undo marshmallow's field-name-keyed `load()` output: rename
        `state_province` back to the literal legacy wire key
        `"state/province"` so the dict handed to `store.save_course` matches
        the shape the legacy UI has always written (`courses.html:335`,
        `course_detail.html:15,21`)."""
        data["state/province"] = data.pop("state_province")
        return data


class CourseInSchema(Schema):
    """Allowlist input for POST/PUT /api/v1/courses (ADR-010). Courses have no
    `user_id` at all (ADR-011 -- shared catalog by design), so there is no
    ownership field to omit here; `name` is still required (ported invariant,
    `courses.py:133`)."""

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1))
    location = fields.Nested(LocationSchema, required=True)
    tees = fields.Dict(load_default=dict)
    holes = fields.Dict(load_default=dict)
    par = fields.Raw(load_default=0)

    @validates_schema
    def _validate_hole_keys(self, data, **kwargs):
        """Ported invariant (`courses.py:9-20` `_validate_hole_keys`): reject
        the legacy-wrong key `"index"`, require `"hole_index"`.

        SEC-1 (Revision 2, HIGH, cross-user DoS): ALSO validates that every
        numeric-typed course/tee sub-field is genuinely coercible to the type
        `source/models.py::dict_to_course` unconditionally converts it with
        (`int(hdata.get("par", 0))`, `int(hdata.get("hole_index", 0))`,
        `float(tdata.get("rating", 72.0))`, and the guarded-but-still-crashing
        `int(tdata["front_slope"])`/etc when present-and-non-empty). Before
        this fix, `holes["1"]["hole_index"] = "not-a-number"` persisted with
        a 201 (no numeric check existed), and `dict_to_course` -- called over
        the ENTIRE shared catalog by `GET /api/v1/stats` (`stats.py:39`, and
        the legacy dashboard) -- raised `ValueError`/`TypeError` on that one
        poisoned row, 500ing `/api/v1/stats` for EVERY user permanently
        (courses are a shared, global catalog, ADR-011 -- one bad write from
        any `courses:write`-scoped key breaks the read path for everyone).
        This validator rejects the write itself with 422 `application/
        problem+json`, before `save_course` is ever called, closing the
        DoS at its source (SEC-1(a) primary fix). `stats.py`'s per-course
        `try/except` (SEC-1(b)) is defense-in-depth for any row that
        predates this fix or reaches the DB by another path.
        """
        holes = data.get("holes") or {}
        if not isinstance(holes, dict):
            raise ValidationError("holes must be an object", field_name="holes")
        for num, hole in holes.items():
            if not isinstance(hole, dict):
                continue
            if "index" in hole:
                raise ValidationError(
                    f"hole {num}: stroke index must use key 'hole_index', not 'index'",
                    field_name="holes",
                )
            if "hole_index" not in hole and hole:
                raise ValidationError(
                    f"hole {num}: stroke index must use key 'hole_index'",
                    field_name="holes",
                )
            for int_field in ("hole_index", "par"):
                if int_field in hole and not _int_coercible(hole[int_field]):
                    raise ValidationError(
                        f"hole {num}: '{int_field}' must be a whole number, got {hole[int_field]!r}",
                        field_name="holes",
                    )

        tees = data.get("tees") or {}
        if not isinstance(tees, dict):
            raise ValidationError("tees must be an object", field_name="tees")
        for tee_name, tee in tees.items():
            if not isinstance(tee, dict):
                continue
            for int_field in ("slope", "front_slope", "back_slope"):
                if tee.get(int_field) not in (None, "") and not _int_coercible(tee[int_field]):
                    raise ValidationError(
                        f"tee '{tee_name}': '{int_field}' must be a whole number, got {tee[int_field]!r}",
                        field_name="tees",
                    )
            for float_field in ("rating", "yardage", "front_rating", "back_rating"):
                if tee.get(float_field) not in (None, "") and not _float_coercible(tee[float_field]):
                    raise ValidationError(
                        f"tee '{tee_name}': '{float_field}' must be numeric, got {tee[float_field]!r}",
                        field_name="tees",
                    )


# POST and PUT /api/v1/courses share an identical body shape (name/location/
# tees/holes/par -- see courses.py:132-149 vs :173-197 in the legacy routes,
# which validate the same fields for create and rename). Both names are kept
# so v1 call sites read clearly; this is NOT the same situation as rounds
# below, where create/update genuinely diverge (date/round_index).
CourseCreateInSchema = CourseInSchema
CourseUpdateInSchema = CourseInSchema


class CourseOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str()
    location = fields.Dict()
    tees = fields.Dict()
    holes = fields.Dict()
    par = fields.Raw()


class CourseListOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    courses = fields.List(fields.Nested(CourseOutSchema))


# ---------------------------------------------------------------------------
# Rounds (ADR-009 -- owner-scoped; ADR-010 mass-assignment guard; Rev-2 M-3)
# ---------------------------------------------------------------------------


class RoundCreateInSchema(Schema):
    """POST /api/v1/rounds. Never declares `user_id`/`id`/`computed_handicap`/
    `differential`/`differential_locked` -- `user_id` is bound server-side
    from `current_user.id` (ADR-009); the computed fields are derived
    server-side (via the existing `recompute_handicaps_for_user` cascade)
    after `save_round`, never accepted from the client."""

    class Meta:
        unknown = EXCLUDE

    date = fields.Str(required=True, validate=validate.Length(min=1))
    course = fields.Str(load_default="")
    tees = fields.Str(load_default="")
    holes_played = fields.Str(load_default="18")
    transport = fields.Str(load_default="")
    entry_mode = fields.Str(load_default="detailed", validate=validate.OneOf(["detailed", "score_only"]))
    notes = fields.Str(load_default="")
    holes = fields.Dict(keys=fields.Str(), values=fields.Dict(), load_default=dict)
    gross_total = fields.Str(load_default="")
    excluded = fields.Boolean(load_default=False)


class RoundUpdateInSchema(Schema):
    """PUT /api/v1/rounds/{id} (ADR-010, Rev-2 M-3). Deliberately excludes
    `date`/`round_index` -- `store.save_round` is `INSERT OR REPLACE` keyed on
    `UNIQUE(user_id, date, round_index)`; accepting a client-supplied
    `date`/index on PUT could collide with and destroy a DIFFERENT existing
    round. The handler pins `date`/`round_index` server-side from the
    fetched, owner-checked row instead (see `rounds.py: update_round()`).

    Deliberately NO `load_default` on any field here (unlike
    `RoundCreateInSchema`) -- PUT is a genuine PARTIAL update: a field the
    client omits is simply absent from the loaded dict, so the handler's
    `json_data.get(field, existing_row.field)` fallback preserves the
    round's current value instead of silently blanking it. Discovered via
    smoke testing: an earlier draft gave every field a `load_default`
    (mirroring `RoundCreateInSchema`), which made every field ALWAYS present
    in the loaded dict -- defeating the handler's own fallback and silently
    wiping `course`/`tees`/`holes`/... to blank on any PUT that only meant
    to change e.g. `notes`. Fixed here; disclosed in build notes."""

    class Meta:
        unknown = EXCLUDE

    course = fields.Str()
    tees = fields.Str()
    holes_played = fields.Str()
    transport = fields.Str()
    entry_mode = fields.Str(validate=validate.OneOf(["detailed", "score_only"]))
    notes = fields.Str()
    holes = fields.Dict(keys=fields.Str(), values=fields.Dict())
    gross_total = fields.Str()
    excluded = fields.Boolean()


class HoleOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    gross = fields.Int()
    putts = fields.Int()
    penalties = fields.Int()
    fairway = fields.Str()
    gir = fields.Str()


class RoundOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int()
    date = fields.Str()
    index = fields.Int()
    course = fields.Str()
    tees = fields.Str()
    holes_played = fields.Str()
    holes_selection = fields.Str()
    entry_mode = fields.Str()
    holes = fields.Dict(keys=fields.Str(), values=fields.Nested(HoleOutSchema))
    total_gross = fields.Str()
    differential = fields.Str()
    computed_handicap = fields.Str()
    notes = fields.Str()
    excluded = fields.Boolean()
    differential_locked = fields.Boolean()


class RoundListOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    rounds = fields.List(fields.Nested(RoundOutSchema))


# ---------------------------------------------------------------------------
# Stats (read-only)
# ---------------------------------------------------------------------------


class HandicapTrendPointSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    date = fields.Str()
    value = fields.Float()


class StatsOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    rounds_total = fields.Int()
    handicap_index = fields.Float(allow_none=True)
    scoring_average = fields.Float(allow_none=True)
    fir_percent = fields.Float(allow_none=True)
    gir_percent = fields.Float(allow_none=True)
    putts_per_round = fields.Float(allow_none=True)
    scramble_percent = fields.Float(allow_none=True)
    par_or_better_percent = fields.Float(allow_none=True)
    handicap_trend = fields.List(fields.Nested(HandicapTrendPointSchema))


# ---------------------------------------------------------------------------
# Settings (owner-scoped; store merges partial updates, `store.py:47-51`)
# ---------------------------------------------------------------------------


class SettingsInSchema(Schema):
    """No field is `required` -- `save_settings` merges the submitted dict
    into the existing stored settings (`store.py:47-51`), so a partial PUT
    (e.g. just `{"include_9hole": false}`) is a legitimate, supported call."""

    class Meta:
        unknown = EXCLUDE

    season_start_month = fields.Int(validate=validate.Range(min=1, max=12))
    season_end_month = fields.Int(validate=validate.Range(min=1, max=12))
    season_start_day = fields.Int(validate=validate.Range(min=1, max=31))
    season_end_day = fields.Int(validate=validate.Range(min=1, max=31))
    season_enabled = fields.Boolean()
    include_9hole = fields.Boolean()


class SettingsOutSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    season_start_month = fields.Int()
    season_end_month = fields.Int()
    season_start_day = fields.Int()
    season_end_day = fields.Int()
    season_enabled = fields.Boolean()
    include_9hole = fields.Boolean(dump_default=True)
