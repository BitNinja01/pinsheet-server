# PinSheet Modern — Design Spec

**Date**: 2026-05-15
**Status**: Approved
**Scope**: Flask + waitress web app replacing the Textual TUI frontend. Same JSON data model, same calc logic, new browser-based UI.

## Motivation

The TUI constraints (monospace grid, no progressive disclosure, color-only emphasis, no animation) limit the design philosophy's goal of making strengths visible and giving the user confidence in their stats. A web UI delivers full CSS layout, rich color-block design, and a more approachable user experience while keeping the same self-contained, no-server-dependency philosophy.

## Architecture

```
Flask (server-rendered pages) + Vanilla JS fetch() (inline mutations) + Jinja2 templates
```

### Data flow

- Navigation: browser GET → Flask route → store reads JSON → calc computes → Jinja2 renders HTML → response
- Inline actions: browser fetch() → Flask `/api/` route → store writes JSON → JSON response → DOM patch

### Hybrid navigation

Pages are server-rendered (full page loads for navigation). Inline actions (save, delete, calculate) use `fetch()` to API endpoints and patch the DOM. No client-side router. This gives reliable page loads with responsive inline interactions.

### Directory structure

```
pinsheet-modern/
├── main.py                    ← Flask app entry, waitress startup
├── store.py                   ← JSON file I/O (ported from original data.py)
├── requirements.txt
├── calc/                      ← Stat calculations (ported 1:1)
│   ├── handicap.py
│   ├── scoring.py
│   ├── approach.py
│   └── putting.py
├── web/
│   ├── static/
│   │   ├── app.css
│   │   ├── app.js
│   │   └── vendor/
│   │       └── chart.js       ← vendored, no CDN (for future trend graphs)
│   └── templates/
│       ├── base.html          ← nav shell
│       ├── dashboard.html
│       ├── round_entry.html
│       ├── round_detail.html
│       ├── report_card.html
│       ├── courses.html
│       ├── course_detail.html
│       ├── course_entry.html
│       ├── stats.html
│       ├── settings.html
│       └── welcome.html
└── data/                      ← .gitignored, created at runtime
```

## Route Map

### HTML Pages (server-rendered)

| Method | Route | Screen |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/rounds/new` | Round entry wizard |
| GET | `/rounds/<date>/<index>` | Round detail / scorecard |
| GET | `/rounds/<date>/<index>/report` | Report card |
| GET | `/courses` | Course list |
| GET | `/courses/<name>` | Course detail |
| GET | `/courses/new` | Course entry wizard |
| GET | `/stats` | Stats screen |
| GET | `/settings` | Settings page |
| GET | `/season` | Season summary |
| GET | `/rounds/<date>/<index>/ghin` | GHIN export |

### JSON API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/dashboard?year=` | Stat panels + rounds table data |
| POST | `/api/rounds` | Save round, return diff + HI |
| PUT | `/api/rounds/<date>/<index>` | Update round |
| DELETE | `/api/rounds/<date>/<index>` | Delete round |
| GET | `/api/rounds/<date>/<index>/report` | Report card data |
| GET | `/api/drafts/round` | Load draft |
| PUT | `/api/drafts/round` | Save draft |
| DELETE | `/api/drafts/round` | Clear draft |
| POST | `/api/courses` | Save course |
| PUT | `/api/courses/<name>` | Update course |
| DELETE | `/api/courses/<name>` | Delete course |
| GET | `/api/drafts/course` | Load draft |
| PUT | `/api/drafts/course` | Save draft |
| DELETE | `/api/drafts/course` | Clear draft |
| GET | `/api/stats` | All 9 stat sections |
| GET | `/api/stats/<section>` | Single section |
| PUT | `/api/settings` | Update settings |

## Navigation Shell (base.html)

Top bar layout:
- Logo/name left ("PinSheet")
- Nav links right: Dashboard · New Round · Courses · Stats · Settings
- Active page highlighted with accent color
- No sidebar — content uses full width

Dark theme default (`theme-green` class on `<body>`). Accent color from CSS custom properties.

## Screens

### Dashboard (`GET /`)

**Stat row**: 6 stat cards in a single horizontal row (flexbox, `justify-content: space-between`):
- Handicap | Avg Score | FIR | GIR | Putts/Rnd | Scramble
- Each card: accent top border, label, large primary value (best-8), smaller secondary (L20: ...) with trend arrow (▲ green if favorable, ▼ red if not)
- Handicap card border-subtitle shows "this time last year" HI when available
- Empty state: italic placeholder text (e.g., "Play 3+ rounds to see handicap")

**Recent Rounds table**: below stat row. Columns: Date, Course, Tees, Score, +/-, Diff. Rounds used in handicap index get accent background tint. Sortable by column click. Click row → round detail page.

