from datetime import date
from flask import render_template, request, redirect, url_for, g
from flask_login import login_required, current_user
from auth_keys import require_permission
from store import (
    create_match, add_match_player, get_match, get_match_players,
    get_match_rounds, get_round_by_id, get_users, get_all_rounds,
    get_slope_rating, link_round,
)
from source.request_data import base_context, get_courses
from calc import per_round_hole_stats, calc_course_handicap, calc_playing_handicap
from calc import WHS_HANDICAP_ALLOWANCES

# WHS Appendix C: human-readable labels for the WHS_HANDICAP_ALLOWANCES keys,
# in display order for the match-format selector on /matches/new. The
# dict/select order intentionally mirrors WHS_HANDICAP_ALLOWANCES's insertion
# order so the constant stays the single source of truth for both the
# percentage AND (via this label map) the option set -- adding a new format
# to WHS_HANDICAP_ALLOWANCES only requires adding its label here too.
MATCH_FORMAT_LABELS = {
    "individual_match": "Individual match play (100%)",
    "individual_stroke": "Individual stroke play (95%)",
    "fourball_match": "Four-ball match (90%)",
    "fourball_stroke": "Four-ball stroke play (85%)",
    "stableford_individual": "Individual Stableford (95%)",
}

# Default format/allowance for /matches/new -- 100% (Individual match play),
# which is the pre-Rule-6.2 behavior (Playing Handicap == Course Handicap).
DEFAULT_MATCH_FORMAT = "individual_match"


def _match_format_options():
    """List of (key, label) tuples for the /matches/new format selector, in
    WHS_HANDICAP_ALLOWANCES's insertion order. Only keys present in BOTH
    WHS_HANDICAP_ALLOWANCES and MATCH_FORMAT_LABELS are offered, so a label
    can never be shown for a format the allowance table doesn't recognize
    (and vice versa)."""
    return [
        (key, MATCH_FORMAT_LABELS[key])
        for key in WHS_HANDICAP_ALLOWANCES
        if key in MATCH_FORMAT_LABELS
    ]


def _resolve_match_allowance(format_key: str) -> tuple[str, int]:
    """Map a submitted match-format key to (normalized_key, allowance_percent)
    via WHS_HANDICAP_ALLOWANCES (Appendix C). An unrecognized/missing format
    key is untrusted user input (POST body) -- rather than trust a raw
    percentage from the client, only the fixed, known Appendix C format keys
    are ever accepted, and anything else silently falls back to
    DEFAULT_MATCH_FORMAT (100%, non-breaking/current behavior). This means
    allowance_percent is always one of WHS_HANDICAP_ALLOWANCES's values
    (85/90/95/100) -- inherently within a sane 1..100 range."""
    key = (format_key or "").strip()
    if key not in WHS_HANDICAP_ALLOWANCES:
        key = DEFAULT_MATCH_FORMAT
    return key, WHS_HANDICAP_ALLOWANCES[key]


