"""Shared per-hole / total gross clamping (issue #80 / #134, CWE-20).

Single source of truth for the score ceiling so the legacy `/api/rounds`
surface (`routes/rounds.py::_sanitize_scores`) and the `/api/v1` surface
(`routes/api_v1/rounds.py`) can never drift apart again. Before #134, only
the legacy surface clamped; v1 persisted arbitrary gross (999, negatives),
poisoning displayed scores and stats.

Lenient contract: blank/None gross stays unscored (never coerced to 0) and
nothing here raises on malformed input -- a crafted client must not be able
to 500 the endpoint.
"""

MAX_HOLE_GROSS = 20  # sane per-hole ceiling (issue #80/#134, CWE-20)


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


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
    """Clamp a score-only total to [0, MAX_HOLE_GROSS * holes_count]."""
    max_total = MAX_HOLE_GROSS * _safe_int(holes_count, 18)
    return max(0, min(_safe_int(raw, default), max_total))
