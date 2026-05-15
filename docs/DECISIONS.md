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
