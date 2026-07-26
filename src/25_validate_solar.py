"""Stage 2b: validation gate for the solar layer (NOTES.md §7).

Compares our computed solar times against **USNO** (aa.usno.navy.mil), the
authoritative US reference, for five sites spanning the failure modes on five
dates spanning the year.

This is a real gate. It is the only check that would catch a longitude sign
error, a refraction threshold mistake or a UTC/local mix-up before those errors
propagate into every downstream map.

Two references are queried, and the difference between them is the point:

  - **USNO** — authoritative, but published only to the minute, so a perfect
    implementation still shows up to ~30s of rounding. This is what gates.
  - **api.sunrise-sunset.org** — NOAA-spreadsheet grade, seconds resolution.
    Reported only. It runs systematically ~90s fast on sunrise at mid-latitudes,
    growing past 300s at Anchorage, which is why it is not the gate. Kept in the
    output because "the convenient API disagrees with USNO by 5 minutes in
    Alaska" is worth knowing rather than discovering later.

USNO is queried in each site's own standard offset with dst=false, so rise,
transit and set all land on one local date and can be converted back to UTC
unambiguously. Requesting tz=0 instead interleaves the previous evening's sunset
into the same UTC day.

Reference values are cached to notes/ and committed, so the gate re-runs with no
network and an upstream change cannot silently alter what we validated against.

Usage:
    uv run src/25_validate_solar.py
    uv run src/25_validate_solar.py --refresh
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
USNO_REF = ROOT / "notes" / "solar_validation_usno.json"
NOAA_REF = ROOT / "notes" / "solar_validation_reference.json"

_spec = importlib.util.spec_from_file_location("solar_stage", ROOT / "src" / "20_solar.py")
_solar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_solar)

USNO_API = "https://aa.usno.navy.mil/api/rstt/oneday"

# lat, lon, standard UTC offset (hours), why this site is in the list
SITES = {
    "Miami, FL": (25.7617, -80.1918, -5, "low latitude, small seasonal amplitude"),
    "Indianapolis, IN": (39.7684, -86.1581, -5, "far west of its zone meridian: the case the argument is about"),
    "Seattle, WA": (47.6062, -122.3321, -8, "high-ish latitude, large amplitude"),
    "Anchorage, AK": (61.2181, -149.9003, -9, "extreme amplitude"),
    "Honolulu, HI": (21.3069, -157.8583, -10, "near-degenerate; sun transits north of zenith in summer"),
}

DATES = [
    ("2026-01-05", "near the latest sunrise of the year"),
    ("2026-03-20", "March equinox"),
    ("2026-06-21", "June solstice"),
    ("2026-09-22", "September equinox"),
    ("2026-12-21", "December solstice"),
]

# USNO publishes to the minute, so 30s of the budget is rounding before our own
# error is counted at all.
TOL_SEC = 90.0

PHEN = {
    "Rise": "sunrise",
    "Set": "sunset",
    "Upper Transit": "solar noon",
    "Begin Civil Twilight": "civil dawn",
    "End Civil Twilight": "civil dusk",
}


def fetch_usno() -> dict:
    ref: dict = {}
    for site, (lat, lon, tz, _why) in SITES.items():
        for date, _label in DATES:
            resp = requests.get(
                USNO_API,
                params={"date": date, "coords": f"{lat},{lon}", "tz": tz, "dst": "false"},
                timeout=40,
            )
            resp.raise_for_status()
            data = resp.json()["properties"]["data"]
            entry = {}
            for item in data["sundata"]:
                if item["phen"] in PHEN:
                    entry[PHEN[item["phen"]]] = item["time"]
            ref[f"{site}|{date}"] = entry
            print(f"  fetched {site}|{date}: {entry}")
            time.sleep(0.5)
    return ref


def local_hhmm_to_utc(date: str, hhmm: str, tz_hours: int) -> pd.Timestamp:
    """USNO time-of-day in the requested offset -> UTC instant."""
    naive = pd.Timestamp(f"{date} {hhmm}")
    return naive.tz_localize("UTC") - pd.Timedelta(hours=tz_hours)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if args.refresh or not USNO_REF.exists():
        print("fetching USNO reference values…")
        usno = fetch_usno()
        USNO_REF.parent.mkdir(parents=True, exist_ok=True)
        USNO_REF.write_text(json.dumps(usno, indent=2, sort_keys=True) + "\n")
        print(f"cached -> {USNO_REF.relative_to(ROOT)}")
    else:
        usno = json.loads(USNO_REF.read_text())
        print(f"using cached USNO reference: {USNO_REF.relative_to(ROOT)}")

    noaa = json.loads(NOAA_REF.read_text()) if NOAA_REF.exists() else {}

    days = pd.date_range("2026-01-01", "2026-12-31", freq="D", tz="UTC")
    date_index = {d.isoformat(): i for i, d in enumerate(days.date)}

    rows = []
    for site, (lat, lon, tz, _why) in SITES.items():
        res = _solar.solve_county(lat, lon, days)
        for date, _label in DATES:
            i = date_index[date]
            ours_map = {
                "solar noon": res["solar_noon_utc"].iloc[i],
                "sunrise": res["sunrise_geom_utc"].iloc[i],
                "sunset": res["sunset_geom_utc"].iloc[i],
                "civil dawn": res["dawn_civil_utc"].iloc[i],
                "civil dusk": res["dusk_civil_utc"].iloc[i],
            }
            noaa_map = {}
            nref = noaa.get(f"{site}|{date}")
            if nref:
                noaa_map = {
                    "solar noon": pd.Timestamp(nref["solar_noon"]),
                    "sunrise": pd.Timestamp(nref["sunrise"]),
                    "sunset": pd.Timestamp(nref["sunset"]),
                    "civil dawn": pd.Timestamp(nref["civil_begin"]),
                    "civil dusk": pd.Timestamp(nref["civil_end"]),
                }
            for quantity, ours in ours_map.items():
                hhmm = usno[f"{site}|{date}"].get(quantity)
                if hhmm is None or pd.isna(ours):
                    continue
                ref_ts = local_hhmm_to_utc(date, hhmm, tz)
                dev = (ours - ref_ts).total_seconds()
                noaa_dev = (
                    (noaa_map[quantity] - ref_ts).total_seconds()
                    if quantity in noaa_map
                    else float("nan")
                )
                rows.append(
                    {
                        "site": site,
                        "date": date,
                        "quantity": quantity,
                        "ours_utc": ours.strftime("%H:%M:%S"),
                        "usno_utc": ref_ts.strftime("%H:%M"),
                        "dev_sec": dev,
                        "noaa_api_dev_sec": noaa_dev,
                    }
                )

    df = pd.DataFrame(rows)

    print("\n--- per-quantity |deviation| from USNO (seconds) ---")
    summary = (
        df.assign(abs_dev=df["dev_sec"].abs())
        .groupby("quantity")["abs_dev"]
        .agg(n="size", median="median", max="max")
    )
    print(summary.to_string(float_format=lambda v: f"{v:.1f}"))

    print("\n--- per-site max |deviation| from USNO ---")
    print(
        df.assign(abs_dev=df["dev_sec"].abs())
        .groupby("site")["abs_dev"]
        .max()
        .sort_values(ascending=False)
        .to_string(float_format=lambda v: f"{v:.1f}")
    )

    print("\n--- worst 8 rows ---")
    print(
        df.reindex(df["dev_sec"].abs().sort_values(ascending=False).index)
        .head(8)
        .to_string(index=False, float_format=lambda v: f"{v:+.0f}")
    )

    if not df["noaa_api_dev_sec"].isna().all():
        print("\n--- for comparison: sunrise-sunset.org vs USNO, same rows ---")
        cmp = (
            df.assign(abs_dev=df["noaa_api_dev_sec"].abs())
            .dropna(subset=["abs_dev"])
            .groupby("quantity")["abs_dev"]
            .agg(median="median", max="max")
        )
        print(cmp.to_string(float_format=lambda v: f"{v:.1f}"))
        print("  (reported only; this is why USNO is the gate)")

    worst = df["dev_sec"].abs().max()
    print()
    if worst > TOL_SEC:
        print(f"FAIL: max deviation from USNO {worst:.1f}s exceeds {TOL_SEC:.0f}s")
        return 1
    print(
        f"PASS: max deviation from USNO {worst:.1f}s, within {TOL_SEC:.0f}s "
        "(of which ~30s is USNO's minute rounding)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
