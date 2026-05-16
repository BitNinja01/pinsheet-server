import os
import json
import logging
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from datetime import date, timedelta

from flask import Flask, render_template, jsonify, request, redirect, url_for

from store import (
    init_data_dir, load_settings, save_settings,
    get_courses, get_all_rounds, get_slope_rating,
    save_round, delete_round, save_course, delete_course, rename_course,
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_handicap_benchmarks,
)
from calc import (
    DEFAULT_DASHBOARD_STATS,
    STAT_CATALOG,
    calc_best_3round_stretch,
    calc_best_fir_round,
    calc_best_gir_round,
    calc_best_single_round,
    calc_big_number_rate,
    calc_biggest_improvement,
    calc_clean_card_percent,
    calc_course_handicap,
    calc_expected_9hole_dif,
    calc_fir_miss_tendency,
    calc_fir_percent,
    calc_first_hi_milestone,
    calc_first_score_milestone,
    calc_gir_miss_direction,
    calc_gir_percent,
    calc_golfiest_month,
    calc_handicap_index,
    calc_hi_journey,
    calc_hole_in_ones,
    calc_momentum_recovery,
    calc_most_common_day,
    calc_most_played_course,
    calc_one_putt_percent,
    calc_par_or_better_percent,
    calc_penalty_free_rounds,
    calc_penalty_stats,
    calc_personal_bests,
    calc_putts_per_gir,
    calc_putts_per_round,
    calc_round_dif,
    calc_rounds_total,
    calc_scoring_average,
    calc_scoring_avg_by_par_type,
    calc_scoring_by_fairway,
    calc_scoring_by_gir,
    calc_scoring_consistency,
    calc_scramble_by_miss_direction,
    calc_scramble_percent,
    calc_score_breakdown,
    calc_season_rounds,
    calc_season_yardage,
    calc_three_putt_percent,
    calc_two_putt_percent,
    get_best_n_rounds,
)

_log = logging.getLogger("pinsheet")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

PORT = 8420


def find_free_port() -> int:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", PORT))
            return PORT
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def _last_n_rounds(all_rounds, courses, n: int) -> list:
    return [r for r in all_rounds[:n] if not r.get("excluded")]


def _best_n_rounds(all_rounds, courses, n: int) -> list:
    eligible = [r for r in all_rounds if not r.get("excluded") and r.get("differential") and r["differential"] != "0"]
    eligible.sort(key=lambda r: float(r["differential"]))
    return eligible[:min(n, len(eligible))]


def _build_window(all_rounds, target_date):
    return [r for r in all_rounds if r.get("date", "") <= target_date][:20]


def _get_last_year_hi(all_rounds, include_9hole):
    today = date.today()
    target = today.replace(year=today.year - 1)
    window_start = target - timedelta(days=60)
    window_end = target + timedelta(days=60)
    for r in all_rounds:
        if not r.get("differential") or r["differential"] == "0":
            continue
        d = r.get("date", "")
        if window_start.isoformat() <= d <= window_end.isoformat():
            window = _build_window(all_rounds, d)
            hi = calc_handicap_index(window, include_9hole)
            if hi is not None:
                return hi
    return None


def _round_vs_par(round_data, courses):
    course = courses.get(round_data.get("course", ""), {})
    par = int(course.get("par", 0))
    total = int(round_data.get("total_gross", 0))
    return total - par if par and total else None


def _avg_vs_par(rounds, courses):
    vals = [_round_vs_par(r, courses) for r in rounds]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _round_vs_rating(round_data, courses):
    course = courses.get(round_data.get("course", ""), {})
    tees = course.get("tees", {}).get(round_data.get("tees", ""), {})
    rating = float(tees.get("rating", 72))
    total = int(round_data.get("total_gross", 0))
    return total - rating if total else None


def _avg_vs_rating(rounds, courses):
    vals = [_round_vs_rating(r, courses) for r in rounds]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _penalties_per_round(rounds):
    totals = []
    for r in rounds:
        if not r.get("holes"):
            continue
        pen = sum(int(h.get("penalties", "0")) for h in r["holes"].values())
        totals.append(pen)
    return sum(totals) / len(totals) if totals else None


