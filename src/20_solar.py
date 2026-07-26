"""Stage 2: solar layer. One row per county-day, all instants in UTC.

3,143 counties x 365 days of 2026 = 1,147,195 rows, computed at each county's
center of population.

Everything is stored as **UTC instants** and converted to local clock time only
at metric time (NOTES.md §7). Storing local times would mean recomputing the
whole solar layer once per regime, which is both wasteful and an invitation to
the four regimes silently disagreeing about the sun.

Method split, and why (validated in 25_validate_solar.py against USNO):

  - **Solar noon** comes from pvlib's NREL SPA transit
    (`sun_rise_set_transit_spa`). This is the quantity the headline signed-solar-
    offset metric depends on, and it matches USNO to 30s, which is USNO's own
    minute-rounding.
  - **Sunrise, sunset, civil dawn and civil dusk** all come from the hour-angle
    formula, anchored on that SPA transit and an SPA-derived declination.

pvlib's SPA rise/set helper is deliberately *not* used for sunrise/sunset, even
though it is the more obvious choice. Measured against USNO across five sites and
five dates:

    quantity   pvlib SPA        hour-angle
    sunrise    25.5s max        60.6s max
    sunset     164.1s max       37.4s max

pvlib's sunset degrades to ~2.7 minutes at Anchorage (61 deg N) near the
equinoxes, with the error flipping sign either side, while the hour-angle result
stays inside 40s everywhere. The asymmetry is the tell: a threshold or
declination error would move sunrise and sunset together, and sunrise is fine.
Using one method for all four crossings also means the geometric and civil
columns cannot disagree for methodological reasons, only for the threshold that
is actually being varied.

The trade is a slightly worse sunrise (61s vs 26s worst case). Both are inside
the 90s gate, and consistency across the four crossings is worth more here than
26 seconds on sunrise.

Usage:
    uv run src/20_solar.py
    uv run src/20_solar.py --force
    uv run src/20_solar.py --limit 50      # quick partial run while developing
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
COUNTIES_PARQUET = INTERIM / "counties.parquet"
SOLAR_PARQUET = INTERIM / "solar.parquet"

MODEL_YEAR = 2026
GEOMETRIC_ELEV = -0.8333  # 34' refraction + 16' solar semidiameter
CIVIL_ELEV = -6.0



def hour_angle_crossing(
    lat_deg: float, dec_deg: np.ndarray, elev_deg: float
) -> np.ndarray:
    """Half-day-length in hours for the sun to reach `elev_deg`, or NaN if it
    never does (polar day / polar night)."""
    phi = np.radians(lat_deg)
    dec = np.radians(dec_deg)
    h0 = np.radians(elev_deg)
    cos_h = (np.sin(h0) - np.sin(phi) * np.sin(dec)) / (np.cos(phi) * np.cos(dec))
    with np.errstate(invalid="ignore"):
        out = np.degrees(np.arccos(np.clip(cos_h, -1.0, 1.0))) / 15.0
    return np.where(np.abs(cos_h) <= 1.0, out, np.nan)


def solve_county(lat: float, lon: float, days: pd.DatetimeIndex) -> dict:
    """SPA rise/set/transit plus hour-angle dawn/dusk for one county."""
    rst = pvlib.solarposition.sun_rise_set_transit_spa(days, lat, lon)
    transit = rst["transit"]

    # Declination recovered from the SPA solar position at transit. At upper
    # transit the sun's true elevation is 90 - |phi - dec|, so the magnitude of
    # (phi - dec) is known; the azimuth disambiguates the sign. That matters for
    # Hawaii, where in summer the sun transits *north* of the zenith (dec > phi)
    # and assuming "south" would flip the sign.
    valid = transit.notna()
    dec = np.full(len(days), np.nan)
    eot = np.full(len(days), np.nan)
    if valid.any():
        sp = pvlib.solarposition.get_solarposition(transit[valid], lat, lon)
        # True (unrefracted) elevation: declination is a geometric quantity, so
        # using apparent_elevation here would fold refraction into it.
        gap = 90.0 - sp["elevation"].to_numpy()
        north = np.cos(np.radians(sp["azimuth"].to_numpy())) > 0  # azimuth near 0/360
        dec[valid.to_numpy()] = np.where(lat - gap > -90, lat - gap, np.nan)
        dec[valid.to_numpy()] = np.where(north, lat + gap, lat - gap)
        eot[valid.to_numpy()] = sp["equation_of_time"].to_numpy()

    h_civil = hour_angle_crossing(lat, dec, CIVIL_ELEV)
    h_geom = hour_angle_crossing(lat, dec, GEOMETRIC_ELEV)

    # Stay in pandas for the arithmetic: a tz-aware Series comes out of
    # .to_numpy() as an object array of Timestamps, which will not take a
    # timedelta64. Series keep the datetime64[ns, UTC] dtype, and parquet
    # preserves it, which is the whole point of storing UTC instants.
    offs_civil = pd.to_timedelta(pd.Series(h_civil, index=transit.index), unit="h")
    offs_geom = pd.to_timedelta(pd.Series(h_geom, index=transit.index), unit="h")

    reset = lambda s: s.reset_index(drop=True)  # noqa: E731
    return {
        "solar_noon_utc": reset(transit),
        # Hour-angle for all four crossings, not pvlib's SPA rise/set: see the
        # module docstring for the USNO comparison that decided this.
        "sunrise_geom_utc": reset(transit - offs_geom),
        "sunset_geom_utc": reset(transit + offs_geom),
        "dawn_civil_utc": reset(transit - offs_civil),
        "dusk_civil_utc": reset(transit + offs_civil),
        "declination_deg": dec,
        "eot_min": eot,
        # Diagnostic only, not persisted: pvlib's own SPA rise/set, kept so the
        # run can report where the two methods diverge (Alaska, near equinoxes).
        "_spa_sunrise_utc": reset(rst["sunrise"]),
        "_spa_sunset_utc": reset(rst["sunset"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, help="only process the first N counties")
    args = ap.parse_args()

    if SOLAR_PARQUET.exists() and not args.force:
        n = pd.read_parquet(SOLAR_PARQUET, columns=["GEOID"]).shape[0]
        print(f"cached: {SOLAR_PARQUET.relative_to(ROOT)} ({n:,} county-days)")
        print("use --force to rebuild")
        return 0

    counties = pd.read_parquet(COUNTIES_PARQUET)
    if args.limit:
        counties = counties.head(args.limit)
    days = pd.date_range(f"{MODEL_YEAR}-01-01", f"{MODEL_YEAR}-12-31", freq="D", tz="UTC")
    print(f"{len(counties):,} counties x {len(days)} days = {len(counties) * len(days):,} rows")

    frames = []
    check_dev = []
    t0 = time.perf_counter()
    for i, row in enumerate(counties.itertuples(index=False), start=1):
        res = solve_county(row.cenpop_lat, row.cenpop_lon, days)
        spa_rise = res.pop("_spa_sunrise_utc")
        spa_set = res.pop("_spa_sunset_utc")
        for ours, theirs in (
            (res["sunrise_geom_utc"], spa_rise),
            (res["sunset_geom_utc"], spa_set),
        ):
            dev = (ours - theirs).dt.total_seconds().to_numpy()
            check_dev.append(dev[np.isfinite(dev)])

        frames.append(
            pd.DataFrame(
                {
                    "GEOID": row.GEOID,
                    "date": days.date,
                    **res,
                }
            )
        )
        if i % 250 == 0 or i == len(counties):
            rate = i / (time.perf_counter() - t0)
            eta = (len(counties) - i) / rate
            print(f"  {i:>5,}/{len(counties):,}  {rate:.0f} counties/s  eta {eta / 60:.1f} min")

    solar = pd.concat(frames, ignore_index=True)

    # --- diagnostic: divergence from pvlib's own SPA rise/set ------------------
    # Reported, not gated. The authoritative gate is 25_validate_solar.py against
    # USNO, which is what established that pvlib's SPA sunset is the weaker of
    # the two at high latitude. This just shows how large the disagreement is
    # across the whole country rather than at five test sites.
    dev = np.concatenate(check_dev)
    print("\nours (hour-angle) vs pvlib SPA rise/set, same -0.8333 deg threshold:")
    print(
        f"  n={dev.size:,}  mean {np.mean(dev):+.2f}s  "
        f"median |dev| {np.percentile(np.abs(dev), 50):.2f}s  "
        f"p99 {np.percentile(np.abs(dev), 99):.2f}s  "
        f"max {np.max(np.abs(dev)):.2f}s"
    )
    print("  (expected: small everywhere except Alaskan sunsets near the equinoxes)")

    nulls = {
        c: int(solar[c].isna().sum())
        for c in ["solar_noon_utc", "sunrise_geom_utc", "sunset_geom_utc", "dawn_civil_utc"]
    }
    print("\nnull counts (expected non-zero only at high Alaskan latitudes):")
    for c, n in nulls.items():
        print(f"  {c}: {n:,}")

    INTERIM.mkdir(parents=True, exist_ok=True)
    solar.to_parquet(SOLAR_PARQUET, index=False)
    size_mb = SOLAR_PARQUET.stat().st_size / 1_048_576
    print(f"\nwrote {SOLAR_PARQUET.relative_to(ROOT)}: {len(solar):,} rows, {size_mb:.1f} MiB")
    print(f"elapsed {(time.perf_counter() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
