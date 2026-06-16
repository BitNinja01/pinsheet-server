from datetime import datetime

from flask import render_template, request, jsonify, g, current_app, url_for
from flask_login import login_required, current_user

from store import create_invite_code, get_invite_codes, get_plugin_states, generate_password_reset_token
from calc import (
    calc_scoring_average, calc_fir_percent, calc_gir_percent,
    calc_putts_per_round, calc_scramble_percent, calc_penalties_per_round,
    calc_scoring_avg_by_par_type, calc_one_putt_percent, calc_two_putt_percent,
    calc_three_putt_percent, calc_putts_per_gir, calc_personal_bests,
    calc_handicap_index, calc_hi_journey, calc_most_played_course,
    calc_golfiest_month, calc_most_common_day, calc_best_single_round,
    calc_best_3round_stretch, calc_biggest_improvement, calc_first_score_milestone,
    calc_first_hi_milestone, calc_score_breakdown, calc_hole_in_ones,
    calc_best_gir_round, calc_best_fir_round, calc_season_yardage,
    calc_penalty_free_rounds, calc_rounds_total, calc_season_rounds,
    calc_per_round_average, calc_hole_percentage,
    last_n_rounds, best_n_rounds,
)
from calc import stat_delta
from source.models import dict_to_course
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context


