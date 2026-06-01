from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import save_course, delete_course, rename_course
from source.routes.auth import requires_own_data
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context
from source.plugin import fire_hook


def register_courses_routes(app, csrf):
    @app.route("/courses/new")
    @login_required
    def course_entry():
        if not g.is_own_data:
            return "You can only enter data for yourself.", 403
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

        edit_mode = request.args.get("edit") == "1"

        play_count = 0
        first_played = None
        last_played = None
        for r in get_all_rounds_for_user():
            if r.course == name:
                play_count += 1
                d = r.date
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
                y = yardages_data.get(hn)
                if y is None:
                    y = h.get("tees", {}).get(tee_name, "")
                yardages[tee_name] = y
            hole_rows.append({
                "num": int(hn),
                "par": h.get("par", ""),
                "index": h.get("index", h.get("hole_index", "")),
                "yardages": yardages,
            })

        return render_template("course_detail.html", **base_context(
            course=course, name=name, tees=tees, holes=hole_rows,
            play_count=play_count, first_played=first_played, last_played=last_played,
            edit_mode=edit_mode,
        ))

    @app.route("/api/courses", methods=["POST"])
    @login_required
    @requires_own_data
    @csrf.exempt
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
        fire_hook("on_course_saved", course_name=name, course_data=course, user_id=current_user.id, db_path=app.config["DB_PATH"])
        return jsonify({"ok": True, "name": name})

    @app.route("/api/courses/<name>", methods=["DELETE"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_courses_delete(name):
        for r in get_all_rounds_for_user():
            if r.course == name:
                return jsonify({"error": "Cannot delete course with existing rounds"}), 409
        delete_course(name)
        return jsonify({"ok": True})

    @app.route("/api/courses/<name>", methods=["PUT"])
    @login_required
    @requires_own_data
    @csrf.exempt
    def api_courses_put(name):
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
