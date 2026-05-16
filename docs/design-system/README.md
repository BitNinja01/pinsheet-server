# PinSheet — Design Language

This document is the source of truth for the PinSheet visual system.
Any new screen, component, or marketing surface should follow it.

> **For LLMs**: read this in full before adding to the design. The tokens
> in [`tokens.css`](./tokens.css) are the contract; the principles below
> explain *why* and *when* to apply them.

---

## 1. Aesthetic essence

PinSheet is an **editorial / tour-pro** dashboard for serious golfers.
The feel is closer to a printed yardage book or a Hodinkee article than
to a fitness app. Three principles drive every decision:

1. **The number is the hero.** Data points are typeset, not decorated.
   The handicap index, scoring average, and per-round score are the
   loudest things on every screen. Everything else recedes.
2. **Hairlines, never rounded corners.** All structure is built from
   1px rules and hard rectangles. Cards have flat backgrounds and a
   1px border. No shadows, no gradients, no glassmorphism.
3. **Monospace by default, condensed sans for display.** Body, labels,
   table cells, axis ticks — all IBM Plex Mono. Display headlines
   (handicap, large stats) — Barlow Condensed at weight 200.

If a design choice doesn't reinforce one of these, drop it.

---

## 2. Color

Two modes, identical structure. Apply `.ps-light` or `.ps-dark` to the
root of the screen.

| Token            | Light       | Dark        | Use                                     |
| ---------------- | ----------- | ----------- | --------------------------------------- |
| `--ps-paper`     | `#faf6ec`   | `#131312`   | Body background                         |
| `--ps-paper-2`   | `#f1ebda`   | `#1c1c1a`   | Card / chart-card background            |
| `--ps-ink`       | `#16110a`   | `#ecebe6`   | Primary text, emphatic rules            |
| `--ps-ink-2`     | `#4a4239`   | `#a8a59d`   | Secondary text                          |
| `--ps-ink-3`     | `#8a8174`   | `#6c685f`   | Tertiary text, eyebrows, axis labels    |
| `--ps-rule-c`    | `#d6cdb8`   | `#2a2925`   | Hairline rule color                     |
| `--ps-accent`    | `#3d8a72`   | `#5db49a`   | The single chromatic color — mint       |
| `--ps-accent-dim`| 12% mint    | 16% mint    | Area fill under charts, soft mint wash  |
| `--ps-warn`      | `#b04848`   | `#d96a6a`   | Negative delta or error, used sparingly |

**Rules**

- **Mint is the only color.** Use it for: positive movement (▼ handicap,
  ▲ FIR/GIR/scramble), the active chip, hero accent digits, the chart
  line, the dot in the logo. Nothing else gets a hue.
- Light mode paper is **warm** cream. Dark mode paper is **cool**
  neutral near-black. Don't tint dark paper warm — we tried, it felt
  off.
- The handicap index decimal digit ("8" in "6.8") is mint. The integer
  part stays ink. Don't italicize either.

---

## 3. Typography

### Stacks

```
display: 'Barlow Condensed', 'Oswald', system-ui, sans-serif;
body:    'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace;
```

Load Barlow Condensed (200, 300) and IBM Plex Mono (400, 500, 600, 700)
from Google Fonts.

### When to use which

| Element                              | Family             | Size  | Weight |
| ------------------------------------ | ------------------ | ----- | ------ |
| Hero numeral (handicap, big stat)    | Barlow Condensed   | 240px | 200    |
| Stat-strip numerals                  | IBM Plex Mono      | 38px  | 300    |
| Page H1                              | IBM Plex Mono      | 32px  | 400    |
| Card title (H2)                      | IBM Plex Mono      | 18px  | 400    |
| Course name / score in table         | IBM Plex Mono      | 16-22 | 400    |
| Body / table cell                    | IBM Plex Mono      | 13px  | 400    |
| Secondary body                       | IBM Plex Mono      | 14px  | 400    |
| Eyebrow / chip / button label        | IBM Plex Mono      | 10px  | 500    |
| Metadata, footnote                   | IBM Plex Mono      | 11px  | 400    |

