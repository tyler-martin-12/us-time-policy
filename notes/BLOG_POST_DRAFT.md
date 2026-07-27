---
layout: "../../layouts/BlogPost.astro"
title: "The Wrong Hour"
date: "2026-07-27"
description: "Measuring how far every US county's clock sits from its sun, and why the DST debate is arguing about the wrong variable."
slug: "the-wrong-hour"
tags: []
image: "/images/blog/the-wrong-hour/fig_c_before_after.png"
imageAlt: "Two maps of the US coloured by how far each county's clock sits from its sun. Today's map is almost entirely blue; a fitted map is almost entirely white."
---

Washington County, Maine and Ontonagon County, Michigan are in the same time zone. When the clock in both places says noon, the sun over Maine passed overhead half an hour ago, and the sun over Michigan is still nearly an hour from getting there.

That gap is 87 minutes. Congress has spent years arguing about 60.

The two maps above are the argument in one image. On the left is where every US county's clock actually sits relative to its own sun today. On the right is the same country with one fixed offset per county, chosen to fit the sun rather than inherited from a railway timetable. Blue means the sun runs late, red means it runs early, white means the clock and the sun agree.

Two things are worth noticing before any of the detail. The left map is almost entirely blue, and the right map is almost entirely white. And the right map is barely less tidy than the left, which is not what I expected and is the more interesting of the two findings below.

I computed this for all 3,143 US counties. This is a note on how, and on the two results that surprised me.

## The measure

Everything rests on one number, which I'll call the signed solar offset:

> **clock noon minus true solar noon**, in minutes

Positive means the sun runs early: it crosses the meridian before your clock says twelve, so you get early sunrises and early sunsets. That's the eastern edge of a zone. Negative means the sun runs late, which is the western edge.

The reason to use this rather than sunrise times is that sunrise confounds two different things. Anchorage has brutal winter sunrises because it sits at 61°N, and no legislature can do anything about that. Signed solar offset strips latitude out completely and leaves only the part that is actually a policy choice: which UTC offset your clock is set to.

One consequence is worth stating up front, because it trips people up. Adding an hour of daylight saving *subtracts* 60 minutes from this number. Permanent DST makes every county's offset more negative, not less.

It also helps to be clear about what a time zone is. Longitude varies smoothly; clocks jump in whole hours. A time zone is a step function approximating a continuous quantity, and the misalignment is the residual. It is structural. There is no way to set the clocks that makes it zero.

## Building it

Four ingredients.

**Where a county is.** Census TIGER boundaries, but the point I compute the sun at is the Census **centre of population**, not the geometric centroid. This matters more than it sounds. A geometric centroid for a large western county can sit tens of kilometres of longitude away from where anyone actually lives, and since the whole metric is longitude-driven, that would bias the answer directly.

**Which zone it's in.** Resolved from the IANA time zone database by looking up the centre of population. No hand-maintained exception list, which means Arizona, the Navajo Nation and the counties that straddle a boundary all fall out of the geometry rather than out of my assumptions. Roughly 24 counties do straddle a zone boundary; each gets the zone its population centre falls in, and they're listed in the output so the caveat is visible.

**Where the sun is.** NREL's Solar Position Algorithm via pvlib, over 3,143 counties × 365 days of 2026, which is 1.1 million county-days. Everything is stored as UTC instants and converted to local clock time only at the very end, once per regime. Storing local times would mean recomputing the sun for every policy scenario, which is both wasteful and an invitation to the scenarios quietly disagreeing with each other about astronomy.

**What the clock says.** Each policy regime is modelled as a function from (county, instant) to a UTC offset, never as a label. Current law reads its offsets straight from the tz database, so DST transition dates are never hardcoded.

## The validation caught a real problem

I validated the solar layer against published sunrise and sunset times for five sites spanning the failure modes, on five dates spanning the year.

My first reference was a convenient public API. It failed, badly, by up to five minutes at Anchorage. But the pattern was diagnostic rather than alarming: solar noon agreed to within 2 seconds and civil twilight to within 3, while only sunrise and sunset were off, systematically, with the error growing with latitude. That is not what a broken calculation looks like.

So I switched to USNO, the authoritative source, and found that the convenient API is itself 95 to 231 seconds off USNO on sunrise. It was the reference that was wrong.

That still left one problem. pvlib's own sunrise/sunset helper was drifting to 164 seconds at Anchorage near the equinoxes, with the error flipping sign either side. Sunrise was fine, and that asymmetry ruled out a threshold error, since a bad threshold moves sunrise and sunset together. Computing the crossings from the hour angle instead, anchored on the same SPA transit, brought the worst case to 37 seconds.

Final position: solar noon from SPA, all four crossings from the hour angle, everything within 68 seconds of USNO, of which about 30 seconds is USNO's own rounding to the minute. It is worth saying that the gate changed the implementation. A validation step that can only ever confirm what you already did isn't doing anything.

## What it shows

Intra-zone spread of the annual mean offset, on standard time so that DST is not itself contributing:

