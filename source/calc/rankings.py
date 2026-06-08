import logging
from store import get_users, get_all_rounds, get_courses
from source.models import dict_to_course
from calc import (
    calc_handicap_index,
    calc_scoring_average,
    calc_fir_percent,
    calc_gir_percent,
    calc_putts_per_round,
    calc_scramble_percent,
)

_log = logging.getLogger("pinsheet")

STAT_META = {
    "handicap": {"label": "Handicap", "higher_better": False, "suffix": ""},
    "score": {"label": "Avg Score", "higher_better": False, "suffix": ""},
    "fir": {"label": "FIR", "higher_better": True, "suffix": "%"},
    "gir": {"label": "GIR", "higher_better": True, "suffix": "%"},
    "putts": {"label": "Putts / Rnd", "higher_better": False, "suffix": ""},
    "scramble": {"label": "Scramble", "higher_better": True, "suffix": "%"},
}

BOARD_STATS = ["handicap", "score", "fir", "gir", "putts", "scramble"]


def _filter_rounds_by_date(rounds, date_start: str | None, date_end: str | None) -> list:
    if not date_start and not date_end:
        return rounds
    filtered = []
    for r in rounds:
        if date_start and r.date < date_start:
            continue
        if date_end and r.date > date_end:
            continue
        filtered.append(r)
    return filtered


def _compute_user_stats(rounds, courses_dict, include_9hole: bool) -> dict:
    stat_values = {}
    stat_values["handicap"] = calc_handicap_index(rounds, include_9hole)
    stat_values["score"] = calc_scoring_average(rounds)
    stat_values["fir"] = calc_fir_percent(rounds, courses_dict)
    stat_values["gir"] = calc_gir_percent(rounds)
    stat_values["putts"] = calc_putts_per_round(rounds)
    stat_values["scramble"] = calc_scramble_percent(rounds, courses_dict)
    return stat_values


def compute_rankings(
    sort_key: str = "handicap",
    sort_desc: bool = False,
    date_start: str | None = None,
    date_end: str | None = None,
    include_9hole: bool = True,
) -> list[dict]:
    if sort_key not in STAT_META:
        sort_key = "handicap"

    users = get_users()
    courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}
    higher_better = STAT_META[sort_key]["higher_better"]

    rankings = []
    for user in users:
        rounds = get_all_rounds(user_id=user["id"])
        rounds = _filter_rounds_by_date(rounds, date_start, date_end)
        stats = _compute_user_stats(rounds, courses_dict, include_9hole)
        rankings.append({
            "user_id": user["id"],
            "display_name": user["display_name"],
            "username": user["username"],
            "stats": stats,
        })

    def _sort_key(entry):
        val = entry["stats"][sort_key]
        if val is None:
            return (1, 0)
        return (0, -val if higher_better else val)

    reverse = sort_desc
    rankings.sort(key=_sort_key, reverse=reverse)

    return rankings


def compute_board_meta(rankings, board_stats, stat_meta):
    meta = {}
    for key in board_stats:
        vals = [e["stats"][key] for e in rankings if e["stats"][key] is not None]
        if not vals:
            meta[key] = {"min": None, "max": None, "avg": None}
        else:
            meta[key] = {
                "min": min(vals),
                "max": max(vals),
                "avg": sum(vals) / len(vals),
            }
    return meta
