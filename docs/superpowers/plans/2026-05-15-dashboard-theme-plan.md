# Dashboard Theme — Dark Engineering Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's green-on-dark theme with a Cool Teal / Near-Black engineering graph paper aesthetic — adaptive grid, full monospace, dashed borders, crosshair dots.

**Architecture:** New CSS custom properties on `:root` (replacing existing tokens). A separate `grid.js` module reads stat panel bounding rects and renders absolutely-positioned major grid lines and crosshair dots into a dedicated overlay element appended by JavaScript. The existing theme system (12 swatch overrides) is preserved — the new tokens become the default (no `theme-*` class) look.

**Tech Stack:** Vanilla CSS (no preprocessor), vanilla JS (no framework), Jinja2 templates, Flask backend (unchanged).

---

## File Structure

| File | Role |
|---|---|
| `source/web/static/app.css` | `:root` tokens, dashboard panel/table/header styles |
| `source/web/static/grid.js` | Adaptive grid overlay: reads panel rects, positions lines/dots |
| `source/web/templates/base.html` | Shell template: includes `grid.js`, adds `data-grid-region` |
| `source/web/templates/dashboard.html` | Dashboard page: adds `data-grid-panel` attributes |
| `source/main.py` | UNCHANGED — dashboard route handler not modified |

---

### Task 1: Replace `:root` CSS custom properties with Dark Engineering Grid tokens

**Files:**
- Modify: `source/web/static/app.css:7-15`

- [ ] **Step 1: Replace `:root` block**

Replace lines 7-15:
```css
:root {
    --bg: #111;
    --surface: #1a1a2e;
    --text: #e0e0e0;
    --text-muted: #888;
    --accent: #00E676;
    --border: #333;
    --font: 'Segoe UI', system-ui, -apple-system, sans-serif;
}
```

With:
```css
:root {
    --bg: #0d1114;
    --surface: #181e22;
    --text: #d0dce0;
    --text-muted: #90a0a4;
    --accent: #50c8d2;
    --border: #2a363a;
    --border-style: dashed;
    --border-width: 2px;
    --border-radius: 2px;
    --font: 'Courier New', Consolas, monospace;

    --grid-minor-dot: rgba(100, 200, 210, 0.05);
    --grid-minor-size: 8px;
    --grid-major: rgba(80, 200, 210, 0.12);
    --grid-crosshair: rgba(80, 200, 210, 0.22);
}
```

- [ ] **Step 2: Verify CSS compiles**

Run: `python -m py_compile source/web/static/app.css` (expected: silent success — but actually this is CSS, not Python, so skip py_compile for CSS). Just visually confirm no syntax errors by re-reading the file.

- [ ] **Step 3: Commit**

```bash
git add source/web/static/app.css
git commit -m "feat: replace :root tokens with Dark Engineering Grid palette"
```

---

### Task 2: Update body background with dot grid texture

**Files:**
- Modify: `source/web/static/app.css:17-22`

- [ ] **Step 1: Add dot grid background to body**

Replace lines 17-22:
```css
body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
}
```

With:
```css
body {
    font-family: var(--font);
    background-color: var(--bg);
    background-image: radial-gradient(circle, var(--grid-minor-dot) 0.5px, transparent 0.5px);
    background-size: var(--grid-minor-size) var(--grid-minor-size);
    background-position: 4px 4px;
    color: var(--text);
    min-height: 100vh;
}
```

- [ ] **Step 2: Commit**

```bash
git add source/web/static/app.css
git commit -m "feat: add 8px dot grid background texture to body"
```

---

### Task 3: Update header and nav styles

**Files:**
- Modify: `source/web/static/app.css:24-49`

- [ ] **Step 1: Replace header and nav CSS**

Replace lines 24-49:
```css
.app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 2rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
}

.app-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--accent);
}

.app-nav {
    display: flex;
    gap: 1.5rem;
}

.app-nav a {
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.875rem;
    transition: color 0.15s;
}

.app-nav a:hover {
    color: var(--text);
}
```

