import logging

from flask import request, jsonify, current_app
from flask_login import login_required, current_user

from source.store import set_plugin_state, get_plugin_states

_log = logging.getLogger("pinsheet")


def register_admin_routes(app, csrf):
    @csrf.exempt
    @app.route("/api/admin/plugin-state", methods=["POST"])
    @login_required
    def api_admin_plugin_state():
        if not current_user.is_admin:
            return "Forbidden", 403

        data = request.get_json()
        plugin_name = data.get("plugin_name", "")
        enabled = bool(data.get("enabled", True))

        if not plugin_name:
            return jsonify({"error": "plugin_name required"}), 400

        set_plugin_state(plugin_name, enabled)
        _log.info("admin: plugin %s %s", plugin_name, "enabled" if enabled else "disabled")

        return jsonify({"ok": True})
