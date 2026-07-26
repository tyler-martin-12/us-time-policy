"""Stage 1: build the one-row-per-county base table.

Joins boundaries, center of population, population weight and IANA time zone
into data/interim/counties.parquet, and flags counties that straddle a zone
boundary into data/out/split_counties.csv.

This is the only place a county's point location and zone are decided. Every
later stage takes them as given, so the decisions here (NOTES.md §5, §6) are
load-bearing:
  - The point is the 2020 *center of population*, not a geometric centroid.
  - The zone is whatever timezonefinder returns at that point. No hand-kept
    exception list, so Arizona, the Navajo Nation and split counties all resolve
    from geometry.

Usage:
    uv run src/10_counties.py
    uv run src/10_counties.py --force        # rebuild even if output exists
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from timezonefinder import TimezoneFinder

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "out"

COUNTIES_PARQUET = INTERIM / "counties.parquet"
SPLIT_CSV = OUT / "split_counties.csv"

MODEL_YEAR = 2026
# A date on which no US zone is in DST, so the zone's offset here *is* its
# standard offset (NOTES.md §4). Arizona and Hawaii are unaffected by the choice.
STANDARD_OFFSET_PROBE = datetime(MODEL_YEAR, 1, 15, 12)
DST_PROBE = datetime(MODEL_YEAR, 7, 15, 12)

# Territory state FIPS. Out of scope for the baseline (NOTES.md §5): not in the
# same state-based county series, and they add nothing to an argument about the
# contiguous zone structure. PR (72) comes back behind --include-pr.
TERRITORY_FIPS = {"60", "66", "69", "74", "78"}
PR_FIPS = "72"

# Split-county detection: grid resolution inside each county's bounding box.
SPLIT_GRID = 7


def load_boundaries() -> gpd.GeoDataFrame:
    zip_path = RAW / "tl_2020_us_county.zip"
    gdf = gpd.read_file(f"zip://{zip_path}")
    gdf = gdf[["GEOID", "STATEFP", "COUNTYFP", "NAME", "NAMELSAD", "ALAND", "geometry"]]
    return gdf.rename(columns={"NAME": "county", "NAMELSAD": "county_long"})


def load_centers() -> pd.DataFrame:
    # utf-8-sig: the file carries a BOM. Coordinates are zero-padded and signed
    # ("+32.500194", "-086.487813"), which pandas parses as float fine.
    df = pd.read_csv(
        RAW / "CenPop2020_Mean_CO.txt",
        dtype={"STATEFP": str, "COUNTYFP": str},
        encoding="utf-8-sig",
    )
    df["GEOID"] = df["STATEFP"] + df["COUNTYFP"]
    return df.rename(
        columns={
            "LATITUDE": "cenpop_lat",
            "LONGITUDE": "cenpop_lon",
            "POPULATION": "pop_2020_census",
            "STNAME": "state",
        }
    )[["GEOID", "state", "cenpop_lat", "cenpop_lon", "pop_2020_census"]]


def load_population() -> pd.DataFrame:
    df = pd.read_csv(RAW / "co-est2025-alldata.csv", encoding="latin-1")
    df = df[df["SUMLEV"] == 50]  # 050 = county; 040 rows are state totals
    df["GEOID"] = (
        df["STATE"].astype(int).astype(str).str.zfill(2)
        + df["COUNTY"].astype(int).astype(str).str.zfill(3)
    )
    return df[["GEOID", "POPESTIMATE2025"]].rename(columns={"POPESTIMATE2025": "pop_2025_est"})


def zone_offsets(zone_name: str) -> tuple[float, float, bool]:
    """(standard offset hours, summer offset hours, observes DST) for a zone."""
    tz = ZoneInfo(zone_name)
    std = STANDARD_OFFSET_PROBE.replace(tzinfo=tz).utcoffset()
    summer = DST_PROBE.replace(tzinfo=tz).utcoffset()
    std_h = std.total_seconds() / 3600
    summer_h = summer.total_seconds() / 3600
    return std_h, summer_h, std_h != summer_h


def detect_split(gdf: gpd.GeoDataFrame, tf: TimezoneFinder) -> pd.DataFrame:
    """Sample a grid inside each county and record every distinct zone found.

    Reported rather than assumed: a county gets one zone (from its center of
    population), so any county appearing here has metrics describing only the
    zone its population centre falls in.
    """
    rows = []
    geoms = gdf.geometry.to_numpy()
    for geoid, name, state, geom in zip(
        gdf["GEOID"], gdf["county"], gdf["state"], geoms, strict=True
    ):
        minx, miny, maxx, maxy = geom.bounds
        xs = np.linspace(minx, maxx, SPLIT_GRID)
        ys = np.linspace(miny, maxy, SPLIT_GRID)
        gx, gy = np.meshgrid(xs, ys)
        gx, gy = gx.ravel(), gy.ravel()
        inside = shapely.contains_xy(geom, gx, gy)
        px, py = gx[inside], gy[inside]
        if len(px) == 0:
            # Slivers and tiny islands can miss every grid point.
            rep = geom.representative_point()
            px, py = np.array([rep.x]), np.array([rep.y])

        found: dict[str, int] = {}
        for x, y in zip(px, py, strict=True):
            z = tf.timezone_at(lng=float(x), lat=float(y))
            if z:
                found[z] = found.get(z, 0) + 1
        if len(found) > 1:
            rows.append(
                {
                    "GEOID": geoid,
                    "county": name,
                    "state": state,
                    "zones_detected": "|".join(sorted(found)),
                    "n_zones": len(found),
                    "n_sample_points": int(len(px)),
                    "n_points_per_zone": "|".join(
                        f"{z}={found[z]}" for z in sorted(found)
                    ),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--include-pr", action="store_true", help="include Puerto Rico's municipios"
    )
    args = ap.parse_args()

    INTERIM.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    if COUNTIES_PARQUET.exists() and not args.force:
        existing = pd.read_parquet(COUNTIES_PARQUET)
        print(f"cached: {COUNTIES_PARQUET.relative_to(ROOT)} ({len(existing):,} counties)")
        print("use --force to rebuild")
        return 0

    print("reading boundaries…")
    gdf = load_boundaries()
    print(f"  {len(gdf):,} county records in TIGER")

    drop = set(TERRITORY_FIPS)
    if not args.include_pr:
        drop.add(PR_FIPS)
    gdf = gdf[~gdf["STATEFP"].isin(drop)].copy()
    print(f"  {len(gdf):,} after dropping {sorted(drop)}")

    centers = load_centers()
    pop = load_population()

    df = gdf.merge(centers, on="GEOID", how="left").merge(pop, on="GEOID", how="left")

    missing_center = df["cenpop_lat"].isna().sum()
    if missing_center:
        print(f"  ! {missing_center} counties with no center of population")
        print(df.loc[df["cenpop_lat"].isna(), ["GEOID", "county"]].to_string(index=False))

    # The canonical weight is the 2020 census count, not the 2025 estimate.
    # Reason (NOTES.md §5): Connecticut abolished its counties for statistical
    # purposes, so vintage 2025 reports 9 planning regions under new FIPS codes
    # that do not nest into the 2020 county boundaries this pipeline uses. Those 8
    # counties therefore have no 2025 estimate and cannot be backfilled by
    # aggregation. Using the 2020 count keeps boundaries, point locations and
    # weights all on one vintage with no gaps; the estimate is kept alongside as a
    # sensitivity column.
    df["pop_weight"] = df["pop_2020_census"]
    missing_est = df["pop_2025_est"].isna()
    if missing_est.any():
        print(
            f"  {missing_est.sum()} counties have no 2025 estimate "
            "(boundary change, see NOTES.md §5); weighting uses the 2020 count throughout"
        )
        print(
            df.loc[missing_est, ["GEOID", "county", "state"]].to_string(index=False)
        )

    print("resolving time zones at centers of population…")
    tf = TimezoneFinder(in_memory=True)
    df["tz_name"] = [
        tf.timezone_at(lng=float(lon), lat=float(lat))
        for lon, lat in zip(df["cenpop_lon"], df["cenpop_lat"], strict=True)
    ]
    unresolved = df["tz_name"].isna().sum()
    if unresolved:
        print(f"  ! {unresolved} counties with no zone resolved")

    offs = df["tz_name"].map(lambda z: zone_offsets(z) if isinstance(z, str) else (np.nan,) * 3)
    df["std_offset_h"] = [o[0] for o in offs]
    df["summer_offset_h"] = [o[1] for o in offs]
    df["observes_dst"] = [o[2] for o in offs]

    # The offset that would put solar noon exactly at clock noon, unrounded.
    # Stage 2's optimiser rounds this; here it is just a diagnostic.
    df["ideal_offset_h"] = df["cenpop_lon"] / 15.0

    print("detecting split counties…")
    split = detect_split(df, tf)
    split.to_csv(SPLIT_CSV, index=False)
    if len(split):
        split_pop = df.loc[df["GEOID"].isin(split["GEOID"]), "pop_weight"].sum()
        total_pop = df["pop_weight"].sum()
        print(
            f"  {len(split)} counties span >1 zone, "
            f"{split_pop:,.0f} people ({split_pop / total_pop:.2%} of total)"
        )
        print(f"  -> {SPLIT_CSV.relative_to(ROOT)}")

    keep = [
        "GEOID", "county", "county_long", "state", "STATEFP", "COUNTYFP",
        "cenpop_lat", "cenpop_lon", "pop_weight", "pop_2020_census", "pop_2025_est",
        "tz_name", "std_offset_h", "summer_offset_h", "observes_dst",
        "ideal_offset_h", "ALAND",
    ]
    out = pd.DataFrame(df[keep])
    out.to_parquet(COUNTIES_PARQUET, index=False)

    print(f"\nwrote {COUNTIES_PARQUET.relative_to(ROOT)}: {len(out):,} counties")
    print(f"  zones: {out['tz_name'].nunique()}")
    print(f"  population (2020 census, the weight): {out['pop_weight'].sum():,.0f}")
    print("\nzone breakdown:")
    breakdown = (
        out.groupby("tz_name")
        .agg(counties=("GEOID", "size"), pop=("pop_weight", "sum"),
             std_off=("std_offset_h", "first"), dst=("observes_dst", "first"))
        .sort_values("pop", ascending=False)
    )
    print(breakdown.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
