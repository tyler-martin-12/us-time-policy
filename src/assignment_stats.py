"""Shared vocabulary for describing an offset assignment (NOTES.md §9, §13).

Every number that describes a map -- misalignment, mismatched boundaries,
contiguous regions, enclaves -- is computed here and only here. The stage 5
optimiser, the stage 5b reporter and the standalone verifier all import this
module, so a figure quoted in the blog post cannot drift from the figure the
solver optimised.

Three definitions are load-bearing and were all previously implicit:

**Misalignment** is exact, not rounded. Signed solar offset in minutes is
`4*lon - 60*offset_hours` up to the equation of time, which is a pure function
of date and so identical across assignments. Working in *thousandths of a
minute* keeps that integer-exact for CP-SAT while making ties vanishingly
unlikely: at whole-minute resolution 186 counties sat within a minute of a
half-hour boundary and the optimum was not unique, so descriptive statistics of
the winning assignment were arbitrary (see `verify_solution.py`).

**Islands are excluded from region and enclave counts.** The three Hawaiian
counties have no rook neighbour, so they are singleton components under every
assignment. Counting them made today's map look like it strands three counties
in enclaves when in fact it strands none, and that number reached the blog post.
They are reported separately as `n_islands`.

**An enclave county** is a non-island county in a same-offset component that is
not the largest component of its own offset value. That is stricter than
"singleton component": a pair of counties cut off from their offset's main body
is just as much an enclave as a lone one.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

# Misalignment is carried in thousandths of a minute throughout.
MMIN_PER_MIN = 1000
MMIN_PER_HOUR = 60 * MMIN_PER_MIN


def ideal_mmin(lon: np.ndarray) -> np.ndarray:
    """Solar noon's distance from clock noon at offset 0, in thousandths of a minute.

    Longitude in the source data carries six decimal places, so 4000*lon is
    already finer than the input resolution and the rounding here is a no-op in
    every way that matters. It exists to give CP-SAT integers.
    """
    return np.round(4000.0 * np.asarray(lon, dtype=float)).astype(np.int64)


class CountyGraph:
    """County ordering plus the rook adjacency, as index arrays.

    Built once and passed around, so that every statistic is computed over the
    same county order and the same edge list.
    """

    def __init__(self, geoids: list[str], adj: pd.DataFrame) -> None:
        self.geoids = list(geoids)
        self.index = {g: i for i, g in enumerate(self.geoids)}
        self.n = len(self.geoids)
        self.ia = adj["a"].map(self.index).to_numpy()
        self.ib = adj["b"].map(self.index).to_numpy()
        if np.isnan(self.ia).any() or np.isnan(self.ib).any():
            raise ValueError("adjacency references a GEOID not in the county table")
        self.ia = self.ia.astype(int)
        self.ib = self.ib.astype(int)
        self.n_edges = len(self.ia)
        linked = np.zeros(self.n, dtype=bool)
        linked[self.ia] = True
        linked[self.ib] = True
        self.linked = linked

    @property
    def n_islands(self) -> int:
        return int((~self.linked).sum())

    def align(self, offsets: pd.Series | np.ndarray) -> np.ndarray:
        """Offsets as an int array in this graph's county order."""
        if isinstance(offsets, pd.Series):
            aligned = offsets.reindex(self.geoids)
            if aligned.isna().any():
                missing = int(aligned.isna().sum())
                raise ValueError(f"assignment does not cover {missing} counties")
            return aligned.to_numpy().astype(int)
        arr = np.asarray(offsets)
        if len(arr) != self.n:
            raise ValueError(f"expected {self.n} offsets, got {len(arr)}")
        return arr.astype(int)


def mismatched_boundaries(graph: CountyGraph, offsets: np.ndarray) -> int:
    """Adjacent county pairs assigned different offsets."""
    return int((offsets[graph.ia] != offsets[graph.ib]).sum())


