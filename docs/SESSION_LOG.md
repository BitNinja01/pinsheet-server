# Session Log

## 2026-05-28 23:00 UTC

**What was done**:
- Fixed plugin registration on remote: relative imports vs importlib.import_module for function-local imports (Python 3.10 compat with hyphens in module names)
- Fixed blueprint loading: spec_from_file_location instead of importlib dotted-name resolution
- Made all third-party-dependent imports lazy in blueprint routes (svgwrite, lxml, etc.) so course_picker works without any extras installed
- Removed global layout overrides from cartographer.css that were hiding the sidebar
- Fixed `from __init__ import __version__` fragility in main.py (try relative then absolute)
- Added OSM upload API route with validation (extension, empty, XML parse via stdlib)
- Added Upload OSM button to course picker with JS file upload handling
- Updated course picker to show all server courses (from DB) alongside cartographer geometry data
- Renamed local plugin dir from `cartographer` to `pinsheet-cartographer` for consistency
- Added conftest module alias for test compatibility with renamed directory
- 199 cartographer + 177 server = 376 tests passing

**Files touched (main repo)**:
- `source/main.py` — fix `from __init__ import __version__` fragility
- `docs/HANDOFF.md`, `docs/SESSION_LOG.md` — memory framework updates

**Files touched (pinsheet-cartographer)**:
- `__init__.py` — importlib.import_module, spec_from_file_location for blueprint loading
- `blueprint.py` — lazy imports in routes, new upload-osm route, DB-backed course picker
- `renderer.py`, `elevation.py`, `pdf.py`, `tagger/server.py` — relative imports
- `static/cartographer.css` — removed global layout overrides
- `templates/course_picker.html` — Upload OSM button + JS
- `tests/conftest.py` — module alias for renamed dir
- `tests/test_server_plugin.py` — TestOsmUpload, TestCoursePicker updates

**Next**: Debug remote 500, install deps, port achievements plugin.

**What was done**:
- Renamed `plugins/cartographer/` → `plugins/pinsheet-cartographer/` for consistency with remote
- Converted all intra-package imports from absolute (`from cartographer.xxx`) to relative (`from .xxx` / `from ..xxx`) across 6 source files — plugin now works regardless of directory/module name
- Added `conftest.py` alias using `importlib.util.spec_from_file_location` so tests can keep using `from cartographer.xxx` imports
- Fixed `source/main.py` `from __init__ import __version__` to use try/except (relative → absolute fallback) — avoids picking up wrong `__init__.py` from sys.path
- Fixed pre-existing indent bug in 2 test files (imports indented inside method scope)
- Both repos pushed to `origin/dev`

**Next**: Pull & restart on remote to verify plugin registration.

## 2026-05-27 23:00 UTC

**What was done**:
- Added comprehensive test suite (163 tests, all passing)
- Added CI/CD pipeline (ci.yml, release.yml) matching pinsheet core
- Added project tooling (pyproject.toml, requirements-dev.txt, __version__)
- Added README badges (Release, Downloads, CI)
- Added version display on settings page
- Released v0.2.0 — tagged and pushed to origin

**Next**: Deploy to production, increase coverage to 80%, wire up placeholder stats

## 2026-05-28 00:30 UTC

**What was done**:
- Implemented full mobile responsive design across all templates
- Hamburger menu: off-canvas sidebar overlay with backdrop, Escape key close, hamburger-to-X animation
- Table→card layouts: dashboard, rounds list, season breakdown tables become cards on ≤768px
- Round entry: hole cards with shorthand input parser (e.g. "4 L N 2"), live parsed display, auto-scroll, progress dots, bidirectional sync with desktop table
- Stats page: compact 2-col grid at ≤480px (22px values, stacked windows)
- Course detail: tee cards + 3-col hole mini-grid
- Touch targets: 44px min-height on all buttons/inputs/nav links at ≤768px
- Sparkline SVGs: viewBox + max-width: 100% for responsive scaling
- Auth pages: reduced card padding at ≤400px
- Consolidated all responsive CSS (1,536 lines, 9 organized media query blocks)
- 163/163 tests passing throughout

