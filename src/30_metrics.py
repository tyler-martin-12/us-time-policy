"""Stage 3: metrics. One row per county per regime.

Turns the regime-independent solar layer into policy-dependent numbers by
converting UTC instants to local clock time under each regime's offset function
(NOTES.md §4, §8).

Regimes computed here:
    cta                 current switching rules, offsets from the tzdb
    perm_st             standard offset year round
    perm_dst            standard offset +1h year round
    ideal_unconstrained per-county offset = round(longitude / 15), no contiguity

That last one is *not* the optimised regime. It is the unconstrained reference
NOTES.md §9 asks for, and it is a rounding calculation rather than an
optimisation: no adjacency graph, no solver, no penalty weight. It exists so the
four-panel map has a fourth panel and so stage 2's constrained solution has
something to be compared against. The real `optimized` regime is still stage 2.

Outputs:
    data/out/metrics.csv          county x regime
    data/out/rollups.csv          population-weighted national and per-state
    data/out/zone_spread.csv      intra-zone spread: the argument, as a table
    data/out/metrics_meta.json    every parameter in force

Usage:
    uv run src/30_metrics.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "out"

MODEL_YEAR = 2026
WINTER_MONTH = 1  # January (NOTES.md §3)
SUNRISE_LATE_H = 7.5  # 07:30
SUNSET_EARLY_H = 17.0  # 17:00

# Permanent DST applied to every county, including current non-observers.
# Flipping this to True matches the real bills, which exempt AZ and HI.
EXEMPT_CURRENT_NON_OBSERVERS = False

ZONE_LABELS = {
    -5.0: "Eastern",
    -6.0: "Central",
    -7.0: "Mountain",
    -8.0: "Pacific",
    -9.0: "Alaska",
    -10.0: "Hawaii",
}


def cta_offset_table(tz_names: list[str], dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Offset in hours for 12:00 local on each date, per zone, straight from the
    tzdb. 27 zones x 365 days, so this is cheap and avoids a per-row zoneinfo call.

    Using the noon offset for the whole local day is exact for the US: every
    transition happens at 02:00 local, which is outside the sunrise..sunset span,
    so all four solar events on local date D share offset(D). Asserted below.
    """
    rows = []
    for tz_name in tz_names:
        tz = ZoneInfo(tz_name)
        for d in dates:
            local_noon = datetime(d.year, d.month, d.day, 12, tzinfo=tz)
            rows.append(
                {
                    "tz_name": tz_name,
                    "date": d.date(),
                    "offset_h": local_noon.utcoffset().total_seconds() / 3600.0,
                }
            )
    return pd.DataFrame(rows)


def assert_offset_constant_over_solar_day(solar: pd.DataFrame, counties: pd.DataFrame) -> None:
    """Verify the assumption above on the real data rather than asserting it in
    prose: the tzdb offset at sunrise and at sunset must equal the noon offset."""
    sample = counties[counties["observes_dst"]].head(3)
    for r in sample.itertuples():
        d = solar[solar["GEOID"] == r.GEOID].dropna(subset=["sunrise_geom_utc"])
        tz = ZoneInfo(r.tz_name)
        for col in ("sunrise_geom_utc", "sunset_geom_utc"):
            inst = d[col].dt.tz_convert(tz)
            off_event = inst.map(lambda t: t.utcoffset().total_seconds() / 3600.0)
            noon = pd.to_datetime(d["date"]).map(
                lambda x: datetime(x.year, x.month, x.day, 12, tzinfo=tz)
                .utcoffset()
                .total_seconds()
                / 3600.0
            )
            bad = int((off_event.to_numpy() != noon.to_numpy()).sum())
            if bad:
                raise AssertionError(
                    f"{r.county}: {bad} days where the {col} offset differs from the "
                    "noon offset. The single-daily-offset shortcut is invalid."
                )
    print("  assumption holds: offset is constant across each local solar day")


