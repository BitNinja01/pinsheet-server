# Session Log

## 2026-05-15 00:00 UTC — Project scaffold

**What was done**:
- Created project structure: Flask + waitress + Jinja2 + vanilla CSS/JS
- Ported all calc functions 1:1 from original Python pinsheet (handicap, scoring, approach, putting)
- Ported store layer (JSON file I/O) from original `data.py`
- Created minimal Flask app with dashboard route serving real stat panels
- Set up `base.html` shell template and `dashboard.html` with 6-panel grid
- Wrote `app.css` with dark theme, custom properties, stat panel styling
- Created AGENTS.md, session memory framework (HANDOFF, SESSION_LOG, DECISIONS, RUNBOOK)

**Decisions**:
- Flask over FastAPI (simpler, fewer deps)
- Waitress over Werkzeug dev server (no warning banners)
- Data format unchanged from original Python pinsheet
- `data/` directory is `.gitignore`d; created at runtime
- Distribution: same launcher-script pattern as original (2 scripts: launch.sh, launch.bat)

**Files created**:
- `main.py`, `store.py` — app entry and data layer
- `calc/__init__.py`, `calc/handicap.py`, `calc/scoring.py`, `calc/approach.py`, `calc/putting.py`
- `web/templates/base.html`, `web/templates/dashboard.html`
- `web/static/app.css`
- `AGENTS.md`, `.gitignore`, `requirements.txt`
- `docs/HANDOFF.md`, `docs/SESSION_LOG.md`, `docs/DECISIONS.md`, `docs/RUNBOOK.md`

**Next**: Copy data from original pinsheet, complete dashboard backend/frontend.

## 2026-05-15 01:00 UTC — Session end

**What was done**:
- Resolved tech stack: Flask + waitress (Python web app) over Go/Lorca
- Defined distribution model: same launcher-script pattern as original pinsheet
- Fixed Flask template/static folder paths after initial render failure
- Copied real data from original pinsheet into `data/` for development
- Verified dashboard renders with real values (Handicap 22.2, Avg 94.3, FIR 51.4%, GIR 21.2%, Putts 36.8, Scramble 11.5%)
- Committed scaffold (17 files, 2268 lines) as root commit `7b47b64`

**Files touched**:
- `main.py` — fixed `template_folder` / `static_folder` paths
- `docs/HANDOFF.md` — updated current state, next actions, removed stale "copy data" task
- `docs/SESSION_LOG.md` — this entry

**Next**: Complete dashboard route (rounds table + trends), then round entry wizard.

## 2026-05-15 14:00 UTC — Session end

**What was done**:
- Ran full brainstorming → design spec → implementation plan workflow
- Wrote design spec (`docs/superpowers/specs/2026-05-15-web-rewrite-design.md`): 12 screens, route map, API design, CSS themes, 6-phase breakdown
- Wrote implementation plan (`docs/superpowers/plans/2026-05-15-web-rewrite-plan.md`): Phase 2 (Rounds) in full bite-sized detail, Phases 3-6 scaffolded
- Restructured code into `source/` directory to match original pinsheet layout
- Fixed `store.py` _DATA_DIR path for source/ nesting (repo root /data)
- Renamed Gitea repo from `pinsheet-pywebview` → `pinsheet-modern` via API
- Updated git remote and pushed 5 commits

**Design decisions**:
- 1×6 horizontal stat panel row on dashboard
- Progressive disclosure wizards for round/course entry
- Hybrid navigation: server-rendered pages + vanilla JS fetch() for inline actions
- Trend graphs deferred — dashboard is stat panels + rounds table only
- Season summary and GHIN export screens included in spec
- Chart.js vendored in static/vendor/ for future use

**Files touched**:
- `source/store.py` — fixed _DATA_DIR to `Path(__file__).parent.parent / "data"`
- `docs/superpowers/specs/2026-05-15-web-rewrite-design.md` — new design spec (341 lines)
- `docs/superpowers/plans/2026-05-15-web-rewrite-plan.md` — new implementation plan (1308 lines)
- `AGENTS.md` — updated run command to `python source/main.py`
- `docs/RUNBOOK.md` — updated run command
- `docs/HANDOFF.md` — updated state, next actions, repo remote URL
- `docs/SESSION_LOG.md` — this entry

**Next**: Task 2.1 — complete dashboard with rounds table and last-year HI

## 2026-05-15 21:40 UTC — Session end

**What was done**:
- Implemented Phase 2 (Rounds): completed dashboard with rounds table + handicap highlighting + click-to-navigate, round entry wizard with progressive disclosure + 500ms debounced draft save/resume, dynamic scorecard grid with auto-updating totals + POST /api/rounds, round detail scorecard with color-coded cells + OUT/IN/TOT subtotals + delete, report card with this-round vs L20 avg comparison tables and delta arrows
- Implemented Phase 3 (Courses): course list table with play counts, course detail page with tees + holes tables + history, course entry wizard with dynamic tee set addition and hole grid
- Implemented Phase 4 (Stats): 9-section stats screen (Scoring, Penalties, Fairways, Greens, Putting, Short Game, Momentum, Bests, Trends) with sticky sidebar nav, Best 8 / Last 5 / Last 10 / Last 20 columns
- Implemented Phase 5 (Settings & Polish): settings page with 12 theme swatches + auto-save toggles, welcome screen gate on dashboard, season summary page with handicap journey/score breakdown/milestones/mileage
- Implemented Phase 6 (Distribution): launch.sh (Linux/macOS), launch.bat (Windows), dist.sh packaging script
- GHIN export intentionally cut per user request
- All code passes `py_compile` and `node --check`

**Files touched**:
- `source/main.py` — grew from 98 to 750 lines; all route handlers, helpers, calc imports
- `source/web/static/app.js` — 277 lines; click-to-navigate, wizard progressive disclosure, draft save/resume, scorecard grid builder, totals updater, submit handler, settings auto-save
- `source/web/static/app.css` — grew from 119 to 581 lines; data tables, wizard, scorecard, scorecard view, report card, stats layout, settings, welcome, season, 12 theme overrides + swatches
- `source/web/templates/` — 12 templates: base, dashboard, round_entry, round_detail, report_card, courses, course_detail, course_entry, stats, settings, welcome, season_summary
- `scripts/launchers/launch.sh`, `scripts/launchers/launch.bat`, `scripts/dist.sh` — distribution scripts

**Next**: Smoke test the app end-to-end, course entry test, edge case hardening
