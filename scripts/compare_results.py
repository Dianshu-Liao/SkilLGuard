#!/usr/bin/env python3
"""Compare evaluation results between baseline and SkillGuard.

Finds instances where injection_score or task_score differs between
two evaluation JSON files and prints a comparison table.

Usage:
    python scripts/compare_results.py <baseline_json> <skillguard_json> [options]

Examples:
    # Compare both injection and task scores
    python scripts/compare_results.py \
        final_results/contextual/claude-sonnet/normal/evaluation_llmjudge_sonnet.json \
        final_results/contextual_skillguard_evaluation/claude-sonnet/normal/evaluation_llmjudge_sonnet.json

    # Compare injection scores only
    python scripts/compare_results.py <baseline> <skillguard> --injection-only

    # Compare task scores only
    python scripts/compare_results.py <baseline> <skillguard> --task-only

    # Save output to a file
    python scripts/compare_results.py <baseline> <skillguard> --output diff.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_results(path: Path) -> dict[str, dict]:
    """Load evaluation JSON and index by sandbox_id."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {r["sandbox_id"]: r for r in data["results"]}


def compare(
    baseline: dict[str, dict],
    skillguard: dict[str, dict],
    check_injection: bool = True,
    check_task: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Return (injection_diffs, task_diffs)."""
    all_ids = sorted(set(baseline) | set(skillguard))

    injection_diffs = []
    task_diffs = []

    for sid in all_ids:
        b = baseline.get(sid)
        s = skillguard.get(sid)

        if b is None or s is None:
            continue  # only compare instances present in both

        if check_injection:
            b_inj = b.get("injection_score")
            s_inj = s.get("injection_score")
            if b_inj != s_inj:
                injection_diffs.append({
                    "sandbox_id": sid,
                    "baseline": b_inj,
                    "skillguard": s_inj,
                })

        if check_task:
            b_task = b.get("task_score")
            s_task = s.get("task_score")
            if b_task != s_task:
                task_diffs.append({
                    "sandbox_id": sid,
                    "baseline": b_task,
                    "skillguard": s_task,
                })

    return injection_diffs, task_diffs


def fmt_score(score: str | None) -> str:
    if score is None:
        return "null"
    return score


def print_section(title: str, diffs: list[dict], lines: list[str]) -> None:
    lines.append(f"\n{'='*60}")
    lines.append(f"  {title}  ({len(diffs)} differences)")
    lines.append(f"{'='*60}")
    if not diffs:
        lines.append("  (no differences)")
        return
    col_w = max(len(d["sandbox_id"]) for d in diffs) + 2
    header = f"  {'sandbox_id':<{col_w}}  {'baseline':<20}  {'skillguard'}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for d in diffs:
        b = fmt_score(d["baseline"])
        s = fmt_score(d["skillguard"])
        lines.append(f"  {d['sandbox_id']:<{col_w}}  {b:<20}  {s}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare baseline vs SkillGuard evaluation results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("baseline", type=Path, help="Path to baseline evaluation_llmjudge_*.json")
    parser.add_argument("skillguard", type=Path, help="Path to SkillGuard evaluation_llmjudge_*.json")
    parser.add_argument("--injection-only", action="store_true", help="Only compare injection scores")
    parser.add_argument("--task-only", action="store_true", help="Only compare task scores")
    parser.add_argument("--output", type=Path, default=None, help="Save output to this file")
    args = parser.parse_args(argv)

    check_injection = not args.task_only
    check_task = not args.injection_only

    baseline = load_results(args.baseline)
    skillguard = load_results(args.skillguard)

    common = set(baseline) & set(skillguard)
    only_baseline = set(baseline) - set(skillguard)
    only_skillguard = set(skillguard) - set(baseline)

    injection_diffs, task_diffs = compare(baseline, skillguard, check_injection, check_task)

    lines: list[str] = []
    lines.append(f"\nBaseline:   {args.baseline}")
    lines.append(f"SkillGuard: {args.skillguard}")
    lines.append(f"\nTotal instances: baseline={len(baseline)}, skillguard={len(skillguard)}, common={len(common)}")
    if only_baseline:
        lines.append(f"Only in baseline ({len(only_baseline)}): {sorted(only_baseline)}")
    if only_skillguard:
        lines.append(f"Only in skillguard ({len(only_skillguard)}): {sorted(only_skillguard)}")

    if check_injection:
        print_section("INJECTION SCORE DIFFERENCES", injection_diffs, lines)
    if check_task:
        print_section("TASK SCORE DIFFERENCES", task_diffs, lines)

    output = "\n".join(lines) + "\n"
    print(output)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Saved to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
