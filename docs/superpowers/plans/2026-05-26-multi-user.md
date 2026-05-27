# Multi-User PinSheet Modern — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform PinSheet Modern from a single-user JSON-backed local app into a multi-user SQLite-backed self-hosted web application with invite-code registration.

**Architecture:** Three sequential phases: (A) rewrite `store.py` from JSON files to SQLite, (B) add authentication with Flask-Login/bcrypt/CSRF/rate-limiting, (C) add multi-user UI with user switcher, `?user=` view param, and admin invite management. Each phase produces a working, smoke-testable app.

**Tech Stack:** Flask, waitress, SQLite (stdlib), bcrypt, flask-login, flask-limiter, flask-wtf. No Docker, no CLI tools.

**Verification:** This project has no test suite. Verify with `python -m py_compile source/<file>.py` after every code change. Smoke-test by running `python source/main.py` and browsing key routes.

---

## Phase A: SQLite Migration

### Task A1: Rewrite store.py — database foundation

**Files:**
- Create: `source/database.py` (new — connection + schema management)
- Rewrite: `source/store.py` (all 18 functions → SQLite)

- [ ] **Step 1: Create `source/database.py` — connection and schema**

```python
import sqlite3
import logging
from pathlib import Path

_log = logging.getLogger("pinsheet")
_DB_PATH = None


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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
            created_at    TEXT DEFAULT (datetime('now'))
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
```

- [ ] **Step 2: Verify compilation**

```
python -m py_compile source/database.py
```
Expected: no output (success).

- [ ] **Step 3: Rewrite `source/store.py` — full SQLite backend**

Replace the entire contents of `source/store.py` (keep the `_log` logger and imports). Every function now uses `database.get_db()` instead of JSON file I/O. The public API surface preserves compatible signatures — callers in `main.py` do not change.

```python
import json
import logging
from pathlib import Path

from database import get_db, init_db

_log = logging.getLogger("pinsheet")
_DATA_DIR = Path(__file__).parent.parent / "data"


def init_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_settings(user_id: int = 1) -> dict:
    defaults = {"season_start_month": 1, "season_end_month": 12, "season_start_day": 1, "season_end_day": 28, "season_enabled": False}
    db = get_db()
    row = db.execute("SELECT data FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    db.close()
    if row:
        data = json.loads(row["data"])
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    return defaults


def save_settings(data: dict, user_id: int = 1) -> None:
    db = get_db()
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


def rename_course(old_name: str, new_name: str) -> None:
    db = get_db()
    db.execute("UPDATE courses SET name = ? WHERE name = ?", (new_name, old_name))
    db.execute("UPDATE rounds SET course_name = ? WHERE course_name = ?", (new_name, old_name))
    db.commit()
    db.close()
    _log.info("course renamed: %r -> %r", old_name, new_name)


def get_all_rounds(user_id: int = 1, limit: int = None) -> list:
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
            "date": row["date"],
            "index": row["round_index"],
            "user_id": row["user_id"],
            "course": row["course_name"],
            "tees": row["tee_name"],
            "holes_played": row["holes_played"],
            "entry_mode": row["entry_mode"],
            "holes": json.loads(row["holes"]) if row["holes"] else {},
            "total_gross": row["total_gross"],
            "differential": row["differential"],
            "notes": row["notes"],
            "excluded": bool(row["excluded"]),
            "computed_handicap": row["computed_handicap"],
        }
        if row["total_putts"]:
            r["total_putts"] = row["total_putts"]
        result.append(r)
    return result


def save_round(golf_round, date, index, user_id: int = 1) -> None:
    db = get_db()
    total_putts = None
    holes = golf_round.get("holes", {})
    if holes:
        total_putts = sum(
            int(h.get("putts", 0) or 0)
            for h in holes.values()
        )
    db.execute(
        """INSERT INTO rounds
           (user_id, course_name, date, round_index, tee_name, holes_played,
            entry_mode, holes, total_gross, total_putts, differential, notes, excluded, computed_handicap)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            golf_round.get("course", ""),
            date,
            index,
            golf_round.get("tees", ""),
            golf_round.get("holes_played", ""),
            golf_round.get("entry_mode", ""),
            json.dumps(golf_round.get("holes", {})),
            golf_round.get("total_gross", ""),
            str(total_putts) if total_putts else None,
            golf_round.get("differential", ""),
            golf_round.get("notes", ""),
            1 if golf_round.get("excluded") else 0,
            golf_round.get("computed_handicap", ""),
        ),
    )
    db.commit()
    db.close()
    _log.info("round saved: %s #%s course=%s", date, index, golf_round.get("course", "?"))


def delete_round(date: str, index: str, user_id: int = 1) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM rounds WHERE user_id = ? AND date = ? AND round_index = ?",
        (user_id, date, int(index)),
    )
    db.commit()
    db.close()
    _log.info("round deleted: %s #%s", date, index)


def get_slope_rating(tee_data: dict, holes_sel: str) -> tuple[float, float]:
    if holes_sel == "front":
        slope  = float(tee_data.get("front_slope",  tee_data.get("slope",  113)))
        rating = float(tee_data.get("front_rating", tee_data.get("rating", 72.0)))
    elif holes_sel == "back":
        slope  = float(tee_data.get("back_slope",  tee_data.get("slope",  113)))
        rating = float(tee_data.get("back_rating", tee_data.get("rating", 72.0)))
    else:
        slope  = float(tee_data.get("slope",  113))
        rating = float(tee_data.get("rating", 72.0))
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
    rows = db.execute("SELECT id, username, display_name FROM users").fetchall()
    db.close()
    return [{"id": r["id"], "username": r["username"], "display_name": r["display_name"]} for r in rows]
```

