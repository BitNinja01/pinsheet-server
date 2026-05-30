# Codebase Improvements

Architectural deepening opportunities surfaced by `improve-codebase-architecture` skill.
Uses vocabulary from the skill's [LANGUAGE.md](LANGUAGE.md): **module**, **interface**, **seam**, **adapter**, **depth**, **leverage**, **locality**.

---

## 1. Split `main.py` (1600 lines, ~80 imported symbols) into route Blueprints

### Files

| File | Role |
|------|------|
| `source/main.py` | God module — routes, auth, dashboard rendering, stats page, plugin wiring, server startup |
| `source/routes/` (new package) | Target for extraction |

### Problem

`main.py` has no **depth**. It is the single integration point for the entire system:

- Imports ~80 symbols from `store.py`, every function in `calc/`, `database.py`, `plugin.py`, `plugin_loader.py`, `catalog.py`
- Route handlers contain business logic that belongs behind a **seam** in the calc layer: FIR/GIR iteration (lines 416–451, 659–698), SVG sparkline math (380–410, 626–657), delta computation (1099–1128, 1183–1188)
- Understanding any one route requires parsing a 1600-line file. Changes to calc function signatures ripple here.
- The Flask app object is configured and returned in the same module that defines routes — no factory pattern, no registration phase.

### Solution

Split into a `source/routes/` package with one module per domain area, each a Flask Blueprint:

| Module | Routes |
|--------|--------|
| `routes/dashboard.py` | `/`, chart data, sparklines |
| `routes/rounds.py` | `/rounds/*`, `/api/rounds` |
| `routes/courses.py` | `/courses/*`, `/api/courses` |
| `routes/stats.py` | `/stats`, `/season` |
| `routes/settings.py` | `/settings/*` |
| `routes/auth.py` | `/login`, `/register`, `/logout`, `/admin/*` |

`main.py` becomes a minimal app factory: create the Flask app, register Blueprints, start the server.

### Benefits

- **Locality**: changing round-related code doesn't require touching the same file as auth or settings code
- **Leverage**: each Blueprint module presents a small interface (its URL rules) that hides the route implementation
- **Testability**: individual Blueprints can be tested with Flask's `app.test_client()` without loading unused routes
- **Deletion test**: removing `<route>` deletes exactly one file; complexity doesn't scatter

---

## 2. Extract duplicated hole-stats iteration into a single deep module

### Files

| Location | What |
|----------|------|
| `main.py:416–451` | Per-round FIR/GIR/scramble/putts computation in `dashboard()` |
| `main.py:659–698` | Identical computation in `rounds_list()` |
| `main.py:1138–1169` | Third variant via `_per_round_stat` and `_hole_pct` closures in `stats()` |
| `main.py:380–410` | SVG sparkline path in `dashboard()` |
| `main.py:626–657` | Duplicated SVG sparkline path in `rounds_list()` |
| `main.py:1099–1128, 1183–1188` | Duplicated delta logic (`_cell` vs `_sd`) inside `stats()` |

### Problem

The same hole-by-hole iteration pattern appears verbatim in 3 places:

1. Iterate all rounds for the user
2. For each round, look up the course and tee set
3. Iterate holes, count FIR hits vs attempts (excluding par 3s), GIR hits vs total, scramble up/downs, total putts
4. Accumulate into per-round or aggregate stats

A bug in one variant (e.g., wrong par-3 exclusion for scramble) must be fixed in 3 places. SVG sparkline path math (normalize scores → map to SVG coordinates → emit `M...L...`) is duplicated with only canvas dimensions differing. Delta computation (`_cell` and `_sd`) duplicate each other in the same function body.

### Solution

Extract three functions into `calc/` or a new `round_utils.py`:

```python
# Returns per-round stat dicts: FIR%, GIR%, scramble%, putts, etc.
def compute_hole_stats(rounds: list, courses: dict) -> list[dict]:
    ...

# Returns SVG <path> d-attribute string
def sparkline_svg(scores: list[float], width: int, height: int) -> str:
    ...

# Returns stat delta with higher/lower-is-better coloring
def stat_delta(current: float, previous: float, higher_better: bool) -> dict:
    ...
```

All callers in `main.py` route handlers import and call these instead of inlining.

### Benefits

- **Locality**: one place to fix iteration bugs, one place to change hole-stat logic
- **Leverage**: the `compute_hole_stats` interface hides course lookup, par determination, hole iteration, and aggregate math behind a single call
- **Testability**: the extracted functions are pure computation — test them in isolation. Existing route-level tests exercise them indirectly
- **Deletion test**: removing the inline code from each route handler removes duplication, not complexity

---

## 3. Parameterize 4 near-identical putt threshold functions in `calc/putting.py`

### Files

| Function | Lines | Behaviour |
|----------|-------|-----------|
| `calc_one_putt_percent` | ~7 | Count holes where putts == 1 |
| `calc_two_putt_percent` | ~7 | Count holes where putts == 2 |
| `calc_three_putt_percent` | ~7 | Count holes where putts == 3 |
| `calc_four_plus_putt_percent` | ~7 | Count holes where putts >= 4 |

### Problem

These four **modules** are **shallow**: the **interface** is nearly as complex as the **implementation**. Each is a 7-line function that iterates all rounds, iterates holes, filters by putt count, and divides by total. They differ only in the comparison operator and threshold value. There are also per-hole-type variants (`calc_one_putt_percent_by_par_type`, etc.) that add another dimension of near-duplicate code.

The **depth** is low: 4+ entry points, each providing ~2 lines of unique behaviour. A new threshold (e.g., "3-putt or worse %") requires a new copy-paste function.