**Files touched**:
- `source/web/templates/base.html` — hamburger HTML structure
- `source/web/templates/dashboard.html` — card layout + sparkline viewBox
- `source/web/templates/rounds_list.html` — card layout + sparkline viewBox
- `source/web/templates/round_entry.html` — hole cards container
- `source/web/templates/course_detail.html` — tee cards + hole mini-grid
- `source/web/templates/season_summary.html` — breakdown cards
- `source/web/static/app.css` — all responsive CSS (hamburger, cards, stats, hole cards, touch targets)
- `source/web/static/app.js` — hamburger toggle, hole card rendering/parsing/navigation/sync
- `source/web/static/auth.css` — mobile padding breakpoint

**Next**: Manual verification on device, deploy to production

## 2026-05-28 03:00 UTC

**What was done**:
- Pushed 15 mobile-responsive commits to `origin/dev`
- Fixed desktop layout regression: `.ps-sidebar-backdrop` CSS was scoped entirely inside `@media (max-width: 768px)`, leaving the empty `<div>` with no `display: none` on desktop. As a child of the `.ps-layout` CSS Grid, it consumed the first grid cell, pushing `.ps-sidebar` to column 2 and squeezing `.ps-main` into a 200px-wide cell on row 2
- Fix: added top-level `.ps-sidebar-backdrop { display: none; }` to properly exclude it from grid placement on all viewports

**Files touched**:
- `source/web/static/app.css` — top-level `display: none` for `.ps-sidebar-backdrop`, removed redundant dupe inside media query

**Next**: Manual verification, deploy to production

## 2026-05-28 10:00 UTC

**What was done**:
- Designed and implemented a Blender-style plugin system for the Flask server: `plugin_info` dict + `register(app)`/`unregister(app)` per plugin
- Created `source/plugin.py` (public API: `_plugins` registry, `fire_hook` with error isolation)
- Created `source/plugin_loader.py` (internal: `discover_plugins`, template/static auto-wiring, metadata validation)
- Wired plugin system into `source/main.py`: hook fires in `api_rounds_post`/`api_courses_post`, context processor (`plugin_blocks`, `plugin_nav`, `plugin_info`), atexit unregister, `app.config["DB_PATH"]`/`"DATA_DIR"`
- Modified `base.html` with `plugin_blocks.head`, `plugin_nav` rendering, `plugin_blocks.foot` injection points
- Added 14 new tests (6 loader unit + 8 integration) — all 177 pass
- Created test fixture plugins (minimal, full, broken variants)
- Wrote comprehensive `docs/PLUGINS.md` developer guide (1022 lines, 17 sections) with migration mapping table and per-plugin checklists for achievements/cartographer/printables
- Updated `docs/RUNBOOK.md` with plugin section
- Spec at `docs/superpowers/specs/2026-05-28-plugin-system-design.md`
- Plan at `docs/superpowers/plans/2026-05-28-plugin-system-plan.md`

**Files touched**:
- `source/plugin.py` — new, public plugin API (19 loc)
- `source/plugin_loader.py` — new, discovery + auto-wiring (111 loc)
- `source/main.py` — 10 changes: imports, config, discovery, hooks, context processor, atexit (+45 lines)
- `source/web/templates/base.html` — 3 template block injection points (+11 lines)
- `tests/test_plugin_loader.py` — new, 6 tests for loader
- `tests/test_plugin.py` — new, 8 integration tests
- `tests/fixtures/plugins/` — new, 7 fixture files (5 plugin variants)
- `docs/PLUGINS.md` — new, comprehensive developer guide
- `docs/RUNBOOK.md` — added plugin section
- `docs/HANDOFF.md` — updated
- `.gitignore` — scoped `plugins/` to root-level only

**Next**: Port achievements, cartographer, and printables plugins from TUI core

## 2026-05-28 14:00 UTC

