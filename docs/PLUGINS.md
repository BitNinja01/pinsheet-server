# PinSheet Server — Plugin Developer Guide

## 1. Overview

PinSheet Server is a Flask-based golf scoring and handicap tracking application. Its plugin system lets you extend the server with custom pages, hooks, database tables, sidebar navigation, and template injection — without modifying core source code.

Plugins are lightweight Python packages dropped into a `plugins/` directory at the project root. Each plugin exports a `plugin_info` dict and a `register(app)` function. The loader discovers them at startup, wires up template paths and static file serving automatically, and calls `register(app)` with the raw Flask application object.

**Minimum requirements for any plugin:**

| Requirement | Why |
|---|---|
| `plugins/<name>/__init__.py` | Must be an importable Python package |
| `plugin_info` dict | Identity metadata (`name`, `version` required) |
| `register(app)` function | Called at startup to wire into Flask |

## 2. Quick Start

Create a minimal plugin in four steps.

### Step 1: Create the directory

```bash
mkdir -p plugins/hello_world/templates
```

### Step 2: Write `__init__.py`

```python
from flask import Blueprint, render_template

plugin_info = {
    "name": "hello_world",
    "version": "0.1.0",
    "description": "Minimal example plugin",
    "author": "You",
}

hello_bp = Blueprint(
    "hello_world", __name__,
    template_folder="templates",
    static_folder="static",
)

@hello_bp.route("/hello")
def hello():
    return render_template("hello.html", message="Hello from plugin!")

def register(app):
    app.register_blueprint(hello_bp)
    app._plugin_nav.append({
        "label": "Hello",
        "url": "/hello",
        "page_id": "hello",
    })

def unregister(app):
    pass
```

### Step 3: Write a template

```html
<!-- plugins/hello_world/templates/hello.html -->
{% extends "base.html" %}
{% block content %}
<h1>{{ message }}</h1>
{% endblock %}
```

### Step 4: Restart the server

Stop and restart the PinSheet server. You should see in the logs:

```
plugin loaded: hello_world v0.1.0
```

A new "Hello" link appears in the sidebar. Clicking it renders your template.

---

## 3. Plugin Structure

Every plugin lives under `plugins/<name>/`. The directory name must be a valid Python identifier — it becomes the module name used by `importlib`.

```
plugins/
  <name>/
    __init__.py          # plugin_info, register(app), unregister(app)
    blueprint.py         # optional — Flask Blueprint (import from __init__)
    templates/           # optional — Jinja2 templates (auto-discovered)
    static/              # optional — CSS/JS/images (auto-served)
    tools/               # optional — dev scripts (ignored by loader)
    tests/               # optional — pytest tests (ignored by loader)
    requirements.txt     # optional — listed in README, not auto-installed
    README.md            # optional
    LICENSE              # optional
    NOTICE               # optional
```

Only `__init__.py` is required. The loader skips directories without it.

### `blueprint.py` convention

For plugins with many routes, split the Blueprint into its own file:

```python
# plugins/my_plugin/blueprint.py
from flask import Blueprint, render_template

bp = Blueprint("my_plugin", __name__, template_folder="templates")

@bp.route("/foo")
def foo():
    return render_template("foo.html")
```

```python
# plugins/my_plugin/__init__.py
from .blueprint import bp

plugin_info = { ... }

def register(app):
    app.register_blueprint(bp)
```

## 4. plugin_info Contract

The `plugin_info` dict is the plugin's identity card. The loader reads it at import time to validate the plugin before calling `register()`.

```python
plugin_info = {
    "name": "achievements",       # Required. Must match directory name.
    "version": "1.0.0",          # Required. Semver string.
    "description": "Unlock achievements for golf milestones",  # Optional.
    "author": "PinSheet Team",    # Optional.
}
```

### Validation rules

| Condition | Behaviour |
|---|---|
| `plugin_info` missing or not a dict | Plugin skipped with WARNING |
| `name` or `version` missing | Plugin skipped with WARNING |
| `name` != directory name | WARNING logged, plugin loaded anyway |
| Extra keys in dict | Ignored by loader, available at runtime |

