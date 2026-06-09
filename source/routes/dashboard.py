import json
from datetime import date, timedelta, datetime

from flask import render_template, request, redirect, jsonify, g, current_app
from flask_login import login_required, current_user

from store import get_user_by_id, save_settings, get_slope_rating, get_all_matches, get_all_challenges, create_challenge, add_challenge_participant, get_challenge, get_challenge_participants, get_all_rounds, get_users as store_get_users, get_match_players, get_match_rounds, get_round_by_id
from calc import (
    calc_last_year_handicap, get_best_n_rounds,
    calc_handicap_values_in_range, calc_career_low_handicap,
    compute_stat_bundle, StatBundle, last_n_rounds, best_n_rounds,
    calc_course_handicap,
    compute_rankings, compute_board_meta, STAT_META, BOARD_STATS,
)

from source.web.charts import sparkline_svg, make_chart_data
from calc import per_round_hole_stats
from source.models import dict_to_course
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context
from source.web.catalog import STAT_CATALOG


def _featured_match():
    matches = get_all_matches()
    active = [m for m in matches if m.get("status") == "active"]
    if not active:
        return None
    m = active[0]
    players = get_match_players(m["id"])
    participants = []
    for p in players:
        participants.append({
            "name": p["user_name"],
            "net_total": round(float(p["total_net"]), 1) if p.get("total_net") else None,
            "round_count": p["round_count"],
        })
    match_rounds = get_match_rounds(m["id"])
    max_holes = 18
    completed = 0
    for mr in match_rounds:
        rd = get_round_by_id(mr["round_id"])
        if rd and rd.holes:
            completed += len(rd.holes)
    progress = min(completed / max_holes, 1.0) if max_holes else 0
    return {
        "id": m["id"],
        "course_name": m["course_name"],
        "date": m["date"],
        "status": m.get("status", "active"),
        "participants": participants,
        "progress": progress,
        "player_count": m.get("player_count", 0),
    }


def _featured_challenge():
    challenges = get_all_challenges()
    active = [c for c in challenges if c.get("status") == "active"]
    if not active:
        return None
    c = active[0]
    return {
        "id": c["id"],
        "title": c["title"],
        "stat_key": c["stat_key"],
        "start_date": c["start_date"],
        "end_date": c["end_date"],
        "participant_count": c.get("participant_count", 0),
        "status": c.get("status", "active"),
    }


def _build_profile_context():
    """Return template context dict for the profile/dashboard page."""
    if not get_settings().get("welcome_shown"):
        return None
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

        sparkline = sparkline_svg(r.holes)

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

    return {
        "panels": panels, "rounds": rounds_data,
        "last_year_hi": last_year_hi,
        "season_label": season_label,
        "hi_movement": hi_movement, "career_low": career_low, "hi_insight": hi_insight,
        "chart": chart, "chart_data_json": chart_data_json,
    }


