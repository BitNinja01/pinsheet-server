import sqlite3
import logging

_DB_PATH = None
_USE_NOLOCK = None
_log = logging.getLogger("pinsheet")


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def _open_db_normal():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS __ping (x)")
    conn.execute("DROP TABLE IF EXISTS __ping")
    conn.commit()
    return conn


def _open_db_nolock():
    conn = sqlite3.connect(f"file:{_DB_PATH}?nolock=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db() -> sqlite3.Connection:
    global _USE_NOLOCK
    if _USE_NOLOCK:
        return _open_db_nolock()
    if _USE_NOLOCK is False:
        return _open_db_normal()
    try:
        conn = _open_db_normal()
        _USE_NOLOCK = False
        return conn
    except sqlite3.OperationalError:
        _log.warning("Normal SQLite open failed (likely CIFS/SMB) — falling back to nolock mode")
        _USE_NOLOCK = True
        return _open_db_nolock()


def _add_column_if_missing(db: sqlite3.Connection, table: str, column_def: str) -> None:
    """Run `ALTER TABLE {table} ADD COLUMN {column_def}`, treating SQLite's
    "duplicate column name" OperationalError (raised when this migration has
    already run against this DB) as expected and safe to swallow. Any OTHER
    OperationalError -- disk full, DB locked, malformed column_def, wrong
    table name, etc. -- is deliberately RE-RAISED rather than caught by a
    bare `except Exception: pass`, so a genuine migration failure surfaces
    at startup instead of silently leaving the column missing."""
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        db.commit()
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def init_db() -> None:
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            display_name  TEXT NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',
            is_admin      INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         INTEGER PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used       INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS courses (
            id          INTEGER PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            data        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id            INTEGER PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id),
            course_name   TEXT NOT NULL,
            date          TEXT NOT NULL,
            round_index   INTEGER NOT NULL DEFAULT 0,
            tee_name      TEXT,
            holes_played  TEXT,
            entry_mode    TEXT,
            holes         TEXT,
            total_gross   TEXT,
            total_putts   TEXT,
            differential  TEXT,
            notes         TEXT,
            excluded      INTEGER DEFAULT 0,
            computed_handicap TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, date, round_index)
        );

        CREATE TABLE IF NOT EXISTS settings (
            user_id  INTEGER PRIMARY KEY REFERENCES users(id),
            data     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invite_codes (
            code        TEXT PRIMARY KEY,
            created_by  INTEGER REFERENCES users(id),
            used_by     INTEGER REFERENCES users(id),
            created_at  TEXT DEFAULT (datetime('now')),
            used_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS plugin_states (
            plugin_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS matches (
            id          INTEGER PRIMARY KEY,
            created_by  INTEGER NOT NULL REFERENCES users(id),
            course_name TEXT NOT NULL,
            date        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            -- WHS Rule 6.2 / Appendix C: Handicap Allowance percent applied
            -- to the Course Handicap to derive the Playing Handicap for this
            -- match's format. Default 100 preserves pre-Rule-6.2 behavior
            -- (Playing Handicap == Course Handicap) for existing/unspecified
            -- matches. IMMUTABLE in practice: set once at create_match()
            -- time; there is no edit/update path, and match_rounds.net is
            -- computed from this value only at link_round() time (never
            -- recomputed), so a hypothetical future "edit allowance" feature
            -- would need to re-link every already-linked round too.
            allowance_percent INTEGER NOT NULL DEFAULT 100,
            -- WHS Appendix C format key (matches WHS_HANDICAP_ALLOWANCES /
            -- MATCH_FORMAT_LABELS keys in source/routes/matches.py), stored
            -- alongside allowance_percent as the display/source-of-truth for
            -- "which format produced this allowance" -- allowance_percent
            -- ALONE is ambiguous for display (e.g. 95% is shared by both
            -- individual_stroke and stableford_individual), so this column
            -- exists purely to resolve that ambiguity in the UI.
            -- allowance_percent (not this column) remains the value used in
            -- net math. Same immutability caveat as allowance_percent.
            format_key  TEXT NOT NULL DEFAULT 'individual_match',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS match_players (
            id         INTEGER PRIMARY KEY,
            match_id   INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            UNIQUE(match_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS match_rounds (
            id         INTEGER PRIMARY KEY,
            match_id   INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            round_id   INTEGER NOT NULL REFERENCES rounds(id),
            net        REAL NOT NULL,
            UNIQUE(match_id, user_id, round_id)
        );

        CREATE TABLE IF NOT EXISTS challenges (
            id          INTEGER PRIMARY KEY,
            created_by  INTEGER NOT NULL REFERENCES users(id),
            title       TEXT NOT NULL,
            stat_key    TEXT NOT NULL,
            start_date  TEXT NOT NULL,
            end_date    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS challenge_participants (
            id           INTEGER PRIMARY KEY,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            UNIQUE(challenge_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS clubs (
            id         TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            category   TEXT NOT NULL,
            club       TEXT NOT NULL,
            number     TEXT DEFAULT '',
            brand      TEXT DEFAULT '',
            model      TEXT DEFAULT '',
            loft       TEXT DEFAULT '',
            lie        TEXT DEFAULT '',
            length     TEXT DEFAULT '',
            shaft_flex TEXT DEFAULT '',
            shaft_brand TEXT DEFAULT '',
            shaft      TEXT DEFAULT '',
            grip       TEXT DEFAULT '',
            sw         TEXT DEFAULT '',
            carry      INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bag_slots (
            user_id  INTEGER PRIMARY KEY REFERENCES users(id),
            slot_ids TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id           INTEGER PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            label        TEXT NOT NULL,
            key_hash     TEXT UNIQUE NOT NULL,
            prefix       TEXT NOT NULL,
            permissions  TEXT NOT NULL DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now')),
            last_used_at TEXT,
            expires_at   TEXT,
            revoked_at   TEXT
        );

    """)
    for col in ("number", "brand", "model", "lie", "length", "shaft_flex", "shaft_brand"):
        try:
            db.execute(f"ALTER TABLE clubs ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception:
            pass
    try:
        db.execute("ALTER TABLE clubs DROP COLUMN head")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE rounds ADD COLUMN differential_locked INTEGER NOT NULL DEFAULT 0")
        db.commit()
    except Exception:
        pass  # column already exists
    # WHS Rule 6.2: existing DBs predating the Playing Handicap allowance
    # feature won't have this column yet -- backfill it with the
    # non-breaking default (100 == no allowance reduction, matches prior
    # behavior) so an existing DB loads without error. Uses the narrow
    # duplicate-column-only guard (_add_column_if_missing), not a bare
    # `except Exception: pass`, so an unrelated ALTER failure (e.g. a locked
    # or corrupt DB) is not silently hidden.
    _add_column_if_missing(db, "matches", "allowance_percent INTEGER NOT NULL DEFAULT 100")
    # WHS Appendix C: existing DBs predating the format_key column backfill
    # to 'individual_match' -- the same default format as allowance_percent's
    # 100 default, so a pre-existing match row displays "Individual match
    # play (100%)" (its actual pre-Rule-6.2 net behavior) rather than an
    # ambiguous/incorrect label.
    _add_column_if_missing(db, "matches", "format_key TEXT NOT NULL DEFAULT 'individual_match'")
    db.commit()
    db.close()
