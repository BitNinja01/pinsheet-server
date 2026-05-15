# Runbook

## Development

**Run the app:**
```bash
python source/main.py
```

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

## Data directory

The `data/` directory is created at runtime in the repo root (next to `main.py`). It is `.gitignore`d. Copy the data directory from the original pinsheet for development:
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

API routes at `/api/` prefix for JSON fetch() calls.

## Reference docs

| File | Purpose |
|---|---|
| `docs/HANDOFF.md` | Current state, next actions, blockers |
| `docs/SESSION_LOG.md` | Chronological session history |
| `docs/DECISIONS.md` | Durable architectural decisions |
| `docs/RUNBOOK.md` | Operational commands and workflows |
| `AGENTS.md` | Architecture, conventions, commands |