With:
```css
.app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 2rem;
    background: transparent;
    border-bottom: 1px var(--border-style) var(--border);
}

.app-title {
    font-size: 16px;
    font-weight: bold;
    color: var(--accent);
    letter-spacing: 3px;
}

.app-nav {
    display: flex;
    gap: 1.5rem;
}

.app-nav a {
    color: var(--text-muted);
    text-decoration: none;
    font-size: 11px;
    transition: color 0.15s;
}

.app-nav a:hover {
    color: var(--text);
}
```

- [ ] **Step 2: Commit**

```bash
git add source/web/static/app.css
git commit -m "feat: update header/nav to dashed border, monospace sizing, transparent bg"
```

---

### Task 4: Update stat panel and rounds table styles

**Files:**
- Modify: `source/web/static/app.css:55-146`

- [ ] **Step 1: Replace `.app-main`, `.stat-panels`, `.stat-panel`, `.stat-label`, `.stat-value`, `.stat-blank`, `.stat-secondary`**

Replace lines 55-101:
```css
.app-main {
    max-width: 960px;
    margin: 2rem auto;
    padding: 0 1.5rem;
}

.stat-panels {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 2rem;
}

.stat-panel {
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 1.25rem;
    text-align: center;
}

.stat-label {
    font-size: 0.75rem;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
}

.stat-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text);
}

.stat-blank {
    font-size: 0.875rem;
    color: var(--text-muted);
    font-weight: 400;
    font-style: italic;
}

.stat-secondary {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.5rem;
}
```

With:
```css
.app-main {
    max-width: 960px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    position: relative;
}

.stat-panels {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 0.5rem;
    margin-bottom: 2rem;
}

.stat-panel {
    background: var(--surface);
    border: var(--border-width) var(--border-style) var(--border);
    border-radius: var(--border-radius);
    padding: 0.75rem 0.5rem;
    text-align: center;
}

.stat-label {
    font-size: 9px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.4rem;
}

.stat-value {
    font-size: 22px;
    font-weight: bold;
    color: var(--text);
}

.stat-blank {
    font-size: 0.875rem;
    color: var(--text-muted);
    font-weight: 400;
    font-style: italic;
}

.stat-secondary {
    font-size: 9px;
    color: var(--text-muted);
    margin-top: 0.25rem;
}
```

- [ ] **Step 2: Replace `.recent-rounds`, `.data-table`, `.clickable-row`, `.in-handicap`**

Replace lines 103-146:
```css
.recent-rounds {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
}

.recent-rounds h2 {
    font-size: 1rem;
    color: var(--text);
    margin-bottom: 1rem;
}

.placeholder {
    color: var(--text-muted);
    font-style: italic;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
}
.data-table th {
    text-align: left;
    color: var(--text-muted);
    font-weight: 500;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
}
.data-table td {
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.clickable-row {
    cursor: pointer;
    transition: background 0.1s;
}
.clickable-row:hover {
    background: rgba(255,255,255,0.03);
}
.in-handicap {
    background: rgba(0,230,118,0.06);
}
```

With:
```css
.recent-rounds {
    background: var(--surface);
    border: var(--border-width) var(--border-style) var(--border);
    border-radius: var(--border-radius);
    padding: 1.25rem;
}

.recent-rounds h2 {
    font-size: 10px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px var(--border-style) var(--border);
}

.placeholder {
    color: var(--text-muted);
    font-style: italic;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
}
.data-table th {
    text-align: left;
    color: var(--text-muted);
    font-weight: normal;
    font-size: 9px;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px var(--border-style) var(--border);
}
.data-table td {
    padding: 0.4rem 0.75rem;
    border-bottom: 1px var(--border-style) rgba(42, 54, 58, 0.5);
}
.clickable-row {
    cursor: pointer;
    transition: background 0.1s;
}
.clickable-row:hover {
    background: rgba(80, 200, 210, 0.04);
}
.in-handicap {
    background: rgba(80, 200, 210, 0.06);
}

.data-table td:first-child {
    color: var(--accent);
}
```

