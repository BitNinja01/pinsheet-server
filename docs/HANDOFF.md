# Handoff

**Last updated**: 2026-05-16 24:00 UTC

## Current state
Dashboard visually matches the canonical design example (`PinSheet Dashboard_example.html`):
- 22 of 28 audit backlog items completed; 1 deferred (delta arrows), 6 pre-existing items not in scope
- JetBrains Mono replaces IBM Plex Mono + Barlow Condensed — single monospace family, self-hosted TTF (NerdFont NL), weights 200/400/500/600/700
- Hero numeral: 200px JetBrains Mono weight 400, 50% decimal dot on baseline, ink-integer / dimmed-dot / mint-fraction pattern
- Hero grid `1fr 1.6fr` with SVG trajectory chart on right, JS tooltips on hover, chip-driven range switching (3M/12M/2Y/All)
- Topbar with season-aware eyebrow, h1 headline, Search/+ Log round buttons
- 10-column rounds table with FIR/GIR/Putt/Scr/SG·T/By-hole sparklines
- Player info block in sidebar, filter chips above table, filter chips on chart
- Page-level padding 28px 48px 32px on `.ps-layout`, sidebar pr-24, main gap 16px
- Design system docs (README.md + tokens.css) updated to reflect current font choices

## Next actions
1. **Test kiosk mode thoroughly** — verify cursor behavior, window close/shutdown, multi-monitor on Pop!_OS
2. **Acceptance smoke test** — full round/course entry flow with real data
3. **Apply design system to remaining pages** — wizards, round detail, courses, stats, settings, season summary

## Blockers
None.

## Repo location
Remote: `gitea@192.168.86.103:BitNinja01/pinsheet-modern.git` (master)
