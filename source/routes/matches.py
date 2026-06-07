from datetime import date
from flask import render_template, request, redirect, url_for, g
from flask_login import login_required, current_user
from store import (
    create_match, add_match_player, get_match, get_match_players, get_users,
)
from source.request_data import base_context, get_courses


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
        return render_template("match_detail.html", **base_context(
            current_page="matches", match=match, players=players,
        ))
