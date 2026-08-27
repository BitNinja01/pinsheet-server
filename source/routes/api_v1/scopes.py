"""Scope-string constants + endpoint -> scope map for /api/v1 (ADR-004/ADR-007).

`ENDPOINT_SCOPE_MAP` is the single source of truth: eng-qa's
`test_every_v1_route_has_required_scope` (Step 5) iterates `app.url_map` for
every `/api/v1/*` rule and asserts it appears here exactly once, closing the
"new route added without a scope decorator" regression class named in the
architecture's AT-2 I1 leaf.
"""

COURSES_READ = "courses:read"
COURSES_WRITE = "courses:write"
COURSES_DELETE = "courses:delete"
ROUNDS_READ = "rounds:read"
ROUNDS_WRITE = "rounds:write"
ROUNDS_DELETE = "rounds:delete"
STATS_READ = "stats:read"
SETTINGS_READ = "settings:read"
SETTINGS_WRITE = "settings:write"

# Keyed by Flask endpoint name ("<blueprint_name>.<view_func_name>").
ENDPOINT_SCOPE_MAP: dict[str, str] = {
    "courses_v1.list_courses": COURSES_READ,
    "courses_v1.get_course": COURSES_READ,
    "courses_v1.create_course": COURSES_WRITE,
    "courses_v1.update_course": COURSES_WRITE,
    "courses_v1.delete_course": COURSES_DELETE,
    "rounds_v1.list_rounds": ROUNDS_READ,
    "rounds_v1.get_round": ROUNDS_READ,
    "rounds_v1.create_round": ROUNDS_WRITE,
    "rounds_v1.update_round": ROUNDS_WRITE,
    "rounds_v1.delete_round": ROUNDS_DELETE,
    "stats_v1.get_stats": STATS_READ,
    "settings_v1.get_settings": SETTINGS_READ,
    "settings_v1.update_settings": SETTINGS_WRITE,
}
