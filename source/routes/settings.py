import io
import json
import zipfile
import logging

from flask import render_template, request, jsonify, g, current_app, redirect, url_for
from flask_login import login_required, current_user

from store import (
    save_settings, save_course, save_round,
    get_all_rounds, update_round_handicap, update_round_differential,
    get_slope_rating, reshape_course_data,
    create_api_key, list_api_keys, revoke_api_key, API_KEY_PERMISSIONS,
)
from calc import calc_handicap_index
from source.request_data import get_settings, get_courses, base_context
from source.routes.courses import _coerce_course_numerics


_log = logging.getLogger("pinsheet")

# Zip-import decompression bounds (CWE-400 / zip-bomb defense). MAX_CONTENT_LENGTH
# caps the compressed upload; these cap the uncompressed expansion, which a small
# compressed payload can otherwise blow up into.
MAX_IMPORT_ENTRIES = 1000            # max members in the archive
MAX_ENTRY_UNCOMPRESSED = 10 * 1024 * 1024   # 10 MB per member
MAX_TOTAL_UNCOMPRESSED = 50 * 1024 * 1024   # 50 MB aggregate


def register_settings_routes(app, limiter, csrf):
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
    @limiter.limit("5 per minute")
    def settings_import():
        def _import_error(msg):
            return render_template("settings_import.html", **base_context(
                current_page="settings",
                imported=None, error=msg,
            ))

        if request.method == "POST":
            uploaded = request.files.get("zipfile")
            if not uploaded:
                return _import_error("No file provided")

            try:
                zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
            except zipfile.BadZipFile:
                return _import_error("Invalid zip file")

            # Reject decompression bombs before reading any member: bound the
            # entry count and both per-entry and aggregate uncompressed size.
            infos = zf.infolist()
            if len(infos) > MAX_IMPORT_ENTRIES:
                return _import_error("Archive has too many entries")
            total_uncompressed = 0
            for info in infos:
                if info.file_size > MAX_ENTRY_UNCOMPRESSED:
                    return _import_error("Archive entry too large")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
                    return _import_error("Archive contents too large")

            # Header file_size can be spoofed, so also enforce the real
            # decompressed size while streaming each member we actually read.
            def _read_member(member_name):
                with zf.open(member_name) as fh:
                    data = fh.read(MAX_ENTRY_UNCOMPRESSED + 1)
                if len(data) > MAX_ENTRY_UNCOMPRESSED:
                    raise ValueError("member too large")
                return data

            user_id = current_user.id
            courses_count = 0
            rounds_count = 0

            try:
                for name in zf.namelist():
                    if name.endswith("courses.json"):
                        courses_data = json.loads(_read_member(name))
                        for cname, cdata in courses_data.items():
                            # Same numeric-field validation as the API write path
                            # (finding U1 / GH#68), but lenient: blank out any
                            # non-numeric value instead of rejecting the import.
                            _coerce_course_numerics(cdata, strict=False)
                            # TUI-era exports carry per-hole tees and possibly
                            # `index` stroke keys; store canonically.
                            cdata = reshape_course_data(cdata)
                            save_course(cdata, cname)
                            courses_count += 1
                    elif "rounds/" in name and name.endswith(".json"):
                        year_data = json.loads(_read_member(name))
                        for date_str, date_rounds in year_data.items():
                            for idx, rdata in date_rounds.items():
                                save_round(rdata, date_str, int(idx), user_id)
                                rounds_count += 1
                    elif name.endswith("settings.json"):
                        settings_data = json.loads(_read_member(name))
                        save_settings(settings_data, user_id)
            except ValueError:
                return _import_error("Archive entry too large")

            all_imported = get_all_rounds(user_id)
            chronological = list(reversed(all_imported))
            total = len(all_imported)
            courses_data = get_courses()
            include_9hole = get_settings().get("include_9hole", True)
            for i, r in enumerate(chronological):
                if not r.differential or r.differential == "0":
                    course_data = courses_data.get(r.course)
                    if course_data:
                        tee_data = course_data.get("tees", {}).get(r.tees)
                        if tee_data and r.total_gross and r.total_gross != "0":
                            slope, rating = get_slope_rating(tee_data, r.holes_selection)
                            diff = round((113 / slope) * (float(r.total_gross) - rating), 1)
                            update_round_differential(r.date, r.index, diff, user_id)
                            # Keep the in-memory object in sync with the DB write so the
                            # handicap window below sees the fresh differential (not stale "0").
                            r.differential = str(diff)
                # WHS Rule 5.2: calc_handicap_index requires most-recent-first
                # input and windows to the most recent 20 ELIGIBLE
                # differentials internally. `r` is chronological[i]
                # (oldest-first); its position in the original
                # most-recent-first `all_imported` is `idx`, so
                # `all_imported[idx:]` is "all rounds up to and including r,
                # in most-recent-first order" -- the old oldest-first,
                # unbounded `chronological[:i + 1]` violated the contract.
                idx = total - 1 - i
                history_most_recent_first = all_imported[idx:]
                hi = calc_handicap_index(history_most_recent_first, include_9hole)
                if hi is not None:
                    update_round_handicap(r.date, r.index, hi, user_id)

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
    @limiter.limit("10 per minute")  # issue #75: throttle credential minting
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
