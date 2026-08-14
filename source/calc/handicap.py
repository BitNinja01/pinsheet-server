import bisect
import math
from decimal import Decimal, ROUND_HALF_UP

from source.models import RoundData


def round_half_up(value: float, ndigits: int = 1) -> float:
    """WHS-compliant nearest-tenth rounding: rounds .5 ties UP (away from
    zero), NOT Python's built-in `round()`, which uses banker's rounding
    (round-half-to-even) and would silently misround exact ties -- e.g.
    `round(18.25, 1) == 18.2` (wrong) instead of `18.3` (correct).

    WHS Rule 5.1a: "An 18-hole Score Differential is calculated as follows
    and rounded to the nearest tenth, with .5 rounded upwards..." Rule 5.2a
    applies the same "round to the nearest tenth" convention to the
    Handicap Index. Both rules are implemented via this helper so every WHS
    nearest-tenth rounding site behaves identically.

    Uses `Decimal(str(value))` (not `Decimal(value)`) to avoid re-surfacing
    the binary floating-point representation error of `value` itself before
    rounding -- `str(value)` gives Python's shortest round-tripping decimal
    representation, which is what a human (and the WHS rule text) means by
    "the value".

    NEGATIVE-TIE DECISION: `Decimal.quantize(..., rounding=ROUND_HALF_UP)`
    rounds ties AWAY FROM ZERO (e.g. -2.25 -> -2.3), not toward positive
    infinity. WHS Rule 5.1a's "rounded upwards" is written for the
    (always non-negative) Score Differential calculation, where "upwards"
    and "away from zero" coincide -- there is no ambiguity in the rule text
    for that case. For a negative (plus) Handicap Index, "rounded upwards"
    read literally would mean toward +infinity (-2.25 -> -2.2), but
    away-from-zero is the standard, unambiguous interpretation of "round
    half up" used by virtually every rounding-mode implementation
    (including Python's `decimal.ROUND_HALF_UP`) and by common golf/WHS
    software implementations, so it is adopted here uniformly for both
    differentials and Handicap Index values rather than special-casing sign.
    A negative .x5 boundary is asserted against this (away-from-zero)
    behavior in tests -- see `test_round_half_up_negative_tie_away_from_zero`.
    """
    quantum = Decimal(1).scaleb(-ndigits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


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
    # WHS Rule 6.1a (2024): Course Handicap = HI x (Slope/113) + (CR - Par),
    # rounded to the nearest whole number with .5 rounded UP. Python's built-in
    # round() is banker's (half-to-even), so 10.5 -> 10 and 2.5 -> 2 (both
    # should be 11 and 3). round_half_up(x, 0) gives the WHS-correct integer.
    return int(round_half_up(handicap * (course_slope / 113) + (course_rating - course_par), 0))


# WHS Appendix C: recommended Handicap Allowances by play format. These are
# the *recommended* percentages a committee may apply to the Course Handicap
# to derive the Playing Handicap for a given format -- they are reference
# defaults, not mandated values (a committee/club may choose otherwise), so
# callers pass an explicit `allowance_percent` to `calc_playing_handicap`
# rather than this dict being consulted automatically.
WHS_HANDICAP_ALLOWANCES = {
    "individual_match": 100,
    "individual_stroke": 95,
    "fourball_match": 90,
    "fourball_stroke": 85,
    "stableford_individual": 95,
}


def calc_playing_handicap(course_handicap: int, allowance_percent: float = 100) -> int:
    # WHS Rule 6.2: Playing Handicap = Course Handicap x Handicap Allowance,
    # rounded to the nearest whole number with .5 rounded UP (same
    # round_half_up convention as Rule 6.1a's Course Handicap rounding --
    # NOT Python's banker's-rounding round()). Appendix C recommends
    # allowance percentages by format (see WHS_HANDICAP_ALLOWANCES); the
    # default of 100 leaves the Course Handicap unchanged, matching prior
    # (pre-Rule-6.2) behavior for callers that don't specify an allowance.
    return int(round_half_up(course_handicap * allowance_percent / 100.0, 0))


def calc_round_dif(tee_slope, adjusted_gross_score, tee_rating) -> float:
    # WHS Rule 5.1a: "...rounded to the nearest tenth, with .5 rounded
    # upwards" -- use round_half_up, not banker's-rounding round().
    return round_half_up((113 / tee_slope) * (adjusted_gross_score - tee_rating), 1)


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
    # of differentials in the record) before the final round-to-tenth (half
    # up, per Rule 5.1a's rounding convention -- see round_half_up).
    return round_half_up(avg + count_table_adjustment(len(diffs)), 1)


def apply_handicap_cap(raw_hi: float, low_hi: float | None) -> float:
    """WHS Rule 5.8 (Soft Cap / Hard Cap): once a player's Low Handicap Index
    (LHI, Rule 5.7) is established, apply the following to a freshly
    calculated Handicap Index (`raw_hi`):

      increase = raw_hi - low_hi
      - Soft cap: if increase > 3.0, the amount above 3.0 is reduced to 50%:
        capped = low_hi + 3.0 + 0.5 * (increase - 3.0)
      - Hard cap: the (possibly soft-capped) result may never exceed
        low_hi + 5.0.
      - No limit on decrease: if increase <= 3.0 (including negative /
        decreasing HI), `raw_hi` passes through unchanged.

    `low_hi` is None until Rule 5.7 establishes an LHI (the player has not
    yet accumulated >= 20 acceptable scores) -- in that case there is no cap
    and `raw_hi` is returned unchanged (rounded to the nearest tenth, per
    WHS convention).
    """
    if low_hi is None:
        return round_half_up(raw_hi, 1)

    increase = raw_hi - low_hi
    if increase <= 3.0:
        return round_half_up(raw_hi, 1)

    capped = low_hi + 3.0 + 0.5 * (increase - 3.0)  # soft cap
    hard_cap = low_hi + 5.0
    if capped > hard_cap:
        capped = hard_cap  # hard cap
    return round_half_up(capped, 1)


def exceptional_reduction(hi_in_effect: float | None, differential: float) -> float:
    """WHS Rule 5.9 (Exceptional Score Reduction): when a posted Score
    Differential is markedly LOWER than the Handicap Index in effect when
    the round was played, the Handicap Index is reduced:

      gap = hi_in_effect - differential
      -  7.0 <= gap < 10.0  -> -1.0
      - 10.0 <= gap         -> -2.0
      - otherwise (gap < 7.0, including a negative gap)  ->  0.0

    `hi_in_effect` is the DISPLAYED Handicap Index the player held
    immediately before this round was played (i.e. the prior round's
    post-ESR, post-Rule-5.8-cap value) -- not this round's own freshly
    calculated index. If no Handicap Index has been established yet
    (`hi_in_effect is None`), the round cannot be exceptional and this
    returns 0.0 (there is nothing to compare the score against).

    The returned value is the (negative or zero) adjustment itself, ready
    to be summed with other active reductions and added to a raw Handicap
    Index (see `store.recompute_handicaps_for_user`'s WHS Rule 5.9 wiring
    for how the per-round reductions accumulate over the most-recent-20
    eligible window).
    """
    if hi_in_effect is None:
        return 0.0
    # Both `hi_in_effect` and `differential` are values rounded to a tenth
    # (WHS convention -- computed_handicap and Score Differential are both
    # display/stored to 1 decimal place), but subtracting two floats each
    # already rounded to a tenth can still land a hair off an exact tenth
    # (e.g. 20.0 - 13.0 == 6.999999999999998 in IEEE 754 binary floating
    # point for some tenth pairs) due to binary floating-point
    # representation error -- NOT because either input was imprecise. Round
    # the gap itself back to a tenth before the threshold comparisons so a
    # true gap of exactly 7.0/10.0 is never misclassified one bucket low by
    # a sub-cent epsilon.
    gap = round(hi_in_effect - differential, 1)
    if gap >= 10.0:
        return -2.0
    if gap >= 7.0:
        return -1.0
    return 0.0


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
            # the number of differentials in the window) before rounding
            # (half up, mirroring calc_handicap_index -- same rule, same
            # rounding convention, so the trend series and the live
            # Handicap Index never disagree on the same window of diffs).
            val = round_half_up(avg + count_table_adjustment(len(window_diffs)), 1)
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
    # WHS nearest-tenth, .5 UP (round_half_up) for consistency; best_hi is a
    # min of already-tenths-precision stored HIs so no new tie arises today.
    return str(round_half_up(best_hi, 1)) if best_hi < 999.0 else None
