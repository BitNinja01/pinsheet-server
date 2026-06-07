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
    index: int = 0


@dataclass
class TeeData:
    slope: int = 113
    rating: float = 72.0
    yardage: str = "0"
    yardages: dict[str, str] = field(default_factory=dict)


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


def dict_to_hole(d: dict) -> HoleData:
    return HoleData(
        gross=int(d.get("gross", 0)),
        putts=int(d.get("putts", 0)),
        penalties=int(d.get("penalties", 0)),
        fairway=d.get("fairway", ""),
        gir=d.get("gir", ""),
    )


def dict_to_round(d: dict) -> RoundData:
    holes = {}
    for k, v in d.get("holes", {}).items():
        holes[k] = dict_to_hole(v)
    return RoundData(
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
        index=d.get("index", 0),
    )


def dict_to_course(name: str, d: dict) -> CourseData:
    tees_data = {}
    for tname, tdata in d.get("tees", {}).items():
        tees_data[tname] = TeeData(
            slope=tdata.get("slope", 113),
            rating=float(tdata.get("rating", 72.0)),
            yardage=str(tdata.get("yardage", "0")),
            yardages=tdata.get("yardages", {}),
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
