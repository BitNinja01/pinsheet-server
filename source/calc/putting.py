from calc.scoring import calc_trend


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


def _putt_threshold_percent(rounds, predicate) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.get("holes"):
            continue
        for h in r["holes"].values():
            if h.get("putts"):
                total += 1
                if predicate(int(h["putts"])):
                    hits += 1
    return (hits / total) * 100 if total else None


def calc_one_putt_percent(rounds) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p == 1)


def calc_two_putt_percent(rounds) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p == 2)


def calc_three_putt_percent(rounds) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p >= 3)


def calc_four_plus_putt_percent(rounds) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p >= 4)


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
    return calc_trend(all_rounds, calc_putts_per_round, filter_fn=lambda r: r.get("holes_selection", "all") == "all")


def calc_one_putt_trend(all_rounds) -> list:
    return calc_trend(all_rounds, calc_one_putt_percent)


def calc_three_putt_trend(all_rounds) -> list:
    return calc_trend(all_rounds, calc_three_putt_percent)


def calc_putts_gir_trend(all_rounds) -> list:
    return calc_trend(all_rounds, calc_putts_per_gir)
