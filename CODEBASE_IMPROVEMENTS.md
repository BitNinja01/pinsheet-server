# Codebase Improvements

Architectural deepening opportunities surfaced by `improve-codebase-architecture` skill.
Uses vocabulary from the skill's [LANGUAGE.md](LANGUAGE.md): **module**, **interface**, **seam**, **adapter**, **depth**, **leverage**, **locality**.

---

## 1. Close the dict↔RoundData gap — unify round representation at the store.py seam

- **Files**: `source/store.py`, `source/calc/models.py`, `source/routes/*.py`, `source/_helpers.py`
- **Problem**: The seam between `store.py` (raw dicts) and `calc/` (typed `RoundData`) is **porous**. `_helpers.py` has `_best_n_rounds` (dict-based) duplicating `calc.handicap.get_best_n_rounds` (RoundData-based). Route handlers call `dict_to_round()` in 6+ places before crossing into calc. The **deletion test** on either representation fails cleanly — delete dicts and store.py breaks; delete RoundData and all calc type safety vanishes. But the cost is pervasive duplicate iteration/filtering logic.
- **Solution**: Push the `dict_to_round()` conversion to the seam — modify `store.py`'s `get_all_rounds()` or the `_load_globals` before_request to return typed `RoundData` objects directly. Delete `_helpers._best_n_rounds` and route-level `dict_to_round()` calls.
- **Benefits**: One filtering/iteration implementation everywhere. 100+ lines of duplicate code deleted. Route handlers and calc functions work on the same type — no more "dict version vs. typed version" of every helper.

---

## 2. Split scoring.py — god module (988 lines, 40+ functions)

- **Files**: `source/calc/scoring.py`
- **Problem**: Scoring averages, penalty stats, momentum analysis, personal accomplishments, calendar/golfiest stats, milestone tracking, season filtering, per-hole analysis, and rating comparisons are jammed behind one interface. Understanding any one concept requires parsing 988 lines. The **deletion test** shows it's essential (complexity would reappear at callers), but it has no internal **locality** — `calc_trend` (line 8) has wrappers 330 lines away, and `iter_holes` (line 20) is only used 760 lines down.
- **Solution**: Split into ~4 focused modules: `scoring.py` (averages, distribution, consistency), `analysis.py` (penalties, momentum, components), `milestones.py` (personal bests, firsts, career milestones), and `seasons.py` (season filtering, golfiest stats). Each module gets a **deep interface** — the caller imports a few focused functions, not 40.
- **Benefits**: Massive **locality** improvement — bugs in milestone logic stay in milestones.py. ~20 functions become internal (not imported by routes or catalog.py), reducing the calc **interface** surface by half. Tests become more focused.

---

## 3. Route handler refactoring — extract calc logic from `stats()` and `dashboard()`

- **Files**: `source/routes/stats.py`, `source/routes/dashboard.py`, `source/_helpers.py`
- **Problem**: `stats()` is 250 lines with 5 inline helper functions (`_per_round_stat` at line 78, `_hole_pct` at line 90) that duplicate `iter_holes` from scoring.py. Stat values computed once in the stat strip (lines 105-137) are recomputed in detail sections below. `dashboard()` is 185 lines with an inline closure `_get_hi_for_range` (line 102) and ad-hoc career-low iteration (lines 167-179). These handlers are **shallow** — for every inline computation, the interface (the route handler signature) tells you nothing about what data flows through.
- **Solution**: Extract the inline helpers into the calc module they duplicate (e.g., move `_per_round_stat` logic into `calc/scoring.py` as a reusable function). Factor the stat-strip → detail-section recomputation into a single-pass data-preparation function.
- **Benefits**: Route handlers become thin connectors between calc modules and templates (testable through simple function calls, not Flask test client). No more duplicated hole-iteration patterns across routes and calc.

---

## 4. Explicit dependency declaration instead of implicit `g` globals

- **Files**: `source/main.py` `_load_globals` (line 86), all route files
- **Problem**: `_load_globals` populates `g.all_rounds`, `g.courses`, `g.settings` on every request — even for login/register/auth pages that need none of it. Route handlers silently depend on these globals without declaring what they need. The **interface** to every route handler lies about its dependencies: `def dashboard()` takes no parameters but needs 3 data structures.
- **Solution**: Move data loading out of `before_request` and into a lazy-loading helper (`get_courses()`, `get_all_rounds()`), or make route handlers accept explicit dependencies via dependency injection. Routes that need nothing (auth, settings form submits) pay zero loading cost.
- **Benefits**: Every route's **interface** tells you what it needs. No wasted loading on login/auth endpoints. Testable without the full before_request chain — call `get_dashboard_data(user)` directly.

---

## 5. Route registration at import time → lazy factory

- **Files**: `source/main.py` (lines 139-150), all `source/routes/*.py`
- **Problem**: `register_*_routes()` calls happen at module import time (line 139). This means any import of `routes.__init__` triggers all blueprint registration, including plugin loading. Tests must succeed through the entire import chain, making isolated unit testing of individual routes impossible.
- **Solution**: Move route registration into `create_app()`, receiving app as an explicit parameter. Route blueprint files export `register(app)` instead of calling it at module level.
- **Benefits**: Importing `routes.dashboard` doesn't fire side effects. Tests can import calc functions and route modules without launching a full Flask app. Flask's `create_app()` factory pattern becomes the single place where wiring happens.

---

## 6. Linear handicap trend instead of O(n²)

- **Files**: `source/calc/handicap.py` `calc_handicap_trend` (line 84)
- **Problem**: `calc_handicap_trend` recomputes the handicap index from scratch for every data point. For 200 rounds, ~200 calls to `calc_handicap_index` each O(n log n) for sorting diffs. The trend computation is O(n²) total.
- **Solution**: Replace with a rolling-window approach. Maintain a sorted list of differentials at each iteration step — removing the oldest and inserting the newest is O(log n) per step, yielding O(n log n) total.
- **Benefits**: Identical output, dramatically better performance for players with 100+ rounds. The **interface** stays the same — only the **implementation** changes.

---

## 7. [BUG] `report_card` uses wrong comparison (rounds.py:278)

- **Files**: `source/routes/rounds.py` line 278
- **Problem**: `this_round not in [r.get("date") for r in g.all_rounds[:20]]` compares a round dict to date strings. Always `True`, so the current round is always prepended regardless of whether it's in the window. This means `report_card` always shows an inflated "last 20 rounds" window with the current round counted twice.
- **Solution**: Use `r["date"]` access on the dict, or (once Candidate 1 is done) check `this_round_typed.date` against the date list.
- **Benefits**: Correct stat display on the report card page.