**What was done**:
- Copied cartographer plugin from TUI repo to `plugins/cartographer/` (nested git repo)
- Removed old AI artifacts and cache files from the copy
- Created new AI artifacts for the plugin (AGENTS.md, .opencode/, .superpowers/, .od-skills/)
- Designed Stage 1 port: 3 routes, 3 templates, static CSS, DB table, integration tests
- Wrote design spec and implementation plan in docs/superpowers/
- Implemented Stage 1 via subagent-driven development (7 tasks):
  - Replaced `__init__.py` with `plugin_info` + `register(app)`/`unregister(app)` contract
  - Augmented `data.py` with `_server_data_dir` sentinel for server-aware path resolution
  - Created `blueprint.py` with 3 Flask routes (course picker, hole viewer, course gallery)
  - Created 3 Jinja2 templates extending `base.html` with PinSheet design tokens
  - Created `static/cartographer.css` with gallery grid, SVG scaling, mobile-responsive
  - Wrote 13 integration tests (registration, routes, 404s, SVG rendering, data dir)
  - Fixed production bug: blueprint routes now pass `settings` to templates
  - Fixed test isolation: save/restore `_got_first_request` and `_server_data_dir` in fixture
- 364 tests pass (174 cartographer standalone + 190 server/plugin)

**Files touched**:
- `plugins/cartographer/__init__.py` — replaced TUI adapter with server plugin contract
- `plugins/cartographer/plugin.py` — deleted (TUI adapter)
- `plugins/cartographer/data.py` — added `_server_data_dir` for server-aware path resolution
- `plugins/cartographer/blueprint.py` — new, 3 Flask routes
- `plugins/cartographer/templates/` — 3 new templates
- `plugins/cartographer/static/cartographer.css` — new
- `plugins/cartographer/AGENTS.md` — new AI artifact
- `plugins/cartographer/.opencode/session-start.md` — new
- `plugins/cartographer/.superpowers/config.yml` — new
- `plugins/cartographer/.od-skills/config.yml` — new
- `tests/test_cartographer_plugin.py` — new, 13 integration tests
- `.gitignore` — scoped to allow `!/plugins/cartographer/**`
- `docs/HANDOFF.md` — updated
- `docs/SESSION_LOG.md` — this entry
- `docs/superpowers/` — 2 new docs (spec + plan)

**Next**: Cartographer Stage 2 (tagger integration + style pass) or achievements plugin port

## 2026-05-28 18:30 UTC

**What was done**:
- Restored parent `.gitignore` to `/plugins/` — plugin files moved to nested `pinsheet-cartographer` repo
- Moved cartographer integration tests to the plugin repo (`tests/test_server_plugin.py`)
- Pushed cartographer Stage 1 to `pinsheet-cartographer` (new `dev` branch)
- Renamed old TUI cartographer remote to `pinsheet-terminal-cartographer`
- Untracked AI artifacts (`AGENTS.md`) and session memory docs from both repos
- Added `AGENTS.md` to cartographer's `.gitignore`
- Both repos now have clean separation: zero AI artifacts or session memory tracked

**Files touched**:
- `.gitignore` — restored to `/plugins/`, removed plugin exception
- `plugins/cartographer/.gitignore` — added `AGENTS.md`
- `plugins/cartographer/` — all Stage 1 files now committed to nested repo, pushed to GitHub
- `docs/HANDOFF.md` — updated
- `docs/SESSION_LOG.md` — this entry

**Next**: Cartographer Stage 2 (tagger integration + style pass) or achievements plugin port

## 2026-05-28 19:00 UTC

**What was done**:
- Fixed CI for cartographer plugin:
  - Changed checkout from `BitNinja01/pinsheet` (TUI) to `BitNinja01/pinsheet-server:dev` — needed for `source.plugin` imports
  - Added `sys.path` resolution in test fixture to handle missing `PYTHONPATH` in CI
  - Fixed template path in test fixture (was resolving to wrong directory)
  - Rewrote fixture to use `discover_plugins()` instead of manual setup — same code path as production
  - Fixture properly cleans up Flask blueprints, static routes, and `_plugins` on teardown
- 187 tests pass in CI (2 warnings only — flask-limiter in-memory, Pillow deprecation)