### Runtime access

All loaded plugins' `plugin_info` is available in every Jinja template via the `plugin_info` global:

```jinja
{% for name, info in plugin_info.items() %}
  {{ info.name }} v{{ info.version }}
{% endfor %}
```

It's also accessible from Python:

```python
from source.plugin import _plugins
for mod in _plugins:
    print(mod.plugin_info["name"])
```

## 5. register(app) and unregister(app)

These two functions are the plugin's entry and exit points.

### register(app)

Called at server startup, after Flask extensions (LoginManager, CSRF, Limiter) are initialized but before the first request. At this point the following `app.config` keys are guaranteed to exist:

| Key | Type | Example | Description |
|---|---|---|---|
| `app.config["DB_PATH"]` | `Path` | `Path("/home/user/.pinsheet/data/pinsheet.db")` | Absolute path to the SQLite database |
| `app.config["DATA_DIR"]` | `Path` | `Path("/home/user/.pinsheet/data")` | Data directory root |

Two mutable lists are also available on `app`:

| Attribute | Type | Purpose |
|---|---|---|
| `app._plugin_blocks` | `dict` | Template block content (see §9) |
| `app._plugin_nav` | `list` | Sidebar navigation entries (see §10) |

Inside `register()` you can:

- Register Flask Blueprints (`app.register_blueprint(...)`)
- Modify `app.config` for plugin-specific settings
- Add Jinja globals (`app.jinja_env.globals["my_key"] = ...`)
- Register `before_request` / `after_request` handlers
- Write plugin-owned tables to the database
- Install fonts or generate files into `app.config["DATA_DIR"]`

```python
def register(app):
    """Register my plugin's blueprint and nav link."""
    app.register_blueprint(my_bp)
    app._plugin_nav.append({
        "label": "My Plugin",
        "url": "/my-plugin",
        "page_id": "my_plugin",
    })
```

If `register()` raises an exception, the plugin is skipped and a warning is logged. The server continues unaffected.

### unregister(app)

Called at server shutdown via `atexit`. This is best-effort — if the server is killed or `waitress` exits abnormally, this may not run.

```python
def unregister(app):
    """Clean up temp files, close connections, etc."""
    temp_dir = app.config["DATA_DIR"] / "plugins" / "my_plugin"
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir)
```

### What NOT to do in register()

- **Do not modify core `app.config` keys** like `SECRET_KEY`, `DB_PATH`, or `DATA_DIR`. Use the `plugins.<name>.` namespace instead (see §12).
- **Do not mutate `app._plugin_blocks` or `app._plugin_nav` after `register()`** unless you're responding to a runtime event — these are read by the context processor at template-render time.
- **Do not open long-lived database connections.** Open and close connections per operation.

## 6. Blueprints and Routes

Create a Flask Blueprint to add pages. The `template_folder` parameter lets you reference templates relative to your plugin directory, but the loader already auto-adds your `templates/` path — so even without `template_folder`, `render_template("my_template.html")` works.

### Basic blueprint

```python
from flask import Blueprint, render_template

bp = Blueprint("achievements", __name__)

@bp.route("/achievements")
def achievements_page():
    return render_template("achievements.html",
        current_page="achievements",
    )
```

Register it in `register()`:

```python
def register(app):
    app.register_blueprint(bp)
    app._plugin_nav.append({
        "label": "Achievements",
        "url": "/achievements",
        "page_id": "achievements",
    })
```

### Route naming

- Blueprint endpoint names are auto-namespaced (e.g. `achievements.achievements_page`).
- URL paths should avoid conflicting with core routes. Core routes use top-level slugs: `/`, `/rounds`, `/stats`, `/courses`, `/season`, `/settings`, `/admin/...`, `/api/...`. Plugin routes at `/achievements`, `/cartographer/...` etc. are safe.

### Passing `current_page`

