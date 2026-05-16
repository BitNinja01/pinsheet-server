import calendar
from collections import Counter
from datetime import date

from calc.handicap import calc_handicap_index, calc_handicap_trend
from calc.approach import calc_fir_percent, calc_fir_trend, calc_gir_percent, calc_gir_trend, calc_scramble_percent, calc_scramble_trend
from calc.putting import calc_putts_per_round, calc_putts_trend, calc_one_putt_percent, calc_one_putt_trend, calc_three_putt_percent, calc_three_putt_trend, calc_putts_per_gir, calc_putts_gir_trend


def calc_trend(all_rounds: list, calc_fn, *args, filter_fn=None) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for r in chronological:
        if filter_fn and not filter_fn(r):
            continue
        val = calc_fn([r], *args)
        if val is not None:
            result.append((r.get("date", ""), val))
    return result


def calc_scoring_average(rounds) -> float | None:
    scores = [int(r["total_gross"]) for r in rounds
              if r.get("total_gross") and r["total_gross"] != "0"
              and r.get("holes_selection", "all") == "all"]
    return sum(scores) / len(scores) if scores else None


def calc_scoring_trend(all_rounds) -> list:
    chronological = list(reversed(all_rounds))
    return [
        (r.get("date", ""), int(r["total_gross"]))
        for r in chronological
        if r.get("total_gross") and r["total_gross"] != "0"
        and r.get("holes_selection", "all") == "all"
    ]


def calc_scoring_avg_by_par_type(rounds, courses) -> dict:
    totals = {3: [], 4: [], 5: []}
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par in totals and h.get("gross"):
                totals[par].append(int(h["gross"]))
    return {p: sum(v) / len(v) if v else None for p, v in totals.items()}


def calc_par_or_better_percent(rounds, courses) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par and h.get("gross"):
                total += 1
                if int(h["gross"]) <= par:
                    hits += 1
    return (hits / total) * 100 if total else None


def calc_score_distribution(rounds, courses) -> dict:
    counts = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "triple_plus": 0}
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par or not h.get("gross"):
                continue
            diff = int(h["gross"]) - par
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


def calc_big_number_rate(rounds, courses) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par or not h.get("gross"):
                continue
            total += 1
            if int(h["gross"]) - par >= 4:
                hits += 1
    return (hits / total) * 100 if total else None


def calc_clean_card_percent(rounds, courses) -> float | None:
    eligible = [r for r in rounds if r.get("holes") and courses.get(r.get("course", ""))
                and r.get("holes_selection", "all") == "all"]
    if not eligible:
        return None
    clean = 0
    for r in eligible:
        holes = courses[r["course"]].get("holes", {})
        if not any(
            int(h.get("gross", 0)) - int(holes.get(str(n), {}).get("par", 0)) >= 2
            for n, h in r["holes"].items()
            if holes.get(str(n), {}).get("par")
        ):
            clean += 1
    return (clean / len(eligible)) * 100


def calc_scoring_consistency(rounds, courses) -> float | None:
    diffs = []
    for r in rounds:
        if not r.get("total_gross") or r["total_gross"] == "0":
            continue
        if r.get("holes_selection", "all") != "all":
            continue
        course_par = courses.get(r.get("course", ""), {}).get("par")
        if not course_par:
            continue
        diffs.append(int(r["total_gross"]) - int(course_par))
    if len(diffs) < 2:
        return None
    mean = sum(diffs) / len(diffs)
    return (sum((d - mean) ** 2 for d in diffs) / len(diffs)) ** 0.5


def calc_score_components(rounds, courses) -> dict:
    approach = []
    scramble = []
    all_putts = []
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course", "")
        holes = courses.get(course_name, {}).get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par or not h.get("gross") or not h.get("putts"):
                continue
            gross = int(h["gross"])
            putts = int(h["putts"])
            all_putts.append(putts)
            if par == 3:
                continue
            ball_striking = (gross - putts) - (par - 2)
            fw = h.get("fairway", "")
            if fw == "H":
                approach.append(ball_striking)
            elif fw:
                scramble.append(ball_striking)
    return {
        "approach": sum(approach) / len(approach) if approach else None,
        "scramble": sum(scramble) / len(scramble) if scramble else None,
        "putting": sum(all_putts) / len(all_putts) if all_putts else None,
    }