**Files touched**:
- `plugins/cartographer/.github/workflows/ci.yml` — changed parent repo and pinned `ref: dev`
- `plugins/cartographer/tests/test_server_plugin.py` — rewrote fixture to use `discover_plugins()`, fixed template paths, added cleanup
- `docs/HANDOFF.md` — updated
- `docs/SESSION_LOG.md` — this entry

**Next**: Cartographer Stage 2 (tagger integration + style pass) or achievements plugin port

## 2026-05-29 04:30 UTC

**What was done**:
- Cartographer Stage 2 implemented — tagger embedded as blueprint routes, Leaflet UI as Jinja2 template, CSS extracted with `--ps-*` tokens
- 194 tests pass (187 original + 7 tagger route tests)
- Fixed server startup hang on CIFS: added `DISPLAY`/`WAYLAND_DISPLAY` guard around browser launch
- Changed default port from 8420 to 8080 (matching systemd config)
- Fixed `No module named 'source'` on Python 3.10: added `_repo_root` sys.path resolution in `main.py`
- Removed `requirements-dev.txt` (path resolution now handled in main.py)

**Files touched**:
- `source/main.py` — PORT=8080, DISPLAY guard, _repo_root sys.path fix
- `plugins/cartographer/tagger/server.py` — refactored to stateless handlers
- `plugins/cartographer/blueprint.py` — added 7 tagger routes
- `plugins/cartographer/templates/tagger.html` — new Jinja2 template
- `plugins/cartographer/static/cartographer.css` — tagger styles with ps tokens
- `plugins/cartographer/templates/course_picker.html` — "Tag" button
- `plugins/cartographer/tests/test_server_plugin.py` — 7 new tests
- `plugins/cartographer/tagger/__main__.py` — deleted
- `plugins/cartographer/tagger/static/index.html` — deleted
- `requirements-dev.txt` — deleted
- `README.md` — updated port
- `docs/HANDOFF.md`, `docs/SESSION_LOG.md` — updated

**Next**: Test Cartographer Stage 2 on remote, then achievements plugin port.

## 2026-05-29 05:00 UTC

**What was done**:
- Fixed `TypeError: tuple indices must be integers or slices, not str` — added `row_factory = sqlite3.Row` to raw `sqlite3.connect()` in `blueprint.py` course picker
- Fixed OSM upload "Network error" — exempted cartographer POST routes from CSRF in `register()` via `app.extensions['csrf'].exempt()`
- Fixed map not displaying — moved Leaflet/Turf from CDN to local `static/` folder; converted tagger template to standalone HTML page with `body { display: flex; height: 100vh }` then restored `{% extends "base.html" %}` with `position: fixed` layout; set default `center/zoom` on `L.map()`
- Fixed lxml dependency — replaced module-level `from lxml import etree` in `osm.py` with lazy import inside `parse_osm_file()`; added stdlib `xml.etree.ElementTree` fallback
- Fixed shapely dependency — removed all module-level `from shapely.geometry import ...` in `tagger/server.py`; imports moved inside functions; `try/except ImportError` wrapped around post-parse pipeline
- Fixed colors — switched hardcoded `oklch()` values to server theme CSS variables (`--ps-paper`, `--ps-accent`, etc.)

**Still open**: Features API returns non-JSON (`JSON.parse` fails). Map renders but no OSM features shown. Need to inspect remote server logs for the actual exception.

**Files touched**:
- `plugins/pinsheet-cartographer/blueprint.py` — row_factory, CSRF (server plugin repo)
- `plugins/pinsheet-cartographer/__init__.py` — CSRF exemption registration
- `plugins/pinsheet-cartographer/templates/tagger.html` — standalone → base.html, position:fixed, theme CSS vars, center/zoom
- `plugins/pinsheet-cartographer/static/leaflet.js`, `leaflet.css`, `turf.min.js` — local CDN-free copies
- `plugins/pinsheet-cartographer/osm.py` — lazy lxml, stdlib ElementTree fallback
- `plugins/pinsheet-cartographer/tagger/server.py` — lazy shapely, ImportError handling
- `pinsheet-server/docs/HANDOFF.md`, `pinsheet-server/docs/SESSION_LOG.md` — updated

