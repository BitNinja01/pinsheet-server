# Architecture

## Stack

- **Language:** Python `>= 3.11`
- **Web framework:** Flask 3
- **Server (prod):** Waitress
- **Auth:** Flask-Login (session cookies) + bcrypt password hashes
- **CSRF / rate limiting:** Flask-WTF, Flask-Limiter
- **Persistence:** SQLite (single file, `data/pinsheet.db`) via the stdlib
  `sqlite3` module — no ORM
- **Templating:** Jinja2 server-rendered HTML; a small amount of vanilla JS in
  `source/web/static/app.js` for the entry forms and draft autosave
- **Extensibility:** in-repo plugin system (`source/plugin*.py`, `plugins/`)

There is no separate frontend build. Pages are server-rendered; the JSON `/api/*`
endpoints back the interactive round/course entry screens.

## Layered structure

```
HTTP request
  │
  ▼
source/routes/*.py      ── Flask view functions (thin controllers)
  │   validate + shape request, call store + calc, render/return JSON
  ▼
source/request_data.py  ── per-request cached accessors (g._courses, g._all_rounds, …)
  │
  ├─► source/store.py    ── all SQLite reads/writes; the ONLY module that talks to the DB
  │        │
  │        ▼
  │      source/database.py  ── schema (CREATE TABLE …), connection, migrations
  │
  └─► source/calc/*.py   ── pure functions: handicap, differentials, stats. No I/O.
           │
           ▼
      source/models.py   ── dataclasses (RoundData, CourseData, HoleData, …) + dict_to_* parsers
```

**Rules of the layering (enforced by convention, see `INVARIANTS.md`):**

- Only `store.py` (and `database.py`) touch SQLite. Routes never run SQL.
- `calc/*` is pure — no DB, no Flask, deterministic. This is why it is unit-test
  heavy and safe to call from anywhere.
- Routes convert user input → dicts → `dict_to_round`/`dict_to_course` typed
  models, then persist via `store.save_round` etc.
- `request_data.py` memoises expensive reads on Flask's `g` for the request.

## Request lifecycle (typical page)

1. Flask-Login resolves the session cookie → `current_user` (`main._load_user`).
2. The view calls `request_data` accessors (`get_courses()`, `get_all_rounds_for_user()`),
   which lazily load from `store` and cache on `g`.
3. The view calls `calc/*` to derive differentials, handicap, stats.
4. The view renders a Jinja template (`source/web/templates/*.html`) via
   `base_context(**extra)` or returns JSON for `/api/*`.

## Data model (SQLite tables)

Defined in `source/database.py`. Key tables:

| Table | Purpose | Notable columns / constraints |
|-------|---------|-------------------------------|
| `users` | accounts | `username UNIQUE`, `is_admin` |
| `courses` | course + tees + holes (JSON blobs) | `name UNIQUE` |
| `rounds` | one row per played round | `UNIQUE(user_id, date, round_index)`; `holes` JSON; `differential`, `computed_handicap`, `differential_locked`, `excluded` |
| `settings` | per-user prefs | `include_9hole`, units, … |
| `invite_codes` | registration gating | |
| `password_reset_tokens` | reset flow | 24h expiry |
| `matches` / `match_players` / `match_rounds` | head-to-head play | `UNIQUE(match_id, user_id[, round_id])` |
| `challenges` / `challenge_participants` | stat leaderboards | |
| `clubs` / `bag_slots` | the bag feature | |
| `plugin_states` | enable/disable plugins | |

### The `rounds` row (the heart of the app)

- `round_index` disambiguates **multiple rounds on the same date** for a user.
  It is auto-assigned to the lowest free slot by `store.next_round_index()`.
  (Historically this was hardcoded to `0`, which silently overwrote a second
  same-day round — see `INVARIANTS.md`.)
- `holes` is a JSON object `{ "1": {gross, putts, fairway, gir, penalties}, … }`.
  `entry_mode` is either `detailed` (per-hole) or `score_only` (just a total).
- `differential` is the round's score differential. The literal string `"0"` is
  an **exclusion sentinel** — the handicap calc skips it. Incomplete rounds and
  rounds with no real score store `"0"` so they never pollute the index.
- `differential_locked` means a user manually overrode the differential; the
  recompute cascade must not touch it.
- `computed_handicap` is the handicap index *as of that round* (a running value,
  used for course-handicap / net calculations at edit and display time).

## The handicap engine (`source/calc/handicap.py`)

WHS-style computation:

1. **Round differential** — `calc_round_dif(slope, adjusted_gross, rating) =
   round((113 / slope) * (adjusted_gross - rating), 1)`.
   `adjusted_gross` applies per-hole *net double bogey* caps
   (`calc_hole_scores` → equitable stroke control) using the player's current
   course handicap.
2. **Effective differentials** — `calc_effective_diffs` gathers eligible rounds'
   differentials. Excluded rounds, `differential in ("", "0")`, and (unless
   `include_9hole`) 9-hole rounds are dropped.
3. **Best-N of last 20** — `count_table_n(n)` gives how many of the lowest
   differentials to average (WHS table: 3→1, …, 20→8). Fewer than 3 rounds ⇒
   **no index yet** (`calc_handicap_index` returns `None`).
4. **Course handicap** — `calc_course_handicap(hi, par, slope, rating)` converts
   the index to strokes for a given tee; halved for 9-hole selections.

The recompute **cascade** (`store.recompute_handicaps_for_user`) walks a user's
rounds chronologically after any edit/exclude/delete, refilling missing
differentials (skipping incomplete/locked rounds) and rewriting each round's
running `computed_handicap`.

## Score evaluation / "where strokes are lost"

The app surfaces the *signals* but has no single strokes-gained engine:

- **Report card** (`/rounds/<date>/<index>/report`) — this round vs the player's
  last-20 baseline across ~14 metrics (vs par, vs rating, blow-up rate, FIR,
  GIR, putts, 1/2/3-putt, scramble, par-3/4/5 average, penalties).
- **Stats sections** (`/stats/*`) — `scoring`, `penalties`, `fairways`,
  `greens`, `putting`, `short-game`, `momentum`, `trends`, `bests`. Each is a
  category breakdown that reveals weaknesses (e.g. `calc_scoring_avg_by_par_type`,
  `calc_three_putt_percent`, `calc_scramble_by_par_type`).

See `SEQUENCES.md` → "Score evaluation" for the read path.

## Plugins

`source/plugin.py` exposes `fire_hook(name, **kwargs)` and a `_plugins` registry
loaded by `source/plugin_loader.py` from `plugins/`. Rounds fire
`on_round_saved`; plugins may also provide `post_save_redirect(round, user_id)`.
`plugin_states` gates them on/off from the admin screen.
