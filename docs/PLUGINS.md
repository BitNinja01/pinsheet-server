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

## 1a. Security Model (read this first)

Placing a plugin directory under `plugins/` and enabling it grants that code the same privileges as
the host process — there is no sandbox. The loader's job is to make sure that privilege is only ever
granted to a plugin the owner has **explicitly enabled**, and to make the common mistakes (missing
auth, unsafe HTML injection, cross-user data reads) hard to make by accident:

- **Disabled means zero execution.** A plugin that is not enabled in `plugin_states` is never
  imported, never has its dependencies installed, and never gets its templates/static routes wired.
  Only its `plugin_info` (read via static parsing, without import) is available for the admin
  listing UI.
- **No automatic dependency installation.** `requirements.txt` is documentation only. Install a
  plugin's dependencies yourself, deliberately: `pip install -r plugins/<name>/requirements.txt`.
- **Routes must use `plugin_route`, not `app.route`.** Import from `source.plugin_api`:
  `plugin_route(app, name, url)` force-applies `@login_required`, so an unauthenticated route can't
  be shipped by omission. All four bundled stat plugins use this helper — see §18.
- **Nav links must use `add_nav`, not `app._plugin_nav.append(...)` directly.** It validates that
  `url` is an app-relative path (no `javascript:`, no `//host` open-redirect).
- **`<head>`/`<foot>` injection must use `add_block`, not `app._plugin_blocks[...] = ...` directly.**
  `base.html` no longer renders these with `|safe`; a plain string is now HTML-escaped by default.
  `add_block` allowlists content to `<link rel="stylesheet" href="/plugins/<name>/static/...">` /
  `<script src="/plugins/<name>/static/...">` pointing at the plugin's own static namespace, and
  returns a `Markup` object so it renders unescaped.
- **Data access for stat/read-only plugins is `source.request_data` only** — never `import store`.
  `store.get_all_rounds()` now **requires** an explicit `user_id` (the old `user_id=1` default was
  removed — it silently exposed the first user's data to any careless caller). Use
  `request_data.get_all_rounds_for_user()`, which binds `current_user.id`. See §13 and §18.

### Trust model & severity (why the loader is strict)

A plugin system loads code from disk, so severity depends entirely on **who is allowed to author or
supply a plugin**:

| Deployment | What a plugin is | Import-exec / pip severity |
|---|---|---|
| Single-user, owner authors every plugin, never shares | your own code running on your own box | **Low / Informational** — not a vulnerability, it's the feature |
| Plugins shared / downloaded (gist, forum, marketplace, a friend) | untrusted third-party code | **Critical** — dropping a folder = arbitrary code execution |
| Multi-user hosted (this app *is* multi-user: shared DB keyed by `user_id`) | one admin's install decision exposes **all** users' data (hooks receive the raw `db_path`) | **High** — blast radius is every user, decided by one admin |

The loader is written for the strict (untrusted/shared/multi-user) model because a *plugin system*
exists to be extended by code the owner did not necessarily write. If your deployment is strictly the
first row, treat the import/pip findings as Low — but the hardening costs you nothing and the
**"disabled means disabled"** guarantee is a real bug fix at any trust level.

**The core tradeoff — the admin validates the plugin.** A newly discovered plugin is seeded
**disabled**; it executes nothing until an admin explicitly enables it in the admin UI. That enable
action *is* the trust decision. This trades one-click drop-in convenience for a mandatory
human-in-the-loop validation step — the right default when "present on disk" must not mean "trusted
to run". Any older example in this document that predates §1a (raw `app.register_blueprint` /
`@bp.route` without `@login_required`, `g.view_user`, direct `app._plugin_blocks[...] =`) is
**superseded by the rules above** — use `plugin_route` / `current_user` / `add_block`.

## 2. Quick Start

Create a minimal plugin in four steps.

### Step 1: Create the directory

```bash
mkdir -p plugins/hello_world/templates
```

### Step 2: Write `__init__.py`

