# graphify uplift benchmark (issue #102)

Reusable harness for measuring AI-agent performance uplift from graphify
(baseline vs treatment), companion to the #101 integration.

## Files
- `task_pairs.json` — 8 matched tasks (navigation, impact analysis, cross-cutting,
  bug-fix) with **machine-checkable ground truth** (`ground_truth_files` /
  `ground_truth_symbols`) derived from the repo via AST+grep, independent of
  graphify (so scoring does not favor treatment).
- `score.py` — standalone scorer: reads a results file + `task_pairs.json`,
  reports per-task precision/recall and paired token/precision deltas, and
  fails loudly if any baseline run used graphify.

## Protocol (as executed; see .context/graphify-uplift/EXPERIMENT_DESIGN.md v2)
Crossover, 8 matched pairs, identical pinned model both arms
(`claude-sonnet-5`), fresh session per run.
- **Baseline:** Bash (grep/find/cat) + Read. No graphify. No sub-agent delegation.
- **Treatment:** same + graphify CLI (`query`/`affected`/`path`/`explain`/`god-nodes`)
  over `graphify-out/graph.json`.
Each run emits one JSON record; scoring is arm-blind on the final answer only.

## Run
1. Build the graph: `scripts/graphify-setup.sh` (or `graphify extract . --code-only`).
2. For each task in both conditions, run a fresh agent with the task prompt and
   collect a record: `{"task_id","condition","rep","files":[...],"llm_tokens",
   "tool_uses","tools_used":[...],"used_graphify"}` into a `RESULTS.json`
   (`{"trials":[...]}`).
3. Score: `python3 scripts/graphify-uplift/score.py RESULTS.json scripts/graphify-uplift/task_pairs.json`

## Findings (n=8, directional; full write-up gitignored in .context/graphify-uplift/)
Token uplift ~neutral (ratio-of-means −1.3%, median per-task +1%). Real edge:
**consistency + completeness** on large caller-set impact analysis (T3: treatment
62 callers both reps, stdev 462 tokens; baseline 62→21 callers, stdev 7,865) and
**higher file precision** (less over-scoping) on impact/cross-cutting tasks
(T4 0.88→1.00, T6 0.40→1.00). Not a token multiplier. Keep #101; keep CI non-blocking.
