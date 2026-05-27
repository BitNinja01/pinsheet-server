# Testing and Release Pipeline Design

## Overview

Add comprehensive test suite and GitHub Actions CI/CD pipeline to pinsheet-server, matching the pinsheet core repo's patterns. Two independent workstreams: (1) test suite with 80%+ coverage, (2) CI and release workflow automation.

## Testing Architecture

### Directory Structure

```
tests/
  __init__.py
  conftest.py              # shared fixtures: make_round, make_course, app client, db setup
  test_handicap.py          # calc/handicap.py — differentials, HI, course handicap, best-N
  test_scoring.py           # calc/scoring.py — scoring avg, distribution, consistency, STAT_CATALOG
  test_approach.py          # calc/approach.py — FIR%, GIR%, miss tendencies, scramble
  test_putting.py           # calc/putting.py — putts/round, putts/GIR, 1/2/3-putt %, putts by par
  test_store.py             # store.py — SQLite CRUD, settings merge, draft lifecycle, user queries
  test_routes.py            # main.py Flask routes — GET/POST on all pages, auth gates, ?user= param
  test_auth.py              # login, register, invite codes, logout, admin restrictions
```

### Fixture Strategy

**conftest.py shared fixtures:**
- `app` — Flask test client with fresh in-memory SQLite per test (`:memory:` or tmpfile). Factory for isolating tests from real data.
- `make_round(date, gross, putts, fir, gir, ...)` — factory returning a round dict matching store.py/calc expected shape. String-stored numerics per data model conventions.
- `make_course(name, par, slope, rating, ...)` — factory returning a course dict with tees/holes matching JSON blob shape.
- `sample_rounds` — list of 3+ rounds with varied differentials for handicap calc tests.
- `sample_course` — single default course with Blue/White/Red tees.
- `auth_client` — test client with flask-login session simulating a logged-in user.

**Module-specific fixtures (in respective conftest or test files):**
- `test_store.py` — `autouse` fixture overrides `data/` path to `tmp_path`, creates fresh `pinsheet.db` per test module.
- `test_routes.py` — same tmp_path override, seeds test user + course + rounds before route tests.

### Test Patterns by Layer

**calc/ modules (pure functions, easiest to test):**
- Each `def test_<function>_<scenario>()` with synthesized course + round dicts.
- Test edge cases: empty data, single round, max rounds, 9-hole rounds, excluded rounds.
- Port existing tests from pinsheet core's `tests/test_handicap.py`, `tests/test_stats_*.py` — same function signatures, adjust imports only.

**store.py (SQLite integration):**
- Create temp `pinsheet.db` via fixture, exercise CRUD through public API.
- Tests: save/get/delete course, save/get/delete round, year-based round retrieval, settings merge-on-save, draft lifecycle, user CRUD (add/list/check invite code), get_all_rounds ordering.
- Verify SQLite state directly via `sqlite3` module queries for correctness, not just API return values.

**Flask routes (integration):**
- pytest-flask `test_client` — simulate GET/POST on all routes.
- Test patterns: 200 response for valid URLs, 302 redirect for auth-gated pages when not logged in, 403/404 for edge cases, template content assertions (e.g. stat labels present, table rows populated).
- Auth tests: register first user (no invite needed), register second user (invite required), login/logout redirect, admin-only routes blocked for non-admin, `?user=username` access control.

### Coverage

- Target: 80%+ line coverage across `source/` (excluding static assets and templates).
- `pytest-cov` with pyproject.toml config. Enforced in CI as `--cov-fail-under=80`.
- Exclude from coverage: `source/web/static/` (CSS/JS), `source/web/templates/` (HTML).

## CI Pipeline

### ci.yml

**File**: `.github/workflows/ci.yml`

**Triggers:**
- Pull requests targeting `dev` or `main`
- Pushes to `dev`

**Job**: `test`, `ubuntu-latest`, Python 3.11

| Step | Command |
|---|---|
| Checkout | `actions/checkout@v4` |
| Setup Python | `actions/setup-python@v5`, python-version: 3.11 |
| Install deps | `pip install -r requirements.txt && pip install -e ".[dev]"` |
| Compile check | `python -m py_compile` on all `source/*.py`, `source/calc/*.py`, `tests/*.py` |
| Run tests | `SECRET_KEY=ci-test pytest -v --cov --cov-report=term --cov-fail-under=80` |
| Secrets check | `grep` scan for `.env`, `password`, `secret_key` patterns in tracked Python files |

Template rendering smoke test is implicit in route tests (test_client hits routes that render templates).

## Release Pipeline

### release.yml

**File**: `.github/workflows/release.yml`

**Trigger**: push of tag matching `v*.*.*`

**Job**: `build-and-release`, `ubuntu-latest`, `contents: write` permission

| Step | Details |
|---|---|
| Checkout | `actions/checkout@v4` |
| Setup Python | `actions/setup-python@v5`, 3.11 |
| Extract version | Parse `vX.Y.Z` from `GITHUB_REF` |
| Build source zip | `git archive --format=zip --output=pinsheet-server_{version}.zip {ref}` |
| Fetch release notes | `gh` CLI pull body from most recent merged PR to `main` |
| Create release | `softprops/action-gh-release@v1` with zip attached, non-draft, non-prerelease |

### Versioning

- Version source of truth: `__version__ = "X.Y.Z"` added to `source/main.py` (line 1).
- Semver: vMAJOR.MINOR.PATCH.
- Branches: `dev` (integration target, CI runs on PR/push), `main` (stable, release tags point here).
- Release process: PR `dev` → `main` → merge → tag `main` with `vX.Y.Z` → release.yml fires.

### Distribution Artifact

Single source zip (`pinsheet-server_X.Y.Z.zip`) containing:
```
source/
README.md
requirements.txt
data/handicap_benchmarks.json
scripts/launchers/launch.sh
scripts/launchers/launch.bat
```

No platform-specific zips needed — same source runs everywhere via `python source/main.py`.

## Tooling

### pyproject.toml

```toml
[project]
name = "pinsheet-server"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-flask>=1", "pytest-cov>=5"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["source"]
addopts = "-v --strict-markers"

[tool.coverage.run]
source = ["source"]
omit = ["source/web/static/*", "source/web/templates/*"]

[tool.coverage.report]
fail_under = 80
```

### requirements-dev.txt

```
pytest>=8
pytest-flask>=1
pytest-cov>=5
```

### .gitignore additions

```
htmlcov/
.coverage
.pytest_cache/
.eggs/
```

## Implementation Order

1. **Foundation**: Add `__version__` to main.py, create `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml` skeleton
2. **Calc tests**: Port/reuse pinsheet core's calc tests (handicap, scoring, approach, putting) — pure functions, easy to migrate
3. **Store tests**: Integration tests for SQLite store layer with tmp_path isolation
4. **Route tests**: Flask test client integration tests for all routes
5. **Auth tests**: Login/register/invite code/admin guard tests
6. **Coverage tuning**: Fill gaps to hit 80%, add `release.yml`
