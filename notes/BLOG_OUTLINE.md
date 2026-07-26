# Blog outline: the DST debate is about the wrong hour

Draft outline, not prose. Every number below is from `data/out/`; nothing is
estimated or remembered. Target length ~2,000 words, following the essay pattern
in the blog's `STYLE.md` rather than the trip-log pattern.

---

## Working titles

- **The wrong hour** — clean, and the argument in two words
- Your time zone is wrong by more than the hour Congress is arguing about
- Indianapolis and Maine are in the same time zone

---

## 1. Open cold, on one concrete fact

No thesis statement first. Open on the two counties.

> Washington County, Maine and Ontonagon County, Michigan are in the same time
> zone. When the clock in both says noon, the sun over Maine has already been
> past its highest point for half an hour, and the sun over Michigan will not get
> there for nearly another hour.

That gap is **87 minutes**. Congress has spent years arguing about **60**.

Then name what the post is about: the debate treats "DST or standard time" as
the question, but it is a uniform shift applied to a country whose existing
misalignment already varies by more than the shift itself.

## 2. The measure: signed solar offset

Explain the one metric everything rests on, and why it is the right one.

- **Definition:** clock noon minus true solar noon, in minutes.
- **Sign:** positive = the sun runs early (early sunrise, early sunset, the
  eastern edge of a zone). Negative = the sun runs late.
- **Why this and not sunrise times:** sunrise time confounds latitude with
  policy. Anchorage has late winter sunrises because it is at 61°N, which no law
  can fix. Signed solar offset strips latitude out entirely and leaves only the
  part a legislature actually controls: which offset your clock is on.
- **The one counterintuitive consequence, state it early:** adding an hour of
  DST *subtracts* 60 minutes from this number. Permanent DST makes every county
  more negative.

Worth a sentence: a time zone is a step function approximating a continuous
quantity. Longitude varies smoothly; clocks jump an hour. Misalignment is the
residual, and it is structural, not a bug.

## 3. How big is the residual, really

The core table. Intra-zone spread of annual mean offset, under permanent
standard time so DST is not itself contributing:

| Zone | Spread across the zone |
| --- | --- |
| Eastern | **87 min** |
| Central | **80 min** |
| Mountain | **67 min** |
| Pacific | 39 min |

Three of four zones are internally more spread out than the hour under debate.

**Say the exception plainly.** Pacific is not, at 39 minutes, because it is the
narrowest zone in longitude. The argument is strong but it is not universal, and
a reader who checks should find that we said so first.

Stronger version, because "min to max" invites the objection that the extremes
are empty countryside: the **population-weighted interquartile range** is ~30
minutes in each of the big three zones. The *middle half* of the people inside
one zone are spread across half the disputed hour.

**Figure 1:** the four-panel map. Reader should be able to see the sawtooth of
zone boundaries and the red/blue gradient repeating inside each zone.

## 4. What the two proposals actually do

Reframe both proposals as what they are: uniform shifts of a non-uniform problem.

| | Share of population more than 60 min from clock noon |
| --- | --- |
| Permanent standard time | **0.0%** |
| Current law | 34.8% |
| Permanent DST | **68.2%** |

Population-weighted national numbers:

| Regime | Annual offset | Days/yr sunrise after 07:30 | Days/yr sunset before 17:00 |
| --- | --- | --- | --- |
| Permanent ST | −11.9 | 22 | 44 |
| Current law | −50.0 | 39 | 42 |
| Permanent DST | −71.9 | **136** | 0.2 |

**Be fair to permanent DST.** It nearly abolishes the early-sunset problem
(0.2 days a year). That is a real benefit and the reason people want it. The
price is 136 days a year of sunrises after 07:30. This is a trade, not a mistake,
and the post should not pretend otherwise.

The point is not which of the two is better. It is that both apply the same
correction to Maine and to Michigan's Upper Peninsula, which are 87 minutes
apart.

## 5. So what would fitting the country actually look like

Set up the optimisation as a question, not a proposal: *if you did assign offsets
to fit the sun, how ugly would the map be?*

- Objective: minimise population-weighted misalignment, plus a penalty for every
  pair of neighbouring counties on different offsets.
- The penalty weight is swept, not chosen. λ = 0 gives the unconstrained answer,
  which is just "round your longitude", and is used as a correctness check.

**Two results, and the second one is the honest correction to the first.**

### Result A: contiguity is almost free

| | PW mean \|offset\| | Contiguous regions | Enclave counties |
| --- | --- | --- | --- |
| Today's zones, permanent ST | 16.95 min | 9 | 3 |
| Unconstrained ideal | 14.52 min | 15 | 10 |
| Optimised | **14.54 min** | **10** | **3** |

Going from the unconstrained ideal to a map as tidy as today's costs **0.02
minutes**. The intuition that per-place time zones mean a chaotic patchwork is
wrong: longitude bands are naturally contiguous, so the tidiness is nearly free.

