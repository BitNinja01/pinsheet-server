#!/usr/bin/env python3
"""Score a graphify baseline-vs-treatment crossover run (issue #102).

Reads a results file (JSON list of trial records) and the task pairs (with
ground truth), and reports per-task precision/recall + paired token/precision
deltas. Ground truth is file-level; correctness for set tasks = recall==1.0.

Trial record shape (one per run):
  {"task_id","condition":"baseline|treatment","rep":1,
   "files":["source/..."],"llm_tokens":int,"tool_uses":int,
   "tools_used":[...],"used_graphify":bool}

Usage:
  python3 scripts/graphify-uplift/score.py RESULTS.json TASK_PAIRS.json
"""
import json
import statistics
import sys


def load_gt(task_pairs_path):
    d = json.load(open(task_pairs_path))
    tasks = d if isinstance(d, list) else d.get("tasks") or d.get("task_pairs")
    return {t["id"]: [f for f in t.get("ground_truth_files", [])] for t in tasks}


def prf(files, gt):
    fs = {f for f in files if f.startswith("source/")}
    g = set(gt)
    if not fs:
        return 0.0, 0.0
    tp = len(fs & g)
    return tp / len(fs), tp / len(g)


def main(results_path, task_pairs_path):
    gt = load_gt(task_pairs_path)
    rows = json.load(open(results_path))["trials"]
    # normalize key aliases (task/task_id, cond/condition)
    for r in rows:
        r.setdefault("task_id", r.get("task"))
        r.setdefault("condition", r.get("cond"))
    # integrity guard: no baseline run may have used graphify
    leaks = [(r["task_id"], r.get("rep")) for r in rows
             if r["condition"] == "baseline" and r.get("used_graphify")]
    if leaks:
        print(f"INTEGRITY FAIL: baseline runs used graphify: {leaks}")

    def agg(task, cond, key):
        vs = [r[key] for r in rows if r["task_id"].startswith(task)
              and r["condition"] == cond]
        return statistics.mean(vs) if vs else float("nan")

    tasks = sorted({r["task_id"].split("-")[0] for r in rows})
    dtok_pct, dprec = [], []
    print(f"{'task':6}{'tokB':>9}{'tokT':>9}{'Δ%':>7}{'precB':>7}{'precT':>7}")
    for t in tasks:
        for r in rows:  # compute per-run prf if absent
            if "precision" not in r:
                p, rc = prf(r.get("files", []), gt.get(r["task_id"], []))
                r["precision"], r["recall"] = p, rc
        tb, tt = agg(t, "baseline", "llm_tokens"), agg(t, "treatment", "llm_tokens")
        pb, pt = agg(t, "baseline", "precision"), agg(t, "treatment", "precision")
        d = 100 * (tt - tb) / tb
        dtok_pct.append(d)
        dprec.append(pt - pb)
        print(f"{t:6}{tb:>9.0f}{tt:>9.0f}{d:>6.1f}%{pb:>7.2f}{pt:>7.2f}")

    mean_b = statistics.mean([agg(t, "baseline", "llm_tokens") for t in tasks])
    mean_d = statistics.mean([agg(t, "treatment", "llm_tokens") - agg(t, "baseline", "llm_tokens")
                              for t in tasks])
    print("\n== aggregates (directional; small n) ==")
    print(f"tokens ratio-of-means Δ : {100 * mean_d / mean_b:+.1f}%")
    print(f"tokens median per-task Δ: {statistics.median(dtok_pct):+.1f}%")
    print(f"precision mean Δ        : {statistics.mean(dprec):+.3f}")
    print(f"token wins (treat fewer): {sum(1 for d in dtok_pct if d < 0)}/{len(tasks)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
