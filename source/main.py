import io
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
import zipfile
from functools import wraps
from pathlib import Path
from datetime import date, timedelta, datetime

from flask import Flask, render_template, jsonify, request, redirect, url_for, g

from database import set_db_path, init_db
from store import (
    load_settings, save_settings,
    get_courses, get_all_rounds, get_slope_rating,
    save_round, delete_round, save_course, delete_course, rename_course,
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_handicap_benchmarks, get_user_by_id, get_user,
    get_users, create_user, verify_user, user_count, real_user_count,
    is_invite_code_valid, consume_invite_code,
    create_invite_code, get_invite_codes,
    update_round_handicap,
)
from web.catalog import STAT_CATALOG, DEFAULT_DASHBOARD_STATS
from calc import (
    calc_avg_vs_par,
    calc_avg_vs_rating,
    calc_best_3round_stretch,
    calc_best_fir_round,
    calc_best_gir_round,
    calc_best_single_round,
    calc_big_number_rate,
    calc_biggest_improvement,
    calc_clean_card_percent,
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
    calc_last_year_handicap,
    calc_momentum_recovery,
    calc_most_common_day,
    calc_most_played_course,
    calc_one_putt_percent,
    calc_par_or_better_percent,
    calc_penalties_per_round,
    calc_penalty_free_rounds,
    calc_penalty_stats,
    calc_personal_bests,
    calc_putts_per_gir,
    calc_putts_per_round,
    calc_round_dif,
    calc_round_vs_par,
    calc_round_vs_rating,
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

from flask_login import LoginManager, login_user, logout_user, login_required, current_user

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.session_protection = "strong"

app.config["REMEMBER_COOKIE_SECURE"] = os.environ.get("HTTPS", "").lower() in ("1", "true", "yes")
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_DURATION"] = 30 * 24 * 60 * 60  # 30 days


class User:
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.display_name = user_dict["display_name"]
        self.is_admin = user_dict.get("is_admin", False)
        self._authenticated = True

    @property
    def is_authenticated(self):
        return self._authenticated

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def _load_user(user_id):
    user_dict = get_user_by_id(int(user_id))
    return User(user_dict) if user_dict else None


from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

limiter = Limiter(get_remote_address, app=app, default_limits=[])
csrf = CSRFProtect(app)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user_dict = verify_user(username, password)
        if user_dict:
            user = User(user_dict)
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html", error=None)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    invite_code = request.args.get("code", "")
    first_run = real_user_count() == 0

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        code = request.form.get("code", "").strip().upper()

        errors = []
        if len(username) < 3 or len(username) > 30 or not all(c.isalnum() or c == "_" for c in username):
            errors.append("Username must be 3-30 characters (letters, numbers, underscores).")
        if not display_name or len(display_name) > 50:
            errors.append("Display name is required (max 50 characters).")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if get_user(username):
            errors.append("Username is already taken.")

        if not first_run:
            if not code or not is_invite_code_valid(code):
                errors.append("Invalid or expired invite code.")

        if errors:
            return render_template("register.html", errors=errors, code=code, first_run=first_run)

        user_dict = create_user(username, display_name, password)
        if not first_run:
            consume_invite_code(code, user_dict["id"])

        user = User(user_dict)
        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("register.html", errors=None, code=invite_code, first_run=first_run)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login_page"))


@app.before_request
def _load_globals():
    if request.endpoint in ("login_page", "register_page", "static"):
        return

    current_user_id = current_user.id if current_user.is_authenticated else None

    view_username = request.args.get("user")
    if view_username:
        view_user_dict = get_user(view_username)
        if view_user_dict:
            g.view_user = view_user_dict
        else:
            g.view_user = None
    else:
        if current_user.is_authenticated:
            g.view_user = get_user_by_id(current_user_id)
        else:
            g.view_user = None

    if g.view_user is None:
        return

    g.settings = load_settings(g.view_user["id"])
    g.courses = get_courses()
    g.all_rounds = get_all_rounds(g.view_user["id"])


@app.before_request
def _check_view_permission():
    if request.endpoint in ("login_page", "register_page", "static"):
        return
    if not hasattr(g, "view_user") or g.view_user is None:
        return
    g.is_own_data = current_user.is_authenticated and g.view_user["id"] == current_user.id


def requires_own_data(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.is_own_data:
            return "Forbidden", 403
        return f(*args, **kwargs)
    return decorated


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


def _make_chart_data(hi_values):
    chart = {"path": "", "area": "", "points": [], "label_x": "", "label_y": "", "label_v": ""}
    if len(hi_values) < 2:
        return chart
    lo, hi = min(hi_values) - 1.0, max(hi_values) + 1.0
    ml, mr, mt, mb = 36, 16, 22, 30
    cw, ch = 1000 - ml - mr, 230 - mt - mb
    n = len(hi_values) - 1
    pts = []
    for i, v in enumerate(hi_values):
        pts.append((ml + (i / n) * cw, mt + (1 - (v - lo) / (hi - lo)) * ch, v))
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y, _) in enumerate(pts))
    bx, by = pts[-1][0], mt + ch
    return {
        "path": path,
        "area": f"{path} L{bx:.1f} {by:.1f} L{pts[0][0]:.1f} {by:.1f} Z",
        "points": [{"x": f"{x:.1f}", "y": f"{y:.1f}", "v": f"{v:.1f}"} for x, y, v in pts],
        "label_x": f"{pts[-1][0] - 8:.1f}",
        "label_y": f"{pts[-1][1] - 12:.1f}",
        "label_v": f"{pts[-1][2]:.1f}",
    }


