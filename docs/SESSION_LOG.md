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

## 2026-05-15 23:00 UTC — Session end

**What was done**:
- Completed course entry wizard: structured location (city/state/country), 7 tee fields (yardage/rating/slope + front/back rating + front/back slope), DOM-driven tee set management with holes-preserving grid rebuild, draft resume with proper tee restoration
- Added Chrome `--app` mode with auto-shutdown on window close
- Built round entry wizard from scratch: auto-advance progressive disclosure, course→tee filtering, dynamic scorecard grid with OUT/IN/TOT subtotals, text-based color coding (eagle/birdie/bogey/double), draft save/resume with step routing, score-only mode
- Fixed 6 edge cases: no-courses guard on round entry, removed placeholder text, front 9/back 9 switching preserves data, score-only round detail shows gross panel, course deletion blocked when rounds exist, radio buttons start unselected
- Manual smoke testing throughout — course entry flow verified, round entry flow verified

**Files touched**:
- `source/main.py` — round entry route, score-only round detail, course deletion guard
- `source/web/static/app.js` — grew ~500 lines: course wizard rewrite (7 fields, DOM-driven, draft resume), round wizard (auto-advance, scorecard grid, subtotals, color coding, draft save/resume, submit), scorecardData persistence
- `source/web/static/app.css` — location-row, tee-numbers 7-field layout
- `source/web/templates/course_detail.html` — conditional front/back columns, structured location
- `source/web/templates/course_entry.html` — structured location fields
- `source/web/templates/courses.html` — structured location display, removed placeholder
- `source/web/templates/round_entry.html` — no-courses guard, radio buttons unselected
- `source/web/templates/round_detail.html` — score-only conditional panel
- `source/web/templates/dashboard.html` — "Add Round" button for empty state
- `docs/test-data.md` — Druids Glen course + round reference data

## 2026-05-15 23:55 UTC — Session end

**What was done**:
- Ran full brainstorming → design spec → implementation plan workflow for dashboard visual theme
- Used visual companion (browser-based mockup tool) to iterate on grid styles, color palettes, and typography
- Locked in "Dark Engineering Grid" direction: Cool Teal palette (`#0d1114`/`#181e22`/`#50c8d2`), full monospace, adaptive grid with crosshair dots, dashed borders
- Wrote design spec (`docs/superpowers/specs/2026-05-15-dashboard-theme-design.md`) and implementation plan (`docs/superpowers/plans/2026-05-15-dashboard-theme-plan.md`)
- Executed plan via subagent-driven development: 8 tasks, each with spec compliance + code quality review gates
- Replaced `:root` CSS custom properties (Task 1), added 8px dot grid background texture (Task 2), updated header/nav to dashed borders/monospace sizing (Task 3), restyled stat panels to 6-column row + rounds table with teal accents (Task 4), created `grid.js` adaptive grid overlay module (Task 5), wired templates with `data-grid-region`/`data-grid-panel` attributes (Task 6)
- Smoke tested: 15 checks passed (all pages 200, static files served, 6 grid-panel elements detected, no Flask errors)
- Dashboard only — other pages adopt new `:root` tokens but layouts unchanged

**Files touched**:
- `source/web/static/app.css` — `:root` tokens replaced, body dot grid, header/nav, stat panels (3col→6col), rounds table, theme swatch
- `source/web/static/grid.js` — new 91-line vanilla JS adaptive grid overlay module
- `source/web/templates/base.html` — added `data-grid-region` + `grid.js` script include
- `source/web/templates/dashboard.html` — added `data-grid-panel` attribute to stat panels
- `docs/superpowers/specs/2026-05-15-dashboard-theme-design.md` — design spec
- `docs/superpowers/plans/2026-05-15-dashboard-theme-plan.md` — implementation plan

**Next**: Continue theme rollout to other pages, refine scorecard grid visuals, tweak dashboard details

## 2026-05-16 22:30 UTC — Session end