To get the correct sidebar highlighting, pass `current_page` in every `render_template()` call for plugin pages. The value must match the `page_id` in your `plugin_nav` entry.

### CSRF exemption for API routes

If your blueprint defines API routes that receive POST requests from JavaScript (not forms), exempt them from CSRF:

```python
from flask_wtf.csrf import CSRFProtect

@bp.route("/api/achievements/unlock", methods=["POST"])
def unlock():
    # ...
    return {"ok": True}

# In register():
def register(app):
    app.register_blueprint(bp)
    csrf = CSRFProtect()
    csrf.exempt(bp)  # exempt all routes in this blueprint
```

Or exempt individual endpoints:

```python
app._csrf_exempt.add("achievements.unlock")
```

## 7. Database Access

Plugins access the same SQLite database as the core server using `app.config["DB_PATH"]`.

### Opening a connection

```python
import sqlite3

db = sqlite3.connect(str(app.config["DB_PATH"]))
db.row_factory = sqlite3.Row
```

The database uses WAL journal mode (enabled by the core at startup). Read-heavy plugins benefit from concurrent reads. Write operations should use short-lived connections.

### Reading data

Always scope queries by `user_id` — never read all users' data.

```python
db = sqlite3.connect(str(db_path))
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT * FROM rounds WHERE user_id = ? ORDER BY date DESC",
    (user_id,),
).fetchall()
db.close()
```

### Writing data

```python
db = sqlite3.connect(str(db_path))
db.execute(
    "INSERT INTO plugin_notes (user_id, round_date, note) VALUES (?, ?, ?)",
    (user_id, round_date, note_text),
)
db.commit()
db.close()
```

Own table should follow the pattern `plugin_<name>_<table>` to avoid collisions.

### Creating plugin-owned tables

Create your tables in `register()`. Execute DDL before the server starts serving requests.

```python
def register(app):
    db_path = app.config["DB_PATH"]
    db = sqlite3.connect(str(db_path))
    db.execute("""
        CREATE TABLE IF NOT EXISTS plugin_achievements_log (
            id          INTEGER PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            achievement TEXT NOT NULL,
            earned_at   TEXT NOT NULL DEFAULT (datetime('now')),
            round_date  TEXT,
            UNIQUE(user_id, achievement)
        )
    """)
    db.commit()
    db.close()
```

### Core database schema (reference)

| Table | Columns | Notes |
|---|---|---|
| `users` | `id`, `username`, `display_name`, `password_hash`, `is_admin`, `created_at` | |
| `courses` | `id`, `name`, `data` | `data` is JSON text of the full course dict |
| `rounds` | `id`, `user_id`, `course_name`, `date`, `round_index`, `tee_name`, `holes_played`, `entry_mode`, `holes`, `total_gross`, `total_putts`, `differential`, `notes`, `excluded`, `computed_handicap`, `created_at` | `holes` is JSON text; `UNIQUE(user_id, date, round_index)` |
| `settings` | `user_id`, `data` | `data` is JSON text of user preferences |
| `invite_codes` | `code`, `created_by`, `used_by`, `created_at`, `used_at` | |

## 8. Lifecycle Hooks

The server fires hooks at specific points during request processing. A plugin implements a hook by defining a function with the expected name and signature. No base class, no registration call — just name-match and you're wired in.

### 8.1 on_round_saved(round_data, user_id, db_path)

Fired synchronously after a round is saved to the database and the handicap index is computed.

**Parameters:**

| Param | Type | Description |
|---|---|---|
| `round_data` | `dict` | The round dict exactly as written to SQLite |
| `user_id` | `int` | The user who owns this round |
| `db_path` | `Path` | Resolved path to pinsheet.db |

**`round_data` dict keys:**