**Trend graphs**: Chart.js line charts (6 metrics, 3×2 grid) — deferred. Not in initial build.

### Round Entry Wizard (`GET /rounds/new`)

Progressive disclosure form. Each step reveals the next as the previous is completed. Auto-save draft via debounced fetch (500ms) to `/api/drafts/round`. On next visit, if draft exists, offer Resume / Discard.

**Steps:**

1. **Date** — date picker input, defaults to today
2. **Course** — dropdown from saved courses, "Add new course" link
3. **Tee** — dropdown filtered by selected course, showing yardage + rating/slope
4. **Holes** — radio: Full 18 / Front 9 / Back 9
5. **Transport** — radio: Walking / Riding (optional, skippable)
6. **Entry mode** — radio: Detailed (hole-by-hole) or Score Only (total gross)
7. **Hole detail** (if detailed) — grid of 18 (or 9) rows:
   - Columns: Hole #, Par (pre-filled), Yardage, Score, Fairway (dropdown), GIR (dropdown), Putts, Penalties
   - Fairway codes: H · L · R · OBL · OBR · N
   - GIR codes: H · L · R · S · LO · OBL · OBR · OBS · OBLO
   - Totals row auto-updates via JS
   - Net score computed on the fly
8. **Score only** (if score-only mode) — single number input for total gross
9. **Notes** — textarea

Submit → POST `/api/rounds` → acknowledgment or report card redirect (per settings).

**Validation**: course + tee required before hole entry reveals. Date required before course.

### Round Detail / Scorecard (`GET /rounds/<date>/<index>`)

Full hole-by-hole HTML table:
- Columns: Hole #, Par, Yardage, Gross, Fairway, GIR, Putts, Penalties
- Color-coded cells:
  - Birdie (score ≤ par-1): accent green
  - Eagle+ (score ≤ par-2): bold accent green
  - Bogey (score = par+1): subtle warning
  - Double+ (score ≥ par+2): warning red
  - 1-putt: bold accent
  - 3-putt+: red
  - Penalties > 0: red highlight
- OUT / IN / TOT subtotal rows

Summary bar at top: Date · Course · Tees · Total · +/- · Diff · HI after

Notes displayed below scorecard.

Action buttons: Edit (inline), Delete (confirmation modal → redirect /), Report Card link, GHIN export link.

### Report Card (`GET /rounds/<date>/<index>/report`)

Two-column table: stat name | this round | L20 avg | delta (▲/▼ with color)

Stats list:
- Score vs par, Score vs rating, Par or better %, Blow-up rate
- FIR %, GIR %, Par 3/4/5 avg score, Putts/round, Putts per GIR
- 1-putt %, 2-putt %, 3-putt %, Scramble %, Penalties/round

Green arrow = improving on higher_better stats, red arrow = worsening.

### Courses

**Course list** (`GET /courses`):
- Table: Name, Location, Times Played, Last Played
- Click row → course detail
- "Add Course" button → course entry wizard

**Course detail** (`GET /courses/<name>`):
- Header: name, location
- Tee sets section: table with Tee, Rating, Slope, Yardage, Front Rating/Slope, Back Rating/Slope
- Hole-by-hole section: table with Hole, Par, Index, Yardage per tee
- Edit / Delete buttons (delete removes from courses.json + updates rounds referencing it)
- Course history section: times played, first/last round dates

**Course entry wizard** (`GET /courses/new`):
Progressive disclosure, same pattern as round wizard:
1. **Name** — text input
2. **Location** — city, state, country (optional)
3. **Tees** — add one or more. Per tee: name/color, rating, slope, yardage, front rating/slope, back rating/slope. "Add another tee" button
4. **Holes** — 18-row grid: Hole #, Par, Handicap Index, Yardage per tee. Pre-fill from previous tees
5. **Review** — summary of all entered data, confirm save

Auto-save draft via `/api/drafts/course`. Resume/discard on next visit.

### Stats Screen (`GET /stats`)

Sidebar navigation with 9 sections:
1. Scoring
2. Penalties
3. Fairways
4. Greens
5. Putting
6. Short Game
7. Momentum
8. Bests
9. Trends

Each section:
- Prescriptive headline (italic, synthesizes most actionable benchmark gap or trend)
- Data table: Best 8 · Last 5 · Last 10 · Last 20 columns
- Benchmark comparison column (where applicable, vs handicap-level benchmark)
- Color-coded cells: green = above benchmark, red = below

Bests section: personal bests list (lowest gross, lowest diff, most FIR, most GIR, fewest putts) with dates.
Trends section: per-round values as table rows — deferred, no graphs yet.

### Settings (`GET /settings`)

