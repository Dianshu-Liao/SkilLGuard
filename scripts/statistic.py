"""
statistic.py - Summarize token usage and duration for a completed experiment run.

Usage:
    python scripts/statistic.py <experiment_dir>

Example:
    python scripts/statistic.py final_results/contextual/mimo-mimo-v2-5-pro/normal
    python scripts/statistic.py final_results/contextual_skillguard/mimo-mimo-v2-5-pro/normal

Output:
    <experiment_dir>/statistics.csv

If SkillGuard log.jsonl files are present, sg_* columns and combined_* columns are added.
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# SkillGuard log parsing (mirrors statistic_skillguard.py)
# ---------------------------------------------------------------------------

def _parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _parse_skillguard_log(log_file: Path) -> dict | None:
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

    session_ids = {e.get("session_id") for e in lines if e.get("session_id")}

    # Sum per-session durations to exclude gaps between sessions
    total_duration = 0.0
    for sid in session_ids:
        sid_entries = [e for e in lines if e.get("session_id") == sid]
        timestamps = []
        for entry in sid_entries:
            ts = entry.get("timestamp")
            if ts:
                try:
                    timestamps.append(_parse_timestamp(ts))
                except Exception:
                    pass
        if len(timestamps) >= 2:
            total_duration += (max(timestamps) - min(timestamps)).total_seconds()

    input_tokens = 0
    cache_tokens = 0
    output_tokens = 0
    total_tokens = 0
    in_miniagent = False
    current_rounds: set = set()

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
            in_miniagent = False
            current_rounds = set()

    return {
        "sg_input_tokens": input_tokens,
        "sg_cache_tokens": cache_tokens,
        "sg_output_tokens": output_tokens,
        "sg_total_tokens": total_tokens,
        "sg_duration_seconds": round(total_duration, 2),
    }


# ---------------------------------------------------------------------------
# Main collection
# ---------------------------------------------------------------------------

BASE_COLUMNS = [
    "sandbox_id",
    "agent",
    "success",
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_seconds",
]

SG_COLUMNS = [
    "sg_input_tokens",
    "sg_cache_tokens",
    "sg_output_tokens",
    "sg_total_tokens",
    "sg_duration_seconds",
    "combined_input_tokens",
    "combined_cache_tokens",
    "combined_output_tokens",
    "combined_total_tokens",
]


def collect_rows(run_dir: Path) -> tuple[list[dict], bool]:
    """Returns (rows, has_skillguard)."""
    rows = []
    has_skillguard = False

    for subdir in sorted(run_dir.iterdir()):
        if not subdir.is_dir():
            continue

        sid = subdir.name
        token_file = subdir / "token_usage.json"
        stdout_file = subdir / "agent_stdout.txt"
        log_file = subdir / ".claude" / "skillguard" / "log.jsonl"

        success = stdout_file.exists() and stdout_file.stat().st_size > 0

        row: dict = {
            "sandbox_id": sid,
            "agent": "",
            "success": success,
            "input_tokens": "",
            "cache_creation_input_tokens": "",
            "cache_read_input_tokens": "",
            "output_tokens": "",
            "total_tokens": "",
            "duration_seconds": "",
        }

        main_total = 0
        main_duration = 0.0
        input_tok = cache_create = cache_read = output_tok = 0

        if token_file.exists():
            with open(token_file) as f:
                t = json.load(f)
            input_tok = t.get("input_tokens", 0)
            cache_create = t.get("cache_creation_input_tokens", 0)
            cache_read = t.get("cache_read_input_tokens", 0)
            output_tok = t.get("output_tokens", 0)
            main_total = input_tok + cache_create + cache_read + output_tok
            main_duration = round(t.get("duration_seconds", 0), 2)

            row.update({
                "agent": t.get("agent", ""),
                "input_tokens": input_tok,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tok,
                "total_tokens": main_total,
                "duration_seconds": main_duration,
            })

        if log_file.exists():
            has_skillguard = True
            sg = _parse_skillguard_log(log_file)
            if sg:
                combined_total = (main_total + sg["sg_total_tokens"]) if isinstance(main_total, int) else ""
                combined_input = (input_tok + sg["sg_input_tokens"]) if isinstance(main_total, int) else ""
                combined_cache = (cache_create + cache_read + sg["sg_cache_tokens"]) if isinstance(main_total, int) else ""
                combined_output = (output_tok + sg["sg_output_tokens"]) if isinstance(main_total, int) else ""
                row.update({
                    **sg,
                    "combined_input_tokens": combined_input,
                    "combined_cache_tokens": combined_cache,
                    "combined_output_tokens": combined_output,
                    "combined_total_tokens": combined_total,
                })
            else:
                row.update({k: "" for k in SG_COLUMNS})
        else:
            row.update({k: "" for k in SG_COLUMNS})

        rows.append(row)

    return rows, has_skillguard


def compute_summary(rows: list[dict], has_skillguard: bool) -> tuple[dict, dict]:
    success_rows = [r for r in rows if r["success"] is True]
    success_count = len(success_rows)
    total_count = len(rows)

    def safe_sum(col, subset):
        vals = [r[col] for r in subset if isinstance(r[col], (int, float))]
        return sum(vals) if vals else ""

    def safe_avg(col, subset):
        vals = [r[col] for r in subset if isinstance(r[col], (int, float))]
        return round(sum(vals) / len(vals), 2) if vals else ""

    cols = BASE_COLUMNS[3:] + (SG_COLUMNS if has_skillguard else [])

    total_row: dict = {
        "sandbox_id": f"TOTAL ({success_count}/{total_count} succeeded)",
        "agent": "",
        "success": f"{success_count}/{total_count}",
    }
    avg_row: dict = {
        "sandbox_id": f"AVG (success only, n={success_count})",
        "agent": "",
        "success": "",
    }
    for col in cols:
        total_row[col] = safe_sum(col, rows)
        avg_row[col] = safe_avg(col, success_rows)

    return total_row, avg_row


def main():
    parser = argparse.ArgumentParser(description="Summarize experiment token usage into CSV.")
    parser.add_argument("run_dir", type=Path, help="Experiment run directory")
    args = parser.parse_args()

    run_dir: Path = args.run_dir.resolve()
    if not run_dir.exists():
        print(f"Error: directory not found: {run_dir}")
        return

    rows, has_skillguard = collect_rows(run_dir)
    if not rows:
        print("No sandbox directories found.")
        return

    total_row, avg_row = compute_summary(rows, has_skillguard)

    columns = BASE_COLUMNS + (SG_COLUMNS if has_skillguard else [])

    out_file = run_dir / "statistics.csv"
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(total_row)
        writer.writerow(avg_row)

    print(f"Written {len(rows)} sandboxes + summary → {out_file}")
    if has_skillguard:
        print("[SkillGuard] sg_* and combined_* columns included.")

    def fmt(val):
        if isinstance(val, int):
            return f"{val:,}"
        if isinstance(val, float):
            return f"{val:,.2f}"
        return str(val)

    print(f"\n{'='*50}")
    print(f"Sandboxes:               {total_row['success']}")
    print(f"--- TOTAL ---")
    print(f"Input tokens:            {fmt(total_row['input_tokens'])}")
    print(f"Cache creation tokens:   {fmt(total_row['cache_creation_input_tokens'])}")
    print(f"Cache read tokens:       {fmt(total_row['cache_read_input_tokens'])}")
    print(f"Output tokens:           {fmt(total_row['output_tokens'])}")
    print(f"Total tokens:            {fmt(total_row['total_tokens'])}")
    print(f"Duration:                {fmt(total_row['duration_seconds'])}s")
    if has_skillguard:
        print(f"SG total tokens:         {fmt(total_row['sg_total_tokens'])}")
        print(f"SG duration:             {fmt(total_row['sg_duration_seconds'])}s")
        print(f"Combined total tokens:   {fmt(total_row['combined_total_tokens'])}")
    print(f"--- AVG (success only) ---")
    print(f"Total tokens:            {fmt(avg_row['total_tokens'])}")
    print(f"Duration:                {fmt(avg_row['duration_seconds'])}s")
    if has_skillguard:
        print(f"SG total tokens:         {fmt(avg_row['sg_total_tokens'])}")
        print(f"Combined total tokens:   {fmt(avg_row['combined_total_tokens'])}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