```python
{
    "date": "2026-05-15",
    "course": "Augusta National",
    "tees": "Blue",
    "holes_played": "18",
    "holes_selection": "all",
    "transport": "walking",
    "entry_mode": "detailed",
    "notes": "Great day!",
    "holes": {
        "1": {"gross": "4", "putts": "2", "penalties": "0", "fairway": "H", "gir": "H"},
        # ... 18 holes total
    },
    "total_gross": "82",
    "differential": "12.4",
    "computed_handicap": "14.2",
}
```

**Example:**

```python
def on_round_saved(round_data, user_id, db_path):
    """Check if this round earns a new achievement."""
    gross = int(round_data["total_gross"])
    if gross < 80:
        db = sqlite3.connect(str(db_path))
        db.execute(
            "INSERT OR IGNORE INTO plugin_achievements_log (user_id, achievement, round_date) VALUES (?, ?, ?)",
            (user_id, "broke_80", round_data["date"]),
        )
        db.commit()
        db.close()
```

### 8.2 on_course_saved(course_name, course_data, user_id, db_path)

Fired synchronously after a course is saved.

**Parameters:**

| Param | Type | Description |
|---|---|---|
| `course_name` | `str` | The course key/name |
| `course_data` | `dict` | The course dict exactly as written to SQLite |
| `user_id` | `int` | The user who saved this course |
| `db_path` | `Path` | Resolved path to pinsheet.db |

**`course_data` dict keys:**

```python
{
    "location": {
        "city": "Augusta",
        "state/province": "GA",
        "country": "USA",
    },
    "tees": {
        "Blue": {
            "slope": "145",
            "rating": "74.2",
            "yardages": {"1": "445", "2": "575", ...},
        },
    },
    "holes": {
        "1": {"par": "4", "index": "18"},
        # ... 18 holes total
    },
    "par": 72,
}
```

**Example:**

```python
def on_course_saved(course_name, course_data, user_id, db_path):
    """Generate yardage visualisation for the new course."""
    from my_plugin.geometry import generate_hole_maps
    output_dir = Path(db_path).parent / "plugins" / "cartographer"
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_hole_maps(course_name, course_data, output_dir)
```

### 8.3 post_save_redirect(round_data, user_id)

After a round is saved, the server checks each plugin's `post_save_redirect()` function in registration order. The first plugin to return a non-None URL string wins — the client-side JS receives `redirect` in the JSON response and navigates there. If every plugin returns `None`, the default round-detail redirect applies.

**Parameters:**

| Param | Type | Description |
|---|---|---|
| `round_data` | `dict` | Same dict as `on_round_saved` receives |
| `user_id` | `int` | The user who saved the round |

**Returns:** `str | None`

**Example:**

```python
def post_save_redirect(round_data, user_id):
    """Show the achievements screen if something was unlocked."""
    if _has_new_achievements(user_id, round_data["date"]):
        return "/achievements"
    return None
```

## 9. Template System

Plugin templates are auto-discovered. The loader appends `plugins/<name>/templates/` to Flask's Jinja search path before `register()` is called. This means `render_template("plugin_page.html")` works without any special setup.

### Template blocks

The core `base.html` provides two injection points:

```html
<!-- Inside <head>: -->
{% if plugin_blocks.get("head") %}{{ plugin_blocks["head"]|safe }}{% endif %}

<!-- Before </body>: -->
{% if plugin_blocks.get("foot") %}{{ plugin_blocks["foot"]|safe }}{% endif %}
```

A plugin populates these by modifying `app._plugin_blocks` in `register()`:

```python
def register(app):
    app._plugin_blocks["head"] = '<link rel="stylesheet" href="/plugins/achievements/static/achievements.css">'
    app._plugin_blocks["foot"] = '<script src="/plugins/achievements/static/achievements.js"></script>'
```

These are rendered raw (marked `|safe`) so HTML is not escaped.

### Extending base.html

All plugin templates should extend `base.html` to inherit the sidebar, user switcher, and theme:

```html
{% extends "base.html" %}
{% block content %}
<div class="ps-card">
    <h2>Plugin Page Title</h2>
    <p>Your content here.</p>
</div>
{% endblock %}
```

### Template globals available everywhere

