# NOTES.md — definitions and conventions

Pins down every definitional choice before any pipeline code exists, so results
can't be quietly reinterpreted later. Nothing here is a result; it is all
specification. If a number appears below it is an anchor for a unit test, not a
finding.

**Argument this is built to support:** the DST vs standard time debate is about a
one-hour offset applied uniformly, but the variation in solar misalignment
*within a single existing time zone* is already comparable to or larger than one
hour. So the policy variable that matters is zone boundaries and per-place
offsets, not which of two labels the whole country picks.

---

## 1. Model year

**2026.** Non-leap, so exactly 365 days, which keeps every county-day array a
clean `(3143, 365)`. Read out of the tzdb rather than hardcoded, and confirmed:

- US DST 2026 runs **Mar 8** to **Nov 1** (second Sunday in March, first Sunday
  in November).
- `America/Phoenix` holds UTC−7 all year, i.e. Arizona falls out of the tzdb
  correctly with no special-casing.

Days are calendar days in **local civil time under the regime being evaluated**,
not UTC days. This matters at the edges: a county-day is "the day whose local
noon we are measuring", which is unambiguous even on transition days because no
US transition happens near noon.

---

## 2. Sign convention (the thing most likely to be misread)

```
signed_solar_offset = clock_noon − true_solar_noon        [minutes]
```

Both sides are instants; the difference is signed minutes. `clock_noon` is the
instant at which the regime's local civil clock reads 12:00:00. `true_solar_noon`
is the instant of the sun's upper meridian transit at the county's center of
population, from pvlib's NREL SPA implementation.

| Sign | Means | Feels like | Example |
| --- | --- | --- | --- |
| **positive** | solar noon happens *before* clock noon; the sun runs early | early sunrise, early sunset | eastern edge of a zone (Maine) |
| **zero** | clock noon is solar noon | — | longitude exactly on the zone meridian |
| **negative** | solar noon happens *after* clock noon; the sun runs late | late sunrise, late sunset | western edge of a zone (western Michigan) |

**Consequence that must be stated on every chart: adding an hour of DST
subtracts 60 minutes from this metric.** Permanent DST makes the number *more
negative* everywhere it applies. This is the correct behaviour, not a bug, and
it is why the diverging colour scale must be centred on zero with a fixed
symmetric domain rather than auto-scaled per panel.

### Unit-test anchors

Pure-longitude cases, ignoring the equation of time (so these are mean-solar
anchors, tested with EoT forced to zero):

| Longitude | Standard offset | Solar noon (UTC) | Clock noon (UTC) | Expected metric |
| --- | --- | --- | --- | --- |
| −67.5° | UTC−5 | 16:30 | 17:00 | **+30 min** |
| −75.0° | UTC−5 | 17:00 | 17:00 | **0 min** |
| −82.5° | UTC−5 | 17:30 | 17:00 | **−30 min** |
| −75.0° | UTC−4 (DST) | 17:00 | 16:00 | **−60 min** |

A zone meridian is at longitude `15 × offset_hours`, so UTC−5 → −75°, UTC−6 →
−90°, UTC−7 → −105°, UTC−8 → −120°.

---

## 3. Equation of time, and why there are two headline numbers

The equation of time `E = apparent solar time − mean solar time` swings roughly
+14 to −16 minutes across the year. It enters the metric with a **positive**
sign: when `E` is positive the sun is early and the metric is more positive.

- `E` peaks positive around **early November** (sun earliest relative to clock).
- `E` is most negative around **mid-February** (sun latest relative to clock).

So a single annual number hides a ±15 minute seasonal wobble that is a quarter
of the entire hour under debate. Two statistics are therefore reported and must
always be labelled:

- **`offset_annual_mean`** — mean of the daily signed offset over all 365 days.
  Close to the pure-longitude value because `E` roughly cancels over a year, but
  *not exactly*, and the residual is not worth hiding.
- **`offset_winter`** — mean of the daily signed offset over **Jan 1–31**
  inclusive.

Why January for "winter", specifically:

1. DST is inactive in that window under CTA and under permanent standard time,
   so it isolates the standard-offset geography.
2. It brackets the **latest sunrise of the year**, which falls in early January
   at mid-northern latitudes, not at the solstice. (Sunrise = solar noon − half
   the daylength; through late December solar noon drifts later faster than the
   day lengthens, so sunrise keeps getting later for roughly two more weeks.)
3. `E` is mildly negative across January, so the winter figure is slightly more
   negative than the longitude term alone — the honest direction for a "dark
   mornings" reading, without cherry-picking mid-February's extreme.