@app.route("/")
def dashboard():
    settings = load_settings()
    if not settings.get("welcome_shown"):
        return render_template("welcome.html", settings=settings)
    courses = get_courses()
    all_rounds = get_all_rounds()
    include_9hole = settings.get("include_9hole", True)

    l20 = _last_n_rounds(all_rounds, courses, 20)
    b8 = _best_n_rounds(all_rounds, courses, 8)

    panels = {}
    for stat_def in STAT_CATALOG:
        key = stat_def["key"]
        if key not in DEFAULT_DASHBOARD_STATS:
            continue
        primary = stat_def["fn_primary"](l20, b8, courses, include_9hole)
        secondary = stat_def["fn_secondary"](l20, b8, courses, include_9hole)
        panels[key] = {
            "label": stat_def["label"],
            "value": f"{primary:.1f}{stat_def['suffix']}" if primary is not None else "--",
            "secondary": f"{secondary:.1f}{stat_def['suffix']}" if secondary is not None else "--",
            "higher_better": stat_def["higher_better"],
            "color": f"rgb({stat_def['color'][0]},{stat_def['color'][1]},{stat_def['color'][2]})",
            "blank_text": stat_def["blank_text"],
        }

    last_year_hi = _get_last_year_hi(all_rounds, include_9hole)
    if last_year_hi is not None:
        panels["handicap"]["subtitle"] = f"1y {last_year_hi:.1f}"

    rounds_data = []
    for r in all_rounds[:20]:
        course = courses.get(r.get("course", ""), {})
        total = r.get("total_gross", "")
        par = course.get("par", 0)
        score_to_par = int(total) - int(par) if total and par and total != "0" else None
        rounds_data.append({
            "date": r.get("date", ""),
            "course": r.get("course", ""),
            "tees": r.get("tees", ""),
            "total": total,
            "score_to_par": score_to_par,
            "differential": r.get("differential", ""),
            "index": r.get("index", 0),
            "in_handicap": False,
        })

    best_rounds = get_best_n_rounds(all_rounds, include_9hole)
    best_keys = {(r.get("date", ""), r.get("index", 0)) for r in best_rounds}
    for rd in rounds_data:
        if (rd["date"], rd["index"]) in best_keys:
            rd["in_handicap"] = True

    return render_template("dashboard.html", panels=panels, rounds=rounds_data,
                           last_year_hi=last_year_hi, settings=settings)


@app.route("/api/welcome", methods=["POST"])
def api_welcome_done():
    settings = load_settings()
    settings["welcome_shown"] = True
    save_settings(settings)
    return jsonify({"ok": True})


@app.route("/rounds/new")
def round_entry():
    settings = load_settings()
    courses = get_courses()
    today = date.today().isoformat()
    no_courses = len(courses) == 0
    return render_template("round_entry.html", settings=settings, courses=courses, today=today, no_courses=no_courses)


@app.route("/api/drafts/round", methods=["GET"])
def api_draft_round_get():
    draft = load_round_draft()
    return jsonify(draft or {})


@app.route("/api/drafts/round", methods=["PUT"])
def api_draft_round_put():
    save_round_draft(request.get_json())
    return jsonify({"ok": True})


@app.route("/api/drafts/round", methods=["DELETE"])
def api_draft_round_delete():
    clear_round_draft()
    return jsonify({"ok": True})


@app.route("/api/drafts/course", methods=["GET"])
def api_draft_course_get():
    draft = load_course_draft()
    return jsonify(draft or {})


@app.route("/api/drafts/course", methods=["PUT"])
def api_draft_course_put():
    save_course_draft(request.get_json())
    return jsonify({"ok": True})


@app.route("/api/drafts/course", methods=["DELETE"])
def api_draft_course_delete():
    clear_course_draft()
    return jsonify({"ok": True})


@app.route("/api/rounds", methods=["POST"])
def api_rounds_post():
    data = request.get_json()
    date_val = data.get("date", "")
    course_name = data.get("course", "")
    tees_name = data.get("tees", "")

    courses = get_courses()
    course = courses.get(course_name, {})
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

    all_rounds = get_all_rounds()
    all_rounds.insert(0, golf_round)
    settings = load_settings()
    new_hi = calc_handicap_index(all_rounds, settings.get("include_9hole", True))
    if new_hi is not None:
        golf_round["computed_handicap"] = str(new_hi)

    save_round(golf_round, date_val, 0)
    index = 0

    return jsonify({"date": date_val, "index": index, "differential": differential})