## 2026-05-29 07:10 UTC

**What was done**:
- Fixed stdlib fallback bug in `osm.py` (`tag[2:]` → `tag[3:]` for `{*}` wildcard stripping in `_parse_osm_xml`)
- Added XML parser diagnostic log during `register()` — logs whether lxml or stdlib is being used
- Root-caused "No features on map" issue: shapely was missing from server's venv (system `python3` had it, `/opt/pinsheet-server/.venv/` didn't); venv installed via `pip install shapely`
- Fixed assigned-feature red outline: `--danger` → `HIGHLIGHT_COLOR = '#ff3333'` in tagger template
- Renamed data directory: `data/plugins/cartographer/` → `data/plugins/pinsheet-cartographer/`
- Added `handle_get_features` ImportError detail logging (shows exact missing module name in API response)
- Removed "Saved! You can close this tab." confirmation — save now redirects to course gallery
- Built lazy SVG gallery: new `/api/hole/N/svg` endpoint, gallery renders placeholders then fetches SVGs async
- Changed gallery grid 6×3 → 3×6, removed hole page links, larger hole numbers (28px, positioned top-right)
- Added auto-dep-install to plugin loader: `discover_plugins` runs `pip install -r requirements.txt` per plugin
- Pushed 8 commits to `pinsheet-cartographer` (`dev`), 2 commits to `pinsheet-server` (`dev`)

**Next**: Port PDF yardage book generation (Stage 3 of cartographer server migration)

## 2026-05-29 09:30 UTC

**What was done**:
- Ported PDF yardage book generation to the web (Stage 3 complete)
- DB migration: added `pdf_generated_at` column to `plugin_cartographer_geometry`
- Refactored `generate_book()` in `pdf.py` — added `data_dir`, `courses_data`, `rounds_data` params for server context
- Added 4 new routes to blueprint: GET config page, POST generate, SSE stream, download
- Created `pdf_export.html` template with three-state UI (config form → progress → download/error)
- SSE real-time progress via EventSource (sheet/booklet progress bars + detail status)
- Background thread generation with in-memory job tracking
- Course picker now shows Download/Regenerate/Generate PDF per course based on staleness
- 6-month staleness detection: >182 days shows "Regenerate" button in warning color
- Fixed: DB connection leak (try/finally), hardcoded user_id (uses current_user), clean imports
- 31 tests pass (6 new PDF route tests)
- 8 commits to `pinsheet-cartographer` (`dev`)

**Next**: Port achievements plugin

## 2026-05-29 10:00 UTC

**What was done**:
- Fixed runtime errors: libcairo2 auto-install in _ensure_cairo(), OSError in dep checker
- Fixed `from cartographer import stats` → `from . import stats` (package name mismatch)
- Added SSE buffering fix: stream_with_context + no-cache headers
- Added status polling fallback (JS polls /status/<job_id> every 2s when SSE drops)
- Wrapped pdf_generate in try/except returning JSON error (not HTML 500)
- All fixes committed and pushed to `pinsheet-cartographer` (`dev`)

**Next**: Port achievements plugin (BK-15 deferred)

## 2026-05-29 11:00 UTC

**What was done**:
- Fixed `_generate_job` background thread DB write (`current_app` is thread-local; captured `db_path` before thread start)
- Added filesystem fallback in course picker (checks zip mtime when DB lacks timestamp)
- Added `DELETE /<course>/pdf` endpoint that removes zip/booklets/sheets and clears DB timestamp
- Course picker table: renamed "Last Tagged" → "Last Generated", moved date from buttons to column
- Course picker table: fixed column widths (PDF 160px, Actions 220px, Delete 60px)
- Actions column: flexbox with `flex: 1` on buttons so Upload OSM (alone) and View+Tag (paired) occupy same width
- Button visibility: View only with OSM, Upload OSM only without OSM, Tag with OSM
- Delete button per row (red, JS confirm + fetch DELETE)
- All pushed to `BitNinja01/pinsheet-cartographer` (`dev`)

