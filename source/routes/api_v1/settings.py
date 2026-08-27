"""GET/PUT /api/v1/settings -- owner-scoped (`WHERE user_id = ?`)."""
import logging

from apiflask import APIBlueprint
from flask_login import current_user

from source.auth_keys import require_permission
from source.routes.api_v1 import scopes
from source.routes.api_v1.errors import require_json_body
from source.routes.api_v1.schemas import SettingsInSchema, SettingsOutSchema
from store import load_settings, save_settings

_log = logging.getLogger("pinsheet")

settings_v1 = APIBlueprint("settings_v1", __name__, url_prefix="/api/v1/settings")


@settings_v1.route("", methods=["GET"])
@require_permission(scopes.SETTINGS_READ, contract="problem", permissive_pending=True)
@settings_v1.output(SettingsOutSchema)
def get_settings():
    return load_settings(current_user.id)


@settings_v1.route("", methods=["PUT"])
@require_permission(scopes.SETTINGS_WRITE, contract="problem", permissive_pending=True)
@require_json_body
@settings_v1.input(SettingsInSchema)
@settings_v1.output(SettingsOutSchema)
def update_settings(json_data):
    # user_id is bound EXACTLY here, server-side, from current_user.id --
    # SettingsInSchema has no user_id field at all. store.save_settings
    # merges json_data into the existing stored dict (store.py:47-51); the
    # schema still allowlists which fields a v1 caller may influence.
    save_settings(json_data, current_user.id)
    _log.info("api_v1.settings: updated user_id=%s", current_user.id)
    return load_settings(current_user.id)