def calc_penalty_stats(rounds, courses) -> dict:
    round_totals = []
    penalty_vs_par = []
    clean_vs_par = []
    hole_counts: dict = {}
    hole_penalties: dict = {}
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course", "")
        holes = courses.get(course_name, {}).get("holes", {})
        round_pen = 0
        for hole_num, h in r["holes"].items():
            if not h.get("gross"):
                continue
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            gross = int(h["gross"])
            pen = int(h.get("penalties", 0))
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


def calc_momentum_recovery(rounds, courses) -> dict:
    after_bogey = []
    after_double = []
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course", "")
        holes = courses.get(course_name, {}).get("holes", {})
        hole_nums = sorted(r["holes"].keys(), key=lambda x: int(x))
        for i, hole_num in enumerate(hole_nums[:-1]):
            h = r["holes"][hole_num]
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par or not h.get("gross"):
                continue
            vs_par = int(h["gross"]) - par
            next_num = hole_nums[i + 1]
            next_h = r["holes"][next_num]
            next_par = int(holes.get(str(next_num), {}).get("par", 0))
            if not next_par or not next_h.get("gross"):
                continue
            next_vs_par = int(next_h["gross"]) - next_par
            if vs_par >= 1:
                after_bogey.append(next_vs_par)
            if vs_par >= 2:
                after_double.append(next_vs_par <= 0)
    return {
        "after_bogey_avg": sum(after_bogey) / len(after_bogey) if after_bogey else None,
        "recovery_rate": sum(after_double) / len(after_double) * 100 if after_double else None,
    }


def calc_personal_bests(rounds, courses) -> dict:
    best_gross = best_diff = most_fir = most_gir = fewest_putts = None
    best_gross_date = best_diff_date = most_fir_date = most_gir_date = fewest_putts_date = None
    for r in [r for r in rounds if r.get("holes_selection", "all") == "all"]:
        date = r.get("date", "")
        if r.get("total_gross") and r["total_gross"] != "0":
            g = int(r["total_gross"])
            if best_gross is None or g < best_gross:
                best_gross = g
                best_gross_date = date
        if r.get("differential") and r["differential"] != "0":
            d = float(r["differential"])
            if best_diff is None or d < best_diff:
                best_diff = d
                best_diff_date = date
        if not r.get("holes"):
            continue
        fir = sum(1 for h in r["holes"].values() if h.get("fairway") == "H")
        if most_fir is None or fir > most_fir:
            most_fir = fir
            most_fir_date = date
        gir = sum(1 for h in r["holes"].values() if h.get("gir") == "H")
        if most_gir is None or gir > most_gir:
            most_gir = gir
            most_gir_date = date
        putts = sum(int(h["putts"]) for h in r["holes"].values() if h.get("putts"))
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