### Tracking

- **Eyebrows / labels**: `0.16em` tracking, ALL CAPS — this is the
  editorial signature.
- **Chips / buttons**: `0.12em` tracking, ALL CAPS.
- **Display headlines (H1)**: `-0.025em` tracking.
- **Hero numerals**: `-0.04em` tracking + `0.82` line-height. Condensed
  fonts at scale need both.
- **Body**: `0` tracking.

### Italics

Reserved. The only italic we use is in H1 to highlight a key phrase
(e.g., *"trending in the right direction"*) and it carries the accent
color. Never italicize numerals.

### Numerals

All number columns use `font-variant-numeric: tabular-nums`. Score
pills and stat-strip values use `lining-nums tabular-nums`.

---

## 4. Spacing

A flat 4px-based scale. Use tokens, not arbitrary px values.

| Token        | px  | Use                                          |
| ------------ | --- | -------------------------------------------- |
| `--ps-sp-1`  | 4   | Tight gaps inside chips, between glyph + label |
| `--ps-sp-2`  | 8   | Inline gaps, button gutter                   |
| `--ps-sp-3`  | 12  | Table cell padding (vertical 7, horizontal 12) |
| `--ps-sp-4`  | 16  | Small section gap                            |
| `--ps-sp-5`  | 20  | Card padding y                               |
| `--ps-sp-6`  | 24  | Card padding x                               |
| `--ps-sp-7`  | 28  | Page top/bottom padding                      |
| `--ps-sp-8`  | 32  | Major section gap (hero ↔ stat strip)        |
| `--ps-sp-10` | 40  | Hero column gap                              |
| `--ps-sp-12` | 48  | Page side padding                            |

Page padding on 1920×1080 surfaces: `28px 48px 32px`.

---

## 5. Layout

- **Dashboard frame**: 1920×1080. Designs are letterboxed and scaled
  to viewport, not responsive (yet — phone view comes later).
- **Sidebar**: 200px fixed-width, hairline right rule.
- **Main column**: 1fr after the sidebar, with `gap: 36px` between
  major sections.
- **Hero**: `grid-template-columns: 1fr 1.6fr` — handicap on the left,
  trajectory chart on the right.
- **Stat strip**: 6 equal columns with `border-top` + `border-bottom`
  hairlines, internal column dividers as `border-right: 1px solid var(--ps-rule-c)`.

---

## 6. Borders & dividers

- Default rule: `1px solid var(--ps-rule-c)`. Hairline, low contrast.
- Emphatic rule (table head, topbar bottom): `1px solid var(--ps-ink)`.
- Chart guide lines: `0.5px solid var(--ps-rule-c)` (sub-pixel).
- Cards: `1px solid var(--ps-rule-c)` border + `var(--ps-paper-2)`
  background. No shadow, no radius.
- **Never** `border-radius` anything. Hard corners.

---

## 7. Components

### Eyebrow

The signature uppercase label that introduces every block.

```html
<div style="font: 500 10px/1.45 var(--ps-font-mono);
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--ps-ink-3);">
  Handicap Index · USGA
</div>
```

### Hero numeral

```html
<div style="font: 200 240px/0.82 var(--ps-font-display);
            letter-spacing: -0.04em;">
  6<span style="color: var(--ps-ink-3);">.</span><span style="color: var(--ps-accent);">8</span>
</div>
```

Always pattern: integer in ink, decimal point dimmed, fractional digit
in mint.

### Stat tile (used in stat strip)

```html
<div>
  <div class="eyebrow">Scoring avg</div>
  <div style="font: 300 38px/1 var(--ps-font-body);
              letter-spacing: -0.03em;
              margin-top: 4px;">72.4</div>
  <div style="font-size: 12px; color: var(--ps-accent); margin-top: 4px;
              font-weight: 500;">▼ 1.1</div>
</div>
```

