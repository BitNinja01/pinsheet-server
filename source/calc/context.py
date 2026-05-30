from datetime import date, timedelta

from calc.models import RoundData, CourseData, HoleDef


def calc_historical_window(all_rounds: list[RoundData], target_date: str) -> list[RoundData]:
    return [r for r in all_rounds if r.date <= target_date][:20]


def calc_last_year_handicap(all_rounds: list[RoundData], include_9hole: bool) -> float | None:
    if not all_rounds or len(all_rounds) < 3:
        return None
    target = date.today() - timedelta(days=365)
    best = None
    best_dist = None
    for r in all_rounds:
        rd = r.date
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
    ch = best.computed_handicap
    if not ch or ch in ("0", ""):
        return None
    try:
        return float(ch)
    except (ValueError, TypeError):
        return None


def calc_round_vs_par(round_data: RoundData, courses: dict[str, CourseData]) -> int | None:
    total = int(round_data.total_gross) if round_data.total_gross else 0
    if not total:
        return None
    course = courses.get(round_data.course)
    course_holes = course.holes if course else {}
    actual_par = sum(
        course_holes[str(h)].par
        for h in round_data.holes
        if course_holes.get(str(h), HoleDef()).par
    )
    return (total - actual_par) if actual_par else None


def calc_avg_vs_par(rounds: list[RoundData], courses: dict[str, CourseData]) -> float | None:
    diffs = []
    for r in rounds:
        gross = r.total_gross
        if not gross or gross == "0":
            continue
        course = courses.get(r.course)
        course_holes = course.holes if course else {}
        actual_par = sum(
            course_holes[str(h)].par
            for h in r.holes
            if course_holes.get(str(h), HoleDef()).par
        )
        if actual_par:
            diffs.append(int(gross) - actual_par)
    return sum(diffs) / len(diffs) if diffs else None


def calc_round_vs_rating(round_data: RoundData, courses: dict[str, CourseData]) -> float | None:
    course = courses.get(round_data.course)
    tee = course.tees.get(round_data.tees) if course else None
    sel = round_data.holes_selection
    key = "front_rating" if sel == "front" else "back_rating" if sel == "back" else "rating"
    raw = getattr(tee, key, None) if tee else None
    if raw is None:
        return None
    rating = float(raw)
    total = int(round_data.total_gross) if round_data.total_gross else 0
    return total - rating if total else None


def calc_avg_vs_rating(rounds: list[RoundData], courses: dict[str, CourseData]) -> float | None:
    diffs = []
    for r in rounds:
        gross = r.total_gross
        if not gross or gross == "0":
            continue
        course = courses.get(r.course)
        tee = course.tees.get(r.tees) if course else None
        sel = r.holes_selection
        key = "front_rating" if sel == "front" else "back_rating" if sel == "back" else "rating"
        raw = getattr(tee, key, None) if tee else None
        if raw is None:
            continue
        diffs.append(int(gross) - float(raw))
    return sum(diffs) / len(diffs) if diffs else None


def calc_penalties_per_round(rounds: list[RoundData]) -> float | None:
    totals = []
    for r in rounds:
        if not r.holes:
            continue
        pen = sum(h.penalties for h in r.holes.values())
        totals.append(pen)
    return sum(totals) / len(totals) if totals else None
