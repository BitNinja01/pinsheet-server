"""Leaderboard Mascots — pixel creatures + golf-pun nicknames on The Board.

A self-contained plugin that adds a deterministic 8×8 pixel mascot and a
golf-pun nickname to every player on the friends leaderboard (the "/" board
page), plus a roaming mascot that randomly spawns and wanders across the board.

Everything is client-side: the plugin injects a stylesheet and a script via the
core head/foot template blocks. The script activates only when it finds the
leaderboard rows in the DOM, so it is a no-op on every other page. It needs no
core template changes — each mascot is seeded from the player's visible display
name, so the same person always gets the same little guy.
"""

_HEAD_BLOCK = (
    '<link rel="stylesheet" '
    'href="/plugins/leaderboard_mascots/static/mascot.css">'
)
_FOOT_BLOCK = (
    '<script src="/plugins/leaderboard_mascots/static/mascot.js"></script>'
)

plugin_info = {
    "name": "leaderboard_mascots",
    "version": "1.1.0",
    "description": "Pixel mascots and golf-pun nicknames on the friends leaderboard.",
    "author": "PinSheet Community",
}


def register(app):
    """Inject the mascot stylesheet (head) and script (foot) on every page.

    Blocks are appended rather than overwritten so we coexist with any other
    plugin that also contributes head/foot markup. The membership check keeps
    the operation idempotent if register() is ever called more than once.
    """
    blocks = app._plugin_blocks
    if _HEAD_BLOCK not in blocks.get("head", ""):
        blocks["head"] = blocks.get("head", "") + _HEAD_BLOCK
    if _FOOT_BLOCK not in blocks.get("foot", ""):
        blocks["foot"] = blocks.get("foot", "") + _FOOT_BLOCK


def unregister(app):
    """Best-effort removal of our injected blocks at shutdown."""
    blocks = getattr(app, "_plugin_blocks", None)
    if not isinstance(blocks, dict):
        return
    if "head" in blocks:
        blocks["head"] = blocks["head"].replace(_HEAD_BLOCK, "")
    if "foot" in blocks:
        blocks["foot"] = blocks["foot"].replace(_FOOT_BLOCK, "")