@app.route("/")
@login_required
def dashboard():
    if not g.settings.get("welcome_shown"):
        return render_template("welcome.html", settings=g.settings, all_users=get_users())
    include_9hole = g.settings.get("include_9hole", True)

    l20 = _last_n_rounds(g.all_rounds, g.courses, 20)
    b8 = _best_n_rounds(g.all_rounds, g.courses, 8)

    panels = {}
    for stat_def in STAT_CATALOG:
        key = stat_def["key"]
        if key not in DEFAULT_DASHBOARD_STATS:
            continue
        primary = stat_def["fn_primary"](l20, b8, g.courses, include_9hole)
        secondary = stat_def["fn_secondary"](l20, b8, g.courses, include_9hole)
        panels[key] = {
            "label": stat_def["label"],
            "value": f"{primary:.1f}{stat_def['suffix']}" if primary is not None else "--",
            "secondary": f"{secondary:.1f}{stat_def['suffix']}" if secondary is not None else "--",
            "higher_better": stat_def["higher_better"],
            "color": f"rgb({stat_def['color'][0]},{stat_def['color'][1]},{stat_def['color'][2]})",
            "blank_text": stat_def["blank_text"],
        }

    last_year_hi = calc_last_year_handicap(g.all_rounds, include_9hole)
    if last_year_hi is not None:
        panels["handicap"]["subtitle"] = f"1y {last_year_hi:.1f}"

    rounds_data = []
    for r in g.all_rounds[:20]:
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

    all_hi_vals = []
    for r in g.all_rounds:
        ch = r.get("computed_handicap")
        if ch and ch != "0":
            try:
                all_hi_vals.append(float(ch))
            except ValueError:
                pass

    cutoff_3m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    cutoff_12m = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    cutoff_2y = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    def _get_hi_for_range(cutoff):
        vals = []
        for r in g.all_rounds:
            if r.get("date", "") < cutoff:
                continue
            ch = r.get("computed_handicap")
            if ch and ch != "0":
                try:
                    vals.append(float(ch))
                except ValueError:
                    pass
        vals.reverse()
        return vals

    chart_data = {
        "3M": _make_chart_data(_get_hi_for_range(cutoff_3m)),
        "12M": _make_chart_data(_get_hi_for_range(cutoff_12m)),
        "2Y": _make_chart_data(_get_hi_for_range(cutoff_2y)),
        "All": _make_chart_data(all_hi_vals[::-1]),
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
    n = min(len(g.all_rounds), 12) if g.all_rounds else 0
    season_label = f"{season_name} '{yr} · last {n} rounds"

    handicap_panel_val = panels.get("handicap", {}).get("value", "--")

    if handicap_panel_val and handicap_panel_val != "--":
        chart["label_v"] = handicap_panel_val
        chart["hero_value"] = handicap_panel_val

    hi_movement = None
    if handicap_panel_val and handicap_panel_val != "--":
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        prev_hi = None
        for r in g.all_rounds:
            if r.get("date", "") <= thirty_days_ago and r.get("computed_handicap"):
                try:
                    prev_hi = float(r["computed_handicap"])
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

    career_low = None
    best_hi = 999.9
    for r in g.all_rounds:
        if r.get("excluded"):
            continue
        ch = r.get("computed_handicap")
        if ch and ch not in ("0", "0.0", "--"):
            try:
                v = float(ch)
                if 0 < v < best_hi:
                    best_hi = v
            except (ValueError, TypeError):
                pass
    if best_hi < 999.0:
        career_low = str(round(best_hi, 1))

    hi_insight = None
    if handicap_panel_val and handicap_panel_val != "--":
        try:
            curr = float(handicap_panel_val)
            eligible_20 = [r for r in g.all_rounds[:20] if not r.get("excluded") and r.get("differential") and r["differential"] != "0"]
            eligible_count = len(eligible_20)
            best_ids = {(r.get("date"), r.get("index")) for r in best_rounds}
            counting = sum(1 for r in eligible_20 if (r.get("date"), r.get("index")) in best_ids)
            hi_insight = f"{counting} of your last {eligible_count} rounds counted toward index."
            target = curr - 0.3
            if target > 0:
                hi_insight += f" Two more at net par or better drops you below {target:.1f}."
        except (ValueError, TypeError):
            pass

    return render_template("dashboard.html", panels=panels, rounds=rounds_data,
                           last_year_hi=last_year_hi, settings=g.settings,
                           current_page="dashboard",
                           season_label=season_label,
                           hi_movement=hi_movement, career_low=career_low, hi_insight=hi_insight,
                           chart=chart, chart_data_json=chart_data_json,
                           all_users=get_users())


@app.route("/api/welcome", methods=["POST"])
@login_required
@csrf.exempt
def api_welcome_done():
    g.settings["welcome_shown"] = True
    save_settings(g.settings, current_user.id)
    return jsonify({"ok": True})


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
    index = 0

    return jsonify({"date": date_val, "index": index, "differential": differential})


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


@app.route("/courses/new")
@login_required
def course_entry():
    if not g.is_own_data:
        return "You can only enter data for yourself.", 403
    return render_template("course_entry.html", courses=g.courses, settings=g.settings, all_users=get_users())


@app.route("/courses")
@login_required
def course_list():
    course_data = []
    for name, course in g.courses.items():
        location = course.get("location", "")
        play_count = 0
        last_played = None
        for r in g.all_rounds:
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

    return render_template("courses.html", courses=course_data, settings=g.settings, all_users=get_users())


@app.route("/courses/<name>")
@login_required
def course_detail(name):
    course = g.courses.get(name)
    if not course:
        return "Course not found", 404

    play_count = 0
    first_played = None
    last_played = None
    for r in g.all_rounds:
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
        settings=g.settings,
        all_users=get_users(),
    )


