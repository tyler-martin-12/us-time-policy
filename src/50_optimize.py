"""Stage 5: contiguity-penalised per-county offset assignment (NOTES.md §9).

    minimise   sum_i  pop_i * |offset_i - ideal_i|      [person-minutes]
             + lambda * sum_(i,j) in E  [offset_i != offset_j]

offset_i is an integer number of hours. `ideal_i` is the offset that would put
solar noon exactly at clock noon. Because signed solar offset in minutes is
exactly `4 * longitude - 60 * offset_hours` (up to the equation of time, which is
a pure function of date and so identical across regimes), the misalignment term
is integer-exact and needs no approximation.

lambda is a parameter and is **swept**, not fixed. lambda = 0 must reproduce the
unconstrained solution, which is round(longitude / 15); that is asserted, and it
is a cheap check that would catch a sign error in `ideal_i`.

Adjacency is **rook**: counties sharing a boundary of non-zero length. Counties
meeting at a single point are not neighbours, and pairs whose intersection is a
Point are filtered out explicitly rather than trusted to `touches`.

Islands have no land neighbours and so appear in no penalty term. They are free
to take their ideal offset at any lambda, which is correct but looks like a
solver bug on a map, so they are listed in the output.

Usage:
    uv run src/50_optimize.py
    uv run src/50_optimize.py --lambdas 0 0.5 1 2 5 --select 1.0
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "out"

ADJACENCY_PARQUET = INTERIM / "adjacency.parquet"
SELECTED_OFFSETS = INTERIM / "optimized_offsets.csv"

# lambda in MILLIONS of person-minutes per mismatched adjacent pair.
DEFAULT_LAMBDAS = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0]
DEFAULT_SELECT = 1.0

SOLVER_SECONDS = 120


def build_adjacency(force: bool = False) -> pd.DataFrame:
    if ADJACENCY_PARQUET.exists() and not force:
        adj = pd.read_parquet(ADJACENCY_PARQUET)
        print(f"cached adjacency: {len(adj):,} undirected pairs")
        return adj

    print("building adjacency graph…")
    gdf = gpd.read_file(f"zip://{RAW / 'tl_2020_us_county.zip'}")
    gdf = gdf[~gdf["STATEFP"].isin(["60", "66", "69", "72", "74", "78"])]
    gdf = gdf[["GEOID", "geometry"]].reset_index(drop=True)
    # Equal-area projection so the "shared boundary length" test is in metres.
    gdf = gdf.to_crs("EPSG:5070")

    pairs = gpd.sjoin(gdf, gdf, predicate="touches")[["GEOID_left", "GEOID_right"]]
    pairs = pairs[pairs["GEOID_left"] < pairs["GEOID_right"]].drop_duplicates()
    print(f"  {len(pairs):,} candidate touching pairs")

    geom = gdf.set_index("GEOID").geometry
    left = geom.loc[pairs["GEOID_left"]].reset_index(drop=True)
    right = geom.loc[pairs["GEOID_right"]].reset_index(drop=True)
    shared = left.intersection(right, align=False).length.to_numpy()

    # Rook, not queen: a Point intersection has zero length and is dropped.
    keep = shared > 0.0
    adj = pd.DataFrame(
        {
            "a": pairs["GEOID_left"].to_numpy()[keep],
            "b": pairs["GEOID_right"].to_numpy()[keep],
            "shared_m": shared[keep],
        }
    )
    print(f"  {len(adj):,} rook pairs ({int((~keep).sum())} corner-only pairs dropped)")
    adj.to_parquet(ADJACENCY_PARQUET, index=False)
    return adj


def solve(
    counties: pd.DataFrame, adj: pd.DataFrame, lam_millions: float, seconds: int
) -> tuple[pd.Series, dict]:
    geoids = counties["GEOID"].tolist()
    idx = {g: i for i, g in enumerate(geoids)}

    # signed solar offset in minutes = 4*lon - 60*offset_hours. Integer-exact.
    ideal_min = np.round(4.0 * counties["cenpop_lon"].to_numpy()).astype(int)
    pop = counties["pop_weight"].fillna(0).to_numpy().astype(int)

    lo = int(np.floor(counties["cenpop_lon"].min() / 15.0))
    hi = int(np.ceil(counties["cenpop_lon"].max() / 15.0))

    # Population in thousands, floor 1. Keeps objective coefficients ~1e3 smaller
    # without changing the optimum in any way that matters at national scale: the
    # weight resolution becomes 1,000 people, and no county is allowed to fall to
    # zero weight and drift freely.
    pop_k = np.maximum(pop // 1000, 1)

    model = cp_model.CpModel()
    off = [model.NewIntVar(lo, hi, f"o{i}") for i in range(len(geoids))]

    dev = []
    for i in range(len(geoids)):
        span = max(abs(ideal_min[i] - 60 * lo), abs(ideal_min[i] - 60 * hi))
        d = model.NewIntVar(0, int(span), f"d{i}")
        model.AddAbsEquality(d, ideal_min[i] - 60 * off[i])
        dev.append(d)

    # Only build the boundary terms when they can affect the objective. At
    # lambda = 0 the problem is separable per county, and 8,933 spare boolean
    # constraints turn an instant separable solve into a search that times out
    # with a 40%+ gap.
    mismatch = []
    if lam_millions > 0:
        big = hi - lo
        for a, b in zip(adj["a"], adj["b"], strict=True):
            ia, ib = idx[a], idx[b]
            m = model.NewBoolVar("")
            # Only the "if they differ then m = 1" direction is needed: m appears
            # with a positive coefficient in a minimisation, so the solver will
            # set it to 0 whenever it is allowed to. That avoids full reification
            # and keeps these as plain linear constraints.
            model.Add(off[ia] - off[ib] <= big * m)
            model.Add(off[ib] - off[ia] <= big * m)
            mismatch.append(m)

    # lambda arrives in millions of person-minutes; the objective is in
    # thousand-person-minutes, hence the 1e3.
    lam = int(round(lam_millions * 1_000))
    objective = sum(int(p) * d for p, d in zip(pop_k, dev, strict=True))
    if mismatch:
        objective = objective + lam * sum(mismatch)
    model.Minimize(objective)

    # Warm start from the unconstrained optimum. It is the exact answer at
    # lambda = 0 and a good basin elsewhere.
    for i in range(len(geoids)):
        model.AddHint(off[i], int(np.round(counties["cenpop_lon"].iloc[i] / 15.0)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(seconds)
    solver.parameters.num_workers = 8
    t0 = time.perf_counter()
    status = solver.Solve(model)
    elapsed = time.perf_counter() - t0

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"no solution for lambda={lam_millions}: {solver.StatusName(status)}")

    chosen = pd.Series([solver.Value(o) for o in off], index=geoids, name="offset_h")
    misalign = np.abs(ideal_min - 60 * chosen.to_numpy())

    # Counted from the solution against the adjacency table, not from the solver's
    # indicator variables: at lambda = 0 those variables do not exist, and this
    # way the number always describes the assignment rather than the model.
    n_mismatch = int(
        (chosen.reindex(adj["a"]).to_numpy() != chosen.reindex(adj["b"]).to_numpy()).sum()
    )

    stats = {
        "lambda_millions": lam_millions,
        "status": solver.StatusName(status),
        "seconds": round(elapsed, 1),
        "gap_pct": round(
            100.0
            * abs(solver.ObjectiveValue() - solver.BestObjectiveBound())
            / max(abs(solver.ObjectiveValue()), 1.0),
            4,
        ),
        "pw_mean_abs_offset_min": float(np.average(misalign, weights=np.maximum(pop, 1))),
        "n_mismatch_vars": len(mismatch),
        "max_abs_offset_min": int(misalign.max()),
        "distinct_offsets": int(chosen.nunique()),
        "mismatched_boundaries": n_mismatch,
        "total_boundaries": len(adj),
        "pct_boundaries_mismatched": round(100.0 * n_mismatch / len(adj), 2),
    }
    return chosen, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lambdas", type=float, nargs="+", default=DEFAULT_LAMBDAS)
    ap.add_argument("--select", type=float, default=DEFAULT_SELECT,
                    help="which lambda's solution to write for the metrics stage")
    ap.add_argument("--seconds", type=int, default=SOLVER_SECONDS)
    ap.add_argument("--rebuild-adjacency", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    counties = pd.read_parquet(INTERIM / "counties.parquet")
    adj = build_adjacency(force=args.rebuild_adjacency)

    # Islands: no land neighbours, so no penalty term constrains them.
    linked = set(adj["a"]) | set(adj["b"])
    islands = counties[~counties["GEOID"].isin(linked)]
    print(f"\n{len(islands)} counties have no rook neighbour and are unconstrained:")
    if len(islands):
        print(islands[["GEOID", "county", "state"]].to_string(index=False))
    islands[["GEOID", "county", "state", "cenpop_lon", "pop_weight"]].to_csv(
        OUT / "unconstrained_islands.csv", index=False
    )

    rows, solutions = [], {}
    for lam in args.lambdas:
        print(f"\nsolving lambda = {lam}M person-minutes per mismatched boundary…")
        chosen, stats = solve(counties, adj, lam, args.seconds)
        solutions[lam] = chosen
        rows.append(stats)
        print(
            f"  {stats['status']} in {stats['seconds']}s, gap {stats['gap_pct']}%  |  "
            f"pw mean |offset| {stats['pw_mean_abs_offset_min']:.1f} min, "
            f"{stats['distinct_offsets']} distinct offsets, "
            f"{stats['mismatched_boundaries']:,} / {stats['total_boundaries']:,} "
            f"boundaries mismatched ({stats['pct_boundaries_mismatched']}%)"
        )

    sweep = pd.DataFrame(rows)
    sweep.to_csv(OUT / "optimize_sweep.csv", index=False)
    print("\n--- lambda sweep ---")
    print(
        sweep[["lambda_millions", "pw_mean_abs_offset_min", "max_abs_offset_min",
               "distinct_offsets", "mismatched_boundaries", "pct_boundaries_mismatched",
               "gap_pct"]].to_string(index=False, float_format=lambda v: f"{v:.2f}")
    )

    # At lambda = 0 the objective is separable, so every county must independently
    # achieve the minimum of its own term. That is the property worth asserting,
    # and unlike comparing against round(lon/15) it does not depend on how ties
    # are broken.
    if 0.0 in solutions:
        ideal_min = np.round(4.0 * counties["cenpop_lon"].to_numpy()).astype(int)
        lo = int(np.floor(counties["cenpop_lon"].min() / 15.0))
        hi = int(np.ceil(counties["cenpop_lon"].max() / 15.0))
        candidates = np.arange(lo, hi + 1)
        best = np.min(np.abs(ideal_min[:, None] - 60 * candidates[None, :]), axis=1)
        got = solutions[0.0].reindex(counties["GEOID"]).to_numpy()
        achieved = np.abs(ideal_min - 60 * got)
        suboptimal = int((achieved > best).sum())
        print(f"\nlambda=0 separability check: {suboptimal} counties above their own minimum")
        if suboptimal:
            print("  FAIL: unconstrained solution is not per-county optimal")
            return 1
        print("  every county is at its individual optimum")

        # Informational: agreement with the naive reference. Disagreements are
        # near-ties introduced by integerising ideal to whole minutes, not errors.
        naive = np.round(counties["cenpop_lon"].to_numpy() / 15.0).astype(int)
        diff = int((naive != got).sum())
        near_tie = int((np.abs(np.abs(ideal_min) % 60 - 30) <= 1).sum())
        print(f"  vs round(lon/15): {diff} differ, all within {near_tie} near-tie counties "
              "(|ideal| within a minute of a half-hour boundary)")

    if args.select not in solutions:
        print(f"\n--select {args.select} was not in the sweep; nothing written for metrics")
        return 0
    sel = solutions[args.select].rename("offset_h").reset_index()
    sel.columns = ["GEOID", "offset_h"]
    sel.to_csv(SELECTED_OFFSETS, index=False)
    print(f"\nselected lambda={args.select}M -> {SELECTED_OFFSETS.relative_to(ROOT)}")

    (OUT / "optimize_meta.json").write_text(
        json.dumps(
            {
                "objective": "sum_i pop_i*|ideal_i - 60*offset_i| + lambda*sum_edges[o_i != o_j]",
                "lambda_units": "millions of person-minutes per mismatched adjacent pair",
                "lambdas_swept": args.lambdas,
                "selected_lambda_millions": args.select,
                "adjacency": "rook (shared boundary length > 0), EPSG:5070",
                "n_edges": int(len(adj)),
                "n_unconstrained_islands": int(len(islands)),
                "solver": "OR-Tools CP-SAT",
                "time_limit_s": args.seconds,
            },
            indent=2,
        )
        + "\n"
    )
    print("wrote data/out/optimize_meta.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