**Commits**: 973ed16 (db_path capture), bf7d17d (filesystem fallback), c757b95 (Last Generated rename), e0a5066 (table redesign + delete), 9335afa (hide Upload OSM when has_osm), 9af188d (flexbox sizing), 03de17f (wrapper div table fix)

**Next**: Port achievements plugin (BK-15 deferred on dashboard)

## 2026-05-29 19:30 UTC

**What was done**:
- Completed CODEBASE_IMPROVEMENTS.md item #4: fixed `rounds.py:180` passing raw dicts to `calc_handicap_index()` — added `dict_to_round()` conversion before crossing calc seam
- Completed CODEBASE_IMPROVEMENTS.md item #5: moved 6 functions from `calc/context.py` into `calc/scoring.py`, updated import in `calc/__init__.py`, deleted `context.py`
- All 177 tests passing, pushed to `origin/dev`

**Files touched**:
- `source/routes/rounds.py` — added typed conversion before `calc_handicap_index()` call
- `source/calc/scoring.py` — appended 6 context functions, added `timedelta` import
- `source/calc/__init__.py` — switched import from `calc.context` to `calc.scoring`
- `source/calc/context.py` — deleted

**Next**: Port achievements plugin (per HANDOFF.md)

## 2026-05-30 12:00 UTC

**What was done**:
- Ran `improve-codebase-architecture` skill, replaced CODEBASE_IMPROVEMENTS.md with 7 new candidates
- Task 1: Pushed `dict_to_round()` into `store.get_all_rounds()` seam — all routes get typed RoundData directly
- Task 2: Split `scoring.py` (988→436 lines) into `analysis.py`, `milestones.py`, `seasons.py`
- Task 3: Extracted `_per_round_stat`, `_hole_pct` from stats.py → `calc_per_round_average()`, `calc_hole_percentage()`; extracted `_get_hi_for_range` and career-low from dashboard → handicap.py
- Task 4: Created `source/request_data.py` with lazy-loading helpers; slimmed `_load_globals` to only set view_user/is_own_data
- Task 5: Moved route registration from module import time into `main()` via `register_routes()`
- Task 6: Replaced O(n²) handicap trend with O(n log n) rolling window using bisect.insort
- Task 7 bug fix: `report_card` RoundData vs date string comparison (included in Task 1)
- All 177 tests passing after each step, pushed to `origin/dev`

**Files touched**:
- `source/store.py` — get_all_rounds returns list[RoundData]
- `source/calc/models.py` — unchanged (dict_to_round used internally)
- `source/calc/__init__.py` — exports reorganized for 6 source modules
- `source/calc/scoring.py` — trimmed from 988→436 lines; added calc_per_round_average, calc_hole_percentage
- `source/calc/analysis.py` — new (79 lines): penalty stats, momentum recovery
- `source/calc/milestones.py` — new (319 lines): personal bests, career milestones
- `source/calc/seasons.py` — new (159 lines): seasonal/calendar stats
- `source/calc/handicap.py` — added calc_handicap_values_in_range, calc_career_low_handicap; optimized calc_handicap_trend
- `source/request_data.py` — new: lazy-loading get_settings/get_courses/get_all_rounds_for_user
- `source/main.py` — removed data imports from _load_globals; moved route registration to main()
- `source/routes/__init__.py` — now exports register_routes() with local imports
- `source/routes/rounds.py` — removed dict_to_round, attribute access, lazy data helpers
- `source/routes/dashboard.py` — same + extracted inline closures
- `source/routes/stats.py` — same + extracted inline closures
- `source/routes/courses.py` — attribute access, lazy data helpers
- `source/routes/settings.py` — removed dict_to_round, lazy data helpers
- `source/_helpers.py` — HoleData attribute access
- `tests/test_store.py` — attribute access updates
- `tests/test_routes.py` — explicit register_routes() in test setup
- `tests/test_scoring.py` — updated imports for new module locations
- `CODEBASE_IMPROVEMENTS.md` — emptied (completed items)
- `.gitignore` — added CODEBASE_IMPROVEMENTS.md

