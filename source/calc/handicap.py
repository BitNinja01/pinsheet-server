import bisect
import math

from source.models import RoundData


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


# WHS Rule 5.2: the Handicap Index is computed from the most recent 20
# acceptable Score Differentials. Shared by calc_handicap_index's default
# window and calc_handicap_trend's rolling window so the two windowing
# implementations can't drift apart.
WHS_HANDICAP_WINDOW = 20


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


def count_table_adjustment(count: int) -> float:
    """WHS Rule 5.2a: for scoring records with fewer than 20 differentials,
    after averaging the lowest-N differentials, subtract an Adjustment keyed
    on the number of differentials in the record, then round to nearest
    tenth. 3 -> -2.0, 4 -> -1.0, 6 -> -1.0, all other counts -> 0.0."""
    if count == 3:
        return -2.0
    if count == 4:
        return -1.0
    if count == 6:
        return -1.0
    return 0.0


def _is_eligible_diff_round(r: RoundData, include_9hole: bool) -> bool:
    """WHS Rule 5.2 acceptability: not excluded, has a real (non-sentinel)
    differential, and -- for 9-hole rounds -- only counts if 9-hole scores
    are opted into the record and the round already has a computed
    (non-zero) handicap to combine against."""
    if r.excluded:
        return False
    if not r.differential or r.differential == "0":
        return False
    if r.holes_selection != "all":
        if not include_9hole or not r.computed_handicap or float(r.computed_handicap) == 0:
            return False
    return True


def calc_effective_diffs(rounds: list[RoundData], include_9hole: bool = False) -> list:
    diffs = []
    for r in rounds:
        if not _is_eligible_diff_round(r, include_9hole):
            continue
        diffs.append(math.floor(float(r.differential) * 10) / 10)
    return sorted(diffs)


def get_best_n_rounds(
    rounds: list[RoundData],
    include_9hole: bool = False,
    n: int | None = None,
    window: int | None = None,
) -> list[RoundData]:
    """Return the best-N eligible rounds by differential.

    By default (`window=None`) this scans ALL of `rounds` for eligible
    rounds -- it does NOT apply the WHS Rule 5.2 most-recent-20 window on
    its own; callers that want the current-Handicap-Index best-N must
    either pre-slice to the recent window themselves, or (preferably) pass
    `window=WHS_HANDICAP_WINDOW` along with the full most-recent-first
    `rounds` list so eligible-round counting (not raw-round counting)
    determines the window, mirroring `calc_handicap_index`.
    """
    eligible = []
    for r in rounds:
        if not _is_eligible_diff_round(r, include_9hole):
            continue
        eligible.append(r)
        if window is not None and len(eligible) >= window:
            break
    eligible.sort(key=lambda r: math.floor(float(r.differential) * 10) / 10)
    if n is None:
        n = count_table_n(len(eligible))
    return eligible[:n]


def calc_handicap_index(
    rounds: list[RoundData],
    include_9hole: bool = False,
    window: int | None = WHS_HANDICAP_WINDOW,
) -> float | None:
    """WHS Rule 5.2: Handicap Index = (best-N of the) most recent acceptable
    Score Differentials, N chosen per the WHS count table, then adjusted per
    Rule 5.2a.

    CONTRACT: `rounds` MUST be sorted most-recent-first (index 0 = the most
    recently played round). This function walks `rounds` in that order,
    collecting only ELIGIBLE differentials (non-excluded, scored -- see
    `_is_eligible_diff_round`, the same rule used by `calc_effective_diffs`)
    and stops once it has collected `window` of them (default
    WHS_HANDICAP_WINDOW == 20, the WHS Rule 5.2 window size). An
    excluded/ineligible round does NOT consume a window slot -- the window
    is 20 eligible differentials, not 20 raw rounds. Pass `window=None` to
    disable the cap entirely (e.g. for callers that intentionally want the
    whole career record). Note: `calc_handicap_trend` does NOT delegate to
    this function -- it implements its own independent rolling-window
    accumulator over the same WHS_HANDICAP_WINDOW size.

    Once the (<=window) eligible differentials are collected, the usual
    Rule 5.2 best-N selection and Rule 5.2a adjustment are applied.
    """
    diffs = []
    for r in rounds:
        if not _is_eligible_diff_round(r, include_9hole):
            continue
        diffs.append(math.floor(float(r.differential) * 10) / 10)
        if window is not None and len(diffs) >= window:
            break

    diffs.sort()
    n = count_table_n(len(diffs))
    if n == 0 or not diffs:
        return None
    best_n = diffs[:n]
    avg = sum(best_n) / len(best_n)
    # WHS Rule 5.2a: subtract the count-table adjustment (keyed on the number
    # of differentials in the record) before the final round-to-tenth.
    return round(avg + count_table_adjustment(len(diffs)), 1)


def calc_handicap_trend(all_rounds: list[RoundData], include_9hole: bool = False) -> list:
    """Rolling WHS Rule 5.2 Handicap Index as of each round, chronologically.

    NOTE: this is an independent rolling-window accumulator -- it does NOT
    call/delegate to `calc_handicap_index`; it maintains its own sorted
    window of the most recent WHS_HANDICAP_WINDOW eligible differentials
    as it walks the (reconstructed) chronological order."""
    chronological = list(reversed(all_rounds))
    result = []
    window_diffs = []
    window_items = []

    for r in chronological:
        if not _is_eligible_diff_round(r, include_9hole):
            continue

        diff = math.floor(float(r.differential) * 10) / 10

        window_items.append((diff, r))
        bisect.insort(window_diffs, diff)

        if len(window_items) > WHS_HANDICAP_WINDOW:
            old_diff, _ = window_items.pop(0)
            window_diffs.remove(old_diff)

        n = count_table_n(len(window_diffs))
        if n > 0:
            avg = sum(window_diffs[:n]) / n
            # WHS Rule 5.2a: subtract the count-table adjustment (keyed on
            # the number of differentials in the window) before rounding.
            val = round(avg + count_table_adjustment(len(window_diffs)), 1)
            result.append((r.date, val))

    return result


def calc_playing_to_handicap_rate(rounds: list[RoundData], include_9hole: bool = False) -> float | None:
    overall_hi = calc_handicap_index(rounds, include_9hole)
    valid = []
    for r in rounds:
        if r.excluded:
            continue
        if not r.differential or r.differential in ("0", ""):
            continue
        hc = r.computed_handicap if r.computed_handicap and r.computed_handicap not in ("0", "") else overall_hi
        if hc is None:
            continue
        valid.append((float(r.differential), float(hc)))
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