@app.route("/rounds/<date>/<index>")
def round_detail(date, index):
    courses = get_courses()
    rounds = get_all_rounds()
    round_data = None
    for r in rounds:
        if r.get("date") == date and str(r.get("index")) == str(index):
            round_data = r
            break
    if not round_data:
        return "Round not found", 404

    course = courses.get(round_data.get("course", ""), {})
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
        settings=load_settings(),
    )


@app.route("/rounds/<date>/<index>/report")
def report_card(date, index):
    courses = get_courses()
    all_rounds = get_all_rounds()

    this_round = None
    for r in all_rounds:
        if r.get("date") == date and str(r.get("index")) == str(index):
            this_round = r
            break
    if not this_round:
        return "Round not found", 404

    l20 = [r for r in all_rounds[:20] if not r.get("excluded")]
    if this_round not in l20:
        l20.insert(0, this_round)
        l20 = l20[:20]

    rows = [
        ("Score vs Par", _round_vs_par(this_round, courses), _avg_vs_par(l20, courses), False, "", 1),
        ("Score vs Rating", _round_vs_rating(this_round, courses), _avg_vs_rating(l20, courses), False, "", 1),
        ("Par or Better %", calc_par_or_better_percent([this_round], courses), calc_par_or_better_percent(l20, courses), True, "%", 1),
        ("Blow-up Rate", calc_big_number_rate([this_round], courses), calc_big_number_rate(l20, courses), False, "%", 1),
        ("FIR %", calc_fir_percent([this_round], courses), calc_fir_percent(l20, courses), True, "%", 1),
        ("GIR %", calc_gir_percent([this_round]), calc_gir_percent(l20), True, "%", 1),
        ("Putts / Rnd", calc_putts_per_round([this_round]), calc_putts_per_round(l20), False, "", 1),
        ("1-Putt %", calc_one_putt_percent([this_round]), calc_one_putt_percent(l20), True, "%", 1),
        ("2-Putt %", calc_two_putt_percent([this_round]), calc_two_putt_percent(l20), True, "%", 1),
        ("3-Putt %", calc_three_putt_percent([this_round]), calc_three_putt_percent(l20), False, "%", 1),
        ("Scramble %", calc_scramble_percent([this_round], courses), calc_scramble_percent(l20, courses), True, "%", 1),
    ]

    par_this = calc_scoring_avg_by_par_type([this_round], courses)
    par_l20 = calc_scoring_avg_by_par_type(l20, courses)
    for p in [3, 4, 5]:
        rows.append((
            f"Par {p} Avg",
            par_this.get(p),
            par_l20.get(p),
            False, "", 2,
        ))

    rows.append(("Penalties / Rnd", _penalties_per_round([this_round]), _penalties_per_round(l20), False, "", 1))

    return render_template("report_card.html", rows=rows, round=this_round, settings=load_settings())


@app.route("/api/rounds/<date>/<index>", methods=["DELETE"])
def api_rounds_delete(date, index):
    delete_round(date, index)
    return jsonify({"ok": True})


@app.route("/courses/new")
def course_entry():
    courses = get_courses()
    return render_template("course_entry.html", courses=courses, settings=load_settings())


@app.route("/courses")
def course_list():
    courses = get_courses()
    all_rounds = get_all_rounds()

    course_data = []
    for name, course in courses.items():
        location = course.get("location", "")
        play_count = 0
        last_played = None
        for r in all_rounds:
            if r.get("course") == name:
                play_count += 1
                if last_played is None or r.get("date", "") > last_played:
                    last_played = r.get("date", "")

        course_data.append({
            "name": name,
            "location": location,
            "play_count": play_count,
            "last_played": last_played,
        })

    course_data.sort(key=lambda c: c["name"].lower())

    return render_template("courses.html", courses=course_data, settings=load_settings())


@app.route("/courses/<name>")
def course_detail(name):
    courses = get_courses()
    course = courses.get(name)
    if not course:
        return "Course not found", 404

    all_rounds = get_all_rounds()

    play_count = 0
    first_played = None
    last_played = None
    for r in all_rounds:
        if r.get("course") == name:
            play_count += 1
            d = r.get("date", "")
            if first_played is None or d < first_played:
                first_played = d
            if last_played is None or d > last_played:
                last_played = d

    tees = course.get("tees", {})
    holes = course.get("holes", {})
    hole_nums = sorted(holes.keys(), key=lambda x: int(x))

    hole_rows = []
    for hn in hole_nums:
        h = holes[hn]
        yardages = {}
        for tee_name in tees:
            td = tees[tee_name]
            yardages_data = td.get("yardages", {})
            yardages[tee_name] = yardages_data.get(hn, "")
        hole_rows.append({
            "num": int(hn),
            "par": h.get("par", ""),
            "index": h.get("index", ""),
            "yardages": yardages,
        })

    return render_template("course_detail.html",
        course=course, name=name, tees=tees, holes=hole_rows,
        play_count=play_count, first_played=first_played, last_played=last_played,
        settings=load_settings(),
    )