- [ ] **Step 3: Update theme overrides to use new accent values for swatches that overlap**

The existing theme overrides (lines 565-576) only change `--accent`. They remain functional — each theme just swaps the accent color. No change needed for green (`theme-green` uses the new default `#50c8d2`). However the `theme-green` swatch (line 579: `background: #00E676`) should be updated to match the new default accent.

Replace line 579:
```css
.theme-swatch-green { background: #00E676; }
```

With:
```css
.theme-swatch-green { background: #50c8d2; }
```

- [ ] **Step 4: Commit**

```bash
git add source/web/static/app.css
git commit -m "feat: restyle stat panels (6-col), rounds table, and active row for new theme"
```

---

### Task 5: Create adaptive grid JavaScript module

**Files:**
- Create: `source/web/static/grid.js`

- [ ] **Step 1: Write `grid.js`**

```javascript
(function () {
    var overlayEl = null;
    var gridRegion = document.querySelector("[data-grid-region]");
    if (!gridRegion) return;

    function createOverlay() {
        if (overlayEl) overlayEl.remove();
        overlayEl = document.createElement("div");
        overlayEl.id = "grid-overlay";
        overlayEl.style.cssText =
            "position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:0;";
        gridRegion.style.position = "relative";
        gridRegion.appendChild(overlayEl);
    }

    function drawGrid() {
        if (!overlayEl) return;
        var panels = document.querySelectorAll("[data-grid-panel]");
        if (panels.length === 0) {
            overlayEl.innerHTML = "";
            return;
        }

        var regionRect = gridRegion.getBoundingClientRect();
        var offsetX = regionRect.left;
        var offsetY = regionRect.top;

        var horizontalLines = [];
        var verticalLines = [];
        var crosshairDots = [];

        // Collect unique x and y positions from panel edges
        var uniqueX = {};
        var uniqueY = {};

        panels.forEach(function (panel) {
            var r = panel.getBoundingClientRect();
            var left = r.left - offsetX;
            var right = r.right - offsetX;
            var top = r.top - offsetY;
            var bottom = r.bottom - offsetY;

            // Track unique positions (rounded to 1 decimal)
            left = Math.round(left * 10) / 10;
            right = Math.round(right * 10) / 10;
            top = Math.round(top * 10) / 10;
            bottom = Math.round(bottom * 10) / 10;

            uniqueX[left] = true;
            uniqueX[right] = true;
            uniqueY[top] = true;
            uniqueY[bottom] = true;
        });

        var xPositions = Object.keys(uniqueX).map(Number).sort(function (a, b) { return a - b; });
        var yPositions = Object.keys(uniqueY).map(Number).sort(function (a, b) { return a - b; });

        // Build horizontal line elements
        yPositions.forEach(function (y) {
            horizontalLines.push(
                '<div style="position:absolute;left:0;right:0;top:' + y +
                'px;height:1px;background:var(--grid-major);"></div>'
            );
        });

        // Build vertical line elements
        xPositions.forEach(function (x) {
            verticalLines.push(
                '<div style="position:absolute;top:0;bottom:0;left:' + x +
                'px;width:1px;background:var(--grid-major);"></div>'
            );
        });

        // Build crosshair dots at intersections
        yPositions.forEach(function (y) {
            xPositions.forEach(function (x) {
                crosshairDots.push(
                    '<div style="position:absolute;top:' + y +
                    'px;left:' + x +
                    'px;width:3px;height:3px;background:var(--grid-crosshair);border-radius:50%;margin:-1.5px;"></div>'
                );
            });
        });

        overlayEl.innerHTML = horizontalLines.join("") + verticalLines.join("") + crosshairDots.join("");
    }

    createOverlay();
    drawGrid();

    var resizeTimer;
    window.addEventListener("resize", function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(drawGrid, 100);
    });
})();
```

- [ ] **Step 2: Verify JS syntax**

Run: `node --check source/web/static/grid.js`
Expected: silent success (no output)

