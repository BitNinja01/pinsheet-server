## graphify: codebase knowledge graph (agent guidance)

This repo has an **optional, local, opt-in** knowledge graph of the codebase, built by
`graphify` (run `scripts/graphify-setup.sh` to install/refresh it). It is NOT committed to
the repo (`graphify-out/` is gitignored) and is NOT built or trusted automatically -- treat
it as a navigation aid, not ground truth, and always validate against the rules below before
acting on it.

Background/evidence for every claim below: `.context/graphify-spike/MEASUREMENTS.md` and
`.context/graphify-spike/PS_ANALYSIS.md` (Issue #101 spike + go/no-go decision,
GO-WITH-CONDITIONS, Pattern 2).

### 0. Staleness check -- do this FIRST, every time, before trusting the graph

The graph is a point-in-time snapshot with no automatic freshness check. Before using any
graph output for an impact assessment, verify it matches the current tree:

```bash
python3 -c "import json; print(json.load(open('graphify-out/graph.json'))['built_at_commit'])"
git rev-parse HEAD
```

- If the two commits **match**: the graph reflects the current tree. Proceed.
- If they **do not match**: the graph is stale. Do not treat node/edge counts, "affected"
  results, or god-node rankings as authoritative for the current diff. Re-run
  `scripts/graphify-setup.sh` (or `graphify extract . --code-only` directly) to refresh, or
  fall back to grep/Glob for anything touching the mismatched window.

`graphify-out/manifest.json` additionally records per-file `mtime`, `ast_hash`, and
`semantic_hash` if finer-grained partial-staleness checking (e.g. "has this one file changed
since extraction") is needed.

### 1. When to query the graph vs. blind file search

Prefer querying the graph over an unguided `grep -r` / repo-wide `Glob` scan when the task is
one of:

- "What calls / is called by function X" or "what breaks if I change X" (cross-module impact).
- Understanding call fan-out through this repo's routes -> calc -> storage layering (the graph's
  own hub ranking independently reconstructs this architecture -- see `god-nodes` below).
- Locating the architecturally central files for a subsystem before making a structural change.

Still use grep/Glob directly (do not query the graph first) when:

- The change is confined to a single already-known file.
- The code path involves **dynamic dispatch / dynamic imports** -- see Section 3, mandatory.
- The graph is stale (Section 0) and you have not refreshed it.

### 2. Confidence-aware querying -- do not treat all edges equally

Every edge in `graphify-out/graph.json` (`links[]`) carries a `confidence` label
(`EXTRACTED` or `INFERRED`) and a numeric `confidence_score`. Do not stop at the
EXTRACTED/INFERRED binary label -- read the score:

| confidence_score | Meaning | How to treat it |
|---|---|---|
| 1.0 (`EXTRACTED`) | Directly read from AST (calls, imports, contains, references, etc.) | Directly actionable. |
| 0.8 (`INFERRED`, routine) | Method/polymorphic call resolved without full type inference (e.g. `self.method()` matched to a class) | Actionable, but labeled as inferred -- low risk, this is the large majority of INFERRED edges in this repo (~97%). |
| 0.5 (`INFERRED`, speculative) | Genuine dynamic-dispatch guess (`indirect_call`, `uses`) | **Verify manually before acting.** Do not cite as fact; confirm with grep/Read of the actual source. This is a small slice of the graph (~1% of all edges in this repo) but is exactly where the graph can mislead. |

Rule of thumb: `confidence_score < 0.8` = "verify before acting", `>= 0.8` = "actionable, cite
as graph-derived."

### 3. MANDATORY grep-fallback for dynamic-import / dynamic-dispatch code

`source/plugin_loader.py` uses `importlib.import_module(folder_name)` to load plugins at
runtime (confirmed: the only non-test dynamic import in this repo). graphify captures
`plugin_loader.py`'s own static structure fully (`discover_plugins` -> `load_plugin` ->
`wire_template_path` / `wire_static_route` / `install_requirements`, all EXTRACTED), but the
actual plugin `register()` targets loaded at runtime are **not statically resolvable** and are
therefore invisible to the graph, or represented only by low-confidence (`indirect_call`,
score 0.5) guesses.

**Rule: any change touching `source/plugin_loader.py`, plugin `register()` functions, or any
future `importlib.import_module` / dynamic-dispatch code must NOT rely on graph output alone
for impact analysis.** Always additionally grep for the relevant symbol/plugin folder name and
manually read the runtime-wired call sites. Treat the graph's silence here as "unknown," never
as "no impact."

If you add a new dynamic-import site elsewhere in the codebase, add it to this list.

### 4. Query CLI commands

Confirmed — each command below was **executed during the spike** and its flags checked against
`graphify --help` (evidence in `.context/graphify-spike/MEASUREMENTS.md`):

```bash
# No-LLM extraction (local AST/tree-sitter only, zero API calls, must be re-run after pulling changes)
graphify extract . --code-only

# Reverse-impact / blast-radius query, confirmed working in this repo's spike
# (correctly returns DB-touching callers + tests for get_db, depth-bounded)
graphify affected <symbol> --depth <N>

# Ranked architectural hubs -- confirmed run in the spike (--graph/--top verified against
# `graphify --help` and executed; produced make_round() 137, create_user() 114,
# RoundData 96, make_course() 86, get_db() 72, register_routes() 35, ...)
graphify god-nodes --graph graphify-out/graph.json --top <N>
```

The following subcommands appear in `graphify --help` (captured during the spike) but their
exact flags were **not executed** this session. Treat their flags as **unconfirmed** until
checked locally -- run `graphify <subcommand> --help` before relying on them in automation:

```bash
graphify query <term>        # UNCONFIRMED flags -- BFS traversal of the graph for a question
graphify path <from> <to>    # UNCONFIRMED flags -- shortest path between two nodes
```

If you run either unconfirmed command above, update this section with the verified
flags so future agents don't have to re-discover them.

### 5. What the graph is good for here (validated)

The graph's top hubs (`make_round()`, `create_user()`, `RoundData`, `make_course()`, `get_db()`,
`register_routes()`, `_login()`) independently reconstruct this repo's actual
routes -> calc -> storage fan-out architecture without being told about it in advance -- this is
a real, structural correctness signal, not just a benchmark score. Use the graph with confidence
for cross-module "what depends on this" questions in the calc/storage layers, subject to
Sections 0-3 above.

### 6. Never auto-install or reconfigure graphify itself

Do not run `uv tool install graphify` / `graphifyy` / any bare package name, and do not edit
`scripts/graphify-setup.sh`'s pinned commit without human review. The single-y `graphify` name
is an open, unresolved typosquat risk on PyPI (see `.context/graphify-spike/PS_ANALYSIS.md`
Section 2a). If graphify is missing or out of date, tell the user to run
`scripts/graphify-setup.sh` rather than installing or upgrading it yourself.
