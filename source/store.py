import json
import logging
from pathlib import Path

from database import get_db, init_db, set_db_path

_log = logging.getLogger("pinsheet")
_DATA_DIR = Path(__file__).parent.parent / "data"


def init_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    set_db_path(str(_DATA_DIR / "pinsheet.db"))
    init_db()


def load_settings(user_id: int = 1) -> dict:
    defaults = {"season_start_month": 1, "season_end_month": 12, "season_start_day": 1, "season_end_day": 28, "season_enabled": False}
    db = get_db()
    row = db.execute("SELECT data FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    db.close()
    if row:
        data = json.loads(row["data"])
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    return defaults


def save_settings(data: dict, user_id: int = 1) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO settings (user_id, data) VALUES (?, ?)",
        (user_id, json.dumps(data)),
    )
    db.commit()
    db.close()


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
    db = get_db()
    rows = db.execute("SELECT name, data FROM courses").fetchall()
    db.close()
    result = {}
    for row in rows:
        result[row["name"]] = json.loads(row["data"])
    return result


def save_course(course, course_name) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO courses (name, data) VALUES (?, ?)",
        (course_name, json.dumps(course)),
    )
    db.commit()
    db.close()
    _log.info("course saved: %s", course_name)


def delete_course(course_name: str) -> None:
    db = get_db()
    db.execute("DELETE FROM courses WHERE name = ?", (course_name,))
    db.commit()
    db.close()
    _log.info("course deleted: %s", course_name)


def rename_course(old_name: str, new_name: str) -> None:
    db = get_db()
    db.execute("UPDATE courses SET name = ? WHERE name = ?", (new_name, old_name))
    db.execute("UPDATE rounds SET course_name = ? WHERE course_name = ?", (new_name, old_name))
    db.commit()
    db.close()
    _log.info("course renamed: %r -> %r", old_name, new_name)


def get_all_rounds(user_id: int = 1, limit: int = None) -> list:
    db = get_db()
    query = "SELECT * FROM rounds WHERE user_id = ? ORDER BY date DESC, round_index DESC"
    if limit is not None:
        query += " LIMIT ?"
        rows = db.execute(query, (user_id, limit)).fetchall()
    else:
        rows = db.execute(query, (user_id,)).fetchall()
    db.close()
    result = []
    for row in rows:
        r = {
            "date": row["date"],
            "index": row["round_index"],
            "user_id": row["user_id"],
            "course": row["course_name"],
            "tees": row["tee_name"],
            "holes_played": row["holes_played"],
            "entry_mode": row["entry_mode"],
            "holes": json.loads(row["holes"]) if row["holes"] else {},
            "total_gross": row["total_gross"],
            "differential": row["differential"],
            "notes": row["notes"],
            "excluded": bool(row["excluded"]),
            "computed_handicap": row["computed_handicap"],
        }
        if row["total_putts"]:
            r["total_putts"] = row["total_putts"]
        result.append(r)
    return result


def save_round(golf_round, date, index, user_id: int = 1) -> None:
    db = get_db()
    total_putts = None
    holes = golf_round.get("holes", {})
    if holes:
        total_putts = sum(
            int(h.get("putts", 0) or 0)
            for h in holes.values()
        )
    db.execute(
        """INSERT OR REPLACE INTO rounds
           (user_id, course_name, date, round_index, tee_name, holes_played,
            entry_mode, holes, total_gross, total_putts, differential, notes, excluded, computed_handicap)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            golf_round.get("course", ""),
            date,
            index,
            golf_round.get("tees", ""),
            golf_round.get("holes_played", ""),
            golf_round.get("entry_mode", ""),
            json.dumps(golf_round.get("holes", {})),
            golf_round.get("total_gross", ""),
            str(total_putts) if total_putts else None,
            golf_round.get("differential", ""),
            golf_round.get("notes", ""),
            1 if golf_round.get("excluded") else 0,
            golf_round.get("computed_handicap", ""),
        ),
    )
    db.commit()
    db.close()
    _log.info("round saved: %s #%s course=%s", date, index, golf_round.get("course", "?"))


def delete_round(date: str, index: str, user_id: int = 1) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM rounds WHERE user_id = ? AND date = ? AND round_index = ?",
        (user_id, date, int(index)),
    )
    db.commit()
    db.close()
    _log.info("round deleted: %s #%s", date, index)


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


def save_course_draft(draft_state: dict, user_id: int = 1) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    draft_dir = _DATA_DIR / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / f"course_draft_{user_id}.json").write_text(json.dumps(draft_state, indent=2))


def load_course_draft(user_id: int = 1) -> dict | None:
    path = _DATA_DIR / "drafts" / f"course_draft_{user_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def clear_course_draft(user_id: int = 1) -> None:
    path = _DATA_DIR / "drafts" / f"course_draft_{user_id}.json"
    if path.exists():
        path.unlink()
        _log.info("course draft cleared")


def save_round_draft(draft_state: dict, user_id: int = 1) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    draft_dir = _DATA_DIR / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / f"round_draft_{user_id}.json").write_text(json.dumps(draft_state, indent=2))


def load_round_draft(user_id: int = 1) -> dict | None:
    path = _DATA_DIR / "drafts" / f"round_draft_{user_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def clear_round_draft(user_id: int = 1) -> None:
    path = _DATA_DIR / "drafts" / f"round_draft_{user_id}.json"
    if path.exists():
        path.unlink()
        _log.info("round draft cleared")


def get_users() -> list:
    db = get_db()
    rows = db.execute("SELECT id, username, display_name FROM users").fetchall()
    db.close()
    return [{"id": r["id"], "username": r["username"], "display_name": r["display_name"]} for r in rows]
