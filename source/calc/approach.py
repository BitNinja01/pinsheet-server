from calc.scoring import calc_trend


def calc_fir_percent(rounds, courses) -> float | None:
    hits = 0
    eligible = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course")
        if not course_name or course_name not in courses:
            continue
        for hole_num, hole_data in r["holes"].items():
            par = int(courses[course_name]["holes"][str(hole_num)]["par"])
            if par == 3:
                continue
            eligible += 1
            if hole_data.get("fairway") == "H":
                hits += 1
    return (hits / eligible) * 100 if eligible else None


def calc_gir_percent(rounds) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        for hole_data in r["holes"].values():
            total += 1
            if hole_data.get("gir") == "H":
                hits += 1
    return (hits / total) * 100 if total else None


def calc_scramble_percent(rounds, courses) -> float | None:
    saved = 0
    missed_gir = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course")
        if not course_name or course_name not in courses:
            continue
        for hole_num, hole_data in r["holes"].items():
            if hole_data.get("gir") == "H":
                continue
            missed_gir += 1
            par = int(courses[course_name]["holes"][str(hole_num)]["par"])
            if int(hole_data.get("gross", "999")) <= par:
                saved += 1
    return (saved / missed_gir) * 100 if missed_gir else None


def calc_fir_trend(all_rounds, courses) -> list:
    return calc_trend(all_rounds, calc_fir_percent, courses)


def calc_gir_trend(all_rounds) -> list:
    return calc_trend(all_rounds, calc_gir_percent)


def calc_scramble_trend(all_rounds, courses) -> list:
    return calc_trend(all_rounds, calc_scramble_percent, courses)


def calc_fir_miss_tendency(rounds, courses) -> dict:
    left = 0
    right = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par == 3:
                continue
            fw = h.get("fairway", "")
            if fw in {"L", "OBL"}:
                left += 1
            elif fw in {"R", "OBR"}:
                right += 1
    total = left + right
    if not total:
        return {"left": None, "right": None}
    return {"left": (left / total) * 100, "right": (right / total) * 100}


def calc_scoring_by_fairway(rounds, courses) -> dict:
    hit_diffs = []
    missed_diffs = []
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par == 3 or not h.get("gross"):
                continue
            diff = int(h["gross"]) - par
            fw = h.get("fairway", "")
            if fw == "H":
                hit_diffs.append(diff)
            elif fw in {"L", "OBL", "R", "OBR"}:
                missed_diffs.append(diff)
    return {
        "hit": sum(hit_diffs) / len(hit_diffs) if hit_diffs else None,
        "missed": sum(missed_diffs) / len(missed_diffs) if missed_diffs else None,
    }


def calc_scoring_by_miss_side(rounds, courses) -> dict:
    left_diffs = []
    right_diffs = []
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par == 3 or not h.get("gross"):
                continue
            diff = int(h["gross"]) - par
            fw = h.get("fairway", "")
            if fw in {"L", "OBL"}:
                left_diffs.append(diff)
            elif fw in {"R", "OBR"}:
                right_diffs.append(diff)
    return {
        "left": sum(left_diffs) / len(left_diffs) if left_diffs else None,
        "right": sum(right_diffs) / len(right_diffs) if right_diffs else None,
    }


def calc_gir_by_par_type(rounds, courses) -> dict:
    hits = {3: 0, 4: 0, 5: 0}
    totals = {3: 0, 4: 0, 5: 0}
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par not in totals:
                continue
            totals[par] += 1
            if h.get("gir") == "H":
                hits[par] += 1
    return {p: (hits[p] / totals[p]) * 100 if totals[p] else None for p in [3, 4, 5]}


def calc_gir_miss_direction(rounds) -> dict:
    counts = {"L": 0, "R": 0, "S": 0, "LO": 0}
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            gir = h.get("gir", "")
            if gir in {"L", "OBL"}:
                counts["L"] += 1
            elif gir in {"R", "OBR"}:
                counts["R"] += 1
            elif gir in {"S", "OBS"}:
                counts["S"] += 1
            elif gir in {"LO", "OBLO"}:
                counts["LO"] += 1
    total = sum(counts.values())
    if not total:
        return {k: None for k in counts}
    return {k: (v / total) * 100 for k, v in counts.items()}


def calc_gir_from_fairway_vs_rough(rounds, courses) -> dict:
    fw_hits = fw_total = rough_hits = rough_total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par == 3:
                continue
            fw = h.get("fairway", "")
            gir_hit = h.get("gir") == "H"
            if fw == "H":
                fw_total += 1
                if gir_hit:
                    fw_hits += 1
            elif fw in {"L", "OBL", "R", "OBR"}:
                rough_total += 1
                if gir_hit:
                    rough_hits += 1
    return {
        "fairway": (fw_hits / fw_total) * 100 if fw_total else None,
        "rough": (rough_hits / rough_total) * 100 if rough_total else None,
    }


def calc_scoring_by_gir(rounds, courses) -> dict:
    hit_diffs = []
    missed_diffs = []
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
            if h.get("gir") == "H":
                hit_diffs.append(diff)
            else:
                missed_diffs.append(diff)
    return {
        "hit": sum(hit_diffs) / len(hit_diffs) if hit_diffs else None,
        "missed": sum(missed_diffs) / len(missed_diffs) if missed_diffs else None,
    }