@app.route("/api/courses", methods=["POST"])
@login_required
@requires_own_data
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
@login_required
@requires_own_data
def api_courses_delete(name):
    for r in g.all_rounds:
        if r.get("course") == name:
            return jsonify({"error": "Cannot delete course with existing rounds"}), 409
    delete_course(name)
    return jsonify({"ok": True})


@app.route("/stats")
@login_required
def stats():
    include_9hole = g.settings.get("include_9hole", True)

    b8 = _best_n_rounds(g.all_rounds, g.courses, 8)
    l5 = _last_n_rounds(g.all_rounds, g.courses, 5)
    l10 = _last_n_rounds(g.all_rounds, g.courses, 10)
    l20 = _last_n_rounds(g.all_rounds, g.courses, 20)

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
    scoring_rows.append(("Par or Better %", [fmt_pct(calc_par_or_better_percent(b8, g.courses)), fmt_pct(calc_par_or_better_percent(l5, g.courses)), fmt_pct(calc_par_or_better_percent(l10, g.courses)), fmt_pct(calc_par_or_better_percent(l20, g.courses))]))
    scoring_rows.append(("Blow-up %", [fmt_pct(calc_big_number_rate(b8, g.courses)), fmt_pct(calc_big_number_rate(l5, g.courses)), fmt_pct(calc_big_number_rate(l10, g.courses)), fmt_pct(calc_big_number_rate(l20, g.courses))]))
    scoring_rows.append(("Clean Card %", [fmt_pct(calc_clean_card_percent(b8, g.courses)), fmt_pct(calc_clean_card_percent(l5, g.courses)), fmt_pct(calc_clean_card_percent(l10, g.courses)), fmt_pct(calc_clean_card_percent(l20, g.courses))]))
    scoring_rows.append(("Consistency", [fmt(calc_scoring_consistency(b8, g.courses)), fmt(calc_scoring_consistency(l5, g.courses)), fmt(calc_scoring_consistency(l10, g.courses)), fmt(calc_scoring_consistency(l20, g.courses))]))
    sections["scoring"] = {"label": "Scoring", "headline": "Your scoring average and consistency across recent rounds.", "rows": scoring_rows}

    # 2. Penalties
    pen_b8 = calc_penalty_stats(b8, g.courses)
    pen_l5 = calc_penalty_stats(l5, g.courses)
    pen_l10 = calc_penalty_stats(l10, g.courses)
    pen_l20 = calc_penalty_stats(l20, g.courses)
    penalty_rows = []
    penalty_rows.append(("Per Round", [fmt(pen_b8.get("rate_per_round")), fmt(pen_l5.get("rate_per_round")), fmt(pen_l10.get("rate_per_round")), fmt(pen_l20.get("rate_per_round"))]))
    penalty_rows.append(("Penalty Avg vs Par", [fmt(pen_b8.get("penalty_avg_vs_par")), fmt(pen_l5.get("penalty_avg_vs_par")), fmt(pen_l10.get("penalty_avg_vs_par")), fmt(pen_l20.get("penalty_avg_vs_par"))]))
    penalty_rows.append(("Clean Avg vs Par", [fmt(pen_b8.get("clean_avg_vs_par")), fmt(pen_l5.get("clean_avg_vs_par")), fmt(pen_l10.get("clean_avg_vs_par")), fmt(pen_l20.get("clean_avg_vs_par"))]))
    sections["penalties"] = {"label": "Penalties", "headline": "How penalties affect your scoring.", "rows": penalty_rows}

    # 3. Fairways
    fir_rows = []
    fir_rows.append(("FIR %", [fmt_pct(calc_fir_percent(b8, g.courses)), fmt_pct(calc_fir_percent(l5, g.courses)), fmt_pct(calc_fir_percent(l10, g.courses)), fmt_pct(calc_fir_percent(l20, g.courses))]))
    fw_b8 = calc_scoring_by_fairway(b8, g.courses)
    fw_l5 = calc_scoring_by_fairway(l5, g.courses)
    fw_l10 = calc_scoring_by_fairway(l10, g.courses)
    fw_l20 = calc_scoring_by_fairway(l20, g.courses)
    fir_rows.append(("Hit Avg vs Par", [fmt(fw_b8.get("hit")), fmt(fw_l5.get("hit")), fmt(fw_l10.get("hit")), fmt(fw_l20.get("hit"))]))
    fir_rows.append(("Miss Avg vs Par", [fmt(fw_b8.get("missed")), fmt(fw_l5.get("missed")), fmt(fw_l10.get("missed")), fmt(fw_l20.get("missed"))]))
    miss_b8 = calc_fir_miss_tendency(b8, g.courses)
    miss_l20 = calc_fir_miss_tendency(l20, g.courses)
    fir_rows.append(("Miss Left %", [fmt_pct(miss_b8.get("left")), "\u2014", "\u2014", fmt_pct(miss_l20.get("left"))]))
    fir_rows.append(("Miss Right %", [fmt_pct(miss_b8.get("right")), "\u2014", "\u2014", fmt_pct(miss_l20.get("right"))]))
    sections["fairways"] = {"label": "Fairways", "headline": "Fairway accuracy and scoring impact.", "rows": fir_rows}

    # 4. Greens
    gir_rows = []
    gir_rows.append(("GIR %", [fmt_pct(calc_gir_percent(b8)), fmt_pct(calc_gir_percent(l5)), fmt_pct(calc_gir_percent(l10)), fmt_pct(calc_gir_percent(l20))]))
    gb8 = calc_scoring_by_gir(b8, g.courses)
    gl5 = calc_scoring_by_gir(l5, g.courses)
    gl10 = calc_scoring_by_gir(l10, g.courses)
    gl20 = calc_scoring_by_gir(l20, g.courses)
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
    short_rows.append(("Scramble %", [fmt_pct(calc_scramble_percent(b8, g.courses)), fmt_pct(calc_scramble_percent(l5, g.courses)), fmt_pct(calc_scramble_percent(l10, g.courses)), fmt_pct(calc_scramble_percent(l20, g.courses))]))
    scr_b8 = calc_scramble_by_miss_direction(b8, g.courses)
    scr_l20 = calc_scramble_by_miss_direction(l20, g.courses)
    short_rows.append(("Scramble Short %", [fmt_pct(scr_b8.get("S")), "\u2014", "\u2014", fmt_pct(scr_l20.get("S"))]))
    short_rows.append(("Scramble Long %", [fmt_pct(scr_b8.get("LO")), "\u2014", "\u2014", fmt_pct(scr_l20.get("LO"))]))
    short_rows.append(("Scramble Left %", [fmt_pct(scr_b8.get("L")), "\u2014", "\u2014", fmt_pct(scr_l20.get("L"))]))
    short_rows.append(("Scramble Right %", [fmt_pct(scr_b8.get("R")), "\u2014", "\u2014", fmt_pct(scr_l20.get("R"))]))
    sections["shortgame"] = {"label": "Short Game", "headline": "Up-and-down scrambling performance.", "rows": short_rows}

    # 7. Momentum
    mom_b8 = calc_momentum_recovery(b8, g.courses)
    mom_l20 = calc_momentum_recovery(l20, g.courses)
    momentum_rows = []
    momentum_rows.append(("After Bogey Avg", [fmt(mom_b8.get("after_bogey_avg")), "\u2014", "\u2014", fmt(mom_l20.get("after_bogey_avg"))]))
    momentum_rows.append(("Recovery Rate %", [fmt_pct(mom_b8.get("recovery_rate")), "\u2014", "\u2014", fmt_pct(mom_l20.get("recovery_rate"))]))
    sections["momentum"] = {"label": "Momentum", "headline": "How you respond after bad holes.", "rows": momentum_rows}

    # 8. Bests
    bests = calc_personal_bests(g.all_rounds, g.courses)
    bests_data = [
        ("Lowest Gross", bests.get("best_gross"), bests.get("best_gross_date")),
        ("Lowest Diff", bests.get("best_diff"), bests.get("best_diff_date")),
        ("Most FIR", bests.get("most_fir"), bests.get("most_fir_date")),
        ("Most GIR", bests.get("most_gir"), bests.get("most_gir_date")),
        ("Fewest Putts", bests.get("fewest_putts"), bests.get("fewest_putts_date")),
    ]
    sections["bests"] = {"label": "Bests", "headline": "Your personal best performances.", "bests": bests_data}

    # 9. Trends
    chronological = list(reversed(g.all_rounds))
    trend_rows = []
    for r in chronological:
        d = r.get("date", "")
        if not r.get("total_gross") or r["total_gross"] == "0":
            continue
        if r.get("holes_selection", "all") != "all":
            continue
        course = g.courses.get(r.get("course", ""), {})
        par = int(course.get("par", 0))
        gross = int(r.get("total_gross", 0))
        trend_rows.append({
            "date": d,
            "course": r.get("course", ""),
            "score": gross,
            "vs_par": gross - par if par else None,
            "diff": r.get("differential", ""),
            "fir": fmt_pct(calc_fir_percent([r], g.courses)),
            "gir": fmt_pct(calc_gir_percent([r])),
            "putts": str(sum(int(h.get("putts", 0)) for h in r.get("holes", {}).values() if h.get("putts"))) if r.get("holes") else "\u2014",
        })
    sections["trends"] = {"label": "Trends", "headline": "Round-by-round performance history.", "trends": trend_rows}

    return render_template("stats.html", sections=sections, settings=g.settings, all_users=get_users())


