import io
import json
import zipfile
import logging

from flask import render_template, request, jsonify, g, current_app, redirect, url_for
from flask_login import login_required, current_user

from store import (
    save_settings, save_course, save_round,
    recompute_handicaps_for_user,
    create_api_key, list_api_keys, revoke_api_key, API_KEY_PERMISSIONS,
)
from source.request_data import get_courses, base_context


_log = logging.getLogger("pinsheet")


def register_settings_routes(app, csrf):
    @app.route("/settings")
    @login_required
    def settings_page():
        themes = ["dark", "light"]
        return render_template("settings.html", **base_context(
            current_page="settings",
            courses=get_courses(), themes=themes,
        ))

    @app.route("/settings/import", methods=["GET", "POST"])
    @login_required
    def settings_import():
        if request.method == "POST":
            uploaded = request.files.get("zipfile")
            if not uploaded:
                return render_template("settings_import.html", **base_context(
                    current_page="settings",
                    imported=None, error="No file provided",
                ))

            try:
                zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
            except zipfile.BadZipFile:
                return render_template("settings_import.html", **base_context(
                    current_page="settings",
                    imported=None, error="Invalid zip file",
                ))

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

            # Backfill differentials and (re)compute Handicap Index for every
            # imported round via the single authoritative sequential path --
            # this keeps the WHS Rule 5.2 windowing AND the Rule 5.7 (Low HI)
            # / Rule 5.8 (soft/hard cap) logic in exactly one place instead
            # of duplicating it here (see `recompute_handicaps_for_user`).
            recompute_handicaps_for_user(user_id)

            return render_template("settings_import.html", **base_context(
                current_page="settings",
                imported={"courses": courses_count, "rounds": rounds_count},
            ))

        return render_template("settings_import.html", **base_context(
            current_page="settings",
            imported=None,
        ))

    @csrf.exempt
    @app.route("/api/settings", methods=["PUT"])
    @login_required
    def api_settings_put():
        data = request.get_json()
        _log.info("api_settings_put user_id=%s, data=%s", current_user.id, data)
        save_settings(data, current_user.id)
        return jsonify({"ok": True})

    # --- API-key management UI (UC-APIKEY-001) — session-only, CSRF-protected ---
    @app.route("/settings/api-keys")
    @login_required
    def api_keys_page():
        return render_template("api_keys.html", **base_context(
            current_page="settings",
            keys=list_api_keys(current_user.id),
            permission_options=list(API_KEY_PERMISSIONS),
            new_key=None,
            new_key_meta=None,
        ))

    @app.route("/settings/api-keys", methods=["POST"])
    @login_required
    def api_keys_create():
        label = request.form.get("label", "").strip() or "Unnamed key"
        permissions = [p for p in request.form.getlist("permissions") if p in API_KEY_PERMISSIONS]
        plaintext, meta = create_api_key(current_user.id, label, permissions)
        # Render the plaintext exactly once; it is never stored or shown again.
        return render_template("api_keys.html", **base_context(
            current_page="settings",
            keys=list_api_keys(current_user.id),
            permission_options=list(API_KEY_PERMISSIONS),
            new_key=plaintext,
            new_key_meta=meta,
        ))

    @app.route("/settings/api-keys/<int:key_id>/revoke", methods=["POST"])
    @login_required
    def api_keys_revoke(key_id):
        revoke_api_key(key_id, current_user.id)
        return redirect(url_for("api_keys_page"))
