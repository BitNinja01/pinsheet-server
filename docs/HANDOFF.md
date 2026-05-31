# Handoff

**Last updated**: 2026-05-31 01:00 UTC

## Current state
Net column rounds tables show values off by −1 for some 18-hole rounds (e.g. Maplewood gross=84 shows net −6 instead of −7). `calc_course_handicap` uses `round()` and computes correctly in tests, but the UI shows values consistent with `int()` truncation. Root cause unconfirmed — need to add diagnostic logging.

## Next actions
1. **[BLOCKED]** Debug net column rounding error — add logging to `calc_course_handicap` to trace the actual intermediate values at runtime
2. **[P1]** Port achievements plugin — follow `docs/PLUGINS.md` §16.1
3. **[BK-15]** Stat delta arrows (▼/▲) instead of L20/1y text

## Blockers
Net column rounding error — CH computed as 1 less than expected for Maplewood (CH=18 vs 19) and Druids Glen (CH=22 vs 23). `calc_course_handicap` uses `round()` but behavior matches `int()` truncation. `__pycache__` cleared, server restarted — still persists. Needs runtime logging to diagnose.