def time_of_day_hours(s: pd.Series, offset_h: np.ndarray) -> np.ndarray:
    """Local clock time-of-day, in hours, for UTC instants shifted by offset_h.

    Deliberately computed from a shifted naive timestamp rather than tz_convert,
    so the permanent regimes (which are fixed offsets with no tzdb entry) and CTA
    go through identical arithmetic.
    """
    shifted = s.dt.tz_localize(None) + pd.to_timedelta(offset_h, unit="h")
    return (
        shifted.dt.hour.to_numpy()
        + shifted.dt.minute.to_numpy() / 60.0
        + shifted.dt.second.to_numpy() / 3600.0
    )


def build_regime(
    solar: pd.DataFrame, counties: pd.DataFrame, regime: str, cta_offsets: pd.DataFrame
) -> pd.DataFrame:
    df = solar.merge(
        counties[["GEOID", "tz_name", "std_offset_h", "observes_dst", "cenpop_lon"]],
        on="GEOID",
        how="left",
    )

    if regime == "cta":
        df = df.merge(cta_offsets, on=["tz_name", "date"], how="left")
    elif regime == "perm_st":
        df["offset_h"] = df["std_offset_h"]
    elif regime == "perm_dst":
        bump = np.ones(len(df))
        if EXEMPT_CURRENT_NON_OBSERVERS:
            bump = df["observes_dst"].to_numpy().astype(float)
        df["offset_h"] = df["std_offset_h"] + bump
    elif regime == "ideal_unconstrained":
        df["offset_h"] = np.round(df["cenpop_lon"] / 15.0)
    else:
        raise ValueError(regime)

    # Clock noon: the UTC instant at which the local clock reads 12:00 on `date`.
    naive_noon = pd.to_datetime(df["date"]).dt.tz_localize(None) + pd.Timedelta(hours=12)
    clock_noon_utc = naive_noon - pd.to_timedelta(df["offset_h"], unit="h")
    solar_noon_naive = df["solar_noon_utc"].dt.tz_localize(None)

    # THE headline metric. Positive = solar noon before clock noon = sun runs
    # early. Adding an hour of DST makes this 60 minutes more negative.
    df["signed_offset_min"] = (
        clock_noon_utc - solar_noon_naive
    ).dt.total_seconds() / 60.0

    off = df["offset_h"].to_numpy()
    df["sunrise_tod_h"] = time_of_day_hours(df["sunrise_geom_utc"], off)
    df["sunset_tod_h"] = time_of_day_hours(df["sunset_geom_utc"], off)
    df["dawn_tod_h"] = time_of_day_hours(df["dawn_civil_utc"], off)

    df["no_sunrise"] = df["sunrise_geom_utc"].isna()
    df["no_sunset"] = df["sunset_geom_utc"].isna()
    df["month"] = pd.to_datetime(df["date"]).dt.month

    # A day with no sunrise counts as satisfying "sunrise after 07:30": the sun
    # never came up, which is strictly worse than a late sunrise. Same for sunset.
    df["late_sunrise"] = (df["sunrise_tod_h"] > SUNRISE_LATE_H) | df["no_sunrise"]
    df["early_sunset"] = (df["sunset_tod_h"] < SUNSET_EARLY_H) | df["no_sunset"]
    df["late_dawn"] = (df["dawn_tod_h"] > SUNRISE_LATE_H) | df["dawn_civil_utc"].isna()

    g = df.groupby("GEOID", sort=False)
    agg = g.agg(
        offset_annual_mean=("signed_offset_min", "mean"),
        days_sunrise_after_0730=("late_sunrise", "sum"),
        days_sunset_before_1700=("early_sunset", "sum"),
        days_dawn_after_0730=("late_dawn", "sum"),
        days_no_sunrise=("no_sunrise", "sum"),
        days_no_sunset=("no_sunset", "sum"),
        mean_offset_h=("offset_h", "mean"),
    )
    winter = (
        df[df["month"] == WINTER_MONTH]
        .groupby("GEOID", sort=False)["signed_offset_min"]
        .mean()
        .rename("offset_winter")
    )

    # Latest sunrise: max of local TIME OF DAY, not of the absolute instant.
    # Taking the argmax of the UTC timestamp trivially returns Dec 31 everywhere
    # (NOTES.md §8).
    ok = df.dropna(subset=["sunrise_tod_h"])
    idx = ok.groupby("GEOID", sort=False)["sunrise_tod_h"].idxmax()
    latest = ok.loc[idx, ["GEOID", "sunrise_tod_h", "date"]].set_index("GEOID")
    latest.columns = ["latest_sunrise_tod_h", "latest_sunrise_date"]

    out = agg.join(winter).join(latest).reset_index()
    out["regime"] = regime
    return out