| Variable | Source | Description |
|---|---|---|
| `plugin_blocks` | `app._plugin_blocks` | Dict of `{"head": ..., "foot": ...}` |
| `plugin_nav` | `app._plugin_nav` | List of `{"label": ..., "url": ..., "page_id": ...}` |
| `plugin_info` | All loaded `plugin_info` dicts | `{"name": {...}, ...}` map |
| `g.view_user` | Server | The user being viewed (may differ from logged-in user) |
| `g.settings` | Server | Current user's settings |
| `current_user` | Flask-Login | The authenticated user (see §13) |

## 10. Navigation Links

Add sidebar links by appending to `app._plugin_nav` during `register()`:

```python
def register(app):
    app._plugin_nav.append({
        "label": "Achievements",
        "url": "/achievements",
        "page_id": "achievements",
    })
```

Each entry is a dict with three keys:

| Key | Type | Description |
|---|---|---|
| `label` | `str` | Display text in the sidebar |
| `url` | `str` | URL path for the link |
| `page_id` | `str` | Identifier for `is-active` highlighting |

### Active-link highlighting

The core sidebar compares `current_page` (passed via `render_template()`) against each nav item's `page_id`. To make your link highlight correctly:

```python
@bp.route("/achievements")
def achievements_page():
    return render_template("achievements.html", current_page="achievements")
```

### Multiple nav entries

A plugin can add multiple links. Each gets its own entry:

```python
def register(app):
    for item in [
        {"label": "Course Gallery", "url": "/cartographer/gallery", "page_id": "cartographer_gallery"},
        {"label": "Hole Viewer",    "url": "/cartographer/holes",  "page_id": "cartographer_holes"},
        {"label": "PDF Export",     "url": "/cartographer/pdf",    "page_id": "cartographer_pdf"},
    ]:
        app._plugin_nav.append(item)
```

## 11. Static Files

Any files in `plugins/<name>/static/` are auto-served at `/plugins/<name>/static/<path>`.

### How it works

The loader registers a route like this before `register()` is called:

```python
@app.route("/plugins/achievements/static/<path:filename>")
def _plugin_achievements_static(filename):
    return send_from_directory(static_dir, filename)
```

The endpoint name is namespaced (`_plugin_<name>_static`) to avoid collisions.

### Referencing from templates

```html
<!-- In a plugin template -->
<link rel="stylesheet" href="/plugins/achievements/static/achievements.css">
<script src="/plugins/achievements/static/achievements.js"></script>
<img src="/plugins/achievements/static/trophy.png" alt="Trophy">
```

### Injecting via template blocks

For styles/scripts that should load on every page, use the head/foot template blocks from `register()`:

```python
def register(app):
    app._plugin_blocks["head"] = (
        '<link rel="stylesheet" href="/plugins/achievements/static/achievements.css">'
    )
    app._plugin_blocks["foot"] = (
        '<script src="/plugins/achievements/static/achievements.js"></script>'
    )
```

### CSS conventions

The core uses CSS custom properties for theming. Plugins should respect them:

```css
/* Available theme variables (approximate): */
.ps-card {
    background: var(--ps-bg-1);
    color: var(--ps-fg);
    border: 1px solid var(--ps-ink-1);
}
```

Use the `.ps-dark` / `.ps-light` body classes for theme-aware styling:

```css
body.ps-dark .plugin-widget {
    background: #1a1a2e;
}
body.ps-light .plugin-widget {
    background: #ffffff;
}
```

## 12. Settings Convention

Plugin-specific settings go under `app.config` with the `plugins.<name>.` prefix. This namespace is reserved by convention but not enforced.

```python
def register(app):
    app.config.setdefault("plugins.achievements.enabled", True)
    app.config.setdefault("plugins.achievements.notify_on_new", True)
```

Read settings in routes:

```python
@bp.route("/achievements")
def achievements_page():
    if not app.config.get("plugins.achievements.enabled", True):
        return "Achievements disabled", 404
    # ...
```

