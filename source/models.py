from dataclasses import dataclass, field


@dataclass
class HoleData:
    gross: int = 0
    putts: int = 0
    penalties: int = 0
    fairway: str = ""
    gir: str = ""


# OB (out-of-bounds) classification code sets, SPLIT by shot field. Per the
# 2026-06-15 directional-stats convention, a code that cannot apply to a given
# field is a generic miss for that field -- ignored by its directional stats,
# NOT counted as that field's OB. OBS (short) and OBLO (long) are approach-shot
# (GIR) miss directions with no tee-shot meaning, so they count as OB only in
# the GIR field, never in the fairway (FIR) field. Defined ONCE here as the
# single source of truth and imported by both calc_ob_stats (calc/approach.py)
# and calc_penalty_hole_breakdown (calc/analysis.py) so the two field sets can
# never silently drift apart again (regression #133: PR #85 had collapsed them
# into one combined set, wrongly counting fairway OBS/OBLO as tee-shot OB).
FIR_OB_CODES = frozenset({"OBL", "OBR"})
GIR_OB_CODES = frozenset({"OBL", "OBR", "OBS", "OBLO"})


@dataclass
class RoundData:
    id: int = 0
    user_id: int = 0
    date: str = ""
    course: str = ""
    tees: str = ""
    holes_played: str = ""
    holes_selection: str = "all"
    transport: str = ""
    entry_mode: str = ""
    notes: str = ""
    holes: dict[str, HoleData] = field(default_factory=dict)
    gross_total: str = ""
    total_gross: str = "0"
    differential: str = ""
    computed_handicap: str = ""
    excluded: bool = False
    differential_locked: bool = False
    index: int = 0
    # WHS Rule 5.6 / 5.1a: Playing Conditions Calculation adjustment for this
    # round, range [-1.0, +3.0] (see clamp_pcc). Default 0.0 == no PCC
    # adjustment, the pre-Rule-5.6 behavior, for every round that doesn't
    # set one.
    pcc: float = 0.0


@dataclass
class TeeData:
    slope: int = 113
    rating: float = 72.0
    yardage: str = "0"
    yardages: dict[str, str] = field(default_factory=dict)
    front_slope: int | None = None
    front_rating: float | None = None
    back_slope: int | None = None
    back_rating: float | None = None


@dataclass
class HoleDef:
    par: int = 0
    hole_index: int = 0


@dataclass
class CourseData:
    name: str = ""
    location: dict = field(default_factory=dict)
    par: str = "72"
    holes: dict[str, HoleDef] = field(default_factory=dict)
    tees: dict[str, TeeData] = field(default_factory=dict)


@dataclass
class MatchData:
    id: int = 0
    created_by: int = 0
    course_name: str = ""
    date: str = ""
    status: str = "active"
    created_at: str = ""


@dataclass
class MatchPlayerData:
    id: int = 0
    match_id: int = 0
    user_id: int = 0


@dataclass
class MatchRoundData:
    id: int = 0
    match_id: int = 0
    user_id: int = 0
    round_id: int = 0
    net: float = 0.0


@dataclass
class ChallengeData:
    id: int = 0
    created_by: int = 0
    title: str = ""
    stat_key: str = ""
    start_date: str = ""
    end_date: str = ""
    status: str = "active"
    created_at: str = ""