- [ ] **Step 4: Verify compilation**

```
python -m py_compile source/database.py source/store.py
```
Expected: no output (success).

---

### Task A2: Update main.py — wire SQLite backend

**Files:**
- Modify: `source/main.py` (imports, `@app.before_request`, `main()`)

- [ ] **Step 1: Update imports in main.py**

At the top of `source/main.py`, change the import block from store (lines 14-21) — add `set_db_path, init_db` from database, remove `init_data_dir` (replaced by init_db), update store function calls for `user_id` defaults:

```python
from database import set_db_path, init_db
from store import (
    load_settings, save_settings,
    get_courses, get_all_rounds, get_slope_rating,
    save_round, delete_round, save_course, delete_course, rename_course,
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_handicap_benchmarks,
)
```

Remove `init_data_dir` from the existing import line (it was on line 15 of the old file).

- [ ] **Step 2: Update `@app.before_request`**

The current `_load_globals()` sets `g.settings`, `g.courses`, `g.all_rounds`. These calls don't change signature — store functions use `user_id=1` defaults. No changes needed to the function body.

- [ ] **Step 3: Add `--data` flag and update `main()`**

Add an `argparse` block for `--host`, `--port`, and `--data` before `main()`. Update `main()` to call `set_db_path` and `init_db()` instead of `init_data_dir()`.

At the top of `main()` (around line 957), change:
```python
def main():
    init_data_dir()
```
to:
```python
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data", default=None)
    args = parser.parse_args()

    if args.data:
        data_dir = Path(args.data)
    else:
        data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = str(data_dir / "pinsheet.db")
    set_db_path(db_path)
    init_db()
```

Also update `serve()` to use `args.host` and `args.port`:
```python
    from waitress import serve
    print(f"PinSheet -> http://{args.host}:{port}")
    serve(app, host=args.host, port=port)
```

The `find_free_port()` call should only run if `args.port` is None:
```python
    port = args.port if args.port else find_free_port()
```

Wrap Chrome launch in a check — skip if `args.host != "127.0.0.1"` (production mode) or if `FLASK_ENV` is "production":
```python
    chrome_proc = None
    if args.host == "127.0.0.1" and os.environ.get("FLASK_ENV") != "production":
        chrome = _find_chrome()
        if chrome:
            chrome_proc = subprocess.Popen(
                [chrome, f"--app={url}", "--start-maximized"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open(url)
```

- [ ] **Step 4: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 5: Commit**

```bash
git add source/database.py source/store.py source/main.py
git commit -m "feat: rewrite store layer from JSON to SQLite"
```

---

### Task A3: Add JSON import page

**Files:**
- Modify: `source/main.py` (add `/settings/import` route and POST handler)
- Create: `source/web/templates/settings_import.html`

- [ ] **Step 1: Add import routes to main.py**

After the existing `/settings` route (around line 856), add:

```python
@app.route("/settings/import")
def settings_import():
    return render_template("settings_import.html", settings=g.settings, imported=None)


@app.route("/settings/import", methods=["POST"])
def settings_import_post():
    uploaded = request.files.get("zipfile")
    if not uploaded:
        return render_template("settings_import.html", settings=g.settings, imported=None, error="No file provided")

    import zipfile, io

    try:
        zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
    except zipfile.BadZipFile:
        return render_template("settings_import.html", settings=g.settings, imported=None, error="Invalid zip file")

    user_id = 1  # Phase A: default user
    courses_count = 0
    rounds_count = 0

    for name in zf.namelist():
        if name.endswith("courses.json"):
            courses_data = json.loads(zf.read(name))
            for cname, cdata in courses_data.items():
                save_course(cdata, cname)
                courses_count += 1
        elif "rounds/" in name and name.endswith(".json"):
            year_data = json.loads(zf.read(name))
            for date_str, date_rounds in year_data.items():
                for idx, rdata in date_rounds.items():
                    save_round(rdata, date_str, int(idx), user_id)
                    rounds_count += 1
        elif name.endswith("settings.json"):
            settings_data = json.loads(zf.read(name))
            save_settings(settings_data, user_id)

    return render_template("settings_import.html", settings=g.settings,
                           imported={"courses": courses_count, "rounds": rounds_count})
```

