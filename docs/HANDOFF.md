# Handoff

**Last updated**: 2026-05-15 00:00 UTC

## Current state
Project scaffolded. Flask + waitress web app foundation in place:
- All calc functions ported 1:1 from original Python pinsheet (handicap, scoring, approach, putting)
- Store layer (JSON file I/O) ported from original `data.py`
- Minimal Flask server with dashboard route (stat panels rendering with real data)
- `base.html` shell template with navigation, `dashboard.html` with stat panel grid
- `app.css` with dark theme, custom properties, stat panel layout
- AGENTS.md, docs/ session memory files in place

No real `data/` directory yet — needs to be populated from the original pinsheet data for testing.

## Next actions (`[P0]`)
1. **Copy data from pinsheet** — `cp -r ../pinsheet/data data/` for development
2. **Dashboard backend** — complete the dashboard route with rounds table and trend data
3. **Dashboard frontend** — recent rounds table, trend graphs (Chart.js), "this time last year" HI

## Blockers
None.

## Repo location
`/mnt/Claude/repositories/pinsheet-modern` — local only, no remote configured yet.