- [ ] **Step 3: Commit**

```bash
git add source/web/static/grid.js
git commit -m "feat: add adaptive grid overlay JS (reads panel rects, draws major lines + crosshair dots)"
```

---

### Task 6: Update templates for grid support

**Files:**
- Modify: `source/web/templates/base.html`
- Modify: `source/web/templates/dashboard.html`

- [ ] **Step 1: Add `data-grid-region` to `.app-main` and include `grid.js` in `base.html`**

Replace lines 21-25:
```html
    <main class="app-main">
        {% block content %}{% endblock %}
    </main>
    <script src="/static/app.js"></script>
```

With:
```html
    <main class="app-main" data-grid-region>
        {% block content %}{% endblock %}
    </main>
    <script src="/static/app.js"></script>
    <script src="/static/grid.js"></script>
```

- [ ] **Step 2: Add `data-grid-panel` attributes to stat panels in `dashboard.html`**

Replace line 5:
```html
    <div class="stat-panel" style="--accent: {{ p.color }}">
```

With:
```html
    <div class="stat-panel" data-grid-panel style="--accent: {{ p.color }}">
```

- [ ] **Step 3: Also update the rounds section heading tag from `h2` to `div` with section-heading styling (the new CSS expects this pattern)**

The CSS change in Task 4 expects `.recent-rounds h2` to look like an accent section heading. The template already uses `<h2>Recent Rounds</h2>` so this works. No change needed — verify alignment.

- [ ] **Step 4: Verify template renders**

Run: `python -c "from source.main import app; from flask import template_rendered; print('Templates loaded OK')"`
Expected: no import errors.

- [ ] **Step 5: Commit**

```bash
git add source/web/templates/base.html source/web/templates/dashboard.html
git commit -m "feat: add data-grid-region and data-grid-panel attributes for adaptive grid"
```

---

### Task 7: Smoke test end-to-end

- [ ] **Step 1: Start the app**

Run: `python source/main.py`
Expected: Flask starts on port 5000, browser opens.

- [ ] **Step 2: Verify dashboard visual checklist**

Open `http://127.0.0.1:5000/` and confirm:
- [x] Dot grid background texture visible across full page
- [x] Adaptive major lines trace stat panel column and row boundaries
- [x] Crosshair dots at major line intersections
- [x] All text in monospace (Courier New / Consolas)
- [x] Dashed borders on stat panels and rounds table
- [x] Header nav uses dashed bottom border, transparent background
- [x] App title "PIN SHEET" in accent color with increased letter-spacing
- [x] Rounds table rows separated by dashed lines
- [x] Active nav "Dashboard" distinguishable from other links
- [x] In-handicap rounds highlight works (teal tint instead of green)
- [x] Resize browser: grid lines reposition to match new panel bounds

- [ ] **Step 3: Verify other pages are NOT affected beyond token changes**

Navigate to `/courses`, `/stats`, `/settings` and confirm they render without errors. The tokens changed globally but the dashboard-specific restyling (Task 4) only touches `.stat-panels`, `.stat-panel`, `.recent-rounds`, `.data-table`, `.clickable-row`, `.in-handicap` — other pages share `.data-table` so they'll pick up dashed borders and font change, which is expected and acceptable.

- [ ] **Step 4: Stop the app** (Ctrl+C)

- [ ] **Step 5: Verify no Python syntax errors in modified files**

Run: `python -m py_compile source/main.py && python -m py_compile source/store.py`
Expected: silent success (even though we didn't change these files, confirmation that the project still compiles).

---

### Task 8: Final commit

- [ ] **Step 1: Verify working tree**

Run: `git status`
Expected: clean working tree (all changes committed).

- [ ] **Step 2: If any untracked docs files exist, commit them**

```bash
git add docs/superpowers/specs/2026-05-15-dashboard-theme-design.md docs/superpowers/plans/2026-05-15-dashboard-theme-plan.md
git commit -m "docs: add dashboard theme design spec and implementation plan"
```
