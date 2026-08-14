"""Closure tests for issue #79 — unpinned dependencies (CWE-1104).

Direct dependencies must cap the major version, and a hash-pinned lockfile
must exist as the reproducible-build basis.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_direct_deps_have_upper_bounds():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert deps
    for dep in deps:
        assert "<" in dep, f"dependency {dep!r} has no upper version bound"


def test_requirements_txt_has_upper_bounds():
    lines = [
        ln.split("#")[0].strip()
        for ln in (ROOT / "requirements.txt").read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines
    for spec in lines:
        assert "<" in spec, f"requirement {spec!r} has no upper version bound"


def test_lockfile_exists_and_is_hash_pinned():
    lock = ROOT / "requirements.lock"
    assert lock.exists(), "requirements.lock is missing"
    text = lock.read_text()
    assert "--hash=sha256:" in text, "lockfile is not hash-pinned"
    # Exact pins (==), not ranges — the direct deps must appear pinned.
    for pkg in ("flask", "werkzeug", "waitress", "bcrypt", "flask-login", "flask-limiter", "flask-wtf"):
        assert re.search(rf"^{re.escape(pkg)}==", text, re.MULTILINE | re.IGNORECASE), \
            f"{pkg} is not pinned in requirements.lock"
