# Multi-User PinSheet Modern — Design Spec

**Date**: 2026-05-26
**Status**: Approved

## Overview

Transform pinsheet-modern from a single-user local web app into a self-hosted multi-user application. One person hosts the instance (LXC/VM on a home server), friends register with invite codes, and everyone can view each other's stats. All data lives in SQLite. Clean break from JSON — no dual-backend. No Docker — plain Python process behind a reverse proxy.

## Implementation Phases

Three independent, testable, shippable phases:

| Phase | What | Deliverable |
|-------|------|-------------|
| A: SQLite migration | Rewrite `store.py` to SQLite, seed default user (id=1), JSON import page. App works identically to current. | Working app on SQLite, single-user |
| B: Auth layer | User/password/bcrypt, login/register pages, Flask-Login sessions, invite codes, `@login_required` gate. | Working app with login, still single-user-scoped |
| C: Multi-user UI | User switcher, `?user=` view param, admin invites page, read-only enforcement. | Full multi-user app |

Each phase compiles, runs, and can be smoke-tested before moving to the next.

## Schema

Four tables in `data/pinsheet.db`. SQLite (stdlib, no pip dependency). String numerics preserved. JSON text columns for nested data to avoid exploding the schema.

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,            -- bcrypt (empty string for default user in Phase A)
    is_admin      INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE invite_codes (
    code        TEXT PRIMARY KEY,           -- format: PS-XXXX-XXXX
    created_by  INTEGER REFERENCES users(id),
    used_by     INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT (datetime('now')),
    used_at     TEXT
);

CREATE TABLE courses (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    data        TEXT NOT NULL               -- JSON blob: {location, tees, holes, ...}
);

