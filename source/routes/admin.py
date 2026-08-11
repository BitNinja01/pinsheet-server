import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from store import set_plugin_state, recompute_all_handicaps

_log = logging.getLogger("pinsheet")


def register_admin_routes(app, csrf):
    @csrf.exempt
    @app.route("/api/admin/plugin-state", methods=["POST"])
    @login_required
    def api_admin_plugin_state():
        if not current_user.is_admin:
            return "Forbidden", 403

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400
        plugin_name = data.get("plugin_name", "")
        enabled = bool(data.get("enabled", True))

        if not plugin_name:
            return jsonify({"error": "plugin_name required"}), 400

        set_plugin_state(plugin_name, enabled)
        _log.info("admin: plugin %s %s", plugin_name, "enabled" if enabled else "disabled")

        return jsonify({"ok": True})

    @csrf.exempt
    @app.route("/api/admin/recompute-handicaps", methods=["POST"])
    @login_required
    def api_admin_recompute_handicaps():
        """Force a resync of every user's differentials + handicap index against
        current course data. Same forced pass as scripts/resync_handicaps.py;
        preserves locked differentials and the "0" skip sentinel."""
        if not current_user.is_admin:
            return "Forbidden", 403

        updated = recompute_all_handicaps(force=True)
        _log.info("admin: forced handicap resync by user %s — %d row(s) updated",
                  current_user.id, updated)
        return jsonify({"ok": True, "updated": updated})