def register_dashboard_routes(app, limiter, csrf):
    @app.route("/")
    @login_required
    def dashboard():
        if not get_settings().get("welcome_shown"):
            return render_template("welcome.html", **base_context())
        sort_key = request.args.get("sort", "handicap")
        sort_desc = request.args.get("desc", "0") == "1"
        date_start = request.args.get("from") or None
        date_end = request.args.get("to") or None
        rankings = compute_rankings(
            sort_key=sort_key,
            sort_desc=sort_desc,
            date_start=date_start,
            date_end=date_end,
        )
        board_meta = compute_board_meta(rankings, BOARD_STATS, STAT_META)

        you_rank = 0
        you_lead_stat = None
        for i, entry in enumerate(rankings, 1):
            if entry["user_id"] == current_user.id:
                you_rank = i
                you_lead_stat = entry["stats"].get("lead_stat")
                break

        now = datetime.now()
        month = now.month
        if month <= 2:
            season_name = "Winter"
        elif month <= 5:
            season_name = "Spring"
        elif month <= 8:
            season_name = "Summer"
        else:
            season_name = "Fall"
        season_label = f"{season_name} '{now.strftime('%y')}"

        return render_template(
            "dashboard_social.html",
            **base_context(
                current_page="dashboard",
                rankings=rankings,
                board_meta=board_meta,
                current_sort=sort_key,
                current_desc=sort_desc,
                date_from=date_start or "",
                date_to=date_end or "",
                stat_meta=STAT_META,
                board_stats=BOARD_STATS,
                matches=get_all_matches(),
                challenges=get_all_challenges(),
                featured_match=_featured_match(),
                featured_challenge=_featured_challenge(),
                you_rank=you_rank,
                you_lead_stat=you_lead_stat,
                season_label=season_label,
            ),
        )

    @app.route("/challenges/new", methods=["GET", "POST"])
    @login_required
    def challenge_new():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            participant_ids = request.form.getlist("participants")
            start_date = request.form.get("start_date", "").strip()
            end_date = request.form.get("end_date", "").strip()
            stat_key = request.form.get("stat_key", "").strip()

            all_users = store_get_users()
            valid_stat_keys = {s["key"] for s in STAT_CATALOG}

            if not title:
                return render_template("challenge_new.html", **base_context(
                    current_page="dashboard", users=all_users,
                    today=date.today().isoformat(), stat_catalog=STAT_CATALOG,
                    error="Title is required.",
                ))
            if len(participant_ids) < 2:
                return render_template("challenge_new.html", **base_context(
                    current_page="dashboard", users=all_users,
                    today=date.today().isoformat(), stat_catalog=STAT_CATALOG,
                    error="At least 2 participants are required.",
                ))
            if not start_date or not end_date:
                return render_template("challenge_new.html", **base_context(
                    current_page="dashboard", users=all_users,
                    today=date.today().isoformat(), stat_catalog=STAT_CATALOG,
                    error="Start and end dates are required.",
                ))
            if start_date > end_date:
                return render_template("challenge_new.html", **base_context(
                    current_page="dashboard", users=all_users,
                    today=date.today().isoformat(), stat_catalog=STAT_CATALOG,
                    error="End date must be after start date.",
                ))
            if stat_key not in valid_stat_keys:
                return render_template("challenge_new.html", **base_context(
                    current_page="dashboard", users=all_users,
                    today=date.today().isoformat(), stat_catalog=STAT_CATALOG,
                    error="Invalid stat selected.",
                ))

            challenge_id = create_challenge(
                created_by=current_user.id,
                title=title,
                stat_key=stat_key,
                start_date=start_date,
                end_date=end_date,
            )
            for uid_str in participant_ids:
                add_challenge_participant(challenge_id, int(uid_str))
            return redirect(f"/challenges/{challenge_id}")

        return render_template("challenge_new.html", **base_context(
            current_page="dashboard",
            users=store_get_users(),
            today=date.today().isoformat(),
            stat_catalog=STAT_CATALOG,
        ))

    @app.route("/profile")
    @login_required
    def profile():
        ctx = _build_profile_context()
        if ctx is None:
            return render_template("welcome.html", **base_context())
        return render_template("dashboard.html", **base_context(current_page="profile", **ctx))

    @app.route("/challenges/<int:challenge_id>")
    @login_required
    def challenge_detail(challenge_id):
        challenge = get_challenge(challenge_id)
        if not challenge:
            return "Challenge not found.", 404
        participant_ids = get_challenge_participants(challenge_id)
        all_users = store_get_users()
        user_lookup = {u["id"]: u for u in all_users}
        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}
        include_9hole = get_settings().get("include_9hole", True)
        stat_entry = next((s for s in STAT_CATALOG if s["key"] == challenge["stat_key"]), {})
        fn_primary = stat_entry.get("fn_primary")
        higher_better = stat_entry.get("higher_better", True)

        leaderboard = []
        for uid in participant_ids:
            user = user_lookup.get(uid, {"display_name": f"User #{uid}"})
            rounds = get_all_rounds(uid)
            scoped = [
                r for r in rounds
                if r.date >= challenge["start_date"] and r.date <= challenge["end_date"]
            ]
            value = None
            round_count = len(scoped)
            if scoped and fn_primary:
                try:
                    val = fn_primary(scoped, scoped, courses_dict, include_9hole)
                    if val is not None:
                        value = round(val, 1)
                except Exception:
                    pass
            leaderboard.append({
                "user_id": uid,
                "display_name": user.get("display_name", f"User #{uid}"),
                "value": value,
                "round_count": round_count,
            })

        non_none = [x for x in leaderboard if x["value"] is not None]
        none_vals = [x for x in leaderboard if x["value"] is None]
        non_none.sort(key=lambda x: x["value"], reverse=higher_better)
        leaderboard = non_none + none_vals

        if leaderboard and leaderboard[0]["value"] is not None:
            leaderboard[0]["is_leader"] = True

        return render_template("challenge_detail.html", **base_context(
            current_page="dashboard",
            challenge=challenge,
            leaderboard=leaderboard,
            stat_entry=stat_entry,
        ))

    @app.route("/api/welcome", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_welcome_done():
        settings = get_settings()
        settings["welcome_shown"] = True
        save_settings(settings, current_user.id)
        return jsonify({"ok": True})
