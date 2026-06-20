import json
import logging
import secrets
import string

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from store import get_clubs, save_club, delete_club, get_bag_slots, save_bag_slots, get_distinct_club_field_values
from source.request_data import base_context

_log = logging.getLogger("pinsheet")

BAG_SIZE = 14
CAT_ORDER = ["Drivers", "Woods", "Hybrids", "Irons", "Wedges", "Putters"]


def _club_id() -> str:
    return "c" + secrets.token_hex(4)


def register_bag_routes(app, csrf):
    @app.route("/bag")
    @login_required
    def bag_page():
        user_id = current_user.id
        clubs = get_clubs(user_id)
        slots = get_bag_slots(user_id)
        clubs_by_id = {c["id"]: c for c in clubs}
        ac_fields = ["brand", "model", "shaft_brand", "shaft", "grip"]
        autocomplete_data = {f: get_distinct_club_field_values(f) for f in ac_fields}
        return render_template("bag.html", **base_context(
            current_page="bag",
            clubs=clubs,
            clubs_by_id=clubs_by_id,
            clubs_json=json.dumps(clubs_by_id),
            slots=slots,
            slots_json=json.dumps(slots),
            bag_size=BAG_SIZE,
            cat_order=CAT_ORDER,
            autocomplete_data=autocomplete_data,
        ))

    @app.route("/bag/club", methods=["POST"])
    @csrf.exempt
    @login_required
    def bag_save_club():
        data = request.get_json(force=True)
        club_id = data.get("id", _club_id())
        club_data = {
            "id": club_id,
            "category": data.get("category", "Irons"),
            "club": data.get("club", ""),
            "number": data.get("number", ""),
            "brand": data.get("brand", ""),
            "model": data.get("model", ""),
            "loft": data.get("loft", ""),
            "lie": data.get("lie", ""),
            "length": data.get("length", ""),
            "shaft_flex": data.get("shaft_flex", ""),
            "shaft_brand": data.get("shaft_brand", ""),
            "shaft": data.get("shaft", ""),
            "grip": data.get("grip", ""),
            "sw": data.get("sw", ""),
            "carry": data.get("carry"),
        }
        save_club(club_data, current_user.id)
        return jsonify({"ok": True, "id": club_id})

    @app.route("/bag/club/<club_id>/delete", methods=["POST"])
    @csrf.exempt
    @login_required
    def bag_delete_club(club_id):
        delete_club(club_id, current_user.id)
        return jsonify({"ok": True})

    @app.route("/bag/slots", methods=["POST"])
    @csrf.exempt
    @login_required
    def bag_save_slots():
        data = request.get_json(force=True)
        save_bag_slots(data.get("slots", []), current_user.id)
        return jsonify({"ok": True})
