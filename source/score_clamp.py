"""Shared per-hole / total gross clamping (issue #80 / #134, CWE-20).

Single source of truth for the score ceiling so the legacy `/api/rounds`
surface (`routes/rounds.py::_sanitize_scores`) and the `/api/v1` surface
(`routes/api_v1/rounds.py`) can never drift apart again. Before #134, only
the legacy surface clamped; v1 persisted arbitrary gross (999, negatives),
poisoning displayed scores and stats.

Lenient contract: blank/None gross stays unscored (never coerced to 0) and
nothing here raises on malformed input -- a crafted client must not be able
to 500 the endpoint. `hole_count` resolves selection strings (`"front"`,
`"back9"`, `"all"`, ...) as well as numeric counts, so the ceiling matches
the actual number of holes played.
"""

MAX_HOLE_GROSS = 20  # sane per-hole ceiling (issue #80/#134, CWE-20)

_HOLES_SELECTION_COUNTS = {
    "": 18,
    "18": 18,
    "all": 18,
    "9": 9,
    "front": 9,
    "back": 9,
    "front9": 9,
    "back9": 9,
}


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError, OverflowError):
        return default


def hole_count(value, default=18):
    """Resolve a holes selection or numeric count to a positive hole count.

    Unknown or malformed values fall back to `default`; the result is never
    zero or negative.
    """
    fallback = _safe_int(default, 18)
    if fallback <= 0:
        fallback = 18
    if isinstance(value, str):
        mapped = _HOLES_SELECTION_COUNTS.get(value.strip().lower())
        if mapped is not None:
            return mapped
    count = _safe_int(value, fallback)
    return count if count > 0 else fallback


def clamp_gross(raw, default=0):
    """Clamp a single raw gross value to [0, MAX_HOLE_GROSS]."""
    return max(0, min(_safe_int(raw, default), MAX_HOLE_GROSS))


def clamp_holes_in_place(holes):
    """Clamp each hole's gross to [0, MAX_HOLE_GROSS] in place.

    Blank/None gross is left untouched (unscored). Hole values may be plain
    dicts (v1 schema output) or any mapping supporting get/[]=.
    """
    for hole in (holes or {}).values():
        raw = hole.get("gross", "")
        if raw in (None, ""):
            continue
        hole["gross"] = str(clamp_gross(raw))


def clamp_total(raw, holes_count, default=0):
    """Clamp a score-only total to [0, MAX_HOLE_GROSS * hole_count(holes_count)].

    `default` is coerced to an int first, so a stored string total (e.g.
    `"80"`) survives a partial update that omits `gross_total`.
    """
    max_total = MAX_HOLE_GROSS * hole_count(holes_count)
    return max(0, min(_safe_int(raw, _safe_int(default, 0)), max_total))