For per-user settings, store them in the `settings` table alongside core settings. The `data` column is a JSON blob — read it, merge your keys, write it back:

```python
import json
from database import get_db

db = get_db()
row = db.execute("SELECT data FROM settings WHERE user_id = ?", (user_id,)).fetchone()
settings = json.loads(row["data"]) if row else {}
plugin_setting = settings.get("plugins.achievements.enabled", True)
```

## 13. Multi-User Considerations

PinSheet is multi-user. It also has a "view as" feature (`?user=username` in the URL) that lets admins view other users' data. This means the `current_user` from Flask-Login may NOT be the data owner.

### The golden rule

**Never use `current_user` to scope data queries.** Always use the `user_id` passed by hooks or the `g.view_user` set by the server's `before_request` handler.

### In hooks

Hooks receive `user_id` explicitly:

```python
def on_round_saved(round_data, user_id, db_path):
    db = sqlite3.connect(str(db_path))
    rows = db.execute(
        "SELECT * FROM plugin_notes WHERE user_id = ?",
        (user_id,),  # ✅ correct
    )
```

### In routes

If you need the current data-owner in a route, use `g.view_user` (not `current_user`):

```python
@bp.route("/achievements")
def achievements_page():
    view_user = getattr(g, "view_user", None)
    if view_user is None:
        return "No user", 400
    uid = view_user["id"]  # ✅ the user whose data we're viewing
    # ...
```

The `current_user` is still available from Flask-Login for authentication checks (e.g. `.is_authenticated`, `.is_admin`), but should not be used for data scoping.

### Query scoping patterns

```python
# ✅ Correct: scoped by user_id
db.execute("SELECT * FROM plugin_x WHERE user_id = ?", (user_id,))

# ❌ Wrong: reads for logged-in user, ignoring ?user= parameter
db.execute("SELECT * FROM plugin_x WHERE user_id = ?", (current_user.id,))
```

## 14. Error Handling & Logging

### Logging

Use Python's standard `logging` module:

```python
import logging
log = logging.getLogger(__name__)

log.info("plugin achievement check passed")
log.warning("unexpected data format: %s", key)
```

Logs propagate to the server's output stream automatically. No special configuration needed.

### Hook exception safety

The server wraps every hook call in try/except. If your hook raises an exception:

- The error is logged with the plugin name and hook name
- The hook loop continues to the next plugin
- The HTTP response is unaffected

```python
def on_round_saved(round_data, user_id, db_path):
    try:
        risky_operation()
    except Exception:
        log.exception("failed to process round %s", round_data.get("date"))
```

### register() failures

If `register()` raises, the plugin is skipped with a WARNING. The server continues. To diagnose:

```python
def register(app):
    try:
        db = sqlite3.connect(str(app.config["DB_PATH"]))
        db.execute("CREATE TABLE ...")
        db.close()
    except Exception:
        log.exception("failed to initialize plugin database")
        raise  # plugin will be skipped
```

### Static file 404s

If a route references a missing static file, Flask returns 404 normally — no special handling.

## 15. Migration Guide — Porting from PinSheet Core (TUI)

The original PinSheet was a Textual TUI application. If you're porting a TUI plugin to the server, here is the mapping:

| TUI API | Server Equivalent |
|---|---|
| `screens()` → returns list of Screen classes | Blueprint + routes (`/name`, `/name/page`) |
| `bindings()` → key bindings on screens | `app._plugin_nav.append(...)` for sidebar links |
| `css()` → TCSS stylesheet | `static/` folder, `<link>` in plugin template |
| `settings_schema()` → defines configurable settings | `app.config` with `plugins.<name>.` prefix |
| `on_round_saved(round_data)` | `on_round_saved(round_data, user_id, db_path)` — now receives `user_id` and `db_path` |
| `on_course_saved(course_name, course_data)` | `on_course_saved(course_name, course_data, user_id, db_path)` |
| `acknowledgment_screen()` → post-save overlay | `post_save_redirect(round_data, user_id)` → returns URL string |
| `per_hole_content()` → widgets in hole tabs | Template blocks or custom round detail route |
| `__init__()` → font installation, startup logic | `register()` → same logic, run at server startup |

