from datetime import date
from flask import render_template, request, redirect, url_for, g
from flask_login import login_required, current_user
from store import (
    create_match, add_match_player, get_match, get_match_players,
    get_match_rounds, get_round_by_id, get_users, get_all_rounds,
    get_slope_rating, link_round,
)
from source.request_data import base_context, get_courses
from calc import per_round_hole_stats, calc_course_handicap


def _build_round_details(match_rounds):
    courses_dict = get_courses()
    details = []
    for mr in match_rounds:
        rd = get_round_by_id(mr["round_id"])
        if not rd:
            continue
        course_data = courses_dict.get(rd.course, {})
        hs = per_round_hole_stats(rd.holes, course_data.get("holes", {})) if course_data else {}
        gross = int(rd.total_gross) if rd.total_gross else 0
        net = int(mr["net"]) if mr["net"] else 0
        score_to_par = None
        if course_data and gross:
            played_par = int(course_data.get("par", 72))
            score_to_par = gross - played_par
        details.append({
            "user_id": mr["user_id"],
            "user_name": mr["user_name"],
            "round_id": mr["round_id"],
            "gross": gross,
            "net": net,
            "fir_display": hs.get("fir_display", "--"),
            "gir_display": hs.get("gir_display", "--"),
            "putts": hs.get("total_putts", "--"),
            "score_to_par": score_to_par,
            "date": rd.date,
            "course": rd.course,
        })
    return details


def _played_par_for_round(round_data, course_data):
    course_holes = course_data.get("holes", {})
    if round_data.holes_selection != "all" and course_holes:
        if round_data.holes:
            return sum(int(course_holes.get(hn, {}).get("par", 0)) for hn in round_data.holes)
        hole_nums = sorted(course_holes.keys(), key=int)
        half = hole_nums[:9] if round_data.holes_selection == "front" else hole_nums[9:18]
        return sum(int(course_holes[hn].get("par", 0)) for hn in half)
    return int(course_data.get("par", 0))


def register_matches_routes(app):
    @app.route("/matches/new", methods=["GET", "POST"])
    @login_required
    def match_new():
        if request.method == "POST":
            course_name = request.form.get("course", "").strip()
            match_date = request.form.get("date", "").strip()
            participant_ids = request.form.getlist("participants")
            if not course_name:
                return render_template("match_new.html", **base_context(
                    current_page="matches", courses=get_courses(),
                    users=get_users(), today=date.today().isoformat(),
                    error="Course is required.",
                ))
            if not match_date:
                return render_template("match_new.html", **base_context(
                    current_page="matches", courses=get_courses(),
                    users=get_users(), today=date.today().isoformat(),
                    error="Date is required.",
                ))
            if len(participant_ids) < 2:
                return render_template("match_new.html", **base_context(
                    current_page="matches", courses=get_courses(),
                    users=get_users(), today=date.today().isoformat(),
                    error="At least 2 participants are required.",
                ))
            match_id = create_match(
                created_by=current_user.id,
                course_name=course_name,
                date=match_date,
            )
            for uid_str in participant_ids:
                add_match_player(match_id, int(uid_str))
            return redirect(url_for("match_detail", match_id=match_id))
        return render_template("match_new.html", **base_context(
            current_page="matches", courses=get_courses(),
            users=get_users(), today=date.today().isoformat(),
        ))

    @app.route("/matches/<int:match_id>")
    @login_required
    def match_detail(match_id):
        match = get_match(match_id)
        if not match:
            return "Match not found.", 404
        players = get_match_players(match_id)
        match_rounds = get_match_rounds(match_id)
        round_details = _build_round_details(match_rounds)
        is_participant = any(p["user_id"] == current_user.id for p in players)
        if players:
            min_net = min(p["total_net"] for p in players)
            for p in players:
                p["is_winner"] = p["total_net"] == min_net and p["round_count"] > 0
        player_rounds = {}
        for rd in round_details:
            player_rounds.setdefault(rd["user_id"], []).append(rd)
        return render_template("match_detail.html", **base_context(
            current_page="matches", match=match, players=players,
            round_details=round_details, player_rounds=player_rounds,
            is_participant=is_participant,
        ))

    @app.route("/matches/<int:match_id>/link-round", methods=["GET", "POST"])
    @login_required
    def match_link_round(match_id):
        match = get_match(match_id)
        if not match:
            return "Match not found.", 404
        players = get_match_players(match_id)
        if current_user.id not in [p["user_id"] for p in players]:
            return "You are not a participant in this match.", 403

        linked_ids = {mr["round_id"] for mr in get_match_rounds(match_id)}
        all_rounds = get_all_rounds(current_user.id)
        courses_dict = get_courses()

        if request.method == "POST":
            round_id = request.form.get("round_id")
            if not round_id:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match,
                    unlinked=[], error="Please select a round.",
                ))
            round_id = int(round_id)
            if round_id in linked_ids:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match,
                    unlinked=[], error="This round is already linked.",
                ))
            round_data = get_round_by_id(round_id)
            if not round_data or round_data.user_id != current_user.id:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match,
                    unlinked=[], error="Round not found.",
                ))
            if not round_data.computed_handicap:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match,
                    unlinked=[], error="Cannot link a round without a handicap index.",
                ))

            gross = int(round_data.total_gross)
            hi = float(round_data.computed_handicap)
            adj_hi = hi / 2 if round_data.holes_selection != "all" else hi
            course_data = courses_dict.get(round_data.course, {})
            tee_data = course_data.get("tees", {}).get(round_data.tees, {}) if round_data.tees else {}
            slope, rating = get_slope_rating(tee_data, round_data.holes_selection)
            played_par = _played_par_for_round(round_data, course_data)
            ch = calc_course_handicap(adj_hi, played_par, slope, rating)
            net = gross - ch

            link_round(match_id, current_user.id, round_id, float(net))
            return redirect(url_for("match_detail", match_id=match_id))

        unlinked = []
        for rd in all_rounds:
            if rd.id in linked_ids:
                continue
            if not rd.computed_handicap:
                continue
            course_data = courses_dict.get(rd.course, {})
            gross = int(rd.total_gross) if rd.total_gross else 0
            played_par = _played_par_for_round(rd, course_data)
            score_to_par = gross - played_par if gross and played_par else None
            tee_data = course_data.get("tees", {}).get(rd.tees, {}) if rd.tees else {}
            slope, rating = get_slope_rating(tee_data, rd.holes_selection)
            hi = float(rd.computed_handicap)
            adj_hi = hi / 2 if rd.holes_selection != "all" else hi
            ch = calc_course_handicap(adj_hi, played_par, slope, rating)
            net = gross - ch

            unlinked.append({
                "round_id": rd.id,
                "date": rd.date,
                "course": rd.course,
                "tees": rd.tees,
                "gross": gross,
                "score_to_par": score_to_par,
                "net": net,
            })

        return render_template("match_link_round.html", **base_context(
            current_page="matches", match=match, unlinked=unlinked,
        ))