- [ ] **Step 2: Create `source/web/templates/settings_import.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="ps-topbar">
    <div>
        <div class="ps-eyebrow">Settings</div>
        <h1 class="ps-headline">Import Data</h1>
    </div>
</div>

<div class="ps-card" style="margin-top: 24px; max-width: 580px;">
    <div style="padding: 24px;">
        <p style="color: var(--ps-ink-2); margin-bottom: 16px; line-height: 1.5;">
            Upload a zip file of your old PinSheet data directory (containing
            <code>courses.json</code>, <code>rounds/</code>, and
            <code>settings.json</code>).
        </p>

        {% if imported %}
        <div style="background: var(--ps-mint-1); border: 1px solid var(--ps-accent); padding: 16px; margin-bottom: 16px;">
            <p style="color: var(--ps-accent); margin: 0; font-weight: 500;">
                Imported {{ imported.courses }} courses and {{ imported.rounds }} rounds.
            </p>
        </div>
        {% endif %}

        {% if error %}
        <div style="background: rgba(204, 51, 0, 0.08); border: 1px solid #c30; padding: 16px; margin-bottom: 16px;">
            <p style="color: #c30; margin: 0; font-weight: 500;">{{ error }}</p>
        </div>
        {% endif %}

        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="zipfile" accept=".zip" style="margin-bottom: 16px;">
            <br>
            <button type="submit" class="btn-accent">Import</button>
        </form>

        <p style="color: var(--ps-ink-3); font-size: 12px; margin-top: 24px;">
            <a href="/settings" style="color: var(--ps-ink-3);">Back to Settings</a>
        </p>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add source/main.py source/web/templates/settings_import.html
git commit -m "feat: add JSON import page at /settings/import"
```

---

### Task A4: Create systemd service and launcher updates

**Files:**
- Create: `scripts/pinsheet.service`
- Create: `scripts/install-service.sh`
- Modify: `scripts/launchers/launch.sh`
- Modify: `scripts/launchers/launch.bat`

- [ ] **Step 1: Create `scripts/pinsheet.service`**

```ini
[Unit]
Description=PinSheet Modern
After=network.target

[Service]
Type=simple
User=pinsheet
WorkingDirectory=/opt/pinsheet
Environment=SECRET_KEY=REPLACE_ME
Environment=FLASK_ENV=production
ExecStart=/opt/pinsheet/.venv/bin/python source/main.py --host 127.0.0.1 --port 8080
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create `scripts/install-service.sh`**

```bash
#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cp "$SCRIPT_DIR/pinsheet.service" /etc/systemd/system/pinsheet.service
echo "Installed pinsheet.service. Edit /etc/systemd/system/pinsheet.service to set SECRET_KEY."
echo "Then run: systemctl daemon-reload && systemctl enable --now pinsheet"
```

```bash
chmod +x scripts/install-service.sh
```

- [ ] **Step 3: Update `scripts/launchers/launch.sh`** — add SECRET_KEY if not set

At line 17 (before the `python` invocation), add:

```bash
if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY="dev-key-$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
    echo "Generated SECRET_KEY for development: $SECRET_KEY"
fi
```

- [ ] **Step 4: Update `scripts/launchers/launch.bat`** — add SECRET_KEY if not set

At the equivalent position (before `python` invocation), add:

```batch
if "%SECRET_KEY%"=="" (
    python -c "import secrets; print(secrets.token_hex(16))" > %TEMP%\psk.txt
    set /p SECRET_KEY=<%TEMP%\psk.txt
    del %TEMP%\psk.txt
)
```

- [ ] **Step 5: Commit**

```bash
git add scripts/pinsheet.service scripts/install-service.sh scripts/launchers/launch.sh scripts/launchers/launch.bat
git commit -m "feat: add systemd service, install helper, launcher SECRET_KEY setup"
```

---

### Task A5: Phase A smoke test

- [ ] **Step 1: Run the app and verify dashboard renders**

```bash
python source/main.py
```
Open `http://127.0.0.1:8420`. Verify:
- Dashboard loads with no rounds (empty state)
- "Player" shown in sidebar
- All nav links work (`/courses`, `/stats`, `/season`, `/settings`)
- `/settings/import` shows the upload form
- No console errors in browser dev tools

- [ ] **Step 2: Import test data**

Create a zip of the old `data/` directory (if available) and upload at `/settings/import`. Verify:
- Success message shows imported counts
- Dashboard shows imported rounds
- Stats page populates with data

- [ ] **Step 3: Commit (if any fixes needed)**

```bash
git commit -m "chore: Phase A smoke test fixes"
```

---

## Phase B: Auth Layer

### Task B1: Add auth dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update `requirements.txt`**

Add to the existing 2-line file:

```
flask>=3.0
waitress>=2.0
bcrypt>=4.0
flask-login>=0.6
flask-limiter>=3.0
flask-wtf>=1.2
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add auth dependencies (bcrypt, flask-login, flask-limiter, flask-wtf)"
```

---

### Task B2: Add user/invite functions to store.py

**Files:**
- Modify: `source/store.py` (add auth functions)
- Modify: `source/database.py` (add invite_codes table)

- [ ] **Step 1: Add `invite_codes` table to `init_db()`**

In `source/database.py`, inside `init_db()`, add after the existing tables:

```python
        CREATE TABLE IF NOT EXISTS invite_codes (
            code        TEXT PRIMARY KEY,
            created_by  INTEGER REFERENCES users(id),
            used_by     INTEGER REFERENCES users(id),
            created_at  TEXT DEFAULT (datetime('now')),
            used_at     TEXT
        );
```

