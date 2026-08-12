"""Check the published map without re-running the solver.

This is the reproducibility guarantee the project actually offers, and it is a
stronger one than a deterministic solve. Re-deriving a CP-SAT search depends on
the OR-Tools version, the worker count and the machine; checking a committed
assignment depends on none of those. Everything published about the map is
recomputed here from `data/committed/optimized_offsets.csv` and the county
table, and compared against `optimize_meta.json`.

What this proves, and it is the whole claim:

  There exists a whole-hour per-county offset map with no more mismatched
  county borders than today's map, whose population-weighted mean distance
  from solar noon is the figure printed below.

That is a constructive claim. The witness is the committed CSV. The solver's
optimality gap bounds how much *better* some other tidy map might be; it has no
bearing on whether this one exists, so a 2% gap costs the argument nothing.

What this does not prove: that the published map is the best possible map
within the border budget. Nothing in the project claims that.

Usage:
    uv run src/verify_solution.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from assignment_stats import MMIN_PER_HOUR, CountyGraph, describe, ideal_mmin

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
COMMITTED = ROOT / "data" / "committed"


def main() -> int:
    counties = pd.read_parquet(INTERIM / "counties.parquet")
    adj = pd.read_parquet(INTERIM / "adjacency.parquet")
    graph = CountyGraph(counties["GEOID"].tolist(), adj)
    ideal = ideal_mmin(counties["cenpop_lon"].to_numpy())
    pop = counties["pop_weight"].fillna(0).to_numpy().astype(np.int64)

    meta = json.loads((COMMITTED / "optimize_meta.json").read_text())
    published = pd.read_csv(
        COMMITTED / "optimized_offsets.csv", dtype={"GEOID": str}
    ).set_index("GEOID")["offset_h"]

    today = counties.set_index("GEOID")["std_offset_h"].astype(int)
    today_stats = describe(graph, today, ideal, pop)
    naive = pd.Series(
        np.round(ideal / MMIN_PER_HOUR).astype(int), index=counties["GEOID"]
    )
    naive_stats = describe(graph, naive, ideal, pop)
    got = describe(graph, published, ideal, pop)

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str) -> None:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}: {detail}")
        if not ok:
            failures.append(label)

    print("covering the country")
    check("every county assigned", len(published) == graph.n,
          f"{len(published)} of {graph.n}")
    check("offsets are whole hours", published.map(float).eq(published.astype(int)).all(),
          f"{got['distinct_offsets']} distinct values")

    print("\nmatching what was published")
    check("assignment hash", got["sha256"] == meta["published_sha256"],
          got["sha256"][:16] + "…")

    print("\nthe claim")
    budget = meta["published_budget"]
    check("border budget is today's count", budget == today_stats["mismatched_boundaries"],
          f"budget {budget}, today {today_stats['mismatched_boundaries']}")
    check("published map is within budget", got["mismatched_boundaries"] <= budget,
          f"{got['mismatched_boundaries']} <= {budget}")
    check("published map beats today on alignment",
          got["pw_mean_abs_offset_min"] < today_stats["pw_mean_abs_offset_min"],
          f"{got['pw_mean_abs_offset_min']:.4f} < {today_stats['pw_mean_abs_offset_min']:.4f} min")
    # round(lon/15) ignores contiguity entirely, so it is a valid lower bound on
    # what any assignment can achieve, budget or no budget.
    cost = got["pw_mean_abs_offset_min"] - naive_stats["pw_mean_abs_offset_min"]
    check("tidiness cost is non-negative", cost >= 0,
          f"{cost:.4f} min = {cost * 60:.2f} s above the unconstrained optimum")

    print("\nreported alongside, not constrained")
    for key in ("n_regions", "n_enclave_counties", "n_islands"):
        print(f"  today {key:20s} {today_stats[key]:>5}   published {got[key]:>5}")

    # The two measurement systems, reconciled. The optimiser scores on the
    # proxy 4*lon; `30_metrics.py` integrates real solar position over all 365
    # days. They are close but not identical, and they used to disagree about
    # what the unconstrained baseline even *was*: metrics used round(lon/15)
    # while the optimiser's lambda=0 returned a different member of a tied
    # optimum. With the ties gone they agree on the assignment, which is
    # asserted here rather than assumed.
    metrics_path = ROOT / "data" / "out" / "metrics.csv"
    if metrics_path.exists():
        print("\nagainst the real-solar metrics, which is what the write-up quotes")
        metrics = pd.read_csv(metrics_path)
        by_regime = {}
        for regime in ("ideal_unconstrained", "optimized", "perm_st"):
            rows = metrics[metrics["regime"] == regime]
            if len(rows) == 0:
                continue
            by_regime[regime] = float(np.average(
                rows["offset_annual_mean"].abs(), weights=rows["pop_weight"]
            ))
        if "ideal_unconstrained" in by_regime and "optimized" in by_regime:
            metrics_cost = by_regime["optimized"] - by_regime["ideal_unconstrained"]
            check("metrics agrees with the proxy on the sign of the cost",
                  (metrics_cost >= 0) == (cost >= 0),
                  f"metrics {metrics_cost * 60:.2f} s, proxy {cost * 60:.2f} s")
            check("the two systems agree to within a quarter second",
                  abs(metrics_cost - cost) * 60 < 0.25,
                  f"difference {abs(metrics_cost - cost) * 60:.2f} s")
            print(f"  metrics-system tidiness cost: {metrics_cost:.4f} min "
                  f"= {metrics_cost * 60:.2f} s  <- quote this one")
        if "perm_st" in by_regime and "optimized" in by_regime:
            gain = by_regime["perm_st"] - by_regime["optimized"]
            print(f"  redrawing gains the average American {gain:.2f} min "
                  "against permanent standard time")
    else:
        print("\n(no metrics.csv yet; run 30_metrics.py for the real-solar figures)")

    print("\n--- summary ---")
    print(f"unconstrained optimum   {naive_stats['pw_mean_abs_offset_min']:.4f} min "
          f"({naive_stats['mismatched_boundaries']} borders, "
          f"{naive_stats['n_regions']} regions)")
    print(f"published map           {got['pw_mean_abs_offset_min']:.4f} min "
          f"({got['mismatched_boundaries']} borders, {got['n_regions']} regions)")
    print(f"today's map             {today_stats['pw_mean_abs_offset_min']:.4f} min "
          f"({today_stats['mismatched_boundaries']} borders, "
          f"{today_stats['n_regions']} regions)")
    print(f"\ncost of staying as tidy as today: {cost:.4f} min = {cost * 60:.2f} seconds")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