def hhmm(hours: float) -> str:
    if not np.isfinite(hours):
        return ""
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h:02d}:{m:02d}"


def weighted(df: pd.DataFrame, col: str, w: str = "pop_weight") -> float:
    d = df.dropna(subset=[col, w])
    return float(np.average(d[col], weights=d[w])) if len(d) else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    counties = pd.read_parquet(INTERIM / "counties.parquet")
    solar = pd.read_parquet(INTERIM / "solar.parquet")
    print(f"{len(counties):,} counties, {len(solar):,} county-days")

    dates = pd.date_range(f"{MODEL_YEAR}-01-01", f"{MODEL_YEAR}-12-31", freq="D")
    print("building CTA offset table from the tzdb…")
    cta_offsets = cta_offset_table(sorted(counties["tz_name"].unique()), dates)
    print(f"  {len(cta_offsets):,} (zone, date) offsets")
    assert_offset_constant_over_solar_day(solar, counties)

    regimes = ["cta", "perm_st", "perm_dst", "ideal_unconstrained"]
    frames = []
    for regime in regimes:
        print(f"computing {regime}…")
        frames.append(build_regime(solar, counties, regime, cta_offsets))
    metrics = pd.concat(frames, ignore_index=True)

    attrs = counties[
        ["GEOID", "county", "state", "tz_name", "std_offset_h", "observes_dst",
         "cenpop_lat", "cenpop_lon", "pop_weight"]
    ]
    metrics = metrics.merge(attrs, on="GEOID", how="left")
    metrics["zone"] = metrics["std_offset_h"].map(ZONE_LABELS).fillna("Other")
    metrics["latest_sunrise_local"] = metrics["latest_sunrise_tod_h"].map(hhmm)

    cols = [
        "GEOID", "county", "state", "zone", "tz_name", "regime",
        "cenpop_lat", "cenpop_lon", "pop_weight",
        "offset_annual_mean", "offset_winter",
        "days_sunrise_after_0730", "days_sunset_before_1700", "days_dawn_after_0730",
        "latest_sunrise_local", "latest_sunrise_date",
        "days_no_sunrise", "days_no_sunset", "mean_offset_h",
    ]
    metrics = metrics[cols].sort_values(["regime", "GEOID"])
    metrics.to_csv(OUT / "metrics.csv", index=False)
    print(f"\nwrote data/out/metrics.csv: {len(metrics):,} rows")

    # --- sanity checks ---------------------------------------------------------
    print("\nsanity checks")
    piv = metrics.pivot_table(index="GEOID", columns="regime", values="offset_annual_mean")

    # Permanent DST is standard offset +1h, so the metric must shift by exactly
    # -60 minutes everywhere. Anything else means the sign convention or the
    # offset arithmetic is wrong.
    d = piv["perm_dst"] - piv["perm_st"]
    print(f"  perm_dst - perm_st: min {d.min():+.4f}, max {d.max():+.4f} min "
          "(must be exactly -60)")

    # Counties that never observe DST (Arizona, Hawaii) must be identical under
    # CTA and permanent standard time, because for them nothing changes.
    non_dst = set(counties.loc[~counties["observes_dst"], "GEOID"])
    same = (piv["perm_st"] - piv["cta"]).reindex(sorted(non_dst)).abs()
    print(f"  |perm_st - cta| across {len(non_dst)} non-DST counties: "
          f"max {same.max():.4f} min (must be 0)")

    # And DST-observing counties must differ, or the regimes are not distinct.
    dst_geoids = sorted(set(counties.loc[counties["observes_dst"], "GEOID"]))
    differ = (piv["cta"] - piv["perm_st"]).reindex(dst_geoids)
    print(f"  cta - perm_st across {len(dst_geoids)} DST counties: "
          f"mean {differ.mean():+.2f} min, range {differ.min():+.2f} to {differ.max():+.2f} "
          "(negative: DST pulls the clock ahead of the sun for part of the year)")

    # --- rollups --------------------------------------------------------------
    roll = []
    for regime, grp in metrics.groupby("regime"):
        roll.append({
            "scope": "national", "regime": regime,
            "offset_annual_mean_pw": weighted(grp, "offset_annual_mean"),
            "offset_winter_pw": weighted(grp, "offset_winter"),
            "days_sunrise_after_0730_pw": weighted(grp, "days_sunrise_after_0730"),
            "days_sunset_before_1700_pw": weighted(grp, "days_sunset_before_1700"),
            "population": float(grp["pop_weight"].sum()),
        })
        for state, sgrp in grp.groupby("state"):
            roll.append({
                "scope": state, "regime": regime,
                "offset_annual_mean_pw": weighted(sgrp, "offset_annual_mean"),
                "offset_winter_pw": weighted(sgrp, "offset_winter"),
                "days_sunrise_after_0730_pw": weighted(sgrp, "days_sunrise_after_0730"),
                "days_sunset_before_1700_pw": weighted(sgrp, "days_sunset_before_1700"),
                "population": float(sgrp["pop_weight"].sum()),
            })
    pd.DataFrame(roll).to_csv(OUT / "rollups.csv", index=False)
    print("wrote data/out/rollups.csv")

    # --- zone spread: the argument, as a table --------------------------------
    spread = []
    for (zone, regime), grp in metrics.groupby(["zone", "regime"]):
        v = grp["offset_annual_mean"]
        d = grp.dropna(subset=["offset_annual_mean", "pop_weight"]).sort_values("offset_annual_mean")
        cw = d["pop_weight"].cumsum() / d["pop_weight"].sum()
        q = lambda p: float(np.interp(p, cw, d["offset_annual_mean"]))  # noqa: E731
        spread.append({
            "zone": zone, "regime": regime, "counties": len(grp),
            "population": float(grp["pop_weight"].sum()),
            "min_min": float(v.min()), "max_min": float(v.max()),
            "range_min": float(v.max() - v.min()),
            "pw_p10": q(0.10), "pw_p50": q(0.50), "pw_p90": q(0.90),
            "pw_iqr_min": q(0.75) - q(0.25),
        })
    spread_df = pd.DataFrame(spread).sort_values(["regime", "population"], ascending=[True, False])
    spread_df.to_csv(OUT / "zone_spread.csv", index=False)
    print("wrote data/out/zone_spread.csv")

    print("\nintra-zone spread of annual mean signed offset, CTA:")
    show = spread_df[spread_df["regime"] == "cta"][
        ["zone", "counties", "min_min", "max_min", "range_min", "pw_iqr_min"]
    ]
    print(show.to_string(index=False, float_format=lambda v: f"{v:.1f}"))

    meta = {
        "model_year": MODEL_YEAR,
        "regimes": regimes,
        "note_on_ideal_unconstrained":
            "round(longitude/15); the unconstrained reference from NOTES.md §9, "
            "not the contiguity-constrained optimised regime, which is stage 2",
        "winter_month": WINTER_MONTH,
        "sunrise_late_threshold_local": "07:30",
        "sunset_early_threshold_local": "17:00",
        "geometric_elevation_deg": -0.8333,
        "civil_elevation_deg": -6.0,
        "exempt_current_non_observers": EXEMPT_CURRENT_NON_OBSERVERS,
        "population_weight": "2020 census count (pop_weight)",
        "sign_convention": "clock noon minus true solar noon; positive = sun early; "
                           "permanent DST subtracts 60 minutes",
        "counties": int(counties.shape[0]),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / "metrics_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("wrote data/out/metrics_meta.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
