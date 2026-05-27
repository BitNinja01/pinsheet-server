import sqlite3
import logging

_DB_PATH = None
_log = logging.getLogger("pinsheet")


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError as e:
        _log.warning("WAL mode failed (may be on network filesystem): %s", e)
        conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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

    """)

    cur = db.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        db.execute(
            "INSERT INTO users (id, username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?, ?)",
            (1, "default", "Player", "", 1),
        )
    db.commit()
    db.close()
