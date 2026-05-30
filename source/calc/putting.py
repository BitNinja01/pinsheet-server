from source.models import RoundData, CourseData, HoleDef
from calc.scoring import calc_trend


def calc_putts_per_round(rounds: list[RoundData]) -> float | None:
    totals = []
    for r in rounds:
        if not r.holes or r.holes_selection != "all":
            continue
        totals.append(sum(h.putts for h in r.holes.values()))
    return sum(totals) / len(totals) if totals else None


def calc_putts_per_gir(rounds: list[RoundData]) -> float | None:
    putts = []
    for r in rounds:
        if not r.holes:
            continue
        for h in r.holes.values():
            if h.gir == "H" and h.putts:
                putts.append(h.putts)
    return sum(putts) / len(putts) if putts else None


def _putt_threshold_percent(rounds: list[RoundData], predicate) -> float | None:
    hits = 0
    total = 0
    for r in rounds:
        if not r.holes:
            continue
        for h in r.holes.values():
            if h.putts:
                total += 1
                if predicate(h.putts):
                    hits += 1
    return (hits / total) * 100 if total else None


def calc_one_putt_percent(rounds: list[RoundData]) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p == 1)


def calc_two_putt_percent(rounds: list[RoundData]) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p == 2)


def calc_three_putt_percent(rounds: list[RoundData]) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p >= 3)


def calc_four_plus_putt_percent(rounds: list[RoundData]) -> float | None:
    return _putt_threshold_percent(rounds, lambda p: p >= 4)


def calc_putts_by_par_type(rounds: list[RoundData], courses: dict[str, CourseData]) -> dict:
    totals = {3: [], 4: [], 5: []}
    for r in rounds:
        if not r.holes:
            continue
        course = courses.get(r.course)
        holes = course.holes if course else {}
        for hole_num, h in r.holes.items():
            par = holes.get(str(hole_num), HoleDef()).par
            if par in totals and h.putts:
                totals[par].append(h.putts)
    return {p: sum(v) / len(v) if v else None for p, v in totals.items()}


def calc_putts_trend(all_rounds: list[RoundData]) -> list:
    return calc_trend(all_rounds, calc_putts_per_round, filter_fn=lambda r: r.holes_selection == "all")


def calc_one_putt_trend(all_rounds: list[RoundData]) -> list:
    return calc_trend(all_rounds, calc_one_putt_percent)


def calc_three_putt_trend(all_rounds: list[RoundData]) -> list:
    return calc_trend(all_rounds, calc_three_putt_percent)


def calc_putts_gir_trend(all_rounds: list[RoundData]) -> list:
    return calc_trend(all_rounds, calc_putts_per_gir)
