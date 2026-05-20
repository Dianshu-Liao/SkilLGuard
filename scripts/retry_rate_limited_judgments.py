#!/usr/bin/env python3
"""Re-run contextual LLM judge only for sandboxes whose saved evidence looks like API failure.

Typical patterns: \"You've hit your limit\", \"429\", judge returning rate-limit text instead of JSON.

Usage (from repo root or skill-inject):

  cd skill-inject
  python scripts/retry_rate_limited_judgments.py \\
    final_results/contextual_skillguard/claude-sonnet/normal \\
    --evaluation-json final_results/contextual_skillguard/claude-sonnet/normal/evaluation_llmjudge_sonnet.json \\
    --evaluate-task \\
    --delay 2.0

This merges new judgments into the JSON and overwrites it (use --dry-run to list IDs only).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONTEXTUAL_INJECTIONS_FILE
from judges._base import BaseJudge, TECHNICAL_ERROR_MARKERS
from judges.contextual_judge import ContextualJudge

# Judge failures stored *as evidence* (different from agent_stdout rate limits).
JUDGE_FAILURE_MARKERS = TECHNICAL_ERROR_MARKERS + (
    "resets 12am",
)


def needs_retry(row: dict) -> bool:
    blob = (row.get("injection_evidence") or "") + (row.get("task_evidence") or "")
    return any(m in blob for m in JUDGE_FAILURE_MARKERS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry LLM judge rows contaminated by rate limits")
    parser.add_argument(
        "results_dir",
        type=Path,
        help="Directory containing INST-* sandbox folders",
    )
    parser.add_argument(
        "--evaluation-json",
        type=Path,
        required=True,
        help="Existing evaluation_llmjudge_*.json to read and update",
    )
    parser.add_argument(
        "--injections-file",
        type=Path,
        default=CONTEXTUAL_INJECTIONS_FILE,
    )
    parser.add_argument("--model", default="sonnet", help="Judge model id passed to run_claude_judge")
    parser.add_argument(
        "--evaluate-task",
        action="store_true",
        help="Must match how the original evaluation was produced",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to sleep between sandboxes (reduces judge API throttling)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print sandbox IDs that would be retried",
    )
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    eval_path = args.evaluation_json.resolve()
    if not eval_path.is_file():
        sys.exit(f"Not found: {eval_path}")

    data = json.loads(eval_path.read_text(encoding="utf-8"))
    rows: list[dict] = data.get("results", [])
    retry_ids = [r["sandbox_id"] for r in rows if needs_retry(r)]

    if not retry_ids:
        print("No rows matched judge-failure markers; nothing to do.")
        return

    print(f"Found {len(retry_ids)} rows to retry (e.g. rate-limited judge output).")
    if args.dry_run:
        for sid in retry_ids:
            print(sid)
        return

    missing_dirs = [sid for sid in retry_ids if not (results_dir / sid).is_dir()]
    if missing_dirs:
        print("Warning: sandbox dirs missing (skipped):", ", ".join(missing_dirs[:10]))
        if len(missing_dirs) > 10:
            print(f"  ... and {len(missing_dirs) - 10} more")
        retry_ids = [sid for sid in retry_ids if (results_dir / sid).is_dir()]

    sandbox_dirs = sorted(results_dir / sid for sid in retry_ids)
    judge = ContextualJudge()
    injections = judge.load_injections(args.injections_file)
    tasks = judge.prepare_tasks(
        sandbox_dirs,
        injections,
        evaluate_task=args.evaluate_task,
        evaluate_injection=True,
    )

    print(f"Re-evaluating {len(tasks)} sandboxes sequentially (delay={args.delay}s)...")
    new_by_id: dict[str, dict] = {}
    for i, t in enumerate(tasks):
        sid = t["sandbox_dir"].name
        print(f"  [{i + 1}/{len(tasks)}] {sid} ...", flush=True)
        new_by_id[sid] = judge.evaluate_single(t, args.model)
        if i + 1 < len(tasks) and args.delay > 0:
            time.sleep(args.delay)

    merged: list[dict] = []
    for r in rows:
        sid = r["sandbox_id"]
        if sid in new_by_id:
            merged.append(new_by_id[sid])
        else:
            merged.append(r)

    extra: dict = {}
    if args.evaluate_task:
        ts = sum(1 for r in merged if r.get("task_score") == "task_success")
        tf = sum(1 for r in merged if r.get("task_score") == "task_failed")
        tt = sum(1 for r in merged if r.get("task_score") == "technical")
        extra["task"] = {"success": ts, "failed": tf, "technical": tt}

    out_path = judge.save_results(merged, results_dir, args.model, **extra)
    print(f"Updated {len(new_by_id)} rows; wrote {out_path}")


if __name__ == "__main__":
    main()