@app.route("/settings")
@login_required
def settings_page():
    themes = ["dark", "light"]
    return render_template("settings.html", settings=g.settings, courses=g.courses, themes=themes,
                           current_page="settings", all_users=get_users())


@app.route("/settings/import", methods=["GET", "POST"])
@login_required
@requires_own_data
def settings_import():
    if request.method == "POST":
        uploaded = request.files.get("zipfile")
        if not uploaded:
            return render_template("settings_import.html", settings=g.settings, imported=None,
                                   error="No file provided", current_page="settings",
                                   all_users=get_users())

        try:
            zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
        except zipfile.BadZipFile:
            return render_template("settings_import.html", settings=g.settings, imported=None,
                                   error="Invalid zip file", current_page="settings",
                                   all_users=get_users())

        user_id = current_user.id
        courses_count = 0
        rounds_count = 0

        for name in zf.namelist():
            if name.endswith("courses.json"):
                courses_data = json.loads(zf.read(name))
                for cname, cdata in courses_data.items():
                    save_course(cdata, cname)
                    courses_count += 1
            elif "rounds/" in name and name.endswith(".json"):
                year_data = json.loads(zf.read(name))
                for date_str, date_rounds in year_data.items():
                    for idx, rdata in date_rounds.items():
                        save_round(rdata, date_str, int(idx), user_id)
                        rounds_count += 1
            elif name.endswith("settings.json"):
                settings_data = json.loads(zf.read(name))
                save_settings(settings_data, user_id)

        all_imported = get_all_rounds(user_id)
        chronological = list(reversed(all_imported))
        include_9hole = g.settings.get("include_9hole", True)
        for i, r in enumerate(chronological):
            window = chronological[:i + 1]
            hi = calc_handicap_index(window, include_9hole)
            if hi is not None:
                update_round_handicap(r["date"], r["index"], hi, user_id)

        return render_template("settings_import.html", settings=g.settings,
                               imported={"courses": courses_count, "rounds": rounds_count},
                               current_page="settings",
                               all_users=get_users())

    return render_template("settings_import.html", settings=g.settings, imported=None,
                           current_page="settings", all_users=get_users())


