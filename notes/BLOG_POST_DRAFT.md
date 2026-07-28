---
layout: "../../layouts/BlogPost.astro"
title: "I Tried to Redraw America's Time Zones"
date: "2026-07-27"
description: "Solving for the time zone map that fits the sun, and finding that tidiness is nearly free but barely helps the average person."
slug: "redrawing-americas-time-zones"
tags: []
image: "/images/blog/redrawing-americas-time-zones/fig_c_before_after.png"
imageAlt: "Two maps of the US coloured by how far each county's clock sits from its sun. Today's map is almost entirely blue; a fitted map is almost entirely white."
---

I spent a weekend trying to redraw America's time zones to fit the sun, and got two answers I did not expect. One of them argues against the point I set out to make.

The maps above are the result. On the left is where every US county's clock actually sits relative to its own sun today. On the right is the same country with one fixed offset per county, chosen by an optimiser to fit the sun rather than inherited from a railway timetable. Blue means the sun runs late, so late sunrises and late sunsets. Red means it runs early. White means the clock and the sun agree.

## Why bother

The daylight saving debate is about applying one hour, uniformly, to the entire country. That framing quietly assumes everyone starts from the same place, and they do not.

Washington County, Maine and Ontonagon County, Michigan are in the same time zone. When the clock in both says noon, the sun over Maine passed overhead half an hour ago, and the sun over Michigan is still nearly an hour from getting there. That gap is 87 minutes. Congress has spent years arguing about 60.

## This part is not new, and it matters that it is not

I should be straight about what is mine here, because the central observation is not.

