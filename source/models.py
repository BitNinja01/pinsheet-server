from dataclasses import dataclass, field


@dataclass
class HoleData:
    gross: int = 0
    putts: int = 0
    penalties: int = 0
    fairway: str = ""
    gir: str = ""


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
        tees_data[tname] = TeeData(
            slope=tdata.get("slope", 113),
            rating=float(tdata.get("rating", 72.0)),
            yardage=str(tdata.get("yardage", "0")),
            yardages=tdata.get("yardages", {}),
            front_slope=int(tdata["front_slope"]) if tdata.get("front_slope") not in (None, "") else None,
            front_rating=float(tdata["front_rating"]) if tdata.get("front_rating") not in (None, "") else None,
            back_slope=int(tdata["back_slope"]) if tdata.get("back_slope") not in (None, "") else None,
            back_rating=float(tdata["back_rating"]) if tdata.get("back_rating") not in (None, "") else None,
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
