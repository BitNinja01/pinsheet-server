from datetime import date, timedelta

from source.models import RoundData, CourseData, HoleData, HoleDef, TeeData


def calc_trend(all_rounds: list[RoundData], calc_fn, *args, filter_fn=None) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for r in chronological:
        if filter_fn and not filter_fn(r):
            continue
        val = calc_fn([r], *args)
        if val is not None:
            result.append((r.date, val))
    return result


def iter_holes(rounds: list[RoundData], courses: dict[str, CourseData]):
    for r in rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes_dict = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes_dict.get(str(hole_num), HoleDef()).par
            yield r, hole_num, h, par, r.course, holes_dict


def calc_scoring_average(rounds: list[RoundData]) -> float | None:
    scores = [int(r.total_gross) for r in rounds
              if r.total_gross and r.total_gross != "0"
              and r.holes_selection == "all"]
    return sum(scores) / len(scores) if scores else None


def calc_scoring_trend(all_rounds: list[RoundData]) -> list:
    chronological = list(reversed(all_rounds))
    return [
        (r.date, int(r.total_gross))
        for r in chronological
        if r.total_gross and r.total_gross != "0"
        and r.holes_selection == "all"
    ]


def calc_scoring_avg_by_par_type(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    totals = {3: [], 4: [], 5: []}
    for r in rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if par in totals and h.gross:
                totals[par].append(h.gross)
    return {p: sum(v) / len(v) if v else None for p, v in totals.items()}


def calc_par_or_better_percent(rounds: list[RoundData], courses: dict[str, CourseData]) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if par and h.gross:
                total += 1
                if h.gross <= par:
                    hits += 1
    return (hits / total) * 100 if total else None


def calc_score_distribution(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    counts = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "triple_plus": 0}
    total = 0
    for r in rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if not par or not h.gross:
                continue
            diff = h.gross - par
            total += 1
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
    if not total:
        return {k: None for k in counts}
    return {k: (v / total) * 100 for k, v in counts.items()}


def calc_big_number_rate(rounds: list[RoundData], courses: dict[str, CourseData]) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if not par or not h.gross:
                continue
            total += 1
            if h.gross - par >= 4:
                hits += 1
    return (hits / total) * 100 if total else None


def calc_clean_card_percent(rounds: list[RoundData], courses: dict[str, CourseData]) -> float | None:
    eligible = [r for r in rounds if r.holes and courses.get(r.course)
                and r.holes_selection == "all"]
    if not eligible:
        return None
    clean = 0
    for r in eligible:
        course = courses[r.course]
        holes = course.holes
        if not any(
            h.gross - holes.get(str(n), HoleDef()).par >= 2
            for n, h in r.holes.items()
            if holes.get(str(n), HoleDef()).par
        ):
            clean += 1
    return (clean / len(eligible)) * 100


def calc_scoring_consistency(rounds: list[RoundData], courses: dict[str, CourseData]) -> float | None:
    diffs = []
    for r in rounds:
        if not r.total_gross or r.total_gross == "0":
            continue
        if r.holes_selection != "all":
            continue
        course = courses.get(r.course)
        if not course:
            continue
        course_par = course.par
        if not course_par:
            continue
        diffs.append(int(r.total_gross) - int(course_par))
    if len(diffs) < 2:
        return None
    mean = sum(diffs) / len(diffs)
    return (sum((d - mean) ** 2 for d in diffs) / len(diffs)) ** 0.5


def calc_score_components(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    approach = []
    scramble = []
    all_putts = []
    for r in rounds:
        if not r.holes:
            continue
        course_name = r.course
        course = courses.get(course_name)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if not par or not h.gross or not h.putts:
                continue
            gross = h.gross
            putts = h.putts
            all_putts.append(putts)
            if par == 3:
                continue
            ball_striking = (gross - putts) - (par - 2)
            fw = h.fairway
            if fw == "H":
                approach.append(ball_striking)
            elif fw and fw != "N":
                scramble.append(ball_striking)
    return {
        "approach": sum(approach) / len(approach) if approach else None,
        "scramble": sum(scramble) / len(scramble) if scramble else None,
        "putting": sum(all_putts) / len(all_putts) if all_putts else None,
    }


def calc_pob_trend(all_rounds: list[RoundData], courses: dict[str, CourseData]) -> list:
    return calc_trend(all_rounds, calc_par_or_better_percent, courses)


def calc_clean_card_trend(all_rounds: list[RoundData], courses: dict[str, CourseData]) -> list:
    return calc_trend(all_rounds, calc_clean_card_percent, courses)


def calc_big_number_trend(all_rounds: list[RoundData], courses: dict[str, CourseData]) -> list:
    return calc_trend(all_rounds, calc_big_number_rate, courses)


def calc_per_hole_stats(
    rounds: list[RoundData],
    courses: dict[str, CourseData],
    course_name: str,
    hole_num: int,
    handicap_index: float | None = None,
) -> dict:
    h_str = str(hole_num)
    gross_vals: list[int] = []
    fir_hits = 0
    fir_eligible = 0
    fir_miss_l = 0
    fir_miss_r = 0
    gir_hits = 0
    gir_total = 0
    gir_miss_s = 0
    gir_miss_lo = 0
    gir_miss_l = 0
    gir_miss_r = 0
    putts_vals: list[int] = []
    pen_vals: list[int] = []
    scramble_attempts = 0
    scramble_successes = 0
    par_val = None
    strokes_received = 0
    holes_with_si = 0

    for r, h_round_num, h, par, round_course_name, holes_dict in iter_holes(rounds, courses):
        if round_course_name != course_name:
            continue
        if str(h_round_num) != h_str:
            continue

        if par:
            par_val = par

        if h.gross:
            gross = h.gross
            gross_vals.append(gross)

            if handicap_index is not None and par_val:
                si_val = holes_dict.get(h_str, HoleDef()).hole_index
                if si_val:
                    try:
                        si_int = si_val
                        course_obj = courses.get(course_name)
                        tee_data = course_obj.tees if course_obj else {}
                        first_tee = next(iter(tee_data.values())) if tee_data else TeeData()
                        slope = float(first_tee.slope or "113")
                        rating = float(first_tee.rating or "0")
                        c_par = int(course_obj.par) if course_obj else par_val
                        course_hcp = round(handicap_index * slope / 113 + (c_par - rating))
                        strokes_received += 1 if si_int <= course_hcp else 0
                        holes_with_si += 1
                    except (ValueError, TypeError, StopIteration):
                        pass

        if par_val and par_val in (4, 5) and h.fairway != "N":
            fir_eligible += 1
            fw = h.fairway
            if not fw or fw == "H":
                fir_hits += 1
            elif fw in {"L", "OBL"}:
                fir_miss_l += 1
            elif fw in {"R", "OBR"}:
                fir_miss_r += 1

        gir = h.gir
        if gir == "N":
            pass
        elif not gir or gir == "H":
            gir_hits += 1
            gir_total += 1
        elif gir:
            gir_total += 1
            if gir in {"L", "OBL"}:
                gir_miss_l += 1
            elif gir in {"R", "OBR"}:
                gir_miss_r += 1
            elif gir in {"S", "OBS"}:
                gir_miss_s += 1
            elif gir in {"LO", "OBLO"}:
                gir_miss_lo += 1

        if h.putts:
            putts_vals.append(h.putts)

        if h.penalties:
            pen_vals.append(h.penalties)

        if gir and gir != "H" and h.gross and par_val:
            scramble_attempts += 1
            if h.gross <= par_val:
                scramble_successes += 1

    fir_pct = (fir_hits / fir_eligible * 100) if fir_eligible else None
    total_misses = fir_miss_l + fir_miss_r
    fir_miss_l_pct = (fir_miss_l / total_misses * 100) if total_misses else None
    fir_miss_r_pct = (fir_miss_r / total_misses * 100) if total_misses else None

    total_gir_misses = gir_miss_s + gir_miss_lo + gir_miss_l + gir_miss_r

    total_holes = len(gross_vals)
    avg_score = sum(gross_vals) / total_holes if total_holes else None
    avg_vs_par_val = (avg_score - par_val) if (avg_score is not None and par_val is not None) else None

    expected_val = (strokes_received / holes_with_si) if holes_with_si else None
    gap_val = (avg_vs_par_val - expected_val) if (avg_vs_par_val is not None and expected_val is not None) else None

    return {
        "rounds_played": total_holes,
        "avg_score": avg_score,
        "avg_vs_par": avg_vs_par_val,
        "expected": expected_val,
        "gap": gap_val,
        "fir_pct": fir_pct,
        "fir_miss_l_pct": fir_miss_l_pct,
        "fir_miss_r_pct": fir_miss_r_pct,
        "gir_pct": (gir_hits / gir_total * 100) if gir_total else None,
        "gir_miss_s_pct": (gir_miss_s / total_gir_misses * 100) if total_gir_misses else None,
        "gir_miss_lo_pct": (gir_miss_lo / total_gir_misses * 100) if total_gir_misses else None,
        "gir_miss_l_pct": (gir_miss_l / total_gir_misses * 100) if total_gir_misses else None,
        "gir_miss_r_pct": (gir_miss_r / total_gir_misses * 100) if total_gir_misses else None,
        "avg_putts": sum(putts_vals) / len(putts_vals) if putts_vals else None,
        "avg_penalties": sum(pen_vals) / len(pen_vals) if pen_vals else None,
        "scramble_pct": (scramble_successes / scramble_attempts * 100) if scramble_attempts else None,
    }


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


def calc_per_round_average(rounds: list[RoundData], courses: dict[str, CourseData], predicate) -> float | None:
    total = 0
    for r in rounds:
        course_name = r.course
        course = courses.get(course_name)
        course_holes = course.holes if course else {}
        for hn, h in r.holes.items():
            gross = h.gross
            par = course_holes.get(hn, HoleDef()).par
            if gross and par and predicate(gross, par):
                total += 1
    return total / len(rounds) if rounds else None


def calc_hole_percentage(rounds: list[RoundData], courses: dict[str, CourseData], predicate) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        course_name = r.course
        course = courses.get(course_name)
        course_holes = course.holes if course else {}
        for hn, h in r.holes.items():
            gross = h.gross
            par = course_holes.get(hn, HoleDef()).par
            if gross and par:
                total += 1
                if predicate(gross, par):
                    hits += 1
    return (hits / total * 100) if total else None


def stat_delta(current, previous, higher_better=False, precision=1, suffix=""):
    if current is None or previous is None or current == previous:
        return "", "\u2014", ""
    raw = current - previous
    is_up = (raw > 0 and higher_better) or (raw < 0 and not higher_better)
    cls = "is-up" if is_up else "is-down"
    cell_cls = "is-improved" if is_up else "is-declined"
    text = f"{raw:+.{precision}f}{suffix} vs L20"
    return cls, text, cell_cls
