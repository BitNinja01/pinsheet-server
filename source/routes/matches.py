from datetime import date
from flask import render_template, request, redirect, url_for, g
from flask_login import login_required, current_user
from store import (
    create_match, add_match_player, get_match, get_match_players,
    get_match_rounds, get_round_by_id, get_users,
)
from source.request_data import base_context, get_courses
from calc import per_round_hole_stats


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


def register_matches_routes(app):
    @app.route("/matches/new", methods=["GET", "POST"])
    @login_required
    def match_new():
        if not g.is_own_data:
            return "You can only create matches for yourself.", 403
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
        ))
