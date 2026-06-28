import logging
from datetime import date

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import (
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_slope_rating, save_round, delete_round,
    get_matches_for_user, link_round,
    recompute_all_handicaps,
)
from calc import (
    calc_round_dif, calc_handicap_index, calc_round_vs_par,
    calc_avg_vs_par, calc_round_vs_rating, calc_avg_vs_rating,
    calc_par_or_better_percent, calc_big_number_rate, calc_fir_percent,
    calc_gir_percent, calc_putts_per_round, calc_one_putt_percent,
    calc_two_putt_percent, calc_three_putt_percent, calc_scramble_percent,
    calc_scoring_avg_by_par_type, calc_penalties_per_round,
    calc_scoring_average,
    get_best_n_rounds, last_n_rounds,
    calc_course_handicap,
    calc_hole_scores,
)
from source.web.charts import sparkline_svg
from calc import per_round_hole_stats
from source.models import dict_to_round, dict_to_course
from source.plugin import fire_hook, _plugins
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context

_log = logging.getLogger("pinsheet")


def register_rounds_routes(app, csrf):
    @app.route("/rounds/new")
    @login_required
    def round_entry():
        today = date.today().isoformat()
        no_courses = len(get_courses()) == 0
        matches = get_matches_for_user(current_user.id)
        return render_template("round_entry.html", **base_context(
            current_page="round_entry",
            courses=get_courses(), today=today, no_courses=no_courses,
            matches=matches,
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
    @csrf.exempt
    def api_draft_round_put():
        save_round_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/round", methods=["DELETE"])
    @login_required
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
    @csrf.exempt
    def api_draft_course_put():
        save_course_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/course", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def api_draft_course_delete():
        clear_course_draft(current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/rounds", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_rounds_post():
        data = request.get_json()
        date_val = data.get("date", "")
        course_name = data.get("course", "")
        tees_name = data.get("tees", "")
        match_id = data.get("match_id")

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

        all_rounds_for_user = get_all_rounds_for_user()
        adjusted_gross = total_gross
        if data.get("entry_mode") != "score_only" and data.get("holes"):
            current_hi = calc_handicap_index(all_rounds_for_user, get_settings().get("include_9hole", True))
            if current_hi is not None:
                adj_hi = current_hi / 2 if holes_sel != "all" else current_hi
                course_holes = course.get("holes", {})
                if holes_sel != "all" and course_holes:
                    hole_nums = sorted(course_holes.keys(), key=int)
                    half = hole_nums[:9] if holes_sel == "front" else hole_nums[9:18]
                    played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
                else:
                    played_par = int(course.get("par", 0))
                course_handicap = calc_course_handicap(adj_hi, played_par, slope, rating)
                adjusted_total = 0
                for hole_num, hole_data in data["holes"].items():
                    hc_hole = course_holes.get(hole_num, {})
                    if hc_hole:
                        par = int(hc_hole.get("par", 0))
                        stroke_index = int(hc_hole.get("hole_index", 999))
                        gross = int(hole_data.get("gross", 0))
                        _, _, esc_gross = calc_hole_scores(stroke_index, course_handicap, par, gross)
                        adjusted_total += esc_gross
                    else:
                        adjusted_total += int(hole_data.get("gross", 0))
                adjusted_gross = adjusted_total

        differential = calc_round_dif(slope, adjusted_gross, rating)
        golf_round["differential"] = str(differential)

        golf_round_typed = dict_to_round(golf_round)
        all_rounds_for_user.insert(0, golf_round_typed)
        new_hi = calc_handicap_index(all_rounds_for_user, get_settings().get("include_9hole", True))
        if new_hi is not None:
            golf_round["computed_handicap"] = str(new_hi)
            golf_round_typed.computed_handicap = str(new_hi)

        round_id = save_round(golf_round, date_val, 0, current_user.id)
        fire_hook("on_round_saved", round_data=golf_round, user_id=current_user.id, db_path=app.config["DB_PATH"])
        index = 0

        if match_id and golf_round.get("computed_handicap"):
            try:
                match_id = int(match_id)
                hi = float(golf_round["computed_handicap"])
                adj_hi = hi / 2 if holes_sel != "all" else hi
                course_holes = course.get("holes", {})
                if holes_sel != "all" and course_holes:
                    if golf_round.get("holes"):
                        played_par = sum(int(course_holes.get(hn, {}).get("par", 0)) for hn in golf_round.get("holes", {}))
                    else:
                        hole_nums = sorted(course_holes.keys(), key=int)
                        half = hole_nums[:9] if holes_sel == "front" else hole_nums[9:18]
                        played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
                else:
                    played_par = int(course.get("par", 0))
                ch = calc_course_handicap(adj_hi, played_par, slope, rating)
                net = total_gross - ch
                link_round(match_id, current_user.id, round_id, float(net))
            except (ValueError, TypeError, Exception) as exc:
                _log.warning("match linking failed — %s", exc)

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
        tee_data = course.get("tees", {}).get(round_data.tees, {}) if round_data.tees else {}
        slope, rating = get_slope_rating(tee_data, round_data.holes_selection)

        rounds_before = [r for r in all_rounds_for_user
                         if r.date < round_data.date or (r.date == round_data.date and r.index < round_data.index)]
        hi_before = calc_handicap_index(rounds_before, get_settings().get("include_9hole", True))

        hole_nums_all = sorted(course_holes.keys(), key=int)
        if not hole_nums_all:
            total_par_course = 0
        elif round_data.holes_selection == "front":
            total_par_course = sum(int(course_holes[hn].get("par", 0)) for hn in hole_nums_all[:9])
        elif round_data.holes_selection == "back":
            total_par_course = sum(int(course_holes[hn].get("par", 0)) for hn in hole_nums_all[9:18])
        else:
            total_par_course = sum(int(course_holes[hn].get("par", 0)) for hn in hole_nums_all)

        course_handicap = None
        if hi_before is not None and slope:
            adj_hi = hi_before / 2 if round_data.holes_selection != "all" else hi_before
            course_handicap = calc_course_handicap(adj_hi, total_par_course, slope, rating)

        holes = []
        front_gross = back_gross = front_par = back_par = 0
        front_putts = back_putts = 0
        front_net = back_net = 0
        front_fir_hits = front_fir_eligible = 0
        back_fir_hits = back_fir_eligible = 0
        front_gir_hits = back_gir_hits = 0
        front_holes_cnt = back_holes_cnt = 0

        fir_hits = fir_eligible = 0
        gir_hits = 0
        total_putts = 0
        scramble_hits = scramble_opps = 0
        dist = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "worse": 0}
        net_dist = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "worse": 0}

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
            is_par3 = par == 3

            hole_index = int(course_holes.get(hn, {}).get("hole_index", 999))
            strokes = 0
            if course_handicap is not None:
                if hole_index <= course_handicap:
                    strokes += 1
                if hole_index <= course_handicap - 18:
                    strokes += 1
            net = gross - strokes
            net_diff = net - par
            yds = tee_data.get("yardages", {}).get(hn, "")

            if hole_num <= 9:
                front_gross += gross; front_par += par; front_putts += putts
                front_net += net; front_holes_cnt += 1
            else:
                back_gross += gross; back_par += par; back_putts += putts
                back_net += net; back_holes_cnt += 1

            if not is_par3:
                fir_eligible += 1
                if hole_num <= 9:
                    front_fir_eligible += 1
                else:
                    back_fir_eligible += 1
                if not fw or fw == "H":
                    fir_hits += 1
                    if hole_num <= 9:
                        front_fir_hits += 1
                    else:
                        back_fir_hits += 1

            if not gir or gir == "H":
                gir_hits += 1
                if hole_num <= 9:
                    front_gir_hits += 1
                else:
                    back_gir_hits += 1

            total_putts += putts

            if gir and gir != "H":
                scramble_opps += 1
                if gross <= par:
                    scramble_hits += 1

            diff_val = gross - par
            if diff_val <= -2:
                dist["eagle"] += 1
            elif diff_val == -1:
                dist["birdie"] += 1
            elif diff_val == 0:
                dist["par"] += 1
            elif diff_val == 1:
                dist["bogey"] += 1
            elif diff_val == 2:
                dist["double"] += 1
            else:
                dist["worse"] += 1

            if net_diff <= -2:
                net_dist["eagle"] += 1
            elif net_diff == -1:
                net_dist["birdie"] += 1
            elif net_diff == 0:
                net_dist["par"] += 1
            elif net_diff == 1:
                net_dist["bogey"] += 1
            elif net_diff == 2:
                net_dist["double"] += 1
            else:
                net_dist["worse"] += 1

            holes.append({
                "num": hole_num, "par": par,
                "gross": gross, "gross_diff": diff_val,
                "fw": fw, "gir": gir,
                "putts": putts, "penalties": pen,
                "is_par3": is_par3,
                "strokes": strokes, "net": net, "net_diff": net_diff,
                "yds": yds,
            })

        total_par = front_par + back_par
        total_gross = front_gross + back_gross
        total_holes = len(hole_nums)

        if entry_mode == "score_only":
            total_gross = int(round_data.total_gross) if round_data.total_gross else 0
            total_par = 0

        net_total = total_gross - course_handicap if (course_handicap is not None and entry_mode != "score_only") else None
        net_to_par = net_total - total_par if (net_total is not None and total_par) else None

        fir_pct = round(fir_hits / fir_eligible * 100, 1) if fir_eligible else 0
        gir_pct = round(gir_hits / total_holes * 100, 1) if total_holes else 0
        scr_pct = round(scramble_hits / scramble_opps * 100, 1) if scramble_opps else 0

        course_rounds = [r for r in all_rounds_for_user if r.course == round_data.course]
        course_avgs = None
        if course_rounds and len(course_rounds) >= 2:
            courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}
            cf = calc_fir_percent(course_rounds, courses_dict)
            cg = calc_gir_percent(course_rounds)
            cp = calc_putts_per_round(course_rounds)
            cs = calc_scramble_percent(course_rounds, courses_dict)
            csc = calc_scoring_average(course_rounds)
            course_avgs = {
                "fir_pct": round(cf, 1) if cf is not None else None,
                "gir_pct": round(cg, 1) if cg is not None else None,
                "putts": round(cp, 1) if cp is not None else None,
                "scr_pct": round(cs, 1) if cs is not None else None,
                "score": round(csc, 1) if csc is not None else None,
            }

        return render_template("round_detail.html", **base_context(
            round=round_data, course=course, holes=holes,
            entry_mode=entry_mode,
            rating=rating, slope=slope,
            front_nine={
                "gross": front_gross, "par": front_par, "putts": front_putts,
                "net_total": front_net, "net_to_par": front_net - front_par,
                "fir_hits": front_fir_hits, "fir_eligible": front_fir_eligible,
                "gir_hits": front_gir_hits,
                "holes_cnt": front_holes_cnt,
            },
            back_nine={
                "gross": back_gross, "par": back_par, "putts": back_putts,
                "net_total": back_net, "net_to_par": back_net - back_par,
                "fir_hits": back_fir_hits, "fir_eligible": back_fir_eligible,
                "gir_hits": back_gir_hits,
                "holes_cnt": back_holes_cnt,
            },
            total={
                "gross": total_gross, "par": total_par,
                "diff": total_gross - total_par if total_par else None,
                "net_diff": net_to_par, "net_total": net_total,
                "fir_hits": fir_hits, "fir_eligible": fir_eligible,
                "gir_hits": gir_hits, "total_holes": total_holes,
                "putts": total_putts,
                "scramble_hits": scramble_hits, "scramble_opps": scramble_opps,
            },
            dist=dist, net_dist=net_dist,
            round_stats={
                "fir_pct": fir_pct, "gir_pct": gir_pct,
                "putts": total_putts, "scr_pct": scr_pct,
            },
            hi_before=hi_before,
            course_handicap=course_handicap,
            course_avgs=course_avgs,
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
        if data.get("entry_mode") != "score_only" and data.get("holes"):
            rounds_before = [
                r for r in all_rounds_for_user
                if not (r.date == date and str(r.index) == str(index))
            ]
            current_hi = calc_handicap_index(rounds_before, get_settings().get("include_9hole", True))
            if current_hi is not None:
                adj_hi = current_hi / 2 if holes_sel != "all" else current_hi
                course_holes = course.get("holes", {})
                if holes_sel != "all" and course_holes:
                    hole_nums = sorted(course_holes.keys(), key=int)
                    half = hole_nums[:9] if holes_sel == "front" else hole_nums[9:18]
                    played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
                else:
                    played_par = int(course.get("par", 0))
                course_handicap = calc_course_handicap(adj_hi, played_par, slope, rating)
                adjusted_total = 0
                for hole_num, hole_data in data["holes"].items():
                    hc_hole = course_holes.get(hole_num, {})
                    if hc_hole:
                        par = int(hc_hole.get("par", 0))
                        stroke_index = int(hc_hole.get("hole_index", 999))
                        gross = int(hole_data.get("gross", 0))
                        _, _, esc_gross = calc_hole_scores(stroke_index, course_handicap, par, gross)
                        adjusted_total += esc_gross
                    else:
                        adjusted_total += int(hole_data.get("gross", 0))
                adjusted_gross = adjusted_total

        # --- Differential: lock-aware ---
        diff_override = data.get("differential_override")  # float or None
        send_override = "differential_override" in data
        client_locked = data.get("differential_locked", False)

        if send_override and diff_override is not None:
            # User explicitly provided a new manual value — lock it
            differential = round(float(diff_override), 1)
            golf_round["differential_locked"] = True
        elif send_override and diff_override is None:
            # User cleared the lock — recompute
            differential = calc_round_dif(slope, adjusted_gross, rating)
            golf_round["differential_locked"] = False
        elif old_round.differential_locked:
            # Preserve existing lock — don't recompute
            differential = float(old_round.differential)
            golf_round["differential_locked"] = True
        else:
            # Normal recompute
            differential = calc_round_dif(slope, adjusted_gross, rating)
            golf_round["differential_locked"] = False

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

        # Recompute cascade — update computed_handicap on all subsequent rounds
        recompute_all_handicaps()

        return jsonify({"ok": True, "differential": differential})

    @app.route("/api/rounds/<date>/<index>", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def api_rounds_delete(date, index):
        delete_round(date, index, current_user.id)
        return jsonify({"ok": True})