def _format_label(match: dict) -> str:
    """Human-readable Appendix C format label for a stored match, e.g.
    'Four-ball stroke play (85%)'. Reads `match['format_key']` (the
    display/source-of-truth for the label -- see create_match's docstring)
    rather than reverse-mapping `allowance_percent`, since the percent alone
    is ambiguous (95% is shared by individual_stroke and
    stableford_individual). Falls back to the default label for a missing/
    unrecognized format_key (e.g. a pre-migration match row, or a stray
    value that predates a future format addition/removal)."""
    key = match.get("format_key") or DEFAULT_MATCH_FORMAT
    allowance = match.get("allowance_percent", 100)
    # Cross-check the format label against the ACTUAL applied allowance. A
    # legacy row created after the allowance feature but before format_key
    # existed backfills to individual_match yet may carry allowance 85/90/95 --
    # trusting format_key alone would mislabel it "Individual match play
    # (100%)". If the key's canonical allowance disagrees with the stored one
    # (net math always uses allowance_percent), show a percent-only label so
    # the displayed % never contradicts the % actually applied to the net.
    if key in WHS_HANDICAP_ALLOWANCES and WHS_HANDICAP_ALLOWANCES[key] != allowance:
        return f"Custom allowance ({allowance}%)"
    return MATCH_FORMAT_LABELS.get(key, MATCH_FORMAT_LABELS[DEFAULT_MATCH_FORMAT])


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
            format_key, allowance_percent = _resolve_match_allowance(request.form.get("format", ""))
            if not course_name:
                return render_template("match_new.html", **base_context(
                    current_page="matches", courses=get_courses(),
                    users=get_users(), today=date.today().isoformat(),
                    formats=_match_format_options(), selected_format=format_key,
                    error="Course is required.",
                ))
            if not match_date:
                return render_template("match_new.html", **base_context(
                    current_page="matches", courses=get_courses(),
                    users=get_users(), today=date.today().isoformat(),
                    formats=_match_format_options(), selected_format=format_key,
                    error="Date is required.",
                ))
            if len(participant_ids) < 2:
                return render_template("match_new.html", **base_context(
                    current_page="matches", courses=get_courses(),
                    users=get_users(), today=date.today().isoformat(),
                    formats=_match_format_options(), selected_format=format_key,
                    error="At least 2 participants are required.",
                ))
            match_id = create_match(
                created_by=current_user.id,
                course_name=course_name,
                date=match_date,
                allowance_percent=allowance_percent,
                format_key=format_key,
            )
            for uid_str in participant_ids:
                add_match_player(match_id, int(uid_str))
            return redirect(url_for("match_detail", match_id=match_id))
        return render_template("match_new.html", **base_context(
            current_page="matches", courses=get_courses(),
            users=get_users(), today=date.today().isoformat(),
            formats=_match_format_options(), selected_format=DEFAULT_MATCH_FORMAT,
        ))

    @app.route("/matches/<int:match_id>")
    @login_required
    def match_detail(match_id):
        match = get_match(match_id)
        if not match:
            return "Match not found.", 404
        players = get_match_players(match_id)
        is_participant = any(p["user_id"] == current_user.id for p in players)
        if not is_participant and not current_user.is_admin:
            return "Match not found.", 404
        match_rounds = get_match_rounds(match_id)
        round_details = _build_round_details(match_rounds)
        if players:
            min_net = min(p["total_net"] for p in players)
            for p in players:
                p["is_winner"] = p["total_net"] == min_net and p["round_count"] > 0
        player_rounds = {}
        for rd in round_details:
            player_rounds.setdefault(rd["user_id"], []).append(rd)
        podium_players = [p for p in players if p["round_count"] > 0]
        podium_players.sort(key=lambda x: x["total_net"])
        podium_top = podium_players[:3]
        return render_template("match_detail.html", **base_context(
            current_page="matches", match=match, players=players,
            round_details=round_details, player_rounds=player_rounds,
            podium_players=podium_players, podium_top=podium_top,
            is_participant=is_participant, format_label=_format_label(match),
        ))

    # Linking mutates a round's match association + net score — a round write,
    # so gate it on rounds:write like the other round mutations.
    @app.route("/matches/<int:match_id>/link-round", methods=["GET", "POST"])
    @login_required
    @require_permission("rounds:write")
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
                    current_page="matches", match=match, format_label=_format_label(match),
                    unlinked=[], error="Please select a round.",
                ))
            round_id = int(round_id)
            if round_id in linked_ids:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match, format_label=_format_label(match),
                    unlinked=[], error="This round is already linked.",
                ))
            round_data = get_round_by_id(round_id)
            if not round_data or round_data.user_id != current_user.id:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match, format_label=_format_label(match),
                    unlinked=[], error="Round not found.",
                ))
            if not round_data.computed_handicap:
                return render_template("match_link_round.html", **base_context(
                    current_page="matches", match=match, format_label=_format_label(match),
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
            # WHS Rule 6.2 / Appendix C: reduce the Course Handicap to a
            # Playing Handicap using this match's allowance percent (default
            # 100 -- unchanged from the pre-Rule-6.2 full-Course-Handicap net).
            allowance = match.get("allowance_percent", 100)
            ph = calc_playing_handicap(ch, allowance)
            net = gross - ph

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
            # WHS Rule 6.2 / Appendix C: same allowance-adjusted Playing
            # Handicap used at link time, so the preview net matches what
            # will actually be stored on link.
            ph = calc_playing_handicap(ch, match.get("allowance_percent", 100))
            net = gross - ph

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
            format_label=_format_label(match),
        ))
