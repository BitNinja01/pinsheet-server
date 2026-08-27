"""GET/POST/PUT/DELETE /api/v1/rounds -- owner-scoped (`WHERE user_id = ?`).

Single-round routes (`GET`/`PUT`/`DELETE /rounds/<id>`) enforce ownership IN
THE HANDLER (ADR-009): `get_round_by_id` is intentionally left untouched at
the store layer -- it has legitimate cross-player callers (`matches.py:17,150`,
`dashboard.py:46`) that must keep working. A v1 caller who does not own the
requested round id gets the EXACT SAME 404 Problem Details as a caller
requesting an id that does not exist at all, so a foreign id is never
distinguishable from a missing one (no existence oracle -- IDOR mitigation).
"""
import logging

from apiflask import APIBlueprint
from flask_login import current_user

from source.auth_keys import require_permission
from source.routes.api_v1 import scopes
from source.routes.api_v1.errors import problem, require_json_body
from source.routes.api_v1.schemas import (
    RoundCreateInSchema,
    RoundListOutSchema,
    RoundOutSchema,
    RoundUpdateInSchema,
)
from store import delete_round as _delete_round_row
from store import (
    get_all_rounds,
    get_round_by_id,
    next_round_index,
    recompute_handicaps_for_user,
    save_round,
    update_round as store_update_round,
)

_log = logging.getLogger("pinsheet")

rounds_v1 = APIBlueprint("rounds_v1", __name__, url_prefix="/api/v1/rounds")


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _round_to_dict(r) -> dict:
    return {
        "id": r.id,
        "date": r.date,
        "index": r.index,
        "course": r.course,
        "tees": r.tees,
        "holes_played": r.holes_played,
        "holes_selection": r.holes_selection,
        "entry_mode": r.entry_mode,
        "holes": {k: vars(h) for k, h in r.holes.items()},
        "total_gross": r.total_gross,
        "differential": r.differential,
        "computed_handicap": r.computed_handicap,
        "notes": r.notes,
        "excluded": r.excluded,
        "differential_locked": r.differential_locked,
    }


def _owned_round_or_404(round_id: int):
    """ADR-009 owner-check: `row is None or row.user_id != current_user.id`
    both collapse to the caller getting `None` here, so every call site emits
    an identical 404 regardless of which case it was."""
    row = get_round_by_id(round_id)
    if row is None or row.user_id != current_user.id:
        return None
    return row


@rounds_v1.route("", methods=["GET"])
@require_permission(scopes.ROUNDS_READ, contract="problem", permissive_pending=True)
@rounds_v1.output(RoundListOutSchema)
def list_rounds():
    rows = get_all_rounds(current_user.id)
    return {"rounds": [_round_to_dict(r) for r in rows]}


@rounds_v1.route("/<int:round_id>", methods=["GET"])
@require_permission(scopes.ROUNDS_READ, contract="problem", permissive_pending=True)
@rounds_v1.output(RoundOutSchema)
def get_round(round_id):
    row = _owned_round_or_404(round_id)
    if row is None:
        return problem(404, "Round not found.")
    return _round_to_dict(row)


@rounds_v1.route("", methods=["POST"])
@require_permission(scopes.ROUNDS_WRITE, contract="problem", permissive_pending=True)
@require_json_body
@rounds_v1.input(RoundCreateInSchema)
@rounds_v1.output(RoundOutSchema, status_code=201)
def create_round(json_data):
    date_val = json_data["date"]
    # user_id is bound EXACTLY here, server-side, from current_user.id --
    # NEVER from json_data (ADR-009; RoundCreateInSchema has no user_id
    # field at all, so there is nothing to bind even if a client sent one).
    index = next_round_index(date_val, current_user.id)

    golf_round = {
        "course": json_data.get("course", ""),
        "tees": json_data.get("tees", ""),
        "holes_played": json_data.get("holes_played", "18"),
        "entry_mode": json_data.get("entry_mode", "detailed"),
        "notes": json_data.get("notes", ""),
        "holes": json_data.get("holes", {}),
        "excluded": json_data.get("excluded", False),
    }
    if json_data.get("entry_mode") == "score_only":
        golf_round["total_gross"] = str(_safe_int(json_data.get("gross_total"), 0))
    elif golf_round["holes"]:
        golf_round["total_gross"] = str(sum(_safe_int(h.get("gross"), 0) for h in golf_round["holes"].values()))

    round_id = save_round(golf_round, date_val, index, current_user.id)

    # differential/computed_handicap are deliberately left unset above and
    # derived here via the SAME cascade the legacy bulk-import and post-
    # delete/exclude flows already use (store.recompute_handicaps_for_user,
    # settings.py:88-90 / rounds.py:737,752) -- not re-implemented inline.
    # RoundCreateInSchema also never declares these fields, so a client
    # cannot set them even if it tried (ADR-010 mass-assignment guard).
    # Disclosed simplification: this uses the simpler recompute-cascade
    # differential formula (store.py:313, raw total_gross vs. slope/rating),
    # not the live-entry ESC/course-handicap-adjusted formula the legacy
    # `/api/rounds` POST computes inline (rounds.py:254-278). Both produce a
    # valid WHS-eligible differential; they can diverge slightly for
    # partial/incomplete rounds. See build notes.
    recompute_handicaps_for_user(current_user.id)
    row = get_round_by_id(round_id)
    _log.info("api_v1.rounds: created id=%s date=%s index=%s user_id=%s", round_id, date_val, index, current_user.id)
    return _round_to_dict(row), 201


