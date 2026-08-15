"""GET/POST/PUT/DELETE /api/v1/courses -- shared, global catalog (ADR-011).

Full CRUD, gated by opt-in `courses:write`/`courses:delete` scopes (a key
must be explicitly granted these at creation -- they are never on by
default, `store.py:1012`). There is no `user_id` to filter on: courses are a
shared catalog by design on this closed, invite-gated instance (ADR-011).
"""
import logging

from apiflask import APIBlueprint
from flask_login import current_user

from source.auth_keys import require_permission
from source.routes.api_v1 import scopes
from source.routes.api_v1.errors import problem, require_json_body
from source.routes.api_v1.schemas import (
    CourseCreateInSchema,
    CourseListOutSchema,
    CourseOutSchema,
    CourseUpdateInSchema,
)
from store import delete_course as _delete_course_row
from store import course_in_use_by_anyone, get_courses, rename_course, save_course

_log = logging.getLogger("pinsheet")

courses_v1 = APIBlueprint("courses_v1", __name__, url_prefix="/api/v1/courses")


@courses_v1.route("", methods=["GET"])
@require_permission(scopes.COURSES_READ, contract="problem")
@courses_v1.output(CourseListOutSchema)
def list_courses():
    courses = get_courses()
    return {"courses": [{"name": name, **data} for name, data in courses.items()]}


@courses_v1.route("/<name>", methods=["GET"])
@require_permission(scopes.COURSES_READ, contract="problem")
@courses_v1.output(CourseOutSchema)
def get_course(name):
    course = get_courses().get(name)
    if course is None:
        return problem(404, "Course not found.")
    return {"name": name, **course}


@courses_v1.route("", methods=["POST"])
@require_permission(scopes.COURSES_WRITE, contract="problem", enforce_now=True)
@require_json_body
@courses_v1.input(CourseCreateInSchema)
@courses_v1.output(CourseOutSchema, status_code=201)
def create_course(json_data):
    name = json_data["name"]
    course = {
        "location": json_data["location"],
        "tees": json_data.get("tees", {}),
        "holes": json_data.get("holes", {}),
        "par": json_data.get("par", 0),
    }
    save_course(course, name)
    _log.info("api_v1.courses: created name=%s user_id=%s", name, current_user.id)
    return {"name": name, **course}, 201


@courses_v1.route("/<name>", methods=["PUT"])
@require_permission(scopes.COURSES_WRITE, contract="problem", enforce_now=True)
@require_json_body
@courses_v1.input(CourseUpdateInSchema)
@courses_v1.output(CourseOutSchema)
def update_course(name, json_data):
    if get_courses().get(name) is None:
        return problem(404, "Course not found.")

    new_name = json_data["name"]
    if new_name != name and get_courses().get(new_name) is not None:
        return problem(409, "A course with that name already exists.")

    if new_name != name:
        rename_course(name, new_name)

    course = {
        "location": json_data["location"],
        "tees": json_data.get("tees", {}),
        "holes": json_data.get("holes", {}),
        "par": json_data.get("par", 0),
    }
    save_course(course, new_name)
    _log.info("api_v1.courses: updated name=%s -> %s user_id=%s", name, new_name, current_user.id)
    return {"name": new_name, **course}


@courses_v1.route("/<name>", methods=["DELETE"])
@require_permission(scopes.COURSES_DELETE, contract="problem", enforce_now=True)
def delete_course(name):
    if get_courses().get(name) is None:
        return problem(404, "Course not found.")
    # Revision 2, SEC-3: catalog-wide usage check. The original build ported
    # the legacy conflict-check's exact (self-scoped, `get_all_rounds
    # (current_user.id)`-only) semantics, matching what courses.py:160-162
    # does for a SESSION user deleting their own course. But courses are a
    # SHARED, global catalog (ADR-011) -- a self-scoped check only sees the
    # deleting caller's own rounds, missing every OTHER user's rounds
    # referencing the same course. Deleting a course another user still has
    # rounds on would silently orphan their data (`course_name` becomes a
    # dangling reference, `get_courses().get(r.course)` -> None everywhere
    # that round is displayed/computed, including this endpoint's own
    # `stats.py` catalog dict). `course_in_use_by_anyone` queries `rounds`
    # directly across ALL users for exactly this reason.
    if course_in_use_by_anyone(name):
        return problem(409, "Cannot delete course with existing rounds.")
    _delete_course_row(name)
    _log.info("api_v1.courses: deleted name=%s user_id=%s", name, current_user.id)
    return "", 204
