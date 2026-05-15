import json
import logging
from pathlib import Path

_log = logging.getLogger("pinsheet")

_DATA_DIR = Path(__file__).parent / "data"


def init_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    settings_file = _DATA_DIR / "settings.json"
    defaults = {"season_start_month": 1, "season_end_month": 12, "season_start_day": 1, "season_end_day": 28, "season_enabled": False}
    if settings_file.exists():
        data = json.loads(settings_file.read_text())
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    return defaults


def save_settings(data: dict) -> None:
    settings_file = _DATA_DIR / "settings.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, indent=2))


def get_handicap_benchmarks(handicap_index: float) -> dict | None:
    path = _DATA_DIR / "handicap_benchmarks.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    idx = max(-4, min(36, int(handicap_index)))
    for key in (str(idx), f"+{idx}"):
        if key in data:
            return data[key]
    return None


def get_courses() -> dict:
    course_json = _DATA_DIR / "courses.json"
    return json.loads(course_json.read_text()) if course_json.exists() else {}


def get_rounds(year: str) -> dict:
    path = _DATA_DIR / "rounds" / f"{year}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_course(course, course_name) -> None:
    course_json = _DATA_DIR / "courses.json"
    course_json.parent.mkdir(parents=True, exist_ok=True)
    library = json.loads(course_json.read_text()) if course_json.exists() else {}
    if not library.get(course_name):
        library[course_name] = {}
    library[course_name] = course
    course_json.write_text(json.dumps(library, indent=2))
    _log.info("course saved: %s", course_name)


def save_course_draft(draft_state: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    (_DATA_DIR / "course_draft.json").write_text(json.dumps(draft_state, indent=2))


def load_course_draft() -> dict | None:
    path = _DATA_DIR / "course_draft.json"
    return json.loads(path.read_text()) if path.exists() else None


def clear_course_draft() -> None:
    path = _DATA_DIR / "course_draft.json"
    if path.exists():
        path.unlink()
        _log.info("course draft cleared")


def save_round(golf_round, date, index) -> None:
    year = date[:4] if date else "unknown"
    path = _DATA_DIR / "rounds" / f"{year}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    library = json.loads(path.read_text()) if path.exists() else {}
    if not library.get(date):
        library[date] = {}
    library[date][str(index)] = golf_round
    path.write_text(json.dumps(library, indent=2))
    _log.info("round saved: %s #%s course=%s", date, index, golf_round.get("course", "?"))


def save_round_draft(draft_state: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    (_DATA_DIR / "round_draft.json").write_text(json.dumps(draft_state, indent=2))


def load_round_draft() -> dict | None:
    path = _DATA_DIR / "round_draft.json"
    return json.loads(path.read_text()) if path.exists() else None


def clear_round_draft() -> None:
    path = _DATA_DIR / "round_draft.json"
    if path.exists():
        path.unlink()
        _log.info("round draft cleared")


def delete_course(course_name: str) -> None:
    course_json = _DATA_DIR / "courses.json"
    if not course_json.exists():
        return
    library = json.loads(course_json.read_text())
    if course_name in library:
        del library[course_name]
        course_json.write_text(json.dumps(library, indent=2))
        _log.info("course deleted: %s", course_name)


def delete_round(date: str, index: str) -> None:
    year = date[:4] if date else "unknown"
    path = _DATA_DIR / "rounds" / f"{year}.json"
    if not path.exists():
        return
    library = json.loads(path.read_text())
    if date in library and str(index) in library[date]:
        del library[date][str(index)]
        if not library[date]:
            del library[date]
        path.write_text(json.dumps(library, indent=2))
        _log.info("round deleted: %s #%s", date, index)


def rename_course(old_name: str, new_name: str) -> None:
    rounds_dir = _DATA_DIR / "rounds"
    if not rounds_dir.exists():
        return
    for json_file in rounds_dir.glob("*.json"):
        data = json.loads(json_file.read_text())
        modified = False
        for date_rounds in data.values():
            for round_data in date_rounds.values():
                if round_data.get("course") == old_name:
                    round_data["course"] = new_name
                    modified = True
        if modified:
            json_file.write_text(json.dumps(data, indent=2))
    _log.info("course renamed: %r -> %r", old_name, new_name)


def get_all_rounds(limit=None) -> list:
    rounds_dir = _DATA_DIR / "rounds"
    collected = []

    if not rounds_dir.exists():
        return collected

    for file in sorted(rounds_dir.glob("*.json"), reverse=True):
        file_data = json.loads(file.read_text())
        for date in sorted(file_data.keys(), reverse=True):
            for index in sorted(file_data[date].keys(), reverse=True):
                collected.append({"date": date, "index": index, **file_data[date][index]})
                if limit and len(collected) == limit:
                    return collected

    return collected


def get_slope_rating(tee_data: dict, holes_sel: str) -> tuple[float, float]:
    if holes_sel == "front":
        slope  = float(tee_data.get("front_slope",  tee_data.get("slope",  113)))
        rating = float(tee_data.get("front_rating", tee_data.get("rating", 72.0)))
    elif holes_sel == "back":
        slope  = float(tee_data.get("back_slope",  tee_data.get("slope",  113)))
        rating = float(tee_data.get("back_rating", tee_data.get("rating", 72.0)))
    else:
        slope  = float(tee_data.get("slope",  113))
        rating = float(tee_data.get("rating", 72.0))
    return slope, rating
