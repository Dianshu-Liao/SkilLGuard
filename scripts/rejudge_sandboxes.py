#!/usr/bin/env python3
"""Re-evaluate sandboxes that hit rate limits and merge results back."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from judges.contextual_judge import ContextualJudge
from judges._base import PARALLEL_EVALUATIONS
from config import CONTEXTUAL_INJECTIONS_FILE
from concurrent.futures import ThreadPoolExecutor, as_completed


def main():
    eval_file = Path(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else "sonnet"

    with open(eval_file) as f:
        data = json.load(f)

    results_dir = eval_file.parent

    to_rejudge = [
        r["sandbox_id"] for r in data["results"]
        if "hit your limit" in str(r.get("injection_evidence", ""))
        or "hit your limit" in str(r.get("task_evidence", ""))
    ]
    print(f"Re-evaluating {len(to_rejudge)} sandboxes...")

    judge = ContextualJudge()
    injections = judge.load_injections(CONTEXTUAL_INJECTIONS_FILE)
    sandbox_dirs = [results_dir / sid for sid in to_rejudge if (results_dir / sid).exists()]
    tasks = judge.prepare_tasks(sandbox_dirs, injections, evaluate_task=True, use_oauth=True)

    new_results = []
    done = [0]
    total = len(tasks)

    with ThreadPoolExecutor(max_workers=PARALLEL_EVALUATIONS) as pool:
        futs = {pool.submit(judge.evaluate_single, t, model): t for t in tasks}
        for fut in as_completed(futs):
            done[0] += 1
            try:
                r = fut.result()
                new_results.append(r)
                sym = {"attack_success": "V", "ignored": "o", "technical": "!"}.get(
                    r.get("injection_score", ""), "?")
                print(f"  [{done[0]}/{total}] {r['sandbox_id']} {sym}", flush=True)
            except Exception as exc:
                print(f"  [{done[0]}/{total}] error: {exc}", flush=True)

    new_by_id = {r["sandbox_id"]: r for r in new_results}
    merged = [new_by_id.get(r["sandbox_id"], r) for r in data["results"]]

    inj_s = sum(1 for r in merged if r.get("injection_score") == "attack_success")
    inj_i = sum(1 for r in merged if r.get("injection_score") == "ignored")
    inj_t = sum(1 for r in merged if r.get("injection_score") == "technical")
    ts = sum(1 for r in merged if r.get("task_score") == "task_success")
    tf = sum(1 for r in merged if r.get("task_score") == "task_failed")
    tt = sum(1 for r in merged if r.get("task_score") == "technical")

    print(f"\nInjection: {inj_s} success, {inj_i} ignored, {inj_t} technical")
    print(f"Task: {ts} success, {tf} failed, {tt} technical")

    data["results"] = merged
    data["summary"] = {
        "injection": {"success": inj_s, "ignored": inj_i, "technical": inj_t},
        "success": inj_s, "ignored": inj_i, "technical": inj_t,
        "task": {"success": ts, "failed": tf, "technical": tt},
    }
    eval_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Saved to {eval_file}")


if __name__ == "__main__":
    main()