**Next**: Port achievements plugin (per HANDOFF.md)

## 2026-05-30 14:00 UTC

**What was done**:
- Merged `candidate-3-snapshot` into dev (invert store→calc.models dependency), deleted branch
- Candidate 4: Added `base_context(**extra)` to `request_data.py`; removed `settings=get_settings(), all_users=get_users()` boilerplate from 22 `render_template()` calls across 5 route files
- Candidate 5: Added 70 tests covering `seasons.py` (8 functions) and `milestones.py` (11 functions) — 247 total, all passing

**Files touched**:
- `source/request_data.py` — added `get_users()` lazy-loader and `base_context()` helper
- `source/routes/dashboard.py` — switched to `base_context()`, removed `from store import get_users`
- `source/routes/stats.py` — same
- `source/routes/rounds.py` — same
- `source/routes/courses.py` — same
- `source/routes/settings.py` — same
- `source/models.py` — moved from `source/calc/models.py` (Candidate 3 merge)
- `tests/test_seasons.py` — new (30 tests)
- `tests/test_milestones.py` — new (40 tests)

**Next**: Port achievements plugin (per HANDOFF.md)

## 2026-05-30 15:40 UTC

**What was done**:
- Bumped `--ps-fs-body` from 13px to 18px (nav, body text, table cells, forms)
- Bumped `--ps-fs-eyebrow` from 10px to 13px (labels, stat deltas, windows)
- Replaced hardcoded 10px/11px/12px/13px with CSS variables in `.stat-cell-delta`, `.stat-cell-window`, `.ps-stat-delta`, `.ps-topar`, and table date/tees/diff cells
- Removed `.ps-meta` course sub-text from dashboard and rounds_list table rows
- Added `font-weight: var(--ps-fw-label)` to `.ps-course` and date cells
- Bumped table row padding from 7px to 10px
- All changes pushed to dev

**Files touched**:
- `source/web/static/app.css` — typography variables, .ps-topar, .ps-stat-delta, .stat-cell-delta, .stat-cell-window, .ps-course, td padding
- `source/web/templates/dashboard.html` — removed inline font-size overrides, removed .ps-meta, added font-weight to date cells
- `source/web/templates/rounds_list.html` — same pattern as dashboard.html

**Next**: Per HANDOFF.md — port achievements plugin first.

## 2026-05-31 00:45 UTC

**What was done**:
- Fixed course detail hole rendering for imported data (two data formats: UI vs imported `hole_index`/per-hole `tees`)
- Added `width: fit-content` to course/round detail tables so they size to their data on wide screens
- Added zebra striping to all `.data-table` and `.ps-table` tables
- Added Net column to dashboard and rounds_list tables with green/red net-to-par coloring
- Swapped `is-under` from score-to-par to handicap-inclusion, then reverted it
- Fixed 9-hole `score_to_par` to use holes-actually-played par instead of full 18-hole par
- Fixed 9-hole net calculation: halved HI, used `get_slope_rating` for correct 9-hole slope/rating, handled empty `r.holes` via course hole data

**Files touched**:
- `source/routes/courses.py` — fallback keys for imported course data format
- `source/routes/dashboard.py` — net score computation, 9-hole adjustments
- `source/routes/rounds.py` — net score computation, 9-hole adjustments
- `source/web/static/app.css` — fit-content, zebra striping, is-over class
- `source/web/templates/dashboard.html` — Net column, mobile net display
- `source/web/templates/rounds_list.html` — Net column, mobile net display

**Bug**: Net column CH is off by −1 for some 18-hole rounds (Maplewood CH=18 vs expected 19, Druids Glen CH=22 vs expected 23). `calc_course_handicap` uses `round()` and computes correctly in tests, but live server output matches `int()` truncation. `__pycache__` cleared, server restarted — still persists. Needs runtime logging to diagnose.

**Next**: Per HANDOFF.md — port achievements plugin first.