```python
from flask import render_template
from source.plugin_api import plugin_route, add_nav

plugin_info = {
    "name": "hello_world",
    "version": "0.1.0",
    "description": "Minimal example plugin",
    "author": "You",
}

def register(app):
    @plugin_route(app, "hello_world", "/hello")   # auto-applies @login_required
    def hello():
        return render_template("hello.html", message="Hello from plugin!")

    add_nav(app, label="Hello", url="/hello", page_id="hello")

def unregister(app):
    pass
```

`plugin_route` registers directly on `app` (not a Blueprint) and force-wraps the view with
`@login_required`, so the route can't accidentally ship unauthenticated. If you prefer Blueprints
for a multi-route plugin (see §6), you are responsible for applying `@login_required` to every
route yourself — `plugin_route` is the only mechanism that enforces it for you.
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

`app._csrf_exempt` does **not** exist (a prior revision of this doc referenced it in error — same
documentation-drift class as the `g.view_user` correction in §13). Use the real `flask_wtf` API
shown above (`csrf.exempt(bp)` or `csrf.exempt(view_func)`) for every CSRF exemption.

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
{% if plugin_blocks.get("head") %}{{ plugin_blocks["head"] }}{% endif %}

<!-- Before </body>: -->
{% if plugin_blocks.get("foot") %}{{ plugin_blocks["foot"] }}{% endif %}
```

**(T7/VULN-05 hardening — no `|safe` anymore.)** A plain Python string assigned directly to
`app._plugin_blocks[...]` is now HTML-escaped by Jinja's autoescaping and renders as inert text, not
live markup. Use `source.plugin_api.add_block()` instead — it allowlists content to a stylesheet
`<link>` or an external `<script src>` pointing at your own plugin's static namespace, and returns a
`Markup` object so it renders unescaped:

```python
from source.plugin_api import add_block

def register(app):
    add_block(app, "achievements", "head",
        '<link rel="stylesheet" href="/plugins/achievements/static/achievements.css">')
    add_block(app, "achievements", "foot",
        '<script src="/plugins/achievements/static/achievements.js"></script>')
```

Inline `<script>` bodies, arbitrary tags, and references to another plugin's or the core app's
static paths are rejected (logged, `register()` continues — a rejected block just doesn't render).

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
| `current_user` | Flask-Login | The authenticated user (see §13). There is no `g.view_user` — see §13 correction. |

## 10. Navigation Links

Add sidebar links with `source.plugin_api.add_nav()` during `register()` (T8 hardening — validates
`url` is an app-relative path, rejecting `javascript:`/`//host` values that raw dict-append would
have allowed):

```python
from source.plugin_api import add_nav

def register(app):
    add_nav(app, label="Achievements", url="/achievements", page_id="achievements")
```

Each entry has three keys:

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

**Correction (2026-08-09, VULN-03):** earlier revisions of this document described a `g.view_user`
"view as" mechanism (`?user=username`) for admins to view other users' data. **`g.view_user` does
not exist anywhere in `source/` and no "view as" feature is implemented.** That guidance was
aspirational/stale documentation, not a real accessor — a plugin author who tried to build against
it would either get `None` back every time (fails closed, but broken) or, worse, "fix" the missing
reference by inventing their own unauthenticated `?user=` switch, which would be a textbook IDOR
(CWE-639). This section now documents the **actual, working** pattern.

PinSheet is multi-user: rounds/settings/etc. are stored in shared tables keyed by `user_id`. The
real isolation boundary is `current_user.id` (Flask-Login) bound into the query at the data-access
layer.

### The golden rule — for the stat-plugin contract used in this repo

Stat plugins (see §18) do not query the database at all. They call
`source.request_data.get_all_rounds_for_user()`, which internally does
`store.get_all_rounds(current_user.id)` — i.e. it is **always** scoped to whoever is logged in for
the current request. **Never** import `store`/`database` directly and never call
`store.get_all_rounds()` with no argument — that function defaults to `user_id=1` and will silently
return the wrong user's data if you forget the argument (a real footgun that exists in the core
store layer; flagged to eng-lead separately, out of plugin scope).

```python
# ✅ Correct — scoped to the logged-in user automatically
from source.request_data import get_all_rounds_for_user
rounds = list(get_all_rounds_for_user())

# ❌ Wrong — bypasses the request_data layer, defaults to user_id=1
import store
rounds = store.get_all_rounds()
```

### In hooks

