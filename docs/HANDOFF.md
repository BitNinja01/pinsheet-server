# Handoff

**Last updated**: 2026-05-31 21:30 UTC

## Current state
Net column rounding bug resolved. Root cause: the source data (pinsheet core project) had stale/unverified handicap indexes. The import process recalculates all HIs from scratch using WHS-compliant flooring, producing correct values. `calc_course_handicap` with `round()` was always correct — the discrepancy was between old source HIs and the recomputed HIs. No code changes needed.

Diagnostic logging added then removed after confirmation. Regression tests retained (`test_calc_course_handicap_maplewood_white`, `test_calc_course_handicap_druids_white`, `test_calc_course_handicap_round_over_int`, `test_calc_course_handicap_near_boundary`).

## Next actions
1. **[P1]** Port achievements plugin — follow `docs/PLUGINS.md` §16.1
2. **[BK-15]** Stat delta arrows (▼/▲) instead of L20/1y text

## Blockers
None.