Delta convention: `▼` for decreases, `▲` for increases. Color is
always mint when the change is *good for the golfer* (handicap down,
GIR% up). Use `var(--ps-warn)` only when the change is bad.

### Chip

```html
<span style="font: 500 10px/1 var(--ps-font-mono);
             letter-spacing: 0.12em;
             text-transform: uppercase;
             padding: 5px 10px;
             border: 1px solid var(--ps-rule-c);
             color: var(--ps-ink-2);">12M</span>
```

Active state: `background: var(--ps-ink); color: var(--ps-paper);
border-color: var(--ps-ink);`. The accent color is **not** used for
chip-active. Active chips are inverted ink.

### Button

Primary: solid ink fill, paper text, no radius.
Ghost: transparent fill, ink border, ink text.
Both use mono 11px @ weight 500, 8px × 16px padding, `0.06em` tracking,
ALL CAPS.

### Score pill in table

Two states:
- **Under par** (toPar ≤ 0): mint text, no fill.
- **Over par**: ink text, no fill.
- "to-par" delta sits to the right at 11px, ink-3 (over) or accent (under).

### Chart

Single-line line chart for trajectories:
- Stroke: 1.5px mint
- Area below stroke: `var(--ps-accent-dim)`
- Dots: 2.4px radius, paper fill, mint stroke
- Last point highlighted: 5.5px solid mint dot + mono numeric label
- Y-grid: 0.5px hairlines at major tick values
- Axis labels: 10px mono, ink-3, no axis line

### Sparkline (per-row in tables)

Single-line, no axis, no dots except final. 1.4px stroke, mint. Width
200–220px, height 28–30px.

---

## 8. Iconography

**We don't ship with an icon set.** Glyphs are limited to:

- Logo dot — a 8×8 mint solid circle prefix
- Arrows `▼ ▲ ← → ↘ ↙` — used inline in deltas and links
- Score notation `+/−` for to-par
- USGA badge text — set in mono, not depicted as a graphic

If a screen needs to suggest a thing (a course, a club, a player),
either:

1. Use a placeholder slot with a dashed hairline border + a mono caption
   describing what should drop in there, **or**
2. Use the user's own image — `<image-slot>` if available.

**Never** hand-draw an SVG icon. Never use emoji except as data
annotation (e.g., `⛳️` in a milestone note — and only if the user opts
into that voice).

---

## 9. Voice

- **Numerals over adjectives.** "▼ 0.4 this month" beats "improving
  steadily."
- **Lowercase metadata, sentence case in headlines.** Eyebrows are
  ALLCAPS, body is sentence case, marketing-style copy avoided.
- **Direct address.** The dashboard talks to the player: "Trending in
  the right direction." Not "Jordan's handicap is trending downward."
- **Mono for telemetry.** Anything that reads like a piece of data —
  ID numbers, dates, course slope/rating, last-sync timestamps — is in
  mono and lowercase (`pac.coast.u / '27`).

---

## 10. What to avoid

These are all things we tried or considered and rejected:

- Highlighter yellow fills (replaced by wavy mint underline scribbles
  in the wireframe stage, removed in production).
- Rounded corners on any element.
- Card shadows or elevation.
- Gradients (background, button, or text).
- Hand-drawn / sketchy fonts in production (kept in wireframes only).
- Icon-led labels — every label is text-first.
- Warm-tinted dark mode (causes the off-white text to look stained).
- Italicized numerals.
- More than one accent color. If you feel the need for a second hue,
  introduce hairline rules or paper-2 backgrounds first.

---

## 11. File map

```
PinSheet Dashboard.html        ← the canonical screen
dashboard.jsx                  ← the rendered React component + data
design-system/
  tokens.css                   ← CSS variables
  README.md                    ← this file
wireframes/                    ← exploration archive (not production)
```

When adding a new screen, import `tokens.css`, apply `.ps-light` or
`.ps-dark` on the root, and follow the component recipes in §7.