def calc_scramble_by_miss_direction(rounds, courses) -> dict:
    saved = {"L": 0, "R": 0, "S": 0, "LO": 0}
    missed = {"L": 0, "R": 0, "S": 0, "LO": 0}
    _map = {"L": "L", "OBL": "L", "R": "R", "OBR": "R",
            "S": "S", "OBS": "S", "LO": "LO", "OBLO": "LO"}
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            gir = h.get("gir", "")
            if gir == "H" or gir not in _map or not h.get("gross"):
                continue
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if not par:
                continue
            direction = _map[gir]
            missed[direction] += 1
            if int(h["gross"]) <= par:
                saved[direction] += 1
    return {d: (saved[d] / missed[d]) * 100 if missed[d] else None for d in saved}


def calc_scramble_by_par_type(rounds, courses) -> dict:
    saved = {3: 0, 4: 0, 5: 0}
    missed = {3: 0, 4: 0, 5: 0}
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            if h.get("gir") == "H" or not h.get("gross"):
                continue
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par not in missed:
                continue
            missed[par] += 1
            if int(h["gross"]) <= par:
                saved[par] += 1
    return {p: (saved[p] / missed[p]) * 100 if missed[p] else None for p in [3, 4, 5]}


def calc_ob_stats(rounds, courses) -> dict:
    _FIR_OB = {"OBL", "OBR"}
    _GIR_OB = {"OBL", "OBR", "OBS", "OBLO"}
    fir_ob_round_totals = []
    gir_ob_round_totals = []
    fir_ob_vs_par = []
    fir_clean_vs_par = []
    gir_ob_vs_par = []
    gir_clean_vs_par = []
    hole_fir_counts: dict = {}
    hole_fir_ob: dict = {}
    hole_gir_counts: dict = {}
    hole_gir_ob: dict = {}
    for r in rounds:
        if not r.get("holes"):
            continue
        course_name = r.get("course", "")
        holes = courses.get(course_name, {}).get("holes", {})
        fir_ob_count = 0
        gir_ob_count = 0
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            gross = int(h["gross"]) if h.get("gross") else None
            fw = h.get("fairway", "")
            gir = h.get("gir", "")
            key_fir = (course_name, hole_num)
            key_gir = (course_name, hole_num)
            if par != 3:
                hole_fir_counts[key_fir] = hole_fir_counts.get(key_fir, 0) + 1
                if fw in _FIR_OB:
                    fir_ob_count += 1
                    hole_fir_ob[key_fir] = hole_fir_ob.get(key_fir, 0) + 1
                    if par and gross is not None:
                        fir_ob_vs_par.append(gross - par)
                elif par and gross is not None:
                    fir_clean_vs_par.append(gross - par)
            hole_gir_counts[key_gir] = hole_gir_counts.get(key_gir, 0) + 1
            if gir in _GIR_OB:
                gir_ob_count += 1
                hole_gir_ob[key_gir] = hole_gir_ob.get(key_gir, 0) + 1
                if par and gross is not None:
                    gir_ob_vs_par.append(gross - par)
            elif par and gross is not None:
                gir_clean_vs_par.append(gross - par)
        fir_ob_round_totals.append(fir_ob_count)
        gir_ob_round_totals.append(gir_ob_count)
    fir_worst = sorted(
        [
            (course, hole, hole_fir_ob.get((course, hole), 0) / hole_fir_counts[(course, hole)])
            for (course, hole) in hole_fir_counts
            if hole_fir_counts[(course, hole)] >= 2 and (course, hole) in hole_fir_ob
        ],
        key=lambda x: x[2],
        reverse=True,
    )[:5]
    gir_worst = sorted(
        [
            (course, hole, hole_gir_ob.get((course, hole), 0) / hole_gir_counts[(course, hole)])
            for (course, hole) in hole_gir_counts
            if hole_gir_counts[(course, hole)] >= 2 and (course, hole) in hole_gir_ob
        ],
        key=lambda x: x[2],
        reverse=True,
    )[:5]
    n = len(fir_ob_round_totals)
    return {
        "fir_ob_per_round":    sum(fir_ob_round_totals) / n if n else None,
        "gir_ob_per_round":    sum(gir_ob_round_totals) / n if n else None,
        "total_ob_per_round":  (sum(fir_ob_round_totals) + sum(gir_ob_round_totals)) / n if n else None,
        "fir_ob_avg_vs_par":   sum(fir_ob_vs_par) / len(fir_ob_vs_par) if fir_ob_vs_par else None,
        "fir_clean_avg_vs_par": sum(fir_clean_vs_par) / len(fir_clean_vs_par) if fir_clean_vs_par else None,
        "gir_ob_avg_vs_par":   sum(gir_ob_vs_par) / len(gir_ob_vs_par) if gir_ob_vs_par else None,
        "gir_clean_avg_vs_par": sum(gir_clean_vs_par) / len(gir_clean_vs_par) if gir_clean_vs_par else None,
        "fir_worst_holes":     fir_worst,
        "gir_worst_holes":     gir_worst,
    }