---

## 4. Regimes

Each regime is a function `offset(county, instant) → UTC offset`, never a label.
All four are evaluated over the same 365 county-days.

| # | Key | Definition |
| --- | --- | --- |
| 1 | `cta` | **Current law.** Offset comes from `zoneinfo` applied to the county's IANA zone at each instant. DST transition dates are *never hardcoded* — they come from the tzdb, which is also what makes Arizona and the Navajo Nation fall out correctly. |
| 2 | `perm_dst` | Standard offset **+1 hour**, all year. |
| 3 | `perm_st` | Standard offset, all year. Identical to `cta` for counties that already never observe DST. |
| 4 | `optimized` | Per-county **integer-hour** offset chosen by optimisation, contiguity-penalised. Stage 2 — see §9. |

**Standard offset** is defined as the county zone's UTC offset at **12:00 local
on Jan 15, 2026**, a date on which no US zone is in DST. For Arizona and Hawaii
this equals their year-round offset.

### Open decision, flagged for Tyler

Real proposed legislation (e.g. the Sunshine Protection Act) **exempts current
non-observers** — Arizona and Hawaii stay put. That makes `perm_dst` ambiguous.
The pipeline will implement a flag:

- `exempt_current_non_observers = False` (**default**): permanent DST applies
  everywhere, including Arizona and Hawaii. Cleaner as a controlled comparison,
  since every county moves by exactly the same hour and the map shows the pure
  geography.
- `exempt_current_non_observers = True`: matches the actual bills. Arizona and
  Hawaii are unchanged from `cta`.

Default is `False` with the caveat printed in the output. Say the word if you'd
rather the headline maps match the real bills instead.

---

## 5. Geography and population

- **Boundaries:** Census TIGER/Line county shapefiles, 2020 vintage.
  `tl_2020_us_county.zip`, 76.9 MiB, upstream `Last-Modified` 2021-02-02.
- **Point per county:** Census **2020 Center of Population**
  (`CenPop2020_Mean_CO.txt`, 171 KB, upstream 2021-11-16), *not* the geometric
  centroid. Geometric centroids misplace large western counties badly — a
  centroid can sit in empty desert tens of kilometres of longitude away from
  where anyone actually lives, which directly biases a longitude-driven metric.
  File has a UTF-8 BOM (read as `utf-8-sig`) and zero-padded signed coordinates
  (`+32.500194`, `-086.487813`).
- **Weights:** Census **vintage 2025** county population estimates
  (`co-est2025-alldata.csv`, 2.0 MiB, upstream 2026-03-26). Filter `SUMLEV == 050`
  for counties and use `POPESTIMATE2025`. Every national or state aggregate is
  population-weighted: `weighted = Σ(pop_i × metric_i) / Σ(pop_i)`.

  **Mixed vintages, deliberately.** The point locations are 2020 (the most recent
  centers of population published) while the weights are 2025 estimates. The
  alternative is the `POPULATION` column inside `CenPop2020_Mean_CO.txt`, which is
  the 2020 census count and vintage-consistent with the coordinates. Current
  estimates were chosen because the weighting question is "how many people live
  with this misalignment now", and a county's centre of population moves far more
  slowly than its population does. Both columns are carried through stage 1 so
  the choice can be swapped and the sensitivity checked.
- **Time zone per county:** `timezonefinder` queried at the center of population,
  giving an IANA zone name. Deliberately no hand-maintained exception list;
  Arizona, the Navajo Nation and zone-straddling counties all resolve from
  geometry.

### Scope

**Baseline: 50 states + DC = 3,143 counties and county equivalents (2020).**

Puerto Rico's 78 municipios are available in TIGER and the offset metric is
meaningful there, so PR sits behind an `include_pr` flag, default off. Guam,
USVI, American Samoa and the Northern Marianas are out of scope: they are not in
the same state-based county series, and their offsets add nothing to an argument
about the contiguous zone structure. Flagged as an open question rather than
silently dropped.

---

## 6. Split counties

Roughly 20 counties are split across two time zones. Resolution:

**A county gets exactly one zone, taken from its center of population.** Metrics
for a split county therefore describe *the zone the majority of its people live
in*, not the whole county's area.

Detection, so this is reported rather than assumed: sample `timezonefinder` over
a grid of points inside each county polygon plus its boundary vertices, and flag
any county returning more than one distinct zone. Output
`data/out/split_counties.csv` with columns:

