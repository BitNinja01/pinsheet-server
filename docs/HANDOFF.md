# Handoff

**Last updated**: 2026-05-16 18:51 UTC

## Current state
Architecture deepened: calc package has clean public interface (`calc/__init__.py`), presentation config (`STAT_CATALOG`) moved to web layer, 10 duplicate trend functions consolidated, business-logic helpers extracted from main.py, Flask `before_request` hook eliminates store-call boilerplate across all routes. Chrome launches in `--kiosk` mode for immersive fullscreen with system cursors.

## Next actions
1. **Apply visual theme to other pages** — rounds entry wizard, stats page, courses, settings, season summary still need the new visual system
2. **Test kiosk mode thoroughly** — verify cursor behavior, window close/shutdown, multi-monitor behavior on Pop!_OS
3. **Acceptance smoke test** — full round/course entry flow, stats, season summary with real data

## Blockers
None.

## Repo location
Remote: `gitea@192.168.86.103:BitNinja01/pinsheet-modern.git` (master)