def region_stats(graph: CountyGraph, offsets: np.ndarray) -> dict:
    """Contiguous same-offset regions and enclave counties, islands excluded.

    Components are taken over the subgraph of edges whose two counties agree,
    which is the graph-theoretic version of "colour the map and count the
    blobs".
    """
    same = offsets[graph.ia] == offsets[graph.ib]
    kept = coo_matrix(
        (np.ones(int(same.sum())), (graph.ia[same], graph.ib[same])),
        shape=(graph.n, graph.n),
    )
    _, labels = connected_components(kept, directed=False)

    mainland = graph.linked
    n_regions = int(len(np.unique(labels[mainland])))

    enclave = np.zeros(graph.n, dtype=bool)
    for value in np.unique(offsets[mainland]):
        members = np.where(mainland & (offsets == value))[0]
        member_labels = labels[members]
        counts = pd.Series(member_labels).value_counts()
        # Ties on size are broken by the smallest component id, which is
        # deterministic given the county order. Two same-size components of one
        # offset would be an ambiguous map either way.
        largest = min(counts[counts == counts.iloc[0]].index)
        enclave[members[member_labels != largest]] = True

    # A map using k offsets on the mainland cannot have fewer than k regions,
    # so the raw region count punishes a map for using more offsets, which is
    # the very thing it is supposed to be doing. The excess over that floor is
    # the part that is actually fragmentation: it counts the extra pieces beyond
    # one connected band per offset. Today's map scores zero, and so would any
    # perfectly banded map however many offsets it used.
    #
    # It is also the measure that cannot be gamed. Collapsing the country onto
    # two offsets scores wonderfully on region count and is a terrible map; it
    # scores no better than anything else on excess.
    n_mainland_offsets = int(len(np.unique(offsets[mainland])))

    return {
        "n_regions": n_regions,
        "n_mainland_offsets": n_mainland_offsets,
        "excess_regions": n_regions - n_mainland_offsets,
        "n_enclave_counties": int(enclave.sum()),
        "n_islands": graph.n_islands,
        "enclave_mask": enclave,
        "labels": labels,
    }


def pw_mean_abs_min(offsets: np.ndarray, ideal: np.ndarray, pop: np.ndarray) -> float:
    """Population-weighted mean |misalignment| in minutes, exact and unrounded.

    This is the optimiser's proxy objective expressed per person. It is close to
    but not identical with the figure `30_metrics.py` reports, which integrates
    real solar position over every day of the year. Quote the metrics figure in
    anything public; this one exists so the solver's own objective can be
    checked against the assignment it returned.
    """
    dev = np.abs(ideal - MMIN_PER_HOUR * offsets) / MMIN_PER_MIN
    return float(np.average(dev, weights=pop))


def assignment_sha256(geoids: list[str], offsets: np.ndarray) -> str:
    """Stable content hash of an assignment.

    Sorted by GEOID so the hash describes the map rather than the row order of
    whatever wrote it.
    """
    pairs = sorted(zip(geoids, (int(o) for o in offsets), strict=True))
    body = "\n".join(f"{g},{o}" for g, o in pairs)
    return hashlib.sha256(body.encode()).hexdigest()


def describe(
    graph: CountyGraph,
    offsets: pd.Series | np.ndarray,
    ideal: np.ndarray,
    pop: np.ndarray,
) -> dict:
    """Every headline statistic for one assignment, in one call."""
    off = graph.align(offsets)
    regions = region_stats(graph, off)
    n_mismatch = mismatched_boundaries(graph, off)
    return {
        "pw_mean_abs_offset_min": pw_mean_abs_min(off, ideal, pop),
        "max_abs_offset_min": float(
            np.abs(ideal - MMIN_PER_HOUR * off).max() / MMIN_PER_MIN
        ),
        "distinct_offsets": int(len(np.unique(off))),
        "mismatched_boundaries": n_mismatch,
        "total_boundaries": graph.n_edges,
        "pct_boundaries_mismatched": round(100.0 * n_mismatch / graph.n_edges, 2),
        "n_regions": regions["n_regions"],
        "n_mainland_offsets": regions["n_mainland_offsets"],
        "excess_regions": regions["excess_regions"],
        "n_enclave_counties": regions["n_enclave_counties"],
        "n_islands": regions["n_islands"],
        "sha256": assignment_sha256(graph.geoids, off),
    }