### Result B: but the average American barely gains, and that is the interesting part

Today's zone *boundaries* are already close to as good as whole-hour offsets
allow, on average: 16.95 min against a theoretical floor of 14.52. **Redrawing
every boundary in the country buys 2.4 minutes of mean alignment.** Do not
oversell this.

The gain is entirely in the **tail**:

| Share of population more than… | Permanent ST | Optimised |
| --- | --- | --- |
| 30 min from solar noon | 17.5% | **1.4%** |
| 45 min from solar noon | 1.4% | **0.0%** |

So the case for redrawing zones is not "everyone gains". It is "**58 million
people are badly served and almost none of them need to be**".

### The floor nobody can get under

Even the optimised map still spans **61 minutes** inside its Eastern band
(−30.9 to +30.5). That is not a failure of the optimiser: whole-hour offsets can
only ever place you within ±30 minutes of solar noon, so ±30 is a hard floor and
a 60-minute spread is structural.

Which is the neatest way to put the whole argument: **the hour Congress is
debating is exactly the granularity of the entire system.** Arguing about which
hour to apply, uniformly, to a country whose irreducible internal spread is
already that same hour.

**Figure 1, panel 4** carries Result A: near-white nearly everywhere.

## 6. The before and after, on three counties

Return to the counties from the opening. Same table as NOTES.md §13:

| County | Today | Permanent ST | Permanent DST | Fitted |
| --- | --- | --- | --- | --- |
| Ontonagon, MI | −96 | −57 | −117 | **+3** |
| Marion, IN (Indianapolis) | −84 | −45 | −105 | **+15** |
| Washington, ME | −9 | +30 | −30 | **+30** |

The fitted map moves Michigan's UP and Indianapolis to Central and leaves Maine
alone. 910 counties move, 16.8% of the population. Note the asymmetry: Maine is
identical under permanent standard time and under the fitted map, because Maine
is already where it should be. All the movement is in the west of each zone. The big movers are Detroit,
Columbus, Atlanta and Indianapolis to Central, San Antonio and Austin to
Mountain.

**Indiana is the honest anecdote here** and worth a short paragraph: it spent
decades fighting over exactly this, county by county, and the fight was
substantive rather than silly. The counties that resisted Eastern time were the
ones the arithmetic says were right.

## 7. Caveats, in their own section

Short, direct, no hedging elsewhere in the piece so this can be crisp.

- **Solar alignment is not the only thing time zones are for.** Trade, broadcast
  schedules, and simply sharing an offset with the city you do business with are
  real. The post measures one axis and says so.
- **The optimiser is not a proposal.** It is a measuring instrument for "how much
  misalignment is structural versus chosen".
- **Only the low-λ solutions are proved optimal.** From λ = 1 upward the solver
  returns feasible solutions with 2–37% gaps. The flatness of the curve is safe;
  a claim that one specific map is *the* optimum is not.
- **County resolution has limits.** ~24 counties straddle a zone boundary and are
  assigned by where their population centre falls.
- **Alaska is off the scale** and is shown inset. Nome's latest sunrise under
  permanent standard time is 12:02, after noon.

## 8. Close

Do not summarise. Land on something concrete, per `STYLE.md`.

Candidate: the Indianapolis 08:12 sunrise on 31 October — the last day of DST,
the latest clock sunrise of the year, in a city that sits 45 minutes west of
where its clock says it is. Nothing in the current debate would change that
number by more than an hour in either direction, and one of the two options
makes it worse.

---

## Figures

| # | Figure | Status |
| --- | --- | --- |
| 1 | Four-panel choropleth, annual mean | **done** — `signed_solar_offset_four_panel_offset_annual_mean.png` |
| 2 | Same, January mean | **done** — shows panels 1 and 2 collapsing to identical, since DST is off in January |
| 3 | Intra-zone spread: dot plot per zone, min/max/IQR, with the 60-minute bar for comparison | **to build** — this is the single most persuasive chart and does not exist yet |
| 4 | λ sweep: alignment vs contiguity trade-off curve | **to build** — small, makes "contiguity is free" visual |

Figure 3 is the one I would add before publishing. The maps show the pattern;
a dot plot per zone with a 60-minute reference bar shows the *comparison*, which
is the actual claim.

## Open questions before drafting prose

1. **Does permanent DST exempt Arizona and Hawaii?** Currently modelled as
   applying everywhere (`EXEMPT_CURRENT_NON_OBSERVERS = False`). Real bills exempt
   them. Panel 3 is the most dramatic panel, so this affects the headline image.
2. **Lead with the map or the two counties?** Outline currently leads with the
   counties and holds the map for §3.
3. **How much method detail in-post vs linked?** Suggest: the metric definition
   and sign convention in-post, everything else in a linked methods note.