def calc_nemesis_best_holes(rounds, courses) -> tuple:
    hole_data: dict = {}
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course", "")
        course = courses.get(course_name, {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par or not h.get("gross"):
                continue
            key = (course_name, hole_num)
            hole_data.setdefault(key, []).append(int(h["gross"]) - par)
    averages = [
        (course, hole, sum(diffs) / len(diffs))
        for (course, hole), diffs in hole_data.items()
        if len(diffs) >= 2
    ]
    averages.sort(key=lambda x: x[2])
    return list(reversed(averages[-5:])), averages[:5]


def calc_pob_trend(all_rounds, courses) -> list:
    return calc_trend(all_rounds, calc_par_or_better_percent, courses)


def calc_clean_card_trend(all_rounds, courses) -> list:
    return calc_trend(all_rounds, calc_clean_card_percent, courses)


def calc_big_number_trend(all_rounds, courses) -> list:
    return calc_trend(all_rounds, calc_big_number_rate, courses)


STAT_CATALOG: list = [
    {
        "key": "handicap",
        "label": "Handicap",
        "suffix": "",
        "higher_better": False,
        "color": (64, 196, 255),
        "fn_primary":   lambda l20, b8, c, i9: calc_handicap_index(l20, i9),
        "fn_secondary": lambda l20, b8, c, i9: calc_handicap_index(l20[1:], i9),
        "trend_fn":     lambda all_r, c, i9: calc_handicap_trend(all_r, i9),
        "blank_text": "Play 3+ rounds to see handicap",
    },
    {
        "key": "score",
        "label": "Avg Score",
        "suffix": "",
        "higher_better": False,
        "color": (64, 255, 128),
        "fn_primary":   lambda l20, b8, c, i9: calc_scoring_average(b8),
        "fn_secondary": lambda l20, b8, c, i9: calc_scoring_average(l20),
        "trend_fn":     lambda all_r, c, i9: calc_scoring_trend(all_r),
        "blank_text": "Play a round to see scoring avg",
    },
    {
        "key": "fir",
        "label": "FIR",
        "suffix": "%",
        "higher_better": True,
        "color": (255, 220, 64),
        "fn_primary":   lambda l20, b8, c, i9: calc_fir_percent(b8, c),
        "fn_secondary": lambda l20, b8, c, i9: calc_fir_percent(l20, c),
        "trend_fn":     lambda all_r, c, i9: calc_fir_trend(all_r, c),
        "blank_text": "Play a round to see FIR %",
    },
    {
        "key": "gir",
        "label": "GIR",
        "suffix": "%",
        "higher_better": True,
        "color": (255, 128, 64),
        "fn_primary":   lambda l20, b8, c, i9: calc_gir_percent(b8),
        "fn_secondary": lambda l20, b8, c, i9: calc_gir_percent(l20),
        "trend_fn":     lambda all_r, c, i9: calc_gir_trend(all_r),
        "blank_text": "Play a round to see GIR %",
    },
    {
        "key": "putts",
        "label": "Putts / Rnd",
        "suffix": "",
        "higher_better": False,
        "color": (160, 128, 255),
        "fn_primary":   lambda l20, b8, c, i9: calc_putts_per_round(b8),
        "fn_secondary": lambda l20, b8, c, i9: calc_putts_per_round(l20),
        "trend_fn":     lambda all_r, c, i9: calc_putts_trend(all_r),
        "blank_text": "Play a round to see putts",
    },
    {
        "key": "scramble",
        "label": "Scramble",
        "suffix": "%",
        "higher_better": True,
        "color": (255, 64, 128),
        "fn_primary":   lambda l20, b8, c, i9: calc_scramble_percent(b8, c),
        "fn_secondary": lambda l20, b8, c, i9: calc_scramble_percent(l20, c),
        "trend_fn":     lambda all_r, c, i9: calc_scramble_trend(all_r, c),
        "blank_text": "Play a round to see scramble %",
    },
    {
        "key": "one_putt",
        "label": "1-Putt %",
        "suffix": "%",
        "higher_better": True,
        "color": (128, 200, 255),
        "fn_primary":   lambda l20, b8, c, i9: calc_one_putt_percent(b8),
        "fn_secondary": lambda l20, b8, c, i9: calc_one_putt_percent(l20),
        "trend_fn":     lambda all_r, c, i9: calc_one_putt_trend(all_r),
        "blank_text": "Play a round to see stats",
    },
    {
        "key": "three_putt",
        "label": "3-Putt %",
        "suffix": "%",
        "higher_better": False,
        "color": (255, 100, 100),
        "fn_primary":   lambda l20, b8, c, i9: calc_three_putt_percent(b8),
        "fn_secondary": lambda l20, b8, c, i9: calc_three_putt_percent(l20),
        "trend_fn":     lambda all_r, c, i9: calc_three_putt_trend(all_r),
        "blank_text": "Play a round to see stats",
    },
    {
        "key": "putts_gir",
        "label": "Putts/GIR",
        "suffix": "",
        "higher_better": False,
        "color": (200, 160, 255),
        "fn_primary":   lambda l20, b8, c, i9: calc_putts_per_gir(b8),
        "fn_secondary": lambda l20, b8, c, i9: calc_putts_per_gir(l20),
        "trend_fn":     lambda all_r, c, i9: calc_putts_gir_trend(all_r),
        "blank_text": "Play a round to see stats",
    },
    {
        "key": "pob",
        "label": "Par/Better %",
        "suffix": "%",
        "higher_better": True,
        "color": (100, 255, 180),
        "fn_primary":   lambda l20, b8, c, i9: calc_par_or_better_percent(b8, c),
        "fn_secondary": lambda l20, b8, c, i9: calc_par_or_better_percent(l20, c),
        "trend_fn":     lambda all_r, c, i9: calc_pob_trend(all_r, c),
        "blank_text": "Play a round to see stats",
    },
    {
        "key": "clean_card",
        "label": "Clean Card %",
        "suffix": "%",
        "higher_better": True,
        "color": (255, 220, 120),
        "fn_primary":   lambda l20, b8, c, i9: calc_clean_card_percent(b8, c),
        "fn_secondary": lambda l20, b8, c, i9: calc_clean_card_percent(l20, c),
        "trend_fn":     lambda all_r, c, i9: calc_clean_card_trend(all_r, c),
        "blank_text": "Play a round to see stats",
    },
    {
        "key": "big_number",
        "label": "Blow-up %",
        "suffix": "%",
        "higher_better": False,
        "color": (255, 80, 80),
        "fn_primary":   lambda l20, b8, c, i9: calc_big_number_rate(b8, c),
        "fn_secondary": lambda l20, b8, c, i9: calc_big_number_rate(l20, c),
        "trend_fn":     lambda all_r, c, i9: calc_big_number_trend(all_r, c),
        "blank_text": "Play a round to see stats",
    },
]

DEFAULT_DASHBOARD_STATS: list = ["handicap", "score", "fir", "gir", "putts", "scramble"]


def calc_rounds_this_year(all_rounds) -> int:
    current_year = str(date.today().year)
    return sum(1 for r in all_rounds if r.get("date", "").startswith(current_year))


def calc_rounds_total(all_rounds) -> int:
    return len(all_rounds)


def calc_golfiest_month(season_rounds: list) -> tuple[str, int]:
    if not season_rounds:
        return ("—", 0)
    counts = Counter()
    for r in season_rounds:
        d = r.get("date", "")
        try:
            month = int(d[5:7])
        except (ValueError, IndexError):
            continue
        counts[month] += 1
    if not counts:
        return ("—", 0)
    best_month, best_count = counts.most_common(1)[0]
    return (calendar.month_name[best_month], best_count)


def calc_most_common_day(season_rounds: list) -> tuple[str, int]:
    if not season_rounds:
        return ("—", 0)
    counts = Counter()
    for r in season_rounds:
        d = r.get("date", "")
        try:
            day_name = date.fromisoformat(d).strftime("%A")
        except ValueError:
            continue
        counts[day_name] += 1
    if not counts:
        return ("—", 0)
    best_day, best_count = counts.most_common(1)[0]
    return (best_day, best_count)


def calc_weekly_streak(season_rounds: list) -> int:
    if not season_rounds:
        return 0
    weeks = set()
    for r in season_rounds:
        d = r.get("date", "")
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


def calc_best_single_round(season_rounds: list) -> dict | None:
    best = None
    best_diff = None
    for r in season_rounds:
        raw = r.get("differential")
        if raw is None:
            continue
        try:
            diff = float(raw)
        except (ValueError, TypeError):
            continue
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = r
    return best


def calc_best_3round_stretch(season_rounds: list) -> tuple[float, str, str] | None:
    eligible = [r for r in sorted(season_rounds, key=lambda r: r.get("date", "")) if r.get("differential") not in (None, "")]
    if len(eligible) < 3:
        return None
    best_avg = None
    best_start = None
    best_end = None
    for i in range(len(eligible) - 2):
        window = eligible[i:i + 3]
        try:
            avg = sum(float(r["differential"]) for r in window) / 3
        except (ValueError, TypeError):
            continue
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_start = window[0]["date"]
            best_end = window[2]["date"]
    if best_avg is None:
        return None
    return (best_avg, best_start, best_end)


def calc_biggest_improvement(season_rounds: list) -> tuple[float, dict] | None:
    best_gap = None
    best_round = None
    for r in season_rounds:
        raw_diff = r.get("differential")
        raw_hi = r.get("computed_handicap")
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


def calc_first_score_milestone(season_rounds: list, all_rounds: list) -> tuple[int, dict] | None:
    milestones = [100, 95, 90, 85, 80, 75, 70]
    season_ids = {id(r) for r in season_rounds}
    pre_season = [r for r in all_rounds if id(r) not in season_ids]
    already_broken = set()
    for r in pre_season:
        if r.get("holes_selection", "all") != "all":
            continue
        raw = r.get("total_gross")
        if raw is None:
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
    sorted_rounds = sorted(season_rounds, key=lambda r: r.get("date", ""))
    best_threshold = None
    best_round = None
    for r in sorted_rounds:
        if r.get("holes_selection", "all") != "all":
            continue
        raw = r.get("total_gross")
        if raw is None:
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


def calc_first_hi_milestone(season_rounds: list, all_rounds: list) -> tuple[int, dict] | None:
    milestones = list(range(36, 0, -1))
    season_ids = {id(r) for r in season_rounds}
    pre_season = [r for r in all_rounds if id(r) not in season_ids]
    already_broken = set()
    for r in pre_season:
        raw = r.get("computed_handicap")
        if raw is None or raw == "":
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
    sorted_rounds = sorted(season_rounds, key=lambda r: r.get("date", ""))
    best_threshold = None
    best_round = None
    for r in sorted_rounds:
        raw = r.get("computed_handicap")
        if raw is None or raw == "":
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


def calc_score_breakdown(season_rounds: list, courses: dict) -> dict:
    counts = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "triple_plus": 0}
    for r in season_rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par or not h.get("gross"):
                continue
            diff = int(h["gross"]) - par
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


def calc_hole_in_ones(season_rounds: list, courses: dict) -> int:
    count = 0
    for r in season_rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            if h.get("gross") == "1":
                count += 1
    return count


def calc_best_gir_round(season_rounds: list) -> tuple[dict, int] | None:
    best = None
    best_count = -1
    for r in season_rounds:
        if not r.get("holes"):
            continue
        count = sum(1 for h in r["holes"].values() if h.get("gir") == "H")
        if count > best_count:
            best_count = count
            best = r
    if best is None or best_count == 0:
        return None
    return best, best_count


def calc_best_fir_round(season_rounds: list, courses: dict) -> tuple[dict, int] | None:
    best = None
    best_count = -1
    for r in season_rounds:
        if not r.get("holes"):
            continue
        course_holes = courses.get(r.get("course", ""), {}).get("holes", {})
        count = sum(
            1 for h_num, h in r["holes"].items()
            if h.get("fairway") == "H"
            and int(course_holes.get(str(h_num), {}).get("par", 0)) != 3
        )
        if count > best_count:
            best_count = count
            best = r
    if best is None or best_count == 0:
        return None
    return best, best_count


def calc_most_played_course(season_rounds: list) -> tuple[str, int, float] | None:
    if not season_rounds:
        return None
    counts: Counter = Counter()
    for r in season_rounds:
        course = r.get("course", "")
        if course:
            counts[course] += 1
    if not counts:
        return None
    best_count = counts.most_common(1)[0][1]
    candidates = [c for c, n in counts.items() if n == best_count]
    best_course = None
    best_avg = None
    for course in candidates:
        diffs = [float(r["differential"]) for r in season_rounds if r.get("course") == course and r.get("differential") not in (None, "")]
        avg = sum(diffs) / len(diffs) if diffs else float("inf")
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_course = course
    return (best_course, best_count, best_avg if best_avg != float("inf") else 0.0)


def calc_season_yardage(season_rounds: list, courses: dict, mode: str) -> float | None:
    total_yards = 0.0
    for r in season_rounds:
        transport = r.get("transport", "")
        if mode == "walking" and transport not in ("", "walking"):
            continue
        if mode == "riding" and transport != "riding":
            continue
        course_data = courses.get(r.get("course", ""), {})
        tee_name = r.get("tees", "")
        tees = course_data.get("tees", {})
        tee_data = tees.get(tee_name, {})
        yardage = tee_data.get("yardage")
        if yardage is None:
            continue
        yardage = int(yardage)
        holes = r.get("holes", {})
        if holes:
            yardage = yardage * len(holes) // 18
        total_yards += yardage
    if total_yards == 0:
        return None
    return total_yards / 1760


def calc_penalty_free_rounds(season_rounds: list) -> int:
    count = 0
    for r in season_rounds:
        if not r.get("holes"):
            continue
        total = sum(int(h.get("penalties", "0")) for h in r["holes"].values())
        if total == 0:
            count += 1
    return count


def calc_hi_journey(all_rounds: list, season_rounds: list, live_hi: float | None = None) -> tuple[float, float, float] | None:
    if live_hi is not None:
        end_hi = live_hi
    else:
        end_hi = None
        for r in season_rounds:
            ch = r.get("computed_handicap", "")
            if ch and ch != "0":
                end_hi = float(ch)
                break
    if end_hi is None:
        return None

    season_dates = [r.get("date", "") for r in season_rounds if r.get("date")]
    if not season_dates:
        return None
    earliest = min(season_dates)

    start_hi = None
    for r in all_rounds:
        if r.get("date", "") <= earliest:
            ch = r.get("computed_handicap", "")
            if ch and ch != "0":
                start_hi = float(ch)
                break
    if start_hi is None:
        for r in season_rounds:
            ch = r.get("computed_handicap", "")
            if ch and ch != "0":
                start_hi = float(ch)
                break
    if start_hi is None:
        return None

    delta = start_hi - end_hi
    return (start_hi, end_hi, delta)


def calc_season_rounds(rounds: list, settings: dict) -> list:
    current_year = str(date.today().year)
    start_month = settings.get("season_start_month", 1)
    end_month = settings.get("season_end_month", 12)
    start_day = settings.get("season_start_day", 1)
    end_day = settings.get("season_end_day", 28)
    result = []
    for r in rounds:
        d = r.get("date", "")
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
