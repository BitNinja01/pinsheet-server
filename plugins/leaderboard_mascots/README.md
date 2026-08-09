# Leaderboard Mascots

[![CI](https://github.com/BitNinja01/pinsheet-server/actions/workflows/ci.yml/badge.svg)](https://github.com/BitNinja01/pinsheet-server/actions/workflows/ci.yml)

CI runs the full Python suite (`pytest`), a JS syntax check, and this plugin's
jsdom DOM test on every PR to `dev`/`main` — so the pass counts below are
continuously auditable, not a one-time local claim.

> Ported from **PR #31** (`feat(board): pixel mascots + golf-pun nicknames on
> the leaderboard`, github.com/BitNinja01/pinsheet-server/pull/31). The original
> PR edited core templates + core `app.css`; this rewrite delivers the same
> feature as a self-contained plugin with **zero core changes** (see
> [How it works](#how-it-works)).

Adds fun to the friends leaderboard ("The Board", the `/` page):

- **Pixel mascot** per player — a deterministic 8×8 pixel creature seeded from
  the player's display name, so a given display name always renders the same
  little guy. Rendered on a `<canvas>` with `image-rendering: pixelated`.
- **Golf-pun nickname** per player — Sandbagger, Wormburner, Chili Dipper,
  Three-Putt, etc. Deterministic per display name.
- **Leader flex** — the player on **row 1 of the board's current sort** draws
  from a flattering pool (Birdie Boss, Green Reaper…) and their mascot wears a
  gold crown. Re-sorting the board (`?sort=…`) moves the crown to whoever is
  on top of that view — it follows the displayed ranking, not a fixed metric.
- **Random spawn** — a roaming mascot pops in at a random spot over the board
  every few seconds and wanders across, then despawns. Under
  `prefers-reduced-motion` the roamer is disabled entirely (the loop never
  starts, so no canvases are spawned); the static per-row mascots still render.

### Notes & trade-offs

- **Seed = display name.** The mascot can't read the user id (the plugin makes
  no template changes and the id isn't in the board DOM), so the display name
  is the seed. Two players sharing an *exact* display name would share a mascot
  — a rarer form of the same class of collision the core avatar initials
  already have (`w[:1]|upper` matches on initials, which collide more often
  than full names).
- **Layout.** Each desktop row gains a ~26px mascot plus a gap in the
  fixed-width (220px) Player column, mirroring the original PR #31 markup. That
  trims the name/nickname budget by roughly 30px; very long two-word names can
  crowd the first stat column. Adjust `.lbm-mascot` width in `mascot.css` if
  that matters for your board.
- **CSS namespace.** Plugin styles use an `.lbm-` prefix (not the core `.ps-`
  design-system prefix) to avoid colliding with future core classes, while
  still consuming `--ps-*` theme variables.
- **Nickname pool.** Non-leaders draw from a 24-nickname pool and leaders from
  an 8-name pool, so two *different* players can still land on the same
  nickname (birthday-paradox territory once a board has ~6+ friends). This is
  cosmetic and intentional — nicknames are flavour, not identifiers.

### Known limitations (accepted, low priority)

These were surfaced by an adversarial review and consciously left as-is; they
are documented here so a future maintainer has the rationale (see `CHANGELOG.md`
for the finding IDs):

- Mobile nickname is a `display:block` span inside the inline `.board-card-name`
  — renders correctly, mildly non-semantic (SR-004). *To fix:* append the
  nickname as a sibling of `.board-card-name` inside `.board-card-head` and drop
  the inline `display:block`.
- `prefers-reduced-motion` is sampled once at page load; a mid-session OS toggle
  isn't observed until reload — standard for a multi-page (non-SPA) app (DA-005).
  *To fix:* keep the `setTimeout` id from `loop()` in a variable and register
  `matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", e =>
  { if (e.matches) clearTimeout(id); })` so the loop stops live when the user
  enables reduced motion.
- `startRoamer()` sets `overflow:hidden` on `.desktop-table`; this only runs on
  the board page (the only page nesting `.ps-avatar` in that container) (DA-006).
  *To fix:* wrap the rows in a dedicated `.lbm-stage` element and clip that
  instead of the shared table.

## How it works

This is a **pure client-side plugin** — it makes no changes to core templates
or routes. `register(app)` injects a stylesheet and a script through the core
`base.html` head/foot template blocks:

```python
def register(app):
    blocks = app._plugin_blocks
    # Append (don't clobber a co-installed plugin's blocks); the membership
    # check keeps it idempotent if register() is ever called twice.
    if _HEAD_BLOCK not in blocks.get("head", ""):
        blocks["head"] = blocks.get("head", "") + _HEAD_BLOCK  # <link ...mascot.css>
    if _FOOT_BLOCK not in blocks.get("foot", ""):
        blocks["foot"] = blocks.get("foot", "") + _FOOT_BLOCK  # <script ...mascot.js>
```

`mascot.js` runs on every page but **only acts when it finds the leaderboard
rows** (`.desktop-table .ps-avatar` and `.mobile-cards .ps-avatar`). On any
other page it is a no-op. For each row it reads the player's visible display
name, uses it as a stable seed, and grafts a mascot canvas + nickname beside
the name. Because the seed is the display name, the mascot is stable across
visits without needing the user id in the DOM.

## Files

```
plugins/leaderboard_mascots/
  __init__.py          # plugin_info, register(app), unregister(app)
  static/
    mascot.css         # mascot + roamer styles (served automatically)
    mascot.js          # seeded hash + PRNG, canvas drawing, roamer loop
  tests/
    dom_test.js        # Node + jsdom DOM behaviour test (loader-ignores tests/)
  README.md
```

## Testing

- **Python contract** (register/unregister block injection, static assets):
  `tests/test_plugin_leaderboard_mascots.py` in the repo's pytest suite.
- **JS DOM behaviour** (mascot placement, leader nick, seed stability, header
  avatar left alone, aria-hidden, idempotency, reduced-motion): `tests/dom_test.js`
  — `cd plugins/leaderboard_mascots/tests && npm install && node dom_test.js`.
  This runs automatically in CI (see `.github/workflows/ci.yml`). Note: jsdom has
  no 2D canvas backend, so the DOM test stubs `getContext()` and verifies
  placement/wiring only — the actual pixel rendering is checked by eye in a
  real browser.

## Install

Drop the `leaderboard_mascots/` folder into the server's `plugins/` directory
and restart. You should see:

```
plugin loaded: leaderboard_mascots v1.0.0
```

## Requirements

None. No Python dependencies, no database tables, no network access.
