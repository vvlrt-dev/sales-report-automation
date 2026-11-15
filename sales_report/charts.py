"""PNG charts with matplotlib (no display needed)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

INK = "#1f2a37"
MUTED = "#6b7785"
GRID = "#e5e9ee"
BAR = "#2f6f8f"
LINE = "#e0892f"


def _style(ax, title: str, subtitle: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=22)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=10, color=MUTED, va="bottom")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def _money_axis(currency: str):
    return FuncFormatter(lambda v, _: f"{currency}{v:,.0f}")


def revenue_by_day(by_day: pd.DataFrame, path: Path, currency: str) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    ax.bar(by_day["day"], by_day["revenue"], color=BAR, width=0.8, label="Daily revenue")
    ax.plot(by_day["day"], by_day["revenue_7d_avg"], color=LINE, linewidth=2.2, label="7-day average")
    _style(ax, "Revenue by day", f"{by_day['day'].min():%d %b} – {by_day['day'].max():%d %b %Y}")
    ax.yaxis.set_major_formatter(_money_axis(currency))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.legend(frameon=False, loc="lower right", fontsize=9, ncols=2, bbox_to_anchor=(1.0, 1.01))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def top_products_chart(top: pd.DataFrame, path: Path, currency: str) -> Path:
    rows = top.iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 0.45 * len(rows) + 1.6), dpi=150)
    bars = ax.barh(rows["product"], rows["revenue"], color=BAR, height=0.65)
    for bar, share in zip(bars, rows["share"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"  {currency}{bar.get_width():,.0f} · {share:.0%}", va="center", fontsize=9, color=INK)
    _style(ax, f"Top {len(rows)} products by revenue", "Share of total revenue in labels")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID)
    ax.xaxis.set_major_formatter(_money_axis(currency))
    ax.tick_params(axis="y", labelsize=10, labelcolor=INK)
    ax.set_xlim(0, rows["revenue"].max() * 1.22)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def average_check_chart(by_day: pd.DataFrame, path: Path, currency: str, overall: float) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.0), dpi=150)
    days = by_day.dropna(subset=["average_check"])
    ax.plot(days["day"], days["average_check"], color=BAR, linewidth=2, marker="o", markersize=3)
    ax.axhline(overall, color=LINE, linestyle="--", linewidth=1.5)
    ax.text(1.0, 1.02, f"- - period average {currency}{overall:,.2f}", transform=ax.transAxes, color=LINE,
            fontsize=9, va="bottom", ha="right")
    _style(ax, "Average check by day", "Revenue ÷ number of orders")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{currency}{v:,.2f}"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