### Solution

Replace the 4 functions with a single parameterized function:

```python
def putt_threshold_percent(rounds: list, op: Callable[[int], bool]) -> float:
    hits = total = 0
    for r in rounds:
        for h in r.get("holes", {}).values():
            if h.get("putts", "0").isdigit():
                total += 1
                if op(int(h["putts"])):
                    hits += 1
    return round((hits / total * 100) if total else 0, 1)
```

Public wrappers can remain for backwards compatibility:

```python
def calc_one_putt_percent(rounds):
    return putt_threshold_percent(rounds, lambda p: p == 1)
```

Or break them entirely if no external callers depend on the names.

### Benefits

- **Leverage**: one small interface hides the iteration boilerplate for any putt threshold
- **Locality**: a new threshold (e.g., "5-putt %") doesn't need a new function — just a new lambda at the call site
- **Testability**: one test function exercises the parameterized version; the wrappers are trivially tested or eliminated
- **Depth**: the behaviour/code ratio increases — more computation behind less interface

---

## 4. Define typed data models at the calc module's interface seam

### Files

| File | Role |
|------|------|
| `source/calc/__init__.py` | Public re-export facade |
| `source/calc/scoring.py` | Consumes round/course dicts |
| `source/calc/handicap.py` | Consumes round dicts |
| `source/calc/approach.py` | Consumes round dicts |
| `source/calc/putting.py` | Consumes round dicts |
| `source/calc/context.py` | Consumes round dicts |
| `source/store.py` | Emits raw SQLite rows / JSON dicts |
| `source/main.py` | Converts request JSON → dicts, passes to calc |

### Problem

The calc module's **interface** is implicit. Every function receives raw dicts with undocumented invariants:

- Numeric fields are stored as strings (`"gross": "4"`) — every function must `int(h["gross"])` or risk `TypeError`
- Missing keys are handled inconsistently: some functions use `.get("key", default)`, others risk `KeyError`
- The `holes` field is a JSON-serialized string in SQLite but a dict in memory — the raw dict vs in-memory dict shapes differ, and this is never enforced at a **seam**
- Course lookup requires knowing the dict key convention (`courses[name]`) — there is no `Course` type to query

This means:

- Callers and tests must reproduce the dict shape conventions
- A malformed round silently produces wrong stats rather than a type error
- Parsing logic is scattered across 50+ functions instead of concentrated at one conversion point

### Solution

Define dataclasses at the calc module's public **seam** (in `source/calc/models.py`):

```python
@dataclass
class HoleData:
    gross: int
    putts: int
    penalties: int = 0
    fairway: str = ""
    gir: str = ""

@dataclass
class RoundData:
    date: str
    course: str
    tees: str
    holes_played: str  # "all" | "front" | "back"
    entry_mode: str    # "detailed" | "score_only"
    holes: dict[int, HoleData]
    total_gross: int
    total_par: int

@dataclass
class CourseData:
    name: str
    tees: dict[str, TeeData]
    holes: list[HoleDef]

@dataclass
class TeeData:
    name: str
    slope: float
    rating: float
    yardages: list[int]
```

Add converter functions (`dict_to_round`, `dict_to_course`) that validate and transform raw dicts → dataclasses. Call these in the route handlers before crossing into calc. Calc functions accept dataclasses.

### Benefits

- **Leverage**: the dataclass **interface** documents all fields, types, and defaults in one place — callers don't need to read every calc function
- **Locality**: parsing/validation logic concentrates at the converter, not across 50 functions. A new invariant (e.g., "putts cannot exceed 20") is added in one place
- **Testability**: tests construct `RoundData(...)` directly — no more `{"gross": "4", "putts": "2", ...}` boilerplate. Invalid data can't accidentally pass a type check
- **Seam discipline**: two **adapters** already exist (JSON dict input and SQLite row input) — the converter makes the seam real instead of hypothetical

---

## 5. Consolidate `calc/context.py` into `calc/scoring.py`

### Files

| File | Lines | Functions |
|------|-------|-----------|
| `calc/context.py` | 104 | 6: `calc_historical_window`, `calc_round_vs_par`, `calc_round_vs_rating`, `calc_penalties_per_round`, `calc_avg_vs_par_on_penalty_holes`, `calc_last_year_handicap` |
| `calc/scoring.py` | 875 | 30+ scoring functions |
| `calc/__init__.py` | 93 | Re-exports everything from both |

### Problem

`context.py` is a **shallow** module whose 6 functions are structurally identical to those in `scoring.py` — they iterate rounds, filter by condition, compute averages, return numbers. The **seam** between them doesn't earn its keep:

- No caller depends on `context` being a separate module — both are imported via `calc/__init__.py` and used side by side
- There is no second **adapter** that would vary independently under `context` vs `scoring`
- `calc_historical_window` is a trivial 2-line filter; `calc_penalties_per_round` is a sum-and-average; both patterns already exist in `scoring.py`
- The split adds a cognitive step: "is this a 'scoring' function or a 'context' function?" without a clear rule

### Solution

Move the 6 functions into `scoring.py` and remove `context.py`. Update `calc/__init__.py` and `calc/__init__.py`'s re-export to point to `scoring` instead of `context`.

### Benefits

- **Locality**: all scoring-adjacent logic lives in one module. A new function that could logically live in either doesn't require a naming debate
- **Leverage**: the `scoring` module's interface is marginally bigger (6 more functions) but one fewer module to learn
- **Deletion test**: removing `context.py` concentrates its complexity in `scoring.py` — it doesn't scatter across callers. The project has one fewer file, one fewer import in the facade, and zero reduction in behaviour
