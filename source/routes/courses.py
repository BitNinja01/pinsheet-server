from flask import render_template, request, jsonify, g, current_app, redirect, url_for
from flask_login import login_required, current_user

from store import save_course, delete_course, rename_course
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context
from source.plugin import fire_hook


def _course_write_forbidden():
    """Return a 403 response if the caller may not mutate courses, else None.

    Courses are shared global data referenced by every user's rounds, so
    create/edit/delete is restricted. Session users must be admins (mirrors
    admin.py). API-key identities must carry the ``courses:write`` scope.
    """
    if getattr(current_user, "via_api_key", False):
        granted = getattr(current_user, "api_permissions", None) or []
        if "courses:write" not in granted:
            return jsonify({"error": "insufficient_scope", "required": "courses:write"}), 403
        return None
    if not current_user.is_admin:
        return "Forbidden", 403
    return None


def _validate_hole_keys(holes) -> str | None:
    """Return an error message if the holes payload uses the wrong stroke-index key."""
    if not isinstance(holes, dict):
        return "holes must be an object"
    for num, hole in holes.items():
        if not isinstance(hole, dict):
            continue
        if "index" in hole:
            return f"hole {num}: stroke index must use key 'hole_index', not 'index'"
        if "hole_index" not in hole and hole:
            return f"hole {num}: stroke index must use key 'hole_index'"
    return None


def register_courses_routes(app, csrf):
    @app.route("/courses/new")
    @login_required
    def course_entry():
        if not current_user.is_admin:
            return redirect(url_for("course_list"))
        return render_template("course_entry.html", **base_context(
            courses=get_courses(),
        ))

    @app.route("/courses")
    @login_required
    def course_list():
        course_data = []
        for name, course in get_courses().items():
            location = course.get("location", "")
            play_count = 0
            last_played = None
            for r in get_all_rounds_for_user():
                if r.course == name:
                    play_count += 1
                    if last_played is None or r.date > last_played:
                        last_played = r.date

            course_data.append({
                "name": name,
                "location": location,
                "play_count": play_count,
                "last_played": last_played,
            })

        course_data.sort(key=lambda c: c["name"].lower())

        return render_template("courses.html", **base_context(
            courses=course_data,
        ))

    @app.route("/courses/<name>")
    @login_required
    def course_detail(name):
        course = get_courses().get(name)
        if not course:
            return "Course not found", 404

        edit_mode = request.args.get("edit") == "1" and current_user.is_admin

        play_count = 0
        first_played = None
        last_played = None
        tee_scores = {}
        for r in get_all_rounds_for_user():
            if r.course == name:
                play_count += 1
                d = r.date
                if first_played is None or d < first_played:
                    first_played = d
                if last_played is None or d > last_played:
                    last_played = d

                # Collect gross scores per tee for full 18-hole rounds only.
                if r.holes_selection == "all" and r.total_gross and r.total_gross != "0":
                    try:
                        gross = int(r.total_gross)
                    except (ValueError, TypeError):
                        gross = None
                    if gross is not None:
                        tee_scores.setdefault(r.tees or "—", []).append(gross)

        score_stats = []
        for tee_name, scores in tee_scores.items():
            score_stats.append({
                "tee": tee_name,
                "rounds": len(scores),
                "best": min(scores),
                "avg": round(sum(scores) / len(scores), 1),
                "worst": max(scores),
            })
        score_stats.sort(key=lambda s: s["tee"].lower())

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
                y = yardages_data.get(hn)
                if y is None:
                    y = h.get("tees", {}).get(tee_name, "")
                yardages[tee_name] = y
            hole_rows.append({
                "num": int(hn),
                "par": h.get("par", ""),
                "index": h.get("hole_index", h.get("index", "")),
                "yardages": yardages,
            })

        return render_template("course_detail.html", **base_context(
            course=course, name=name, tees=tees, holes=hole_rows,
            play_count=play_count, first_played=first_played, last_played=last_played,
            score_stats=score_stats, edit_mode=edit_mode,
        ))

    @app.route("/api/courses", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_courses_post():
        forbidden = _course_write_forbidden()
        if forbidden:
            return forbidden
        data = request.get_json()
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name is required"}), 400

        location = data.get("location", {})
        if not isinstance(location, dict) or not location.get("city") or not location.get("state/province") or not location.get("country"):
            return jsonify({"error": "City, state/province, and country are required"}), 400

        err = _validate_hole_keys(data.get("holes", {}))
        if err:
            return jsonify({"error": err}), 400

        course = {
            "location": location,
            "tees": data.get("tees", {}),
            "holes": data.get("holes", {}),
            "par": data.get("par", 0),
        }

        save_course(course, name)
        fire_hook("on_course_saved", course_name=name, course_data=course, user_id=current_user.id, db_path=app.config["DB_PATH"])
        return jsonify({"ok": True, "name": name})

    @app.route("/api/courses/<name>", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def api_courses_delete(name):
        forbidden = _course_write_forbidden()
        if forbidden:
            return forbidden
        for r in get_all_rounds_for_user():
            if r.course == name:
                return jsonify({"error": "Cannot delete course with existing rounds"}), 409
        delete_course(name)
        return jsonify({"ok": True})

    @app.route("/api/courses/<name>", methods=["PUT"])
    @login_required
    @csrf.exempt
    def api_courses_put(name):
        forbidden = _course_write_forbidden()
        if forbidden:
            return forbidden
        if not get_courses().get(name):
            return jsonify({"error": "Course not found"}), 404

        data = request.get_json()
        new_name = data.get("name", "").strip()
        if not new_name:
            return jsonify({"error": "Name is required"}), 400

        if new_name != name and get_courses().get(new_name):
            return jsonify({"error": "A course with that name already exists"}), 409

        location = data.get("location", {})
        if not isinstance(location, dict) or not location.get("city") or not location.get("state/province") or not location.get("country"):
            return jsonify({"error": "City, state/province, and country are required"}), 400

        err = _validate_hole_keys(data.get("holes", {}))
        if err:
            return jsonify({"error": err}), 400

        if new_name != name:
            rename_course(name, new_name)

        course = {
            "location": location,
            "tees": data.get("tees", {}),
            "holes": data.get("holes", {}),
            "par": data.get("par", 0),
        }

        save_course(course, new_name)
        fire_hook("on_course_saved", course_name=new_name, course_data=course, user_id=current_user.id, db_path=app.config["DB_PATH"])
        return jsonify({"ok": True, "name": new_name})
