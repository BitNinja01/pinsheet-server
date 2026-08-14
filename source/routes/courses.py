from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import save_course, delete_course, rename_course
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context
from source.plugin import fire_hook


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


_COURSE_NUMERIC_TEE_FIELDS = (
    "yardage", "rating", "slope",
    "front_rating", "front_slope", "back_rating", "back_slope",
)

# Slope/rating (and their front_/back_ variants) are divisors/terms in the
# WHS Course Handicap and Score Differential formulas
# (calc_course_handicap, calc_round_dif). Unlike blank/missing, "0" (and
# negative values) parse fine as a float but are domain-invalid --
# calc_round_dif divides by slope, so slope<=0 is a ZeroDivisionError
# waiting to happen at round-save time (CV-001). "yardage" has no such
# constraint (a 0 yardage is merely unhelpful, not divide-by-zero
# dangerous), so it is deliberately excluded from this stricter check.
_POSITIVE_ONLY_TEE_FIELDS = ("rating", "slope", "front_rating", "front_slope", "back_rating", "back_slope")


def _coerce_course_numerics(data: dict, *, strict: bool = True) -> str | None:
    """Validate tee/hole numeric fields on an incoming course payload.

    Stored-XSS fix (finding U1 / GH#68): these fields are rendered in
    course_detail.html without HTML-escaping-defeating filters, so any
    attacker-controlled string (e.g. "<img src=x onerror=...>") accepted
    here would be persisted verbatim and executed in every viewer's
    session. Rejecting non-numeric values at the write path closes that
    hole regardless of template behavior.

    strict=True (API write path, courses.py): the first present,
      non-empty, non-numeric OR non-positive (slope/rating only) value
      causes this to return an error message describing the offending
      tee/field; the payload is left untouched so the caller can 400
      before anything is persisted.
    strict=False (zip import path, settings.py): non-numeric/non-positive
      values are blanked out in place instead of rejected, so a single bad
      course in a batch import doesn't fail the whole import; this always
      returns None.

    Blank/missing values are left as-is in both modes (blank is allowed).
    A non-positive slope/rating ("0", "-5", ...) is NOT treated as blank --
    it is domain-invalid (see `_POSITIVE_ONLY_TEE_FIELDS` above) and is
    rejected/blanked the same as a non-numeric value.
    """
    tees = data.get("tees")
    if not isinstance(tees, dict):
        return None
    for tee_name, tee in tees.items():
        if not isinstance(tee, dict):
            continue
        for field in _COURSE_NUMERIC_TEE_FIELDS:
            val = tee.get(field)
            if val in (None, ""):
                continue
            try:
                parsed = float(val)
            except (TypeError, ValueError):
                if strict:
                    return f"tee '{tee_name}' field '{field}' must be numeric"
                tee[field] = ""
                continue
            if field in _POSITIVE_ONLY_TEE_FIELDS and parsed <= 0:
                if strict:
                    return f"tee '{tee_name}' field '{field}' must be a positive number"
                tee[field] = ""
        yardages = tee.get("yardages")
        if isinstance(yardages, dict):
            for hole_num, yval in list(yardages.items()):
                if yval in (None, ""):
                    continue
                try:
                    float(yval)
                except (TypeError, ValueError):
                    if strict:
                        return f"tee '{tee_name}' yardage for hole {hole_num} must be numeric"
                    yardages[hole_num] = ""
    return None


def register_courses_routes(app, csrf):
    @app.route("/courses/new")
    @login_required
    def course_entry():
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

        err = _coerce_course_numerics(data)
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
        for r in get_all_rounds_for_user():
            if r.course == name:
                return jsonify({"error": "Cannot delete course with existing rounds"}), 409
        delete_course(name)
        return jsonify({"ok": True})

    @app.route("/api/courses/<name>", methods=["PUT"])
    @login_required
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

        err = _validate_hole_keys(data.get("holes", {}))
        if err:
            return jsonify({"error": err}), 400

        err = _coerce_course_numerics(data)
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
