import logging
from datetime import datetime, timedelta
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
from calc.composite import last_n_rounds, best_n_rounds

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


def _compute_form_svg(form_values: list[float], width: int = 88, height: int = 26) -> dict | None:
    if len(form_values) < 2:
        return None
    mn, mx = min(form_values), max(form_values)
    pad = 3
    range_h = mx - mn or 1
    x_step = (width - pad * 2) / (len(form_values) - 1)
    parts = []
    for i, v in enumerate(form_values):
        px = pad + i * x_step
        py = height - pad - ((v - mn) / range_h) * (height - pad * 2)
        parts.append(f"{'M' if i == 0 else 'L'}{px:.1f} {py:.1f}")
    last_i = len(form_values) - 1
    last_px = pad + last_i * x_step
    last_py = height - pad - ((form_values[-1] - mn) / range_h) * (height - pad * 2)
    return {
        "path": " ".join(parts),
        "final_x": round(last_px, 1),
        "final_y": round(last_py, 1),
        "width": width,
        "height": height,
    }


def _compute_user_stats(rounds, courses_dict, include_9hole: bool, all_rounds: list = None) -> dict:
    l20 = last_n_rounds(rounds, 20)
    b8 = best_n_rounds(rounds, 8)
    stat_values = {}
    stat_values["handicap"] = calc_handicap_index(l20, include_9hole)
    stat_values["score"] = calc_scoring_average(b8)
    stat_values["fir"] = calc_fir_percent(b8, courses_dict)
    stat_values["gir"] = calc_gir_percent(b8)
    stat_values["putts"] = calc_putts_per_round(b8)
    stat_values["scramble"] = calc_scramble_percent(b8, courses_dict)

    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    streak = sum(1 for r in all_rounds if r.date >= thirty_days_ago) if all_rounds else 0
    stat_values["streak"] = streak

    sorted_rounds = sorted(all_rounds, key=lambda r: r.date) if all_rounds else []
    form = []
    for r in sorted_rounds:
        if r.computed_handicap and r.computed_handicap != "0":
            try:
                form.append(float(r.computed_handicap))
            except ValueError:
                pass
    stat_values["form"] = form[-6:]

    stat_values["form_svg"] = _compute_form_svg(form[-6:])

    current_hi = stat_values["handicap"]
    hi_movement = None
    if current_hi is not None and all_rounds:
        thirty_days_ago_dt = datetime.now() - timedelta(days=30)
        cutoff = thirty_days_ago_dt.strftime("%Y-%m-%d")
        prev_hi = None
        sorted_desc = sorted(all_rounds, key=lambda r: r.date, reverse=True)
        for r in sorted_desc:
            if r.date <= cutoff and r.computed_handicap and r.computed_handicap != "0":
                try:
                    prev_hi = float(r.computed_handicap)
                    break
                except ValueError:
                    pass
        if prev_hi is not None:
            diff = prev_hi - current_hi
            hi_movement = f"{'▼' if diff > 0 else '▲'} {abs(diff):.1f} this month"
    stat_values["hi_movement"] = hi_movement

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
        all_user_rounds = get_all_rounds(user_id=user["id"])
        filtered_rounds = _filter_rounds_by_date(all_user_rounds, date_start, date_end)
        stats = _compute_user_stats(filtered_rounds, courses_dict, include_9hole, all_user_rounds)
        rankings.append({
            "user_id": user["id"],
            "display_name": user["display_name"],
            "username": user["username"],
            "stats": stats,
        })

    for entry in rankings:
        best_stat = None
        best_rank = float("inf")
        for key in BOARD_STATS:
            val = entry["stats"].get(key)
            if val is None:
                continue
            sorted_vals = sorted(
                [(e["stats"].get(key), e["user_id"]) for e in rankings if e["stats"].get(key) is not None],
                key=lambda x: x[0],
                reverse=STAT_META[key]["higher_better"],
            )
            for rank, (_, uid) in enumerate(sorted_vals, 1):
                if uid == entry["user_id"]:
                    if rank < best_rank:
                        best_rank = rank
                        best_stat = key
                    break
        entry["stats"]["lead_stat"] = best_stat

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
