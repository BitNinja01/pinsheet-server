import logging
from datetime import date

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import (
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_slope_rating, save_round, delete_round,
)
from calc import (
    calc_round_dif, calc_handicap_index, calc_round_vs_par,
    calc_avg_vs_par, calc_round_vs_rating, calc_avg_vs_rating,
    calc_par_or_better_percent, calc_big_number_rate, calc_fir_percent,
    calc_gir_percent, calc_putts_per_round, calc_one_putt_percent,
    calc_two_putt_percent, calc_three_putt_percent, calc_scramble_percent,
    calc_scoring_avg_by_par_type, calc_penalties_per_round,
    get_best_n_rounds, last_n_rounds,
    calc_course_handicap,
)
from source.web.charts import sparkline_svg
from source.routes.auth import requires_own_data
from calc import per_round_hole_stats
from source.models import dict_to_round, dict_to_course
from source.plugin import fire_hook, _plugins
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context

_log = logging.getLogger("pinsheet")


def register_rounds_routes(app, csrf):
    @app.route("/rounds/new")
    @login_required
    def round_entry():
        if not g.is_own_data:
            return "You can only enter data for yourself.", 403
        today = date.today().isoformat()
        no_courses = len(get_courses()) == 0
        return render_template("round_entry.html", **base_context(
            current_page="round_entry",
            courses=get_courses(), today=today, no_courses=no_courses,
        ))

    @app.route("/rounds")
    @login_required
    def rounds_list():
        settings = get_settings()
        all_rounds_for_user = get_all_rounds_for_user()
        include_9hole = settings.get("include_9hole", True)

        rounds_data = []
        for r in all_rounds_for_user:
            course = get_courses().get(r.course, {})
            total = r.total_gross
            course_holes = course.get("holes", {})
            if r.holes_selection != "all" and course_holes:
                if r.holes:
                    played_par = sum(int(course_holes.get(hn, {}).get("par", 0)) for hn in r.holes)
                else:
                    hole_nums = sorted(course_holes.keys(), key=int)
                    half = hole_nums[:9] if r.holes_selection == "front" else hole_nums[9:18]
                    played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
            else:
                played_par = int(course.get("par", 0))
            score_to_par = int(total) - played_par if total and played_par and total != "0" else None
            raw_mode = r.entry_mode
            display_mode = "normal" if raw_mode == "detailed" else (raw_mode or "score_only")

            net_score = None
            net_to_par = None
            if r.computed_handicap:
                try:
                    hi = float(r.computed_handicap)
                    tee_data = course.get("tees", {}).get(r.tees, {}) if r.tees else {}
                    slope, rating = get_slope_rating(tee_data, r.holes_selection)
                    if hi and slope:
                        adj_hi = hi / 2 if r.holes_selection != "all" else hi
                        ch = calc_course_handicap(adj_hi, played_par, slope, rating)
                        net_score = int(total) - ch
                        net_to_par = net_score - played_par
                except (ValueError, TypeError):
                    pass

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
                "net": net_score,
                "net_to_par": net_to_par,
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

        best_rounds = get_best_n_rounds(all_rounds_for_user, include_9hole)
        best_keys = {(r.date, r.index) for r in best_rounds}
        for rd in rounds_data:
            if (rd["date"], rd["index"]) in best_keys:
                rd["in_handicap"] = True

        return render_template("rounds_list.html", **base_context(
            current_page="rounds_list",
            rounds=rounds_data,
            settings=settings,
            include_9hole=include_9hole,
        ))

    @app.route("/api/drafts/round", methods=["GET"])
    @login_required
    def api_draft_round_get():
        draft = load_round_draft(current_user.id)
        return jsonify(draft or {})

    @app.route("/api/drafts/round", methods=["PUT"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_draft_round_put():
        save_round_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/round", methods=["DELETE"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_draft_round_delete():
        clear_round_draft(current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/course", methods=["GET"])
    @login_required
    def api_draft_course_get():
        draft = load_course_draft(current_user.id)
        return jsonify(draft or {})

    @app.route("/api/drafts/course", methods=["PUT"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_draft_course_put():
        save_course_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/course", methods=["DELETE"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_draft_course_delete():
        clear_course_draft(current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/rounds", methods=["POST"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_rounds_post():
        data = request.get_json()
        date_val = data.get("date", "")
        course_name = data.get("course", "")
        tees_name = data.get("tees", "")

        course = get_courses().get(course_name, {})
        tees = course.get("tees", {}).get(tees_name, {})

        holes_sel = data.get("holes_played", "18")
        if holes_sel == "front9":
            holes_sel = "front"
        elif holes_sel == "back9":
            holes_sel = "back"
        else:
            holes_sel = "all"

        slope, rating = get_slope_rating(tees, holes_sel)

        golf_round = {
            "date": date_val,
            "course": course_name,
            "tees": tees_name,
            "holes_played": data.get("holes_played", "18"),
            "holes_selection": holes_sel,
            "transport": data.get("transport", ""),
            "entry_mode": data.get("entry_mode", "detailed"),
            "notes": data.get("notes", ""),
            "holes": data.get("holes", {}),
            "gross_total": data.get("gross_total", ""),
        }

        total_gross = 0
        if data.get("entry_mode") == "score_only":
            total_gross = int(data.get("gross_total", "0"))
            golf_round["total_gross"] = str(total_gross)
        elif data.get("holes"):
            for h in data["holes"].values():
                gross = int(h.get("gross", 0))
                total_gross += gross
            golf_round["total_gross"] = str(total_gross)

        adjusted_gross = total_gross
        differential = calc_round_dif(slope, adjusted_gross, rating)
        golf_round["differential"] = str(differential)

        golf_round_typed = dict_to_round(golf_round)
        all_rounds_for_user = get_all_rounds_for_user()
        all_rounds_for_user.insert(0, golf_round_typed)
        new_hi = calc_handicap_index(all_rounds_for_user, get_settings().get("include_9hole", True))
        if new_hi is not None:
            golf_round["computed_handicap"] = str(new_hi)
            golf_round_typed.computed_handicap = str(new_hi)

        save_round(golf_round, date_val, 0, current_user.id)
        fire_hook("on_round_saved", round_data=golf_round, user_id=current_user.id, db_path=app.config["DB_PATH"])
        index = 0
        redirect_url = None
        for plugin in _plugins:
            fn = getattr(plugin, "post_save_redirect", None)
            if fn is not None:
                try:
                    url = fn(golf_round, current_user.id)
                    if url:
                        redirect_url = url
                        break
                except Exception as exc:
                    _log.warning("plugin %s: post_save_redirect() failed — %s", getattr(plugin, "plugin_info", {}).get("name", "?"), exc)

        return jsonify({"date": date_val, "index": index, "differential": differential, "redirect": redirect_url})

    @app.route("/rounds/<date>/<index>")
    @login_required
    def round_detail(date, index):
        all_rounds_for_user = get_all_rounds_for_user()
        round_data = None
        for r in all_rounds_for_user:
            if r.date == date and str(r.index) == str(index):
                round_data = r
                break
        if not round_data:
            return "Round not found", 404

        edit_mode = request.args.get("edit") == "1"
        course = get_courses().get(round_data.course, {})
        course_holes = course.get("holes", {})
        entry_mode = round_data.entry_mode

        holes = []
        front_gross = back_gross = front_par = back_par = 0
        front_putts = back_putts = 0
        hole_data = round_data.holes
        hole_nums = sorted(hole_data.keys(), key=lambda x: int(x))

        for hn in hole_nums:
            h = hole_data[hn]
            hole_num = int(hn)
            par = int(course_holes.get(hn, {}).get("par", 0))
            gross = h.gross
            putts = h.putts
            pen = h.penalties
            fw = h.fairway
            gir = h.gir

            if hole_num <= 9:
                front_gross += gross; front_par += par; front_putts += putts
            else:
                back_gross += gross; back_par += par; back_putts += putts

            holes.append({
                "num": hole_num, "par": par,
                "gross": gross, "gross_diff": gross - par if gross and par else None,
                "fw": fw, "gir": gir,
                "putts": putts, "penalties": pen,
                "is_par3": par == 3,
            })

        total_par = front_par + back_par
        total_gross = front_gross + back_gross

        if entry_mode == "score_only":
            total_gross = int(round_data.gross_total) if round_data.gross_total else 0

        return render_template("round_detail.html", **base_context(
            round=round_data, course=course, holes=holes,
            entry_mode=entry_mode,
            front_nine={"gross": front_gross, "par": front_par, "putts": front_putts},
            back_nine={"gross": back_gross, "par": back_par, "putts": back_putts},
            total={"gross": total_gross, "par": total_par,
                   "diff": total_gross - total_par if total_par else 0},
            edit_mode=edit_mode,
            courses=get_courses(),
        ))

    @app.route("/rounds/<date>/<index>/report")
    @login_required
    def report_card(date, index):
        all_rounds_for_user = get_all_rounds_for_user()
        this_round = None
        for r in all_rounds_for_user:
            if r.date == date and str(r.index) == str(index):
                this_round = r
                break
        if not this_round:
            return "Round not found", 404

        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}

        l20 = last_n_rounds(all_rounds_for_user, 20)
        if this_round.date not in [r.date for r in all_rounds_for_user[:20]]:
            l20.insert(0, this_round)
            l20 = l20[:20]

        rows = [
            ("Score vs Par", calc_round_vs_par(this_round, courses_dict), calc_avg_vs_par(l20, courses_dict), False, "", 1),
            ("Score vs Rating", calc_round_vs_rating(this_round, courses_dict), calc_avg_vs_rating(l20, courses_dict), False, "", 1),
            ("Par or Better %", calc_par_or_better_percent([this_round], courses_dict), calc_par_or_better_percent(l20, courses_dict), True, "%", 1),
            ("Blow-up Rate", calc_big_number_rate([this_round], courses_dict), calc_big_number_rate(l20, courses_dict), False, "%", 1),
            ("FIR %", calc_fir_percent([this_round], courses_dict), calc_fir_percent(l20, courses_dict), True, "%", 1),
            ("GIR %", calc_gir_percent([this_round]), calc_gir_percent(l20), True, "%", 1),
            ("Putts / Rnd", calc_putts_per_round([this_round]), calc_putts_per_round(l20), False, "", 1),
            ("1-Putt %", calc_one_putt_percent([this_round]), calc_one_putt_percent(l20), True, "%", 1),
            ("2-Putt %", calc_two_putt_percent([this_round]), calc_two_putt_percent(l20), True, "%", 1),
            ("3-Putt %", calc_three_putt_percent([this_round]), calc_three_putt_percent(l20), False, "%", 1),
            ("Scramble %", calc_scramble_percent([this_round], courses_dict), calc_scramble_percent(l20, courses_dict), True, "%", 1),
        ]

        par_this = calc_scoring_avg_by_par_type([this_round], courses_dict)
        par_l20 = calc_scoring_avg_by_par_type(l20, courses_dict)
        for p in [3, 4, 5]:
            rows.append((
                f"Par {p} Avg",
                par_this.get(p),
                par_l20.get(p),
                False, "", 2,
            ))

        rows.append(("Penalties / Rnd", calc_penalties_per_round([this_round]), calc_penalties_per_round(l20), False, "", 1))

        return render_template("report_card.html", **base_context(
            rows=rows, round=this_round,
        ))

    @app.route("/api/rounds/<date>/<index>", methods=["PUT"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_rounds_put(date, index):
        all_rounds_for_user = get_all_rounds_for_user()
        old_round = None
        for r in all_rounds_for_user:
            if r.date == date and str(r.index) == str(index):
                old_round = r
                break
        if not old_round:
            return jsonify({"error": "Round not found"}), 404

        data = request.get_json()
        course_name = data.get("course", "")
        tees_name = data.get("tees", "")
        course = get_courses().get(course_name, {})
        tees = course.get("tees", {}).get(tees_name, {})

        holes_sel = data.get("holes_played", "18")
        if holes_sel == "front9":
            holes_sel = "front"
        elif holes_sel == "back9":
            holes_sel = "back"
        else:
            holes_sel = "all"

        slope, rating = get_slope_rating(tees, holes_sel)

        golf_round = {
            "date": data.get("date", date),
            "course": course_name,
            "tees": tees_name,
            "holes_played": data.get("holes_played", "18"),
            "holes_selection": holes_sel,
            "transport": data.get("transport", ""),
            "entry_mode": data.get("entry_mode", "detailed"),
            "notes": data.get("notes", ""),
            "holes": data.get("holes", {}),
            "gross_total": data.get("gross_total", ""),
        }

        total_gross = 0
        if data.get("entry_mode") == "score_only":
            total_gross = int(data.get("gross_total", "0"))
            golf_round["total_gross"] = str(total_gross)
        elif data.get("holes"):
            for h in data["holes"].values():
                gross = int(h.get("gross", 0))
                total_gross += gross
            golf_round["total_gross"] = str(total_gross)

        adjusted_gross = total_gross
        differential = calc_round_dif(slope, adjusted_gross, rating)
        golf_round["differential"] = str(differential)

        if data.get("date", date) != date:
            delete_round(date, index, current_user.id)

        golf_round_typed = dict_to_round(golf_round)
        for i, r in enumerate(all_rounds_for_user):
            if r.date == date and str(r.index) == str(index):
                all_rounds_for_user[i] = golf_round_typed
                break
        new_hi = calc_handicap_index(all_rounds_for_user, get_settings().get("include_9hole", True))
        if new_hi is not None:
            golf_round["computed_handicap"] = str(new_hi)
            golf_round_typed.computed_handicap = str(new_hi)

        save_round(golf_round, data.get("date", date), int(index), current_user.id)
        fire_hook("on_round_saved", round_data=golf_round, user_id=current_user.id, db_path=app.config["DB_PATH"])
        return jsonify({"ok": True, "differential": differential})

    @app.route("/api/rounds/<date>/<index>", methods=["DELETE"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_rounds_delete(date, index):
        delete_round(date, index, current_user.id)
        return jsonify({"ok": True})