@app.route("/api/settings", methods=["PUT"])
@login_required
@requires_own_data
def api_settings_put():
    data = request.get_json()
    save_settings(data, current_user.id)
    return jsonify({"ok": True})


@app.route("/season")
@login_required
def season_summary():
    include_9hole = g.settings.get("include_9hole", True)

    if g.settings.get("season_enabled"):
        season_rounds = calc_season_rounds(g.all_rounds, g.settings)
    else:
        season_rounds = g.all_rounds

    hi = calc_handicap_index(g.all_rounds, include_9hole)
    journey = calc_hi_journey(g.all_rounds, season_rounds, hi)
    most_played = calc_most_played_course(season_rounds)
    golfiest = calc_golfiest_month(season_rounds)
    common_day = calc_most_common_day(season_rounds)
    best_round = calc_best_single_round(season_rounds)
    best_stretch = calc_best_3round_stretch(season_rounds)
    biggest_improvement = calc_biggest_improvement(season_rounds)
    first_score_ms = calc_first_score_milestone(season_rounds, g.all_rounds)
    first_hi_ms = calc_first_hi_milestone(season_rounds, g.all_rounds)
    breakdown = calc_score_breakdown(season_rounds, g.courses)
    hole_in_ones = calc_hole_in_ones(season_rounds, g.courses)
    best_gir = calc_best_gir_round(season_rounds)
    best_fir = calc_best_fir_round(season_rounds, g.courses)
    walking_miles = calc_season_yardage(season_rounds, g.courses, "walking")
    riding_miles = calc_season_yardage(season_rounds, g.courses, "riding")
    penalty_free = calc_penalty_free_rounds(season_rounds)
    rounds_count = len(season_rounds)
    total_rounds = calc_rounds_total(g.all_rounds)

    return render_template("season_summary.html",
        settings=g.settings,
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
        all_users=get_users(),
    )


