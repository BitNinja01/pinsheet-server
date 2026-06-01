# Handoff

**Last updated**: 2026-06-01 01:50 UTC

## Current state
P0_011 resolved — two fixes:
1. Added `@requires_own_data` to `api_welcome_done` (was only write route missing it)
2. Added `is_own_data` to template context via `inject_permissions()` context processor; hid "Add Round" / "Add Course" buttons when viewing another user's data (4 templates updated)

All 253 tests pass. Issue closed.

## Next actions
1. **[P1]** Port achievements plugin — `.scratch/issues/P1_007_port-achievements-plugin.md`
2. **[P2]** Stat delta arrows (▼/▲) instead of L20/1y text — `.scratch/issues/P2_001`
3. **[P2]** Add fairway S/LO codes — `.scratch/issues/P2_003`
4. **[P2]** Port printables plugin — `.scratch/issues/P2_010`

## Blockers
None.