- [ ] **Step 2: Add auth functions to `source/store.py`**

Append to `store.py`:

```python
import bcrypt
import secrets
import string


def get_user(username: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    db.close()
    if row:
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "password_hash": row["password_hash"], "is_admin": bool(row["is_admin"])}
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
    is_admin = 0
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        is_admin = 1
    cur = db.execute(
        "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        (username, display_name, password_hash, is_admin),
    )
    db.commit()
    user_id = cur.lastrowid
    db.close()
    return {"id": user_id, "username": username, "display_name": display_name, "is_admin": bool(is_admin)}


def verify_user(username: str, password: str) -> dict | None:
    user = get_user(username)
    if not user or not user["password_hash"]:
        return None
    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return user
    return None


def user_count() -> int:
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db.close()
    return count


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
    row = db.execute(
        "SELECT 1 FROM invite_codes WHERE code = ? AND used_by IS NULL",
        (code,),
    ).fetchone()
    if not row:
        db.close()
        return False
    db.execute(
        "UPDATE invite_codes SET used_by = ?, used_at = datetime('now') WHERE code = ?",
        (used_by, code),
    )
    db.commit()
    db.close()
    return True


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
```

- [ ] **Step 3: Verify compilation**

```
python -m py_compile source/database.py source/store.py
```
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add source/database.py source/store.py
git commit -m "feat: add user auth and invite code functions to store layer"
```

---

### Task B3: Flask-Login setup + User class + SECRET_KEY enforcement

**Files:**
- Modify: `source/main.py` (add Flask-Login, SECRET_KEY enforcement, User class)

- [ ] **Step 1: Add `get_user_by_id` to store imports**

In the existing store import block in main.py, add `get_user_by_id` to the list:

```python
from store import (
    load_settings, save_settings,
    get_courses, get_all_rounds, get_slope_rating,
    save_round, delete_round, save_course, delete_course, rename_course,
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_handicap_benchmarks, get_user_by_id,
)
```

- [ ] **Step 2: Add imports and Flask-Login initialization to main.py**

After line 80 (`app = Flask(...)`), add:

```python
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.session_protection = "strong"

app.config["REMEMBER_COOKIE_SECURE"] = True
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_DURATION"] = 30 * 24 * 60 * 60  # 30 days


class User:
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.display_name = user_dict["display_name"]
        self.is_admin = user_dict.get("is_admin", False)
        self._authenticated = True

    @property
    def is_authenticated(self):
        return self._authenticated

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def _load_user(user_id):
    user_dict = get_user_by_id(int(user_id))
    return User(user_dict) if user_dict else None
