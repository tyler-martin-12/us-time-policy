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
    "ideal_unconstrained": "4. Per-county ideal (unconstrained)",
}
PANEL_ORDER = ["cta", "perm_st", "perm_dst", "ideal_unconstrained"]

CMAP = "RdBu_r"  # low (sun late) -> blue, zero -> white, high (sun early) -> red


def load_geometry() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(f"zip://{RAW / 'tl_2020_us_county.zip'}")
    return gdf[["GEOID", "STATEFP", "geometry"]]


def project_and_simplify(gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    out = gdf.to_crs(crs)
    out["geometry"] = out.geometry.simplify(SIMPLIFY_M, preserve_topology=True)
    return out


def draw_panel(ax, conus, ak, hi, column: str, norm, title: str) -> None:
    kw = dict(column=column, cmap=CMAP, norm=norm, linewidth=0, edgecolor="none")
    conus.plot(ax=ax, **kw)
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

    fig, axes = plt.subplots(2, 2, figsize=(15, 11.5))
    for ax, regime in zip(axes.ravel(), PANEL_ORDER, strict=True):
        draw_panel(ax, conus, ak, hi, f"m_{regime}", norm, REGIME_TITLES[regime])

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
        "Panel 4 is the unconstrained per-county ideal, round(longitude / 15) — a reference point, "
        "not the contiguity-constrained optimisation.",
    ]
    fig.text(0.5, 0.052, "\n".join(note_lines), ha="center", va="top",
             fontsize=8, color="0.4", linespacing=1.5)

    fig.subplots_adjust(left=0.01, right=0.99, top=0.935, bottom=0.125,
                        wspace=0.01, hspace=0.02)
    dest = OUT / f"signed_solar_offset_four_panel_{args.metric}.png"
    fig.savefig(dest, dpi=170)
    print(f"wrote {dest.relative_to(ROOT)}")

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