| Zone | Spread |
| --- | --- |
| Eastern | 87 min |
| Central | 80 min |
| Mountain | 66 min |
| Pacific | 39 min |

Three of the four are internally wider than the hour under debate. Pacific is not, because it is the narrowest zone in longitude, and I'd rather say that than have someone find it.

The min-to-max version invites the objection that the extremes are empty countryside, so here is the stronger form: the population-weighted interquartile range is around 30 minutes in each of the big three. The middle half of the people inside one zone are spread across half the disputed hour.

Set against that, here is what the two proposals do to the share of the population living more than an hour from solar noon:

| | Share more than 60 min out |
| --- | --- |
| Permanent standard time | 0.0% |
| Current law | 34.8% |
| Permanent DST | 68.2% |

To be fair to permanent DST, it nearly abolishes the early-sunset problem, taking the population-weighted count of days with sunset before 5pm from 44 a year to essentially zero. That is a real benefit and it is why people want it. The price is 136 days a year of sunrises after 7:30am, against 22 under permanent standard time. It is a trade, not a mistake.

## Then I tried to fit the country properly

The obvious follow-up: if you assigned offsets to fit the sun instead of inheriting them, how ugly would the map be? I set it up as an integer program over the county adjacency graph, minimising population-weighted misalignment plus a penalty for every pair of neighbouring counties on different offsets, and swept the penalty weight rather than picking one.

Two results, and the second is the honest correction to the first.

**Contiguity is nearly free.** Going from the unconstrained answer to a map as tidy as today's zones costs 0.02 minutes of population-weighted alignment. The intuition that per-place time zones would mean a chaotic patchwork is wrong, because longitude bands are naturally contiguous. Measured as connected regions, the unconstrained solution has 15 with 10 counties stranded in enclaves; the penalised one has 10 and 3, against today's 9 and 3.

That is what the right-hand map at the top of this post is. It is not a patchwork. It has one more contiguous region than the current system and the same number of stranded counties, and it is the near-white one.

**But the average American barely gains.** Today's zone boundaries are already close to as good as whole-hour offsets allow: 16.95 minutes of population-weighted misalignment against a floor of 14.52. Redrawing every boundary in the country buys 2.4 minutes. I had written a much more exciting sentence before I checked that number.

The gain is entirely in the tail. The share of the population more than 30 minutes from solar noon falls from 17.5% to 1.4%. So the case for redrawing zones is not that everyone gains. It is that about 58 million people are badly served and almost none of them need to be.

## The floor

Even the fitted map still spans 61 minutes inside its Eastern band. That isn't a failure of the optimiser. Whole-hour offsets can only ever place you within ±30 minutes of solar noon, so a 60-minute spread is the hard floor of the entire system.

Which is the tidiest way I can put it. The hour Congress is debating is exactly the granularity of the thing it is debating. Both sides are arguing about whether to add or subtract one unit of a quantity whose irreducible internal variation is already one unit.

## What this isn't

Solar alignment is not the only thing time zones are for. Sharing an offset with the city you trade with is worth something real, and none of this measures that. The optimisation is a measuring instrument for how much of the misalignment is structural rather than chosen, not a proposal. And only the low-penalty solutions are proved optimal; above that the solver returns feasible answers with gaps of 2 to 37 percent, so the shape of the curve is trustworthy and any particular map is not.

The number I keep coming back to is Indianapolis. On 31 October 2026, the last full day of daylight saving, the sun there rises at 8:12am. Nothing currently on the table changes that by more than an hour in either direction, and one of the two options makes it worse.

---

## Notes for Tyler, delete before publishing

- **Length:** ~1,450 words. Longer than "short" but this is the methodology
  piece; the LinkedIn post is the short version. Cut §"Then I tried to fit the
  country" if you want it under 1,000.
- **Figures, in order.** Copy all into `public/images/blog/the-wrong-hour/`.
  1. **Hero: `fig_c_before_after_offset_annual_mean.png`**, set in frontmatter so
     the layout renders it at the top. Today vs fitted, and the post now opens by
     reading it. Rename to `fig_c_before_after.png` to match the frontmatter, or
     change the frontmatter.
  2. `fig_a_zone_spread.png` in "What it shows". This is the one that proves the
     87-minute claim generalises; the hero shows the pattern, this shows the
     comparison against 60 minutes.
  3. `signed_solar_offset_four_panel_offset_annual_mean.png` in "What the two
     proposals do". It is the only place permanent DST is shown rather than
     tabulated, and panel 3 going solid dark blue is worth seeing.
  4. `fig_b_two_counties.png` is optional. The opening paragraph now does its job
     in words, so only use it if the post feels like it needs a beat before the
     method section.
- **Style check:** British spelling, no em dashes, no "genuine", contractions
  used sparingly as per the essay pattern in `STYLE.md`.
- **Open question still unresolved:** permanent DST is modelled as applying to
  Arizona and Hawaii too. Real bills exempt them. Currently not mentioned in the
  post; add a line if you want to pre-empt it.
