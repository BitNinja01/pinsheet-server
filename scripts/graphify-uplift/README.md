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

## Findings (n=8, 26 runs, directional; full write-up gitignored in .context/graphify-uplift/)
Token uplift ~neutral (ratio-of-means −1.9%, median per-task +1.5%). Real edge is
**reliability**, all replicated (2 reps): completeness on large caller-set impact
analysis (T3 symbol-recall treatment 1.00 vs baseline 0.67; token stdev 462 vs 7,865)
and **precision stability** on impact/cross-cutting tasks (treatment precision stdev
0.000 vs baseline 0.062/0.300 on T4/T6 — baseline reaches the same answers but
inconsistently). Not a token multiplier. Keep #101; keep CI non-blocking.