@app.route("/api/courses", methods=["POST"])
def api_courses_post():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    location = data.get("location", {})
    if not isinstance(location, dict) or not location.get("city") or not location.get("state/province") or not location.get("country"):
        return jsonify({"error": "City, state/province, and country are required"}), 400

    course = {
        "location": location,
        "tees": data.get("tees", {}),
        "holes": data.get("holes", {}),
        "par": data.get("par", 0),
    }

    save_course(course, name)
    return jsonify({"ok": True, "name": name})


@app.route("/api/courses/<name>", methods=["DELETE"])
def api_courses_delete(name):
    all_rounds = get_all_rounds()
    for r in all_rounds:
        if r.get("course") == name:
            return jsonify({"error": "Cannot delete course with existing rounds"}), 409
    delete_course(name)
    return jsonify({"ok": True})


@app.route("/stats")
def stats():
    settings = load_settings()
    courses = get_courses()
    all_rounds = get_all_rounds()
    include_9hole = settings.get("include_9hole", True)

    b8 = _best_n_rounds(all_rounds, courses, 8)
    l5 = _last_n_rounds(all_rounds, courses, 5)
    l10 = _last_n_rounds(all_rounds, courses, 10)
    l20 = _last_n_rounds(all_rounds, courses, 20)

    hi = calc_handicap_index(l20, include_9hole)
    benchmarks = get_handicap_benchmarks(hi) if hi is not None else None

    def fmt(val, suffix="", precision=1):
        if val is None:
            return "\u2014"
        return f"{val:.{precision}f}{suffix}"

    def fmt_pct(val):
        if val is None:
            return "\u2014"
        return f"{val:.1f}%"

    sections = {}

    # 1. Scoring
    scoring_rows = []
    scoring_rows.append(("Scoring Avg", [fmt(calc_scoring_average(b8)), fmt(calc_scoring_average(l5)), fmt(calc_scoring_average(l10)), fmt(calc_scoring_average(l20))]))
    scoring_rows.append(("Par or Better %", [fmt_pct(calc_par_or_better_percent(b8, courses)), fmt_pct(calc_par_or_better_percent(l5, courses)), fmt_pct(calc_par_or_better_percent(l10, courses)), fmt_pct(calc_par_or_better_percent(l20, courses))]))
    scoring_rows.append(("Blow-up %", [fmt_pct(calc_big_number_rate(b8, courses)), fmt_pct(calc_big_number_rate(l5, courses)), fmt_pct(calc_big_number_rate(l10, courses)), fmt_pct(calc_big_number_rate(l20, courses))]))
    scoring_rows.append(("Clean Card %", [fmt_pct(calc_clean_card_percent(b8, courses)), fmt_pct(calc_clean_card_percent(l5, courses)), fmt_pct(calc_clean_card_percent(l10, courses)), fmt_pct(calc_clean_card_percent(l20, courses))]))
    scoring_rows.append(("Consistency", [fmt(calc_scoring_consistency(b8, courses)), fmt(calc_scoring_consistency(l5, courses)), fmt(calc_scoring_consistency(l10, courses)), fmt(calc_scoring_consistency(l20, courses))]))
    sections["scoring"] = {"label": "Scoring", "headline": "Your scoring average and consistency across recent rounds.", "rows": scoring_rows}

    # 2. Penalties
    pen_b8 = calc_penalty_stats(b8, courses)
    pen_l5 = calc_penalty_stats(l5, courses)
    pen_l10 = calc_penalty_stats(l10, courses)
    pen_l20 = calc_penalty_stats(l20, courses)
    penalty_rows = []
    penalty_rows.append(("Per Round", [fmt(pen_b8.get("rate_per_round")), fmt(pen_l5.get("rate_per_round")), fmt(pen_l10.get("rate_per_round")), fmt(pen_l20.get("rate_per_round"))]))
    penalty_rows.append(("Penalty Avg vs Par", [fmt(pen_b8.get("penalty_avg_vs_par")), fmt(pen_l5.get("penalty_avg_vs_par")), fmt(pen_l10.get("penalty_avg_vs_par")), fmt(pen_l20.get("penalty_avg_vs_par"))]))
    penalty_rows.append(("Clean Avg vs Par", [fmt(pen_b8.get("clean_avg_vs_par")), fmt(pen_l5.get("clean_avg_vs_par")), fmt(pen_l10.get("clean_avg_vs_par")), fmt(pen_l20.get("clean_avg_vs_par"))]))
    sections["penalties"] = {"label": "Penalties", "headline": "How penalties affect your scoring.", "rows": penalty_rows}

    # 3. Fairways
    fir_rows = []
    fir_rows.append(("FIR %", [fmt_pct(calc_fir_percent(b8, courses)), fmt_pct(calc_fir_percent(l5, courses)), fmt_pct(calc_fir_percent(l10, courses)), fmt_pct(calc_fir_percent(l20, courses))]))
    fw_b8 = calc_scoring_by_fairway(b8, courses)
    fw_l5 = calc_scoring_by_fairway(l5, courses)
    fw_l10 = calc_scoring_by_fairway(l10, courses)
    fw_l20 = calc_scoring_by_fairway(l20, courses)
    fir_rows.append(("Hit Avg vs Par", [fmt(fw_b8.get("hit")), fmt(fw_l5.get("hit")), fmt(fw_l10.get("hit")), fmt(fw_l20.get("hit"))]))
    fir_rows.append(("Miss Avg vs Par", [fmt(fw_b8.get("missed")), fmt(fw_l5.get("missed")), fmt(fw_l10.get("missed")), fmt(fw_l20.get("missed"))]))
    miss_b8 = calc_fir_miss_tendency(b8, courses)
    miss_l20 = calc_fir_miss_tendency(l20, courses)
    fir_rows.append(("Miss Left %", [fmt_pct(miss_b8.get("left")), "\u2014", "\u2014", fmt_pct(miss_l20.get("left"))]))
    fir_rows.append(("Miss Right %", [fmt_pct(miss_b8.get("right")), "\u2014", "\u2014", fmt_pct(miss_l20.get("right"))]))
    sections["fairways"] = {"label": "Fairways", "headline": "Fairway accuracy and scoring impact.", "rows": fir_rows}

    # 4. Greens
    gir_rows = []
    gir_rows.append(("GIR %", [fmt_pct(calc_gir_percent(b8)), fmt_pct(calc_gir_percent(l5)), fmt_pct(calc_gir_percent(l10)), fmt_pct(calc_gir_percent(l20))]))
    gb8 = calc_scoring_by_gir(b8, courses)
    gl5 = calc_scoring_by_gir(l5, courses)
    gl10 = calc_scoring_by_gir(l10, courses)
    gl20 = calc_scoring_by_gir(l20, courses)
    gir_rows.append(("Hit Avg vs Par", [fmt(gb8.get("hit")), fmt(gl5.get("hit")), fmt(gl10.get("hit")), fmt(gl20.get("hit"))]))
    gir_rows.append(("Miss Avg vs Par", [fmt(gb8.get("missed")), fmt(gl5.get("missed")), fmt(gl10.get("missed")), fmt(gl20.get("missed"))]))
    gmiss_b8 = calc_gir_miss_direction(b8)
    gmiss_l20 = calc_gir_miss_direction(l20)
    gir_rows.append(("Miss Short %", [fmt_pct(gmiss_b8.get("S")), "\u2014", "\u2014", fmt_pct(gmiss_l20.get("S"))]))
    gir_rows.append(("Miss Long %", [fmt_pct(gmiss_b8.get("LO")), "\u2014", "\u2014", fmt_pct(gmiss_l20.get("LO"))]))
    gir_rows.append(("Miss Left %", [fmt_pct(gmiss_b8.get("L")), "\u2014", "\u2014", fmt_pct(gmiss_l20.get("L"))]))
    gir_rows.append(("Miss Right %", [fmt_pct(gmiss_b8.get("R")), "\u2014", "\u2014", fmt_pct(gmiss_l20.get("R"))]))
    sections["greens"] = {"label": "Greens", "headline": "Greens in regulation and scoring impact.", "rows": gir_rows}

    # 5. Putting
    putting_rows = []
    putting_rows.append(("Putts / Rnd", [fmt(calc_putts_per_round(b8)), fmt(calc_putts_per_round(l5)), fmt(calc_putts_per_round(l10)), fmt(calc_putts_per_round(l20))]))
    putting_rows.append(("Putts / GIR", [fmt(calc_putts_per_gir(b8)), fmt(calc_putts_per_gir(l5)), fmt(calc_putts_per_gir(l10)), fmt(calc_putts_per_gir(l20))]))
    putting_rows.append(("1-Putt %", [fmt_pct(calc_one_putt_percent(b8)), fmt_pct(calc_one_putt_percent(l5)), fmt_pct(calc_one_putt_percent(l10)), fmt_pct(calc_one_putt_percent(l20))]))
    putting_rows.append(("2-Putt %", [fmt_pct(calc_two_putt_percent(b8)), fmt_pct(calc_two_putt_percent(l5)), fmt_pct(calc_two_putt_percent(l10)), fmt_pct(calc_two_putt_percent(l20))]))
    putting_rows.append(("3-Putt %", [fmt_pct(calc_three_putt_percent(b8)), fmt_pct(calc_three_putt_percent(l5)), fmt_pct(calc_three_putt_percent(l10)), fmt_pct(calc_three_putt_percent(l20))]))
    sections["putting"] = {"label": "Putting", "headline": "Putting performance across recent rounds.", "rows": putting_rows}

    # 6. Short Game
    short_rows = []
    short_rows.append(("Scramble %", [fmt_pct(calc_scramble_percent(b8, courses)), fmt_pct(calc_scramble_percent(l5, courses)), fmt_pct(calc_scramble_percent(l10, courses)), fmt_pct(calc_scramble_percent(l20, courses))]))
    scr_b8 = calc_scramble_by_miss_direction(b8, courses)
    scr_l20 = calc_scramble_by_miss_direction(l20, courses)
    short_rows.append(("Scramble Short %", [fmt_pct(scr_b8.get("S")), "\u2014", "\u2014", fmt_pct(scr_l20.get("S"))]))
    short_rows.append(("Scramble Long %", [fmt_pct(scr_b8.get("LO")), "\u2014", "\u2014", fmt_pct(scr_l20.get("LO"))]))
    short_rows.append(("Scramble Left %", [fmt_pct(scr_b8.get("L")), "\u2014", "\u2014", fmt_pct(scr_l20.get("L"))]))
    short_rows.append(("Scramble Right %", [fmt_pct(scr_b8.get("R")), "\u2014", "\u2014", fmt_pct(scr_l20.get("R"))]))
    sections["shortgame"] = {"label": "Short Game", "headline": "Up-and-down scrambling performance.", "rows": short_rows}

    # 7. Momentum
    mom_b8 = calc_momentum_recovery(b8, courses)
    mom_l20 = calc_momentum_recovery(l20, courses)
    momentum_rows = []
    momentum_rows.append(("After Bogey Avg", [fmt(mom_b8.get("after_bogey_avg")), "\u2014", "\u2014", fmt(mom_l20.get("after_bogey_avg"))]))
    momentum_rows.append(("Recovery Rate %", [fmt_pct(mom_b8.get("recovery_rate")), "\u2014", "\u2014", fmt_pct(mom_l20.get("recovery_rate"))]))
    sections["momentum"] = {"label": "Momentum", "headline": "How you respond after bad holes.", "rows": momentum_rows}

    # 8. Bests
    bests = calc_personal_bests(all_rounds, courses)
    bests_data = [
        ("Lowest Gross", bests.get("best_gross"), bests.get("best_gross_date")),
        ("Lowest Diff", bests.get("best_diff"), bests.get("best_diff_date")),
        ("Most FIR", bests.get("most_fir"), bests.get("most_fir_date")),
        ("Most GIR", bests.get("most_gir"), bests.get("most_gir_date")),
        ("Fewest Putts", bests.get("fewest_putts"), bests.get("fewest_putts_date")),
    ]
    sections["bests"] = {"label": "Bests", "headline": "Your personal best performances.", "bests": bests_data}

    # 9. Trends
    chronological = list(reversed(all_rounds))
    trend_rows = []
    for r in chronological:
        d = r.get("date", "")
        if not r.get("total_gross") or r["total_gross"] == "0":
            continue
        if r.get("holes_selection", "all") != "all":
            continue
        course = courses.get(r.get("course", ""), {})
        par = int(course.get("par", 0))
        gross = int(r.get("total_gross", 0))
        trend_rows.append({
            "date": d,
            "course": r.get("course", ""),
            "score": gross,
            "vs_par": gross - par if par else None,
            "diff": r.get("differential", ""),
            "fir": fmt_pct(calc_fir_percent([r], courses)),
            "gir": fmt_pct(calc_gir_percent([r])),
            "putts": str(sum(int(h.get("putts", 0)) for h in r.get("holes", {}).values() if h.get("putts"))) if r.get("holes") else "\u2014",
        })
    sections["trends"] = {"label": "Trends", "headline": "Round-by-round performance history.", "trends": trend_rows}

    return render_template("stats.html", sections=sections, settings=settings)