- Theme selector: visual swatch grid (12 themes from original). Click applies immediately via CSS class swap
- Toggles (checkboxes):
  - Include 9-hole rounds in handicap
  - Auto-calculate handicap from rounds
  - Show report card after completing a round
  - Season tracking enabled
- Season date range: start month/day, end month/day (shown when season tracking enabled)
- Home course / default tees: dropdowns
- Handicap target: number input (optional)
- Restore defaults button

Changes auto-save via `PUT /api/settings` on toggle/change.

### Welcome Screen (first launch only)

Shown via `welcome_shown` flag in `settings.json`. Brief intro paragraph about PinSheet. "Get Started" button → writes `welcome_shown: true`, redirects to dashboard.

### Season Summary

Navigable from dashboard. Single page showing season-level aggregations:
- HI journey: start → end handicap for the season, with delta
- Rounds played, most played course, golfiest month, most common day
- Score breakdown (eagles, birdies, pars, bogeys, doubles, triple+)
- Best stretches: best single round, best 3-round stretch, biggest improvement
- Mileage: total yards walked / ridden (miles)
- milestones: first time breaking score thresholds (100, 95, 90, 85, 80, 75, 70) and HI thresholds
- Penalty-free rounds count, hole-in-ones count
- Best FIR and GIR rounds

### GHIN Export

Navigable from round detail. Generates formatted text output for pasting into GHIN handicap services:
- Date, course, tees, rating, slope, adjusted gross, differential
- Single-round or batch (select range)

## Themes

12 themes matching original (`pinsheet-green`, `pinsheet-ocean`, `pinsheet-amber`, `pinsheet-sunset`, `pinsheet-purple`, `pinsheet-teal`, `pinsheet-crimson`, `pinsheet-midnight`, `pinsheet-rose`, `pinsheet-gold`, `pinsheet-slate`, `pinsheet-lime`). Default: `pinsheet-green`.

Theme name stored in `settings.json`. Applied as `<body class="theme-{name}">`. CSS uses `:root` defaults (dark green) and `.theme-{name}` overrides for `--accent`, `--accent-dim`, `--surface-alt`.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| HTML rendering | Flask + Jinja2 (server-rendered) | Simple, reliable. Fast page loads. No JS framework build step |
| Inline interactivity | Vanilla JS fetch() | Handles save/delete/calculate without page reloads. No framework needed |
| Wizards | Progressive disclosure, single page | Better UX than multi-page. Auto-save per step. Resumable |
| Auto-save drafts | Debounced 500ms fetch() | Prevents data loss without hammering the API |
| Charts | Vendored Chart.js, no CDN | Needed for dashboard trend graphs, no runtime network dependency |
| CSS | Plain CSS, custom properties | No preprocessor. Themes via CSS variable overrides |
| Theme switching | CSS class on body, instant | No page reload. Settings auto-save on change |
| Data format | Identical to original Python | Drop-in replacement for data/ directory |

## Distribution

Same launcher-script pattern as original pinsheet:
- `launch.sh` for Linux/macOS
- `launch.bat` for Windows
- Scripts create `.venv`, pip install from `requirements.txt`, launch `python main.py`
- Server starts on `127.0.0.1:8420` (or first free port), browser opens via `webbrowser.open()`
- Ctrl+C to stop server

## Implementation Phases

### Phase 1: Foundation (done)
- Calc functions ported 1:1
- Store layer ported
- Flask server shell
- Dashboard with stat panels (real data)

### Phase 2: Rounds (next)
- Round entry wizard (all steps, progressive disclosure, draft save/resume)
- Round detail / scorecard (view + edit + delete)
- Report card
- All round API endpoints

### Phase 3: Courses
- Course list + detail
- Course entry wizard
- Course history on detail page

### Phase 4: Stats
- Stats screen with 9-section sidebar
- Benchmark comparison
- Prescriptive headlines

### Phase 5: Settings & Polish
- Settings page (theme swatches, toggles)
- Welcome screen
- GHIN export
- Empty states, responsive polish

### Phase 6: Distribution
- Launcher scripts
- dist.sh packaging
- Release workflow

## In Scope

- All screens from original pinsheet (dashboard, round entry/detail/report, courses, stats, settings, welcome, GHIN export, season summary)
- All calculations (handicap, scoring, approach, putting)
- JSON data format unchanged
- Draft save/resume for both wizards
- 12 themes via CSS custom properties
- Single-user local web app (Flask + waitress)

## Out of Scope

- Mobile responsive (desktop-first)
- Trend graphs (Chart.js) — deferred
- Multi-user / authentication
- PWA / offline mode
- Data migration (drop-in compatible)
- Backward compatibility with Python TUI releases (data format is identical)
