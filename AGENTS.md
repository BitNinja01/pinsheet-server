# AGENTS.md

This file provides guidance to OpenCode when working with code in this repository.

## What PinSheet Modern Is

A web-based golf stats tracker built with Python (Flask + waitress). Replaces the Textual TUI frontend with a browser-based UI while preserving the same JSON data model and stat calculations. Golfers enter stats after a round using a physical-scorecard shorthand, and PinSheet computes handicap index, derived stats, and trend graphs.

Same philosophy as the original: self-contained app with no server dependency, no database, no network calls — all data is stored in JSON files in `data/`. The Flask server runs locally on `127.0.0.1` and opens the user's browser.

## Before you start

- All relevant project documentation can be found in docs/
- Original source of truth for data model and calculations: `/mnt/Claude/repositories/pinsheet/source/`
- Data format is identical to the original Python pinsheet — same JSON files, same string-stored numerics
- **Do not reference `/mnt/Claude/repositories/pinsheet-go/`** — that repo is abandoned

### Claude memory files (ignore)
This project may contain Claude Code artifacts (`CLAUDE.md`, `.claude/`). These are managed by a different tool. OpenCode must never read, write, or modify them — they do not exist as far as this agent is concerned.

## Process rules

These apply to every coding session, no exceptions.

### Design freeze before first write
For any visual/UI feature, produce a text wireframe (ASCII layout sketch) and get it confirmed before writing code. Never iterate on format/layout by rewriting the full file — settle the design in conversation first.

### Scope gate
Before implementing, write out explicit "in scope / out of scope" decisions.

### Edit discipline
Every `oldString` in an edit call must include at least 2–3 lines of surrounding context — never match on a bare function name, single-line CSS property, or lone closing brace. If a match has any chance of being ambiguous, use `grep` or `read` first to confirm uniqueness.

### Pre-edit read
Re-read the target file section before every edit, even if it was just written.

### Post-change verification
After writing any `.py` file, run `python -m py_compile` on it. Check that templates render without error.

## Commands

**Run the app (development):**
```bash
python source/main.py
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Push to remote:**
```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/GITEAKEY02 -o StrictHostKeyChecking=no" git push
```

There are no tests and no linter configured yet.

## Architecture

### Source layout
- `main.py` — Flask app entry point; route definitions; `waitress` server startup
- `store.py` — all data access and persistence (JSON file I/O)
- `calc/` — stat calculation functions (no I/O, no UI)
  - `handicap.py` — WHS formula, differentials, course handicap
  - `scoring.py` — scoring stats, distribution, trends, STAT_CATALOG
  - `approach.py` — FIR %, GIR %, miss tendencies, OB stats
  - `putting.py` — putts per round, distribution, scramble
- `web/templates/` — Jinja2 HTML templates
- `web/static/` — CSS, JS, vendored libraries (Chart.js)

### Data layer (`store.py`)
Module-level functions handle all persistence, ported 1:1 from the original `source/data.py`:
- `load_settings` / `save_settings` — reads/writes `data/settings.json`
- `get_courses` / `get_rounds(year)` — reads courses and rounds from disk
- `get_all_rounds(limit)` — reads all rounds across year files, newest first
- `save_course` / `save_round` / `save_course_draft` / `save_round_draft` — writes to disk
- `load_course_draft` / `load_round_draft` / `clear_course_draft` / `clear_round_draft` — draft lifecycle
- `delete_course` / `delete_round` / `rename_course` — mutations
- `init_data_dir` — creates the data directory on first run
- `get_slope_rating` — extracts slope/rating from tee data for a given holes selection

The data directory resolves relative to `main.py` (repo root).

### Data storage
- `data/courses.json` — all courses keyed by name
- `data/rounds/<year>.json` — rounds keyed by date string then index integer
- `data/settings.json` — user preferences
- `data/course_draft.json` / `data/round_draft.json` — in-progress wizard state
- `data/handicap_benchmarks.json` — benchmark lookup table

Round data uses strings for numeric values (gross, putts, etc.). Parse with `int()` / `float()` before arithmetic.

### Hole-data shorthand
Fairway codes: `H` (hit) · `L` · `R` · `OBL` · `OBR` · `N` (no attempt, par 3s)  
GIR codes: `H` · `L` · `R` · `S` (short) · `LO` (long) · `OBL` · `OBR` · `OBS` · `OBLO`

### Calc functions (ported 1:1)
All `calc_*` functions in `calc/` are pure functions that take round/course dicts as arguments (no disk I/O). Ported directly from the original Python codebase — same formulas, same edge cases, type-for-type compatible.

### Web layer
- **Templates**: Jinja2 in `web/templates/`. `base.html` provides the shell (header, nav, CSS includes). Other templates `{% extends "base.html" %}`.
- **Static files**: Served from `web/static/` at `/static/` URL prefix.
- **CSS**: Plain CSS with custom properties for theming. No preprocessor.
- **JS**: Keep it vanilla. No framework build step. Chart.js vendored in `web/static/vendor/` (no CDN).

### Themes
Theme colors defined in CSS custom properties. The active theme name is stored in `settings.json` under `theme`. Body gets class `theme-{name}` for theme-scoped CSS.

## Navigation

Flask uses standard HTTP GET navigation — routes map to pages, links navigate between them. No client-side router.

| Route | Screen |
|---|---|
| `GET /` | Dashboard |
| `GET /rounds/new` | Round entry wizard |
| `GET /rounds/{date}/{index}` | Round detail (scorecard) |
| `GET /courses` | Course list |
| `GET /courses/{name}` | Course detail |
| `GET /courses/new` | Course entry wizard |
| `GET /stats` | Stats screen |
| `GET /settings` | Settings page |

API routes at `/api/` prefix serve JSON for AJAX/fetch calls.

## Style conventions

### Python
- Standard library imports → third-party → local, each group separated by a blank line
- All function signatures have return type hints
- No comments by default — only when the *why* is non-obvious
- Logging: `_log = logging.getLogger("pinsheet")`, use `%s` formatting, never f-strings

### CSS
- Custom properties at `:root` for theming
- Dark theme default
- Static panels: grid layout, bordered cards with accent color
- Use CSS grid/flexbox — no dependency on a CSS framework

### Templates
- Consistent indentation (2 spaces)
- Jinja2 filters for formatting: `{{ value|round(1) }}`
- Empty states have italic placeholder text

### Naming
| Thing | Convention | Example |
|---|---|---|
| Flask route handler | `snake_case` | `def round_detail(date, index):` |
| CSS classes | `kebab-case` | `.stat-panel`, `.app-header` |
| Store functions | `verb_noun` | `get_courses`, `save_round` |
| Calc functions | `calc_` prefix | `calc_handicap_index` |
| Templates | `snake_case.html` | `dashboard.html`, `round_detail.html` |
