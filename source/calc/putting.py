def calc_putts_per_round(rounds) -> float | None:
    totals = []
    for r in rounds:
        if not r.get("holes") or r.get("holes_selection", "all") != "all":
            continue
        totals.append(sum(int(h["putts"]) for h in r["holes"].values() if "putts" in h))
    return sum(totals) / len(totals) if totals else None


def calc_putts_per_gir(rounds) -> float | None:
    putts = []
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            if h.get("gir") == "H" and h.get("putts"):
                putts.append(int(h["putts"]))
    return sum(putts) / len(putts) if putts else None


def calc_three_putt_percent(rounds) -> float | None:
    three_putts = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            if h.get("putts"):
                total += 1
                if int(h["putts"]) >= 3:
                    three_putts += 1
    return (three_putts / total) * 100 if total else None


def calc_four_plus_putt_percent(rounds) -> float | None:
    four_plus = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            if h.get("putts"):
                total += 1
                if int(h["putts"]) >= 4:
                    four_plus += 1
    return (four_plus / total) * 100 if total else None


def calc_two_putt_percent(rounds) -> float | None:
    two_putts = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            if h.get("putts"):
                total += 1
                if int(h["putts"]) == 2:
                    two_putts += 1
    return (two_putts / total) * 100 if total else None


def calc_one_putt_percent(rounds) -> float | None:
    one_putts = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            if h.get("putts"):
                total += 1
                if int(h["putts"]) == 1:
                    one_putts += 1
    return (one_putts / total) * 100 if total else None


def calc_putts_by_par_type(rounds, courses) -> dict:
    totals = {3: [], 4: [], 5: []}
    for r in rounds:
        if not r.get("holes"):
            continue
        course = courses.get(r.get("course", ""), {})
        holes = course.get("holes", {})
        for hole_num, h in r["holes"].items():
            par = int(holes.get(str(hole_num), {}).get("par", 0))
            if par in totals and h.get("putts"):
                totals[par].append(int(h["putts"]))
    return {p: sum(v) / len(v) if v else None for p, v in totals.items()}


def calc_putts_trend(all_rounds) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for r in chronological:
        if r.get("holes_selection", "all") != "all":
            continue
        val = calc_putts_per_round([r])
        if val is not None:
            result.append((r.get("date", ""), val))
    return result


def calc_one_putt_trend(all_rounds) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for r in chronological:
        val = calc_one_putt_percent([r])
        if val is not None:
            result.append((r.get("date", ""), val))
    return result


def calc_three_putt_trend(all_rounds) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for r in chronological:
        val = calc_three_putt_percent([r])
        if val is not None:
            result.append((r.get("date", ""), val))
    return result


def calc_putts_gir_trend(all_rounds) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for r in chronological:
        val = calc_putts_per_gir([r])
        if val is not None:
            result.append((r.get("date", ""), val))
    return result