@app.route("/admin/invites", methods=["GET", "POST"])
@login_required
def admin_invites():
    if not current_user.is_admin:
        return "Forbidden", 403

    if request.method == "POST":
        code = create_invite_code(current_user.id)
        base_url = request.host_url.rstrip("/")
        return render_template("admin_invites.html", settings=g.settings,
                               codes=get_invite_codes(), new_code=code, base_url=base_url,
                               all_users=get_users())

    return render_template("admin_invites.html", settings=g.settings,
                           codes=get_invite_codes(), new_code=None, base_url=None,
                           all_users=get_users())


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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data", default=None)
    args = parser.parse_args()

    if args.data:
        data_dir = Path(args.data)
    else:
        data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    secret_key = os.environ.get("SECRET_KEY", "")
    default_keys = ("REPLACE_ME", "dev-key-", "change-me", "secret")
    if not secret_key or secret_key == "":
        print("ERROR: SECRET_KEY environment variable is required.", file=sys.stderr)
        print("Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"", file=sys.stderr)
        sys.exit(1)
    if any(secret_key.startswith(dk) for dk in default_keys):
        print("ERROR: SECRET_KEY must not be a default/placeholder value.", file=sys.stderr)
        sys.exit(1)
    app.secret_key = secret_key

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()

    port = args.port if args.port is not None else find_free_port()
    url = f"http://{args.host}:{port}"

    chrome_proc = None
    if args.host == "127.0.0.1" and os.environ.get("FLASK_DEBUG") != "0":
        chrome = _find_chrome()
        if chrome:
            chrome_proc = subprocess.Popen(
                [chrome, f"--app={url}", "--start-maximized"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open(url)

    if chrome_proc:
        def _watch_chrome():
            chrome_proc.wait()
            _log.info("Chrome window closed — shutting down")
            os._exit(0)
        threading.Thread(target=_watch_chrome, daemon=True).start()

    from waitress import serve
    print(f"PinSheet -> http://{args.host}:{port}")
    serve(app, host=args.host, port=port)


if __name__ == "__main__":
    main()
