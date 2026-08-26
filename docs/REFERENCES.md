# References & Refresh Guide

A single linked index of the authoritative sources behind PinSheet Server's docs, plus a checklist for keeping docs current when an external rule or internal code changes.

- **External authorities** — the upstream sources of truth (handicap rules, doc methodology, tech stack).
- **Internal code map** — which source file(s) implement each documented topic, so docs get re-derived from code.
- **Refresh checklist** — change trigger → files/docs to update.
- **Doc inventory** — every doc in the repo, its Diataxis quadrant, and purpose.

---

## External authorities

Each URL below was checked. Links marked **Verified (fetch)** returned live content when fetched. Links marked **Verified (search)** are confirmed as the canonical official source via web search but return `HTTP 403` to automated fetching (bot protection) — open them in a browser.

### Handicap math — source of truth

| Source | URL | Status |
|--------|-----|--------|
| World Handicap System (WHS) — official home, jointly operated by the USGA and The R&A | https://www.whs.com/ | Verified (search); fetch blocked (403) |
| USGA Handicapping — home / resources | https://www.usga.org/content/usga/home-page/handicapping.html | Verified (search); fetch blocked (403) |
| Rules of Handicapping (2024 revision, USGA edition, PDF) | https://www.usga.org/content/dam/usga/pdf/2024-revision/2024-Rules-of-Handicapping-USGA.pdf | Verified (search); fetch blocked (403) |

The Handicap Index math in this repo (best-8-of-last-20 differentials, Course Handicap, score differential) is governed by the **Rules of Handicapping**. Use the WHS/USGA text above as the authority when changing `source/calc/handicap.py`.

### Documentation methodology

| Source | URL | Status |
|--------|-----|--------|
| Diataxis documentation framework (tutorial / how-to / reference / explanation) | https://diataxis.fr/ | Verified (search) |
| Diataxis — Start here (five-minute intro) | https://diataxis.fr/start-here/ | Verified (search) |

### Tech stack (from `README.md` and `pyproject.toml`)

| Library | Official docs | Status |
|---------|---------------|--------|
| Flask (3.1.x) | https://flask.palletsprojects.com/ | Verified (fetch) |
| Jinja2 (3.1.x) | https://jinja.palletsprojects.com/ | Verified (fetch) |
| Waitress (3.0.x) | https://docs.pylonsproject.org/projects/waitress/en/stable/ | Verified (fetch) |
| bcrypt | https://pypi.org/project/bcrypt/ | Verified (fetch) |
| Flask-Login (0.6.x) | https://flask-login.readthedocs.io/en/latest/ | Verified (fetch) |
| Flask-WTF (1.2.x) | https://flask-wtf.readthedocs.io/en/1.2.x/ | Verified (fetch) |
| Flask-Limiter (4.x) | https://flask-limiter.readthedocs.io/en/stable/ | Verified (fetch) |
| Flask-Talisman (CSP / security headers) | https://pypi.org/project/Flask-Talisman/ | Verified (search) |
| Chart.js | https://www.chartjs.org/docs/latest/ | Verified (fetch) |
| Werkzeug (WSGI toolkit, Flask dependency) | https://werkzeug.palletsprojects.com/ | Verified (search) |

---

## Internal code map

Repo-relative paths. Each doc topic maps to the source file(s) that are its ground truth. Re-derive docs from these files, not from memory.

| Topic | Ground-truth source | Related docs |
|-------|---------------------|--------------|
| **Handicap Index / Course Handicap (WHS math)** | `source/calc/handicap.py` (`calc_handicap_index`, `calc_course_handicap`, `calc_round_dif`, `calc_expected_9hole_dif`, `count_table_n`, `get_best_n_rounds`, `calc_effective_diffs`) | `docs/STATS.md` (Handicap section), `README.md` |
| **Handicap trend / current-vs-previous index** | `source/calc/composite.py` (`current_and_previous_handicap_index`, `handicap_trend_from_stored`, `best_n_rounds`, `last_n_rounds`) | `docs/STATS.md` (Trends) |
| **Per-hole shorthand codes (fairway/GIR/OB)** | `source/models.py` (`HoleData`, `RoundData`, `TeeData`, `CourseData`, `HoleDef`), `source/calc/analysis.py` (`_OB_CODES`), `source/routes/rounds.py` (round entry/parse) | `docs/STATS.md` (Per-Hole Stats) |
| **Scoring stats** (averages, distribution, par-or-better, consistency, by-hole-type) | `source/calc/scoring.py` | `docs/STATS.md` (Scoring) |
| **Fairways / greens / scrambling** | `source/calc/approach.py` (`calc_fir_percent`, `calc_gir_percent`, `calc_scramble_percent`, trends) | `docs/STATS.md` (Fairways, Greens, Short Game) |
| **Putting stats** | `source/calc/putting.py` | `docs/STATS.md` (Putting) |
| **Penalties / momentum / recovery** | `source/calc/analysis.py` | `docs/STATS.md` (Penalties, Momentum) |
| **Personal bests / nemesis & best holes** | `source/calc/milestones.py` | `docs/STATS.md` (Trends) |
| **Season aggregates** (rounds/year, streaks, golfiest month) | `source/calc/seasons.py` | `docs/STATS.md` |
| **Multi-user rankings / leaderboard form** | `source/calc/rankings.py` | `README.md` (Multi-User) |
| **Public stats API surface** (aggregated exports) | `source/calc/__init__.py` | `docs/STATS.md` |
| **Data storage / DB connection & schema** | `source/database.py` (`set_db_path`, connection helpers) | `README.md` (Data Storage) |
| **Data access layer** (courses, rounds, users, drafts, invites, import) | `source/store.py` | `README.md` (Data Storage, Migrating) |
| **Data model / dataclasses** | `source/models.py` | `docs/STATS.md` (Data Model) |
| **Plugin discovery & loading** | `source/plugin_loader.py` | `docs/PLUGINS.md` |
| **Plugin hooks** | `source/plugin.py` (`fire_hook`) | `docs/PLUGINS.md` |
| **Secure plugin contract** (route/nav/block registration) | `source/plugin_api.py` | `docs/PLUGINS.md` |
| **Bundled plugins directory** | `plugins/` (drop-in packages) | `docs/PLUGINS.md`, `README.md` (Plugins) |
| **Auth (login / register / reset / invite codes)** | `source/routes/auth.py`, `source/store.py` (invite/user helpers) | `README.md` (Multi-User) |
| **CSRF + rate-limiting wiring** | `source/extensions.py` (`init_app`), uses Flask-WTF `CSRFProtect` + Flask-Limiter | `README.md` (Tech Stack) |
| **API-key scope enforcement** | `source/auth_keys.py` (`@require_permission`, wired on rounds/stats/courses routes) | — |
| **Per-request data caching** | `source/request_data.py` (`get_settings`, `get_courses`, `get_all_rounds_for_user`) | — |
| **Web routes / blueprints** | `source/routes/*.py` (`admin`, `auth`, `bag`, `courses`, `dashboard`, `matches`, `rounds`, `settings`, `stats`) | — |
| **Templates (Jinja2)** | `source/web/templates/*.html` | `README.md` (Tech Stack) |
| **Front-end assets** | `source/web/static/app.css`, `source/web/static/app.js`, `flatpickr.*` | — |
| **Stat catalog + chart data (Chart.js)** | `source/web/catalog.py`, `source/web/charts.py` | `docs/STATS.md` |
| **Setup / run / CLI args / server bootstrap** | `source/main.py` (waitress + dev server, `--host/--port/--data`, browser open) | `README.md` (Quick Start, Installation, Run) |
| **Deployment (systemd) & scripts** | `scripts/install-service.sh`, `scripts/pinsheet.service`, `scripts/update.sh`, `scripts/dist.sh` | `README.md` (Deployment, Updating) |
| **Dependency pins / project metadata** | `pyproject.toml`, `requirements.txt` | `README.md` (Tech Stack) |

