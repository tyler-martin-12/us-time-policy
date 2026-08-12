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
| 4 | `optimized` | Per-county **integer-hour** offset chosen by optimisation, constrained to use no more mismatched county borders than today's map. See §9. |

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
- **Weights:** the **2020 census count**, taken from the `POPULATION` column of
  `CenPop2020_Mean_CO.txt`. Column `pop_weight` in `counties.parquet`. Every
  national or state aggregate is population-weighted:
  `weighted = Σ(pop_i × metric_i) / Σ(pop_i)`. Sums to 331,449,281, which matches
  the published 2020 census total for the 50 states plus DC.

  **This reverses an earlier choice, for a concrete reason.** Vintage 2025
  estimates (`co-est2025-alldata.csv`) were the first pick, on the grounds that
  "how many people live with this misalignment *now*" is the better question. They
  turn out to be unusable as the primary weight: **Connecticut abolished its
  counties for statistical purposes**, so vintage 2025 reports 9 planning regions
  under new FIPS codes that do not nest into the 2020 county boundaries this
  pipeline uses. All 8 Connecticut counties come back null on the join, and they
  cannot be backfilled by aggregation because the old and new units do not nest.

  Using the 2020 count puts boundaries, point locations and weights all on a
  single vintage with no gaps, which for a longitude-driven metric matters more
  than five years of population drift. `pop_2025_est` is still carried in
  `counties.parquet` as a sensitivity column, null for those 8 counties.
- **Time zone per county:** `timezonefinder` queried at the center of population,
  giving an IANA zone name. Deliberately no hand-maintained exception list;
  Arizona, the Navajo Nation and zone-straddling counties all resolve from
  geometry. Note the provenance carefully: the *names* are IANA, but the
  *polygons* are OpenStreetMap's timezone-boundary-builder, which encodes
  observed practice rather than the legal boundaries in 49 CFR Part 71. That is
  the intended input and it is not the same thing as "from the IANA database".
  See §6a.

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
for a split county therefore describe *the zone at the population-weighted mean
location of its residents*, not the whole county's area.

That is weaker than it first looks and the earlier wording here overstated it.
The center of population falling in zone A does **not** establish that a
majority of residents live in zone A: a mean is not a median, and a county with
two clusters can have its mean land in the emptier one. Since sub-county
population by time zone is not available in the source data, the honest claim
is that this is the single best available point estimate for the county, not
that it represents most of its people.

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

No attempt is made to apportion population within a county between zones. The
count of affected counties and their combined population is printed in the run
summary so the size of the caveat is visible.

---

## 6a. Observed practice vs the law

Raised in review, checked, and resolved in favour of keeping what we have.

`timezonefinder` returns IANA zone names, but its polygons are OpenStreetMap's
timezone-boundary-builder. Those are drawn to match **what clocks people
actually keep**. The legal boundaries are a different object: 49 CFR Part 71,
digitised by USDOT's Office of General Counsel and published in the National
Transportation Atlas Database.

`src/26_validate_tz.py` compares the two at every county's center of population
and commits the result. It is not part of the pipeline, because the project
deliberately does not use the legal layer and there is no reason to make every
rebuild download it.

The disagreement, in full:

| County | Ours (observed) | DOT (legal) | Population |
| --- | --- | --- | --- |
| Chambers, AL | Eastern | Central | 34,772 |
| Russell, AL | Eastern | Central | 59,183 |

Plus one county, Aleutians West, whose center of population falls inside no DOT
polygon at all. That is a coastline digitisation artefact in their layer, not a
finding about ours.

**Observed practice is the correct input for this metric**, and the reasoning is
not a preference. The whole quantity being measured is how far a person's clock
sits from their sun, so the clock that matters is the one they read. Phenix City
in Russell County is legally Central and runs on Eastern, along with a radius of
surrounding towns including Smiths Station, because it belongs to the Columbus,
Georgia economy. Putting those 59,183 people on Central would model a clock
nobody there uses.

**It does not cut cleanly, and that is worth stating.** In Chambers County only
Lanett and Valley, on the Georgia edge, keep Eastern, so assigning the whole
county to Eastern is arguably worse than the legal answer. Neither layer is
right for every county. This is a county-resolution model meeting a
sub-county-resolution reality, the same limitation as §6.

**It does not matter numerically.** 93,955 people, 0.028% of the population.
Under today's map at standard time the population-weighted mean misalignment is
16.9521 min on observed practice and 16.9461 min on the legal layer, a
difference of 0.36 seconds.

