"""
plot_violin_horizontal.py - Draw a horizontal annotated violin plot for duration data.

Usage:
    python scripts/plot_violin_horizontal.py <csv_file> [--column COLUMN] [--xlabel XLABEL] [--unit UNIT] [--output OUTPUT]

Example:
    python scripts/plot_violin_horizontal.py \
        final_results/contextual_skillguard_evaluation/mimo-mimo-v2-5-pro/normal/statistics.csv \
        --column duration_seconds \
        --xlabel "Duration (s)" \
        --unit s
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde


def make_fmt(unit: str):
    if unit == "k":
        return lambda val: f"{val/1000:,.0f}k"
    else:
        return lambda val: f"{val:,.0f}{unit}"


def plot_violin_horizontal(data: np.ndarray, xlabel: str, ax=None, unit: str = "s"):
    if ax is None:
        fig, ax = plt.subplots(figsize=(4, 3))

    fmt = make_fmt(unit)

    # --- Stats ---
    vmin = data.min()
    vmax = data.max()
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    median = np.median(data)
    mean = np.mean(data)

    # --- KDE violin (horizontal: x=data axis, y=width axis) ---
    kde = gaussian_kde(data, bw_method=0.3)
    x = np.linspace(vmin, vmax, 500)
    y = kde(x)
    y = y / y.max() * 0.38  # half-height

    ax.fill_between(x, -y, y, color="lightgray", edgecolor="black", linewidth=0.8)

    # --- Median: vertical black line + label ---
    ax.plot([median, median], [-0.38, 0.38], color="black", linewidth=5.0, zorder=4)
    offset = (vmax - vmin) * 0.02
    ax.text(median + offset, 0, f"Md={fmt(median)}", color="black",
            va="center", ha="left", fontsize=18, fontweight="bold", zorder=5)

    # --- Bounding box ---
    BOX_Y = 0.5
    ax.set_ylim(-BOX_Y, BOX_Y)
    ax.set_xlim(vmin - (vmax - vmin) * 0.05, vmax + (vmax - vmin) * 0.05)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_color("black")

    # --- Bottom axis: ticks pointing outward at min, Q1, Q3, max ---
    TICK_LEN = 0.06
    LABEL_PAD = 0.04
    for val in [vmin, q1, q3, vmax]:
        ax.plot([val, val], [-BOX_Y - TICK_LEN, -BOX_Y],
                color="black", linewidth=0.8, clip_on=False)
        ax.text(val, -BOX_Y - TICK_LEN - LABEL_PAD, fmt(val),
                va="top", ha="center", fontsize=18, clip_on=False)

    # --- Top axis: Mean tick + label ---
    ax.plot([mean, mean], [BOX_Y, BOX_Y + TICK_LEN],
            color="black", linewidth=0.8, clip_on=False)
    ax.text(mean, BOX_Y + TICK_LEN + LABEL_PAD, f"Mean={fmt(mean)}",
            va="bottom", ha="center", fontsize=18, clip_on=False)

    # --- Left label with outward tick ---
    xmin_ax = ax.get_xlim()[0]
    ax.plot([xmin_ax, xmin_ax - (vmax - vmin) * 0.02], [0, 0],
            color="black", linewidth=0.8, clip_on=False)
    ax.set_ylabel(xlabel, fontsize=18, labelpad=20)

    return ax


def main():
    plt.rcParams["font.family"] = "Times New Roman"
    parser = argparse.ArgumentParser(description="Horizontal annotated violin plot from statistics CSV.")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--column", default="duration_seconds",
                        help="Column to plot (default: duration_seconds)")
    parser.add_argument("--xlabel", default=None,
                        help="Axis label (default: column name)")
    parser.add_argument("--unit", default="s",
                        help="Unit suffix for tick labels, e.g. 's' (default) or 'k'")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output image path (default: same dir as CSV)")
    parser.add_argument("--max", type=float, default=None,
                        help="Exclude values above this threshold (e.g. 1200)")
    args = parser.parse_args()

    df = pd.read_csv(args.csv_file)
    if "success" in df.columns:
        df = df[df["success"].astype(str) == "True"]
    df = df[pd.to_numeric(df[args.column], errors="coerce").notna()]
    data = pd.to_numeric(df[args.column]).to_numpy()
    if args.max is not None:
        data = data[data <= args.max]

    if len(data) == 0:
        print(f"No valid data in column '{args.column}'.")
        return

    fig, ax = plt.subplots(figsize=(8, 3))
    label = args.xlabel if args.xlabel else args.column
    plot_violin_horizontal(data, label, ax=ax, unit=args.unit)
    plt.tight_layout()

    out = args.output or args.csv_file.parent / f"violin_h_{args.column}.pdf"
    plt.savefig(out, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()