@rounds_v1.route("/<int:round_id>", methods=["PUT"])
@rounds_v1.doc(
    description=(
        "Partial update of an existing round. `date`/`round_index` cannot be "
        "changed via PUT (use POST to create a new round on a different "
        "date). Idempotent-safe by id: this endpoint performs a true SQL "
        "UPDATE keyed on (user_id, date, round_index), so the round's `id` "
        "is stable across edits -- retrying this exact request with the "
        "same `{id}` after a dropped response (e.g. on a flaky on-course "
        "connection) reconciles to the same row and returns 200 with the "
        "current state, never a spurious 404."
    )
)
@require_permission(scopes.ROUNDS_WRITE, contract="problem", permissive_pending=True)
@require_json_body
@rounds_v1.input(RoundUpdateInSchema)
@rounds_v1.output(RoundOutSchema)
def update_round(round_id, json_data):
    row = _owned_round_or_404(round_id)
    if row is None:
        return problem(404, "Round not found.")

    entry_mode = json_data.get("entry_mode", row.entry_mode)
    holes = json_data.get("holes") or {k: vars(h) for k, h in row.holes.items()}
    golf_round = {
        "course": json_data.get("course", row.course),
        "tees": json_data.get("tees", row.tees),
        "holes_played": json_data.get("holes_played", row.holes_played),
        "entry_mode": entry_mode,
        "notes": json_data.get("notes", row.notes),
        "holes": holes,
        "excluded": json_data.get("excluded", row.excluded),
        # Passthrough the round's existing PCC (audit fix, #121 merge): the
        # schema has no pcc field and the handler must not wipe it -- the
        # legacy edit path keeps it via `data.get("pcc", old_round.pcc)`
        # (routes/rounds.py:843); store.update_round defaults an absent pcc
        # to 0.0.
        "pcc": row.pcc,
    }
    if entry_mode == "score_only":
        golf_round["total_gross"] = str(_safe_int(json_data.get("gross_total"), row.total_gross))
    elif holes:
        golf_round["total_gross"] = str(sum(_safe_int(h.get("gross"), 0) for h in holes.values()))
    else:
        golf_round["total_gross"] = row.total_gross

    # Rev-2 M-3 (mandatory): date/round_index are pinned SERVER-SIDE from the
    # fetched, owner-checked row -- RoundUpdateInSchema does not declare
    # either field, so json_data can never contain them. Known v1 behavior
    # difference from the legacy UI: v1 cannot move a round to a new date
    # via PUT (disclosed, per plan).
    #
    # PM-1: use store.update_round (a true SQL UPDATE keyed WHERE id=? AND
    # user_id=?) instead of save_round (INSERT OR REPLACE = DELETE+INSERT,
    # which churns the row's surrogate `id`). This is dev's #66 fix (rebased
    # in): it keeps the id STABLE, so a mobile client retrying a
    # dropped-response PUT with the SAME `{id}` reconciles to the same row.
    # date/index are pinned server-side from the fetched row (Rev-2 M-3), so
    # a v1 PUT never moves the round to a new date. `store_update_round`
    # returns rows-updated (0 => the row vanished mid-edit -> 404).
    rows = store_update_round(round_id, golf_round, row.date, row.index, current_user.id)
    if rows == 0:
        # Defensive: the row vanished between the owner-check above and this
        # write (e.g. a concurrent DELETE) -- 404, not a 500.
        return problem(404, "Round not found.")
    recompute_handicaps_for_user(current_user.id)
    updated = get_round_by_id(round_id)  # id is stable across the UPDATE
    _log.info("api_v1.rounds: updated id=%s user_id=%s", round_id, current_user.id)
    return _round_to_dict(updated)


@rounds_v1.route("/<int:round_id>", methods=["DELETE"])
@require_permission(scopes.ROUNDS_DELETE, contract="problem", permissive_pending=True)
def delete_round(round_id):
    row = _owned_round_or_404(round_id)
    if row is None:
        return problem(404, "Round not found.")
    _delete_round_row(row.date, row.index, current_user.id)
    recompute_handicaps_for_user(current_user.id)
    _log.info("api_v1.rounds: deleted id=%s user_id=%s", round_id, current_user.id)
    return "", 204
