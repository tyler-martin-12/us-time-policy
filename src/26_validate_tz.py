"""Cross-check the time zone layer against the legal boundaries (NOTES.md §6a).

The pipeline resolves each county's zone with `timezonefinder`, which returns
IANA zone *names* but whose polygons come from OpenStreetMap's
timezone-boundary-builder. Those polygons encode **observed practice**. The
Department of Transportation publishes the **legal** boundaries, digitised from
49 CFR Part 71 by DOT's Office of General Counsel. The two disagree, and the
disagreement is not a bug in either.

Observed practice is the right input here, and deliberately so. The metric is
how far a person's clock sits from their sun, so what matters is the clock they
actually read. Phenix City in Russell County, Alabama is legally Central and
runs on Eastern because it is part of the Columbus, Georgia economy, along with
a radius of surrounding towns. Modelling those people on Central time would put
a clock in their kitchen that nobody there uses.

It cuts both ways, which is why this script reports rather than corrects. In
Chambers County only Lanett and Valley, on the Georgia edge, keep Eastern, so
assigning the whole county to Eastern is arguably worse than the legal answer.
Neither layer is uniformly right for every county, the affected population is
around 94,000, and the national figures do not move. Saying that is better than
picking a side silently.

This is not part of the pipeline. It downloads a layer the project does not
otherwise use, so it runs on request, and its output is committed so a reader
can see the answer without running it.

Usage:
    uv run src/26_validate_tz.py
    uv run src/26_validate_tz.py --force-download
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
COMMITTED = ROOT / "data" / "committed"

DOT_GEOJSON = RAW / "dot_time_zones.geojson"
DOT_URL = (
    "https://services.arcgis.com/xOi1kZaI0eWDREZv/ArcGIS/rest/services/"
    "NTAD_Time_Zones/FeatureServer/0/query"
    "?where=1%3D1&outFields=zone,utc&returnGeometry=true&outSR=4326&f=geojson"
)
DOT_CITATION = (
    "USDOT/BTS National Transportation Atlas Database, Time Zones layer, "
    "digitised from 49 CFR Part 71 by USDOT Office of General Counsel."
)
TIMEOUT = 120


def fetch_dot(force: bool = False) -> Path:
    if DOT_GEOJSON.exists() and not force:
        print(f"cached {DOT_GEOJSON.relative_to(ROOT)}")
        return DOT_GEOJSON
    print(f"downloading DOT time zone polygons…\n  {DOT_URL}")
    RAW.mkdir(parents=True, exist_ok=True)
    response = requests.get(DOT_URL, timeout=TIMEOUT)
    response.raise_for_status()
    DOT_GEOJSON.write_bytes(response.content)
    digest = hashlib.sha256(response.content).hexdigest()
    print(f"  {len(response.content):,} bytes, sha256 {digest[:12]}…")
    return DOT_GEOJSON


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force-download", action="store_true")
    args = ap.parse_args()

    COMMITTED.mkdir(parents=True, exist_ok=True)
    fetch_dot(force=args.force_download)

    dot = gpd.read_file(DOT_GEOJSON)
    # "-05:00" is the zone's standard offset, which is what std_offset_h holds.
    dot["dot_std_offset_h"] = dot["utc"].str.slice(0, 3).astype(int)
    print(f"\nDOT layer: {len(dot)} zones")
    print(dot[["zone", "utc", "dot_std_offset_h"]].to_string(index=False))

    counties = pd.read_parquet(INTERIM / "counties.parquet")
    points = gpd.GeoDataFrame(
        counties[["GEOID", "county", "state", "tz_name", "std_offset_h", "pop_weight"]],
        geometry=[Point(x, y) for x, y in
                  zip(counties["cenpop_lon"], counties["cenpop_lat"], strict=True)],
        crs="EPSG:4326",
    )

    joined = gpd.sjoin(
        points, dot[["zone", "dot_std_offset_h", "geometry"]],
        how="left", predicate="within",
    ).drop(columns="index_right")
    # A county centre can land in two polygons where they share an edge, or in
    # none where the digitised coastline clips it. Both are layer artefacts
    # rather than findings, so they are reported separately from real conflicts.
    duplicated = joined.index.duplicated(keep="first")
    if duplicated.any():
        print(f"\n{int(duplicated.sum())} county centres fell in more than one DOT "
              "polygon (shared edges); keeping the first")
        joined = joined[~duplicated]

    uncovered = joined[joined["dot_std_offset_h"].isna()]
    print(f"\n{len(uncovered)} county centres are not inside any DOT polygon:")
    if len(uncovered):
        print(uncovered[["GEOID", "county", "state", "tz_name", "std_offset_h"]]
              .to_string(index=False))

    covered = joined[joined["dot_std_offset_h"].notna()].copy()
    covered["dot_std_offset_h"] = covered["dot_std_offset_h"].astype(int)
    conflict = covered[covered["dot_std_offset_h"] != covered["std_offset_h"].astype(int)]

    print(f"\n{len(conflict)} counties where observed practice and the law disagree, "
          f"{int(conflict['pop_weight'].sum()):,} people "
          f"({100 * conflict['pop_weight'].sum() / counties['pop_weight'].sum():.3f}% "
          "of the population):")
    if len(conflict):
        print(conflict[["GEOID", "county", "state", "tz_name", "std_offset_h",
                        "zone", "dot_std_offset_h", "pop_weight"]].to_string(index=False))

    # Sensitivity. The proxy misalignment is 4*lon - 60*offset, so switching a
    # county's offset by an hour moves it by exactly 60 minutes; what matters is
    # the population-weighted national figure, and whether it moves at all.
    lon = counties.set_index("GEOID")["cenpop_lon"]
    pop = counties.set_index("GEOID")["pop_weight"].astype(float)
    ours = counties.set_index("GEOID")["std_offset_h"].astype(float)
    theirs = ours.copy()
    theirs.loc[conflict["GEOID"]] = conflict.set_index("GEOID")["dot_std_offset_h"].astype(float)

    def pw(offsets: pd.Series) -> float:
        return float(np.average(np.abs(4.0 * lon - 60.0 * offsets), weights=pop))

    a, b = pw(ours), pw(theirs)
    print("\npopulation-weighted mean |misalignment| under today's map, "
          "standard time, proxy metric:")
    print(f"  observed practice (published) {a:.4f} min")
    print(f"  legal boundaries (DOT)        {b:.4f} min")
    print(f"  difference                    {b - a:+.4f} min = {(b - a) * 60:+.2f} s")

    out = conflict[["GEOID", "county", "state", "tz_name", "std_offset_h",
                    "zone", "dot_std_offset_h", "pop_weight"]].copy()
    out = out.rename(columns={"std_offset_h": "observed_std_offset_h",
                              "zone": "dot_zone"})
    out.to_csv(COMMITTED / "tz_dot_diff.csv", index=False)

    (COMMITTED / "tz_dot_meta.json").write_text(
        json.dumps(
            {
                "purpose": "cross-check only; the pipeline uses observed practice",
                "published_layer":
                    "OpenStreetMap timezone-boundary-builder via timezonefinder, "
                    "queried at each county's centre of population",
                "comparison_layer": DOT_CITATION,
                "comparison_url": DOT_URL,
                "n_counties_conflicting": int(len(conflict)),
                "population_conflicting": int(conflict["pop_weight"].sum()),
                "n_centres_not_covered_by_dot": int(len(uncovered)),
                "counties_not_covered": uncovered["GEOID"].tolist(),
                "pw_mean_abs_offset_min_observed": round(a, 4),
                "pw_mean_abs_offset_min_legal": round(b, 4),
                "difference_seconds": round((b - a) * 60, 2),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {(COMMITTED / 'tz_dot_diff.csv').relative_to(ROOT)} and "
          f"{(COMMITTED / 'tz_dot_meta.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