Chronobiologists have been making this argument for years. [Roenneberg and colleagues](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2019.00944/full) put it plainly in 2019: standard time zones are gerrymandered, the western edge of most is delayed more than 30 minutes from solar time and sometimes over an hour, and that mismatch matters more than the switching question. [Stefano Maggiolo](https://blog.poormansmath.net/how-much-is-time-wrong-around-the-world/) mapped solar-versus-clock offset for the whole world in 2014 and it went round the internet. If the left-hand map above feels familiar, that is why.

What I could not find was anyone who had actually solved for the right-hand map. That is the part worth reading.

## Why misalignment is worth measuring at all

A measurement needs a stake, and "the clock disagrees with the sun" is not self-evidently a problem. The evidence that it is comes from studies using time zone borders as a natural experiment: two towns a few miles apart, similar in most respects, on different clocks.

The best-identified result is [Giuntella and Mazzonna (2019)](https://www.sciencedirect.com/science/article/abs/pii/S0167629618309718) in the Journal of Health Economics. An extra hour of natural light in the evening, which is what living on the western edge of a zone gives you, costs about **19 minutes of sleep a night** and raises the chance of reporting insufficient sleep. That literature also reports [lower wages and a national cost in the billions](https://theconversation.com/the-hazards-of-living-on-the-right-side-of-a-time-zone-border-116630) on the late-sunset side of borders.

Worth flagging honestly: the more alarming claims in this area are contested. A widely-reported link between position in a time zone and cancer risk was [re-examined by Niu and colleagues in 2023](https://arxiv.org/abs/2306.05921), who found no significant effect on overall cancer incidence and described inconsistencies in the earlier work. The sleep and labour-market findings are on firmer ground than the cancer ones, and I would not lean on the latter.

So: a real effect, modest per person, applied to a lot of people.

## The measure

Everything rests on one number, which I will call the signed solar offset:

> **clock noon minus true solar noon**, in minutes

Positive means the sun runs early, which is the eastern edge of a zone. Negative means it runs late, the western edge.

The reason to use this rather than sunrise times is that sunrise confounds two different things. Anchorage has brutal winter sunrises because it sits at 61°N, and no legislature can do anything about that. Signed solar offset strips latitude out entirely and leaves only the part that is a policy choice: which UTC offset your clock is set to.

One consequence trips people up, so it is worth saying early. Adding an hour of daylight saving *subtracts* 60 minutes from this number. Permanent DST makes every county's offset more negative.

It also helps to be clear what a time zone is. Longitude varies smoothly; clocks jump in whole hours. A time zone is a step function approximating a continuous quantity, and misalignment is the residual. It is structural. No way of setting the clocks makes it zero.

## Building it

Four ingredients, and one of them matters more than it sounds.

**Where a county is.** Census TIGER boundaries, but the point I compute the sun at is the Census **centre of population**, not the geometric centroid. A geometric centroid for a large western county can sit tens of kilometres of longitude from where anyone actually lives, and since the whole metric is longitude-driven that would bias the answer directly.

**Which zone it is in.** Resolved from the IANA time zone database at that point, so Arizona, the Navajo Nation and the counties that straddle a boundary all fall out of geometry rather than out of my assumptions. About 24 counties do straddle a boundary; each takes the zone its population centre falls in, and they are listed in the output so the caveat is visible rather than buried.

**Where the sun is.** NREL's Solar Position Algorithm via pvlib, over 3,143 counties by 365 days of 2026, which is 1.1 million county-days. Everything is stored as UTC instants and converted to local clock time only at the end, once per scenario. Storing local times would mean recomputing the sun for every policy scenario, which is both wasteful and an invitation to the scenarios quietly disagreeing about astronomy.

**What the clock says.** Each regime is a function from county and instant to a UTC offset, never a label. Current law reads its offsets from the tz database, so DST transition dates are never hardcoded.

## The validation changed the code twice

I checked the solar layer against published sunrise and sunset times for five sites spanning the failure modes, on five dates spanning the year.

My first reference was a convenient public API, and it failed by up to five minutes at Anchorage. The pattern was diagnostic rather than alarming: solar noon agreed to 2 seconds and civil twilight to 3, while only sunrise and sunset drifted, systematically, growing with latitude. That is not what a broken calculation looks like. I switched to USNO, the authoritative source, and found the convenient API is itself 95 to 231 seconds off USNO on sunrise. The reference was wrong, not the code.

That still left pvlib's own sunrise and sunset helper drifting to 164 seconds at Anchorage near the equinoxes, with the error flipping sign either side. Sunrise was fine, and that asymmetry ruled out a threshold error, because a bad threshold moves sunrise and sunset together. Computing the crossings from the hour angle instead, anchored on the same SPA transit, brought the worst case to 37 seconds.

Final position: solar noon from SPA, all four crossings from the hour angle, everything within 68 seconds of USNO, of which about 30 seconds is USNO's own rounding to the minute. A validation step that can only confirm what you already did is not doing anything.

## How big the residual is

Intra-zone spread of the annual mean offset, on standard time so that DST is not itself contributing:

| Zone | Spread |
| --- | --- |
| Eastern | 87 min |
| Central | 80 min |
| Mountain | 66 min |
| Pacific | 39 min |

Three of the four are internally wider than the hour under debate. Pacific is not, because it is the narrowest zone in longitude, and I would rather say that than have someone find it.

Min-to-max invites the objection that the extremes are empty countryside, so here is the stronger form: the population-weighted interquartile range is around 30 minutes in each of the big three. The middle half of the people inside one zone are spread across half the disputed hour.

Against that, here is what the two proposals do to the share of the population living more than an hour from solar noon:

| | Share more than 60 min out |
| --- | --- |
| Permanent standard time | 0.0% |
| Current law | 34.8% |
| Permanent DST | 68.2% |

To be fair to permanent DST, it nearly abolishes the early-sunset problem, taking the population-weighted count of days with sunset before 5pm from 44 a year to essentially zero. That is a real benefit and it is why people want it. The price is 136 days a year of sunrises after 7:30am, against 22 under permanent standard time. It is a trade, not a mistake.

## Solving for the map

Now the part I had not seen anyone do. An integer program over the county adjacency graph: choose one integer offset per county to minimise population-weighted misalignment, plus a penalty for every pair of neighbouring counties that end up on different offsets. Solved with CP-SAT, and the penalty weight swept rather than picked, since picking it would be choosing the answer.

**Surprise one: keeping the map tidy is nearly free.** Going from the unconstrained answer to a map as contiguous as today's zones costs **0.02 minutes** of population-weighted alignment. The patchwork objection to per-place time zones is simply wrong, because longitude bands are naturally contiguous. Measured as connected regions, the unconstrained solution has 15 with 10 counties stranded in enclaves; the penalised one has 10 and 3, against today's 9 and 3. The right-hand map at the top of this post is that solution. It has one more contiguous region than the current system and the same number of stranded counties, and it is the near-white one.

**Surprise two, which argues against my own framing: the average American barely gains.** Today's boundaries are already close to as good as whole-hour offsets allow, at 16.95 minutes of population-weighted misalignment against a floor of 14.52. Redrawing every line in the country buys **2.4 minutes**. I had written a much more exciting sentence before I checked that number.

The entire gain is in the tail. The share of the population more than 30 minutes from solar noon falls from 17.5% to 1.4%. So the case for redrawing zones is not that everyone gains. It is that about 58 million people are badly served and almost none of them need to be. That is a narrower claim than I started with and I think it is the true one.

## The floor

Even the fitted map still spans 61 minutes inside its Eastern band. That is not a failure of the optimiser. Whole-hour offsets can only ever place you within ±30 minutes of solar noon, so a 60-minute spread is the hard floor of the entire system.

Which is the tidiest way I can put the whole thing. The hour being debated is exactly the granularity of the system doing the debating. Both sides are arguing about whether to add or subtract one unit of a quantity whose irreducible internal variation is already one unit.

## What this is not

Solar alignment is not the only thing time zones are for. Sharing an offset with the city you trade with is worth something real and none of this measures it. The optimisation is a measuring instrument for how much misalignment is structural rather than chosen, not a proposal; I am not campaigning for Indianapolis to join Central. And only the low-penalty solutions are proved optimal, so the shape of the trade-off curve is trustworthy while any one particular map is not.

The number I keep coming back to is Indianapolis. On 31 October 2026, the last full day of daylight saving, the sun there rises at 8:12am. Nothing currently on the table changes that by more than an hour in either direction, and one of the two options makes it worse.

Code and data are on GitHub, including the notes file where I pinned down the sign conventions before writing any of it, which is the only reason the numbers above agree with each other.

---

## Notes for Tyler, delete before publishing

- **~1,900 words.** Longer than the last draft because of the two new sections
  ("this part is not new" and "why misalignment is worth measuring"). Those are
  the two that protect the post, so I would cut elsewhere if you want it shorter:
  the validation section could lose its middle paragraph.
- **Title and slug changed** to lead on the optimisation rather than the
  misalignment, matching the reframe. Old slug was `the-wrong-hour`.
- **Figures, in order.** Copy into `public/images/blog/redrawing-americas-time-zones/`.
  1. Hero: `fig_c_before_after_offset_annual_mean.png`, renamed to
     `fig_c_before_after.png` to match frontmatter.
  2. `fig_a_zone_spread.png` in "How big the residual is".
  3. `signed_solar_offset_four_panel_offset_annual_mean.png` in the same section,
     after the proposals table. The only place permanent DST is shown rather than
     tabulated, and panel 3 going solid dark blue earns its place.
- **Repo is private.** Either make it public before publishing or cut the last
  line.
- **Still unresolved:** permanent DST is modelled as applying to Arizona and
  Hawaii, while the real bills exempt them. Not mentioned in the post. It is the
  most likely thing a sharp commenter picks at, so consider a footnote.
- **Deliberately not claimed:** that this is novel. Two sections now credit prior
  work explicitly. That costs a little swagger and buys a lot of defensibility.
