"""
statistic_skillguard.py - Summarize SkillGuard overhead from log.jsonl files.

Usage:
    python scripts/statistic_skillguard.py <experiment_dir>

Example:
    python scripts/statistic_skillguard.py \
        final_results/contextual_skillguard/mimo-mimo-v2-5-pro/normal

Output:
    <experiment_dir>/skillguard_statistics.csv
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


COLUMNS = [
    "sandbox_id",
    "session_count",
    "total_duration_seconds",
    "miniagent_call_count",
    "total_rounds",
    "input_tokens",
    "cache_tokens",
    "output_tokens",
    "total_tokens",
    "blocked_count",
    "allow_count",
]


def parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_log(log_file: Path) -> dict | None:
    lines = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not lines:
        return None

    # --- Session IDs ---
    session_ids = {entry.get("session_id") for entry in lines if entry.get("session_id")}
    session_count = len(session_ids)

    # --- Total duration: sum per-session durations to exclude gaps between sessions ---
    total_duration = 0.0
    for sid in session_ids:
        sid_entries = [e for e in lines if e.get("session_id") == sid]
        timestamps = []
        for entry in sid_entries:
            ts = entry.get("timestamp")
            if ts:
                try:
                    timestamps.append(parse_timestamp(ts))
                except Exception:
                    pass
        if len(timestamps) >= 2:
            total_duration += (max(timestamps) - min(timestamps)).total_seconds()

    # --- Mini agent calls: explore_agent start → permission generation completed ---
    miniagent_call_count = 0
    total_rounds = 0
    input_tokens = 0
    cache_tokens = 0
    output_tokens = 0
    total_tokens = 0

    in_miniagent = False
    current_rounds = set()

    for entry in lines:
        msg = entry.get("message", "")
        ctx = entry.get("context", {})

        if msg == "explore_agent start":
            in_miniagent = True
            current_rounds = set()

        elif msg == "explore_agent round_usage" and in_miniagent:
            usage = ctx.get("usage", {})
            round_num = ctx.get("round")
            if round_num is not None:
                current_rounds.add(round_num)
            input_tokens += usage.get("input_tokens", 0)
            cache_tokens += usage.get("cache_read_input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)

        elif msg == "permission generation completed" and in_miniagent:
            miniagent_call_count += 1
            total_rounds += len(current_rounds)
            in_miniagent = False
            current_rounds = set()

    # --- Blocked / allow counts ---
    blocked_count = 0
    allow_count = 0
    for entry in lines:
        ctx = entry.get("context", {})
        decision = ctx.get("decision")
        if decision == "deny":
            blocked_count += 1
        elif decision == "allow":
            allow_count += 1

    return {
        "session_count": session_count,
        "total_duration_seconds": round(total_duration, 2),
        "miniagent_call_count": miniagent_call_count,
        "total_rounds": total_rounds,
        "input_tokens": input_tokens,
        "cache_tokens": cache_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "blocked_count": blocked_count,
        "allow_count": allow_count,
    }


def collect_rows(run_dir: Path) -> list[dict]:
    rows = []
    for subdir in sorted(run_dir.iterdir()):
        if not subdir.is_dir():
            continue
        log_file = subdir / ".claude" / "skillguard" / "log.jsonl"
        if not log_file.exists():
            continue

        sid = subdir.name
        result = parse_log(log_file)
        if result is None:
            continue

        rows.append({"sandbox_id": sid, **result})

    return rows


def compute_summary(rows: list[dict]) -> dict:
    valid = [r for r in rows if isinstance(r.get("total_tokens"), int)]

    def safe_sum(col):
        vals = [r[col] for r in valid if isinstance(r[col], (int, float))]
        return sum(vals) if vals else ""

    def safe_avg(col):
        vals = [r[col] for r in valid if isinstance(r[col], (int, float))]
        return round(sum(vals) / len(vals), 2) if vals else ""

    return {
        "sandbox_id": f"TOTAL (n={len(valid)})",
        "session_count": "",
        "total_duration_seconds": safe_sum("total_duration_seconds"),
        "miniagent_call_count": safe_sum("miniagent_call_count"),
        "total_rounds": safe_sum("total_rounds"),
        "input_tokens": safe_sum("input_tokens"),
        "cache_tokens": safe_sum("cache_tokens"),
        "output_tokens": safe_sum("output_tokens"),
        "total_tokens": safe_sum("total_tokens"),
        "blocked_count": safe_sum("blocked_count"),
        "allow_count": safe_sum("allow_count"),
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize SkillGuard overhead from log.jsonl files.")
    parser.add_argument("run_dir", type=Path, help="Experiment run directory")
    args = parser.parse_args()

    run_dir: Path = args.run_dir.resolve()
    if not run_dir.exists():
        print(f"Error: directory not found: {run_dir}")
        return

    rows = collect_rows(run_dir)
    if not rows:
        print("No log.jsonl files found.")
        return

    summary = compute_summary(rows)

    out_file = run_dir / "skillguard_statistics.csv"
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(summary)

    print(f"Written {len(rows)} sandboxes + summary → {out_file}")

    def fmt(val):
        if isinstance(val, int):
            return f"{val:,}"
        if isinstance(val, float):
            return f"{val:,.2f}"
        return str(val)

    print(f"\n{'='*50}")
    print(f"Sandboxes processed:     {len(rows)}")
    print(f"Total duration:          {fmt(summary['total_duration_seconds'])}s")
    print(f"Mini agent calls:        {fmt(summary['miniagent_call_count'])}")
    print(f"Total rounds:            {fmt(summary['total_rounds'])}")
    print(f"Input tokens:            {fmt(summary['input_tokens'])}")
    print(f"Cache tokens:            {fmt(summary['cache_tokens'])}")
    print(f"Output tokens:           {fmt(summary['output_tokens'])}")
    print(f"Total tokens:            {fmt(summary['total_tokens'])}")
    print(f"Blocked count:           {fmt(summary['blocked_count'])}")
    print(f"Allow count:             {fmt(summary['allow_count'])}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