def _safe_int(val, default=0):
    """Parse an int, tolerating blank/non-numeric user input."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# WHS Rule 5.6: PCC (Playing Conditions Calculation) is bounded to
# [-1.0, +3.0] by the rule itself.
PCC_MIN = -1.0
PCC_MAX = 3.0


def clamp_pcc(value, default: float = 0.0) -> float:
    """Clamp a PCC (Playing Conditions Calculation) value to WHS Rule 5.6's
    [-1.0, +3.0] range. Non-numeric / missing input defaults to 0.0 (no
    adjustment -- the pre-Rule-5.6 behavior) rather than raising, since
    callers include untrusted JSON request bodies (routes/rounds.py),
    zip-import archive contents (routes/settings.py), and legacy DB rows
    that predate this column.

    Defined here (not calc/handicap.py) to avoid a circular import --
    calc/handicap.py already imports RoundData from this module, so this
    module must not import from calc. calc.calc_round_dif's own `pcc`
    parameter deliberately does NOT re-clamp (it's a pure calculation
    function that trusts its caller, matching calc_course_handicap /
    calc_playing_handicap's convention of not clamping their own inputs) --
    every call site is responsible for clamping via this helper first.

    DESIGN DECISION: clamp (not reject) out-of-range input -- a value of
    5.0 becomes 3.0, -2.0 becomes -1.0, matching the "reject or clamp out-of
    -range; pick one" requirement.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN guard (NaN != NaN is the standard NaN-detection idiom)
        return default
    return max(PCC_MIN, min(PCC_MAX, v))


def effective_pcc(pcc: float, holes_selection: str) -> float:
    """WHS Rule 5.1b: "50% of the playing conditions calculation (PCC) for
    the day is applied" when computing a 9-hole Score Differential -- the
    FULL day's PCC is only applied to an 18-hole ("all") score. Callers
    store/enter the player-facing, un-halved `pcc` value (the day's
    published PCC) and pass the result of THIS function into
    `calc.handicap.calc_round_dif`'s `pcc` parameter at the point the
    differential is actually computed -- mirrors the existing 9-hole
    Handicap Index halving pattern already used throughout
    routes/rounds.py (`adj_hi = hi / 2 if holes_sel != "all" else hi`).

    `holes_selection` is the normalized value ("all" / "front" / "back"),
    not the raw wire value ("18" / "front9" / "back9") -- every call site
    already normalizes this before use (see routes/rounds.py's
    `holes_sel` normalization block)."""
    return pcc * 0.5 if holes_selection != "all" else pcc


def safe_float(val, default=0.0):
    """Parse a float, tolerating blank/missing/non-numeric input.

    Blank ("") tee numeric fields (rating, slope, front_/back_ variants)
    are explicitly allowed by routes/courses.py:_coerce_course_numerics
    ("Blank/missing values are left as-is"), so a present-but-blank value
    must fall back to `default` the same as a missing key -- NOT crash on
    float(""). A plain `dict.get(field, default)` does not catch this
    because the default only applies when the key is absent, not when its
    value is "".
    """
    if val in (None, ""):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_positive_float(*candidates, default: float) -> float:
    """Return the first candidate that parses to a finite, STRICTLY
    POSITIVE float; falls through to the next candidate (mirroring a
    missing/blank cascade) and finally to `default` if none qualify.

    "0" (and negative values) parse fine as a float -- `safe_float` alone
    would happily return 0.0 -- but a non-positive slope/rating is
    domain-invalid for the WHS formulas that divide by slope
    (`calc_round_dif`: `113 / tee_slope`; `calc_course_handicap`:
    `slope / 113` is safe, but a 0/negative slope or rating still
    corrupts the Course Handicap / Score Differential). Blank, missing,
    non-numeric, AND non-positive values are all treated the same way
    here: "invalid, try the next fallback."
    """
    for c in candidates:
        parsed = safe_float(c, None)
        if parsed is not None and parsed > 0:
            return parsed
    return default


_POSITIVE_ONLY_TEE_FIELDS = (
    "rating", "slope", "front_rating", "front_slope", "back_rating", "back_slope",
)


def invalid_tee_numeric_reason(tee: dict) -> str | None:
    """Return a human-readable reason if a PRESENT (non-blank) tee
    slope/rating (or front_/back_ variant) is non-numeric or non-positive,
    else None. Blank/missing fields are allowed (not this function's
    concern -- see `safe_float`/`safe_positive_float`).

    Shared write-path guard for course save (routes/courses.py) and round
    save (routes/rounds.py): "0" is a valid float but a domain-invalid
    slope/rating (calc_round_dif divides by slope -- slope<=0 is a
    ZeroDivisionError waiting to happen at round-save time), so it must be
    rejected with a clean validation error rather than silently accepted.
    """
    for field in _POSITIVE_ONLY_TEE_FIELDS:
        val = tee.get(field)
        if val in (None, ""):
            continue
        try:
            parsed = float(val)
        except (TypeError, ValueError):
            return f"field '{field}' must be numeric"
        if parsed <= 0:
            return f"field '{field}' must be a positive number"
    return None


def _safe_optional_float(val):
    """Blank-safe optional numeric tee-override parse (front_/back_
    rating): None for missing/blank input (no override -- the base
    slope/rating field applies), and -- unlike a raw float()/int() cast --
    never raises on non-numeric garbage either; falls back to None (no
    override) instead of crashing course-load-time. Mirrors `safe_float`'s
    blank/non-numeric handling, scoped to the "optional override" fields
    where None (not a hardcoded default) is the correct fallback."""
    if val in (None, ""):
        return None
    return safe_float(val, None)


def _safe_optional_int(val):
    """Same contract as `_safe_optional_float` (front_/back_ slope), but
    returns an int (or None)."""
    parsed = _safe_optional_float(val)
    return int(parsed) if parsed is not None else None


def dict_to_hole(d: dict) -> HoleData:
    return HoleData(
        gross=_safe_int(d.get("gross"), 0),
        putts=_safe_int(d.get("putts"), 0),
        penalties=_safe_int(d.get("penalties"), 0),
        fairway=d.get("fairway", ""),
        gir=d.get("gir", ""),
    )


def dict_to_round(d: dict) -> RoundData:
    holes = {}
    for k, v in d.get("holes", {}).items():
        holes[k] = dict_to_hole(v)
    return RoundData(
        id=d.get("id", 0),
        user_id=d.get("user_id", 0),
        date=d.get("date", ""),
        course=d.get("course", ""),
        tees=d.get("tees", ""),
        holes_played=d.get("holes_played", ""),
        holes_selection=d.get("holes_selection", "all"),
        transport=d.get("transport", ""),
        entry_mode=d.get("entry_mode", ""),
        notes=d.get("notes", ""),
        holes=holes,
        gross_total=d.get("gross_total", ""),
        total_gross=d.get("total_gross", "0"),
        differential=d.get("differential", ""),
        computed_handicap=d.get("computed_handicap", ""),
        excluded=d.get("excluded", False),
        differential_locked=bool(d.get("differential_locked", False)),
        index=d.get("index", 0),
        # Defense-in-depth: re-clamp on construction too (not just at the
        # HTTP input boundary in routes/rounds.py) so every RoundData object
        # -- including ones built from zip-import archive contents or a
        # legacy DB row -- carries a range-valid pcc, even if the dict that
        # produced it came from an untrusted or pre-validation source.
        pcc=clamp_pcc(d.get("pcc", 0.0)),
    )


def dict_to_course(name: str, d: dict) -> CourseData:
    tees_data = {}
    for tname, tdata in d.get("tees", {}).items():
        # DA-002: blank ("") is explicitly allowed by _coerce_course_numerics
        # ("Blank/missing values are left as-is"), so a present-but-blank
        # slope/rating must fall back to a sane default (not crash
        # course-load-time on float("")/int("")) the same way `rating`
        # already did -- `slope` previously stored the raw un-parsed value
        # (violating TeeData.slope: int) and was only masked downstream by
        # scoring.py's `float(first_tee.slope or "113")` idiom. Use
        # `safe_float` for both base fields, and the blank/non-numeric-safe
        # `_safe_optional_float` for the front_/back_ override fields (a
        # blank/garbage override correctly falls back to None -- "no
        # override, use the base field" -- rather than crashing).
        tees_data[tname] = TeeData(
            slope=safe_float(tdata.get("slope"), 113),
            rating=safe_float(tdata.get("rating"), 72.0),
            yardage=str(tdata.get("yardage", "0")),
            yardages=tdata.get("yardages", {}),
            front_slope=_safe_optional_int(tdata.get("front_slope")),
            front_rating=_safe_optional_float(tdata.get("front_rating")),
            back_slope=_safe_optional_int(tdata.get("back_slope")),
            back_rating=_safe_optional_float(tdata.get("back_rating")),
        )
    holes_data = {}
    for hn, hdata in d.get("holes", {}).items():
        holes_data[hn] = HoleDef(
            par=int(hdata.get("par", 0)),
            hole_index=int(hdata.get("hole_index", 0)),
        )
    return CourseData(
        name=name,
        location=d.get("location", {}),
        par=str(d.get("par", "72")),
        holes=holes_data,
        tees=tees_data,
    )