So: report it, do not switch. What *was* wrong was the description. Saying zones
"come from the IANA database" is loose enough to be a fair catch, and it has
been corrected everywhere it appeared.

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
| `latest_sunrise_local` | Max local clock `sunrise_geom` over the year. **Max of local time-of-day, not of the absolute instant** — taking the argmax of the UTC timestamp trivially returns Dec 31 for every county | Null days excluded |
| `latest_sunrise_date` | Date achieving it. See the note below: under CTA this is usually a DST boundary day, not January |
| `days_dawn_after_0730` | Civil-twilight sensitivity version of the sunrise count | as above |

Thresholds `07:30` and `17:00` are parameters, not literals, and appear in the
output metadata so a reader can see they were chosen rather than derived.

### Finding: under CTA the latest sunrise is a DST boundary day

§3 says the latest sunrise falls in early January. That is true of *solar*
sunrise, and therefore true under **permanent standard time** (and under
permanent DST, shifted an hour). It is **not** generally true under CTA, because
DST adds an hour to the clock while the sun is already rising late in autumn.
Measured on the built solar layer:

| County | Latest clock sunrise under CTA |
| --- | --- |
| Marion, IN (Indianapolis) | **Oct 31, 08:12** |
| New York, NY | **Oct 31, 07:25** |
| King, WA (Seattle) | Jan 1, 07:56 |
| Honolulu, HI | Jan 15, 07:11 (no DST) |
| Anchorage, AK | Dec 26, 10:14 |
| Miami-Dade, FL | **Mar 8, 07:37** |

Oct 31 2026 is the last full day of DST and Mar 8 is the first. So for much of
the country the latest sunrise of the year is manufactured by the DST rules
rather than by the sun, and an 08:12 sunrise in Indianapolis at the end of
October is a compact statement of the whole argument.

This also serves as a correctness check on the CTA regime: the metric landing
precisely on the two 2026 transition dates is evidence that offsets are coming
from the tzdb correctly.

Both a per-county table and population-weighted rollups (national, per state)
are produced. The intra-zone spread statistics — for each existing zone, the
min, max and population-weighted IQR of `offset_annual_mean` — are what carry
the argument, so they get their own table:
`data/out/zone_spread.csv`.

---

## 9. Optimisation

**Revised after review.** The formulation below is what ships; the original
penalty-only spec, kept beneath it, is now the search heuristic rather than the
published result. Three things were wrong with it and all three are fixed in
`src/50_optimize.py`.

### 9.1 What is published: the border budget

```
minimise   Σ_i pop_i · |offset_i − ideal_i|
subject to Σ_(i,j) ∈ E  [offset_i ≠ offset_j]  ≤  B
```

with `B` set to the number of mismatched borders in **today's** map, computed at
run time rather than written down. Today's map uses 246 of 8,933.

This replaced the penalty form as the published statement for one reason: it
makes the headline claim prove itself. Any feasible solution *is* the witness.
It exhibits a whole-hour map no more fragmented than today's, at a cost you can
measure. The solver's optimality gap bounds how much better a tidy map could be
and has no bearing on whether this one exists, so an unproven solution costs the
argument nothing. Under the penalty form the same claim needed a lambda, and a
lambda needs defending.

**Say "borders", not "tidy".** The constraint is on mismatched county borders,
which is the measure the proof is about. Contiguous regions and enclave counties
are reported alongside it and are *not* constrained, because connectivity
constraints in CP-SAT are a different and much harder problem. Do not let a
qualitative word carry a mathematical claim: the provable statement is about
border count, everything else is description.

### 9.2 Ties, and why the old numbers were not reproducible

The first implementation rounded misalignment to whole minutes and population to
thousands. Misalignment rounding left **70 counties exactly tied** between two
offsets, and 186 within a minute of the boundary. The objective value was unique
and proved optimal; **the assignment achieving it was not**. So every
descriptive statistic of the winning map, its border count, its distinct offsets,
its region count, was an arbitrary pick among optima. The §13 sweep table below
recorded 252 borders for the unconstrained optimum where `round(lon/15)` gives
260, and an outside reviewer re-running the repo naturally got the 260. The
region and enclave counts that reached the blog draft came from the same place.

Misalignment is now carried in **thousandths of a minute** with **unrounded
population**, which leaves zero exact ties, and `λ = 0` is asserted to return
`round(lon/15)` *exactly* rather than merely "no county above its own minimum".
Note the tie count by scale, in case a coarser one is ever wanted for speed:

