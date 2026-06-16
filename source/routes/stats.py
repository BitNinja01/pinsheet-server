from datetime import datetime

from flask import render_template, request, jsonify, g, current_app, url_for, redirect
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
    calc_avg_vs_par, calc_score_distribution, calc_big_number_rate,
    calc_clean_card_percent, calc_scoring_consistency, calc_score_components,
    calc_four_plus_putt_percent, calc_putts_by_par_type,
    calc_fir_miss_tendency, calc_scoring_by_fairway, calc_scoring_by_miss_side,
    calc_gir_by_par_type, calc_gir_miss_direction, calc_gir_from_fairway_vs_rough,
    calc_scoring_by_gir, calc_scramble_by_miss_direction, calc_scramble_by_par_type,
    calc_ob_stats, calc_penalty_stats, calc_momentum_recovery,
    calc_nemesis_best_holes, calc_scoring_trend, calc_fir_trend, calc_gir_trend,
    calc_putts_trend, calc_scramble_trend, calc_handicap_trend,
    calc_playing_to_handicap_rate,
    calc_par_or_better_percent,
)
from calc import stat_delta
from source.models import dict_to_course
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context


def register_stats_routes(app):
    def _fmt(val, suffix="", precision=1):
        if val is None:
            return "\u2014"
        if suffix == "%":
            return f"{val:.{precision}f}%"
        return f"{val:.{precision}f}{suffix}"

    def _delta(val_b8, val_l20, higher_better, precision=1, suffix=""):
        cls, text, _ = stat_delta(val_b8, val_l20, higher_better, precision, suffix)
        return {"delta_dir": "up" if cls == "is-up" else ("down" if cls == "is-down" else ""), "delta": text}

    def _load_rounds():
        all_rounds = list(get_all_rounds_for_user())
        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}
        b8 = best_n_rounds(all_rounds, 8)
        l5 = last_n_rounds(all_rounds, 5)
        l10 = last_n_rounds(all_rounds, 10)
        l20 = last_n_rounds(all_rounds, 20)
        return all_rounds, courses_dict, b8, l5, l10, l20

    @app.route("/stats")
    @login_required
    def stats_redirect():
        return redirect("/stats/scoring")

    @app.route("/stats/scoring")
    @login_required
    def stats_scoring():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        sa_b8 = calc_scoring_average(b8)
        sa_l20 = calc_scoring_average(l20)
        to_par_b8 = calc_avg_vs_par(b8, courses_dict)
        to_par_l20 = calc_avg_vs_par(l20, courses_dict)
        par3_b8 = calc_scoring_avg_by_par_type(b8, courses_dict).get(3)
        par3_l20 = calc_scoring_avg_by_par_type(l20, courses_dict).get(3)
        par4_b8 = calc_scoring_avg_by_par_type(b8, courses_dict).get(4)
        par4_l20 = calc_scoring_avg_by_par_type(l20, courses_dict).get(4)
        par5_b8 = calc_scoring_avg_by_par_type(b8, courses_dict).get(5)
        par5_l20 = calc_scoring_avg_by_par_type(l20, courses_dict).get(5)
        stddev_b8 = calc_scoring_consistency(b8, courses_dict)
        stddev_l20 = calc_scoring_consistency(l20, courses_dict)
        pob_b8 = calc_par_or_better_percent(b8, courses_dict)
        pob_l20 = calc_par_or_better_percent(l20, courses_dict)
        score_dist_b8 = calc_score_distribution(b8, courses_dict)
        score_dist_l20 = calc_score_distribution(l20, courses_dict)
        blowup_b8 = calc_big_number_rate(b8, courses_dict)
        blowup_l20 = calc_big_number_rate(l20, courses_dict)
        clean_card_b8 = calc_clean_card_percent(b8, courses_dict)
        clean_card_l20 = calc_clean_card_percent(l20, courses_dict)
        components = calc_score_components(b8, courses_dict)

        scoring_by_fw = calc_scoring_by_fairway(b8, courses_dict)
        miss_cost = (scoring_by_fw.get("missed") - scoring_by_fw.get("hit")) if scoring_by_fw.get("hit") is not None and scoring_by_fw.get("missed") is not None else None
        scoring_spark = [v for _, v in calc_scoring_trend(all_rounds)]

        return render_template("stats/scoring.html", **base_context(
            current_page="stats",
            scoring_avg=sa_b8, scoring_avg_delta=_delta(sa_b8, sa_l20, False),
            to_par=to_par_b8, to_par_delta=_delta(to_par_b8, to_par_l20, False),
            par_3_avg=par3_b8, par_3_avg_delta=_delta(par3_b8, par3_l20, False),
            par_4_avg=par4_b8, par_4_avg_delta=_delta(par4_b8, par4_l20, False),
            par_5_avg=par5_b8, par_5_avg_delta=_delta(par5_b8, par5_l20, False),
            std_dev=stddev_b8, std_dev_delta=_delta(stddev_b8, stddev_l20, False),
            par_or_better_pct=pob_b8, par_or_better_delta=_delta(pob_b8, pob_l20, True, 1, "%"),
            blow_up_rate=blowup_b8, blow_up_delta=_delta(blowup_b8, blowup_l20, False, 1, "%"),
            clean_card_pct=clean_card_b8, clean_card_delta=_delta(clean_card_b8, clean_card_l20, True, 1, "%"),
            score_distribution=score_dist_b8,
            score_components=components,
            fairway_miss_cost=miss_cost,
            scoring_spark=scoring_spark,
        ))

    @app.route("/stats/penalties")
    @login_required
    def stats_penalties():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        pen_rd_b8 = calc_penalties_per_round(b8)
        pen_rd_l20 = calc_penalties_per_round(l20)
        pen_stats = calc_penalty_stats(b8, courses_dict)
        ob_stats = calc_ob_stats(b8, courses_dict)
        total_ob_rd = ob_stats.get("total_ob_per_round")

        pen_free = sum(1 for r in b8 if r.holes and sum(h.penalties for h in r.holes.values()) == 0)
        pen_free_pct = (pen_free / len(b8) * 100) if b8 else None

        return render_template("stats/penalties.html", **base_context(
            current_page="stats",
            penalties_per_round=pen_rd_b8, pen_rd_delta=_delta(pen_rd_b8, pen_rd_l20, False),
            penalty_vs_par=pen_stats.get("penalty_avg_vs_par"),
            clean_vs_par=pen_stats.get("clean_avg_vs_par"),
            pen_free_pct=pen_free_pct,
            total_ob_rd=total_ob_rd,
            ob_stats=ob_stats,
            penalty_stats=pen_stats,
        ))

    @app.route("/stats/fairways")
    @login_required
    def stats_fairways():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        fir_b8 = calc_fir_percent(b8, courses_dict)
        fir_l20 = calc_fir_percent(l20, courses_dict)
        miss_tend = calc_fir_miss_tendency(b8, courses_dict)
        scoring_fw = calc_scoring_by_fairway(b8, courses_dict)
        scoring_miss_side = calc_scoring_by_miss_side(b8, courses_dict)
        ob_stats = calc_ob_stats(b8, courses_dict)
        fir_spark = [v for _, v in calc_fir_trend(all_rounds, courses_dict)]

        return render_template("stats/fairways.html", **base_context(
            current_page="stats",
            fir_pct=fir_b8, fir_delta=_delta(fir_b8, fir_l20, True, 1, "%"),
            miss_left=miss_tend.get("left"),
            miss_right=miss_tend.get("right"),
            scoring_hit=scoring_fw.get("hit"),
            scoring_missed=scoring_fw.get("missed"),
            scoring_miss_left=scoring_miss_side.get("left"),
            scoring_miss_right=scoring_miss_side.get("right"),
            ob_stats=ob_stats,
            fir_spark=fir_spark,
        ))

    @app.route("/stats/greens")
    @login_required
    def stats_greens():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        gir_b8 = calc_gir_percent(b8)
        gir_l20 = calc_gir_percent(l20)
        gir_by_par = calc_gir_by_par_type(b8, courses_dict)
        gir_miss_dir = calc_gir_miss_direction(b8)
        gir_from = calc_gir_from_fairway_vs_rough(b8, courses_dict)
        scoring_gir = calc_scoring_by_gir(b8, courses_dict)
        ob_stats = calc_ob_stats(b8, courses_dict)
        gir_spark = [v for _, v in calc_gir_trend(all_rounds)]

        return render_template("stats/greens.html", **base_context(
            current_page="stats",
            gir_pct=gir_b8, gir_delta=_delta(gir_b8, gir_l20, True, 1, "%"),
            gir_par_3=gir_by_par.get(3),
            gir_par_4=gir_by_par.get(4),
            gir_par_5=gir_by_par.get(5),
            gir_from_fairway=gir_from.get("fairway"),
            gir_from_rough=gir_from.get("rough"),
            gir_miss_direction=gir_miss_dir,
            gir_scoring_hit=scoring_gir.get("hit"),
            gir_scoring_missed=scoring_gir.get("missed"),
            ob_stats=ob_stats,
            gir_spark=gir_spark,
        ))

    @app.route("/stats/putting")
    @login_required
    def stats_putting():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        pt_rd_b8 = calc_putts_per_round(b8)
        pt_rd_l20 = calc_putts_per_round(l20)
        pt_gir_b8 = calc_putts_per_gir(b8)
        pt_gir_l20 = calc_putts_per_gir(l20)
        o1_b8 = calc_one_putt_percent(b8)
        o1_l20 = calc_one_putt_percent(l20)
        o2_b8 = calc_two_putt_percent(b8)
        o2_l20 = calc_two_putt_percent(l20)
        o3_b8 = calc_three_putt_percent(b8)
        o3_l20 = calc_three_putt_percent(l20)
        o4p_b8 = calc_four_plus_putt_percent(b8)
        o4p_l20 = calc_four_plus_putt_percent(l20)
        pt_by_par = calc_putts_by_par_type(b8, courses_dict)
        putts_spark = [v for _, v in calc_putts_trend(all_rounds)]

        return render_template("stats/putting.html", **base_context(
            current_page="stats",
            putts_per_round=pt_rd_b8, pt_rd_delta=_delta(pt_rd_b8, pt_rd_l20, False),
            putts_per_gir=pt_gir_b8, pt_gir_delta=_delta(pt_gir_b8, pt_gir_l20, False),
            one_putt_pct=o1_b8, o1_delta=_delta(o1_b8, o1_l20, True, 1, "%"),
            two_putt_pct=o2_b8, o2_delta=_delta(o2_b8, o2_l20, True, 1, "%"),
            three_putt_pct=o3_b8, o3_delta=_delta(o3_b8, o3_l20, False, 1, "%"),
            four_plus_putt_pct=o4p_b8, o4p_delta=_delta(o4p_b8, o4p_l20, False, 1, "%"),
            putts_by_par=pt_by_par,
            putts_spark=putts_spark,
        ))

    @app.route("/stats/short-game")
    @login_required
    def stats_short_game():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        sc_b8 = calc_scramble_percent(b8, courses_dict)
        sc_l20 = calc_scramble_percent(l20, courses_dict)
        sc_by_dir = calc_scramble_by_miss_direction(b8, courses_dict)
        sc_by_par = calc_scramble_by_par_type(b8, courses_dict)
        scramble_spark = [v for _, v in calc_scramble_trend(all_rounds, courses_dict)]

        return render_template("stats/short-game.html", **base_context(
            current_page="stats",
            scramble_pct=sc_b8, sc_delta=_delta(sc_b8, sc_l20, True, 1, "%"),
            scramble_left=sc_by_dir.get("L"),
            scramble_right=sc_by_dir.get("R"),
            scramble_short=sc_by_dir.get("S"),
            scramble_long=sc_by_dir.get("LO"),
            scramble_par_3=sc_by_par.get(3),
            scramble_par_4=sc_by_par.get(4),
            scramble_par_5=sc_by_par.get(5),
            scramble_spark=scramble_spark,
        ))

    @app.route("/stats/momentum")
    @login_required
    def stats_momentum():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        momentum = calc_momentum_recovery(b8, courses_dict)
        after_bogey_avg = momentum.get("after_bogey_avg")
        recovery_rate = momentum.get("recovery_rate")

        bogey_free = 0
        for r in b8:
            if not r.holes:
                continue
            course = courses_dict.get(r.course)
            ch = course.holes if course else {}
            has_bogey = False
            for n, h in r.holes.items():
                par = ch.get(str(n), type("obj", (), {"par": None})()).par
                if h.gross and par and h.gross - par >= 1:
                    has_bogey = True
                    break
            if not has_bogey:
                bogey_free += 1

        opening_3 = []
        closing_3 = []
        for r in b8:
            if r.holes:
                course = courses_dict.get(r.course)
                ch = course.holes if course else {}
                sorted_nums = sorted(r.holes.keys(), key=int)
                for group, indices in [("opening", sorted_nums[:3]), ("closing", sorted_nums[-3:])]:
                    scores = []
                    for n in indices:
                        h = r.holes[n]
                        par = ch.get(str(n), type("obj", (), {"par": None})()).par
                        if h.gross and par:
                            scores.append(h.gross - par)
                    if scores:
                        avg = sum(scores) / len(scores)
                        if group == "opening":
                            opening_3.append(avg)
                        else:
                            closing_3.append(avg)

        opening_3_avg = sum(opening_3) / len(opening_3) if opening_3 else None
        closing_3_avg = sum(closing_3) / len(closing_3) if closing_3 else None

        return render_template("stats/momentum.html", **base_context(
            current_page="stats",
            after_bogey_avg=after_bogey_avg,
            recovery_rate=recovery_rate,
            bogey_free=bogey_free,
            opening_3_avg=opening_3_avg,
            closing_3_avg=closing_3_avg,
        ))

    @app.route("/stats/trends")
    @login_required
    def stats_trends():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()
        settings = get_settings()
        include_9hole = settings.get("include_9hole", True)

        scoring_t = calc_scoring_trend(all_rounds)
        fir_t = calc_fir_trend(all_rounds, courses_dict)
        gir_t = calc_gir_trend(all_rounds)
        putts_t = calc_putts_trend(all_rounds)
        scramble_t = calc_scramble_trend(all_rounds, courses_dict)
        hi_t = calc_handicap_trend(all_rounds, include_9hole)
        pth = calc_playing_to_handicap_rate(all_rounds, include_9hole)

        return render_template("stats/trends.html", **base_context(
            current_page="stats",
            scoring_trend=scoring_t,
            fir_trend=fir_t,
            gir_trend=gir_t,
            putts_trend=putts_t,
            scramble_trend=scramble_t,
            handicap_trend=hi_t,
            playing_to_handicap_rate=pth,
        ))

    @app.route("/stats/bests")
    @login_required
    def stats_bests():
        all_rounds, courses_dict, b8, l5, l10, l20 = _load_rounds()

        bests = calc_personal_bests(all_rounds, courses_dict)

        return render_template("stats/bests.html", **base_context(
            current_page="stats",
            best_gross=bests.get("best_gross"),
            best_gross_date=bests.get("best_gross_date"),
            best_diff=bests.get("best_diff"),
            best_diff_date=bests.get("best_diff_date"),
            most_fir=bests.get("most_fir"),
            most_fir_date=bests.get("most_fir_date"),
            most_gir=bests.get("most_gir"),
            most_gir_date=bests.get("most_gir_date"),
            fewest_putts=bests.get("fewest_putts"),
            fewest_putts_date=bests.get("fewest_putts_date"),
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
                generated_token = generate_password_reset_token(reset_user_id)
                token_url = url_for("reset_password", token=generated_token, _external=True)
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
