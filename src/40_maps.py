"""Stage 4: four-panel choropleth of signed solar offset (NOTES.md §10).

One panel per regime, all four sharing **one fixed diverging colour scale centred
on zero**. Per-panel auto-scaling would destroy the comparison outright, because
permanent DST shifts every county by exactly -60 minutes; independently scaled
panels would render that shift invisible.

Alaska and Hawaii are drawn as insets on the same scale rather than being
reprojected into the CONUS frame. Alaska Time spans roughly -130 to -170 of
longitude, so its offsets run far outside the CONUS range; leaving it in the main
frame would force the shared scale wide enough to flatten all the CONUS
variation, which is the variation the argument is about.

Values outside the fixed domain are clipped, and the clipping is stated in the
caption rather than silently saturating.

Usage:
    uv run src/40_maps.py
    uv run src/40_maps.py --domain 90    # override the colour scale half-range
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import numpy as np
import pandas as pd

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "out"

CONUS_CRS = "EPSG:5070"  # Albers Equal Area (CONUS). Equal-area matters: the
# argument is partly about how much land and population sits far from its meridian.
AK_CRS = "EPSG:3338"
HI_CRS = "EPSG:6633"

SIMPLIFY_M = 800  # geometry simplification in projected metres, for file size

REGIME_TITLES = {
    "cta": "1. Current law (switching)",
    "perm_st": "2. Permanent standard time",
    "perm_dst": "3. Permanent DST",
    "optimized": "4. Optimised per-county offsets",
    "ideal_unconstrained": "Per-county ideal (unconstrained)",
}
PANEL_ORDER = ["cta", "perm_st", "perm_dst", "optimized"]

CMAP = "RdBu_r"  # low (sun late) -> blue, zero -> white, high (sun early) -> red

# Three counties in the *same* time zone, chosen because between them they carry
# the whole argument: Maine sits +30 min while Michigan's Upper Peninsula sits
# -57 min, an 87-minute spread inside one zone, and the optimiser fixes the west
# end without touching the east.
HIGHLIGHTS = {
    "26131": "Ontonagon, MI",
    "18097": "Marion, IN\n(Indianapolis)",
    "23029": "Washington, ME",
}


def load_geometry() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(f"zip://{RAW / 'tl_2020_us_county.zip'}")
    return gdf[["GEOID", "STATEFP", "geometry"]]


def project_and_simplify(gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    out = gdf.to_crs(crs)
    out["geometry"] = out.geometry.simplify(SIMPLIFY_M, preserve_topology=True)
    return out


def draw_panel(ax, conus, ak, hi, column: str, norm, title: str,
               states=None, marks=None) -> None:
    kw = dict(column=column, cmap=CMAP, norm=norm, linewidth=0, edgecolor="none")
    conus.plot(ax=ax, **kw)
    if states is not None:
        # State outlines only, drawn over the fill. County outlines at this size
        # would read as texture and swamp the colour.
        states.boundary.plot(ax=ax, linewidth=0.35, edgecolor="0.35", alpha=0.55)
    if marks is not None:
        for _, r in marks.iterrows():
            ax.plot(r["x"], r["y"], marker="o", markersize=5.5,
                    markerfacecolor="none", markeredgecolor="black",
                    markeredgewidth=1.3, zorder=5)
            ax.annotate(
                f"{r['label']}\n{r[column]:+.0f} min",
                xy=(r["x"], r["y"]), xytext=(r["dx"], r["dy"]),
                textcoords="offset points", fontsize=7, ha=r["ha"], va="center",
                zorder=6, linespacing=1.25,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.6", lw=0.5, alpha=0.9),
            )
    ax.set_axis_off()
    # Title inside the axes, not set_title: with set_axis_off the axes bbox fills
    # the panel, so an external title collides with the figure subtitle above.
    ax.text(0.01, 0.99, title, transform=ax.transAxes, ha="left", va="top",
            fontsize=11.5, fontweight="medium")

    # Insets share the panel's scale, so they stay comparable with CONUS.
    ax_ak = ax.inset_axes([0.01, 0.03, 0.26, 0.26])
    ak.plot(ax=ax_ak, **kw)
    ax_ak.set_axis_off()
    ax_ak.text(0.02, 0.98, "Alaska", transform=ax_ak.transAxes,
               ha="left", va="top", fontsize=7, color="0.35")

    ax_hi = ax.inset_axes([0.27, 0.03, 0.13, 0.13])
    hi.plot(ax=ax_hi, **kw)
    ax_hi.set_axis_off()
    ax_hi.text(0.02, 0.98, "Hawaii", transform=ax_hi.transAxes,
               ha="left", va="top", fontsize=7, color="0.35")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", type=float, help="colour scale half-range in minutes")
    ap.add_argument("--metric", default="offset_annual_mean",
                    choices=["offset_annual_mean", "offset_winter"])
    ap.add_argument("--dpi", type=int, default=170)
    ap.add_argument("--single", action="store_true",
                    help="also write one full-width PNG per regime; the 2x2 grid is "
                         "unreadable on a phone however many pixels it has")
    ap.add_argument("--before-after", action="store_true",
                    help="two-panel today-vs-fitted figure, for leading a post")
    args = ap.parse_args()

    metrics = pd.read_csv(OUT / "metrics.csv", dtype={"GEOID": str})
    geom = load_geometry()

    wide = metrics.pivot_table(index="GEOID", columns="regime", values=args.metric)
    wide.columns = [f"m_{c}" for c in wide.columns]
    gdf = geom.merge(wide.reset_index(), on="GEOID", how="inner")
    print(f"{len(gdf):,} counties joined to geometry")

    conus_mask = ~gdf["STATEFP"].isin(["02", "15"])
    values_conus = gdf.loc[conus_mask, [f"m_{r}" for r in PANEL_ORDER]].to_numpy().ravel()
    values_all = gdf[[f"m_{r}" for r in PANEL_ORDER]].to_numpy().ravel()

    # Fixed symmetric domain, chosen from the CONUS distribution so CONUS
    # variation stays legible, then applied to the insets too.
    if args.domain:
        half = args.domain
    else:
        half = float(np.nanpercentile(np.abs(values_conus), 99.5))
        half = float(np.ceil(half / 15.0) * 15.0)  # round up to a whole quarter-hour
    norm = Normalize(vmin=-half, vmax=half)

    clipped_conus = int(np.nansum(np.abs(values_conus) > half))
    clipped_all = int(np.nansum(np.abs(values_all) > half))
    print(f"colour domain: +/-{half:.0f} min")
    print(f"  clipped: {clipped_conus:,} of {values_conus.size:,} CONUS county-panels, "
          f"{clipped_all:,} of {values_all.size:,} including AK/HI")

    print("projecting…")
    conus = project_and_simplify(gdf[conus_mask], CONUS_CRS)
    hi = project_and_simplify(gdf[gdf["STATEFP"] == "15"], HI_CRS)

    # Clip Alaska in lon/lat *before* projecting. The Aleutian chain crosses the
    # antimeridian, and projecting it first smears the inset right across the
    # frame; a projected-coordinate clip can't cleanly express "west of -170".
    ak_ll = gdf[gdf["STATEFP"] == "02"].cx[-170:-129, 50:72]
    ak = project_and_simplify(ak_ll, AK_CRS)

    states = conus.dissolve(by="STATEFP")

    # Highlight markers, positioned at each county's own centroid in the CONUS
    # projection so they land on the county being labelled.
    marks = conus[conus["GEOID"].isin(HIGHLIGHTS)].copy()
    marks["label"] = marks["GEOID"].map(HIGHLIGHTS)
    cent = marks.geometry.representative_point()
    marks["x"], marks["y"] = cent.x.to_numpy(), cent.y.to_numpy()
    # Hand-placed leader offsets: these three sit close to the map edge and to
    # each other, so automatic placement collides.
    place = {
        # Ontonagon sits high on the map, so pushing the label up collides with
        # the panel title; push left instead. Washington ME is in the top-right
        # corner, so it has to go left too or it runs off the panel.
        "26131": (-52, 4, "right"),
        "18097": (14, -54, "left"),
        "23029": (-16, 34, "right"),
    }
    marks["dx"] = marks["GEOID"].map(lambda g: place[g][0])
    marks["dy"] = marks["GEOID"].map(lambda g: place[g][1])
    marks["ha"] = marks["GEOID"].map(lambda g: place[g][2])

    fig, axes = plt.subplots(2, 2, figsize=(15, 11.5))
    for ax, regime in zip(axes.ravel(), PANEL_ORDER, strict=True):
        draw_panel(ax, conus, ak, hi, f"m_{regime}", norm, REGIME_TITLES[regime],
                   states=states, marks=marks)

    label = ("Annual mean" if args.metric == "offset_annual_mean" else "January mean")
    fig.suptitle(
        "Signed solar offset by county: clock noon minus true solar noon",
        fontsize=15.5, y=0.982,
    )
    fig.text(
        0.5, 0.952,
        f"{label} for 2026, minutes. Negative (blue) = the sun runs late: "
        "late sunrises and late sunsets. Positive (red) = the sun runs early.",
        ha="center", fontsize=10, color="0.3",
    )

    cax = fig.add_axes([0.28, 0.085, 0.44, 0.015])
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=CMAP), cax=cax,
                      orientation="horizontal", extend="both")
    cb.set_label(f"{label} signed solar offset (minutes)", fontsize=9, labelpad=8)
    # Label above the bar: below it, the label and the explanatory note collide.
    cb.ax.xaxis.set_label_position("top")

    # Wrapped by hand: matplotlib's wrap=True measures against the figure width,
    # not this text's own box, so it does not break where it needs to here.
    note_lines = [
        f"Scale fixed at ±{half:.0f} min and shared across all four panels. Permanent DST shifts "
        f"every county by exactly −60 min, which independently scaled panels would hide.",
        f"{clipped_all:,} of {values_all.size:,} county-panel values fall outside the domain and are "
        f"clipped ({clipped_conus:,} of them in the contiguous states).",
        "Panel 4 minimises population-weighted misalignment with a penalty per mismatched county "
        "boundary (CP-SAT, lambda = 1M person-minutes per boundary). Circled counties all sit in "
        "today's Eastern zone.",
    ]
    fig.text(0.5, 0.052, "\n".join(note_lines), ha="center", va="top",
             fontsize=8, color="0.4", linespacing=1.5)

    fig.subplots_adjust(left=0.01, right=0.99, top=0.935, bottom=0.125,
                        wspace=0.01, hspace=0.02)
    dest = OUT / f"signed_solar_offset_four_panel_{args.metric}.png"
    fig.savefig(dest, dpi=args.dpi)
    print(f"wrote {dest.relative_to(ROOT)}  ({args.dpi} dpi)")
    plt.close(fig)

    if args.single:
        # One regime per file, full width. On a phone the 2x2 grid gives each map
        # under half the screen width, which no amount of dpi fixes.
        for i, regime in enumerate(PANEL_ORDER, start=1):
            f1, ax1 = plt.subplots(figsize=(11, 8))
            # Empty in-axes title: the figure suptitle already names the
            # regime, and draw_panel would print it a second time.
            draw_panel(ax1, conus, ak, hi, f"m_{regime}", norm,
                       "", states=states, marks=marks)
            f1.suptitle(
                f"Signed solar offset, {label.lower()} 2026 — {REGIME_TITLES[regime]}",
                fontsize=13, y=0.97,
            )
            c1 = f1.add_axes([0.22, 0.075, 0.56, 0.022])
            cbar = f1.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=CMAP), cax=c1,
                               orientation="horizontal", extend="both")
            cbar.set_label("minutes: negative = sun runs late, positive = sun runs early",
                           fontsize=8.5, labelpad=7)
            cbar.ax.xaxis.set_label_position("top")
            f1.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.13)
            p1 = OUT / f"panel{i}_{regime}_{args.metric}.png"
            f1.savefig(p1, dpi=args.dpi)
            plt.close(f1)
            print(f"  wrote {p1.name}")

    if args.before_after:
        # Two panels, not four. As a lead image the 2x2 grid asks a reader to
        # decode a scale and hold four scenarios at once before they have been
        # told what the metric is; the comparison that carries the argument is
        # just today against a fitted map.
        f2, axs = plt.subplots(1, 2, figsize=(17, 8.2))
        for ax2, regime, head in (
            (axs[0], "cta", "Today"),
            (axs[1], "optimized", "Fitted to the sun"),
        ):
            draw_panel(ax2, conus, ak, hi, f"m_{regime}", norm, "",
                       states=states, marks=marks)
            ax2.text(0.01, 1.01, head, transform=ax2.transAxes, ha="left", va="bottom",
                     fontsize=20, color="#1a1208", fontweight="bold")
        axs[0].text(0.01, 0.965, "current law, with the seasonal switch",
                    transform=axs[0].transAxes, ha="left", va="top",
                    fontsize=11.5, color="#6b6157")
        axs[1].text(0.01, 0.965, "one fixed offset per county, contiguity-penalised",
                    transform=axs[1].transAxes, ha="left", va="top",
                    fontsize=11.5, color="#6b6157")

        f2.suptitle("How far every US county's clock sits from its sun",
                    fontsize=25, x=0.032, ha="left", y=0.985, color="#1a1208")
        f2.text(0.032, 0.905,
                "Blue: the sun runs late, so late sunrises and late sunsets. Red: the sun runs early. "
                "White: the clock agrees with the sun.",
                fontsize=13, color="#6b6157", ha="left")

        c2 = f2.add_axes([0.31, 0.085, 0.38, 0.019])
        cb2 = f2.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=CMAP), cax=c2,
                          orientation="horizontal", extend="both")
        cb2.set_label("minutes between clock noon and true solar noon", fontsize=10, labelpad=8)
        cb2.ax.xaxis.set_label_position("top")
        f2.text(0.5, 0.038,
                "Annual mean, 2026. The fitted map also drops the seasonal switch, so the difference "
                "shown is both changes together. Alaska and Hawaii inset on the same scale.",
                ha="center", fontsize=9, color="#6b6157")

        f2.subplots_adjust(left=0.01, right=0.99, top=0.87, bottom=0.14, wspace=0.02)
        dest2 = OUT / f"fig_c_before_after_{args.metric}.png"
        f2.savefig(dest2, dpi=args.dpi, facecolor="white")
        plt.close(f2)
        print(f"wrote {dest2.name}")

    meta_path = OUT / "map_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta[args.metric] = {
        "colour_domain_min": [-half, half],
        "cmap": CMAP,
        "clipped_county_panels": clipped_all,
        "total_county_panels": int(values_all.size),
        "conus_crs": CONUS_CRS, "ak_crs": AK_CRS, "hi_crs": HI_CRS,
        "simplify_m": SIMPLIFY_M,
        "panels": PANEL_ORDER,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {meta_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
