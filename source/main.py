import os
import json
import logging
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
from calc.handicap import (
    calc_handicap_index, calc_course_handicap, calc_round_dif,
    calc_expected_9hole_dif, get_best_n_rounds,
)
from calc.approach import (
    calc_fir_percent, calc_gir_percent, calc_scramble_percent,
)
from calc.putting import (
    calc_putts_per_round, calc_one_putt_percent, calc_two_putt_percent, calc_three_putt_percent,
)
from calc.scoring import (
    calc_scoring_average, calc_par_or_better_percent, calc_big_number_rate, calc_scoring_avg_by_par_type,
    STAT_CATALOG, DEFAULT_DASHBOARD_STATS,
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


@app.route("/rounds/new")
def round_entry():
    settings = load_settings()
    courses = get_courses()
    today = date.today().isoformat()
    return render_template("round_entry.html", settings=settings, courses=courses, today=today)


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

    return render_template("round_detail.html",
        round=round_data, course=course, holes=holes,
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

    course = {
        "location": data.get("location", ""),
        "tees": data.get("tees", {}),
        "holes": data.get("holes", {}),
        "par": data.get("par", 0),
    }

    save_course(course, name)
    return jsonify({"ok": True, "name": name})


@app.route("/api/courses/<name>", methods=["DELETE"])
def api_courses_delete(name):
    delete_course(name)
    return jsonify({"ok": True})


def main():
    init_data_dir()
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    webbrowser.open(url)

    from waitress import serve
    print(f"PinSheet → {url}")
    serve(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