```

- [ ] **Step 3: Add SECRET_KEY enforcement in `main()`**

In the `main()` function, before `init_db()`, add:

```python
    secret_key = os.environ.get("SECRET_KEY", "")
    default_keys = ("REPLACE_ME", "dev-key-", "change-me", "secret")
    if not secret_key or secret_key == "":
        print("ERROR: SECRET_KEY environment variable is required.", file=sys.stderr)
        print("Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"", file=sys.stderr)
        sys.exit(1)
    if any(secret_key.startswith(dk) for dk in default_keys):
        print("ERROR: SECRET_KEY must not be a default/placeholder value.", file=sys.stderr)
        sys.exit(1)
    app.secret_key = secret_key
```

- [ ] **Step 4: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

Test that it rejects missing SECRET_KEY:
```bash
SECRET_KEY="" python source/main.py 2>&1 | head -1
```
Expected: "ERROR: SECRET_KEY environment variable is required."

- [ ] **Step 5: Commit**

```bash
git add source/main.py
git commit -m "feat: add Flask-Login setup, User class, SECRET_KEY enforcement"
```

---

### Task B4: Add auth routes (login, register, logout) + rate limiting

**Files:**
- Modify: `source/main.py` (add auth routes)

- [ ] **Step 1: Add Flask-Limiter and Flask-WTF initialization**

After the Flask-Login setup (after the `_load_user` function), add:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

limiter = Limiter(get_remote_address, app=app, default_limits=[])
csrf = CSRFProtect(app)
```

- [ ] **Step 2: Add new imports at top of main.py**

Add to the existing `from flask import ...` line:

```python
from flask import Flask, render_template, jsonify, request, redirect, url_for, g, flash
```

Add after the store imports:

```python
from store import (
    load_settings, save_settings,
    get_courses, get_all_rounds, get_slope_rating,
    save_round, delete_round, save_course, delete_course, rename_course,
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_handicap_benchmarks, get_user_by_id, get_users,
    create_user, verify_user, user_count,
    create_invite_code, is_invite_code_valid, consume_invite_code, get_invite_codes,
)
```

- [ ] **Step 3: Add auth routes**

After the `_load_user` function, add before the `@app.route("/")` line:

```python
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user_dict = verify_user(username, password)
        if user_dict:
            user = User(user_dict)
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html", error=None)


@app.route("/register", methods=["GET", "POST"])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    invite_code = request.args.get("code", "")
    first_run = user_count() == 0

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        code = request.form.get("code", "").strip().upper()

        errors = []
        if len(username) < 3 or len(username) > 30 or not all(c.isalnum() or c == "_" for c in username):
            errors.append("Username must be 3-30 characters (letters, numbers, underscores).")
        if not display_name or len(display_name) > 50:
            errors.append("Display name is required (max 50 characters).")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if get_user(username):
            errors.append("Username is already taken.")

        if not first_run:
            if not code or not is_invite_code_valid(code):
                errors.append("Invalid or expired invite code.")

        if errors:
            return render_template("register.html", errors=errors, code=code, first_run=first_run)

        user_dict = create_user(username, display_name, password)
        if not first_run:
            consume_invite_code(code, user_dict["id"])

        user = User(user_dict)
        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("register.html", errors=None, code=invite_code, first_run=first_run)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login_page"))
```

- [ ] **Step 4: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 5: Commit**

```bash
git add source/main.py
git commit -m "feat: add login, register, logout routes with rate limiting and CSRF"
```

---

### Task B5: Create auth templates and CSS

**Files:**
- Create: `source/web/templates/auth_base.html`
- Create: `source/web/templates/login.html`
- Create: `source/web/templates/register.html`
- Create: `source/web/static/auth.css`

- [ ] **Step 1: Create `source/web/templates/auth_base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PinSheet — {% block title %}Login{% endblock %}</title>
    <link rel="stylesheet" href="/static/app.css">
    <link rel="stylesheet" href="/static/auth.css">
</head>
<body class="ps-dark">
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-logo">PinSheet</div>
            {% block auth_content %}{% endblock %}
        </div>
    </div>
</body>
</html>
```

- [ ] **Step 2: Create `source/web/templates/login.html`**

```html
{% extends "auth_base.html" %}
{% block title %}Login{% endblock %}
{% block auth_content %}
<h2 class="auth-heading">Sign In</h2>

{% if error %}
<div class="auth-error">{{ error }}</div>
{% endif %}

<form method="POST" class="auth-form">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="auth-field">
        <label for="username">Username</label>
        <input type="text" id="username" name="username" required autocomplete="username" autofocus>
    </div>
    <div class="auth-field">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" required autocomplete="current-password">
    </div>
    <div class="auth-field" style="flex-direction: row; align-items: center; gap: 8px;">
        <input type="checkbox" id="remember" name="remember" style="width: auto;">
        <label for="remember" style="margin: 0;">Remember me</label>
    </div>
    <button type="submit" class="auth-button">Sign In</button>
</form>

<p class="auth-footer">
    Don't have an account? <a href="{{ url_for('register_page') }}">Register</a>
</p>
{% endblock %}
```

- [ ] **Step 3: Create `source/web/templates/register.html`**

```html
{% extends "auth_base.html" %}
{% block title %}Register{% endblock %}
{% block auth_content %}
<h2 class="auth-heading">Create Account</h2>

{% if errors %}
<div class="auth-error">
    {% for e in errors %}<p style="margin: 0 0 4px;">{{ e }}</p>{% endfor %}
</div>
{% endif %}

<form method="POST" class="auth-form">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="auth-field">
        <label for="username">Username</label>
        <input type="text" id="username" name="username" required autocomplete="username" autofocus>
    </div>
    <div class="auth-field">
        <label for="display_name">Display Name</label>
        <input type="text" id="display_name" name="display_name" required>
    </div>
    <div class="auth-field">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" required minlength="8">
    </div>
    <div class="auth-field">
        <label for="confirm">Confirm Password</label>
        <input type="password" id="confirm" name="confirm" required minlength="8">
    </div>
    {% if not first_run %}
    <div class="auth-field">
        <label for="code">Invite Code</label>
        <input type="text" id="code" name="code" value="{{ code }}" required placeholder="PS-XXXX-XXXX">
    </div>
    {% endif %}
    <button type="submit" class="auth-button">Create Account</button>
</form>

<p class="auth-footer">
    Already have an account? <a href="{{ url_for('login_page') }}">Sign In</a>
</p>
{% endblock %}
```

- [ ] **Step 4: Create `source/web/static/auth.css`**

```css
.auth-container {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 40px;
}

.auth-card {
    width: 100%;
    max-width: 400px;
    border: 1px solid var(--ps-ink-1);
    padding: 40px;
}

.auth-logo {
    font-family: 'JetBrains Mono', monospace;
    font-size: 24px;
    font-weight: 600;
    color: var(--ps-ink);
    margin-bottom: 32px;
    text-align: center;
    letter-spacing: -0.02em;
}

.auth-logo::after {
    content: '.';
    color: var(--ps-accent);
}

.auth-heading {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 500;
    color: var(--ps-ink-2);
    margin-bottom: 24px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.auth-error {
    background: rgba(204, 51, 0, 0.08);
    border: 1px solid #c30;
    padding: 12px 16px;
    margin-bottom: 20px;
    color: #c30;
    font-size: 12px;
}

.auth-form {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.auth-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.auth-field label {
    font-size: 10px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: var(--ps-ink-3);
}

.auth-field input[type="text"],
.auth-field input[type="password"] {
    background: var(--ps-ink-0);
    border: 1px solid var(--ps-ink-1);
    color: var(--ps-ink);
    padding: 8px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    outline: none;
}

.auth-field input:focus {
    border-color: var(--ps-accent);
}

.auth-button {
    margin-top: 8px;
    background: var(--ps-accent);
    color: #0a0a0a;
    border: none;
    padding: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
}

.auth-button:hover {
    opacity: 0.9;
}

.auth-footer {
    margin-top: 24px;
    text-align: center;
    font-size: 12px;
    color: var(--ps-ink-3);
}

.auth-footer a {
    color: var(--ps-accent);
    text-decoration: none;
}

.auth-footer a:hover {
    text-decoration: underline;
}
```

- [ ] **Step 5: Commit**

```bash
git add source/web/templates/auth_base.html source/web/templates/login.html source/web/templates/register.html source/web/static/auth.css
git commit -m "feat: add auth templates (login, register) and auth CSS"
```

---

### Task B6: Apply @login_required to all routes

**Files:**
- Modify: `source/main.py` (add decorator to all page routes)

- [ ] **Step 1: Add `@login_required` decorator**

Add `@login_required` above every page route handler. The auth routes (`login_page`, `register_page`) and static files are excluded. Also add the `@limiter.limit` decorator to login/register.

Update login route signature:
```python
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login_page():
```

Update register route signature:
```python
@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register_page():
```

All other page routes get:
```python
@app.route("/")
@login_required
def dashboard():
```

Apply to every route handler: `dashboard`, `round_entry`, `api_draft_round_get`, `api_draft_round_put`, `api_draft_round_delete`, `api_draft_course_get`, `api_draft_course_put`, `api_draft_course_delete`, `api_rounds_post`, `round_detail`, `report_card`, `api_rounds_delete`, `course_entry`, `course_list`, `course_detail`, `api_courses_post`, `api_courses_delete`, `stats`, `settings_page`, `api_settings_put`, `season_summary`, `player_profile`, `settings_import`, `settings_import_post`.

- [ ] **Step 2: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add source/main.py
git commit -m "feat: add @login_required to all routes"
```

---

### Task B7: Phase B smoke test

- [ ] **Step 1: Run the app with a SECRET_KEY**

```bash
SECRET_KEY="smoke-test-key-$(python3 -c 'import secrets; print(secrets.token_hex(16))')" python source/main.py
```

- [ ] **Step 2: Test first-run registration**

Open `http://127.0.0.1:8420`. Verify:
- Redirected to `/register` (no invite code field visible since first_run=True)
- Register with username `admin`, display name `Admin`, password `password123`
- Redirected to dashboard on success
- Sidebar shows "Admin" as player name, not "Golfer"

- [ ] **Step 3: Test logout and re-login**

Visit `/logout`, verify redirected to `/login`. Log back in with the credentials from step 2.

- [ ] **Step 4: Test registration with invite code (gated)**

Log out. Visit `/register` as a new user. Verify:
- Invite code field is visible and required
- Submitting without a code shows error
- Valid invite code allows registration (generate one first from admin — Phase C)

- [ ] **Step 5: Commit (if any fixes needed)**

```bash
git commit -m "chore: Phase B smoke test fixes"
```

---

## Phase C: Multi-User UI

### Task C1: Add `?user=` view param to `@app.before_request`

**Files:**
- Modify: `source/main.py` (update `_load_globals`)

- [ ] **Step 1: Update `@app.before_request` to handle `?user=`**

Replace the existing `_load_globals()` function:

```python
@app.before_request
def _load_globals():
    if request.endpoint in ("login_page", "register_page", "static"):
        return

    current_user_id = current_user.id if current_user.is_authenticated else 1

    view_username = request.args.get("user")
    if view_username:
        view_user_dict = get_user(view_username)
        if view_user_dict:
            g.view_user = view_user_dict
        else:
            g.view_user = None
    else:
        if current_user.is_authenticated:
            g.view_user = get_user_by_id(current_user_id)
        else:
            g.view_user = {"id": 1, "username": "default", "display_name": "Player", "is_admin": False}

    if g.view_user is None:
        g.view_user = {"id": 1, "username": "default", "display_name": "Player", "is_admin": False}

    g.settings = load_settings(g.view_user["id"])
    g.courses = get_courses()
    g.all_rounds = get_all_rounds(g.view_user["id"])
```

- [ ] **Step 2: Add `is_viewing_own_data()` helper**

After `_load_globals()`, add:

```python
@app.before_request
def _check_view_permission():
    if request.endpoint in ("login_page", "register_page", "static"):
        return
    if not hasattr(g, "view_user"):
        return
    g.is_own_data = current_user.is_authenticated and g.view_user["id"] == current_user.id
```

- [ ] **Step 3: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add source/main.py
git commit -m "feat: add ?user= view param and is_own_data helper"
```

---

### Task C2: Add user switcher to base.html

**Files:**
- Modify: `source/web/templates/base.html`

- [ ] **Step 1: Add user switcher dropdown to sidebar**

In `base.html`, replace the player info block (lines 13-17) with:

```html
            <div>
                <div class="ps-eyebrow" style="margin-bottom: 6px;">Viewing</div>
                <div class="ps-serif" style="font-size: 20px; line-height: 1.1;">{{ g.view_user.display_name }}</div>
                <div style="position: relative; margin-top: 4px;">
                    <select id="user-switcher"
                            style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--ps-ink-3);
                                   background: transparent; border: 1px solid var(--ps-ink-1); padding: 4px 6px;
                                   width: 100%; outline: none; cursor: pointer;"
                            onchange="switchUser(this.value)">
                        {% for u in all_users %}
                        <option value="{{ u.username }}" {% if u.id == g.view_user.id %}selected{% endif %}>
                            {{ u.display_name }}
                        </option>
                        {% endfor %}
                    </select>
                </div>
            </div>
