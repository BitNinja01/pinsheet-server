from calc.models import RoundData, CourseData, HoleDef


def calc_penalty_stats(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    round_totals = []
    penalty_vs_par = []
    clean_vs_par = []
    hole_counts: dict = {}
    hole_penalties: dict = {}
    for r in rounds:
        if not r.holes:
            continue
        course_name = r.course
        course = courses.get(course_name)
        holes = course.holes if course else {}
        round_pen = 0
        for hole_num, h in r.holes.items():
            if not h.gross:
                continue
            par = holes.get(str(hole_num), HoleDef()).par
            gross = h.gross
            pen = h.penalties
            round_pen += pen
            key = (course_name, hole_num)
            hole_counts[key] = hole_counts.get(key, 0) + 1
            if pen > 0:
                hole_penalties[key] = hole_penalties.get(key, 0) + pen
                if par:
                    penalty_vs_par.append(gross - par)
            elif par:
                clean_vs_par.append(gross - par)
        round_totals.append(round_pen)
    worst = sorted(
        [
            (course, hole, hole_penalties.get((course, hole), 0) / hole_counts[(course, hole)])
            for (course, hole) in hole_counts
            if hole_counts[(course, hole)] >= 2 and (course, hole) in hole_penalties
        ],
        key=lambda x: x[2],
        reverse=True,
    )[:5]
    return {
        "rate_per_round": sum(round_totals) / len(round_totals) if round_totals else None,
        "penalty_avg_vs_par": sum(penalty_vs_par) / len(penalty_vs_par) if penalty_vs_par else None,
        "clean_avg_vs_par": sum(clean_vs_par) / len(clean_vs_par) if clean_vs_par else None,
        "worst_holes": worst,
    }


def calc_momentum_recovery(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    after_bogey = []
    after_double = []
    for r in rounds:
        if not r.holes:
            continue
        course_name = r.course
        course = courses.get(course_name)
        holes = course.holes if course else {}
        hole_nums = sorted(r.holes.keys(), key=lambda x: int(x))
        for i, hole_num in enumerate(hole_nums[:-1]):
            h = r.holes[hole_num]
            par = holes.get(str(hole_num), HoleDef()).par
            if not par or not h.gross:
                continue
            vs_par = h.gross - par
            next_num = hole_nums[i + 1]
            next_h = r.holes[next_num]
            next_par = holes.get(str(next_num), HoleDef()).par
            if not next_par or not next_h.gross:
                continue
            next_vs_par = next_h.gross - next_par
            if vs_par >= 1:
                after_bogey.append(next_vs_par)
            if vs_par >= 2:
                after_double.append(next_vs_par <= 0)
    return {
        "after_bogey_avg": sum(after_bogey) / len(after_bogey) if after_bogey else None,
        "recovery_rate": sum(after_double) / len(after_double) * 100 if after_double else None,
    }
