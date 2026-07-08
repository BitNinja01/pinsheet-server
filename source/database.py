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
    db.commit()
    db.close()
