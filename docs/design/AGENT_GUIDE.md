# Agent Guide

Vendor-neutral guide for any coding agent or new contributor working on PinSheet.
Follows the `AGENTS.md` convention so it works with any tool (Claude, GPT,
Gemini, Cursor, local models). Reachable from the main
[`README.md`](../../README.md) → Documentation. If a specific assistant needs its
own entrypoint (e.g. `CLAUDE.md`, `.cursorrules`), make it a one-line pointer to
this file rather than duplicating content.

> Note: the repo intentionally gitignores top-level `AGENTS.md` / `CLAUDE.md`
> (they are treated as local, per-machine agent scratch). This committed guide is
> the durable, shared version.

## Orient in 60 seconds

1. Read [`FILE_MAP.md`](./FILE_MAP.md) — glob → responsibility. Jump straight to
   the right file.
2. Read [`INVARIANTS.md`](./INVARIANTS.md) — the silent-corruption rules. Do not
   violate these.
3. Skim the relevant diagram in [`SEQUENCES.md`](./SEQUENCES.md) before editing a
   flow.
4. Architecture and data model: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Mental model

- Thin routes (`source/routes/*`) → `store.py` for persistence → `calc/*` for
  pure math → `models.py` for typed data. SQL lives **only** in `store.py` /
  `database.py`.
- SQLite single file. No ORM, no migration framework — schema is raw SQL.
- Server-rendered Jinja; `/api/*` JSON backs the interactive entry screens.

## How to run & verify (in the app repo)

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                      # full suite
.venv/bin/python -m pytest tests/test_e2e_rounds_scores.py -q   # round/score e2e
```

- CI (`.github/workflows/ci.yml`) runs `pytest --cov` on every PR to `dev`/`main`.
  Green CI is the regression gate — add a test for any behaviour you change.
- For an ad-hoc, human-readable end-to-end drive there is a standalone script in
  the app repo at `.context/e2e_flow.py` (prints a PASS/FAIL report). The
  authoritative regression lives in `tests/test_e2e_rounds_scores.py`.

## Conventions that matter

- **Defensive parsing.** Never `int(user_value)` in a request path — use the
  `_safe_int` helpers (routes) / `dict_to_hole` (models). See invariant #4.
- **Differential `"0"` is a sentinel** (excluded from handicap), not a score.
  Write the literal `"0"`, never `"0.0"`. See invariant #2.
- **Same-day rounds** get their index from `store.next_round_index`. Never
  hardcode `0`. See invariant #1.
- **Pure calc.** Keep `calc/*` free of Flask/DB so it stays unit-testable.

## Repository & PR workflow

- App PRs target **`dev`** (never `main`). `main` is release-only.
  Use `gh pr create --base dev`.
- When you change round/score/handicap logic, update this docs repo in the same
  change set: the diagram (`SEQUENCES.md`), the invariant (`INVARIANTS.md`), and
  a test in `tests/test_e2e_rounds_scores.py`.

## Good first questions to ask the code

- "Where is a round persisted?" → `store.save_round` (only writer).
- "How is the handicap computed?" → `calc/handicap.py :: calc_handicap_index`.
- "Why did my second same-day round vanish?" → invariant #1.
- "Why is a round missing from the handicap?" → invariant #2 (differential `"0"`
  / excluded / 9-hole without `include_9hole`).
