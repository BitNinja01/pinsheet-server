import json
from datetime import date, timedelta, datetime

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import get_courses, get_all_rounds, get_users, get_user_by_id, save_settings
from calc import calc_last_year_handicap, get_best_n_rounds
from web.catalog import STAT_CATALOG, DEFAULT_DASHBOARD_STATS

from source._helpers import _last_n_rounds, _best_n_rounds, _make_chart_data, requires_own_data, sparkline_svg, per_round_hole_stats
from source.calc.models import dict_to_round, dict_to_course


def register_dashboard_routes(app, limiter, csrf):
    @app.route("/")
    @login_required
    def dashboard():
        if not g.settings.get("welcome_shown"):
            return render_template("welcome.html", settings=g.settings, all_users=get_users())
        include_9hole = g.settings.get("include_9hole", True)

        rounds = [dict_to_round(r) for r in g.all_rounds]
        courses_dict = {name: dict_to_course(name, d) for name, d in g.courses.items()}

        l20 = _last_n_rounds(rounds, courses_dict, 20)
        b8 = _best_n_rounds(rounds, courses_dict, 8)

        panels = {}
        for stat_def in STAT_CATALOG:
            key = stat_def["key"]
            if key not in DEFAULT_DASHBOARD_STATS:
                continue
            primary = stat_def["fn_primary"](l20, b8, courses_dict, include_9hole)
            secondary = stat_def["fn_secondary"](l20, b8, courses_dict, include_9hole)
            panels[key] = {
                "label": stat_def["label"],
                "value": f"{primary:.1f}{stat_def['suffix']}" if primary is not None else "--",
                "secondary": f"{secondary:.1f}{stat_def['suffix']}" if secondary is not None else "--",
                "higher_better": stat_def["higher_better"],
                "color": f"rgb({stat_def['color'][0]},{stat_def['color'][1]},{stat_def['color'][2]})",
                "blank_text": stat_def["blank_text"],
            }

        last_year_hi = calc_last_year_handicap(rounds, include_9hole)
        if last_year_hi is not None:
            panels["handicap"]["subtitle"] = f"1y {last_year_hi:.1f}"

        rounds_data = []
        for r in g.all_rounds[:20]:
            course = g.courses.get(r.get("course", ""), {})
            total = r.get("total_gross", "")
            par = course.get("par", 0)
            score_to_par = int(total) - int(par) if total and par and total != "0" else None
            raw_mode = r.get("entry_mode")
            display_mode = "normal" if raw_mode == "detailed" else (raw_mode or "score_only")

            sparkline = sparkline_svg(r.get("holes"))

            hs = per_round_hole_stats(r.get("holes") or {}, course.get("holes", {}))
            fir_display = hs["fir_display"]
            gir_display = hs["gir_display"]
            scr_display = hs["scr_display"]
            total_putts = hs["total_putts"]

            rounds_data.append({
                "date": r.get("date", ""),
                "course": r.get("course", ""),
                "tees": r.get("tees", ""),
                "total": total,
                "score_to_par": score_to_par,
                "differential": r.get("differential", ""),
                "index": r.get("index", 0),
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
        for r in g.all_rounds:
            ch = r.get("computed_handicap")
            if ch and ch != "0":
                try:
                    all_hi_vals.append(float(ch))
                except ValueError:
                    pass

        cutoff_3m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        cutoff_12m = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        cutoff_2y = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

        def _get_hi_for_range(cutoff):
            vals = []
            for r in g.all_rounds:
                if r.get("date", "") < cutoff:
                    continue
                ch = r.get("computed_handicap")
                if ch and ch != "0":
                    try:
                        vals.append(float(ch))
                    except ValueError:
                        pass
            vals.reverse()
            return vals

        chart_data = {
            "3M": _make_chart_data(_get_hi_for_range(cutoff_3m)),
            "12M": _make_chart_data(_get_hi_for_range(cutoff_12m)),
            "2Y": _make_chart_data(_get_hi_for_range(cutoff_2y)),
            "All": _make_chart_data(all_hi_vals[::-1]),
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
        n = min(len(g.all_rounds), 12) if g.all_rounds else 0
        season_label = f"{season_name} '{yr} · last {n} rounds"

        handicap_panel_val = panels.get("handicap", {}).get("value", "--")

        if handicap_panel_val and handicap_panel_val != "--":
            chart["label_v"] = handicap_panel_val
            chart["hero_value"] = handicap_panel_val

        hi_movement = None
        if handicap_panel_val and handicap_panel_val != "--":
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            prev_hi = None
            for r in g.all_rounds:
                if r.get("date", "") <= thirty_days_ago and r.get("computed_handicap"):
                    try:
                        prev_hi = float(r["computed_handicap"])
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

        career_low = None
        best_hi = 999.9
        for r in g.all_rounds:
            if r.get("excluded"):
                continue
            ch = r.get("computed_handicap")
            if ch and ch not in ("0", "0.0", "--"):
                try:
                    v = float(ch)
                    if 0 < v < best_hi:
                        best_hi = v
                except (ValueError, TypeError):
                    pass
        if best_hi < 999.0:
            career_low = str(round(best_hi, 1))

        hi_insight = None
        if handicap_panel_val and handicap_panel_val != "--":
            try:
                curr = float(handicap_panel_val)
                eligible_20 = [r for r in g.all_rounds[:20] if not r.get("excluded") and r.get("differential") and r["differential"] != "0"]
                eligible_count = len(eligible_20)
                best_ids = {(r.date, r.index) for r in best_rounds}
                counting = sum(1 for r in eligible_20 if (r.get("date"), r.get("index")) in best_ids)
                hi_insight = f"{counting} of your last {eligible_count} rounds counted toward index."
                target = curr - 0.3
                if target > 0:
                    hi_insight += f" Two more at net par or better drops you below {target:.1f}."
            except (ValueError, TypeError):
                pass

        return render_template("dashboard.html", panels=panels, rounds=rounds_data,
                               last_year_hi=last_year_hi, settings=g.settings,
                               current_page="dashboard",
                               season_label=season_label,
                               hi_movement=hi_movement, career_low=career_low, hi_insight=hi_insight,
                               chart=chart, chart_data_json=chart_data_json,
                               all_users=get_users())

    @app.route("/api/welcome", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_welcome_done():
        g.settings["welcome_shown"] = True
        save_settings(g.settings, current_user.id)
        return jsonify({"ok": True})
