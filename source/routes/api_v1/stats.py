"""GET /api/v1/stats -- read-only, owner-scoped (`WHERE user_id = ?`).

Mirrors the legacy `_load_rounds` best-8/last-N windowing pattern
(`stats.py:49-56`): the handicap-relevant figures use the best-8-of-recent-20
window (`best_n_rounds`), matching how the legacy scoring/fairways/greens/
putting stat pages compute their headline numbers.
"""
import logging

from apiflask import APIBlueprint
from flask_login import current_user

from datetime import datetime, timedelta

from calc import (
    best_n_rounds,
    calc_fir_percent,
    calc_gir_percent,
    calc_handicap_pairs_in_range,
    calc_par_or_better_percent,
    calc_putts_per_round,
    calc_scoring_average,
    calc_scramble_percent,
    current_and_previous_handicap_index,
)
from source.auth_keys import require_permission
from source.models import dict_to_course
from source.routes.api_v1 import scopes
from source.routes.api_v1.schemas import StatsOutSchema
from store import get_all_rounds, get_courses, load_settings

_log = logging.getLogger("pinsheet")

stats_v1 = APIBlueprint("stats_v1", __name__, url_prefix="/api/v1/stats")


@stats_v1.route("", methods=["GET"])
@require_permission(scopes.STATS_READ, contract="problem", permissive_pending=True)
@stats_v1.output(StatsOutSchema)
def get_stats():
    all_rounds = get_all_rounds(current_user.id)
    # SEC-1(b) (Revision 2, defense-in-depth): courses are a shared, global
    # catalog (ADR-011) -- a single malformed row (e.g. a non-numeric
    # hole_index/par/rating/slope, pre-dating the SEC-1(a) schema fix, or
    # written by any other future path) must not 500 this endpoint for
    # EVERY user. Skip and log the bad row instead of letting
    # `dict_to_course`'s `int()`/`float()` conversions propagate.
    courses_dict = {}
    for name, d in get_courses().items():
        try:
            courses_dict[name] = dict_to_course(name, d)
        except (ValueError, TypeError):
            _log.warning("api_v1.stats: skipping malformed course row name=%s", name)
    settings = load_settings(current_user.id)
    include_9hole = settings.get("include_9hole", True)

    b8 = best_n_rounds(all_rounds, 8)

    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    trend = [{"date": d, "value": v} for d, v in calc_handicap_pairs_in_range(all_rounds, cutoff)]

    # Bug #135 / #98 single-source-of-truth: report the STORED, WHS-clamped
    # Handicap Index (post-ESR Rule 5.9, post-cap Rule 5.8, post-54.0 Rule 5.3
    # `computed_handicap` written by `recompute_handicaps_for_user`) that the
    # dashboard hero, round detail, trend and rankings all display -- NOT a
    # fresh raw `calc_handicap_index()`, which returns the pre-ESR/pre-cap
    # value and diverges from every other surface. `current_and_previous_
    # handicap_index` is the same reader the dashboard panel uses.
    current_hi, _ = current_and_previous_handicap_index(all_rounds, include_9hole)

    return {
        "rounds_total": len(all_rounds),
        "handicap_index": current_hi,
        "scoring_average": calc_scoring_average(b8),
        "fir_percent": calc_fir_percent(b8, courses_dict),
        "gir_percent": calc_gir_percent(b8),
        "putts_per_round": calc_putts_per_round(b8),
        "scramble_percent": calc_scramble_percent(b8, courses_dict),
        "par_or_better_percent": calc_par_or_better_percent(b8, courses_dict),
        "handicap_trend": trend,
    }