CREATE TABLE rounds (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    course_name   TEXT NOT NULL,             -- denormalized for convenience (course names are unique)
    date          TEXT NOT NULL,
    round_index   INTEGER NOT NULL DEFAULT 0,-- ordinal for same-date rounds (preserves URL scheme /rounds/{date}/{index})
    tee_name      TEXT,
    holes_played  TEXT,                     -- "all" | "front" | "back"
    entry_mode    TEXT,                     -- "detailed" | "score_only"
    holes         TEXT,                     -- JSON: {1: {gross, fir, gir, ...}, ...}
    total_gross   TEXT,
    total_putts   TEXT,
    differential  TEXT,
    notes         TEXT,
    excluded      INTEGER DEFAULT 0,
    computed_handicap TEXT,                  -- HI at time of round
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE settings (
    user_id  INTEGER PRIMARY KEY REFERENCES users(id),
    data     TEXT NOT NULL                   -- JSON: {theme, season, ...}
);
```

**Design notes**:
- Courses are global (shared).
- Rounds have `user_id` foreign keys. Queries always scoped to a user.
- `display_name` is human-readable. `username` is for login and URL slugs.
- JSON columns read/written as whole Python dicts. No `json_extract()` in normal paths.
- Single `data` blob per course — simpler store API that deserializes the full dict.
- `course_name` denormalized in rounds table so round queries don't need a course join.
- `computed_handicap` column preserved from original data model (stored per-round for historical tracking).
- Invite codes table only created in Phase B. Not present in Phase A schema.
- `round_index` preserves the original JSON storage scheme (`{date: {index: round_data}}`) for URL compatibility (`/rounds/{date}/{index}`). Computed as next ordinal for user+date on save. Import preserves the JSON index value. Gaps from deleted rounds are acceptable (no renumbering).

### Migration of existing JSON data

The `data/` directory (gitignored) contains the current single-user's data. To migrate:
1. Start Phase A app — `init_db()` creates tables and default user (id=1).
2. Open `/settings/import` in the browser.
3. Upload a zip of the old `data/` directory.
4. Server reads courses.json → upserts into courses. Reads rounds/YYYY.json → inserts into rounds (user_id=1). Reads settings.json → settings table.
5. Delete or archive old JSON directory after confirming.

## Phase A: SQLite Migration

### Store rewrite

`store.py` is rewritten from JSON file I/O to SQLite. The public API surface keeps the same signatures. No caller in `main.py` or `calc/` changes needed — only `store.py` internals change.

Key function signatures. Current store.py has 18 functions (see source code). The rewrite adds `user_id` parameters and drops functions tied to JSON file structure:

Functions kept (signature changes noted):
- `init_db()` — creates tables + default user (Phase A), invite_codes (Phase B). Replaces `init_data_dir()`.
- `get_courses()` — unchanged (result list assembled from SQLite rows + JSON deserialization)
- `get_course(name)` — unchanged
- `save_course(course_dict)` — unchanged
- `delete_course(name)` — unchanged
- `rename_course(old_name, new_name)` — unchanged (currently unused in UI but kept)
- `get_all_rounds(user_id, limit=None)` — adds `user_id` parameter. Replaces current `get_all_rounds(limit)`. Returns newest-first list across all years.
- `save_round(user_id, round_dict)` — adds `user_id`, drops separate `date`/`index` args (now fields in round_dict)
- `delete_round(user_id, date, index)` — adds `user_id`. Uses `date` + `round_index` for row matching.
- `get_slope_rating(course_name, tee_name, holes_selection)` — unchanged (reads from course JSON blob)
- `load_settings(user_id)` / `save_settings(user_id, data)` — adds `user_id` parameter
- `get_users()` — new (Phase A), used by user switcher in Phase C

Functions dropped (tied to JSON file structure):
- `get_rounds(year)` — currently unused by main.py. SQLite doesn't have per-year files; use `get_all_rounds()` with date filtering in Python when needed.
- `init_data_dir()` — replaced by `init_db()` which creates `data/` directory + SQLite database.
- `get_handicap_benchmarks()` — ported into `init_db()` or a standalone load (reads from `data/handicap_benchmarks.json`).
- `save_course_draft()` / `load_course_draft()` / `clear_course_draft()` — ported to SQLite `course_drafts` table, or kept as JSON files in `data/drafts/`. Implementation detail — not caller-visible.
- `save_round_draft()` / `load_round_draft()` / `clear_round_draft()` — same as course drafts.

### Phase A user model

`init_db()` in Phase A creates a default user (id=1, username="default", display_name="Player", password_hash="", is_admin=1). All routes use `user_id=1` hardcoded. No auth checks. The app behaves identically to current JSON-backed version.

### Import page (`/settings/import`)

- GET: renders an upload form (select zip file)
- POST: receives zip file, reads in-memory (no temp files)
- Parses `courses.json` → insert/update courses
- Parses each `rounds/YYYY.json` → insert rounds scoped to current user
- Parses `settings.json` → insert/update settings for current user
- Reports: "Imported X courses, Y rounds"
- Idempotent: courses skipped by name uniqueness, rounds insert normally (can re-import)
- File size limit: 10MB

### systemd service

Service unit file at `scripts/pinsheet.service` (alongside existing `scripts/launchers/`):

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

Helper script `scripts/install-service.sh` copies the unit file to `/etc/systemd/system/` and runs `systemctl daemon-reload`. After initial setup, `sudo systemctl restart pinsheet` picks up code changes for dev/test iterations.

Existing launchers at `scripts/launchers/launch.sh` and `scripts/launchers/launch.bat` are updated to pass the `SECRET_KEY` environment variable to the Python process.

## Phase B: Auth Layer

### Dependencies (new)

| Package | Purpose |
|---------|---------|
| `bcrypt` | Password hashing |
| `flask-login` | Session management |
| `flask-limiter` | Rate limiting |
| `flask-wtf` | CSRF protection |

### Routes added

| Route | Method | Purpose |
|---|---|---|
| `/login` | GET/POST | Login form. POST validates credentials, sets Flask-Login session, redirects to `next` or `/` |
| `/register` | GET/POST | Registration form. Open if no users exist. Otherwise requires `?code=` with valid invite |
| `/logout` | GET | Clears session, redirects to `/login` |

### Session configuration

- `SECRET_KEY` required via environment variable. App refuses to start if unset or set to default placeholder.
- Flask-Login `LoginManager` with session protection = "strong"
- Remember-me cookie: `Secure`, `HttpOnly`, `SameSite=Lax`, 30 day expiry
- Session cookie (without remember-me): browser-session lifetime

### User loader

Flask-Login `user_loader` loads user from `users` table by id. User object is a simple `User` class with `is_authenticated`, `is_active`, `is_anonymous`, `get_id()`.

### Bootstrap flow

1. App starts with empty `users` table.
2. First visitor to any page gets redirected to `/register` (no invite code required).
3. First registered user gets `is_admin=1` (auto-admin).
4. All subsequent visits to `/register` require a valid invite code in `?code=` param.
5. Admin generates invite codes from `/admin/invites` and shares the registration URL.

### Registration validation

- Username: 3-30 chars, alphanumeric + underscore, uniqueness check
- Display name: 1-50 chars, non-empty
- Password: minimum 8 chars
- Password confirmation must match
- Invite code: must be valid, unused, and matched
- On success: bcrypt hash password, consume invite code, auto-login, redirect to `/`

### Login validation

- Rate limited: 5 POST attempts/minute/IP (Flask-Limiter)
- 429 response: "Too many attempts. Try again in X seconds."
- Failed login: "Invalid username or password" (no account enumeration)
- Successful login: redirect to `request.args.get('next')` or `/`

### Authorization gate

- `@login_required` decorator on all routes except `/login`, `/register`, `/static/*`
- Unauthenticated requests → redirect to `/login?next=<original_path>`
- Admin-only routes (`/admin/invites`) checked with custom `@admin_required` decorator
- CSRF protection via Flask-WTF on all POST forms

### Store additions (Phase B)

- `create_user(username, display_name, password)` → INSERT, returns user dict
- `verify_user(username, password)` → user dict if valid, None otherwise
- `get_user(username)` → user dict or None
- `get_user_by_id(user_id)` → user dict or None
- `create_invite_code(created_by)` → code string
- `is_invite_code_valid(code)` → bool
- `consume_invite_code(code, user_id)` → bool
- `get_invite_codes()` → list of all codes with usage info
- `user_count()` → int (for first-run check)

### Templates

- `login.html` — standalone form (no nav shell), username + password, remember-me checkbox, link to `/register`
- `register.html` — standalone form, username + display_name + password + confirm password, invite code (pre-filled from `?code=`), link to `/login`

Both extend a minimal `auth_base.html` (no nav, no user context — just CSS includes and centered card layout).

## Phase C: Multi-User UI

### User switcher

In `base.html` topbar (right side):

```
Viewing: [display_name ▼]
```

Dropdown lists all registered users (from `store.get_users()`). Selecting another user reloads the current page with `?user=username` appended. Always visible (even for single-user instances).

### View parameter

A `@app.before_request` hook or helper parses `request.args.get('user')`:

- If present and valid username, sets `g.view_user` to that user's dict
- If absent, `g.view_user` = current user
- Available in all templates as `{{ g.view_user }}`
- All store calls use `g.view_user.id` (not the hardcoded `user_id=1` from Phase A)

Routes that already accept user context:
- `GET /` — dashboard (calculations scoped to viewed user)
- `GET /stats` — stats page
- `GET /courses` — course list (global, but courses are shared so no user scoping needed)
- `GET /courses/<name>` — course detail
- `GET /rounds/<date>/<index>` — round detail (scoped to viewed user's rounds)
- `GET /rounds/new` — round entry wizard (always for current user, ignoring view param)
- `GET /courses/new` — course entry wizard (always for current user)
- `GET /settings` — settings page (always for current user's settings)
- `GET /settings/import` — import page (always for current user)

### Read-only enforcement

A helper `is_viewing_own_data()` checks `g.view_user.id == current_user.id`. Write routes:
- If not own data: 403 Forbidden
- UI: hide "Save"/"Delete"/"Edit" buttons when viewing others' data
- Templates can check `{% if g.view_user.id == current_user.id %}`

### Admin page (`/admin/invites`)

- `@admin_required` decorator (checks `current_user.is_admin`)
- Table listing all invite codes: code, status (unused/used), created at, used by, used at
- "Generate" button creates a new code and shows it prominently with the full registration URL
- Copy-to-clipboard button on the registration URL

### Removed default user

Phase C removes the Phase A default user (id=1, no password). After Phase B, all users have real credentials. The auto-admin from first registration replaces it.

## Security

### We handle

- **SECRET_KEY enforcement**: app refuses to start without a strong key set in environment. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- **bcrypt**: all passwords hashed, salt per user, no plaintext storage
- **Rate limiting**: Flask-Limiter on `/login` and `/register` — 5 req/min/IP
- **Session cookies**: `Secure`, `HttpOnly`, `SameSite=Lax` flags set
- **SQL injection**: all queries use parameterized statements (SQLite `?` placeholders)
- **CSRF**: Flask-WTF CSRF tokens on all POST forms

### Host handles

- **TLS**: caddy or nginx + certbot for HTTPS
- **Firewall**: only port 443 exposed; port 8080 localhost-only
- **SECRET_KEY generation**: one-time setup step (see SECRET_KEY enforcement above); no separate script needed
- **OS updates**: standard server maintenance

### Attack surface

- Reverse proxy misconfiguration → session cookies in cleartext. Mitigation: bind `127.0.0.1` by default, document TLS requirement.
- Weak SECRET_KEY → session forgery. Mitigation: app refuses to start with default key.
- Guessed invite code → unauthorized registration. Mitigation: 8-char alphanumeric (62^8 = 2.2e14 combinations).

## Deployment

### Stack

- App server: waitress (already in requirements.txt)
- Reverse proxy: caddy or nginx
- TLS: Let's Encrypt
- Process manager: systemd

### App flags

- `--host 127.0.0.1` (default) — bind localhost
- `--port 8080` — configurable
- `--data /path/to/data` — configurable data directory (default: `data/` relative to repo)

### Environment

- `SECRET_KEY` — required (app refuses to start if unset or default placeholder)
- `FLASK_ENV` — `production` by default

## Out of Scope

- Docker deployment
- Admin transfer (stays with user id 1)
- User deletion or deactivation
- Per-stat privacy controls (all or nothing for the group)
- Cross-user stat comparison / leaderboards
- Two-factor authentication
- Email verification or password reset
- Data export UI
- 9-hole handicap differential adjustment
- CLI tools (all admin operations are web UI)
- Invite code revocation

## Dependencies (total new)

| Package | Purpose | Phase |
|---------|---------|-------|
| `bcrypt` | Password hashing | B |
| `flask-login` | Session management | B |
| `flask-limiter` | Rate limiting | B |
| `flask-wtf` | CSRF protection | B |
| `sqlite3` | Database (stdlib) | A |

## Template Files (new)

| File | Phase | Purpose |
|------|-------|---------|
| `auth_base.html` | B | Minimal shell for login/register pages (CSS + centered card) |
| `login.html` | B | Login form |
| `register.html` | B | Registration form |
| `admin_invites.html` | C | Admin invite code management |
| `settings_import.html` | A | JSON import upload page |

## Store Function Matrix

| Function | Phase | Signature | Notes |
|----------|-------|-----------|-------|
| `init_db()` | A | `-> None` | Creates tables, default user (Phase A), invite_codes table (Phase B) |
| `get_courses()` | A | `-> list[dict]` | Assembled from SQLite rows + JSON deserialization |
| `get_course(name)` | A | `-> dict \| None` | |
| `save_course(course_dict)` | A | `-> None` | Upsert by name |
| `delete_course(name)` | A | `-> None` | |
| `rename_course(old, new)` | A | `-> None` | Currently unused in UI, kept for completeness |
| `get_all_rounds(user_id, limit=None)` | A | `-> list[dict]` | Newest-first. Replaces both `get_all_rounds(limit)` and `get_rounds(year)` |
| `save_round(user_id, round_dict)` | A | `-> None` | Computes `round_index` as next ordinal for user+date |
| `delete_round(user_id, date, index)` | A | `-> None` | Matches on `date` + `round_index` |
| `get_slope_rating(course, tee, holes)` | A | `-> tuple \| None` | Reads from course JSON blob, unchanged |
| `load_settings(user_id)` | A | `-> dict` | |
| `save_settings(user_id, data)` | A | `-> None` | |
| `get_users()` | A | `-> list[dict]` | All users for topbar switcher |
| `get_user(username)` | B | `-> dict \| None` | |
| `get_user_by_id(user_id)` | B | `-> dict \| None` | For Flask-Login `user_loader` |
| `create_user(username, display, pw)` | B | `-> dict` | bcrypt hashes password internally |
| `verify_user(username, password)` | B | `-> dict \| None` | Returns user dict on success, None on failure |
| `create_invite_code(created_by)` | B | `-> str` | Format: PS-XXXX-XXXX |
| `is_invite_code_valid(code)` | B | `-> bool` | |
| `consume_invite_code(code, user_id)` | B | `-> bool` | |
| `get_invite_codes()` | B | `-> list[dict]` | |
| `user_count()` | B | `-> int` | For first-run auto-admin gate |
| `import_json_zip(zip_data, user_id)` | A | `-> dict` | Returns `{courses: N, rounds: N}` |

### Draft functions

Course/round drafts (in-progress wizard state). Current store.py uses JSON files in `data/`. Two implementation options — pick at implementation time:

- **Option 1**: Keep as JSON files in `data/drafts/<user_id>/`. Scoped per-user, minimal code change.
- **Option 2**: SQLite `drafts` table with `(user_id, draft_type)` key. Cleaner but more work.

Either approach preserves the existing API signatures: `save_course_draft(user_id, data)` / `load_course_draft(user_id)` / `clear_course_draft(user_id)` — same for round drafts. Not caller-visible.

`get_handicap_benchmarks()` is ported to read `data/handicap_benchmarks.json` (a static lookup table, not user data). No user_id needed.

`get_slope_rating()` keeps its current signature but reads from the course JSON blob rather than the tee_data dict passed in — same result, simpler call site.