### Key differences to watch for

1. **Database access**: TUI plugins used internal SQLite queries. Server plugins receive `db_path` explicitly — you must open your own connection.
2. **User context**: TUI was single-user. Server plugins receive `user_id` in every hook and must scope queries.
3. **Asynchronous work**: TUI plugins could block the event loop freely. Server hooks are synchronous in the HTTP request path. Offload heavy work to threads.
4. **State**: TUI plugins held state in Python objects. Server plugins must store state per-user in the database or filesystem under `DATA_DIR`.

## 16. Existing Plugin Migration Checklists

The three core plugins from PinSheet TUI need the following changes to run on the server.

### 16.1 Achievements

| What | Change |
|---|---|
| `plugin_info` | Add `plugin_info` dict with `name: "achievements"`, `version`, `description`, `author` |
| `register(app)` | New function — create DB tables, register Blueprint, add nav link, inject template blocks |
| `unregister(app)` | New function — cleanup (likely empty) |
| `screens()` → Blueprint | Create `plugins/achievements/blueprint.py` with Flask Blueprint, `/achievements` route, `achievements.html` template |
| `bindings()` → nav | `app._plugin_nav.append({"label": "Achievements", "url": "/achievements", "page_id": "achievements"})` |
| `acknowledgment_screen()` | Rename to `post_save_redirect(round_data, user_id)`. Return `"/achievements"` if something new was unlocked, else `None`. |
| `on_round_saved(round_data)` | Add `user_id` and `db_path` parameters. Replace direct DB access with `sqlite3.connect(str(db_path))`. |
| `settings_schema()` | In `register()`: `app.config.setdefault("plugins.achievements.enabled", True)` etc. |
| Template injection | Use `app._plugin_blocks["head"]` for CSS link, `app._plugin_blocks["foot"]` for JS |
| DB table | Create `plugin_achievements_log` in `register()` |

### 16.2 Cartographer

| What | Change |
|---|---|
| `plugin_info` | Add `plugin_info` dict |
| `register(app)` | Create DB tables, register Blueprint with 4+ routes, add multiple nav links |
| `unregister(app)` | New function |
| `screens()` → Blueprint | Create Blueprint with routes for HoleView, CourseGallery, GeometrySetup, PDFExport |
| `bindings()` → nav | Multiple `app._plugin_nav.append(...)` calls — one per page |
| `css()` → static | `plugins/cartographer/static/cartographer.css` — served automatically at `/plugins/cartographer/static/cartographer.css` |
| `settings_schema()` | `app.config["plugins.cartographer.yardage_arcs"]`, `app.config["plugins.cartographer.show_distances"]`, etc. |
| `on_course_saved(course_name, course_data)` | Add `user_id` and `db_path`. Open `sqlite3.connect(str(db_path))` for writes. Generate hole maps in `DATA_DIR / "plugins" / "cartographer" /`. |
| Font installation | Same font-copy code in `register()`, writing to `~/.local/share/fonts/` |
| `per_hole_content()` | Either inject via template blocks on the round-detail page, or create a custom round detail route that includes your per-hole data |
| DB writes | Create `plugin_cartographer_hole_geometry` table in `register()` |

### 16.3 Printables

| What | Change |
|---|---|
| `plugin_info` | Add `plugin_info` dict |
| `register(app)` | PDF generation runs here. Output to `app.config["DATA_DIR"] / "plugins" / "printables" /`. |
| `unregister(app)` | Clean up generated PDFs |
| `screens()` | None — no Blueprint needed |
| `bindings()` | None — no nav links |
| `settings_schema()` | Empty — nothing to migrate |
| Font installation | Same `_install_fonts()` in `register()` |

## 17. Full Example Plugin: Notes

A complete, realistic plugin that adds free-text notes per round, stores them in its own table, displays them on a custom page, and hooks into round save.

