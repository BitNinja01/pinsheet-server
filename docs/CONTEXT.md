# PinSheet Modern — Domain Glossary

## Glossary

- **Round** — a single golf outing. Has a date, course, tees, holes played, entry mode (detailed or score_only), holes data, and computed fields (total_gross, differential, computed_handicap).
- **Course** — a golf course. Has a name, location (city/state/country), tees (each with slope/rating/yardages), holes (each with par/index/yardages by tee), and total par.
- **Tees** — named sets of tee boxes on a course (e.g. "Blue", "White"). Each tee has slope, rating, yardage, and per-hole yardages.
- **Hole** — one of 18 holes on a course. Has par, stroke index, and yardage per tee. In round data, each hole has: gross score, putts, penalties, fairway code, GIR code.
- **Gross** — the raw number of strokes taken on a hole or in a round. Stored as string in JSON.
- **Differential** — the adjusted round score relative to course difficulty: `(113 / slope) * (adjusted_gross - rating)`. Rounded to 1 decimal. WHS formula.
- **Handicap Index** — World Handicap System index. Computed from the best N of last 20 differentials using the WHS count table, averaged and floor-rounded to 0.1.
- **Course Handicap** — handicap index adjusted for the specific course/tees: `round(hi * (slope/113) + (rating - par))`.
- **FIR (Fairway in Regulation)** — hitting the fairway off the tee on par 4s and 5s. Tracked per-hole with fairway codes.
- **GIR (Green in Regulation)** — reaching the green in `par - 2` strokes. Tracked per-hole with GIR codes.
- **Scramble** — making par or better when GIR is missed. Up-and-down percentage.
- **Putts per GIR** — average putts on holes where GIR was hit.
- **Par or Better %** — percentage of holes where gross ≤ par.
- **Clean Card** — a round with no double bogeys or worse.
- **Blow-up** — a hole score 4+ over par.
- **Consistency** — standard deviation of score vs par across rounds.
- **Season** — a configurable date range within the current year. Defaults to Jan 1–Dec 28. Used for season summary stats.

## Data Model Conventions

- **String-stored numerics**: All numeric values in JSON are stored as strings (gross, putts, differentials, yardages). Parse with `int()` / `float()` before arithmetic.
- **Hole-data shorthand**: Per-hole data uses single-letter codes.
  - Fairway codes: `H` (hit), `L` (left miss), `R` (right miss), `OBL` (OB left), `OBR` (OB right), `N` (no attempt, par 3s)
  - GIR codes: `H` (hit), `L` (left), `R` (right), `S` (short), `LO` (long), `OBL`, `OBR`, `OBS`, `OBLO`
- **Round storage by year**: Rounds stored in `data/rounds/YYYY.json`. Each file is a dict of `{date: {index: round_data}}`.
- **holes_selection**: `"all"` for 18-hole rounds, `"front"` or `"back"` for 9-hole rounds.
- **Entry modes**: `"detailed"` (per-hole data with fairway/GIR/putts) or `"score_only"` (total gross only).
- **excluded**: a boolean flag on rounds to exclude them from handicap calculations.
- **computed_handicap**: the HI as of that round, stored on each round after save for historical tracking.

## Key Calc Functions

- **handicap.py**: handicap index, differential, course handicap, effective diffs, best-N selection
- **scoring.py**: scoring average, par/better %, big number rate, clean card %, consistency, penalty stats, momentum/recovery, personal bests, season summary stats, STAT_CATALOG
- **approach.py**: FIR %, GIR %, scramble %, miss tendencies, OB stats, scoring-by-fairway/gir
- **putting.py**: putts per round, putts per GIR, 1/2/3-putt %, putts by par type

## Data Files

| File | Content |
|---|---|
| `data/courses.json` | All courses keyed by name |
| `data/rounds/YYYY.json` | Rounds keyed by date then index |
| `data/settings.json` | User preferences (theme, season range, welcome_shown, include_9hole) |
| `data/course_draft.json` / `data/round_draft.json` | In-progress wizard state |
| `data/handicap_benchmarks.json` | Benchmark lookup table for HI context |
