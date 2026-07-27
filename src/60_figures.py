"""Stage 6: communication figures.

The four-panel choropleth is a working figure: it needs a colour-scale key, a
sign convention and four panels held in the head at once. This stage makes the
figures that carry the argument on their own.

Figure A (the LinkedIn graphic): one row per time zone, every county plotted as a
dot at its solar offset, against a 60-minute reference bar labelled as the size
of the entire DST debate. No map literacy needed and no legend to decode: if the
zone rows are wider than the reference bar, the argument is made.

Figure B: the same idea reduced to two counties in one zone, for use as an
opening image.

Usage:
    uv run src/60_figures.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import numpy as np
import pandas as pd

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"

# Standard time isolates the geography: no DST contribution, and it is what every
# US clock is actually on through the winter, so it needs no caveat to a reader.
REGIME = "perm_st"
ZONES = ["Eastern", "Central", "Mountain", "Pacific"]

CMAP = "RdBu_r"
NORM = Normalize(vmin=-75, vmax=75)

INK = "#1a1208"
MUTED = "#6b6157"
RULE = "#d8d0c4"


def load() -> pd.DataFrame:
    m = pd.read_csv(OUT / "metrics.csv", dtype={"GEOID": str})
    return m[(m.regime == REGIME) & (m.zone.isin(ZONES))].copy()


def wq(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w) / np.sum(w)
    return float(np.interp(q, cw, v))


def figure_a(df: pd.DataFrame, dest: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 8.6))

    rng = np.random.default_rng(0)
    for i, zone in enumerate(ZONES):
        g = df[df.zone == zone]
        x = g.offset_annual_mean.to_numpy()
        w = g.pop_weight.to_numpy()
        y = i + rng.uniform(-0.17, 0.17, len(x))

        # Every county, area proportional to population. The eye reads the dense
        # band as "most people" without needing a percentile explained.
        ax.scatter(x, y, s=np.clip(w / 4200, 4, 900), c=x, cmap=CMAP, norm=NORM,
                   alpha=0.55, linewidths=0)

        lo, hi = x.min(), x.max()
        ax.plot([lo, hi], [i - 0.33, i - 0.33], color=MUTED, lw=1.1, solid_capstyle="butt")
        for xv in (lo, hi):
            ax.plot([xv, xv], [i - 0.29, i - 0.37], color=MUTED, lw=1.1)
        ax.annotate(f"{hi - lo:.0f} min across the zone", xy=((lo + hi) / 2, i - 0.39),
                    ha="center", va="top", fontsize=10.5, color=MUTED)

    # The comparison the whole figure exists to make.
    y0 = -1.05
    ax.annotate("", xy=(-60, y0), xytext=(0, y0),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=2.2))
    for xv in (0, -60):
        ax.plot([xv, xv], [y0 - 0.09, y0 + 0.09], color=INK, lw=2.2)
    ax.text(-30, y0 - 0.20, "60 minutes\nthe entire DST debate",
            ha="center", va="top", fontsize=14, color=INK, fontweight="bold",
            linespacing=1.35)

    ax.axvline(0, color=INK, lw=1.0, alpha=0.5, zorder=0)
    ax.text(0, 3.52, "clock agrees\nwith the sun", ha="center", va="bottom",
            fontsize=10, color=MUTED, linespacing=1.3)

    # Tightened to the data: the old limits left a third of the width empty,
    # which shrank the dots and weakened the comparison with the 60-minute bar.
    ax.set_xlim(-68, 40)
    ax.set_ylim(-1.85, 4.0)
    # Zone names as y tick labels rather than free text, so they cannot drift out
    # of alignment with the row they describe.
    ax.set_yticks(range(len(ZONES)))
    ax.set_yticklabels(ZONES, fontsize=16, color=INK, fontweight="bold")
    ax.set_xticks([-60, -45, -30, -15, 0, 15, 30])
    ax.set_xticklabels(
        ["60 min\nsun late", "45", "30", "15", "0", "15", "30 min\nsun early"],
        fontsize=10.5,
    )
    ax.tick_params(axis="x", colors=MUTED, length=0, pad=6)
    ax.tick_params(axis="y", length=0, pad=10)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.grid(axis="x", color=RULE, lw=0.7, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)

    fig.suptitle("Everyone in a time zone shares a clock.\nThey do not share a sun.",
                 fontsize=25, x=0.045, ha="left", y=0.985, linespacing=1.2, color=INK)
    fig.text(0.045, 0.845,
             "Each dot is one US county, sized by population, placed by how far its clock sits from the sun "
             "on standard time.\nThree of the four zones are internally more spread out than the hour "
             "Congress keeps voting on.",
             fontsize=12.5, color=MUTED, linespacing=1.6, ha="left")
    fig.text(0.045, 0.035,
             "Signed solar offset: clock noon minus true solar noon, annual mean, 2026. "
             "3,143 counties, solar positions from NREL SPA, validated against USNO.",
             fontsize=9, color=MUTED, ha="left")

    fig.subplots_adjust(left=0.115, right=0.975, top=0.80, bottom=0.11)
    fig.savefig(dest, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"wrote {dest.name}")


def figure_b(df: pd.DataFrame, dest: Path) -> None:
    """Two counties, one zone. The opening image."""
    picks = {"23029": "Washington County, Maine", "26131": "Ontonagon County, Michigan"}
    sub = df[df.GEOID.isin(picks)].set_index("GEOID")

    fig, ax = plt.subplots(figsize=(12, 5.6))
    lo = hi = 0.0
    for i, (geoid, name) in enumerate(picks.items()):
        v = float(sub.loc[geoid, "offset_annual_mean"])
        lo, hi = min(lo, v), max(hi, v)
        y = 1 - i
        ax.plot([0, v], [y, y], color=mpl.colormaps[CMAP](NORM(v)), lw=10,
                solid_capstyle="round", zorder=2)
        ax.scatter([v], [y], s=210, color=mpl.colormaps[CMAP](NORM(v)), zorder=3,
                   edgecolor="white", linewidth=1.6)
        # Labels sit above the bar, centred on it. Placing them beyond the bar
        # end pushes long county names straight off the canvas.
        ax.text(v / 2, y + 0.42, name, ha="center", va="bottom",
                fontsize=15, color=INK, fontweight="bold")
        phrase = ("the sun passed overhead 30 minutes ago" if v > 0
                  else "the sun is still 57 minutes away from overhead")
        ax.text(v / 2, y + 0.20, f"at clock noon, {phrase}",
                ha="center", va="bottom", fontsize=12, color=MUTED)

    ax.axvline(0, color=INK, lw=1.4, zorder=1)
    ax.text(0, 2.02, "clock noon", ha="center", va="bottom", fontsize=12, color=INK)

    ax.annotate("", xy=(lo, -0.72), xytext=(hi, -0.72),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=2))
    for xv in (lo, hi):
        ax.plot([xv, xv], [-0.80, -0.64], color=INK, lw=2)
    ax.text((lo + hi) / 2, -0.92, f"{hi - lo:.0f} minutes apart, in the same time zone",
            ha="center", va="top", fontsize=15, color=INK, fontweight="bold")

    ax.set_xlim(-70, 44)
    ax.set_ylim(-1.6, 2.5)
    ax.set_yticks([])
    ax.set_xticks([])
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)

    fig.suptitle("Two counties, one time zone", fontsize=24, x=0.045, ha="left",
                 y=0.97, color=INK)
    fig.text(0.045, 0.045,
             "Signed solar offset on standard time, annual mean 2026. Congress is debating a uniform "
             "60-minute shift.",
             fontsize=9.5, color=MUTED, ha="left")
    fig.subplots_adjust(left=0.045, right=0.975, top=0.84, bottom=0.13)
    fig.savefig(dest, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"wrote {dest.name}")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    df = load()
    print(f"{len(df):,} counties across {df.zone.nunique()} zones, regime={REGIME}")
    for zone in ZONES:
        g = df[df.zone == zone]
        x, w = g.offset_annual_mean.to_numpy(), g.pop_weight.to_numpy()
        print(f"  {zone:9} {x.min():+7.1f} to {x.max():+6.1f}  range {x.max()-x.min():5.1f}  "
              f"pw p10..p90 {wq(x, w, 0.1):+.0f}..{wq(x, w, 0.9):+.0f}")
    figure_a(df, OUT / "fig_a_zone_spread.png")
    figure_b(df, OUT / "fig_b_two_counties.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
