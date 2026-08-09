# Changelog — leaderboard_mascots

## 1.0.0

Initial release. Ports **PR #31** (`feat(board): pixel mascots + golf-pun
nicknames on the leaderboard`,
https://github.com/BitNinja01/pinsheet-server/pull/31) from a core-template +
core-`app.css` edit into a self-contained plugin with zero core changes.

### Adversarial review — finding → fix map

An adversarial review (Steelman S-003, Self-Refine S-010, Devil's Advocate
S-002, Constitutional S-007) produced the findings below. **0 Critical.** Major
findings were all fixed; Minors were fixed or accepted with rationale.

| ID | Sev | Finding | Resolution |
|----|-----|---------|------------|
| SR-001 | Major | Roamer canvases leak under `prefers-reduced-motion` (CSS `display:none` ⇒ no `animationend` ⇒ no cleanup, loop keeps spawning) | `startRoamer()` returns early via `prefersReducedMotion()` (`mascot.js`); DOM test asserts the skip |
| DA-001 | Major | Roaming canvas built by hand in `spawn()`, missing `aria-hidden`/`title` | `spawn()` now builds via `makeCanvas()`; DOM test asserts all canvases `aria-hidden` + titled |
| SR-007 | Major | Claimed jsdom DOM test not committed | Committed `tests/dom_test.js` (+ `tests/package.json`) |
| DA-002 | Major | DOM test not enforced in CI | Added Node job to `.github/workflows/ci.yml` running `node dom_test.js` |
| CC-003 | Major | `.gitignore` cited a PLUGINS.md convention that did not exist | Added "Bundled first-party plugins" section to `docs/PLUGINS.md`; git mechanics confirmed sound |
| SM-002 / SR-003 | Major | "Leader flex" is relative to the current sort, not a fixed metric | Documented in README ("follows the displayed ranking") |
| SR-005 | Minor | Canvas had `title` only for a11y | Added `aria-hidden="true"` in `makeCanvas()` |
| SR-006 | Minor | `register()` not idempotent | Membership-check guard (`__init__.py`) + `test_register_is_idempotent` |
| CC-002 | Minor | Reused core `.ps-` CSS namespace | Renamed plugin classes to `.lbm-` (css + js + test) |
| CC-001 | Minor | `unregister()` mutates `_plugin_blocks` post-`register()`, tension with PLUGINS.md §5 | Documented allowed shutdown exception in `docs/PLUGINS.md` §5 |
| SM-001 / DA-004 | Minor | Determinism / collision wording imprecise | Reworded README (seed = exact display name; nickname-pool collisions) |
| SR-002 / DA-003 | Minor | Mascot tightens the fixed 220px Player column | Documented in README with tuning guidance |
| SR-004 | Minor | Mobile nickname `display:block` on inline span | Accepted (renders correctly) — see README "Known limitations" |
| DA-005 | Minor | `prefers-reduced-motion` sampled once at load | Accepted (standard non-SPA behaviour) — README |
| DA-006 | Minor | `overflow:hidden` side effect on `.desktop-table` | Accepted (only runs on the board page) — README |

### Verification (pass 3)

Self-contained audit trail for this release's fixes (spot-verified locally):

- Every finding ID in the table above is unique — no ID repeats across rows (the mobile `display:block` row was de-duplicated from the wording row during review pass 2).
- Committed jsdom DOM suite (`tests/dom_test.js`): **18/18 pass** (adds empty-board + single-player cases; asserts aria-hidden on all canvases, reduced-motion roamer skip, idempotent re-init).
- `node --check` clean on `mascot.js` and `dom_test.js`.
- Plugin Python contract (`tests/test_plugin_leaderboard_mascots.py`): **7/7 pass**; full repo suite: **668 passed**.
- App boot: `plugin loaded: leaderboard_mascots v1.0.0`; `/plugins/leaderboard_mascots/static/{mascot.js,mascot.css}` → HTTP 200.

Captured output (verbatim, local run):

```
$ node plugins/leaderboard_mascots/tests/dom_test.js ; echo exit=$?
... (18 checks)
ALL DOM TESTS PASS
exit=0

$ node --check plugins/leaderboard_mascots/static/mascot.js && \
  node --check plugins/leaderboard_mascots/tests/dom_test.js && echo OK
OK

$ pytest tests/test_plugin_leaderboard_mascots.py -q
7 passed in 0.02s

$ pytest -q            # full repo suite
668 passed, 86 warnings in 144.17s (0:02:24)
```

CI (`.github/workflows/ci.yml`) re-runs pytest + JS syntax check + the DOM suite on every PR, so the above stays enforced, not one-time.
