import os
import json
import logging
import webbrowser
from pathlib import Path
from datetime import date

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
    calc_expected_9hole_dif,
)
from calc.scoring import (
    calc_scoring_average, STAT_CATALOG, DEFAULT_DASHBOARD_STATS,
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

    return render_template("dashboard.html", panels=panels, settings=settings)


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
