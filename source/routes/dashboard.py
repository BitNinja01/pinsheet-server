import json
from datetime import date, timedelta, datetime

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import get_users, get_user_by_id, save_settings
from calc import (
    calc_last_year_handicap, get_best_n_rounds,
    calc_handicap_values_in_range, calc_career_low_handicap,
    compute_stat_bundle, StatBundle, last_n_rounds, best_n_rounds,
)

from source.web.charts import sparkline_svg, make_chart_data
from source.routes.auth import requires_own_data
from calc import per_round_hole_stats
from source.calc.models import dict_to_course
from source.request_data import get_settings, get_courses, get_all_rounds_for_user


def register_dashboard_routes(app, limiter, csrf):
    @app.route("/")
    @login_required
    def dashboard():
        if not get_settings().get("welcome_shown"):
            return render_template("welcome.html", settings=get_settings(), all_users=get_users())
        include_9hole = get_settings().get("include_9hole", True)

        all_rounds = get_all_rounds_for_user()
        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}
        rounds = list(all_rounds)

        l20 = last_n_rounds(rounds, 20)
        b8 = best_n_rounds(rounds, 8)

        bundle = compute_stat_bundle(l20, b8, courses_dict, include_9hole)

        panels_list = ["handicap", "score", "fir", "gir", "putts", "scramble"]
        panels = {}
        for key in panels_list:
            p = bundle.panels[key]
            panels[key] = {
                "label": p.label,
                "value": f"{p.value:.1f}{p.suffix}" if p.value is not None else "--",
                "secondary": f"{p.secondary:.1f}{p.suffix}" if p.secondary is not None else "--",
                "higher_better": p.higher_better,
                "color": p.color,
                "blank_text": p.blank_text,
            }

        last_year_hi = calc_last_year_handicap(rounds, include_9hole)
        if last_year_hi is not None:
            panels["handicap"]["subtitle"] = f"1y {last_year_hi:.1f}"

        rounds_data = []
        for r in all_rounds[:20]:
            course = get_courses().get(r.course, {})
            total = r.total_gross
            par = course.get("par", 0)
            score_to_par = int(total) - int(par) if total and par and total != "0" else None
            raw_mode = r.entry_mode
            display_mode = "normal" if raw_mode == "detailed" else (raw_mode or "score_only")

            sparkline = sparkline_svg(r.holes)

            hs = per_round_hole_stats(r.holes, course.get("holes", {}))
            fir_display = hs["fir_display"]
            gir_display = hs["gir_display"]
            scr_display = hs["scr_display"]
            total_putts = hs["total_putts"]

            rounds_data.append({
                "date": r.date,
                "course": r.course,
                "tees": r.tees,
                "total": total,
                "score_to_par": score_to_par,
                "differential": r.differential,
                "index": r.index,
                "in_handicap": False,
                "entry_mode_display": display_mode,
                "sparkline": sparkline,
                "fir_display": fir_display,
                "gir_display": gir_display,
                "scr_display": scr_display,
                "putts": total_putts,
            })

        best_rounds = get_best_n_rounds(rounds, include_9hole)
        best_keys = {(r.date, r.index) for r in best_rounds}
        for rd in rounds_data:
            if (rd["date"], rd["index"]) in best_keys:
                rd["in_handicap"] = True

        all_hi_vals = []
        for r in all_rounds:
            ch = r.computed_handicap
            if ch and ch != "0":
                try:
                    all_hi_vals.append(float(ch))
                except ValueError:
                    pass

        cutoff_3m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        cutoff_12m = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        cutoff_2y = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

        chart_data = {
            "3M": make_chart_data(calc_handicap_values_in_range(all_rounds, cutoff_3m)),
            "12M": make_chart_data(calc_handicap_values_in_range(all_rounds, cutoff_12m)),
            "2Y": make_chart_data(calc_handicap_values_in_range(all_rounds, cutoff_2y)),
            "All": make_chart_data(all_hi_vals[::-1]),
        }

        chart = chart_data["12M"]
        chart_data_json = json.dumps(chart_data)

        now = datetime.now()
        start_month = now.month
        if start_month <= 2:
            season_name = "Winter"
        elif start_month <= 5:
            season_name = "Spring"
        elif start_month <= 8:
            season_name = "Summer"
        else:
            season_name = "Fall"
        yr = now.strftime("%y")
        n = min(len(all_rounds), 12) if all_rounds else 0
        season_label = f"{season_name} '{yr} · last {n} rounds"

        handicap_panel_val = panels.get("handicap", {}).get("value", "--")

        if handicap_panel_val and handicap_panel_val != "--":
            chart["label_v"] = handicap_panel_val
            chart["hero_value"] = handicap_panel_val

        hi_movement = None
        if handicap_panel_val and handicap_panel_val != "--":
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            prev_hi = None
            for r in all_rounds:
                if r.date <= thirty_days_ago and r.computed_handicap:
                    try:
                        prev_hi = float(r.computed_handicap)
                        break
                    except (ValueError, TypeError):
                        pass
            try:
                curr = float(handicap_panel_val)
                if prev_hi is not None:
                    diff = prev_hi - curr
                    arrow = "▼" if diff > 0 else "▲"
                    hi_movement = f"{arrow} {abs(diff):.1f} this month"
            except (ValueError, TypeError):
                pass

        career_low = calc_career_low_handicap(all_rounds)

        hi_insight = None
        if handicap_panel_val and handicap_panel_val != "--":
            try:
                curr = float(handicap_panel_val)
                eligible_20 = [r for r in all_rounds[:20] if not r.excluded and r.differential and r.differential != "0"]
                eligible_count = len(eligible_20)
                best_ids = {(r.date, r.index) for r in best_rounds}
                counting = sum(1 for r in eligible_20 if (r.date, r.index) in best_ids)
                hi_insight = f"{counting} of your last {eligible_count} rounds counted toward index."
                target = curr - 0.3
                if target > 0:
                    hi_insight += f" Two more at net par or better drops you below {target:.1f}."
            except (ValueError, TypeError):
                pass

        return render_template("dashboard.html", panels=panels, rounds=rounds_data,
                               last_year_hi=last_year_hi, settings=get_settings(),
                               current_page="dashboard",
                               season_label=season_label,
                               hi_movement=hi_movement, career_low=career_low, hi_insight=hi_insight,
                               chart=chart, chart_data_json=chart_data_json,
                               all_users=get_users())

    @app.route("/api/welcome", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_welcome_done():
        settings = get_settings()
        settings["welcome_shown"] = True
        save_settings(settings, current_user.id)
        return jsonify({"ok": True})