Hooks receive `user_id` explicitly and should use it for any DB write that isn't covered by
`request_data`:

```python
def on_round_saved(round_data, user_id, db_path):
    db = sqlite3.connect(str(db_path))
    rows = db.execute(
        "SELECT * FROM plugin_notes WHERE user_id = ?",
        (user_id,),  # ✅ correct
    )
```

### In routes

Use Flask-Login's `current_user` (the actual, real authentication primitive) together with
`request_data`, not a fictional `g.view_user`:

```python
from flask_login import current_user
from source.request_data import get_all_rounds_for_user

@bp.route("/achievements")
def achievements_page():
    rounds = list(get_all_rounds_for_user())  # ✅ scoped to current_user.id internally
    # ...
```

If a route needs to resolve data for a user OTHER than `current_user` (e.g. an admin comparison
view), that is a privileged operation that does not exist in the current plugin contract. Any
future addition of cross-user viewing MUST gate on `current_user.is_admin` (the existing, real
pattern — see `source/routes/admin.py`), never on unauthenticated client-supplied input.

### Query scoping patterns

```python
# ✅ Correct: scoped by user_id
db.execute("SELECT * FROM plugin_x WHERE user_id = ?", (user_id,))

# ❌ Wrong: unscoped — leaks every user's rows
db.execute("SELECT * FROM plugin_x")
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

> **Security note (2026-08-09, secure-plugin hardening).** This example was
> rewritten to use the secure plugin contract. Do NOT use the older pattern
> (`app.register_blueprint` + raw `@bp.route`, `getattr(g, "view_user", ...)`,
> or direct `app._plugin_blocks[...] = "<html>"`). Those bypass the mandatory
> `@login_required` wrapping, reference a `g.view_user` that does not exist in
> `source/`, and assign to a block that is now HTML-escaped by default. Use
> `plugin_route`, `flask_login.current_user`, `add_nav`, and `add_block` as
> shown below. See §13 for the contract reference.

### Directory structure

```
plugins/notes/
  __init__.py
  routes.py
  templates/
    notes/notes.html
  static/
    notes.css
```

### `plugins/notes/__init__.py`

```python
import sqlite3

plugin_info = {
    "name": "notes",
    "version": "1.0.0",
    "description": "Extended round notes with search and tags",
    "author": "You",
}

def register(app):
    # register routes via the secure helper (forces @login_required) and
    # nav/blocks via the validated helpers — never touch app.route /
    # app._plugin_nav / app._plugin_blocks directly.
    from .routes import register_routes
    register_routes(app)

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

### `plugins/notes/routes.py`

```python
import sqlite3

from flask import render_template, request, jsonify, current_app, abort
from flask_login import current_user

from source.plugin_api import plugin_route, add_nav, add_block


def register_routes(app):
    add_nav(app, label="Round Notes", url="/notes", page_id="notes")
    add_block(app, "notes", "head",
              '<link rel="stylesheet" href="/plugins/notes/static/notes.css">')

    @plugin_route(app, "notes", "/notes")
    def notes_list():
        # current_user is the authenticated owner (auth is force-applied by
        # plugin_route). Scope every query to current_user.id — never trust
        # a client-supplied user id, and there is no cross-user accessor.
        db = sqlite3.connect(str(current_app.config["DB_PATH"]))
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT * FROM plugin_notes WHERE user_id = ? ORDER BY round_date DESC",
            (current_user.id,),
        ).fetchall()
        db.close()
        return render_template("notes/notes.html",
                               notes=[dict(r) for r in rows], current_page="notes")

    @plugin_route(app, "notes", "/api/notes/<date>/<int:index>", methods=["PUT"])
    def update_note(date, index):
        # validate untrusted path/body input; reject with 400 on bad input
        if not date or not (0 <= index <= 17):
            abort(400)
        data = request.get_json(silent=True) or {}
        note = str(data.get("note", ""))[:2000]
        tags = str(data.get("tags", ""))[:500]
        db = sqlite3.connect(str(current_app.config["DB_PATH"]))
        db.execute(
            """INSERT OR REPLACE INTO plugin_notes
               (user_id, round_date, round_index, note, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (current_user.id, date, index, note, tags),
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
