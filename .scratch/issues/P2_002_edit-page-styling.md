---
title: Style round/course edit pages with pinsheet form classes
priority: 2
status: backlog
created: 2026-06-01
---

Edit-mode form controls on round_detail and course_detail pages used bare `<input>` / `<select>` elements with inline styles. Applied `.step-input` for full-size controls and `.hole-input` for scorecard cells, matching the settings page and round entry wizard patterns. Removed redundant inline width/style attributes. Changed `.edit-location` wrapper to use existing `.location-row` class. Updated JS-generated HTML strings for add-tee rows/cards to match.
