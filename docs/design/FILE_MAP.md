# File Map (glob → responsibility)

Fast navigation for agents and new contributors. Paths are relative to the
[pinsheet-server](https://github.com/BitNinja01/pinsheet-server) repo root.
Jump by glob instead of reading the tree.

## Application code

| Glob | Responsibility | Notes |
|------|----------------|-------|
| `source/main.py` | App bootstrap: Flask app, login manager, limiter, CSRF, route registration | Entry point; also `_load_user` |
| `source/routes/*.py` | HTTP controllers (thin). One `register_*_routes(app, …)` per file | See per-file table below |
| `source/store.py` | **All** SQLite reads/writes | The only module that runs SQL besides `database.py` |
| `source/database.py` | Schema (`CREATE TABLE …`), connection, migrations | `set_db_path`, `init_db` |
| `source/models.py` | Dataclasses + `dict_to_round` / `dict_to_course` / `dict_to_hole` parsers | `dict_to_hole` tolerates bad ints (`_safe_int`) — runs on every DB read |
| `source/request_data.py` | Per-request cached accessors on Flask `g` | `get_courses`, `get_all_rounds_for_user`, `base_context` |
| `source/calc/*.py` | Pure calculation. No I/O, deterministic | See per-file table below |
| `source/extensions.py` | Flask extension init | |
| `source/plugin.py`, `source/plugin_loader.py` | Plugin registry + hooks | `fire_hook`, `_plugins`, `discover_plugins` |
| `source/web/templates/**/*.html` | Jinja server-rendered pages | `base.html` is the shell; `stats/*.html` are sections |
| `source/web/static/app.js` | Entry-form JS + draft autosave | Talks to `/api/drafts/*` and `/api/rounds` |
| `source/web/static/*.css` | Styles | |
| `source/web/charts.py`, `source/web/catalog.py` | Server-side chart SVGs + template component catalog | `sparkline_svg`, macros |
| `plugins/**` | Drop-in plugins | Gated by `plugin_states` table |

### `source/routes/*` detail

| File | Owns |
|------|------|
| `auth.py` | `/login`, `/register`, `/logout`, `/reset-password` |
| `dashboard.py` | `/` (home), `/profile`, `/challenges/*`, `/api/welcome` |
| `rounds.py` | `/rounds*`, `/api/rounds*`, `/api/drafts/*`, round detail + report card |
| `courses.py` | `/courses*`, `/api/courses*` |
| `stats.py` | `/stats/*`, `/season`, `/admin/invites` |
| `settings.py` | `/settings*`, `/api/settings` |
| `matches.py` | `/matches/*` (head-to-head) |
| `bag.py` | `/bag*` (clubs) |
| `admin.py` | `/api/admin/plugin-state` |

### `source/calc/*` detail

| File | Owns |
|------|------|
| `handicap.py` | differential, ESC (`calc_hole_scores`), `calc_course_handicap`, `calc_handicap_index`, `count_table_n`, `get_best_n_rounds` |
| `scoring.py` | scoring averages, vs par/rating, blow-up rate, par-type scoring, historical window |
| `approach.py` | FIR/GIR/scramble %, miss tendencies, scoring by fairway/GIR |
| `putting.py` | putts per round/GIR, 1/2/3/4-putt %, putts by par type |
| `analysis.py` | penalty stats, momentum/recovery |
| `milestones.py` | first-score milestones, biggest improvement, best stretches |
| `seasons.py` | season aggregation |
| `composite.py` | composite/report metrics |
| `rankings.py` | multi-user rankings, challenge standings |
| `__init__.py` | re-exports the public calc surface |

## Tests & CI

| Glob | Responsibility |
|------|----------------|
| `tests/test_*.py` | pytest suite (unit + HTTP e2e) |
| `tests/conftest.py` | shared fixtures (`make_round`, `make_course`, `tmp_data_dir`) |
| `tests/test_e2e_rounds_scores.py` | **end-to-end regression** for the round/score/handicap flow (drives real HTTP endpoints) |
| `tests/test_handicap.py`, `test_scoring.py`, … | calc unit tests |
| `.github/workflows/ci.yml` | runs `pytest --cov` on PRs to `dev`/`main` and pushes to `dev` |
| `pyproject.toml` | pytest config (`testpaths=tests`, `pythonpath=source`), coverage gate |

## Ops

| Glob | Responsibility |
|------|----------------|
| `scripts/*.sh`, `scripts/launchers/*` | install / update / launch |
| `scripts/pinsheet.service` | systemd unit |
| `docs/PLUGINS.md` | plugin authoring guide (in the app repo) |

## Where things are NOT

- No ORM, no migrations framework — schema is raw SQL in `database.py`.
- No frontend build — templates are server-rendered; JS is a single static file.
- SQL lives **only** in `store.py` / `database.py`. If you find SQL in a route,
  that is a layering violation.
