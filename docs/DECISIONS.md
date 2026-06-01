# Decisions

Durable architectural and design decisions. Appended chronologically.

## 2026-05-27 — Test framework: pytest with factory fixtures

Chose pytest over unittest for consistency with pinsheet core. Factory fixtures (make_round, make_course) produce correctly-shaped dicts with string-stored numerics matching the real data model. Test database uses tmp_path isolation with monkeypatched _DATA_DIR — no real data ever touched.

## 2026-05-28 — Plugin system: Blender-style register(app) over class-based API

Chose `register(app)`/`unregister(app)` module-level functions with a `plugin_info` dict (inspired by Blender's add-on system) instead of a base class (`PinSheetPlugin`) like the TUI core uses. Rationale: plugins receive the raw Flask `app` object and wire themselves — blueprints, routes, DB, nav, template blocks — without inheriting from a framework class. Simpler to understand, less to document, and the loader takes care of the mechanical work (template path, static serving). Error isolation at every boundary: import, metadata validation, register() call, hook fire, unregister. Plugins that fail don't crash the server.

## 2026-05-28 — Plugin migration: map TUI hooks to web equivalents, don't force 1:1

The original TUI plugin system (Textual-based class `PinSheetPlugin` with `screens()`, `bindings()`, `css()`, etc.) maps to Flask web equivalents: `screens()` → Blueprint + routes, `bindings()` → `app._plugin_nav.append()`, `css()` → `static/` folder. The migration is documented in `docs/PLUGINS.md` §15-16 with per-plugin checklists. Existing TUI plugins keep their internal logic but replace the adapter layer.

## 2026-05-28 — Cartographer port: `_server_data_dir` sentinel for dual-mode path resolution

The cartographer plugin needs to work both standalone (CLI tagger, PDF generator) and under the Flask server. Instead of threading `app` through every function signature or duplicating the data layer, added a module-level `_server_data_dir: Path | None = None` sentinel to `data.py`. `register()` sets it to `app.config["DATA_DIR"] / "plugins" / "cartographer"`; `unregister()` resets it to `None`. `_get_plugin_data_dir()` checks the sentinel first — if set, returns the server path; if None, falls back to parent-repo-relative resolution for standalone use. Zero changes to any other function signature or caller.

## 2026-05-28 — Cartographer port: staged approach (Stage 1 = visual only)

Porting the full cartographer plugin (TUI screens + tagger + PDF export) in one pass is too large. Broke it into three stages: Stage 1 = hole viewer + course gallery (visual browsing), Stage 2 = tagger integration + style pass, Stage 3 = PDF export. This gives incremental value and keeps each stage testable independently.

## 2026-05-28 — Avoid function-local relative imports with hyphenated module names

Relative imports (`from . import data`) inside functions fail on Python 3.10 when the module name contains a hyphen (`pinsheet-cartographer`). Use `importlib.import_module(__name__ + ".submodule")` instead. For submodule files that are not `__init__.py`, use `importlib.util.spec_from_file_location` with explicit file path to bypass dotted-name resolution entirely.

## 2026-05-28 — Lazy-import heavy third-party deps in plugin blueprints

Cartographer depends on several heavy packages (svgwrite, lxml, shapely, overpy, cairosvg). Blueprint module-level imports of cartographer submodules cause cascading import failures if any dep is missing. Import cartographer submodules inside the individual route handlers that need them, not at module level. The course picker page only needs `data.py` (stdlib) and works with zero extra packages installed.

## 2026-05-28 — OSM upload validation with stdlib only

The OSM upload feature uses `xml.etree.ElementTree` from the Python stdlib for XML validation instead of requiring `lxml`. The validation is minimal: checks for `.osm` extension, non-empty file, and that the XML root tag is `osm`. This keeps the upload feature available without installing cartographer's heavy deps.

## 2026-05-28 — Course picker shows server DB courses, not just tagged courses

The course picker originally only showed courses from `courses_geo.json` (courses that have been tagged). Changed to also pull course names from the server's SQLite database, so users can upload OSM data for courses that haven't been tagged yet. Falls back gracefully if the DB query fails (shows only tagged courses).

## 2026-05-29 — PDF progress: SSE + polling dual mechanism

SSE alone was unreliable due to WSGI server buffering (waitress, Flask dev server). Added a polling fallback that queries `/pdf/status/<job_id>` every 2 seconds alongside the EventSource stream. Both mechanisms converge on the same finish() handler. This way progress updates arrive even when SSE disconnects mid-generation.

## 2026-05-31 — 9-hole net score: halved HI, 9-hole slope/rating, course-hole played_par fallback

For the new Net column on 9-hole rounds, the 9-hole course handicap is computed as `round(HI/2 × (9-hole_slope/113) + (9-hole_rating − 9-hole_par))` using `get_slope_rating()` for hole-selection-aware slope/rating. `played_par` is computed from the course's hole data (summing par for the front or back 9) rather than iterating `r.holes`, which is empty for score-only or imported 9-hole rounds. The raw `calc_course_handicap()` function is reused — the halving is done before calling it.

## 2026-05-29 — Best-effort auto-install of system-level plugin deps in register()

`cairosvg` requires the system library `libcairo2` which pip cannot install. Added `_ensure_cairo()` in `__init__.py:register()` that detects the missing library at startup and attempts to install it via the system package manager (apt/dnf/yum/pacman/brew) using passwordless sudo. Best-effort — warns on failure without crashing the server. This extends the existing pattern of auto-running `pip install -r requirements.txt` in the plugin loader.