| Column | Meaning |
| --- | --- |
| `geoid` | County FIPS |
| `name`, `state` | Labels |
| `zone_assigned` | Zone at the center of population, the one used |
| `zones_detected` | All distinct zones found in the county |
| `n_sample_points`, `n_points_per_zone` | Crude area indication of the split |

No attempt is made to apportion population within a county between zones —
sub-county population by time zone is not available in the source data. The
count of affected counties and their combined population is printed in the run
summary so the size of the caveat is visible.

---

## 7. Solar layer

`pvlib` (NREL SPA), fully vectorised over a `(county, day)` grid — 3,143 × 365 =
1,147,195 county-days. Per county-day, computed at the center of population:

| Quantity | Definition |
| --- | --- |
`solar_noon` | Sun's upper meridian transit |
`sunrise_geom` | Solar elevation crossing **−0.833°** (34′ refraction + 16′ solar semidiameter), rising |
`sunset_geom` | Same threshold, setting |
`dawn_civil` | Solar elevation crossing **−6°**, rising |
`dusk_civil` | Same, setting |

Both thresholds are produced so the choice is **visible in the output rather
than baked into a definition**. The `−0.833°` figure is conventional "sunrise";
`−6°` is civil twilight, which is arguably the better proxy for "is it light
enough to function". Headline sunrise metrics use the geometric threshold; civil
twilight is carried as a sensitivity column.

All solar quantities are computed and stored as **UTC instants**, converted to
local clock time only at metric time, per regime. Storing local times would
require recomputing the solar layer for every regime, which is both wasteful and
an invitation to inconsistency.

### Polar edge cases

At high Alaskan latitudes there are days with no sunrise or sunset crossing.
Those are stored as null, not clamped to midnight, and every count metric
documents its null handling (see §8).

### Validation gate

The solar layer is not accepted until it reproduces published sunrise/sunset
times for a spread of sites and dates to within **±1 minute**, against USNO or
NOAA values. Test sites chosen to span the failure modes:

| Site | Why |
| --- | --- |
| Miami, FL | Low latitude, small amplitude |
| Indianapolis, IN | Mid-latitude, far west of its zone meridian — the case the whole argument is about |
| Seattle, WA | High-ish latitude, large amplitude |
| Anchorage, AK | Extreme amplitude |
| Honolulu, HI | Near-degenerate seasonality |

Dates: both solstices, both equinoxes, and Jan 5 (near latest sunrise).

---

## 8. Metrics

One row per **county × regime**. Primary metric first.

| Column | Definition | Null handling |
| --- | --- | --- |
| `offset_annual_mean` | Mean signed solar offset, 365 days | n/a |
| `offset_winter` | Mean signed solar offset, Jan 1–31 | n/a |
| `days_sunrise_after_0730` | Count of days where local clock `sunrise_geom` > 07:30 | Days with no sunrise count as **satisfying** the condition (the sun never came up, which is strictly worse than a late sunrise); count of such days reported separately as `days_no_sunrise` |
| `days_sunset_before_1700` | Count of days where local clock `sunset_geom` < 17:00 | Days with no sunset count as satisfying; `days_no_sunset` reported separately |
| `latest_sunrise_local` | Max local clock `sunrise_geom` over the year | Null days excluded |
| `latest_sunrise_date` | Date achieving it — expected in early January, and worth checking, because landing on the solstice means the calculation is wrong |
| `days_dawn_after_0730` | Civil-twilight sensitivity version of the sunrise count | as above |

Thresholds `07:30` and `17:00` are parameters, not literals, and appear in the
output metadata so a reader can see they were chosen rather than derived.

Both a per-county table and population-weighted rollups (national, per state)
are produced. The intra-zone spread statistics — for each existing zone, the
min, max and population-weighted IQR of `offset_annual_mean` — are what carry
the argument, so they get their own table:
`data/out/zone_spread.csv`.

---

## 9. Optimisation (stage 2, not started)

Do not begin until stages 1–5 are done and reviewed.

Integer program over the county adjacency graph:

```
minimise   Σ_i pop_i · |offset_i − ideal_i|  +  λ · Σ_(i,j) ∈ E  [offset_i ≠ offset_j]
```

- `offset_i` — integer hours, restricted to the UTC offsets plausibly in play.
- `ideal_i` — the offset that would put solar noon at clock noon.
- `λ` — **penalty per adjacent mismatched pair, a parameter, swept not fixed.**
  λ = 0 recovers the unconstrained solution.
- Adjacency `E` — TIGER county geometries sharing a boundary of **non-zero
  length** (rook, not queen), so counties meeting at a single corner are not
  treated as neighbours.
