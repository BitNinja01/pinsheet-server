#!/usr/bin/env bash
#
# scripts/graphify-setup.sh
#
# Local, opt-in bootstrap for graphify (codebase knowledge-graph tool) for
# AI-agent use in this repo. Pattern 2 per Issue #101 / decision in
# .context/graphify-spike/PS_ANALYSIS.md (GO-WITH-CONDITIONS).
#
# What this script does:
#   1. Verifies .gitignore covers graphify-out/, .claude/, and CLAUDE.md
#      (all three are gitignored in this repo already -- this is a defensive
#      re-check, not a first-time setup, so it must never duplicate entries).
#   2. Installs graphify from a PINNED VCS commit (uv, with pipx fallback) --
#      never from a bare package name.
#   3. Runs `graphify claude install` to generate the (gitignored) CLAUDE.md
#      section + .claude/ PreToolUse hook that graphify itself manages.
#   4. Appends this repo's own agent-guidance section (confidence-aware
#      querying, grep-fallback, staleness check) to the same gitignored
#      CLAUDE.md, idempotently.
#   5. Runs `graphify extract . --code-only` -- local AST/tree-sitter only,
#      zero LLM calls, no API key required or used.
#
# SECURITY (read before editing GRAPHIFY_PINNED_COMMIT below):
#   The official, maintained PyPI package is `graphifyy` (two y's). The
#   single-y `graphify` name is UNCLAIMED on PyPI and is a live, currently
#   unresolved typosquat risk: the maintainers were told about it in
#   Graphify-Labs/graphify#280 and closed the report "not planned"; a
#   separate reclaim request (pypi/support#10098) is open and unresolved.
#   See .context/graphify-spike/PS_ANALYSIS.md Section 2a (risk R4, RPN 270,
#   the highest-severity finding in that analysis) for full evidence.
#
#   Because of this, graphify MUST be installed from a pinned VCS commit,
#   never from `uv tool install graphify` / `graphifyy` / any bare name, and
#   never via a plain `pip install`. Do not "simplify" the install command
#   below without re-reading PS_ANALYSIS.md Section 2a first.
#
# This script is safe to re-run (idempotent) and is NOT invoked by CI or any
# automated pipeline -- it is a manual, per-developer step only.

set -euo pipefail

# --- Pinned install target ---------------------------------------------
GRAPHIFY_REPO="https://github.com/Graphify-Labs/graphify"
GRAPHIFY_PINNED_COMMIT="7fe58b0b0f3873be9a21c30106b8b8527c353aa6"
GRAPHIFY_INSTALL_URL="git+${GRAPHIFY_REPO}@${GRAPHIFY_PINNED_COMMIT}"

# --- Paths ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLAUDE_SECTION_FILE="${SCRIPT_DIR}/graphify-claude-section.md"
GITIGNORE_FILE="${REPO_ROOT}/.gitignore"
CLAUDE_MD_FILE="${REPO_ROOT}/CLAUDE.md"

BEGIN_MARKER="<!-- BEGIN graphify-agent-guidance (managed by scripts/graphify-setup.sh) -->"
END_MARKER="<!-- END graphify-agent-guidance (managed by scripts/graphify-setup.sh) -->"

log()  { printf '[graphify-setup] %s\n' "$*"; }
warn() { printf '[graphify-setup] WARNING: %s\n' "$*" >&2; }
die()  { printf '[graphify-setup] ERROR: %s\n' "$*" >&2; exit 1; }

# --- 0. Self-check: refuse to run if the install URL was tampered with ---
case "${GRAPHIFY_INSTALL_URL}" in
  "git+https://github.com/Graphify-Labs/graphify@${GRAPHIFY_PINNED_COMMIT}") ;;
  *)
    die "GRAPHIFY_INSTALL_URL does not match the expected pinned VCS ref -- refusing to install. This script must only ever install from a pinned commit, never a bare package name. See the SECURITY comment at the top of this file."
    ;;
esac

log "Pinned install target: ${GRAPHIFY_INSTALL_URL}"

# --- 1. Ensure gitignore hygiene (defensive; entries should already exist) ---
ensure_gitignored() {
  entry="$1"
  if [ ! -f "${GITIGNORE_FILE}" ]; then
    die ".gitignore not found at ${GITIGNORE_FILE}; run this script from within a clone of the repo."
  fi
  if grep -qxF "${entry}" "${GITIGNORE_FILE}"; then
    log "OK: '${entry}' already present in .gitignore"
  else
    warn "'${entry}' missing from .gitignore -- appending now (graphify output/config must never be committed)"
    printf '\n%s\n' "${entry}" >> "${GITIGNORE_FILE}"
  fi
}

