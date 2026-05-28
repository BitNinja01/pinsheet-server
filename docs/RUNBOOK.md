# Runbook

## Development

**Run the app (dev, auto-opens browser):**
```bash
python source/main.py
```

**Run the app (prod, no browser):**
```bash
FLASK_ENV=production python source/main.py --host 0.0.0.0 --port 8080
```

**Run with custom data directory:**
```bash
python source/main.py --data /path/to/data
```

**SECRET_KEY is required.** Generate one:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Then export it: `export SECRET_KEY="<generated-key>"`

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Post-change verification

**Python files:** run `python -m py_compile` on any changed `.py` file.

**Template changes:** start the app and navigate to the affected route.

## Building

**Source zip for distribution:**
```bash
./scripts/dist.sh
# Output: dist/pinsheet_<version>.zip
```

## Deployment (systemd)

**Install as a systemd service:**
```bash
sudo bash scripts/install-service.sh
# Edit /etc/systemd/system/pinsheet.service to set SECRET_KEY
sudo systemctl daemon-reload
sudo systemctl enable --now pinsheet
```

**Import old JSON data (web UI):**
Navigate to `/settings/import` and upload a zip of the old `data/` directory containing `courses.json`, `rounds/`, and `settings.json`.

## Data directory

The `data/` directory is created at runtime in the repo root (next to `main.py`). It is `.gitignore`d. The SQLite database is stored as `data/pinsheet.db`. Copy the data directory from the original pinsheet for development:
```bash
cp -r ../pinsheet/data data/
```

## Navigation

All navigation is HTTP GET — routes map to pages, `<a>` links navigate between them. No client-side router.

| Route | Screen | Method |
|---|---|---|
| `/` | Dashboard | GET |
| `/rounds/new` | Round entry wizard | GET |
| `/rounds/{date}/{index}` | Round detail | GET |
| `/courses` | Course list | GET |
| `/courses/{name}` | Course detail | GET |
| `/courses/new` | Course entry wizard | GET |
| `/stats` | Stats screen | GET |
| `/settings` | Settings page | GET/POST |
| `/settings/import` | JSON data import | GET/POST |
| `/login` | Login page | GET/POST |
| `/register` | Registration page | GET/POST |
| `/admin/invites` | Admin invite code management | GET/POST |
| `/profile` | Player profile | GET |
| `/season` | Season summary | GET |

API routes at `/api/` prefix for JSON fetch() calls.

## Reference docs

| File | Purpose |
|---|---|
| `docs/HANDOFF.md` | Current state, next actions, blockers |
| `docs/SESSION_LOG.md` | Chronological session history |
| `docs/DECISIONS.md` | Durable architectural decisions |
| `docs/RUNBOOK.md` | Operational commands and workflows |
| `AGENTS.md` | Architecture, conventions, commands |

## Plugins

Plugin packages live in the `plugins/` directory (gitignored). Each plugin is a Python package with an `__init__.py` and a `plugin_info` dict plus `register(app)` / `unregister(app)` functions. Plugins are loaded automatically at server startup.

**Adding a plugin:**
```bash
cd plugins
git clone <plugin-repo-url> <plugin-name>
# Restart the server
```

**Writing a quick test plugin:**
```bash
mkdir -p plugins/my_test
cat > plugins/my_test/__init__.py << 'EOF'
plugin_info = {"name": "my_test", "version": "0.1.0"}
def register(app):
    app.config["plugins.my_test"] = "loaded"
EOF
# Restart the server — plugin appears in logs
```