| Resolution | Exact ties |
| --- | --- |
| 1 minute | 70 |
| 0.1 minute | 6 |
| 0.01 minute | 0 |
| 0.001 minute | 0 |

The integer scale affects only *which* assignment the search picks. Every
published figure is scored afterwards at full float precision from the
assignment itself, so the quantum never enters a quoted number.

### 9.3 Reproducibility is on the artefact, not the search

Measured head to head at identical scaling, single-worker CP-SAT could not
improve on its own warm start where eight workers reached 221 borders. Buying
bit-reproducibility at that price would be a bad trade, and an unnecessary one.

So the search runs wide, and the guarantee lives on the output: the assignment
is committed to `data/committed/optimized_offsets.csv` with its SHA-256, and
`src/verify_solution.py` recomputes every published statistic from that file
with no solver involved. That check survives an OR-Tools upgrade, a different
machine and a different worker count, none of which a reproducible search would.
Deterministic time replaces wall-clock as the limit anyway, with a wall-clock
safety net that flags itself in the sweep output if it ever binds.

### 9.4 How the published map is chosen

Every solve, penalty or budget, contributes a candidate. The published map is
the one with the **lowest misalignment among all candidates whose border count
is within the budget**. Which form or which lambda produced it is an
implementation detail of the search, recorded in `optimize_meta.json` for
honesty but not a choice anyone has to defend. No arbitrary constant survives
into the result.

### 9.5 The original penalty spec, retained as the search heuristic

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

## 13. First results (stages 1–4 complete)

Output, not specification. Everything below is regenerable from
`data/out/metrics.csv`, `zone_spread.csv` and `rollups.csv`.

### The headline claim holds, with one exception

Intra-zone spread of annual mean signed solar offset, **permanent standard time**
(chosen so DST is not itself contributing to the spread):

| Zone | Counties | Min | Max | **Range** | Pop-weighted IQR |
| --- | --- | --- | --- | --- | --- |
| Eastern | 1,153 | −57.1 | +30.1 | **87.3 min** | 30.4 |
| Central | 1,492 | −59.3 | +20.3 | **79.5 min** | 32.5 |
| Mountain | 304 | −48.2 | +18.2 | **66.5 min** | 27.4 |
| Pacific | 159 | −17.3 | +21.5 | 38.8 min | 16.8 |

Eastern, Central and Mountain each span more than the 60 minutes Congress is
arguing about. **Pacific does not** (38.8 min), and the post should say so rather
than implying the claim is universal — it is the narrowest zone in longitude.

Even the population-weighted interquartile range is ~30 min in the three big
zones: the *middle half* of the population inside one zone spans half the
disputed hour.

### Share of population living more than 60 min from clock noon

| Regime | Share | Counties |
| --- | --- | --- |
| Permanent standard time | **0.04%** | 13 (all Alaska) |
| Current law | **34.8%** | 1,413 |
| Permanent DST | **68.2%** | 2,480 |
| Per-county ideal | 0.0% | 0 |

The permanent standard time row is 148,976 people, every one of them in Alaska.
It was previously written as 0.0% and described in the draft as "almost nobody",
which rounds a real and nameable population to nothing. Quote the count.

### Population-weighted national metrics

| Regime | Annual offset | January offset | Days sunrise after 07:30 | Days sunset before 17:00 |
| --- | --- | --- | --- | --- |
| Permanent ST | −11.9 | −21.3 | 22.1 | 44.3 |
| Current law | −50.0 | −21.3 | 38.5 | 42.3 |
| Permanent DST | −71.9 | −81.3 | **136.4** | 0.2 |
| Per-county ideal | −1.4 | −10.8 | 11.0 | 62.3 |

The trade-off is real and should be presented as one: the per-county ideal beats
every uniform policy on dark mornings (11 days vs 22–136) while being the *worst*
on early sunsets (62.3 days). Permanent DST essentially abolishes early sunsets
and pays for it with 136 days a year of post-07:30 sunrises.

### Sanity checks that passed exactly

- `perm_dst − perm_st` = **−60.0000 min** for all 3,143 counties, confirming the
  sign convention end to end.
- Non-DST counties (19: Arizona's 14 and Hawaii's 5) are **identical** under CTA
  and permanent standard time, deviation 0.0000.