```

At the bottom of `base.html`, before `</body>`, add the user-switcher JS:

```html
    <script>
        document.getElementById('user-switcher').addEventListener('change', function() {
            var user = this.value;
            var url = new URL(window.location.href);
            url.searchParams.set('user', user);
            window.location.href = url.toString();
        });
    </script>
```

- [ ] **Step 2: Update `render_template` calls to pass `all_users`**

In every route handler that renders a template, add `all_users=get_users()` to the `render_template` call. For example, in `dashboard()`:

```python
    return render_template("dashboard.html", panels=panels, rounds=rounds_data,
                           last_year_hi=last_year_hi, settings=g.settings,
                           current_page="dashboard",
                           season_label=season_label,
                           hi_movement=hi_movement, career_low=career_low, hi_insight=hi_insight,
                           chart=chart, chart_data_json=chart_data_json,
                           all_users=get_users())
```

The following route handlers need `all_users=get_users()` added to their render_template calls: `dashboard`, `round_entry`, `round_detail`, `report_card`, `course_entry`, `course_list`, `course_detail`, `stats`, `settings_page`, `season_summary`, `player_profile`, `settings_import`, `settings_import_post`.

- [ ] **Step 3: Also add `logout` link to sidebar navigation**

After the Settings nav link (line 27 of base.html), add:

```html
                <a href="/logout">Logout</a>
