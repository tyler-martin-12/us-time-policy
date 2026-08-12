"""Stage 5b: the region and enclave comparison table (NOTES.md §13).

This table was previously computed by hand in a scratch session and typed into
NOTES.md, and two of its numbers reached the blog post. Nothing in `src/`
regenerated it, so nothing could contradict it. This script is that missing
step.

Only three distinct *partitions* of the country exist across the regimes:

- today's zone map, shared by `cta`, `perm_st` and `perm_dst`, since a uniform
  hour applied everywhere moves every county and merges no boundary;
- `round(lon/15)`, the unconstrained per-county optimum;
- the published budget-form solution.

So the table has three rows, not five, and saying why is part of the point.

Usage:
    uv run src/55_regions.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from assignment_stats import MMIN_PER_HOUR, CountyGraph, describe, ideal_mmin, region_stats

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
COMMITTED = ROOT / "data" / "committed"

REPORT_COLUMNS = [
    "assignment", "pw_mean_abs_offset_min", "distinct_offsets",
    "mismatched_boundaries", "pct_boundaries_mismatched",
    "n_regions", "n_mainland_offsets", "excess_regions",
    "n_enclave_counties", "n_islands", "sha256",
]


def main() -> int:
    counties = pd.read_parquet(INTERIM / "counties.parquet")
    adj = pd.read_parquet(INTERIM / "adjacency.parquet")
    graph = CountyGraph(counties["GEOID"].tolist(), adj)
    ideal = ideal_mmin(counties["cenpop_lon"].to_numpy())
    pop = counties["pop_weight"].fillna(0).to_numpy().astype(np.int64)

    optimized = pd.read_csv(
        COMMITTED / "optimized_offsets.csv", dtype={"GEOID": str}
    ).set_index("GEOID")["offset_h"]

    assignments = {
        "today (zone map, all three uniform regimes)":
            counties.set_index("GEOID")["std_offset_h"].astype(int),
        "unconstrained per-county optimum, round(lon/15)":
            pd.Series(np.round(ideal / MMIN_PER_HOUR).astype(int), index=counties["GEOID"]),
        "published, at most today's border count":
            optimized,
    }

    rows = []
    for label, offsets in assignments.items():
        stats = describe(graph, offsets, ideal, pop)
        stats["assignment"] = label
        rows.append(stats)

    table = pd.DataFrame(rows)[REPORT_COLUMNS]
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    table.to_csv(COMMITTED / "regions.csv", index=False)
    print(f"\nwrote {(COMMITTED / 'regions.csv').relative_to(ROOT)}")

    # Which counties are actually stranded, and whether any of them is a real
    # enclave rather than an island. Today's map scores three "enclaves" only
    # because Hawaii has no land neighbours; excluding islands, it strands none.
    print("\n--- enclave counties, islands already excluded ---")
    for label, offsets in assignments.items():
        off = graph.align(offsets)
        mask = region_stats(graph, off)["enclave_mask"]
        named = counties.loc[mask, ["county", "state"]]
        if len(named) == 0:
            print(f"{label}: none")
        else:
            listing = ", ".join(f"{r.county} ({r.state})" for r in named.itertuples())
            print(f"{label}: {len(named)} -- {listing}")
    print(f"\nislands, unconstrained under every assignment: {graph.n_islands}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
