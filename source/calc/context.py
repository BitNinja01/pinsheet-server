from datetime import date, timedelta

from calc.handicap import calc_handicap_index


def calc_historical_window(all_rounds: list, target_date: str) -> list:
    return [r for r in all_rounds if r.get("date", "") <= target_date][:20]


def calc_last_year_handicap(all_rounds: list, include_9hole: bool) -> float | None:
    today = date.today()
    target = today.replace(year=today.year - 1)
    window_start = target - timedelta(days=60)
    window_end = target + timedelta(days=60)
    for r in all_rounds:
        if not r.get("differential") or r["differential"] == "0":
            continue
        d = r.get("date", "")
        if window_start.isoformat() <= d <= window_end.isoformat():
            window = calc_historical_window(all_rounds, d)
            hi = calc_handicap_index(window, include_9hole)
            if hi is not None:
                return hi
    return None


def calc_round_vs_par(round_data: dict, courses: dict) -> int | None:
    course = courses.get(round_data.get("course", ""), {})
    par = int(course.get("par", 0))
    total = int(round_data.get("total_gross", 0))
    return total - par if par and total else None


def calc_avg_vs_par(rounds: list, courses: dict) -> float | None:
    vals = [calc_round_vs_par(r, courses) for r in rounds]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def calc_round_vs_rating(round_data: dict, courses: dict) -> float | None:
    course = courses.get(round_data.get("course", ""), {})
    tees = course.get("tees", {}).get(round_data.get("tees", ""), {})
    rating = float(tees.get("rating", 72))
    total = int(round_data.get("total_gross", 0))
    return total - rating if total else None


def calc_avg_vs_rating(rounds: list, courses: dict) -> float | None:
    vals = [calc_round_vs_rating(r, courses) for r in rounds]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def calc_penalties_per_round(rounds: list) -> float | None:
    totals = []
    for r in rounds:
        if not r.get("holes"):
            continue
        pen = sum(int(h.get("penalties", "0")) for h in r["holes"].values())
        totals.append(pen)
    return sum(totals) / len(totals) if totals else None