```

- [ ] **Step 4: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 5: Commit**

```bash
git add source/main.py source/web/templates/base.html
git commit -m "feat: add user switcher dropdown and logout link"
```

---

### Task C3: Add admin invites page

**Files:**
- Modify: `source/main.py` (add `/admin/invites` route)
- Create: `source/web/templates/admin_invites.html`

- [ ] **Step 1: Add admin routes to main.py**

After the existing routes, add:

```python
@app.route("/admin/invites", methods=["GET", "POST"])
@login_required
def admin_invites():
    if not current_user.is_admin:
        return "Forbidden", 403

    if request.method == "POST":
        code = create_invite_code(current_user.id)
        base_url = request.host_url.rstrip("/")
        return render_template("admin_invites.html", settings=g.settings,
                               codes=get_invite_codes(), new_code=code, base_url=base_url,
                               all_users=get_users())

    return render_template("admin_invites.html", settings=g.settings,
                           codes=get_invite_codes(), new_code=None, base_url=None,
                           all_users=get_users())
```

- [ ] **Step 2: Create `source/web/templates/admin_invites.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="ps-topbar">
    <div>
        <div class="ps-eyebrow">Admin</div>
        <h1 class="ps-headline">Invite Codes</h1>
    </div>
</div>

{% if new_code %}
<div class="ps-card" style="margin-top: 24px; max-width: 580px;">
    <div style="padding: 24px; background: var(--ps-mint-1); border: 1px solid var(--ps-accent);">
        <p style="color: var(--ps-accent); font-weight: 500; margin: 0 0 8px;">New Invite Code Generated</p>
        <p style="font-size: 24px; font-weight: 600; margin: 0 0 8px; font-family: 'JetBrains Mono', monospace;">{{ new_code }}</p>
        <p style="color: var(--ps-ink-2); font-size: 12px; margin: 0;">
            Registration link:
            <code style="color: var(--ps-accent); user-select: all;">{{ base_url }}/register?code={{ new_code }}</code>
        </p>
    </div>
</div>
{% endif %}

<div class="ps-card" style="margin-top: 24px;">
    <div style="padding: 24px;">
        <form method="POST" style="margin-bottom: 24px;">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button type="submit" class="btn-accent">Generate New Code</button>
        </form>

        <table class="data-table">
            <thead>
                <tr>
                    <th>Code</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Used By</th>
                    <th>Used At</th>
                </tr>
            </thead>
            <tbody>
                {% for c in codes %}
                <tr>
                    <td style="font-family: 'JetBrains Mono', monospace;">{{ c.code }}</td>
                    <td>{{ 'Used' if c.used_by else 'Available' }}</td>
                    <td>{{ c.created_at[:10] if c.created_at else '--' }}</td>
                    <td>{{ c.user_name or '--' }}</td>
                    <td>{{ c.used_at[:10] if c.used_at else '--' }}</td>
                </tr>
                {% endfor %}
                {% if not codes %}
                <tr><td colspan="5" style="color: var(--ps-ink-3); font-style: italic;">No invite codes yet.</td></tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Add admin link to sidebar (admin-only)**

In `base.html`, after the logout link, add:

```html
                {% if current_user.is_admin %}<a href="/admin/invites">Admin</a>{% endif %}
```

