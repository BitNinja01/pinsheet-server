import hashlib
import hmac
import json
import logging
import secrets
import string
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt

from database import get_db, init_db, set_db_path
from source.models import dict_to_round, RoundData, clamp_pcc, effective_pcc, safe_float, safe_positive_float

_log = logging.getLogger("pinsheet")
_DATA_DIR = Path(__file__).parent.parent / "data"

_HOLES_NORM = {"": "all", "18": "all", "front9": "front", "back9": "back"}

def _norm_holes(raw: str) -> str:
    return _HOLES_NORM.get(raw, raw)


def init_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    set_db_path(str(_DATA_DIR / "pinsheet.db"))
    init_db()


def load_settings(user_id: int = 1) -> dict:
    defaults = {"season_start_month": 1, "season_end_month": 12, "season_start_day": 1, "season_end_day": 28, "season_enabled": False}
    db = get_db()
    row = db.execute("SELECT data FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    _log.info("load_settings user_id=%s data=%s", user_id, row["data"] if row else "(none)")
    db.close()
    if row:
        data = json.loads(row["data"])
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    return defaults


def save_settings(data: dict, user_id: int = 1) -> None:
    db = get_db()
    _log.info("save_settings user_id=%s data=%s", user_id, json.dumps(data))
    row = db.execute("SELECT data FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        existing = json.loads(row["data"])
        existing.update(data)
        data = existing
    db.execute(
        "INSERT OR REPLACE INTO settings (user_id, data) VALUES (?, ?)",
        (user_id, json.dumps(data)),
    )
    db.commit()
    db.close()


def get_handicap_benchmarks(handicap_index: float) -> dict | None:
    path = _DATA_DIR / "handicap_benchmarks.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    idx = max(-4, min(36, int(handicap_index)))
    for key in (str(idx), f"+{idx}"):
        if key in data:
            return data[key]
    return None


def get_courses() -> dict:
    db = get_db()
    rows = db.execute("SELECT name, data FROM courses").fetchall()
    db.close()
    result = {}
    for row in rows:
        result[row["name"]] = json.loads(row["data"])
    return result


def reshape_course_data(course: dict) -> dict:
    """Convert a legacy TUI-shaped course document to the canonical shape.

    Legacy (TUI-era) courses store per-hole yardages inside each hole
    (``holes[h]["tees"][tee] = yardage``) and older wizard data uses an
    ``index`` stroke-index key. The canonical server shape stores per-hole
    yardages at the tee level (``tees[tee]["yardages"][hole] = yardage``)
    with holes holding only ``par`` + ``hole_index``.

    Canonical documents pass through unchanged; a new dict is returned
    (the input is never mutated).
    """
    out = json.loads(json.dumps(course))
    holes = out.get("holes")
    if isinstance(holes, dict):
        for hkey, hdata in list(holes.items()):
            if not isinstance(hdata, dict):
                continue
            if "index" in hdata and "hole_index" not in hdata:
                hdata["hole_index"] = hdata.pop("index")
            legacy_tees = hdata.pop("tees", None)
            if legacy_tees:
                for tee_name, yardage in legacy_tees.items():
                    tee_data = out.setdefault("tees", {}).setdefault(tee_name, {})
                    yardages = tee_data.setdefault("yardages", {})
                    yardages.setdefault(str(hkey), str(yardage))
    return out


def save_course(course, course_name) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO courses (name, data) VALUES (?, ?)",
        (course_name, json.dumps(course)),
    )
    db.commit()
    db.close()
    _log.info("course saved: %s", course_name)


def delete_course(course_name: str) -> None:
    db = get_db()
    db.execute("DELETE FROM courses WHERE name = ?", (course_name,))
    db.commit()
    db.close()
    _log.info("course deleted: %s", course_name)


def course_in_use_by_anyone(course_name: str) -> bool:
    """Revision 2, SEC-3: catalog-wide usage check. `courses` is a shared,
    global table with no `user_id` (ADR-011) -- unlike `get_all_rounds(...)`,
    which defaults to a SINGLE `user_id` (misleadingly `1` if uncalled with
    an explicit id) and therefore can only ever see that one caller's own
    rounds. A course-in-use conflict-check that only queries the CALLING
    user's rounds misses every OTHER user's rounds referencing the same
    shared course -- deleting it would silently orphan their round data
    (`course_name` becomes a dangling reference with no matching catalog
    entry). This queries `rounds` directly, across ALL users, for exactly
    that reason."""
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM rounds WHERE course_name = ? LIMIT 1", (course_name,)
    ).fetchone()
    db.close()
    return row is not None


def rename_course(old_name: str, new_name: str) -> None:
    db = get_db()
    db.execute("UPDATE courses SET name = ? WHERE name = ?", (new_name, old_name))
    db.execute("UPDATE rounds SET course_name = ? WHERE course_name = ?", (new_name, old_name))
    db.commit()
    db.close()
    _log.info("course renamed: %r -> %r", old_name, new_name)


def get_all_rounds(user_id: int, limit: int = None) -> list[RoundData]:
    # user_id is REQUIRED (no default). A default of 1 silently returned the
    # first user's rounds for any caller that forgot to pass an id — a
    # cross-user data-exposure footgun in a multi-user DB (eng-architect T6).
    db = get_db()
    query = "SELECT * FROM rounds WHERE user_id = ? ORDER BY date DESC, round_index DESC"
    if limit is not None:
        query += " LIMIT ?"
        rows = db.execute(query, (user_id, limit)).fetchall()
    else:
        rows = db.execute(query, (user_id,)).fetchall()
    db.close()
    result = []
    for row in rows:
        r = {
            "id": row["id"],
            "date": row["date"],
            "index": row["round_index"],
            "user_id": row["user_id"],
            "course": row["course_name"],
            "tees": row["tee_name"],
            "holes_played": row["holes_played"],
            "holes_selection": _norm_holes(row["holes_played"]),
            "entry_mode": row["entry_mode"],
            "holes": json.loads(row["holes"]) if row["holes"] else {},
            "total_gross": row["total_gross"],
            "differential": row["differential"],
            "notes": row["notes"],
            "excluded": bool(row["excluded"]),
            "computed_handicap": row["computed_handicap"],
            "differential_locked": bool(row["differential_locked"]) if row["differential_locked"] is not None else False,
            "pcc": row["pcc"] if row["pcc"] is not None else 0.0,
        }
        if row["total_putts"]:
            r["total_putts"] = row["total_putts"]
        result.append(dict_to_round(r))
    return result