log "Checking .gitignore covers graphify-out/, .claude/, and CLAUDE.md..."
ensure_gitignored "graphify-out/"
ensure_gitignored ".claude/"
ensure_gitignored "CLAUDE.md"

# --- 2. Install graphify (pinned, isolated) -------------------------------
if command -v graphify >/dev/null 2>&1 && [ "${GRAPHIFY_SETUP_FORCE_REINSTALL:-0}" != "1" ]; then
  log "graphify already on PATH ($(command -v graphify)); skipping install."
  log "Set GRAPHIFY_SETUP_FORCE_REINSTALL=1 to force a reinstall from the pinned commit above."
else
  installed=0

  if [ "${installed}" -eq 0 ] && command -v uv >/dev/null 2>&1; then
    log "Installing graphify via 'uv tool install' (isolated, pinned commit)..."
    uv tool install "${GRAPHIFY_INSTALL_URL}"
    installed=1
  fi

  if [ "${installed}" -eq 0 ] && command -v pipx >/dev/null 2>&1; then
    log "'uv' not found; installing graphify via 'pipx' (isolated, pinned commit)..."
    pipx install "${GRAPHIFY_INSTALL_URL}"
    installed=1
  fi

  if [ "${installed}" -eq 0 ]; then
    die "Neither 'uv' nor 'pipx' found on PATH. Install one first (https://docs.astral.sh/uv/ or https://pipx.pypa.io/) and re-run this script. Do NOT run 'pip install graphify' or 'pip install graphifyy' directly -- always use the pinned VCS URL above via an isolated tool installer."
  fi
fi

command -v graphify >/dev/null 2>&1 || die "Install reported success but 'graphify' is not on PATH. Check your uv/pipx shell integration ('uv tool update-shell' or 'pipx ensurepath'), open a new shell, and re-run this script."

log "graphify is installed and on PATH: $(command -v graphify)"

# --- 3. Generate the graphify-managed CLAUDE.md section + .claude/ hook ---
cd "${REPO_ROOT}"
log "Running 'graphify claude install' (writes gitignored CLAUDE.md section + .claude/ hook)..."
graphify claude install

# --- 4. Append this repo's own agent-guidance section (idempotent) -------
if [ ! -f "${CLAUDE_SECTION_FILE}" ]; then
  warn "Guidance fragment not found at ${CLAUDE_SECTION_FILE}; skipping. Confidence-aware querying / grep-fallback / staleness-check instructions will be MISSING from CLAUDE.md until this file is present alongside the script."
elif [ -f "${CLAUDE_MD_FILE}" ] && grep -qF "${BEGIN_MARKER}" "${CLAUDE_MD_FILE}"; then
  log "OK: graphify agent-guidance section already present in CLAUDE.md (skipping append)"
else
  log "Appending graphify agent-guidance section to CLAUDE.md..."
  {
    printf '\n%s\n' "${BEGIN_MARKER}"
    cat "${CLAUDE_SECTION_FILE}"
    printf '\n%s\n' "${END_MARKER}"
  } >> "${CLAUDE_MD_FILE}"
fi

# --- 5. Extract the graph (no LLM, local only) ----------------------------
log "Running 'graphify extract . --code-only' (local AST/tree-sitter, zero LLM calls, no API key used)..."
graphify extract . --code-only

log ""
log "Done."
log ""
log "Next steps:"
log "  - graphify-out/, .claude/, and CLAUDE.md are gitignored: never 'git add' them."
log "  - Re-run this script any time (safe/idempotent) to refresh the graph after pulling new commits:"
log "      GRAPHIFY_SETUP_FORCE_REINSTALL=1 ${SCRIPT_DIR}/graphify-setup.sh   # to also force-reinstall the tool"
log "      ${SCRIPT_DIR}/graphify-setup.sh                                   # to just re-extract"
log "  - Before trusting graph output, confirm graphify-out/graph.json's 'built_at_commit' field"
log "    matches \`git rev-parse HEAD\` -- see the appended CLAUDE.md guidance section for the exact check."
log "  - source/plugin_loader.py's importlib.import_module() runtime boundary is NOT visible to"
log "    graphify (confirmed spike finding) -- always grep-fallback for changes touching that file."