def register_stats_routes(app):
    @app.route("/stats")
    @login_required
    def stats():
        include_9hole = get_settings().get("include_9hole", True)

        all_rounds = get_all_rounds_for_user()
        rounds = list(all_rounds)
        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}

        all_eligible = [r for r in rounds if not r.excluded]
        b8 = best_n_rounds(rounds, 8)
        l5 = last_n_rounds(rounds, 5)
        l10 = last_n_rounds(rounds, 10)
        l20 = last_n_rounds(rounds, 20)

        now = datetime.now()
        this_month_rounds = sum(1 for r in all_eligible if r.date.startswith(now.strftime("%Y-%m")))

        def fmt_val(val, suffix="", precision=1):
            if val is None:
                return "\u2014"
            if suffix == "%":
                return f"{val:.{precision}f}%"
            return f"{val:.{precision}f}{suffix}"

        def _cell(label, b8v, l5v, l10v, l20v, suffix="", precision=1, higher_better=False):
            def _fmt(v):
                if v is None:
                    return "\u2014"
                if suffix == "%":
                    return f"{v:.{precision}f}%"
                return f"{v:.{precision}f}{suffix}"
            windows = [
                {"label": "B8", "value": _fmt(b8v)},
                {"label": "L5", "value": _fmt(l5v)},
                {"label": "L10", "value": _fmt(l10v)},
                {"label": "L20", "value": _fmt(l20v)},
            ]
            value = _fmt(b8v)
            delta_class, delta_text, cell_class = stat_delta(b8v, l20v, higher_better, precision, suffix)
            return {
                "label": label, "value": value,
                "delta": delta_text, "delta_class": delta_class,
                "cell_class": cell_class,
                "windows": windows,
            }

        def _placeholder_cell(label):
            d = "\u2014"
            return {
                "label": label, "value": d, "delta": d,
                "delta_class": "", "cell_class": "",
                "windows": [{"label": "B8", "value": d}, {"label": "L5", "value": d}, {"label": "L10", "value": d}, {"label": "L20", "value": d}],
            }

        # ── Stat Strip ──────────────────────────────────────────────────
        _sa_b8 = calc_scoring_average(b8)
        _sa_l20 = calc_scoring_average(l20)
        _fir_b8 = calc_fir_percent(b8, courses_dict)
        _fir_l20 = calc_fir_percent(l20, courses_dict)
        _gir_b8 = calc_gir_percent(b8)
        _gir_l20 = calc_gir_percent(l20)
        _pt_b8 = calc_putts_per_round(b8)
        _pt_l20 = calc_putts_per_round(l20)
        _sc_b8 = calc_scramble_percent(b8, courses_dict)
        _sc_l20 = calc_scramble_percent(l20, courses_dict)

        _sd_sa_cls, _sd_sa_txt, _ = stat_delta(_sa_b8, _sa_l20, False, 1, "")
        _sd_fir_cls, _sd_fir_txt, _ = stat_delta(_fir_b8, _fir_l20, True, 1, "%")
        _sd_gir_cls, _sd_gir_txt, _ = stat_delta(_gir_b8, _gir_l20, True, 1, "%")
        _sd_pt_cls, _sd_pt_txt, _ = stat_delta(_pt_b8, _pt_l20, False, 1, "")
        _sd_sc_cls, _sd_sc_txt, _ = stat_delta(_sc_b8, _sc_l20, True, 1, "%")

        strip_data = [
            {"label": "Rounds", "value": str(len(all_eligible)), "is_pct": False,
             "delta_class": "is-up" if this_month_rounds > 0 else "",
             "delta_text": f"+{this_month_rounds} this month"},
            {"label": "Avg Score", "value": fmt_val(_sa_b8, "", 1), "is_pct": False,
             "delta_class": _sd_sa_cls, "delta_text": _sd_sa_txt},
            {"label": "FIR%", "value": fmt_val(_fir_b8, "", 0), "is_pct": True,
             "delta_class": _sd_fir_cls, "delta_text": _sd_fir_txt},
            {"label": "GIR%", "value": fmt_val(_gir_b8, "", 0), "is_pct": True,
             "delta_class": _sd_gir_cls, "delta_text": _sd_gir_txt},
            {"label": "Putts/Rd", "value": fmt_val(_pt_b8, "", 1), "is_pct": False,
             "delta_class": _sd_pt_cls, "delta_text": _sd_pt_txt},
            {"label": "Scramble%", "value": fmt_val(_sc_b8, "", 0), "is_pct": True,
             "delta_class": _sd_sc_cls, "delta_text": _sd_sc_txt},
        ]

        # ── Section 1: Scoring Statistics ───────────────────────────────
        _birdie = lambda r: calc_per_round_average(r, courses_dict, lambda g, p: g < p)
        _bogey = lambda r: calc_per_round_average(r, courses_dict, lambda g, p: g == p + 1)
        _dbl = lambda r: calc_per_round_average(r, courses_dict, lambda g, p: g >= p + 2)
        _pb = lambda r: calc_hole_percentage(r, courses_dict, lambda g, p: g < p)

        sa_b8 = calc_scoring_average(b8)
        sa_l5_ = calc_scoring_average(l5)
        sa_l10 = calc_scoring_average(l10)
        sa_l20_ = calc_scoring_average(l20)

        section1 = {
            "label": "Scoring",
            "cells": [
                _cell("Score Avg", sa_b8, sa_l5_, sa_l10, sa_l20_, "", 1, False),
                _placeholder_cell("Strokes Gained"),
                _cell("Birdies / Rd", _birdie(b8), _birdie(l5), _birdie(l10), _birdie(l20), "", 1, True),
                _cell("Bogeys / Rd", _bogey(b8), _bogey(l5), _bogey(l10), _bogey(l20), "", 1, False),
                _cell("Doubles+ / Rd", _dbl(b8), _dbl(l5), _dbl(l10), _dbl(l20), "", 1, False),
                _cell("Par Breakers", _pb(b8), _pb(l5), _pb(l10), _pb(l20), "%", 1, True),
            ],
        }

        # ── Section 2: Putting Statistics ───────────────────────────────
        _pt_b8 = calc_putts_per_round(b8)
        _pt_l5_ = calc_putts_per_round(l5)
        _pt_l10 = calc_putts_per_round(l10)
        _pt_l20_ = calc_putts_per_round(l20)

        _o1_b8 = calc_one_putt_percent(b8)
        _o1_l5 = calc_one_putt_percent(l5)
        _o1_l10 = calc_one_putt_percent(l10)
        _o1_l20 = calc_one_putt_percent(l20)

        _o3_b8 = calc_three_putt_percent(b8)
        _o3_l5 = calc_three_putt_percent(l5)
        _o3_l10 = calc_three_putt_percent(l10)
        _o3_l20 = calc_three_putt_percent(l20)

        _pg_b8 = calc_putts_per_gir(b8)
        _pg_l5 = calc_putts_per_gir(l5)
        _pg_l10 = calc_putts_per_gir(l10)
        _pg_l20 = calc_putts_per_gir(l20)

        _o2_b8 = calc_two_putt_percent(b8)
        _o2_l5 = calc_two_putt_percent(l5)
        _o2_l10 = calc_two_putt_percent(l10)
        _o2_l20 = calc_two_putt_percent(l20)

        section2 = {
            "label": "Putting",
            "cells": [
                _cell("Putts / Round", _pt_b8, _pt_l5_, _pt_l10, _pt_l20_, "", 1, False),
                _cell("1-Putt %", _o1_b8, _o1_l5, _o1_l10, _o1_l20, "%", 1, True),
                _cell("2-Putt %", _o2_b8, _o2_l5, _o2_l10, _o2_l20, "%", 1, True),
                _cell("3-Putt %", _o3_b8, _o3_l5, _o3_l10, _o3_l20, "%", 1, False),
                _cell("Putts / GIR", _pg_b8, _pg_l5, _pg_l10, _pg_l20, "", 2, False),
                _placeholder_cell("Longest Made"),
            ],
        }

        # ── Section 3: Short Game Statistics ────────────────────────────
        _sc_b8 = calc_scramble_percent(b8, courses_dict)
        _sc_l5_ = calc_scramble_percent(l5, courses_dict)
        _sc_l10 = calc_scramble_percent(l10, courses_dict)
        _sc_l20_ = calc_scramble_percent(l20, courses_dict)

        _px_b8 = calc_penalties_per_round(b8)
        _px_l5 = calc_penalties_per_round(l5)
        _px_l10 = calc_penalties_per_round(l10)
        _px_l20 = calc_penalties_per_round(l20)

        section3 = {
            "label": "Short Game",
            "cells": [
                _cell("Scramble %", _sc_b8, _sc_l5_, _sc_l10, _sc_l20_, "%", 1, True),
                _placeholder_cell("Sand Save %"),
                _placeholder_cell("Up & Down %"),
                _placeholder_cell("Prox to Hole"),
                _placeholder_cell("Chip-Ins"),
                _cell("Penalties / Rd", _px_b8, _px_l5, _px_l10, _px_l20, "", 2, False),
            ],
        }

        # ── Section 4: Tee to Green Statistics ─────────────────────────
        _fir_b8 = calc_fir_percent(b8, courses_dict)
        _fir_l5_ = calc_fir_percent(l5, courses_dict)
        _fir_l10 = calc_fir_percent(l10, courses_dict)
        _fir_l20_ = calc_fir_percent(l20, courses_dict)

        _gir_b8 = calc_gir_percent(b8)
        _gir_l5_ = calc_gir_percent(l5)
        _gir_l10 = calc_gir_percent(l10)
        _gir_l20_ = calc_gir_percent(l20)

        _p3_b8 = calc_scoring_avg_by_par_type(b8, courses_dict).get(3)
        _p3_l5 = calc_scoring_avg_by_par_type(l5, courses_dict).get(3)
        _p3_l10 = calc_scoring_avg_by_par_type(l10, courses_dict).get(3)
        _p3_l20 = calc_scoring_avg_by_par_type(l20, courses_dict).get(3)

        section4 = {
            "label": "Tee to Green",
            "cells": [
                _cell("FIR %", _fir_b8, _fir_l5_, _fir_l10, _fir_l20_, "%", 1, True),
                _cell("GIR %", _gir_b8, _gir_l5_, _gir_l10, _gir_l20_, "%", 1, True),
                _placeholder_cell("Driving Dist"),
                _placeholder_cell("Approach Prox"),
                _placeholder_cell("SG: T2G"),
                _cell("Par 3 Avg", _p3_b8, _p3_l5, _p3_l10, _p3_l20, "", 2, False),
            ],
        }

        sections_data = [section1, section2, section3, section4]

        # ── Bests ───────────────────────────────────────────────────────
        bests = calc_personal_bests(rounds, courses_dict)
        bests_data = {
            "label": "Bests",
            "headline": "Your personal best performances.",
            "bests": [
                ("Lowest Gross", bests.get("best_gross"), bests.get("best_gross_date")),
                ("Lowest Diff", bests.get("best_diff"), bests.get("best_diff_date")),
                ("Most FIR", bests.get("most_fir"), bests.get("most_fir_date")),
                ("Most GIR", bests.get("most_gir"), bests.get("most_gir_date")),
                ("Fewest Putts", bests.get("fewest_putts"), bests.get("fewest_putts_date")),
            ],
        }

        return render_template("stats.html", **base_context(
            current_page="stats",
            strip=strip_data,
            sections=sections_data,
            bests_section=bests_data,
        ))

    @app.route("/season")
    @login_required
    def season_summary():
        settings = get_settings()
        include_9hole = settings.get("include_9hole", True)

        all_rounds = get_all_rounds_for_user()
        rounds = list(all_rounds)
        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}

        if settings.get("season_enabled"):
            season_rounds = calc_season_rounds(rounds, settings)
        else:
            season_rounds = rounds

        hi = calc_handicap_index(rounds, include_9hole)
        journey = calc_hi_journey(rounds, season_rounds, hi)
        most_played = calc_most_played_course(season_rounds)
        golfiest = calc_golfiest_month(season_rounds)
        common_day = calc_most_common_day(season_rounds)
        best_round = calc_best_single_round(season_rounds)
        best_stretch = calc_best_3round_stretch(season_rounds)
        biggest_improvement = calc_biggest_improvement(season_rounds)
        first_score_ms = calc_first_score_milestone(season_rounds, rounds)
        first_hi_ms = calc_first_hi_milestone(season_rounds, rounds)
        breakdown = calc_score_breakdown(season_rounds, courses_dict)
        hole_in_ones = calc_hole_in_ones(season_rounds, courses_dict)
        best_gir = calc_best_gir_round(season_rounds)
        best_fir = calc_best_fir_round(season_rounds, courses_dict)
        walking_miles = calc_season_yardage(season_rounds, courses_dict, "walking")
        riding_miles = calc_season_yardage(season_rounds, courses_dict, "riding")
        penalty_free = calc_penalty_free_rounds(season_rounds)
        rounds_count = len(season_rounds)
        total_rounds = calc_rounds_total(rounds)

        return render_template("season_summary.html", **base_context(
            settings=settings,
            rounds_count=rounds_count,
            total_rounds=total_rounds,
            journey=journey,
            most_played=most_played,
            golfiest=golfiest,
            common_day=common_day,
            best_round=best_round,
            best_stretch=best_stretch,
            biggest_improvement=biggest_improvement,
            first_score_ms=first_score_ms,
            first_hi_ms=first_hi_ms,
            breakdown=breakdown,
            hole_in_ones=hole_in_ones,
            best_gir=best_gir,
            best_fir=best_fir,
            walking_miles=walking_miles,
            riding_miles=riding_miles,
            penalty_free=penalty_free,
        ))

    @app.route("/admin/invites", methods=["GET", "POST"])
    @login_required
    def admin_invites():
        if not current_user.is_admin:
            return "Forbidden", 403

        if request.method == "POST":
            base_url = request.host_url.rstrip("/")
            generated_token = None
            token_url = None
            code = None

            if request.form.get("reset_user_id"):
                reset_user_id = int(request.form.get("reset_user_id"))
                raw_token = generate_password_reset_token(reset_user_id)
                generated_token = raw_token
                token_url = base_url + url_for("reset_password", token=raw_token)
            else:
                code = create_invite_code(current_user.id)

            return render_template("admin_invites.html", **base_context(
                codes=get_invite_codes(), new_code=code, base_url=base_url,
                plugin_states=get_plugin_states(),
                discovered_plugins=getattr(current_app, "_discovered_plugins", []),
                plugin_states_at_startup=getattr(current_app, "_plugin_states_at_startup", {}),
                generated_token=generated_token, token_url=token_url,
            ))

        return render_template("admin_invites.html", **base_context(
            codes=get_invite_codes(), new_code=None, base_url=None,
            plugin_states=get_plugin_states(),
            discovered_plugins=getattr(current_app, "_discovered_plugins", []),
            plugin_states_at_startup=getattr(current_app, "_plugin_states_at_startup", {}),
            generated_token=None, token_url=None,
        ))
