from datetime import date, timedelta


def calc_historical_window(all_rounds: list, target_date: str) -> list:
    return [r for r in all_rounds if r.get("date", "") <= target_date][:20]


def calc_last_year_handicap(all_rounds: list, include_9hole: bool) -> float | None:
    if not all_rounds or len(all_rounds) < 3:
        return None
    target = date.today() - timedelta(days=365)
    best = None
    best_dist = None
    for r in all_rounds:
        rd = r.get("date")
        if not rd:
            continue
        try:
            rd_date = date.fromisoformat(rd)
        except (ValueError, TypeError):
            continue
        dist = abs((rd_date - target).days)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = r
    if best is None or best_dist > 60:
        return None
    ch = best.get("computed_handicap", "")
    if not ch or ch in ("0", ""):
        return None
    try:
        return float(ch)
    except (ValueError, TypeError):
        return None


def calc_round_vs_par(round_data: dict, courses: dict) -> int | None:
    total = int(round_data.get("total_gross", 0))
    if not total:
        return None
    course_holes = courses.get(round_data.get("course", ""), {}).get("holes", {})
    actual_par = sum(
        int(course_holes[str(h)]["par"])
        for h in round_data.get("holes", {})
        if course_holes.get(str(h), {}).get("par")
    )
    return (total - actual_par) if actual_par else None


def calc_avg_vs_par(rounds: list, courses: dict) -> float | None:
    diffs = []
    for r in rounds:
        gross = r.get("total_gross")
        if not gross or gross == "0":
            continue
        course_holes = courses.get(r.get("course", ""), {}).get("holes", {})
        actual_par = sum(
            int(course_holes[str(h)]["par"])
            for h in r.get("holes", {})
            if course_holes.get(str(h), {}).get("par")
        )
        if actual_par:
            diffs.append(int(gross) - actual_par)
    return sum(diffs) / len(diffs) if diffs else None


def calc_round_vs_rating(round_data: dict, courses: dict) -> float | None:
    course = courses.get(round_data.get("course", ""), {})
    tee = course.get("tees", {}).get(round_data.get("tees", ""), {})
    sel = round_data.get("holes_selection", "all")
    key = "front_rating" if sel == "front" else "back_rating" if sel == "back" else "rating"
    raw = tee.get(key)
    if raw is None:
        return None
    rating = float(raw)
    total = int(round_data.get("total_gross", 0))
    return total - rating if total else None


def calc_avg_vs_rating(rounds: list, courses: dict) -> float | None:
    diffs = []
    for r in rounds:
        gross = r.get("total_gross")
        if not gross or gross == "0":
            continue
        course = courses.get(r.get("course", ""), {})
        tee = course.get("tees", {}).get(r.get("tees", ""), {})
        sel = r.get("holes_selection", "all")
        key = "front_rating" if sel == "front" else "back_rating" if sel == "back" else "rating"
        raw = tee.get(key)
        if raw is None:
            continue
        diffs.append(int(gross) - float(raw))
    return sum(diffs) / len(diffs) if diffs else None


def calc_penalties_per_round(rounds: list) -> float | None:
    totals = []
    for r in rounds:
        if not r.get("holes"):
            continue
        pen = sum(int(h.get("penalties", "0")) for h in r["holes"].values())
        totals.append(pen)
    return sum(totals) / len(totals) if totals else None
