# Leaderboard Mascots — validation screenshots

Captured from the real PinSheet server (two seeded users) with the
`leaderboard_mascots` plugin loaded, driven by headless Google Chrome. They
show the plugin executing on The Board (`/`): a deterministic pixel mascot +
golf-pun nickname per player, a gold crown on the rank-1 leader, and the mobile
board-card layout.

| File | View |
|------|------|
| `board-desktop.png` | Full desktop board |
| `board-closeup.png` | Top rows — crown + nicknames close-up |
| `board-mobile.png`  | Mobile board cards |

Programmatic evidence from the same run: 4 row mascots, all with drawn
(non-transparent) pixels; `aria-label`s `"mascot: The Closer"` (leader) and
`"mascot: Duffer"`; computed mascot width 26px (size-token fallback).

Plugin feature PR: #59. Standalone plugin repo:
https://github.com/malcolm-x-evo/pinsheet-leaderboard-mascots