- [ ] **Step 4: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 5: Commit**

```bash
git add source/main.py source/web/templates/admin_invites.html source/web/templates/base.html
git commit -m "feat: add admin invites page and admin nav link"
```

---

### Task C4: Add read-only enforcement for viewing others' data

**Files:**
- Modify: `source/main.py` (add write-route guards)
- Modify: `source/web/templates/base.html` (conditionally hide write UI)

- [ ] **Step 1: Add write-route guards**

Add a decorator `@requires_own_data` that checks `g.is_own_data` and returns 403 if false:

```python
from functools import wraps

# CSRF exemption for JSON API routes (Flask-WTF auto-skips application/json requests)
# All /api/* POST/PUT/DELETE routes send JSON, so they are automatically CSRF-exempt.

def requires_own_data(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.is_own_data:
            return "Forbidden", 403
        return f(*args, **kwargs)
    return decorated
```

Apply to: `api_rounds_post`, `api_rounds_delete`, `api_courses_post`, `api_courses_delete`, `api_settings_put`, `api_welcome_done`, `api_draft_round_put`, `api_draft_round_delete`, `api_draft_course_put`, `api_draft_course_delete`, `settings_import_post`.

- [ ] **Step 2: Add `g.is_own_data` to templates**

In `base.html`, the sidebar already shows `{{ g.view_user.display_name }}`. Add a conditional block around the "+ Log Round" button in `dashboard.html` (if applicable) and hide delete buttons when viewing others. In `round_detail.html`, wrap the delete button in:

```html
{% if g.is_own_data %}
<button onclick="deleteRound('{{ round.date }}', '{{ round.index }}')" class="btn-danger">Delete</button>
{% endif %}
```

In `course_detail.html`, wrap the delete button similarly. In `round_entry.html` and `course_entry.html`, deny access if `g.is_own_data` is false (these are always current-user actions):

In the route handlers for `round_entry` and `course_entry`, add at the top:
```python
    if not g.is_own_data:
        return "You can only enter data for yourself.", 403
```

- [ ] **Step 3: Verify compilation**

```
python -m py_compile source/main.py
```
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add source/main.py source/web/templates/base.html source/web/templates/round_detail.html source/web/templates/course_detail.html
git commit -m "feat: add read-only enforcement when viewing other users' data"
```

---

### Task C5: Phase C smoke test

- [ ] **Step 1: Run the app with SECRET_KEY**

```bash
SECRET_KEY="test-$(python3 -c 'import secrets; print(secrets.token_hex(16))')" python source/main.py
```

- [ ] **Step 2: Test full multi-user flow**

1. First user registers (auto-admin). Dashboard loads with "Admin" in sidebar.
2. Visit `/admin/invites`, generate an invite code.
3. Copy the registration link, open in incognito, register a second user.
4. Log in as admin. Use user switcher to view the second user's profile.
5. Verify: dashboard URL now has `?user=newuser`, stats and courses reflect that user's data.
6. Verify: cannot save/delete when viewing other user (UI elements hidden, POST returns 403).
7. Verify: user switcher shows both users.

- [ ] **Step 3: Commit (if any fixes needed)**

```bash
git commit -m "chore: Phase C smoke test fixes"
```

---

### Task C6: Update navigation and polish

**Files:**
- Modify: `source/web/templates/base.html` (disable Goals/Bag, add Admin for admins)

- [ ] **Step 1: Finalize base.html navigation**

The nav should be (only showing admin link for admins):

```html
            <nav class="ps-nav">
                <a href="/" class="{% if current_page == 'dashboard' %}is-active{% endif %}">Dashboard</a>
                <a href="/rounds/new" class="{% if current_page == 'round_entry' %}is-active{% endif %}">Rounds</a>
                <a href="/stats" class="{% if current_page == 'stats' %}is-active{% endif %}">Stats</a>
                <a href="/profile" class="{% if current_page == 'player_profile' %}is-active{% endif %}">Profile</a>
                <a href="#" style="color: var(--ps-ink-3); cursor: default;">Goals</a>
                <a href="#" style="color: var(--ps-ink-3); cursor: default;">Bag</a>
                <a href="/courses" class="{% if current_page == 'courses' %}is-active{% endif %}">Courses</a>
                <a href="/season" class="{% if current_page == 'season' %}is-active{% endif %}">Season</a>
                <a href="/settings" class="{% if current_page == 'settings' %}is-active{% endif %}">Settings</a>
                {% if current_user.is_admin %}<a href="/admin/invites">Admin</a>{% endif %}
                <a href="/logout">Logout</a>
            </nav>
```

- [ ] **Step 2: Commit**

```bash
git add source/web/templates/base.html
git commit -m "chore: finalize navigation with admin link and logout"
```

---

## Post-Implementation

- [ ] Run `python -m py_compile` on all changed `.py` files one final time
- [ ] Run the full app with `SECRET_KEY` set and test all routes manually
- [ ] Update `docs/HANDOFF.md` with new state
- [ ] Update `docs/RUNBOOK.md` with new deployment commands (systemd, SECRET_KEY, --host/--port/--data flags)
- [ ] Update `docs/SESSION_LOG.md` with implementation summary