- `cta − perm_st` = **−39.12 min** uniformly, which is exactly 238 DST days ÷ 365
  × 60. An independent arithmetic check on the tzdb offsets.
- Solar layer nulls are exactly the two Arctic county cases: North Slope (70.5°N,
  133 days) and Northwest Arctic (66.9°N, 37 days).

### Stage 5: the optimisation

**These numbers replace an earlier set that was not reproducible.** See §9.2 for
why. Everything below is regenerated by `50_optimize.py` and `55_regions.py`,
and re-derivable from the committed assignment by `verify_solution.py` with no
solver involved.

The three reference maps, all measured the same way, islands excluded from the
region and enclave counts:

| Assignment | PW mean abs | Borders | Offsets | Regions | Excess | Enclaves |
| --- | --- | --- | --- | --- | --- | --- |
| Today, standard time | 16.952 | 246 | 6 | 6 | **0** | **0** |
| Unconstrained, round(lon/15) | 14.517 | 260 | 8 | 12 | 4 | 7 |
| **Published** | **14.526** | **241** | 8 | 9 | 1 | 2 |

**Excess** is regions minus mainland offsets: the pieces beyond one connected
band per offset. It is the fragmentation measure worth using, because raw region
count punishes a map for using more offsets, which is the thing it is supposed
to be doing. Today's map is perfectly banded and scores 0.

**The finding, stated on the count rather than the clock.** The published map
uses **241** mismatched county borders against today's **246**. It is not a
compromise with tidiness, it draws fewer lines than the system we have. The
alignment given up is 14.526 − 14.517 = **0.0094 min = 0.56 seconds** per
person, measured in the real-solar metrics system rather than the optimiser's
proxy (the two agree to 0.01 s).

**Border count alone is not enough, and finding that out was the surprise.**
Minimising misalignment subject only to ≤ 246 borders solves to a 0.008% gap at
14.518, essentially free. But that map has excess 3 and strands 6 counties: the
budget is satisfied by scattering fragments rather than by moving bands. Hence
the two-stage selection rule in §9.4, which sorts on excess first.

**What it actually looks like.** Across the lower 48 the published map is four
clean contiguous bands, exactly as today's is, plus Washington County, Maine on
Atlantic time. That last one is not a quirk: its centre of population is at
longitude −67.466, an ideal offset of −4.498, so it belongs on the Atlantic side
by about 17 seconds, and `round(lon/15)` puts it there too. The single unit of
excess is Alaska and Hawaii both legitimately sitting at −10 while not being
contiguous with each other, which is geography, not fragmentation.

918 counties change offset, 16.9% of the population. The largest are San Antonio
and Austin (Central → Mountain), Detroit, Columbus, Atlanta and Indianapolis
(Eastern → Central), and Honolulu (−10 → −11).

**Honesty about the solver.** The published map carries a 20% gap on its own
penalty objective, and that costs the argument nothing, because the claim is
constructive: the map exists, its borders can be counted, and the unconstrained
optimum at 14.517 is a proved lower bound on what any assignment can achieve.
What is *not* claimed is that this is the best map within the budget.

### Illustrative counties, all three inside today's Eastern zone

| County | Current law | Permanent ST | Permanent DST | Published |
| --- | --- | --- | --- | --- |
| Ontonagon, MI | −96 | −57 | −117 | **+3** |
| Marion, IN (Indianapolis) | −84 | −45 | −105 | **+15** |
| Washington, ME | −9 | **+30** | −30 | **−30** |

One zone, and under permanent standard time its ends differ by 87 minutes. The
optimiser fixes the western end; Maine's tip flips sign rather than staying put,
because moving it to Atlantic time changes +30.1 into −29.9 and is very slightly
better. Equal in absolute misalignment to within a fifth of a minute, so do not
read the flip as a finding.

### Worst-aligned counties, permanent standard time

All Alaska, which is why it is inset: Aleutians West −132.6 min, Nome −121.1,
Kusilvak −117.4. Nome's latest sunrise is **12:02** — after noon.

## 14. Open questions for Tyler

1. **`exempt_current_non_observers`** for permanent DST — default off (all
   counties move) or on (matches real bills)? §4.
2. **Puerto Rico** in the headline maps, or left behind the flag? §5.
3. **Winter statistic = January mean.** Reasonable, or would you rather it were
   the December solstice month, or the whole DST-off period? §3.
4. **07:30 and 17:00** as the count thresholds — keep, or different?
