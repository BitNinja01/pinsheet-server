# PinSheet Server — AGENTS.md

Golf stats web app: Flask + waitress, SQLite, Jinja2, multi-user.

## Plugin architecture

- **Plugin directory**: `plugins/<name>/` — **gitignored** (`/plugins/` in `.gitignore`). Each plugin lives in its own nested git repo.
- **Contract**: `plugin_info` dict + `register(app)`/`unregister(app)` functions in `__init__.py`
- **Loading**: server calls `discover_plugins(app)` at startup — imports + validates + auto-wires `templates/` and `static/` paths, then calls `register(app)`
- **Error isolation**: plugin failures log warnings, never crash the server
- **Context injection**: `app._plugin_blocks` (dict: `head`, `foot` strings), `app._plugin_nav` (list of `{label, url, page_id}`)
- **Hooks**: `on_round_saved(round_data, user_id, db_path)`, `on_course_saved(course_name, course_data, user_id, db_path)`, `post_save_redirect(round_data, user_id)`
- **Plugins shipped**: cartographer (Stage 1 — hole viewer + gallery). Achievements and printables pending.

## Conventions

- **Multi-user**: use `user_id` from hooks (or `g.view_user` in routes) for data scoping, never `current_user`
- **Config**: plugin settings use `app.config` with `plugins.<name>.` prefix
- **Data**: plugins manage their own persistence under `data/plugins/<name>/` or in SQLite via `app.config["DB_PATH"]`
- **Templates**: extend `base.html`, use PinSheet CSS design tokens (`--ps-*`)
- **Tests**: pytest with `tmp_path` isolation. Plugin tests go in the plugin's repo, not the parent

## Session memory

Read in order on session start:
1. `README.md`
2. `docs/HANDOFF.md`
3. `docs/SESSION_LOG.md` (latest entry)
4. `docs/DECISIONS.md`
5. `docs/RUNBOOK.md`

Update `docs/HANDOFF.md` and append to `docs/SESSION_LOG.md` on session end.

## Commands

```bash
# Dev server
python source/main.py

# All tests
PYTHONPATH=source:plugins python -m pytest -v
```
