import logging
from datetime import date

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import (
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_slope_rating, save_round, delete_round, get_users,
)
from calc import (
    calc_round_dif, calc_handicap_index, calc_round_vs_par,
    calc_avg_vs_par, calc_round_vs_rating, calc_avg_vs_rating,
    calc_par_or_better_percent, calc_big_number_rate, calc_fir_percent,
    calc_gir_percent, calc_putts_per_round, calc_one_putt_percent,
    calc_two_putt_percent, calc_three_putt_percent, calc_scramble_percent,
    calc_scoring_avg_by_par_type, calc_penalties_per_round,
    get_best_n_rounds,
)
from source._helpers import requires_own_data
from source.plugin import fire_hook, _plugins

_log = logging.getLogger("pinsheet")


def register_rounds_routes(app):
    @app.route("/rounds/new")
    @login_required
    def round_entry():
        if not g.is_own_data:
            return "You can only enter data for yourself.", 403
        today = date.today().isoformat()
        no_courses = len(g.courses) == 0
        return render_template("round_entry.html", settings=g.settings, courses=g.courses, today=today, no_courses=no_courses, current_page="round_entry", all_users=get_users())

    @app.route("/rounds")
    @login_required
    def rounds_list():
        include_9hole = g.settings.get("include_9hole", True)

        rounds_data = []
        for r in g.all_rounds:
            course = g.courses.get(r.get("course", ""), {})
            total = r.get("total_gross", "")
            par = course.get("par", 0)
            score_to_par = int(total) - int(par) if total and par and total != "0" else None
            raw_mode = r.get("entry_mode")
            display_mode = "normal" if raw_mode == "detailed" else (raw_mode or "score_only")

            sparkline = None
            holes_raw = r.get("holes")
            if holes_raw:
                sorted_nums = sorted(holes_raw.keys(), key=lambda x: int(x))
                scores = []
                for hn in sorted_nums:
                    gv = holes_raw[hn].get("gross")
                    if gv:
                        scores.append(int(gv))
                if len(scores) >= 2:
                    lo, hi = min(scores), max(scores)
                    rng = hi - lo if hi != lo else 1
                    sp_w, sp_h, sp_pad = 210, 28, 2
                    iw = sp_w - sp_pad * 2
                    ih = sp_h - sp_pad * 2
                    n = len(scores) - 1
                    pts = []
                    for j, s in enumerate(scores):
                        pts.append((
                            sp_pad + (j / n) * iw,
                            sp_pad + (1 - (s - lo) / rng) * ih,
                        ))
                    path = " ".join(
                        f"{'M' if j == 0 else 'L'}{x:.1f} {y:.1f}"
                        for j, (x, y) in enumerate(pts)
                    )
                    fx, fy = pts[-1]
                    sparkline = {
                        "path": path,
                        "final_x": f"{fx:.1f}",
                        "final_y": f"{fy:.1f}",
                    }

            fir_display = None
            gir_display = None
            scr_display = None
            total_putts = None
            if r.get("holes"):
                holes = r["holes"]
                fir_hit = fir_attempts = 0
                gir_hit = gir_total = 0
                scr_updown = scr_opps = 0
                total_putts = 0
                course_holes_data = course.get("holes", {})
                for hn, h in holes.items():
                    fw = h.get("fairway", "")
                    if fw and fw != "N":
                        fir_attempts += 1
                        if fw == "H":
                            fir_hit += 1
                    gi = h.get("gir", "")
                    if gi:
                        gir_total += 1
                        if gi == "H":
                            gir_hit += 1
                        if gi != "H":
                            scr_opps += 1
                            try:
                                hole_par = int(course_holes_data.get(hn, {}).get("par", 99))
                                if int(h.get("gross", 99)) <= hole_par:
                                    scr_updown += 1
                            except (ValueError, TypeError):
                                pass
                    try:
                        total_putts += int(h.get("putts", 0) or 0)
                    except (ValueError, TypeError):
                        pass
                if fir_attempts > 0:
                    fir_display = f"{fir_hit}/{fir_attempts}"
                if gir_total > 0:
                    gir_display = f"{gir_hit}/{gir_total}"
                if scr_opps > 0:
                    scr_display = f"{scr_updown}/{scr_opps}"

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

        best_rounds = get_best_n_rounds(g.all_rounds, include_9hole)
        best_keys = {(r.get("date", ""), r.get("index", 0)) for r in best_rounds}
        for rd in rounds_data:
            if (rd["date"], rd["index"]) in best_keys:
                rd["in_handicap"] = True

        return render_template("rounds_list.html", rounds=rounds_data,
                               settings=g.settings, all_users=get_users(),
                               include_9hole=include_9hole,
                               current_page="rounds_list")

    @app.route("/api/drafts/round", methods=["GET"])
    @login_required
    def api_draft_round_get():
        draft = load_round_draft(current_user.id)
        return jsonify(draft or {})

    @app.route("/api/drafts/round", methods=["PUT"])
    @login_required
    @requires_own_data
    def api_draft_round_put():
        save_round_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/round", methods=["DELETE"])
    @login_required
    @requires_own_data
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
    def api_draft_course_put():
        save_course_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/course", methods=["DELETE"])
    @login_required
    @requires_own_data
    def api_draft_course_delete():
        clear_course_draft(current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/rounds", methods=["POST"])
    @login_required
    @requires_own_data
    def api_rounds_post():
        data = request.get_json()
        date_val = data.get("date", "")
        course_name = data.get("course", "")
        tees_name = data.get("tees", "")

        course = g.courses.get(course_name, {})
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

        g.all_rounds.insert(0, golf_round)
        new_hi = calc_handicap_index(g.all_rounds, g.settings.get("include_9hole", True))
        if new_hi is not None:
            golf_round["computed_handicap"] = str(new_hi)

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
        round_data = None
        for r in g.all_rounds:
            if r.get("date") == date and str(r.get("index")) == str(index):
                round_data = r
                break
        if not round_data:
            return "Round not found", 404

        course = g.courses.get(round_data.get("course", ""), {})
        course_holes = course.get("holes", {})
        entry_mode = round_data.get("entry_mode", "detailed")

        holes = []
        front_gross = back_gross = front_par = back_par = 0
        front_putts = back_putts = 0
        hole_data = round_data.get("holes", {})
        hole_nums = sorted(hole_data.keys(), key=lambda x: int(x))

        for hn in hole_nums:
            h = hole_data[hn]
            hole_num = int(hn)
            par = int(course_holes.get(hn, {}).get("par", 0))
            gross = int(h.get("gross", 0)) if h.get("gross") else 0
            putts = int(h.get("putts", 0)) if h.get("putts") else 0
            pen = int(h.get("penalties", 0)) if h.get("penalties") else 0
            fw = h.get("fairway", "")
            gir = h.get("gir", "")

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
            total_gross = int(round_data.get("gross_total", 0)) if round_data.get("gross_total") else 0

        return render_template("round_detail.html",
            round=round_data, course=course, holes=holes,
            entry_mode=entry_mode,
            front_nine={"gross": front_gross, "par": front_par, "putts": front_putts},
            back_nine={"gross": back_gross, "par": back_par, "putts": back_putts},
            total={"gross": total_gross, "par": total_par,
                   "diff": total_gross - total_par if total_par else 0},
            settings=g.settings,
            all_users=get_users(),
        )

    @app.route("/rounds/<date>/<index>/report")
    @login_required
    def report_card(date, index):
        this_round = None
        for r in g.all_rounds:
            if r.get("date") == date and str(r.get("index")) == str(index):
                this_round = r
                break
        if not this_round:
            return "Round not found", 404

        l20 = [r for r in g.all_rounds[:20] if not r.get("excluded")]
        if this_round not in l20:
            l20.insert(0, this_round)
            l20 = l20[:20]

        rows = [
            ("Score vs Par", calc_round_vs_par(this_round, g.courses), calc_avg_vs_par(l20, g.courses), False, "", 1),
            ("Score vs Rating", calc_round_vs_rating(this_round, g.courses), calc_avg_vs_rating(l20, g.courses), False, "", 1),
            ("Par or Better %", calc_par_or_better_percent([this_round], g.courses), calc_par_or_better_percent(l20, g.courses), True, "%", 1),
            ("Blow-up Rate", calc_big_number_rate([this_round], g.courses), calc_big_number_rate(l20, g.courses), False, "%", 1),
            ("FIR %", calc_fir_percent([this_round], g.courses), calc_fir_percent(l20, g.courses), True, "%", 1),
            ("GIR %", calc_gir_percent([this_round]), calc_gir_percent(l20), True, "%", 1),
            ("Putts / Rnd", calc_putts_per_round([this_round]), calc_putts_per_round(l20), False, "", 1),
            ("1-Putt %", calc_one_putt_percent([this_round]), calc_one_putt_percent(l20), True, "%", 1),
            ("2-Putt %", calc_two_putt_percent([this_round]), calc_two_putt_percent(l20), True, "%", 1),
            ("3-Putt %", calc_three_putt_percent([this_round]), calc_three_putt_percent(l20), False, "%", 1),
            ("Scramble %", calc_scramble_percent([this_round], g.courses), calc_scramble_percent(l20, g.courses), True, "%", 1),
        ]

        par_this = calc_scoring_avg_by_par_type([this_round], g.courses)
        par_l20 = calc_scoring_avg_by_par_type(l20, g.courses)
        for p in [3, 4, 5]:
            rows.append((
                f"Par {p} Avg",
                par_this.get(p),
                par_l20.get(p),
                False, "", 2,
            ))

        rows.append(("Penalties / Rnd", calc_penalties_per_round([this_round]), calc_penalties_per_round(l20), False, "", 1))

        return render_template("report_card.html", rows=rows, round=this_round, settings=g.settings, all_users=get_users())

    @app.route("/api/rounds/<date>/<index>", methods=["DELETE"])
    @login_required
    @requires_own_data
    def api_rounds_delete(date, index):
        delete_round(date, index, current_user.id)
        return jsonify({"ok": True})