@app.route("/settings")
def settings_page():
    settings = load_settings()
    courses = get_courses()
    themes = [
        "green", "ocean", "amber", "sunset", "purple", "teal",
        "crimson", "midnight", "rose", "gold", "slate", "lime",
    ]
    return render_template("settings.html", settings=settings, courses=courses, themes=themes)


@app.route("/api/settings", methods=["PUT"])
def api_settings_put():
    data = request.get_json()
    save_settings(data)
    return jsonify({"ok": True})


@app.route("/season")
def season_summary():
    settings = load_settings()
    courses = get_courses()
    all_rounds = get_all_rounds()
    include_9hole = settings.get("include_9hole", True)

    if settings.get("season_enabled"):
        season_rounds = calc_season_rounds(all_rounds, settings)
    else:
        season_rounds = all_rounds

    hi = calc_handicap_index(all_rounds, include_9hole)
    journey = calc_hi_journey(all_rounds, season_rounds, hi)
    most_played = calc_most_played_course(season_rounds)
    golfiest = calc_golfiest_month(season_rounds)
    common_day = calc_most_common_day(season_rounds)
    best_round = calc_best_single_round(season_rounds)
    best_stretch = calc_best_3round_stretch(season_rounds)
    biggest_improvement = calc_biggest_improvement(season_rounds)
    first_score_ms = calc_first_score_milestone(season_rounds, all_rounds)
    first_hi_ms = calc_first_hi_milestone(season_rounds, all_rounds)
    breakdown = calc_score_breakdown(season_rounds, courses)
    hole_in_ones = calc_hole_in_ones(season_rounds, courses)
    best_gir = calc_best_gir_round(season_rounds)
    best_fir = calc_best_fir_round(season_rounds, courses)
    walking_miles = calc_season_yardage(season_rounds, courses, "walking")
    riding_miles = calc_season_yardage(season_rounds, courses, "riding")
    penalty_free = calc_penalty_free_rounds(season_rounds)
    rounds_count = len(season_rounds)
    total_rounds = calc_rounds_total(all_rounds)

    return render_template("season_summary.html",
        settings=settings,
        rounds_count=rounds_count,
        total_rounds=total_rounds,
        journey=journey,
        most_played=most_played,
        golfiest=golfiest,
        common_day=common_day,
        best_round=best_round,
        best_stretch=best_stretch,
        biggest_improvement=biggest_improvement,
        first_score_ms=first_score_ms,
        first_hi_ms=first_hi_ms,
        breakdown=breakdown,
        hole_in_ones=hole_in_ones,
        best_gir=best_gir,
        best_fir=best_fir,
        walking_miles=walking_miles,
        riding_miles=riding_miles,
        penalty_free=penalty_free,
    )


def _find_chrome() -> str | None:
    if sys.platform == "darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    elif sys.platform == "win32":
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        paths = [
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    for p in paths:
        if os.path.isfile(p):
            return p

    found = shutil.which("google-chrome-stable") or shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("chrome")
    return found


def main():
    init_data_dir()
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    chrome = _find_chrome()
    chrome_proc = None
    if chrome:
        chrome_proc = subprocess.Popen([chrome, f"--app={url}", "--start-maximized"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)

    if chrome_proc:
        def _watch_chrome():
            chrome_proc.wait()
            _log.info("Chrome window closed — shutting down")
            os._exit(0)
        threading.Thread(target=_watch_chrome, daemon=True).start()

    from waitress import serve
    print(f"PinSheet → {url}")
    serve(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
