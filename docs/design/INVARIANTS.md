# Invariants

Non-obvious rules the PinSheet code depends on. Break one and data corrupts
**silently** (no crash). Every one of these has a regression test in
`tests/test_e2e_rounds_scores.py` — keep it that way.

## 1. `round_index` makes same-day rounds unique

- `rounds` has `UNIQUE(user_id, date, round_index)` and is written with
  `INSERT OR REPLACE`.
- Therefore the index **must** be unique per (user, date). New rounds get it
  from `store.next_round_index(date, user)` (lowest free slot).
- **Never** hardcode `0` on insert — that overwrites an existing same-day round.
- Regression: `test_two_rounds_same_date_both_persist`, `test_next_round_index_*`.

## 2. `differential == "0"` is an exclusion sentinel, not a value

- The handicap calc (`calc_effective_diffs`) skips rounds whose differential is
  `""` or the exact string `"0"`.
- A round that cannot be fairly rated stores `"0"` so it is saved but excluded:
  - **incomplete** detailed round (fewer scored holes than the selection needs), or
  - **no score** (`total_gross <= 0`).
- `str(0.0) == "0.0"` is **not** the sentinel — always write the literal `"0"`.
- Applies on both `POST` and `PUT`.
- Regression: `test_incomplete_detailed_round_gets_zero_differential`,
  `test_detailed_round_with_no_holes_gets_zero_differential`,
  `test_put_to_incomplete_zeroes_differential`.

## 3. The recompute cascade must not resurrect excluded rounds

- `store.recompute_handicaps_for_user` refills any `""`/`"0"` differential from
  `total_gross`. It runs after every edit/exclude/delete.
- It must skip incomplete rounds (`_is_incomplete_round`) and locked rounds
  (`differential_locked`), or it will recompute a poison differential and undo
  invariant #2.
- Regression: `test_incomplete_round_excluded_from_handicap`.

## 4. All user-supplied numbers are parsed defensively

- Gross/putts/penalties come from HTML forms and may be blank or non-numeric.
- Parse with a tolerant `_safe_int` (routes) — and `models.dict_to_hole` also
  guards, because it runs on **every DB read**, not just on input.
- Never call bare `int(user_value)` in a request path.
- Regression: `test_bad_score_only_gross_does_not_500`,
  `test_non_numeric_hole_gross_does_not_500_and_parses_zero`,
  `test_detail_page_renders_with_bad_stored_hole`, `test_put_bad_gross_does_not_500`.

## 5. Fewer than 3 eligible rounds ⇒ no handicap index

- `calc_handicap_index` returns `None` below the WHS minimum (`count_table_n`).
- Callers must treat `None`/empty `computed_handicap` as "not yet available",
  not as `0`.
- Regression: `test_handicap_index_populated_after_enough_rounds`.

## 6. 9-hole rounds need 9-hole ratings

- `get_slope_rating(tee, "front"|"back")` falls back to the full-18 rating if a
  tee has no `front_rating`/`back_rating`. Rating an 18-hole number against a
  9-hole gross (or vice-versa) yields a garbage differential.
- When adding a 9-hole round, ensure the tee carries 9-hole ratings, or the
  round should be treated as not-rateable.

## 7. Layering: SQL only in `store.py` / `database.py`

- Routes and `calc/*` never open a DB connection. `calc/*` stays pure so it is
  trivially testable and reusable.

---

### When you change round/score/handicap behaviour

1. Update the affected diagram in `SEQUENCES.md`.
2. Update the relevant invariant here.
3. Add/extend a test in `tests/test_e2e_rounds_scores.py` so CI enforces it.