- Islands and counties with no land neighbours have no adjacency terms and are
  therefore unconstrained; they must be listed in the output so a stray offset
  in Nantucket isn't mistaken for a solver bug.
- Solver: PuLP or OR-Tools CP-SAT. CP-SAT is the better fit for the `≠`
  indicator structure.

**Produce the unconstrained (λ = 0) solution first, as a reference.** It should
come out as approximately "round the longitude to the nearest 15°", and if it
doesn't, the objective is wrong. That check is cheap and catches sign errors in
`ideal_i`.

---

## 10. Mapping

- **Four-panel choropleth of signed solar offset**, one panel per regime, all
  four sharing **one fixed diverging colour scale centred on zero**. Per-panel
  auto-scaling would destroy the entire comparison, since permanent DST shifts
  every value by −60.
- Scale domain fixed and symmetric, chosen once from the CONUS distribution and
  written into the output metadata. Values outside it are **clipped, and the
  clipping is stated in the caption**, not silently saturated.
- **Alaska is inset and handled separately.** Alaska Time spans roughly −130° to
  −170° of longitude, so its offsets are far outside the CONUS range and would
  dominate any shared scale. Hawaii and (if enabled) PR are also insets. Insets
  use the same scale as CONUS so they remain comparable, with clipped values
  marked.
- Projection: Albers Equal Area for CONUS, separate appropriate projections for
  the insets. Equal-area matters because the argument is partly about how much
  *land and population* sits far from its zone meridian.

---

## 11. Pipeline shape

Scripts, cached intermediates, no notebook. Each stage is independently
re-runnable and skips work when its output exists and inputs are unchanged.

```
src/
  00_fetch.py       # downloads -> data/raw/, verifies checksums, never re-downloads
  10_counties.py    # geometry + centers of population + population + IANA zone -> data/interim/counties.parquet
  20_solar.py       # pvlib SPA over (county, day) -> data/interim/solar.parquet   (UTC instants)
  30_metrics.py     # regimes x metrics -> data/out/metrics.csv, zone_spread.csv, split_counties.csv
  40_maps.py        # four-panel choropleth -> data/out/*.png
  50_optimize.py    # stage 2, not written yet
notes/              # validation evidence, scratch findings
data/
  raw/  interim/  out/     (all gitignored)
```

- `uv` for dependency management; `pyproject.toml` with pinned versions.
- **Caching:** `data/raw/` holds a `manifest.json` of URL, SHA256, byte size,
  fetch timestamp and upstream `Last-Modified` per file. `00_fetch.py`
  re-downloads only on checksum mismatch or explicit `--force`, so a normal run
  makes zero network requests.
  - The checksum guards **local** integrity (corruption, truncated downloads). It
    is not a pin on upstream content: Census reissues these files, and silently
    trusting a stale local copy forever would be worse than noticing.
    `--check-remote` does a HEAD and reports size / `Last-Modified` drift without
    downloading. Note the centers-of-population URL does not always return
    `Content-Length`, so drift detection there falls back to `Last-Modified`
    alone; the script says `?` for the size rather than pretending to know.
  - Downloads stream to a `.part` file and are renamed only after the byte count
    matches `Content-Length`. An interrupted run must never leave a short file
    that a later run would hash and trust.
- Intermediates are Parquet, not CSV, so dtypes and the UTC-instant distinction
  survive a round trip.
- Every output carries a metadata sidecar recording the parameter values in
  force: model year, twilight thresholds, the 07:30/17:00 cutoffs, the
  `exempt_current_non_observers` flag, `include_pr`, colour scale domain, and λ
  for stage 2.

---

## 12. Things deliberately not done

- **No latitude-driven metric as a headline.** Signed solar offset is used
  precisely because it strips latitude out and isolates the policy variable.
  Sunrise-time metrics do carry latitude, which is why they are secondary and
  reported alongside the offset rather than instead of it.
- **No sub-county apportionment** for split counties (§6).
- **No attempt to model the DST transition weeks themselves** (sleep-loss
  literature, accident spikes). Different argument, different evidence base.
- **No claim about what people should prefer.** The output is the size of the
  intra-zone spread versus the size of the hour under debate.

---

## 13. Open questions for Tyler

1. **`exempt_current_non_observers`** for permanent DST — default off (all
   counties move) or on (matches real bills)? §4.
2. **Puerto Rico** in the headline maps, or left behind the flag? §5.
3. **Winter statistic = January mean.** Reasonable, or would you rather it were
   the December solstice month, or the whole DST-off period? §3.
4. **07:30 and 17:00** as the count thresholds — keep, or different?
