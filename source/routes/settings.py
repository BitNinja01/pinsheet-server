import io
import json
import zipfile
import logging

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import (
    save_settings, get_courses, save_course, save_round,
    get_all_rounds, update_round_handicap, get_users,
)
from calc import calc_handicap_index
from source._helpers import requires_own_data
from source.calc.models import dict_to_round

_log = logging.getLogger("pinsheet")


def register_settings_routes(app, csrf):
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
                window = [dict_to_round(w) for w in chronological[:i + 1]]
                hi = calc_handicap_index(window, include_9hole)
                if hi is not None:
                    update_round_handicap(r["date"], r["index"], hi, user_id)

            return render_template("settings_import.html", settings=g.settings,
                                   imported={"courses": courses_count, "rounds": rounds_count},
                                   current_page="settings",
                                   all_users=get_users())

        return render_template("settings_import.html", settings=g.settings, imported=None,
                               current_page="settings", all_users=get_users())

    @csrf.exempt
    @app.route("/api/settings", methods=["PUT"])
    @login_required
    @requires_own_data
    def api_settings_put():
        data = request.get_json()
        _log.info("api_settings_put user_id=%s, data=%s", current_user.id, data)
        save_settings(data, current_user.id)
        return jsonify({"ok": True})
