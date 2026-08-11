#!/usr/bin/env python3
"""Force-resync every round's differential + handicap index against *current*
course data.

The normal recompute (app startup, round edits) is sticky: it only fills an
empty/"0" differential and never rewrites one that is already set. So a course
slope/rating correction does NOT propagate to rounds that already computed a
differential. This script runs the *forced* recompute (see
``store.recompute_handicaps_for_user(..., force=True)``): it recomputes every
round's differential from the course the round references, then rolls the
handicap index forward over each user's 20-round window.

Preserved regardless of force:
  * ``differential_locked`` rounds  — manual overrides are never touched.
  * the "0" skip sentinel           — rounds deliberately excluded stay excluded.

Usage
-----
  # Dry-run (default): runs against a throwaway copy of the DB and prints the
  # exact before/after diff. The real DB is never opened for writing.
  python scripts/resync_handicaps.py

  # Apply for real:
  python scripts/resync_handicaps.py --apply

  # Point at a non-default data dir / limit to one user:
  python scripts/resync_handicaps.py --data /path/to/data --user 3 --apply
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "source"))

from database import set_db_path, get_db  # noqa: E402
import store  # noqa: E402


def _snapshot(db_path: str, user_id: int | None) -> dict:
    """Map (user_id, date, round_index) -> (differential, computed_handicap)."""
    set_db_path(db_path)
    db = get_db()
    if user_id is None:
        rows = db.execute(
            "SELECT user_id, date, round_index, differential, computed_handicap FROM rounds"
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT user_id, date, round_index, differential, computed_handicap "
            "FROM rounds WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    db.close()
    return {
        (r["user_id"], r["date"], r["round_index"]): (r["differential"], r["computed_handicap"])
        for r in rows
    }


def _run(db_path: str, user_id: int | None) -> int:
    set_db_path(db_path)
    if user_id is None:
        return store.recompute_all_handicaps(force=True)
    return store.recompute_handicaps_for_user(user_id, force=True)


def _print_diff(before: dict, after: dict) -> int:
    changed = 0
    for key in sorted(before):
        b_diff, b_hi = before[key]
        a_diff, a_hi = after.get(key, (b_diff, b_hi))
        if (b_diff, b_hi) == (a_diff, a_hi):
            continue
        changed += 1
        uid, date, idx = key
        parts = [f"user={uid} {date} #{idx}"]
        if b_diff != a_diff:
            parts.append(f"diff {b_diff!r} -> {a_diff!r}")
        if b_hi != a_hi:
            parts.append(f"index {b_hi!r} -> {a_hi!r}")
        print("  " + "  ".join(parts))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data",
                    help="data dir holding pinsheet.db (default: <repo>/data)")
    ap.add_argument("--user", type=int, default=None,
                    help="limit to a single user id (default: all users)")
    ap.add_argument("--apply", action="store_true",
                    help="write changes to the real DB (default: dry-run on a copy)")
    args = ap.parse_args()

    real_db = args.data / "pinsheet.db"
    if not real_db.exists():
        print(f"ERROR: no DB at {real_db}", file=sys.stderr)
        return 1

    before = _snapshot(str(real_db), args.user)

    if args.apply:
        print(f"APPLY: forcing resync on {real_db} ...")
        updated = _run(str(real_db), args.user)
        after = _snapshot(str(real_db), args.user)
        changed = _print_diff(before, after)
        print(f"done: {changed} round(s) changed, {updated} row update(s) written.")
        return 0

    # Dry-run: operate on a throwaway copy, real DB untouched.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "pinsheet.db"
        shutil.copy2(real_db, copy)
        for suffix in ("-wal", "-shm"):
            side = real_db.with_name(real_db.name + suffix)
            if side.exists():
                shutil.copy2(side, copy.with_name(copy.name + suffix))
        _run(str(copy), args.user)
        after = _snapshot(str(copy), args.user)

    print("DRY-RUN (no changes written). Would change:")
    changed = _print_diff(before, after)
    print(f"{changed} round(s) would change. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
