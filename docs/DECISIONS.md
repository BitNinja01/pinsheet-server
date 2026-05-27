# Decisions

Durable architectural and design decisions. Appended chronologically; each entry records the *why*.

---

## 2026-05-15 — Flask + waitress over FastAPI + uvicorn

Flask was chosen over FastAPI for the web backend. Key reasons:
- **Fewer dependencies**: flask + waitress vs fastapi + uvicorn + pydantic + starlette
- **Simpler mental model**: Flask's request/response pattern maps directly to server-rendered HTML
- **No async needed**: Single-user local app, no concurrent request handling requirements
- **Jinja2 built in**: Flask uses Jinja2 by default; FastAPI requires separate jinja2 setup

Waitress was chosen over Flask's built-in Werkzeug dev server because Werkzeug prints an unsilenceable `WARNING: This is a development server...` banner on every launch — the same class of problem as the Lorca banner warnings in the abandoned pinsheet-go.

---

## 2026-05-15 — Data format unchanged

The JSON data format is identical to the original Python pinsheet. This is a drop-in replacement — users can copy their `data/` directory from the TUI version and everything works. Same file structure, same string-stored numerics, same key names. No migration needed.

---

## 2026-05-15 — Calc functions ported 1:1

All `calc_*` functions were ported directly from the original Python codebase without redesign. Same formulas, same edge cases, same return types. This ensures the handicap index and all derived stats produce identical values to the TUI version when given the same input data.

---

## 2026-05-15 — Theme colors in CSS custom properties

Themes are implemented as CSS custom properties rather than Python side. The active theme name from `settings.json` is applied as a class on `<body>` (`theme-{name}`). CSS uses `:root` defaults for dark theme with accent color overrides per theme. This keeps theme logic in the presentation layer where it belongs.

---

## 2026-05-15 — Distribution model

Same launcher-script pattern as the original pinsheet:
- `launch.sh` for Linux/macOS, `launch.bat` for Windows
- Scripts create a `.venv`, install dependencies, launch the app
- No PyInstaller (fragile, requires per-platform compilation)
- No pip package (requires Python infrastructure)
- `webbrowser.open()` handles browser launch across all 3 platforms

The Flask/waitress server stays alive in the terminal — user Ctrl+C to exit. The browser becomes the UI surface.

---

## 2026-05-27 — Multi-user: SQLite clean break

Moving to a multi-user model required a database. Key decisions:

- **Clean break from JSON**: No dual-backend. `store.py` is rewritten to SQLite with identical public API signatures. Old data migrated via `/settings/import` web upload — no `manage.py` CLI.
- **Courses table uses single JSON blob column**: `data TEXT` stores the full course dict (location, tees, holes) as serialized JSON. Keeps the store API simple — no schema explosion for variable tee/hole structures.
- **Round index preserved in SQLite**: Added `round_index INTEGER NOT NULL DEFAULT 0` column to preserve the `{date: {index: round_data}}` JSON structure for URL compatibility (`/rounds/{date}/{index}`). Gaps from deletions acceptable.
- **Drafts stay as JSON files**: Course/round in-progress wizard state stays in `data/drafts/<user_id>.json` to minimize SQLite migration scope. Not caller-visible — function signatures unchanged.

## 2026-05-27 — Multi-user: Auth and bootstrap

- **No CLI tools**: All operations (invite code generation, import, bootstrap) are web UI. Host registers via first-run auto-admin — when user count is 0, `/register` is open (no invite code required). First user gets `is_admin=1`.
- **Flask-WTF for CSRF**: Chosen over manual implementation. JSON API routes are auto-exempted (Flask-WTF skips `application/json` requests), so existing `app.js` fetch calls need no changes.
- **Walled garden model**: No guest access, no public profiles. Everyone sees everyone's data (no per-stat privacy). `?user=username` URL param for cross-user viewing. Write operations restricted to own data.

## 2026-05-27 — Multi-user: Deployment

- **Systemd service** at `scripts/pinsheet.service` (alongside existing `scripts/launchers/`). `scripts/install-service.sh` copies to `/etc/systemd/system/`.
- **SECRET_KEY enforced**: App refuses to start if unset or placeholder. Generated with `python -c "import secrets; print(secrets.token_hex(32))"` — no helper script needed.
- **Chrome auto-launch disabled in production**: Only launches browser when `--host 127.0.0.1` is used and `FLASK_ENV != "production"`. Server-only in deployment.

## 2026-05-27 — Multi-user: Phased implementation

Three sequential phases, each producing a working app:
1. **Phase A**: SQLite migration (default user id=1, no auth). App works identically to current.
2. **Phase B**: Auth layer (bcrypt, flask-login, login/register, invite codes, `@login_required`).
3. **Phase C**: Multi-user UI (user switcher, `?user=` param, admin invites page, read-only enforcement).

Each phase compiles and can be smoke-tested independently. No big-bang rewrite.
