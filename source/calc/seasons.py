import calendar
from collections import Counter
from datetime import date
from source.models import RoundData, CourseData


def calc_rounds_this_year(all_rounds: list[RoundData]) -> int:
    current_year = str(date.today().year)
    return sum(1 for r in all_rounds if r.date.startswith(current_year))


def calc_rounds_total(all_rounds: list[RoundData]) -> int:
    return len(all_rounds)


def calc_golfiest_month(season_rounds: list[RoundData]) -> tuple[str, int]:
    if not season_rounds:
        return ("—", 0)
    counts = Counter()
    for r in season_rounds:
        d = r.date
        try:
            month = int(d[5:7])
        except (ValueError, IndexError):
            continue
        counts[month] += 1
    if not counts:
        return ("—", 0)
    best_month, best_count = counts.most_common(1)[0]
    return (calendar.month_name[best_month], best_count)


def calc_most_common_day(season_rounds: list[RoundData]) -> tuple[str, int]:
    if not season_rounds:
        return ("—", 0)
    counts = Counter()
    for r in season_rounds:
        d = r.date
        try:
            day_name = date.fromisoformat(d).strftime("%A")
        except ValueError:
            continue
        counts[day_name] += 1
    if not counts:
        return ("—", 0)
    best_day, best_count = counts.most_common(1)[0]
    return (best_day, best_count)


def calc_weekly_streak(season_rounds: list[RoundData]) -> int:
    if not season_rounds:
        return 0
    weeks = set()
    for r in season_rounds:
        d = r.date
        try:
            parsed = date.fromisoformat(d)
            weeks.add(parsed.isocalendar()[:2])
        except ValueError:
            continue
    if not weeks:
        return 0
    sorted_weeks = sorted(weeks)
    best = 1
    current = 1
    for i in range(1, len(sorted_weeks)):
        prev_year, prev_week = sorted_weeks[i - 1]
        curr_year, curr_week = sorted_weeks[i]
        prev_date = date.fromisocalendar(prev_year, prev_week, 1)
        curr_date = date.fromisocalendar(curr_year, curr_week, 1)
        if (curr_date - prev_date).days == 7:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def calc_season_yardage(season_rounds: list[RoundData], courses: dict[str, CourseData], mode: str) -> float | None:
    total_yards = 0.0
    for r in season_rounds:
        transport = r.transport
        if mode == "walking" and transport not in ("", "walking"):
            continue
        if mode == "riding" and transport != "riding":
            continue
        course_data = courses.get(r.course)
        tee_name = r.tees
        tee = course_data.tees.get(tee_name) if course_data else None
        if not tee or tee.yardage == "0":
            continue
        yardage = int(tee.yardage)
        holes = r.holes
        if holes:
            yardage = yardage * len(holes) // 18
        total_yards += yardage
    if total_yards == 0:
        return None
    return total_yards / 1760


def calc_hi_journey(all_rounds: list[RoundData], season_rounds: list[RoundData], live_hi: float | None = None) -> tuple[float, float, float] | None:
    if live_hi is not None:
        end_hi = live_hi
    else:
        end_hi = None
        for r in season_rounds:
            ch = r.computed_handicap
            if ch and ch != "0":
                end_hi = float(ch)
                break
    if end_hi is None:
        return None

    season_dates = [r.date for r in season_rounds if r.date]
    if not season_dates:
        return None
    earliest = min(season_dates)

    start_hi = None
    for r in all_rounds:
        if r.date <= earliest:
            ch = r.computed_handicap
            if ch and ch != "0":
                start_hi = float(ch)
                break
    if start_hi is None:
        for r in season_rounds:
            ch = r.computed_handicap
            if ch and ch != "0":
                start_hi = float(ch)
                break
    if start_hi is None:
        return None

    delta = start_hi - end_hi
    return (start_hi, end_hi, delta)


def calc_season_rounds(rounds: list[RoundData], settings: dict) -> list[RoundData]:
    current_year = str(date.today().year)
    start_month = settings.get("season_start_month", 1)
    end_month = settings.get("season_end_month", 12)
    start_day = settings.get("season_start_day", 1)
    end_day = settings.get("season_end_day", 28)
    result = []
    for r in rounds:
        d = r.date
        if not d.startswith(current_year):
            continue
        try:
            month = int(d[5:7])
            day = int(d[8:10])
        except (ValueError, IndexError):
            continue
        round_md = (month, day)
        if (start_month, start_day) <= round_md <= (end_month, end_day):
            result.append(r)
    return result