### Directory structure

```
plugins/notes/
  __init__.py
  blueprint.py
  templates/
    notes.html
  static/
    notes.css
```

### `plugins/notes/__init__.py`

```python
import sqlite3
from .blueprint import bp

plugin_info = {
    "name": "notes",
    "version": "1.0.0",
    "description": "Extended round notes with search and tags",
    "author": "You",
}

def register(app):
    app.register_blueprint(bp)
    app._plugin_nav.append({
        "label": "Round Notes",
        "url": "/notes",
        "page_id": "notes",
    })
    app._plugin_blocks["head"] = (
        '<link rel="stylesheet" href="/plugins/notes/static/notes.css">'
    )

    db = sqlite3.connect(str(app.config["DB_PATH"]))
    db.execute("""
        CREATE TABLE IF NOT EXISTS plugin_notes (
            id          INTEGER PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            round_date  TEXT NOT NULL,
            round_index INTEGER NOT NULL DEFAULT 0,
            note        TEXT NOT NULL,
            tags        TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, round_date, round_index)
        )
    """)
    db.commit()
    db.close()

def unregister(app):
    pass

def on_round_saved(round_data, user_id, db_path):
    note_text = round_data.get("notes", "").strip()
    if not note_text:
        return
    db = sqlite3.connect(str(db_path))
    db.execute(
        """INSERT OR REPLACE INTO plugin_notes
           (user_id, round_date, round_index, note)
           VALUES (?, ?, ?, ?)""",
        (user_id, round_data["date"],
         int(round_data.get("index", 0)), note_text),
    )
    db.commit()
    db.close()
```

### `plugins/notes/blueprint.py`

```python
import sqlite3
from flask import Blueprint, render_template, g, request, jsonify
from flask_login import login_required

bp = Blueprint("notes", __name__)

@bp.route("/notes")
@login_required
def notes_list():
    view_user = getattr(g, "view_user", None)
    if view_user is None:
        return "No user", 400

    db = sqlite3.connect(str(bp.app.config["DB_PATH"]))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT * FROM plugin_notes WHERE user_id = ? ORDER BY round_date DESC",
        (view_user["id"],),
    ).fetchall()
    db.close()

    notes = [dict(r) for r in rows]
    return render_template("notes.html",
        notes=notes,
        current_page="notes",
    )

@bp.route("/api/notes/<date>/<int:index>", methods=["PUT"])
@login_required
def update_note(date, index):
    view_user = getattr(g, "view_user", None)
    data = request.get_json()
    db = sqlite3.connect(str(bp.app.config["DB_PATH"]))
    db.execute(
        """INSERT OR REPLACE INTO plugin_notes
           (user_id, round_date, round_index, note, tags)
           VALUES (?, ?, ?, ?, ?)""",
        (view_user["id"], date, index,
         data.get("note", ""), data.get("tags", "")),
    )
    db.commit()
    db.close()
    return jsonify({"ok": True})
```

### `plugins/notes/templates/notes.html`

```html
{% extends "base.html" %}
{% block content %}
<div class="ps-card">
    <h2>Round Notes</h2>
    {% if notes %}
        {% for note in notes %}
        <div class="note-entry">
            <strong>{{ note.round_date }}</strong>
            <p>{{ note.note }}</p>
            {% if note.tags %}
            <span class="note-tags">{{ note.tags }}</span>
            {% endif %}
        </div>
        {% endfor %}
    {% else %}
        <p>No notes yet. Notes are copied from round entries automatically.</p>
    {% endif %}
</div>
{% endblock %}
```

### `plugins/notes/static/notes.css`

```css
.note-entry {
    padding: 12px 0;
    border-bottom: 1px solid var(--ps-ink-1);
}
.note-entry:last-child {
    border-bottom: none;
}
.note-tags {
    display: inline-block;
    background: var(--ps-accent);
    color: var(--ps-bg);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
}
```

---

*End of plugin developer guide.*
