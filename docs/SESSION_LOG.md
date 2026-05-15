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