> See the Doc inventory below for the full list of project docs and their Diataxis quadrants.

---

## Refresh checklist

One line per source of truth: change trigger → files/docs to update.

- **WHS / Rules of Handicapping change** → update `source/calc/handicap.py` (and `source/calc/composite.py` for trend/current-index), then re-check the Handicap and Trends sections of `docs/STATS.md` and the handicap explanation in `docs/ARCHITECTURE.md`.
- **User-facing flow / UI labels / routes change** → re-verify `docs/TUTORIAL.md` (it walks a live end-to-end path: register → welcome → add course → enter round → view stats) against the actual `source/routes/*` and templates.
- **Per-hole shorthand codes change** (fairway/GIR/OB tokens) → update `source/models.py`, `source/calc/analysis.py` (`_OB_CODES`), and round-entry parsing in `source/routes/rounds.py`; then re-check the Per-Hole Stats section of `docs/STATS.md`.
- **A derived stat is added / renamed / removed** → update the relevant `source/calc/*.py` module and `source/web/catalog.py`; then re-check `docs/STATS.md`.
- **Dashboard chart added / changed** → update `source/web/charts.py` + templates/`app.js`; then re-check the Trends section of `docs/STATS.md` and the Chart.js note in `README.md`.
- **DB schema / storage layout change** → update `source/database.py` and `source/store.py` (and `source/models.py` if dataclasses change); then re-check the Data Model / Data Storage sections of `docs/STATS.md` and `README.md`.
- **Plugin API / hooks / contract change** → update `source/plugin_loader.py`, `source/plugin.py`, `source/plugin_api.py`; then re-check `docs/PLUGINS.md`.
- **Auth / invite-code / rate-limit / CSRF behavior change** → update `source/routes/auth.py`, `source/extensions.py`, `source/store.py`; then re-check the Multi-User and Tech Stack sections of `README.md`.
- **CLI flags / run / deployment change** → update `source/main.py` and `scripts/*`; then re-check the Quick Start, Installation, Run, and Deployment sections of `README.md`.
- **Dependency version bump** → update `pyproject.toml` / `requirements.txt`; then re-check the Tech Stack list in `README.md` and the version notes in this file's External authorities table.

---

## Doc inventory

Diataxis quadrants: **Tutorial** (learning-oriented), **How-to** (task-oriented), **Reference** (information-oriented), **Explanation** (understanding-oriented).

| Doc | Diataxis quadrant | Purpose |
|-----|-------------------|---------|
| `README.md` | How-to (+ Tutorial for Quick Start) | Install, configure, run, deploy, and update the server; overview of features and tech stack. |
| `docs/TUTORIAL.md` | Tutorial | Learning-oriented walkthrough: record your first round and see your stats. |
| `docs/STATS.md` | Reference | Data model (courses, per-hole shorthand, round metadata) and the full catalog of 50+ derived stats. |
| `docs/PLUGINS.md` | How-to (+ Reference) | Plugin developer guide — build, register, and load drop-in plugins (pages, hooks, DB tables, nav). |
| `docs/ARCHITECTURE.md` | Explanation | Why the system is built as it is — shorthand, WHS math, SQLite-only, SSR, plugin model, multi-user scoping. |
| `docs/REFERENCES.md` | Reference | This file — source-of-truth links, code map, and refresh checklist. |

> `.context/todos.md` exists but is internal working notes, not project documentation, and is excluded from this inventory.
