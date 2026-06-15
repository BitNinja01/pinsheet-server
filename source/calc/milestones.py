from collections import Counter
from source.models import RoundData, CourseData, HoleDef


def calc_personal_bests(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    best_gross = best_diff = most_fir = most_gir = fewest_putts = None
    best_gross_date = best_diff_date = most_fir_date = most_gir_date = fewest_putts_date = None
    for r in [r for r in rounds if r.holes_selection == "all"]:
        date = r.date
        if r.total_gross and r.total_gross != "0":
            g = int(r.total_gross)
            if best_gross is None or g < best_gross:
                best_gross = g
                best_gross_date = date
        if r.differential and r.differential != "0":
            d = float(r.differential)
            if best_diff is None or d < best_diff:
                best_diff = d
                best_diff_date = date
        if not r.holes:
            continue
        fir = sum(1 for h in r.holes.values() if not h.fairway or h.fairway == "H")
        if most_fir is None or fir > most_fir:
            most_fir = fir
            most_fir_date = date
        gir = sum(1 for h in r.holes.values() if not h.gir or h.gir == "H")
        if most_gir is None or gir > most_gir:
            most_gir = gir
            most_gir_date = date
        putts = sum(h.putts for h in r.holes.values() if h.putts)
        if putts > 0 and (fewest_putts is None or putts < fewest_putts):
            fewest_putts = putts
            fewest_putts_date = date
    return {
        "best_gross": best_gross,
        "best_gross_date": best_gross_date,
        "best_diff": best_diff,
        "best_diff_date": best_diff_date,
        "most_fir": most_fir,
        "most_fir_date": most_fir_date,
        "most_gir": most_gir,
        "most_gir_date": most_gir_date,
        "fewest_putts": fewest_putts,
        "fewest_putts_date": fewest_putts_date,
    }


def calc_nemesis_best_holes(rounds: list[RoundData], courses: dict[str, CourseData]) -> tuple:
    hole_data: dict = {}
    for r in rounds:
        if not r.holes:
            continue
        course_name = r.course
        course = courses.get(course_name)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if not par or not h.gross:
                continue
            key = (course_name, hole_num)
            hole_data.setdefault(key, []).append(h.gross - par)
    averages = [
        (course, hole, sum(diffs) / len(diffs))
        for (course, hole), diffs in hole_data.items()
        if len(diffs) >= 2
    ]
    averages.sort(key=lambda x: x[2])
    return list(reversed(averages[-5:])), averages[:5]


def calc_best_single_round(season_rounds: list[RoundData]) -> RoundData | None:
    best = None
    best_diff = None
    for r in season_rounds:
        raw = r.differential
        if not raw:
            continue
        try:
            diff = float(raw)
        except (ValueError, TypeError):
            continue
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = r
    return best


def calc_best_3round_stretch(season_rounds: list[RoundData]) -> tuple[float, str, str] | None:
    eligible = [r for r in sorted(season_rounds, key=lambda r: r.date) if r.differential not in (None, "")]
    if len(eligible) < 3:
        return None
    best_avg = None
    best_start = None
    best_end = None
    for i in range(len(eligible) - 2):
        window = eligible[i:i + 3]
        try:
            avg = sum(float(r.differential) for r in window) / 3
        except (ValueError, TypeError):
            continue
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_start = window[0].date
            best_end = window[2].date
    if best_avg is None:
        return None
    return (best_avg, best_start, best_end)


def calc_biggest_improvement(season_rounds: list[RoundData]) -> tuple[float, RoundData] | None:
    best_gap = None
    best_round = None
    for r in season_rounds:
        raw_diff = r.differential
        raw_hi = r.computed_handicap
        if raw_diff in (None, "") or raw_hi in (None, ""):
            continue
        try:
            gap = float(raw_hi) - float(raw_diff)
        except (ValueError, TypeError):
            continue
        if gap > 0 and (best_gap is None or gap > best_gap):
            best_gap = gap
            best_round = r
    if best_gap is None:
        return None
    return (best_gap, best_round)


def calc_first_score_milestone(season_rounds: list[RoundData], all_rounds: list[RoundData]) -> tuple[int, RoundData] | None:
    milestones = [100, 95, 90, 85, 80, 75, 70]
    season_ids = {id(r) for r in season_rounds}
    pre_season = [r for r in all_rounds if id(r) not in season_ids]
    already_broken = set()
    for r in pre_season:
        if r.holes_selection != "all":
            continue
        raw = r.total_gross
        if not raw:
            continue
        try:
            score = int(raw)
        except (ValueError, TypeError):
            continue
        for threshold in milestones:
            if score < threshold:
                already_broken.add(threshold)
    eligible = [t for t in milestones if t not in already_broken]
    if not eligible:
        return None
    sorted_rounds = sorted(season_rounds, key=lambda r: r.date)
    best_threshold = None
    best_round = None
    for r in sorted_rounds:
        if r.holes_selection != "all":
            continue
        raw = r.total_gross
        if not raw:
            continue
        try:
            score = int(raw)
        except (ValueError, TypeError):
            continue
        for threshold in eligible:
            if score < threshold and (best_threshold is None or threshold < best_threshold):
                best_threshold = threshold
                best_round = r
    if best_threshold is None:
        return None
    return (best_threshold, best_round)


def calc_first_hi_milestone(season_rounds: list[RoundData], all_rounds: list[RoundData]) -> tuple[int, RoundData] | None:
    milestones = list(range(36, 0, -1))
    season_ids = {id(r) for r in season_rounds}
    pre_season = [r for r in all_rounds if id(r) not in season_ids]
    already_broken = set()
    for r in pre_season:
        raw = r.computed_handicap
        if not raw:
            continue
        try:
            hi = float(raw)
        except (ValueError, TypeError):
            continue
        for threshold in milestones:
            if hi < threshold:
                already_broken.add(threshold)
    eligible = [t for t in milestones if t not in already_broken]
    if not eligible:
        return None
    sorted_rounds = sorted(season_rounds, key=lambda r: r.date)
    best_threshold = None
    best_round = None
    for r in sorted_rounds:
        raw = r.computed_handicap
        if not raw:
            continue
        try:
            hi = float(raw)
        except (ValueError, TypeError):
            continue
        for threshold in eligible:
            if hi < threshold and (best_threshold is None or threshold < best_threshold):
                best_threshold = threshold
                best_round = r
    if best_threshold is None:
        return None
    return (best_threshold - 1, best_round)


def calc_score_breakdown(season_rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    counts = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "triple_plus": 0}
    for r in season_rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if not par or not h.gross:
                continue
            diff = h.gross - par
            if diff <= -2:
                counts["eagle"] += 1
            elif diff == -1:
                counts["birdie"] += 1
            elif diff == 0:
                counts["par"] += 1
            elif diff == 1:
                counts["bogey"] += 1
            elif diff == 2:
                counts["double"] += 1
            else:
                counts["triple_plus"] += 1
    return counts


def calc_hole_in_ones(season_rounds: list[RoundData], courses: dict[str, CourseData]) -> int:
    count = 0
    for r in season_rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            if h.gross == 1:
                count += 1
    return count


def calc_best_gir_round(season_rounds: list[RoundData]) -> tuple[RoundData, int] | None:
    best = None
    best_count = -1
    for r in season_rounds:
        if not r.holes:
            continue
        count = sum(1 for h in r.holes.values() if not h.gir or h.gir == "H")
        if count > best_count:
            best_count = count
            best = r
    if best is None or best_count == 0:
        return None
    return best, best_count


def calc_best_fir_round(season_rounds: list[RoundData], courses: dict[str, CourseData]) -> tuple[RoundData, int] | None:
    best = None
    best_count = -1
    for r in season_rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        course_holes = course.holes if course else {}
        count = sum(
            1 for h_num, h in r.holes.items()
            if (not h.fairway or h.fairway == "H")
            and course_holes.get(str(h_num), HoleDef()).par != 3
        )
        if count > best_count:
            best_count = count
            best = r
    if best is None or best_count == 0:
        return None
    return best, best_count


def calc_most_played_course(season_rounds: list[RoundData]) -> tuple[str, int, float] | None:
    if not season_rounds:
        return None
    counts: Counter = Counter()
    for r in season_rounds:
        course = r.course
        if course:
            counts[course] += 1
    if not counts:
        return None
    best_count = counts.most_common(1)[0][1]
    candidates = [c for c, n in counts.items() if n == best_count]
    best_course = None
    best_avg = None
    for course in candidates:
        diffs = [float(r.differential) for r in season_rounds if r.course == course and r.differential not in (None, "")]
        avg = sum(diffs) / len(diffs) if diffs else float("inf")
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_course = course
    return (best_course, best_count, best_avg if best_avg != float("inf") else 0.0)


def calc_penalty_free_rounds(season_rounds: list[RoundData]) -> int:
    count = 0
    for r in season_rounds:
        if not r.holes:
            continue
        total = sum(h.penalties for h in r.holes.values())
        if total == 0:
            count += 1
    return count