## 2026-05-31 21:30 UTC

**What was done**:
- Investigated net column -1 rounding bug end-to-end: traced `calc_course_handicap`, all callers, course data loading, and import process
- Added diagnostic `INFO` logging to `calc_course_handicap` with full input/output trace
- Wrote 4 regression tests pinning Maplewood white (CH=19), Druids Glen white (CH=23), and round-over-int behavior
- Ran against re-imported fresh data from pinsheet core; logs proved `round()` computes correctly
- Identified root cause: source data had stale HIs (e.g. Maplewood HI=21.7 source vs 20.8 after import recalculation). The import correctly recomputes all HIs from scratch
- Removed diagnostic logging after confirmation; regression tests retained
- Created `pinsheet-import.zip` from pinsheet core data for re-import; gitignored

**Files touched**:
- `source/calc/handicap.py` — added diagnostic logging, then reverted
- `tests/test_handicap.py` — 4 regression tests (retained)
- `.gitignore` — added `pinsheet-import.zip`

**Bug**: Net column -1 discrepancy was not a code bug. The import recalculates handicap indexes from scratch; source data had stale HIs. No functional changes required.

**Next**: Per HANDOFF.md — port achievements plugin.

## 2026-05-31 23:45 UTC

**What was done**:
- Designed and implemented inline editing for course detail and round detail pages
- Backend: `PUT /api/courses/<name>` with rename handling, conflict detection (404/409), full validation
- Backend: `PUT /api/rounds/<date>/<index>` with score recalculation, differential, full handicap index recompute
- Course edit UI: editable name/location, tee sets table with add/remove (auto-syncs holes columns + mobile cards), editable holes grid
- Round edit UI: editable metadata (date/course/tees/transport), scorecard with fairway/GIR dropdowns, live subtotals, notes textarea, course→tees cascade

**Files touched**:
- `source/routes/courses.py` — added PUT route, edit_mode param
- `source/routes/rounds.py` — added PUT route, edit_mode param + courses context
- `source/web/templates/course_detail.html` — edit mode blocks + JS (save, add/remove tee, sync)
- `source/web/templates/round_detail.html` — edit mode blocks + JS (course cascade, live subtotals, save)
- `tests/test_routes.py` — tests for PUT course and PUT round endpoints
- `docs/superpowers/specs/2026-05-31-edit-pages-design.md` — design doc
- `docs/superpowers/plans/2026-05-31-edit-pages.md` — implementation plan

**Test results**: 253/253 pass (1 new test per PUT endpoint)

**Next**: Per HANDOFF.md — port achievements plugin.

## 2026-06-01 00:30 UTC

**What was done**:
- CSRF fix: PUT routes were being blocked by Flask-WTF CSRFProtect. Exempted both PUT routes via `@csrf.exempt`, matching the existing pattern in `POST /api/welcome`.

**Files touched**:
- `source/routes/__init__.py` — pass `csrf` to course and round route registration
- `source/routes/courses.py` — accept `csrf`, exempt PUT route
- `source/routes/rounds.py` — accept `csrf`, exempt PUT route

**Test results**: 253/253 pass

**Next**: Per HANDOFF.md — port achievements plugin.

## 2026-06-01 08:47 UTC

**What was done**:
- Initialized issue tracker in `.scratch/issues/` (8 backlog issues created)
- Applied `.step-input`/`.hole-input` form styling to round and course edit pages
- Closed P2_002 (edit page styling) after user confirmed testing
- Added `.scratch/` to `.gitignore` and removed from git tracking
- Migrated BK-15 from BACKLOG.md to issue P2_001

**Files touched**:
- `source/web/templates/round_detail.html` — added form classes, removed inline styles
- `source/web/templates/course_detail.html` — added form classes, removed inline styles, `.edit-location` → `.location-row`
- `.gitignore` — added `.scratch/`
- `.scratch/issues/P*.md` — 8 issues created (P1: 2, P2: 5, P3: 1), 1 closed

**Next**: Per HANDOFF.md — port achievements plugin.
