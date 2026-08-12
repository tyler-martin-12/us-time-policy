"""Stage 5: contiguity-constrained per-county offset assignment (NOTES.md §9).

Two formulations of the same trade-off, both solved here.

**Budget form (the one the argument rests on).** Minimise population-weighted
misalignment subject to at most `B` mismatched county borders:

    minimise   sum_i  pop_i * |offset_i - ideal_i|
    subject to sum_(i,j) in E  [offset_i != offset_j]  <=  B

Setting `B` to the number of mismatched borders in today's map turns the
headline into a claim that proves itself. Any feasible solution *is* the
witness: it exhibits a whole-hour map no more fragmented than today's, at a
measured cost. The solver's optimality gap bounds how much better a tidy map
could be; it has no bearing on whether this one exists. That is why the budget
form replaced the penalty form as the published result.

**Penalty form (kept as the supporting sweep).** Minimise misalignment plus
lambda per mismatched border. Fine for showing the shape of the trade-off,
awkward to quote, because lambda is in person-minutes per border and nobody has
an intuition for that. `B` is a count of borders and needs no explaining.

`ideal_i` is the offset that would put solar noon at clock noon. Signed solar
offset in minutes is exactly `4*lon - 60*offset_hours` up to the equation of
time, which is a pure function of date and so identical across assignments, so
the misalignment term is exact rather than approximate.

Misalignment is carried in **thousandths of a minute** and population is
**unrounded**. The earlier version rounded both, which left 186 counties within
a minute of a half-hour boundary genuinely tied. The objective value was unique
and proved optimal; the assignment achieving it was not. Every descriptive
statistic of the winning map -- border count, distinct offsets, region count --
was therefore an arbitrary choice among optima, and two of those numbers reached
the write-up. See NOTES.md §9.

**Reproducibility is offered on the result, not on the search, and that is a
deliberate trade rather than a shortcut.** Single-worker CP-SAT under a fixed
seed and a deterministic time limit is bit-reproducible, and it is also far
worse at this model: measured head to head at identical scaling, one worker
could not improve on its own warm start while eight workers reached 221 borders.
Paying that much solution quality for byte-stability would be a bad deal, and an
unnecessary one, because the claim here is constructive. So the search runs wide
and the *artefact* carries the guarantee: the assignment is committed with its
SHA-256, and `verify_solution.py` recomputes every published statistic from that
CSV with no solver involved. That check survives an OR-Tools upgrade, a
different machine and a different worker count, none of which a reproducible
search would.

The penalty form is used as a search heuristic and the budget form as the
statement of the claim. The published map is then chosen by rule rather than by
picking a lambda, so no arbitrary constant survives into the result. The rule,
stated exactly, because an earlier version of this docstring described a
constraint the code does not apply:

    Among candidates that use no more mismatched county borders than today's
    map AND are better aligned than today's map, take the fewest excess
    regions, then the lowest misalignment.

Note what is *not* in there. The published map is **not** held to today's region
count, and it does not meet it: today's map falls into 6 contiguous regions and
the published one into 9. Region count is reported, never constrained. Holding a
map to it would be both intractable in CP-SAT and wrong, since a map using more
offsets needs more regions to hold them, which is the very thing it is supposed
to be doing.

`excess_regions` is the honest version of that measure: regions minus the number
of offsets used on the mainland, so the count of pieces beyond one connected
band per offset. Today's map is perfectly banded and scores 0; the published map
scores 1, and that single unit is Alaska and Hawaii both sitting at UTC-10
without being contiguous with each other.

Both tests in the filter are load-bearing. Constraining borders alone is nearly
free and provably so, but buys a map with three extra fragments and six stranded
counties: the budget gets satisfied by scattering rather than by moving bands.
And a high penalty drives the solver toward collapsing the country onto a couple
of offsets, which uses no borders at all, scores perfectly on every
fragmentation measure, and is three times worse aligned than what we already
have. Without the "better than today" test the rule published exactly that.

Adjacency is **rook**: counties sharing a boundary of non-zero length. Counties
meeting at a single point are not neighbours, and pairs whose intersection is a
Point are filtered out explicitly rather than trusted to `touches`.

Islands have no land neighbours and so appear in no border term. They are free
to take their ideal offset under any budget, which is correct but looks like a
solver bug on a map, so they are listed in the output and excluded from the
region and enclave counts.

Usage:
    uv run src/50_optimize.py
    uv run src/50_optimize.py --budgets 246 200 150 --workers 1
    uv run src/50_optimize.py --lambdas 0 0.1 1 5 --skip-budget
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

from assignment_stats import MMIN_PER_HOUR, CountyGraph, describe, ideal_mmin

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "out"
COMMITTED = ROOT / "data" / "committed"

ADJACENCY_PARQUET = INTERIM / "adjacency.parquet"
SELECTED_OFFSETS = COMMITTED / "optimized_offsets.csv"
CANDIDATES = COMMITTED / "candidates"

# lambda in MILLIONS of person-minutes per mismatched adjacent pair. The high
# end is not padding: maps that get down to today's *region* count only appear
# above lambda = 5, and the published assignment is selected from among them, so
# a thin sweep up there would leave the headline cost looser than it needs to be.
DEFAULT_LAMBDAS = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]

# Border budgets as a fraction of today's count, plus today's count itself.
# Resolved against the real number at run time rather than hardcoded. Below
# about 0.4 the budget form stops finding anything usable and returns maps worse
# than today's; those rows are kept because where a method breaks down is worth
# showing, but there is no point sweeping further into the rubble.
DEFAULT_BUDGET_FRACTIONS = [1.30, 1.00, 0.85, 0.70, 0.55, 0.40]

# Deterministic time, not wall-clock seconds, so the work done does not depend
# on how busy the machine is. One deterministic unit is a great deal of work on
# this model: measured here, 120s of wall clock buys between 1 and 3 units, so
# 2.0 is a limit that actually binds. The wall figure is a safety net set well
# clear of it, and `wall_limit_hit` in the sweep output says if it ever bound
# first, which would mean that row is machine dependent.
DETERMINISTIC_TIME = 2.0
WALL_SECONDS = 400.0


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
    graph: CountyGraph,
    ideal: np.ndarray,
    pop: np.ndarray,
    *,
    lam_millions: float | None = None,
    budget: int | None = None,
    det_time: float = DETERMINISTIC_TIME,
    workers: int = 1,
    seed: int = 0,
    hint: np.ndarray | None = None,
    wall_seconds: float | None = None,
) -> tuple[pd.Series, dict]:
    """Solve one instance. Exactly one of `lam_millions` and `budget` is set."""
    if (lam_millions is None) == (budget is None):
        raise ValueError("pass exactly one of lam_millions or budget")

    lo = int(np.floor(ideal.min() / MMIN_PER_HOUR))
    hi = int(np.ceil(ideal.max() / MMIN_PER_HOUR))

    model = cp_model.CpModel()
    off = [model.NewIntVar(lo, hi, f"o{i}") for i in range(graph.n)]

    dev = []
    for i in range(graph.n):
        span = max(abs(ideal[i] - MMIN_PER_HOUR * lo), abs(ideal[i] - MMIN_PER_HOUR * hi))
        d = model.NewIntVar(0, int(span), f"d{i}")
        model.AddAbsEquality(d, int(ideal[i]) - MMIN_PER_HOUR * off[i])
        dev.append(d)

    # Only build the border terms when they can bind. Under the penalty form at
    # lambda = 0 the problem is separable per county, and 8,933 spare boolean
    # constraints turn an instant separable solve into a search that times out.
    mismatch = []
    needs_borders = budget is not None or (lam_millions or 0.0) > 0
    if needs_borders:
        big = hi - lo
        for ia, ib in zip(graph.ia, graph.ib, strict=True):
            m = model.NewBoolVar("")
            if budget is None:
                # Penalty form: only "if they differ then m = 1" is needed, since
                # m carries a positive coefficient in a minimisation and the
                # solver sets it to 0 whenever it is allowed to. Two plain linear
                # constraints, no reification machinery.
                model.Add(off[ia] - off[ib] <= big * m)
                model.Add(off[ib] - off[ia] <= big * m)
            else:
                # Budget form needs the converse too. Half-reified, the budget
                # constraint can only ever be checked after the fact; fully
                # reified, a nearly-exhausted budget propagates *backwards* and
                # forces neighbouring counties equal, which is the entire reason
                # the budget form is tractable. It also makes m a function of
                # off, so hinting off alone determines a complete solution.
                model.Add(off[ia] != off[ib]).OnlyEnforceIf(m)
                model.Add(off[ia] == off[ib]).OnlyEnforceIf(m.Not())
            mismatch.append(m)

    misalignment = sum(int(p) * d for p, d in zip(pop, dev, strict=True))
    if budget is not None:
        model.Add(sum(mismatch) <= int(budget))
        model.Minimize(misalignment)
    elif mismatch:
        # lambda arrives in millions of person-minutes; the objective is in
        # person-thousandths-of-a-minute, hence the 1e9.
        model.Minimize(misalignment + int(round(lam_millions * 1e9)) * sum(mismatch))
    else:
        model.Minimize(misalignment)

    # Warm start. The unconstrained optimum round(lon/15) is the exact answer at
    # lambda = 0 and a good basin under the penalty form, but it uses 260 borders
    # and so violates every interesting budget, and CP-SAT given only an
    # infeasible hint can spend its whole budget failing to find a first
    # solution. Under the budget form the caller passes today's map instead,
    # which is feasible by construction whenever the budget is today's count or
    # looser. Hints are advisory either way.
    if hint is None:
        hint = np.round(ideal / MMIN_PER_HOUR).astype(int)
    for i in range(graph.n):
        model.AddHint(off[i], int(hint[i]))
    if mismatch and budget is not None:
        # Hint the border variables too. CP-SAT will repair a partial hint, but
        # spending the budget rediscovering 8,933 values it could have been told
        # is the difference between an instant first solution and none at all.
        for m, ia, ib in zip(mismatch, graph.ia, graph.ib, strict=True):
            model.AddHint(m, int(hint[ia] != hint[ib]))

    solver = cp_model.CpSolver()
    solver.parameters.max_deterministic_time = float(det_time)
    solver.parameters.num_workers = int(workers)
    solver.parameters.random_seed = int(seed)
    if wall_seconds is not None:
        # A safety net, not the limit. The deterministic budget is what makes a
        # run reproducible, so if this one ever binds the result is machine
        # dependent and `wall_limit_hit` says so in the sweep output.
        solver.parameters.max_time_in_seconds = float(wall_seconds)
    t0 = time.perf_counter()
    status = solver.Solve(model)
    wall = time.perf_counter() - t0

    solved = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    stats = {
        "form": "budget" if budget is not None else "penalty",
        "budget": budget,
        "lambda_millions": lam_millions,
        "status": solver.StatusName(status),
        "wall_seconds": round(wall, 1),
        "deterministic_time": round(solver.ResponseProto().deterministic_time, 2),
        "workers": workers,
        "seed": seed,
        "wall_limit_hit": bool(
            wall_seconds is not None and wall >= 0.98 * wall_seconds
        ),
        "gap_pct": round(
            100.0
            * abs(solver.ObjectiveValue() - solver.BestObjectiveBound())
            / max(abs(solver.ObjectiveValue()), 1.0),
            4,
        ) if solved else None,
    }
    # A tight budget can genuinely have no solution the solver can reach, and
    # the sweep runs deliberately far enough to find that edge. Returning the
    # empty row rather than raising keeps the failure in the published table,
    # where it belongs, instead of destroying the run that found it.
    if not solved:
        return None, stats

    chosen = pd.Series(
        [solver.Value(o) for o in off], index=graph.geoids, name="offset_h"
    )
    stats.update(describe(graph, chosen, ideal, pop))
    return chosen, stats


SWEEP_COLUMNS = [
    "form", "budget", "lambda_millions", "pw_mean_abs_offset_min",
    "max_abs_offset_min", "distinct_offsets", "mismatched_boundaries",
    "pct_boundaries_mismatched", "n_regions", "n_mainland_offsets",
    "excess_regions", "n_enclave_counties",
    "status", "gap_pct", "deterministic_time", "wall_limit_hit",
]


def print_sweep(rows: list[dict], title: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    # Rows where the solver returned nothing carry only the status fields, so
    # reindex rather than select: a sweep that ran into the infeasible end
    # should still print, with the empty rows visible as empty.
    frame = frame.reindex(columns=sorted(set(frame.columns) | set(SWEEP_COLUMNS)))
    print(f"\n--- {title} ---")
    print(
        frame[SWEEP_COLUMNS].to_string(
            index=False, float_format=lambda v: f"{v:.3f}"
        )
    )
    return frame


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lambdas", type=float, nargs="+", default=DEFAULT_LAMBDAS)
    ap.add_argument("--budgets", type=int, nargs="+", default=None,
                    help="explicit border budgets; default is fractions of today's count")
    ap.add_argument("--select-budget", type=int, default=None,
                    help="which budget's solution to publish; default is today's count")
    ap.add_argument("--det-time", type=float, default=DETERMINISTIC_TIME)
    ap.add_argument("--wall-seconds", type=float, default=WALL_SECONDS,
                    help="safety net per solve; the deterministic budget is the real limit")
    ap.add_argument("--workers", type=int, default=8,
                    help="8 finds much better maps than 1; the artefact carries the "
                         "guarantee, not the search (see module docstring)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force-resolve", action="store_true",
                    help="re-solve even where a cached candidate exists")
    ap.add_argument("--skip-lambda", action="store_true")
    ap.add_argument("--skip-budget", action="store_true")
    ap.add_argument("--rebuild-adjacency", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    COMMITTED.mkdir(parents=True, exist_ok=True)
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    counties = pd.read_parquet(INTERIM / "counties.parquet")
    adj = build_adjacency(force=args.rebuild_adjacency)

    graph = CountyGraph(counties["GEOID"].tolist(), adj)
    ideal = ideal_mmin(counties["cenpop_lon"].to_numpy())
    pop = counties["pop_weight"].fillna(0).to_numpy().astype(np.int64)
    if (pop <= 0).any():
        raise ValueError("a county has zero population weight and would drift freely")

    islands = counties[~graph.linked]
    print(f"\n{len(islands)} counties have no rook neighbour and are unconstrained:")
    if len(islands):
        print(islands[["GEOID", "county", "state"]].to_string(index=False))
    islands[["GEOID", "county", "state", "cenpop_lon", "pop_weight"]].to_csv(
        OUT / "unconstrained_islands.csv", index=False
    )

    # Reference maps. Today's border count sets the default budget, so it is
    # computed here rather than written down.
    today = counties.set_index("GEOID")["std_offset_h"].astype(int)
    naive = pd.Series(
        np.round(ideal / MMIN_PER_HOUR).astype(int), index=counties["GEOID"], name="offset_h"
    )
    references = {
        "today_standard_time": describe(graph, today, ideal, pop),
        "round_lon_over_15": describe(graph, naive, ideal, pop),
    }
    print("\n--- reference assignments ---")
    print(pd.DataFrame(references).T[
        ["pw_mean_abs_offset_min", "mismatched_boundaries", "n_regions",
         "n_enclave_counties", "distinct_offsets"]
    ].to_string())

    today_borders = references["today_standard_time"]["mismatched_boundaries"]
    today_pw = references["today_standard_time"]["pw_mean_abs_offset_min"]
    print(f"\ntoday's map has {today_borders} mismatched borders; that is the default budget")

    # Every assignment any solve produces, penalty or budget, is a candidate for
    # publication, and every candidate is written to disk as it is found. The
    # selection rule then reads the directory rather than this process's memory,
    # which makes the sweep resumable: a run that is interrupted, or split into
    # chunks across several invocations, still selects over everything found so
    # far. Solves whose candidate file already exists are skipped unless
    # --force-resolve, so re-running the same command finishes the job.
    candidates: list[tuple[pd.Series, dict]] = []

    def describe_row(tag: str, stats: dict) -> None:
        flag = "  [wall limit bound, not deterministic]" if stats["wall_limit_hit"] else ""
        print(f"  {stats['status']} gap {stats['gap_pct']}%  |  "
              f"{stats['pw_mean_abs_offset_min']:.4f} min, "
              f"{stats['mismatched_boundaries']} borders, "
              f"{stats['n_regions']} regions (excess {stats['excess_regions']}), "
              f"{stats['n_enclave_counties']} enclave counties{flag}")

    def run(tag: str, **kwargs) -> tuple[pd.Series | None, dict]:
        csv, meta = CANDIDATES / f"{tag}.csv", CANDIDATES / f"{tag}.json"
        # A solve that found nothing is cached as json with no csv. Without
        # that, every resumed run would spend the full wall budget rediscovering
        # the same failure at the tight end of the sweep.
        if meta.exists() and not args.force_resolve:
            stats = json.loads(meta.read_text())
            if not csv.exists():
                print(f"  cached: {stats['status']}, no assignment")
                return None, stats
            chosen = pd.read_csv(csv, dtype={"GEOID": str}).set_index("GEOID")["offset_h"]
            # Recompute the descriptive statistics rather than trusting what was
            # written. Only the solver's own fields (status, gap, timings) are
            # genuinely historical; everything else is a function of the
            # assignment, so re-deriving it means a cached sweep picks up new
            # measures without re-solving, and a stale file cannot quietly feed
            # an old definition into a published number.
            stats.update(describe(graph, chosen, ideal, pop))
            candidates.append((chosen, stats))
            print("  cached")
            describe_row(tag, stats)
            return chosen, stats

        chosen, stats = solve(graph, ideal, pop, det_time=args.det_time,
                              wall_seconds=args.wall_seconds, workers=args.workers,
                              seed=args.seed, **kwargs)
        meta.write_text(json.dumps(stats, indent=2) + "\n")
        if chosen is None:
            print(f"  {stats['status']} in {stats['wall_seconds']}s, no assignment")
            return None, stats
        candidates.append((chosen, stats))
        chosen.rename("offset_h").rename_axis("GEOID").to_csv(csv)
        describe_row(tag, stats)
        return chosen, stats

    def eligible_within(limit: int) -> list[tuple[pd.Series, dict]]:
        """Candidates inside the border budget that are worth publishing at all.

        The second test looks redundant and is not. A high penalty drives the
        solver towards collapsing the country onto a handful of offsets, which
        uses no borders, looks immaculate on every fragmentation measure, and is
        three times worse aligned than the map we already have. Without this
        guard the selection rule happily published exactly that.
        """
        return [
            c for c in candidates
            if c[1]["mismatched_boundaries"] <= limit
            and c[1]["pw_mean_abs_offset_min"] < today_pw
        ]

    def best_within(limit: int) -> tuple[pd.Series, dict] | None:
        """Lowest-misalignment candidate inside the border budget."""
        eligible = eligible_within(limit)
        return (min(eligible, key=lambda c: c[1]["pw_mean_abs_offset_min"])
                if eligible else None)

    def best_shaped(limit: int) -> tuple[pd.Series, dict] | None:
        """The published map: least fragmented first, then best aligned.

        Lexicographic rather than weighted, so there is no exchange rate to
        invent between minutes and fragments. `excess_regions` is the count of
        pieces beyond one connected band per offset, which is zero for today's
        map and cannot be improved by using fewer offsets.
        """
        eligible = eligible_within(limit)
        if not eligible:
            return None
        return min(eligible, key=lambda c: (c[1]["excess_regions"],
                                            c[1]["pw_mean_abs_offset_min"]))

    lam_rows: list[dict] = []
    lam_solutions: dict[float, pd.Series] = {}
    if not args.skip_lambda:
        for lam in args.lambdas:
            print(f"\npenalty form, lambda = {lam}M person-minutes per border…")
            chosen, stats = run(f"lambda_{lam}", lam_millions=lam)
            lam_solutions[lam] = chosen
            lam_rows.append(stats)

        # At lambda = 0 the objective is separable, so each county independently
        # takes its nearest whole-hour offset: the answer must be round(lon/15)
        # exactly. Under the old whole-minute scaling this check could only be
        # stated as "no county is above its own minimum", because 186 counties
        # were tied and the solver was free to pick either side. That it now
        # holds as strict equality is the evidence the ties are gone, and it
        # would still catch a sign error in `ideal`.
        if lam_solutions.get(0.0) is not None:
            got = lam_solutions[0.0].reindex(counties["GEOID"]).to_numpy()
            differ = int((got != naive.to_numpy()).sum())
            print(f"\nlambda=0 check: {differ} counties differ from round(lon/15)")
            if differ:
                print("  FAIL: unconstrained solution is not the per-county optimum")
                return 1
            print("  exact match, so the optimum is unique and the map is reproducible")

    budgets = args.budgets
    if budgets is None:
        budgets = sorted(
            {int(round(f * today_borders)) for f in DEFAULT_BUDGET_FRACTIONS}, reverse=True
        )
    select = args.select_budget if args.select_budget is not None else today_borders
    if select not in budgets:
        budgets = sorted(set(budgets) | {select}, reverse=True)

    budget_rows: list[dict] = []
    if not args.skip_budget:
        for b in budgets:
            print(f"\nbudget form, at most {b} mismatched borders…")
            # Warm start from the best map already found that fits this budget.
            # Without a feasible incumbent the budget form spends its whole
            # allowance looking for a first solution and returns UNKNOWN;
            # today's map is the fallback because it fits any budget at or above
            # its own border count by construction.
            seed_solution = best_within(b)
            start = (
                seed_solution[0].reindex(counties["GEOID"]).to_numpy()
                if seed_solution is not None
                else today.reindex(counties["GEOID"]).to_numpy()
            )
            _, stats = run(f"budget_{b}", budget=b, hint=start)
            budget_rows.append(stats)

    if lam_rows:
        print_sweep(lam_rows, "penalty sweep (supporting)").to_csv(
            COMMITTED / "optimize_sweep_lambda.csv", index=False
        )
    if budget_rows:
        print_sweep(budget_rows, "budget sweep (published)").to_csv(
            COMMITTED / "optimize_sweep_budget.csv", index=False
        )

    # The selection rule. Two constraints, both read off today's map, and no
    # arbitrary constant: the published assignment is the lowest-misalignment
    # candidate that uses no more mismatched borders *and* falls into no more
    # separate contiguous regions than today's zones do.
    #
    # Both are needed, and finding that out is one of the results. Constraining
    # borders alone is nearly free, but the map it buys is not the map a reader
    # sees: at today's border count the solve is proved optimal and costs
    # essentially nothing, while landing in roughly twice as many disconnected
    # pieces. Border count turns out to be a poor proxy for looking tidy, so the
    # measure a reader would actually judge the map on is constrained too, and
    # the cost is quoted against both.
    today_regions = references["today_standard_time"]["n_regions"]
    winner = best_shaped(select)
    if winner is None:
        print(f"\nno candidate stays within {select} borders while beating today's "
              "alignment; nothing published")
        return 1
    chosen, published = winner

    # The border-only optimum, reported alongside because it is the strongest
    # provable statement available and it is not the published map.
    borders_only = best_within(select)
    if borders_only is not None:
        bo = borders_only[1]
        print(f"\nborder budget alone, for reference: {bo['pw_mean_abs_offset_min']:.4f} min "
              f"({bo['status']}, gap {bo['gap_pct']}%), "
              f"{bo['mismatched_boundaries']} borders but {bo['n_regions']} regions "
              f"against today's {today_regions}")

    sel = chosen.rename("offset_h").reset_index()
    sel.columns = ["GEOID", "offset_h"]
    sel.to_csv(SELECTED_OFFSETS, index=False)
    # 30_metrics.py reads the interim copy; keep them identical.
    sel.to_csv(INTERIM / "optimized_offsets.csv", index=False)
    origin = (f"budget={published['budget']}" if published["form"] == "budget"
              else f"lambda={published['lambda_millions']}M")
    print(f"\npublished: best map within {select} borders, found by the "
          f"{published['form']} form at {origin}")
    print(f"  {published['pw_mean_abs_offset_min']:.4f} min, "
          f"{published['mismatched_boundaries']} borders, "
          f"{published['n_regions']} regions, "
          f"{published['n_enclave_counties']} enclave counties")
    print(f"  -> {SELECTED_OFFSETS.relative_to(ROOT)}")
    print(f"  sha256 {published['sha256']}")

    # The tightest proved lower bound over the budget solves, if any closed
    # enough of a gap to be worth quoting. This is what bounds how much better a
    # tidy map could possibly be.
    tidy_bounds = [r for r in budget_rows if r["budget"] >= select]
    best_gap = min((r["gap_pct"] for r in tidy_bounds), default=None)

    (COMMITTED / "optimize_meta.json").write_text(
        json.dumps(
            {
                # The claim is stated in the budget form; the assignment that
                # witnesses it may have been found by either form. Keeping these
                # as separate keys stops the metadata implying the published map
                # came out of a budget solve when it did not.
                "claim_form": "border_budget",
                "claim_objective":
                    "minimise sum_i pop_i*|ideal_i - 60*offset_i| "
                    "s.t. sum_edges[o_i != o_j] <= B",
                "published_budget": select,
                "published_budget_source":
                    "mismatched borders in today's standard-time map, computed at run time",
                "published_selection_rule":
                    "among candidates using no more mismatched borders than today's "
                    "map and better aligned than today's map, fewest excess regions "
                    "first, then lowest population-weighted misalignment",
                "published_excess_regions": published["excess_regions"],
                "published_regions": published["n_regions"],
                # Reported for comparison only. Region count is NOT a constraint
                # and the published map does not match today's; see the module
                # docstring for why holding it to that would be wrong.
                "today_regions_reported_not_constrained": today_regions,
                "border_budget_only_best_min":
                    round(borders_only[1]["pw_mean_abs_offset_min"], 6)
                    if borders_only else None,
                "border_budget_only_status":
                    borders_only[1]["status"] if borders_only else None,
                "border_budget_only_regions":
                    borders_only[1]["n_regions"] if borders_only else None,
                "published_found_by": published["form"],
                "published_found_at":
                    published["budget"] if published["form"] == "budget"
                    else published["lambda_millions"],
                "published_borders": published["mismatched_boundaries"],
                "published_sha256": published["sha256"],
                "published_status": published["status"],
                "published_gap_pct": published["gap_pct"],
                "best_budget_form_gap_pct": best_gap,
                "misalignment_units": "thousandths of a minute, unrounded population",
                "supporting_form": "penalty, lambda in millions of person-minutes per border",
                "lambdas_swept": args.lambdas if lam_rows else [],
                "budgets_swept": budgets if budget_rows else [],
                "adjacency": "rook (shared boundary length > 0), EPSG:5070",
                "n_edges": graph.n_edges,
                "n_unconstrained_islands": graph.n_islands,
                "solver": "OR-Tools CP-SAT",
                "solver_workers": args.workers,
                "solver_seed": args.seed,
                "solver_deterministic_time": args.det_time,
                "reference_assignments": {
                    k: {kk: vv for kk, vv in v.items() if kk != "sha256"}
                    for k, v in references.items()
                },
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {(COMMITTED / 'optimize_meta.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
