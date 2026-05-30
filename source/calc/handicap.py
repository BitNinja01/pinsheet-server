import math

from calc.models import RoundData


def calc_hole_scores(hole_stroke_index, course_handicap, hole_par, hole_gross) -> tuple:
    strokes_given = 0
    if course_handicap >= hole_stroke_index:
        strokes_given = 1
    if course_handicap >= (hole_stroke_index + 18):
        strokes_given = 2

    hole_net = hole_gross - strokes_given
    esc_gross = min(hole_gross, int(hole_par) + 2 + strokes_given)
    return hole_gross, hole_net, esc_gross


def calc_course_handicap(handicap, course_par, course_slope, course_rating) -> int:
    return round(handicap * (course_slope / 113) + (course_rating - course_par))


def calc_round_dif(tee_slope, adjusted_gross_score, tee_rating) -> float:
    return round((113 / tee_slope) * (adjusted_gross_score - tee_rating), 1)


def calc_expected_9hole_dif(handicap_index: float) -> float:
    return handicap_index * 0.52 + 1.197


def count_table_n(n: int) -> int:
    if n < 3:  return 0
    if n < 6:  return 1
    if n < 9:  return 2
    if n < 12: return 3
    if n < 15: return 4
    if n < 17: return 5
    if n < 19: return 6
    if n < 20: return 7
    return 8


def calc_effective_diffs(rounds: list[RoundData], include_9hole: bool = False) -> list:
    diffs = []
    for r in rounds:
        if r.excluded:
            continue
        if not r.differential or r.differential == "0":
            continue
        if r.holes_selection != "all":
            if not include_9hole or not r.computed_handicap or float(r.computed_handicap) == 0:
                continue
            diffs.append(math.floor(float(r.differential) * 10) / 10)
        else:
            diffs.append(math.floor(float(r.differential) * 10) / 10)
    return sorted(diffs)


def get_best_n_rounds(rounds: list[RoundData], include_9hole: bool = False, n: int | None = None) -> list[RoundData]:
    eligible = []
    for r in rounds:
        if r.excluded:
            continue
        if not r.differential or r.differential == "0":
            continue
        if r.holes_selection != "all":
            if not include_9hole or not r.computed_handicap or float(r.computed_handicap) == 0:
                continue
        eligible.append(r)
    eligible.sort(key=lambda r: math.floor(float(r.differential) * 10) / 10)
    if n is None:
        n = count_table_n(len(eligible))
    return eligible[:n]


def calc_handicap_index(rounds: list[RoundData], include_9hole: bool = False) -> float | None:
    diffs = calc_effective_diffs(rounds, include_9hole)
    n = count_table_n(len(diffs))
    if n == 0 or not diffs:
        return None
    best_n = diffs[:n]
    return round(sum(best_n) / len(best_n), 1)


def calc_handicap_trend(all_rounds: list[RoundData], include_9hole: bool = False) -> list:
    chronological = list(reversed(all_rounds))
    result = []
    for i, r in enumerate(chronological):
        window = chronological[max(0, i - 19):i + 1]
        val = calc_handicap_index(window, include_9hole)
        if val is not None:
            result.append((r.date, val))
    return result


def calc_playing_to_handicap_rate(rounds: list[RoundData]) -> float | None:
    valid = [
        (float(r.differential), float(r.computed_handicap))
        for r in rounds
        if not r.excluded
        and r.differential and r.computed_handicap
        and r.differential not in ("0", "") and r.computed_handicap not in ("0", "")
    ]
    if not valid:
        return None
    return sum(1 for diff, hc in valid if diff <= hc) / len(valid) * 100


def calc_raw_hi(rounds: list[RoundData], include_9hole: bool = False) -> float | None:
    diffs = calc_effective_diffs(rounds, include_9hole)
    if not diffs:
        return None
    return (sum(diffs) / len(diffs)) * 0.96


def calc_handicap_values_in_range(all_rounds: list[RoundData], cutoff: str) -> list[float]:
    vals = []
    for r in all_rounds:
        if r.date < cutoff:
            continue
        ch = r.computed_handicap
        if ch and ch != "0":
            try:
                vals.append(float(ch))
            except ValueError:
                pass
    vals.reverse()
    return vals


def calc_career_low_handicap(all_rounds: list[RoundData]) -> str | None:
    best_hi = 999.9
    for r in all_rounds:
        if r.excluded:
            continue
        ch = r.computed_handicap
        if ch and ch not in ("0", "0.0", "--"):
            try:
                v = float(ch)
                if 0 < v < best_hi:
                    best_hi = v
            except (ValueError, TypeError):
                pass
    return str(round(best_hi, 1)) if best_hi < 999.0 else None
