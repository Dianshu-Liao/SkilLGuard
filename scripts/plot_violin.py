"""
plot_violin.py - Draw an annotated violin plot for a numeric column in a statistics CSV.

Usage:
    python scripts/plot_violin.py <csv_file> [--column COLUMN] [--output OUTPUT]

Example:
    python scripts/plot_violin.py \
        final_results/contextual_skillguard_evaluation/mimo-mimo-v2-5-pro/normal/statistics.csv \
        --column total_tokens
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde


def make_fmt(unit: str):
    """Return a formatter function based on unit."""
    if unit == "k":
        return lambda val: f"{val/1000:,.0f}k"
    else:
        return lambda val: f"{val:,.0f}{unit}"


def plot_violin(data: np.ndarray, column: str, ax=None, unit: str = "k"):
    if ax is None:
        fig, ax = plt.subplots(figsize=(3.5, 7))

    fmt = make_fmt(unit)

    # --- Stats ---
    vmin = data.min()
    vmax = data.max()
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    median = np.median(data)
    mean = np.mean(data)

    # --- KDE violin ---
    kde = gaussian_kde(data, bw_method=0.3)
    y = np.linspace(vmin, vmax, 500)
    x = kde(y)
    x = x / x.max() * 0.38  # half-width

    ax.fill_betweenx(y, -x, x, color="lightgray", edgecolor="black", linewidth=0.8)

    # --- Median: solid black line + label inside violin ---
    ax.plot([-0.38, 0.38], [median, median], color="black", linewidth=5.0, zorder=4)
    offset = (vmax - vmin) * 0.02
    ax.text(0, median - offset, f"Md={fmt(median)}", color="black",
            va="top", ha="center", fontsize=15,
            zorder=5)

    # --- Bounding box: xlim covers only the violin area ---
    BOX_X = 0.5   # half-width of the box
    ax.set_xlim(-BOX_X, BOX_X)
    ax.set_ylim(vmin - (vmax - vmin) * 0.05, vmax + (vmax - vmin) * 0.05)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_color("black")

    # --- Left axis: ticks pointing outward at min, Q1, Q3, max ---
    TICK_LEN = 0.06
    LABEL_PAD = 0.04
    for val in [vmin, q1, q3, vmax]:
        ax.plot([-BOX_X - TICK_LEN, -BOX_X], [val, val],
                color="black", linewidth=0.8, clip_on=False)
        ax.text(-BOX_X - TICK_LEN - LABEL_PAD, val, fmt(val),
                va="center", ha="right", fontsize=15, clip_on=False)

    # --- Right axis: Mean tick pointing outward + rotated label ---
    ax.plot([BOX_X, BOX_X + TICK_LEN], [mean, mean],
            color="black", linewidth=0.8, clip_on=False)
    ax.text(BOX_X + TICK_LEN + LABEL_PAD, mean, f"Mean={fmt(mean)}",
            va="center", ha="left", fontsize=15, rotation=90,
            clip_on=False)

    # --- Bottom: column label with outward tick at center ---
    ymin_ax = ax.get_ylim()[0]
    ax.plot([0, 0], [ymin_ax, ymin_ax - (vmax - vmin) * 0.02],
            color="black", linewidth=0.8, clip_on=False)
    ax.set_xlabel(column, fontsize=15, labelpad=20)

    return ax


def main():
    plt.rcParams["font.family"] = "Times New Roman"
    parser = argparse.ArgumentParser(description="Annotated violin plot from statistics CSV.")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--column", default="total_tokens",
                        help="Column to plot (default: total_tokens)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output image path (default: same dir as CSV)")
    parser.add_argument("--xlabel", default=None,
                        help="Custom x-axis label (default: column name)")
    parser.add_argument("--unit", default="k",
                        help="Unit suffix for tick labels, e.g. 'k' (default) or 's'")
    args = parser.parse_args()

    df = pd.read_csv(args.csv_file)

    # Keep only successful sandboxes with valid numeric data
    df = df[df["success"].astype(str) == "True"]
    df = df[pd.to_numeric(df[args.column], errors="coerce").notna()]
    data = pd.to_numeric(df[args.column]).to_numpy()

    if len(data) == 0:
        print(f"No valid data in column '{args.column}'.")
        return

    fig, ax = plt.subplots(figsize=(4, 5.8))
    label = args.xlabel if args.xlabel else args.column
    plot_violin(data, label, ax=ax, unit=args.unit)
    plt.tight_layout()

    out = args.output or args.csv_file.parent / f"violin_{args.column}.pdf"
    plt.savefig(out, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()