def get_round_by_id(round_id: int) -> RoundData | None:
    db = get_db()
    row = db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    db.close()
    if not row:
        return None
    r = {
        "id": row["id"],
        "date": row["date"],
        "index": row["round_index"],
        "user_id": row["user_id"],
        "course": row["course_name"],
        "tees": row["tee_name"],
        "holes_played": row["holes_played"],
        "holes_selection": _norm_holes(row["holes_played"]),
        "entry_mode": row["entry_mode"],
        "holes": json.loads(row["holes"]) if row["holes"] else {},
        "total_gross": row["total_gross"],
        "differential": row["differential"],
        "notes": row["notes"],
        "excluded": bool(row["excluded"]),
        "computed_handicap": row["computed_handicap"],
        "differential_locked": bool(row["differential_locked"]) if row["differential_locked"] is not None else False,
        "pcc": row["pcc"] if row["pcc"] is not None else 0.0,
    }
    if row["total_putts"]:
        r["total_putts"] = row["total_putts"]
    return dict_to_round(r)


def next_round_index(date: str, user_id: int = 1) -> int:
    """Lowest free round_index for a given date+user, so multiple rounds on the
    same day don't collide on UNIQUE(user_id, date, round_index)."""
    db = get_db()
    rows = db.execute(
        "SELECT round_index FROM rounds WHERE user_id = ? AND date = ?",
        (user_id, date),
    ).fetchall()
    db.close()
    used = {row["round_index"] for row in rows}
    idx = 0
    while idx in used:
        idx += 1
    return idx


