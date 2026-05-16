# Dashboard Theme — Dark Engineering Grid

**Date**: 2026-05-15
**Status**: draft
**Scope**: Dashboard page visual restyle only

## Summary

Replace the existing green-on-dark theme with a Cool Teal / Near-Black "engineering graph paper" aesthetic. Full monospace typography, adaptive grid that snaps to panel boundaries, dashed borders, and crosshair intersection dots.

## In scope

- Dashboard page: stat panels, rounds table, header/nav, empty states
- New CSS custom properties replacing current `:root` tokens
- Grid system: adaptive major lines + minor dot texture + crosshair dots
- Typography stack: full monospace
- Border treatment: 2px dashed
- Affects: `base.html` (header/nav), `dashboard.html`, `app.css`

## Out of scope

- Round entry wizard, round detail, courses, stats, settings, season summary pages (will adopt same tokens later)
- Scorecard grid styling
- Chart.js / trend visuals
- Welcome screen gate
- Theme swatches system (may add this theme to the swatch list in a follow-up)

## Design tokens

```css
:root {
  --bg:              #0d1114;   /* page background */
  --surface:         #181e22;   /* card / panel background */
  --text:            #d0dce0;   /* primary text */
  --text-muted:      #90a0a4;   /* secondary / dim text */
  --accent:          #50c8d2;   /* interactive, highlights, labels */
  --border:          #2a363a;   /* borders, separators */
  --border-width:    2px;
  --border-style:    dashed;
  --border-radius:   2px;
  --font:            'Courier New', Consolas, monospace;
  
  /* Grid */
  --grid-major:      rgba(80, 200, 210, 0.12);   /* adaptive major lines */
  --grid-minor-dot:  rgba(100, 200, 210, 0.05);  /* 8px dot texture */
  --grid-crosshair:  rgba(80, 200, 210, 0.22);   /* intersection dots */
  --grid-minor-size: 8px;
}
```

## Grid system

### Background texture (CSS background on `<body>`)

```
Radial gradient dots at 8px spacing, color: --grid-minor-dot
Covers full page, sits behind all content.
```

Implemented as:
```css
body {
  background-color: var(--bg);
  background-image: radial-gradient(circle, var(--grid-minor-dot) 0.5px, transparent 0.5px);
  background-size: var(--grid-minor-size) var(--grid-minor-size);
  background-position: 4px 4px;
}
```

### Adaptive major lines (CSS on `.app-main` or stat panel region)

Major grid lines rendered as pseudo-element borders or positioned divs that align to stat panel boundaries:

```
Horizontal lines: at top of stat panels, bottom of stat panels, top of rounds table
Vertical lines: at column boundaries of the 6-panel grid
Intersection dots: at every major-line crossing
```

Implementation strategy: since CSS `background-image` with `linear-gradient` cannot adapt to CSS grid track sizes at runtime, the adaptive major lines will be rendered via JavaScript that reads the bounding rects of stat panel elements and positions absolutely-positioned divs. The JS runs on load and on resize.

### Crosshair dots

At each intersection of major grid lines, render a small circle (3px diameter, color `--grid-crosshair`). Positioned via the same JS as the major lines.

## Typography

```css
body {
  font-family: 'Courier New', Consolas, monospace;
  font-size: 14px;
  line-height: 1.5;
}
```

Scale:

| Role | Size | Weight | Color |
|---|---|---|---|
| App title (header) | 16px | bold | accent |
| Nav links | 11px | normal | text-muted → text on hover |
| Stat label | 9px | normal | accent, uppercase, letter-spacing 1px |
| Stat value | 22px | bold | text |
| Stat delta | 9px | normal | text-muted |
| Section heading | 10px | normal | accent, uppercase, letter-spacing 1px |
| Table header | 9px | normal | text-muted |
| Table body | 11px | normal | text |
| Footer / meta | 9px | normal | text-muted (25% opacity) |

## Header

```
[PIN SHEET]                    [Dashboard · Rounds · Courses · Stats · Settings]
```

- Title: bold, accent color, letter-spacing 3px
- Nav: muted text, accent for active page, hover brightens
- Bottom border: 1px dashed --border, full width
- Padding: 1rem 2rem
- Background: transparent (inherits body bg + dot grid)

## Dashboard stat panels

6-column CSS grid (`grid-template-columns: repeat(6, 1fr)`), gap 0.5rem.

Each panel:
- Background: `--surface`
- Border: 2px dashed `--border`, radius 2px
- Padding: 0.75rem 0.5rem
- Text-align: center
- Label: 9px uppercase, accent, letter-spacing 1px
- Value: 22px bold, text color
- Delta: 9px muted below value

## Rounds table

- Container: same surface + dashed border treatment as panels
- Section heading bar: accent text, dashed bottom border
- Rows: dashed top border between rows (1px)
- Active/highlight date: accent color
- Score value: bold, text color
- Other cells: muted
- Handicap highlighting: rounds below HI in one opacity, above in another (preserve existing logic)

## Color semantics (beyond dashboard)

These tokens will be used across all screens when theme is applied:

| Token | Purpose |
|---|---|
| `--accent` | Active nav, stat labels, section headings, highlights, links |
| `--text` | Primary body text, stat values, data |
| `--text-muted` | Secondary info, delta values, older data |
| `--border` | All borders and separators |
| `--surface` | Card/panel backgrounds |

Eagle/birdie/bogey scorecard cell colors, trend arrows, and delete/danger remain as separate tokens not affected by this change.

## Implementation notes

1. Replace current `:root` custom properties in `app.css` with the new token set
2. Update `.app-header`, `.app-nav`, `.stat-panel`, `.stat-label` to use `--border-style: dashed` and adjusted spacing
3. Add JS module for adaptive major grid lines + crosshair dots (new file: `web/static/grid.js`)
4. Update `base.html` to include `grid.js` script
5. The existing theme swatch system (12 theme classes on `<body>`) is untouched — this replaces the `:root` default tokens that the theme system overrides. The new tokens become the default (no-`theme-*` class) look
6. Dashboard template changes: change stat panel grid from `repeat(3, 1fr)` (2 rows) to `repeat(6, 1fr)` (single row), add `data-grid-panel` class hooks on each stat panel for JS adaptive grid targeting
7. No changes to `main.py`, `store.py`, or any calc files

## Verification

- Dashboard renders with dot grid background covering full page
- Adaptive major lines visible along stat panel edges
- Crosshair dots at horizontal/vertical line intersections
- All text uses monospace
- Dashed borders on all panels and separators
- Header nav shows active page in accent color
- Rounds table rows separated by dashed lines
- Theme applies only to dashboard; other pages retain current styling (temporary)
- Resize browser window: adaptive lines reposition to match new panel boundaries
- `python -m py_compile` on any changed `.py` files passes