**What was done**:
- Complete dashboard visual redesign: analyzed 5 reference images (engineering grid, graph paper, stat cards, calendar, bar chart) to create unified design direction
- Transformed from dark monospace engineering aesthetic to light modern technical display: light gray background, white cards, orange accents, modern sans-serif typography
- Layout restructure: changed from vertical stack (stats above table) to side-by-side horizontal layout (3×2 stat grid left, rounds table right) with responsive stacking below 1200px
- Engineering grid system: 2px gray lines trace all panel edges, full-height vertical lines for infinite canvas feel, 20px programmatic dot grid aligned to coordinate system, both scroll with content
- Typography overhaul: 64px bold stat values (was 32px), 11px uppercase labels with 2px letter-spacing, system fonts replacing monospace
- Navigation refinement: solid white background, bold text (weight 600), vertical dividers between items
- Viewport optimization: flexbox body layout constrains to 100vh with no scrollbars, content fills available space precisely, grid overlay uses position:fixed to avoid extending scroll area
- Visual polish: 20px rounded corners (was 2px), prominent drop shadows (0 4px 16px rgba(0,0,0,0.1)), orange accent color (#ff6b35), zebra-striped table rows

**Files touched**:
- `source/web/static/app.css` — complete color system overhaul (light theme, orange accents), typography changes (sans-serif, larger sizes), layout system (flexbox body, side-by-side dashboard grid, viewport constraints), table styling (zebra stripes, internal scrolling), navigation styling (bold text, dividers), shadow enhancements
- `source/web/static/grid.js` — complete rewrite: position:fixed overlay on body (was absolute in container), viewport-relative coordinates, programmatic 20px dot grid, 2px engineering lines, scroll listener for dynamic tracking, removed crosshair symbols
- `source/web/templates/dashboard.html` — wrapped stat-panels and recent-rounds in new `.dashboard-grid` container, removed inline per-panel color styles
- `source/web/templates/base.html` — (grid.js script tag maintained)

**Next**: See HANDOFF.md — apply visual system to other pages, test with real data, verify grid performance

## 2026-05-16 08:23 UTC — Session end

**What was done**:
- Added `--start-maximized` flag to Chrome `--app` launch for fullscreen-on-start
- Added `slideInLeft` CSS keyframe animation with staggered delays on dashboard stat panels (6 panels, 0.1s cascade) and `.recent-rounds` table (0.7s delay)
- Fixed grid overlay positioning bug caused by animations: overlay now starts hidden (`opacity:0`), draws from final element positions on `animationend`, then fades in with 0.5s CSS transition

**Files touched**:
- `source/main.py` — added `--start-maximized` to Chrome subprocess launch args
- `source/web/static/app.css` — `@keyframes slideInLeft`, staggered animation on `.stat-panel` (nth-child delays), animation on `.recent-rounds`
- `source/web/static/grid.js` — overlay starts with `opacity:0` + `transition`, defers `drawGrid()` to `animationend` on `.recent-rounds`, fades in on complete

**Next**: Apply visual theme to other pages, test with real data, verify grid performance

## 2026-05-16 18:51 UTC — Session end

**What was done**:
- Created `docs/CONTEXT.md` — domain glossary with 30+ golf/codebase terms, data model conventions, and calc function reference
- Populated `calc/__init__.py` with package-level re-exports — single import seam for 75+ functions, replaced 4 import blocks in main.py with one `from calc import (...)`
- Consolidated 10 duplicate trend functions into single generic `calc_trend(all_rounds, calc_fn, *args, filter_fn=None)` factory in `scoring.py` — removed ~70 lines of boilerplate across 3 files
- Moved 7 business-logic helpers from `main.py` to new `calc/context.py` (calc_round_vs_par, calc_avg_vs_par, calc_round_vs_rating, calc_avg_vs_rating, calc_penalties_per_round, calc_historical_window, calc_last_year_handicap) — main.py dropped from 778 to ~756 lines
- Moved `STAT_CATALOG` and `DEFAULT_DASHBOARD_STATS` from `calc/scoring.py` to new `web/catalog.py` — broke cross-calc import cycle, presentation concerns now in web layer
- Added Flask `@app.before_request` hook pre-loading `g.settings`, `g.courses`, `g.all_rounds` — eliminated 30+ `load_settings()`/`get_courses()`/`get_all_rounds()` call sites across 13 route handlers
- Consolidated cursor CSS from 7 scattered `cursor: pointer` declarations to 3 centralized rules (`body{cursor:default}`, interactive elements, text inputs)
- Iterated on Chrome launch mode for system cursor support: tried `--app` + env vars, `--new-window` (reverted), X11 forcing — final: `--kiosk` mode for fullscreen immersive with system cursors

**Files touched**:
- `docs/CONTEXT.md` — new domain glossary (50 lines)
- `source/calc/__init__.py` — new package interface re-exporting all public functions (91 lines)
- `source/calc/scoring.py` — added `calc_trend`, removed duplicate trend functions + STAT_CATALOG + cross-module imports (~130 lines removed)
- `source/calc/approach.py` — replaced 3 trend functions with `calc_trend` delegation
- `source/calc/putting.py` — replaced 4 trend functions with `calc_trend` delegation (including filter_fn for putts_trend)
- `source/calc/context.py` — new module with 7 business-logic helpers (61 lines)
- `source/web/catalog.py` — new module with STAT_CATALOG + DEFAULT_DASHBOARD_STATS (163 lines)
- `source/main.py` — before_request hook, consolidated calc imports, route handler simplification, Chrome launch mode changes
- `source/web/static/app.css` — cursor consolidation, cursor:default on body

**Next**: Apply visual theme to other pages, test kiosk mode on Pop!_OS, acceptance smoke test

## 2026-05-16 23:00 UTC — Session end

**What was done**:
- Full dashboard redesign to match design system (`docs/design-system/README.md`):
  - Replaced `app.css` (687→895 lines) — all design tokens inlined, `.ps-dark`/`.ps-light` themes, warm cream paper / cool near-black, mint-only accent
  - IBM Plex Mono (body/labels/table) + Barlow Condensed 200 (display) loaded from Google Fonts
  - Hard rectangles: no `border-radius`, no `box-shadow`, no gradients, 1px hairline rules
  - Layout: 200px fixed sidebar (`.ps-nav` with accent left-border active state, mint-dot `.ps-logo`) + flexible main column
  - Hero numeral: 240px Barlow Condensed 200 with ink-integer, dimmed decimal, mint-fraction pattern
  - 6-column stat strip: `grid-template-columns: repeat(6, 1fr)`, border-top/bottom hairlines, internal dividers via `border-right` on all but last `.ps-stat`
  - Score-pill table: `.ps-score` at 22px, `.ps-topar` at 11px, under-par in mint, handicap rows with accent left-border
  - `grid.js` removed — structural 1px rules replace programmatic overlay
  - Theme system: 12 color themes → light/dark toggle (`.ps-dark` default)
  - Legacy class mappings (`.data-table`, `.btn-accent`, `.stat-panel`, `.btn`, `.stat-value`, `.stat-label`) preserved so non-dashboard pages still function
- Updated `base.html`: Google Fonts preconnect+stylesheet, `ps-dark`/`ps-light` body class, sidebar+main grid layout, removed `grid.js`, `current_page` variable for nav active state
- Updated `settings.html` + `app.js`: light/dark swatches (`theme-swatch-dark`/`theme-swatch-light`), `ps-` body class prefix
- Updated `settings_page()` route: reduced themes list from 12 colors to `["dark", "light"]`, added `current_page`
- Added `current_page="dashboard"` to dashboard route handler
- Verified: 10 routes all return 200, 9 design system checks pass (ps-layout, ps-hero-numeral, ps-stat-strip, ps-table, ps-nav, ps-logo, ps-eyebrow, Google Fonts, no grid.js), no old artifacts detected

**Files touched**:
- `source/web/static/app.css` — complete rewrite (687→895 lines)
- `source/web/static/app.js` — theme swatch default "dark", body class `ps-` prefix
- `source/web/static/grid.js` — deleted
- `source/web/templates/base.html` — Google Fonts, sidebar layout, ps-dark/ps-light theme, nav with current_page
- `source/web/templates/dashboard.html` — hero numeral + 6-col stat strip + score-pill table
- `source/web/templates/settings.html` — light/dark swatches
- `source/main.py` — dashboard route `current_page`, settings route themes→dark/light
- `docs/HANDOFF.md` — updated state/next actions
- `docs/SESSION_LOG.md` — this entry

**Next**: Apply design system to remaining pages (wizards, round detail, courses, stats, settings, season summary)

## 2026-05-17 00:00 UTC — Session end

**What was done**:
- Ran full audit against canonical dashboard example — identified 28 gaps, triaged into P0-P4
- Executed 4 workstreams via subagent-driven-development (writer + critic/spec-review per task):
  - WS1: CSS foundation — layout spacing, token fixes, utility classes (BK-01-04,14,17-19,21-22)
  - WS2: Dashboard template — topbar, player info, hero delta/description, table header, nav items (BK-05,07-11,15,16,20)
  - WS3: Hero chart + sparklines — SVG trajectory chart in hero grid, per-row By-hole sparklines (BK-06,13)
  - WS4: Table columns — 10-column canonical layout with FIR/GIR/Putt/Scr/SG·T (BK-12)
- Fixed WS2 spec review issues: missing route variables for `hi_movement`/`career_low`/`hi_insight`, broken `current_page` on round_entry
- Added JS tooltip to chart dots (native SVG `<title>` unreliable), chart filter chips functional
- Fixed hi_insight to count best-N rounds (not all non-excluded), chart label_v overridden to hero handicap
- Swapped fonts: IBM Plex Mono + Barlow Condensed → JetBrains Mono (self-hosted TTF, NerdFont NL, weights 200/400/500/600/700)
- Removed all Google Fonts CDN links
- Hero numeral: 200px weight 400, decimal dot 50% baseline-aligned
- Updated design system docs (README.md, tokens.css) to reflect JetBrains Mono as source of truth
- Updated BACKLOG.md — 1 deferred item remaining (BK-15 delta arrows)
- Updated HANDOFF.md current state

**Design decisions**:
- Single monospace family (JetBrains Mono) replaces dual display/body font strategy
- Self-hosted fonts (zero external requests) — TTF format, NerdFont NL no-ligature variants
- Hero numeral weight 200→400 for legibility in monospace at large scale
- SVG `<title>` tooltips abandoned for JS-driven tooltip (cross-browser reliability)
- Logo dot `border-radius: 50%` is the sole documented exception to the no-border-radius rule

**Files touched**:
- `source/web/static/app.css` — +100 lines; layout spacing, hero/chart-card CSS, utilities, @font-face declarations, token updates
- `source/web/templates/dashboard.html` — restructured: topbar, hero grid, SVG chart, 10-col table, filter chips, tooltip div
- `source/web/templates/base.html` — player info block, nav item rename, Google Fonts removed
- `source/main.py` — chart trajectory data (4 ranges), sparkline data, FIR/GIR/Scr computation, season label, hi_movement/career_low/hi_insight
- `source/web/static/app.js` — chart filter interactivity, JS tooltip on hover, SVG re-render
- `docs/BACKLOG.md` — new, audit backlog tracker
- `docs/design-system/README.md` — updated font stacks, sizes, weights, border-radius exception
- `docs/design-system/tokens.css` — updated font stacks, weights, hero size, brass token, accent-dim
- `source/web/static/fonts/JetBrainsMono/` — 5 TTF files (200,400,500,600,700)
- `docs/HANDOFF.md` — updated state/next actions
- `docs/SESSION_LOG.md` — this entry

**Next**: Test kiosk mode, acceptance smoke test, apply design system to remaining pages

## 2026-05-27 05:08 UTC — Session end

**What was done**:
- Loaded session memory framework (README, HANDOFF, SESSION_LOG, DECISIONS, RUNBOOK, BACKLOG)
- Reviewed existing multi-user design spec (239 lines) from `docs/superpowers/specs/`
- Brainstormed and refined the multi-user design with user:
  - Clean break to SQLite (no JSON fallback), no CLI tools (all web UI)
  - First-run auto-admin (open registration until first user, then invite-gated)
  - Self-service JSON import at `/settings/import`
  - Flask-WTF for CSRF, bcrypt for passwords
  - Systemd service for LXC deployment (`scripts/pinsheet.service`)
  - Three-phase approach: SQLite → Auth → Multi-user UI
- Cross-referenced spec against actual codebase — found and fixed gaps:
  - Removed references to `manage.py` CLI (killed in brainstorming)
  - Added `round_index` column to preserve `/rounds/{date}/{index}` URLs
  - Fixed systemd service path to `scripts/pinsheet.service`
  - Documented draft functions as implementation detail
  - Launchers at `scripts/launchers/` noted for SECRET_KEY update
- Wrote comprehensive implementation plan (17 tasks, ~1840 lines)
  - Phase A: SQLite migration (5 tasks — store rewrite, import page, systemd, launchers)
  - Phase B: Auth layer (7 tasks — deps, store functions, Flask-Login, routes, templates, @login_required)
  - Phase C: Multi-user UI (5 tasks + polish — view param, user switcher, admin invites, read-only enforcement)
- Ran internal self-review: fixed admin route POST, placeholder removal, missing imports

**Files touched**:
- `docs/superpowers/specs/2026-05-26-multi-user-design.md` — refined from 239-line draft to 410-line approved spec
- `docs/superpowers/plans/2026-05-26-multi-user.md` — new, 1840-line implementation plan
- `docs/HANDOFF.md` — updated state/next actions
- `docs/SESSION_LOG.md` — this entry

**Decisions made**:
- No CLI tools — all admin operations are web UI. Bootstrap via first-run auto-admin.
- JSON import: self-service at `/settings/import` (any user imports own data), not admin-gated
- Drafts: kept as per-user JSON files to minimize SQLite migration scope
- Design system files in `docs/design-system/` — deletion is pre-existing (from prior session), not this session's work

**Next**: Implement Phase A (SQLite migration), Phase B (auth), Phase C (multi-user UI)