def save_round(golf_round, date, index, user_id: int = 1) -> int:
    db = get_db()
    total_putts = None
    holes = golf_round.get("holes", {})
    if holes:
        def _to_int(v):
            try:
                return int(v)
            except (ValueError, TypeError):
                return 0
        total_putts = sum(_to_int(h.get("putts")) for h in holes.values())
    # WHS Rule 5.6 / 5.1a: clamp defensively here too (not just at the
    # HTTP input boundary in routes/rounds.py) so a raw caller -- e.g. the
    # zip-import path in routes/settings.py, which passes an archive's raw
    # (untrusted) round dict straight through -- can never persist an
    # out-of-range pcc.
    pcc = clamp_pcc(golf_round.get("pcc", 0.0))
    cur = db.execute(
        """INSERT OR REPLACE INTO rounds
           (user_id, course_name, date, round_index, tee_name, holes_played,
            entry_mode, holes, total_gross, total_putts, differential, notes,
            excluded, computed_handicap, differential_locked, pcc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            golf_round.get("course", ""),
            date,
            index,
            golf_round.get("tees", ""),
            _norm_holes(golf_round.get("holes_played") or golf_round.get("holes_selection", "")),
            golf_round.get("entry_mode", ""),
            json.dumps(golf_round.get("holes", {})),
            golf_round.get("total_gross", ""),
            str(total_putts) if total_putts is not None else None,
            golf_round.get("differential", ""),
            golf_round.get("notes", ""),
            1 if golf_round.get("excluded") else 0,
            golf_round.get("computed_handicap", ""),
            1 if golf_round.get("differential_locked") else 0,
            pcc,
        ),
    )
    round_id = cur.lastrowid
    db.commit()
    db.close()
    _log.info("round saved: %s #%s course=%s id=%s", date, index, golf_round.get("course", "?"), round_id)
    return round_id


def update_round(round_id: int, golf_round, date, index, user_id: int = 1) -> int:
    """Update an existing round row in place, keyed by its primary id.

    Used by the edit path (including date changes) so the round keeps its id.
    A delete + INSERT-OR-REPLACE would mint a new id and orphan any
    match_rounds rows that reference this round. (Also the v1 PUT path, which
    pins date/index server-side so v1 edits keep the same date/index -- #50.)

    Returns the number of rows updated (0 if the round no longer exists or is
    owned by another user), so callers can detect a lost-row race.

    PRE-EXISTING CAVEAT (not fixed here): if this round is already linked to
    a match (a match_rounds row references it), editing the round's gross
    score / handicap here does NOT recompute or refresh that match_rounds
    row's stored `net` -- `net` is a snapshot computed once at link_round()
    time (see link_round / calc_playing_handicap call sites in
    routes/matches.py and routes/rounds.py) and there is no re-link/refresh
    path. A stale net can therefore persist after a round edit until the
    round is unlinked and re-linked.
    """
    db = get_db()
    total_putts = None
    holes = golf_round.get("holes", {})
    if holes:
        def _to_int(v):
            try:
                return int(v)
            except (ValueError, TypeError):
                return 0
        total_putts = sum(_to_int(h.get("putts")) for h in holes.values())
    # WHS Rule 5.6 / 5.1a: same defensive clamp as save_round.
    pcc = clamp_pcc(golf_round.get("pcc", 0.0))
    cur = db.execute(
        """UPDATE rounds SET
             course_name = ?, date = ?, round_index = ?, tee_name = ?,
             holes_played = ?, entry_mode = ?, holes = ?, total_gross = ?,
             total_putts = ?, differential = ?, notes = ?, excluded = ?,
             computed_handicap = ?, differential_locked = ?, pcc = ?
           WHERE id = ? AND user_id = ?""",
        (
            golf_round.get("course", ""),
            date,
            index,
            golf_round.get("tees", ""),
            _norm_holes(golf_round.get("holes_played") or golf_round.get("holes_selection", "")),
            golf_round.get("entry_mode", ""),
            json.dumps(golf_round.get("holes", {})),
            golf_round.get("total_gross", ""),
            str(total_putts) if total_putts is not None else None,
            golf_round.get("differential", ""),
            golf_round.get("notes", ""),
            1 if golf_round.get("excluded") else 0,
            golf_round.get("computed_handicap", ""),
            1 if golf_round.get("differential_locked") else 0,
            pcc,
            round_id,
            user_id,
        ),
    )
    rowcount = cur.rowcount
    db.commit()
    db.close()
    _log.info("round updated in place: id=%s -> %s #%s (rows=%s)", round_id, date, index, rowcount)
    return rowcount


def delete_round(date: str, index: str, user_id: int = 1) -> None:
    db = get_db()
    row = db.execute(
        "SELECT id FROM rounds WHERE user_id = ? AND date = ? AND round_index = ?",
        (user_id, date, int(index)),
    ).fetchone()
    round_id = row["id"] if row else None
    if round_id:
        db.execute("DELETE FROM match_rounds WHERE round_id = ?", (round_id,))
    db.execute(
        "DELETE FROM rounds WHERE user_id = ? AND date = ? AND round_index = ?",
        (user_id, date, int(index)),
    )
    db.commit()
    db.close()
    _log.info("round deleted: %s #%s", date, index)


def update_round_handicap(date: str, index: int, handicap: float, user_id: int) -> None:
    db = get_db()
    db.execute(
        "UPDATE rounds SET computed_handicap = ? WHERE user_id = ? AND date = ? AND round_index = ?",
        (str(handicap), user_id, date, index),
    )
    db.commit()
    db.close()


def update_round_differential(date: str, index: int, differential: float, user_id: int) -> None:
    db = get_db()
    locked = db.execute(
        "SELECT differential_locked FROM rounds WHERE user_id = ? AND date = ? AND round_index = ?",
        (user_id, date, index),
    ).fetchone()
    if locked and locked["differential_locked"]:
        db.close()
        return
    db.execute(
        "UPDATE rounds SET differential = ? WHERE user_id = ? AND date = ? AND round_index = ?",
        (str(differential), user_id, date, index),
    )
    db.commit()
    db.close()


def _is_incomplete_round(r, course_data) -> bool:
    """A detailed round with fewer scored holes than its selection requires.
    Such a round's gross can't be fairly rated, so it must stay excluded from
    the handicap (differential sentinel "0") and never be resurrected by the
    recompute cascade."""
    holes = r.holes
    if not holes:
        return False  # score_only / no per-hole data: user asserted the total
    scored = sum(1 for h in holes.values() if getattr(h, "gross", 0) > 0)
    course_holes = course_data.get("holes", {})
    expected = (len(course_holes) or 18) if r.holes_selection == "all" else 9
    return scored < expected


# WHS Rule 5.7: a Low Handicap Index is only established once the player
# has accumulated this many acceptable (eligible) scores.
WHS_LHI_MIN_SCORES = 20

# WHS Rule 5.7: the LHI window -- only prior displayed Handicap Index values
# within this many days of the round being processed are eligible.
WHS_LHI_WINDOW_DAYS = 365


def recompute_handicaps_for_user(user_id: int) -> int:
    from calc.handicap import (
        calc_handicap_index,
        apply_handicap_cap,
        _is_eligible_diff_round,
        exceptional_reduction,
        round_half_up,
        WHS_HANDICAP_WINDOW,
        calc_round_dif,
        calc_9hole_dif,
        calc_course_handicap,
        calc_adjusted_gross_score,
        WHS_MAX_HANDICAP_INDEX,
    )

    courses_data = get_courses()
    settings = load_settings(user_id)
    include_9hole = settings.get("include_9hole", True)

    all_rounds = get_all_rounds(user_id)
    if not all_rounds:
        return 0

    chronological = list(reversed(all_rounds))
    total = len(all_rounds)
    updated = 0
    db = get_db()

    # WHS Rule 5.7 (Low Handicap Index): walked oldest -> newest alongside
    # the main loop below. `prior_displayed` holds (date, displayed_hi) for
    # every round that has had a Handicap Index calculated so far -- the
    # *displayed* (i.e. Rule 5.8 capped) value, since Rule 5.7 defines LHI as
    # the lowest Handicap Index the player actually HELD. `acceptable_count`
    # tracks the number of acceptable (eligible) scores seen so far. Both are
    # evaluated using only rounds strictly BEFORE the round currently being
    # processed -- "the LHI used to process a given score is the one
    # determined from the record PRIOR to that score."
    prior_displayed: list[tuple[str, float]] = []
    acceptable_count = 0

    # WHS Rule 5.9 (Exceptional Score Reduction): `exceptional_reductions`
    # holds the per-round reduction (0.0 / -1.0 / -2.0) for every ELIGIBLE
    # round processed so far, oldest -> newest, appended ONLY for eligible
    # rounds -- i.e. this list is parallel to the same "most recent 20
    # eligible differentials" window that calc_handicap_index itself walks,
    # not to raw round count. That means `exceptional_reductions[-window:]`
    # always mirrors exactly the eligible differentials currently inside a
    # given round's Handicap Index window, so a reduction naturally dilutes
    # out once its exceptional round ages past the most-recent-20-eligible
    # boundary. The reduction is recomputed deterministically each pass
    # (not persisted to a column) since it's a pure function of the HI in
    # effect when the round was played (the prior DISPLAYED HI, already
    # tracked via `prior_displayed`) and that round's own differential --
    # both already available sequentially at this point in the loop.
    exceptional_reductions: list[float] = []

    for i, r in enumerate(chronological):
        if (not r.differential or r.differential == "0") and not r.differential_locked:
            course_data = courses_data.get(r.course)
            if course_data and not _is_incomplete_round(r, course_data):
                tee_data = course_data.get("tees", {}).get(r.tees)
                if tee_data and r.total_gross and r.total_gross != "0":
                    slope, rating = get_slope_rating(tee_data, r.holes_selection)
                    # WHS Rule 3 (Net Double Bogey) / Rule 12: the Score
                    # Differential must be computed from the ESC-adjusted
                    # gross (each hole capped to Net Double Bogey), not the
                    # raw total_gross, whenever per-hole data is available --
                    # otherwise a detailed round with a blow-up hole is
                    # over-counted relative to the SAME round entered live
                    # (rounds.py applies this cap inline via
                    # calc_adjusted_gross_score). Score-only rounds have no
                    # per-hole data to cap, so they correctly keep raw
                    # total_gross as the Adjusted Gross Score (AGS).
                    course_holes = course_data.get("holes", {})
                    if r.holes and course_holes:
                        # Course Handicap for the ESC cap uses the HI in
                        # effect when the round was played -- the prior
                        # DISPLAYED HI (same value Rule 5.9/ESR calls
                        # `hi_in_effect`, tracked via `prior_displayed`,
                        # which has not yet had this round appended). 0.0 is
                        # used when no HI has been established yet (the ESC
                        # cap then collapses to par+2 for every hole).
                        hi_before = prior_displayed[-1][1] if prior_displayed else 0.0
                        adj_hi = hi_before / 2 if r.holes_selection != "all" else hi_before
                        played_par = sum(int(course_holes.get(hn, {}).get("par", 0)) for hn in r.holes)
                        course_handicap = calc_course_handicap(adj_hi, played_par, slope, rating)
                        ags = calc_adjusted_gross_score(r.holes, course_holes, course_handicap)
                        adjusted_gross = float(r.total_gross) if ags is None else ags
                    else:
                        adjusted_gross = float(r.total_gross)
                    # WHS Rule 5.6 / 5.1a: subtract this round's own PCC
                    # (r.pcc, range-clamped by clamp_pcc at every write/
                    # construction site) inside calc_round_dif, matching
                    # rounds.py's live-save path exactly. WHS Rule 5.1b: a
                    # 9-hole score applies only HALF the day's PCC --
                    # effective_pcc(r.pcc, r.holes_selection).
                    if r.holes_selection != "all":
                        # WHS 9-hole combine: base 9-hole Score Differential
                        # plus the expected 9-hole adjustment keyed on the HI
                        # in effect when the round was played -- the prior
                        # DISPLAYED HI (`prior_displayed[-1]`, which has not
                        # yet had this round appended), or None when no HI has
                        # been established yet (raw base then).
                        diff = calc_9hole_dif(
                            slope, adjusted_gross, rating,
                            prior_displayed[-1][1] if prior_displayed else None,
                            effective_pcc(r.pcc, r.holes_selection),
                        )
                    else:
                        diff = calc_round_dif(slope, adjusted_gross, rating, effective_pcc(r.pcc, r.holes_selection))
                    str_diff = str(diff)
                    if r.differential != str_diff:
                        db.execute(
                            "UPDATE rounds SET differential = ? WHERE user_id = ? AND date = ? AND round_index = ?",
                            (str_diff, user_id, r.date, r.index),
                        )
                        updated += 1
                    # Keep the in-memory object in sync with the DB write so
                    # the handicap window below (and later iterations, since
                    # `all_rounds[idx:]` shares this same object) sees the
                    # fresh differential instead of a stale "0".
                    r.differential = str_diff

        # WHS Rule 5.2: calc_handicap_index requires most-recent-first input
        # and does its own recent-20-eligible windowing internally. `r` is
        # chronological[i] (oldest-first index i); its position in the
        # original most-recent-first `all_rounds` is `idx` below, so
        # `all_rounds[idx:]` is exactly "all rounds up to and including r,
        # in most-recent-first order" -- built via index arithmetic on the
        # already most-recent-first list instead of re-reversing a growing
        # slice of `chronological` on every iteration.
        idx = total - 1 - i
        history_most_recent_first = all_rounds[idx:]
        raw_hi = calc_handicap_index(history_most_recent_first, include_9hole)

        # WHS Rule 5.9 (Exceptional Score Reduction): the HI "in effect when
        # the round was played" is the most recent prior DISPLAYED HI
        # (`prior_displayed[-1]`, i.e. the post-ESR, post-Rule-5.8-cap value
        # -- `prior_displayed` has not yet had this round appended to it).
        # If no HI has been established yet, the round cannot be
        # exceptional. Only ELIGIBLE rounds consume a slot in the tracked
        # window (mirrors calc_handicap_index's own windowing -- excluded/
        # ineligible rounds never contribute a differential, so they must
        # not contribute a reduction slot either).
        hi_in_effect = prior_displayed[-1][1] if prior_displayed else None
        if _is_eligible_diff_round(r, include_9hole):
            exceptional_reductions.append(
                exceptional_reduction(hi_in_effect, float(r.differential))
            )

        # Sum of active reductions = every exceptional round's reduction
        # still within the most-recent-20-ELIGIBLE window ending at (and
        # including) this round -- exactly the same window
        # calc_handicap_index used to compute `raw_hi` above. Reductions are
        # already negative/zero, so ADDING the sum lowers the HI (this is
        # the mathematically-equivalent shortcut to applying the reduction
        # to each of the 20 windowed differentials individually and
        # re-averaging, since the reduction is uniform across the window).
        active_reduction_sum = sum(exceptional_reductions[-WHS_HANDICAP_WINDOW:])
        hi_after_esr = round_half_up(raw_hi + active_reduction_sum, 1) if raw_hi is not None else None

        # WHS Rule 5.7/5.8: LHI is only established once the record PRIOR to
        # this round already has >= 20 acceptable scores; the cap then
        # applies to this round's freshly-calculated (raw) HI using the
        # lowest displayed HI held within the 365 days preceding this
        # round's date (strictly prior rounds only -- see cutoff below).
        # The 365-day period preceding is a CLOSED interval -- a prior HI
        # dated exactly 365 days before this round's date is the boundary
        # day of that period and must be INCLUDED (`>=`, not `>`); using
        # strict `>` would silently shrink the window to 364 days.
        low_hi = None
        if acceptable_count >= WHS_LHI_MIN_SCORES:
            cutoff = datetime.fromisoformat(r.date).date() - timedelta(days=WHS_LHI_WINDOW_DAYS)
            candidates = [hi for d, hi in prior_displayed if datetime.fromisoformat(d).date() >= cutoff]
            if candidates:
                low_hi = min(candidates)

        hi = apply_handicap_cap(hi_after_esr, low_hi) if hi_after_esr is not None else None
        # WHS Rule 5.3: the 54.0 maximum is the FINAL issued ceiling, applied
        # AFTER the Rule 5.8 soft/hard cap (which must see the true raw
        # increase above `low_hi` -- see calc_handicap_index's docstring).
        # No lower clamp -- plus/negative Handicap Indexes are preserved.
        if hi is not None:
            hi = min(hi, WHS_MAX_HANDICAP_INDEX)

        if hi is not None:
            new_val = str(hi)
            if r.computed_handicap != new_val:
                db.execute(
                    "UPDATE rounds SET computed_handicap = ? WHERE user_id = ? AND date = ? AND round_index = ?",
                    (str(hi), user_id, r.date, r.index),
                )
                updated += 1
            prior_displayed.append((r.date, hi))
        elif r.computed_handicap:
            db.execute(
                "UPDATE rounds SET computed_handicap = '' WHERE user_id = ? AND date = ? AND round_index = ?",
                (user_id, r.date, r.index),
            )
            updated += 1

        if _is_eligible_diff_round(r, include_9hole):
            acceptable_count += 1

    db.commit()
    db.close()
    return updated


def set_round_excluded(date: str, index: int, excluded: bool, user_id: int) -> None:
    db = get_db()
    db.execute(
        "UPDATE rounds SET excluded = ? WHERE user_id = ? AND date = ? AND round_index = ?",
        (1 if excluded else 0, user_id, date, index),
    )
    db.commit()
    db.close()


def recompute_all_handicaps() -> None:
    users = get_users()
    if not users:
        _log.info("No users found — skipping handicap recompute")
        return

    _log.info("Recomputing handicaps for %d user(s)...", len(users))
    import time
    t0 = time.time()
    total_rounds = 0
    total_updated = 0

    for u in users:
        uid = u["id"]
        try:
            all_rounds = get_all_rounds(uid)
            updated = recompute_handicaps_for_user(uid)
            total_rounds += len(all_rounds) if all_rounds else 0
            total_updated += updated
            _log.info(
                "  User '%s': %d rounds, %d updated",
                u["username"], len(all_rounds) if all_rounds else 0, updated,
            )
        except Exception as exc:
            _log.error("  User '%s': error — %s", u["username"], exc)
            continue

    elapsed = time.time() - t0
    _log.info(
        "Handicap recompute complete: %d users, %d rounds processed, %d updated, %.3fs",
        len(users), total_rounds, total_updated, elapsed,
    )


def get_slope_rating(tee_data: dict, holes_sel: str) -> tuple[float, float]:
    """Extract (slope, rating) for the given 9/18-hole selection from a raw
    tee dict (round save/update, matches, dashboard, settings).

    Blank ("") slope/rating values are explicitly allowed by
    routes/courses.py:_coerce_course_numerics ("Blank/missing values are
    left as-is"), so a present-but-blank field must fall back the same as
    a missing one -- a plain `dict.get(field, default)` does NOT do this,
    since the default only applies when the key is absent, not when its
    value is "".

    CV-001 / DA-001: "0" (or a negative value) is NOT blank -- it parses
    fine as a float, but is domain-invalid: slope<=0 divides by zero in
    calc_round_dif (`113 / tee_slope`) and rating<=0 poisons the Score
    Differential (`adjusted_gross_score - tee_rating` inflates hugely),
    corrupting the WHS Rule 5.2 Handicap Index, not just a display stat.
    routes/courses.py:_coerce_course_numerics now rejects non-positive
    slope/rating at course-save time going forward, but this is the
    defense-in-depth backstop for already-persisted/legacy course data --
    `safe_positive_float` treats non-positive the same as blank/missing
    and cascades through the same front_/back_ -> base -> hardcoded-default
    fallback chain. This function must NEVER return a slope or rating <= 0.
    """
    if holes_sel == "front":
        slope  = safe_positive_float(tee_data.get("front_slope"),  tee_data.get("slope"),  default=113)
        rating = safe_positive_float(tee_data.get("front_rating"), tee_data.get("rating"), default=72.0)
    elif holes_sel == "back":
        slope  = safe_positive_float(tee_data.get("back_slope"),  tee_data.get("slope"),  default=113)
        rating = safe_positive_float(tee_data.get("back_rating"), tee_data.get("rating"), default=72.0)
    else:
        slope  = safe_positive_float(tee_data.get("slope"),  default=113)
        rating = safe_positive_float(tee_data.get("rating"), default=72.0)
    return slope, rating


def save_course_draft(draft_state: dict, user_id: int = 1) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    draft_dir = _DATA_DIR / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / f"course_draft_{user_id}.json").write_text(json.dumps(draft_state, indent=2))


def load_course_draft(user_id: int = 1) -> dict | None:
    path = _DATA_DIR / "drafts" / f"course_draft_{user_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def clear_course_draft(user_id: int = 1) -> None:
    path = _DATA_DIR / "drafts" / f"course_draft_{user_id}.json"
    if path.exists():
        path.unlink()
        _log.info("course draft cleared")


def save_round_draft(draft_state: dict, user_id: int = 1) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    draft_dir = _DATA_DIR / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / f"round_draft_{user_id}.json").write_text(json.dumps(draft_state, indent=2))


def load_round_draft(user_id: int = 1) -> dict | None:
    path = _DATA_DIR / "drafts" / f"round_draft_{user_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def clear_round_draft(user_id: int = 1) -> None:
    path = _DATA_DIR / "drafts" / f"round_draft_{user_id}.json"
    if path.exists():
        path.unlink()
        _log.info("round draft cleared")


def get_users() -> list:
    db = get_db()
    rows = db.execute("SELECT id, username, display_name FROM users WHERE password_hash != ''").fetchall()
    db.close()
    return [{"id": r["id"], "username": r["username"], "display_name": r["display_name"]} for r in rows]


def get_user(username: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    db.close()
    if row:
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "is_admin": bool(row["is_admin"])}
    return None


def get_user_by_id(user_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    if row:
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "password_hash": row["password_hash"], "is_admin": bool(row["is_admin"])}
    return None


def create_user(username: str, display_name: str, password: str) -> dict:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db = get_db()
    is_admin = 1 if db.execute("SELECT COUNT(*) FROM users WHERE password_hash != ''").fetchone()[0] == 0 else 0
    cur = db.execute(
        "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        (username, display_name, password_hash, is_admin),
    )
    db.commit()
    user_id = cur.lastrowid
    db.close()
    return {"id": user_id, "username": username, "display_name": display_name, "is_admin": bool(is_admin)}


# Fixed bcrypt hash used to normalize login timing for unknown usernames
# (issue #77). Computed once at import; the password value is irrelevant since
# no real login ever matches against it.
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"pinsheet-timing-normalizer", bcrypt.gensalt()).decode()


def verify_user(username: str, password: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    db.close()
    # Issue #77 (CWE-208): always run one bcrypt.checkpw so an unknown username
    # (no such row) takes the same ~time as a wrong password for a real user,
    # closing the login timing side-channel. Mirrors the _SENTINEL_KEY_HASH
    # pattern used for API keys.
    stored_hash = row["password_hash"] if (row and row["password_hash"]) else _DUMMY_PASSWORD_HASH
    password_ok = bcrypt.checkpw(password.encode(), stored_hash.encode())
    if row and row["password_hash"] and password_ok:
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "is_admin": bool(row["is_admin"])}
    return None


def user_count() -> int:
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db.close()
    return count


def real_user_count() -> int:
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users WHERE password_hash != ''").fetchone()[0]
    db.close()
    return count


def generate_password_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, token_hash, expires_at),
    )
    db.commit()
    db.close()
    _log.info("password reset token generated for user_id=%s", user_id)
    return token


def verify_password_reset_token(token: str) -> dict | None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = get_db()
    row = db.execute(
        "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    db.close()
    if not row:
        return None
    if row["used"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return None
    return get_user_by_id(row["user_id"])


def consume_password_reset_token(token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = get_db()
    row = db.execute(
        "SELECT user_id FROM password_reset_tokens WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    user_id = row["user_id"] if row else None
    db.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE token_hash = ?",
        (token_hash,),
    )
    db.commit()
    db.close()
    _log.info("password reset token consumed for user_id=%s", user_id)


def update_password(user_id: int, new_password: str) -> None:
    password_hash_bytes = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
    password_hash = password_hash_bytes.decode()
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id),
    )
    db.commit()
    db.close()
    _log.info("password updated for user_id=%s", user_id)


def _generate_invite_code() -> str:
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    return f"PS-{part1}-{part2}"


def create_invite_code(created_by: int) -> str:
    db = get_db()
    while True:
        code = _generate_invite_code()
        exists = db.execute("SELECT 1 FROM invite_codes WHERE code = ?", (code,)).fetchone()
        if not exists:
            break
    db.execute(
        "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
        (code, created_by),
    )
    db.commit()
    db.close()
    return code


def is_invite_code_valid(code: str) -> bool:
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM invite_codes WHERE code = ? AND used_by IS NULL",
        (code,),
    ).fetchone()
    db.close()
    return row is not None


def consume_invite_code(code: str, used_by: int) -> bool:
    db = get_db()
    cur = db.execute(
        "UPDATE invite_codes SET used_by = ?, used_at = datetime('now') WHERE code = ? AND used_by IS NULL",
        (used_by, code),
    )
    db.commit()
    affected = cur.rowcount
    db.close()
    return affected > 0


def seed_plugin_state(plugin_name: str) -> None:
    # Trust model: a newly discovered plugin is seeded DISABLED (enabled=0).
    # Dropping a folder into plugins/ must NOT auto-run its code — an admin
    # has to explicitly enable it in the admin UI first, which is the point at
    # which they validate/vouch for the plugin. This is the provenance gate:
    # "plugin present on disk" is not "plugin trusted to execute".
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO plugin_states (plugin_name, enabled) VALUES (?, 0)",
        (plugin_name,),
    )
    db.commit()
    db.close()


def get_plugin_states() -> dict[str, bool]:
    db = get_db()
    rows = db.execute("SELECT plugin_name, enabled FROM plugin_states").fetchall()
    db.close()
    return {r["plugin_name"]: bool(r["enabled"]) for r in rows}


def set_plugin_state(plugin_name: str, enabled: bool) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO plugin_states (plugin_name, enabled) VALUES (?, ?)",
        (plugin_name, 1 if enabled else 0),
    )
    db.commit()
    db.close()


def get_invite_codes() -> list:
    db = get_db()
    rows = db.execute("""
        SELECT ic.*, u1.display_name as creator_name, u2.display_name as user_name
        FROM invite_codes ic
        LEFT JOIN users u1 ON ic.created_by = u1.id
        LEFT JOIN users u2 ON ic.used_by = u2.id
        ORDER BY ic.created_at DESC
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        result.append({
            "code": r["code"],
            "created_by": r["created_by"],
            "creator_name": r["creator_name"],
            "used_by": r["used_by"],
            "user_name": r["user_name"],
            "created_at": r["created_at"],
            "used_at": r["used_at"],
        })
    return result


def create_match(
    created_by: int,
    course_name: str,
    date: str,
    allowance_percent: int = 100,
    format_key: str = "individual_match",
) -> int:
    # NOTE (WHS Rule 6.2 / Appendix C): `allowance_percent` and `format_key`
    # are effectively IMMUTABLE after match creation -- there is no
    # update_match()/edit path that changes either. `match_rounds.net` is
    # computed once, at link_round() time, from
    # calc_playing_handicap(course_handicap, allowance_percent) as it stood
    # at that moment; it is never recomputed. If an allowance/format-editing
    # path is ever added, it MUST also re-link (recompute net for) every
    # round already linked to the match, or those stored nets will silently
    # go stale relative to the new allowance.
    #
    # `format_key` is the display/source-of-truth for "which Appendix C
    # format produced this allowance" (see MATCH_FORMAT_LABELS in
    # routes/matches.py) -- `allowance_percent` alone is ambiguous for
    # display purposes (e.g. 95% is shared by both individual_stroke and
    # stableford_individual). `allowance_percent`, NOT `format_key`, remains
    # the value actually used in net math.
    db = get_db()
    cur = db.execute(
        "INSERT INTO matches (created_by, course_name, date, allowance_percent, format_key) "
        "VALUES (?, ?, ?, ?, ?)",
        (created_by, course_name, date, allowance_percent, format_key),
    )
    db.commit()
    match_id = cur.lastrowid
    db.close()
    _log.info("match created: id=%s", match_id)
    return match_id


def get_match(match_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        """SELECT m.*,
           (SELECT COUNT(*) FROM match_players WHERE match_id = m.id) as player_count,
           (SELECT COUNT(*) FROM match_rounds WHERE match_id = m.id) as round_count
           FROM matches m WHERE m.id = ?""",
        (match_id,),
    ).fetchone()
    db.close()
    return dict(row) if row else None


def get_all_matches() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT m.*,
           (SELECT COUNT(*) FROM match_players WHERE match_id = m.id) as player_count,
           (SELECT COUNT(*) FROM match_rounds WHERE match_id = m.id) as round_count
           FROM matches m ORDER BY m.created_at DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_matches_for_user(user_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT m.*
           FROM matches m
           JOIN match_players mp ON mp.match_id = m.id
           WHERE mp.user_id = ? AND m.status = 'active'
           ORDER BY m.created_at DESC""",
        (user_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def complete_match(match_id: int) -> None:
    db = get_db()
    db.execute("UPDATE matches SET status = 'completed' WHERE id = ?", (match_id,))
    db.commit()
    db.close()
    _log.info("match completed: id=%s", match_id)


def add_match_player(match_id: int, user_id: int) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO match_players (match_id, user_id) VALUES (?, ?)",
        (match_id, user_id),
    )
    db.commit()
    player_id = cur.lastrowid
    db.close()
    return player_id


def remove_match_player(match_id: int, user_id: int) -> bool:
    db = get_db()
    db.execute(
        "DELETE FROM match_rounds WHERE match_id = ? AND user_id = ?",
        (match_id, user_id),
    )
    cur = db.execute(
        "DELETE FROM match_players WHERE match_id = ? AND user_id = ?",
        (match_id, user_id),
    )
    db.commit()
    affected = cur.rowcount
    db.close()
    return affected > 0


def link_round(match_id: int, user_id: int, round_id: int, net: float) -> int:
    db = get_db()
    try:
        cur = db.execute(
            "INSERT OR IGNORE INTO match_rounds (match_id, user_id, round_id, net) VALUES (?, ?, ?, ?)",
            (match_id, user_id, round_id, net),
        )
        db.commit()
        return cur.lastrowid
    finally:
        db.close()


def unlink_round(match_id: int, user_id: int, round_id: int) -> bool:
    db = get_db()
    try:
        cur = db.execute(
            "DELETE FROM match_rounds WHERE match_id = ? AND user_id = ? AND round_id = ?",
            (match_id, user_id, round_id),
        )
        db.commit()
        return cur.rowcount > 0
    finally:
        db.close()


def get_match_rounds(match_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT mr.*, u.display_name as user_name
           FROM match_rounds mr
           JOIN users u ON mr.user_id = u.id
           WHERE mr.match_id = ?
           ORDER BY mr.user_id, mr.id""",
        (match_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_match_players(match_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT mp.*, u.display_name as user_name,
           COALESCE(SUM(mr.net), 0) as total_net,
           COUNT(mr.id) as round_count
           FROM match_players mp
           JOIN users u ON mp.user_id = u.id
           LEFT JOIN match_rounds mr ON mr.match_id = mp.match_id AND mr.user_id = mp.user_id
           WHERE mp.match_id = ?
           GROUP BY mp.id
                       ORDER BY total_net ASC""",
        (match_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def create_challenge(created_by: int, title: str, stat_key: str, start_date: str, end_date: str) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO challenges (created_by, title, stat_key, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
        (created_by, title, stat_key, start_date, end_date),
    )
    db.commit()
    challenge_id = cur.lastrowid
    db.close()
    _log.info("challenge created: id=%s title=%s", challenge_id, title)
    return challenge_id


def get_challenge(challenge_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        """SELECT c.*,
           (SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = c.id) as participant_count
           FROM challenges c WHERE c.id = ?""",
        (challenge_id,),
    ).fetchone()
    db.close()
    return dict(row) if row else None


def get_all_challenges() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT c.*,
           (SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = c.id) as participant_count
           FROM challenges c ORDER BY c.created_at DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def add_challenge_participant(challenge_id: int, user_id: int) -> None:
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO challenge_participants (challenge_id, user_id) VALUES (?, ?)",
        (challenge_id, user_id),
    )
    db.commit()
    db.close()


def remove_challenge_participant(challenge_id: int, user_id: int) -> bool:
    db = get_db()
    cur = db.execute(
        "DELETE FROM challenge_participants WHERE challenge_id = ? AND user_id = ?",
        (challenge_id, user_id),
    )
    db.commit()
    affected = cur.rowcount
    db.close()
    return affected > 0


def get_challenge_participants(challenge_id: int) -> list[int]:
    db = get_db()
    rows = db.execute(
        "SELECT user_id FROM challenge_participants WHERE challenge_id = ?",
        (challenge_id,),
    ).fetchall()
    db.close()
    return [r["user_id"] for r in rows]


def complete_challenge(challenge_id: int) -> None:
    db = get_db()
    db.execute("UPDATE challenges SET status = 'completed' WHERE id = ?", (challenge_id,))
    db.commit()
    db.close()
    _log.info("challenge completed: id=%s", challenge_id)


def get_clubs(user_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT id, category, club, number, brand, model, loft, lie, length, shaft_flex, shaft_brand, shaft, grip, sw, carry FROM clubs WHERE user_id = ? ORDER BY category, club",
        (user_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def save_club(club_data: dict, user_id: int) -> bool:
    """Insert or update a club for ``user_id``.

    Ownership guard (issue #69, CWE-639): the client controls the ``id`` primary
    key, so an INSERT OR REPLACE could otherwise overwrite another user's club
    row and reassign it. Reject when the id already exists under a different
    owner. Returns True if saved, False if rejected as a cross-user write.
    """
    db = get_db()
    existing = db.execute(
        "SELECT user_id FROM clubs WHERE id = ?", (club_data["id"],)
    ).fetchone()
    if existing is not None and existing["user_id"] != user_id:
        db.close()
        _log.warning(
            "save_club rejected: club %s is owned by another user", club_data["id"]
        )
        return False
    db.execute(
        """INSERT OR REPLACE INTO clubs (id, user_id, category, club, number, brand, model, loft, lie, length, shaft_flex, shaft_brand, shaft, grip, sw, carry)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            club_data["id"],
            user_id,
            club_data.get("category", "Irons"),
            club_data.get("club", ""),
            club_data.get("number", ""),
            club_data.get("brand", ""),
            club_data.get("model", ""),
            club_data.get("loft", ""),
            club_data.get("lie", ""),
            club_data.get("length", ""),
            club_data.get("shaft_flex", ""),
            club_data.get("shaft_brand", ""),
            club_data.get("shaft", ""),
            club_data.get("grip", ""),
            club_data.get("sw", ""),
            club_data.get("carry"),
        ),
    )
    db.commit()
    db.close()
    _log.info("club saved: %s", club_data["id"])
    return True


def delete_club(club_id: str, user_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM clubs WHERE id = ? AND user_id = ?", (club_id, user_id))
    row = db.execute("SELECT slot_ids FROM bag_slots WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        slots = json.loads(row["slot_ids"])
        slots = [s for s in slots if s != club_id]
        db.execute(
            "UPDATE bag_slots SET slot_ids = ? WHERE user_id = ?",
            (json.dumps(slots), user_id),
        )
    db.commit()
    db.close()
    _log.info("club deleted: %s", club_id)


def get_bag_slots(user_id: int) -> list[str]:
    db = get_db()
    row = db.execute("SELECT slot_ids FROM bag_slots WHERE user_id = ?", (user_id,)).fetchone()
    db.close()
    if row:
        return json.loads(row["slot_ids"])
    return []


def save_bag_slots(slot_ids: list, user_id: int) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO bag_slots (user_id, slot_ids) VALUES (?, ?)",
        (user_id, json.dumps(slot_ids)),
    )
    db.commit()
    db.close()
    _log.info("bag slots saved for user_id=%s", user_id)


def get_distinct_club_field_values(field: str, user_id: int) -> list[str]:
    # Issue #72 (CWE-200): scope to the caller's own clubs — without WHERE
    # user_id this leaked every user's brand/model/shaft/grip to any /bag
    # visitor. `field` stays allowlist-checked against SAFE (not user input in
    # the SQL text); user_id is bound as a parameter.
    SAFE = {"brand", "model", "shaft_brand", "shaft", "grip"}
    if field not in SAFE:
        return []
    db = get_db()
    rows = db.execute(
        f"SELECT DISTINCT {field} FROM clubs WHERE user_id = ? AND {field} IS NOT NULL AND {field} != '' ORDER BY {field}",
        (user_id,),
    ).fetchall()
    db.close()
    return [r[field] for r in rows]


# ---------------------------------------------------------------------------
# API keys (UC-APIKEY-001 / GAP-024) — hand-rolled, stdlib only.
# Store ONLY the sha256 hash + a short non-secret prefix; the plaintext key
# (psk_<token_urlsafe>) is shown exactly once at creation and never persisted
# or logged. Lookup is constant-time via hmac.compare_digest.
# ---------------------------------------------------------------------------

API_KEY_PERMISSIONS = (
    "rounds:read", "rounds:write", "rounds:delete",
    "courses:read", "courses:write", "courses:delete",
    "stats:read",
    "settings:read", "settings:write",
)

# Fixed-length dummy hash compared on the "key not found" path so an unknown key
# runs the same constant-time comparison as a known one (no existence timing oracle).
_SENTINEL_KEY_HASH = hashlib.sha256(b"pinsheet-api-key-sentinel").hexdigest()


def _hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _split_permissions(raw: str) -> list[str]:
    return [p for p in (raw or "").split(",") if p]


def _api_key_expired(expires_at: str | None) -> bool:
    """Tolerant expiry check that fails closed. Accepts ISO-8601 strings whether
    stored with a 'T' or space separator (SQLite datetime('now')) or a 'Z' suffix."""
    if not expires_at:
        return False
    raw = expires_at.strip().replace(" ", "T").rstrip("Z")
    try:
        return datetime.fromisoformat(raw) <= datetime.utcnow()
    except ValueError:
        return True  # malformed expiry — treat as expired


def create_api_key(user_id: int, label: str, permissions, expires_at: str | None = None) -> tuple[str, dict]:
    """Mint a new key. Returns (plaintext, metadata). The plaintext is returned
    exactly once here and is never stored or logged — only its sha256 hash and a
    short non-secret prefix are persisted."""
    plaintext = "psk_" + secrets.token_urlsafe(32)
    key_hash = _hash_api_key(plaintext)
    prefix = plaintext[:12]  # non-secret display fragment (e.g. "psk_Abc12Xy")
    if isinstance(permissions, (list, tuple)):
        perms = [p for p in permissions if p in API_KEY_PERMISSIONS]
        permissions = ",".join(perms)
    else:
        permissions = permissions or ""
    db = get_db()
    cur = db.execute(
        "INSERT INTO api_keys (user_id, label, key_hash, prefix, permissions, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, label, key_hash, prefix, permissions, expires_at),
    )
    db.commit()
    key_id = cur.lastrowid
    db.close()
    _log.info("api_key created: id=%s user_id=%s prefix=%s", key_id, user_id, prefix)
    meta = {
        "id": key_id,
        "user_id": user_id,
        "label": label,
        "prefix": prefix,
        "permissions": _split_permissions(permissions),
        "expires_at": expires_at,
    }
    return plaintext, meta


def list_api_keys(user_id: int) -> list[dict]:
    """Return metadata for a user's keys. Never returns key_hash or plaintext."""
    db = get_db()
    rows = db.execute(
        "SELECT id, label, prefix, permissions, created_at, last_used_at, expires_at, revoked_at "
        "FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    db.close()
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "prefix": r["prefix"],
            "permissions": _split_permissions(r["permissions"]),
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "expires_at": r["expires_at"],
            "revoked_at": r["revoked_at"],
        }
        for r in rows
    ]


def revoke_api_key(key_id: int, user_id: int) -> bool:
    """Owner-scoped revocation. Returns True iff a live key owned by user_id was revoked."""
    db = get_db()
    cur = db.execute(
        "UPDATE api_keys SET revoked_at = datetime('now') "
        "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
        (key_id, user_id),
    )
    db.commit()
    changed = cur.rowcount
    db.close()
    return changed > 0


def get_user_by_api_key(plaintext: str) -> dict | None:
    """Resolve a bearer key to its owning user dict (+ granted permissions), or None.
    Rejects unknown, revoked, and expired keys. Constant-time hash comparison."""
    if not plaintext or not plaintext.startswith("psk_"):
        return None
    key_hash = _hash_api_key(plaintext)
    db = get_db()
    row = db.execute(
        "SELECT id, user_id, key_hash, prefix, permissions, expires_at, revoked_at "
        "FROM api_keys WHERE key_hash = ?",
        (key_hash,),
    ).fetchone()
    # Constant-time compare on BOTH paths: an unknown key is compared against a
    # fixed sentinel so it cannot be distinguished from a known key by timing.
    stored_hash = row["key_hash"] if row is not None else _SENTINEL_KEY_HASH
    matches = hmac.compare_digest(stored_hash.encode(), key_hash.encode())
    if row is None or not matches:
        db.close()
        return None
    if row["revoked_at"]:
        db.close()
        return None
    if _api_key_expired(row["expires_at"]):
        db.close()
        return None
    db.execute("UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?", (row["id"],))
    db.commit()
    user_id = row["user_id"]
    permissions = row["permissions"]
    prefix = row["prefix"]
    db.close()
    user = get_user_by_id(user_id)
    if not user:
        _log.warning("api_key id=%s: key_hash matched but user_id=%s not found", row["id"], user_id)
        return None
    user["is_admin"] = False  # keys are never admin — enforced at the store layer too
    user["permissions"] = _split_permissions(permissions)
    user["prefix"] = prefix  # non-secret display fragment (store.py:1010) — audit-log correlator only
    return user
