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

I spent a weekend trying to redraw America's time zones to fit the sun. Two things surprised me, and one of them argues against the point I set out to make.

The maps above are the answer. On the left is where every US county's clock sits relative to its own sun today. On the right is the same country with one fixed offset per county, chosen by an optimiser to fit the sun instead of inherited from a railway timetable. Blue means the sun runs late, red means it runs early, white means the clock and the sun agree.

## Start with Indianapolis

On 15 June this year, the sun over Indianapolis reaches its highest point at **1:45 in the afternoon**. Not noon. In January, with the clocks back, it peaks at 12:54.

Drive four hours west to Chicago and on that same January day the sun peaks at 12:00, almost exactly.

Both are Midwestern cities, less than two degrees of longitude apart. The difference is that Indianapolis is on Eastern time and Chicago is on Central.

That gap is what I set out to measure, and I'll call it the **signed solar offset**: the distance between the clock's noon and the sun's noon. Chicago in January is zero. Indianapolis is 54 minutes.

Two things follow, and they are the whole argument in miniature.

**Daylight saving makes the gap bigger, not smaller, in places like this.** Indianapolis goes from 54 minutes out in winter to an hour and three quarters out in June. Every hour of DST pushes the sun's noon later on the clock, so permanent DST would lock in the summer figure year round.

**This is not about latitude.** Anchorage has punishing winter sunrises because it sits at 61°N, and no law can fix that. The Indianapolis gap is different: it is purely a consequence of which offset the clock is set to, which is the only part anyone actually votes on.

A time zone is a step function laid over a smooth quantity. Longitude changes continuously as you drive west; clocks jump an hour at a time. The gap is the leftover, and no way of setting the clocks makes it zero.

## Why this is worth measuring

"Your clock disagrees with your sun" is not self-evidently a problem, so it is fair to ask whether it does any harm.

The best evidence comes from studies that use time zone borders as a natural experiment: two towns a few miles apart, alike in most respects, on different clocks. [Giuntella and Mazzonna (2019)](https://www.sciencedirect.com/science/article/abs/pii/S0167629618309718) find that an extra hour of evening light, which is what the western edge of a zone gives you, costs about **19 minutes of sleep a night**. The same literature reports [lower wages and national costs in the billions](https://theconversation.com/the-hazards-of-living-on-the-right-side-of-a-time-zone-border-116630) on the late-sunset side of borders.

Some louder claims in this area are contested, and it is worth being straight about that. A widely-repeated link between time zone position and cancer risk was [re-examined in 2023](https://arxiv.org/abs/2306.05921) and did not hold up for overall cancer incidence. The sleep and wage findings are on firmer ground.

So: a real effect, modest per person, spread over a lot of people.

None of that observation is mine, incidentally. Chronobiologists have made this case for years, [Roenneberg and colleagues](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2019.00944/full) most directly in 2019, and [Stefano Maggiolo](https://blog.poormansmath.net/how-much-is-time-wrong-around-the-world/) mapped clock-versus-sun offset for the whole world back in 2014. If the left-hand map looks familiar, that is why. What I could not find was anyone who had solved for the right-hand one.

## How far off is everyone

I computed the offset for all 3,143 US counties, every day of 2026, and checked the result against US Naval Observatory tables. [1] [4]

Washington County, Maine and Ontonagon County, Michigan are both on Eastern time. When the clock in both says noon, the sun over Maine passed overhead half an hour ago, and the sun over Michigan is still nearly an hour away. That is 87 minutes of difference inside a single time zone.

It is not just those two. Measured across each zone on standard time:

| Zone | Widest gap inside the zone |
| --- | --- |
| Eastern | 87 min |
| Central | 80 min |
| Mountain | 66 min |
| Pacific | 39 min |

Three of the four zones are internally more spread out than the hour Congress keeps voting on. Pacific is not, because it is the narrowest zone in longitude, and I would rather say that than have someone find it.

That is min-to-max, which invites the objection that the extremes are empty countryside. So here is the version that survives it: in each of the big three zones, the middle half of the population is spread across about 30 minutes. Half the disputed hour, just among the ordinary middle of one zone.

Set against that, here is what the two proposals actually do, counted in people living more than an hour from solar noon:

| | People more than an hour out |
| --- | --- |
| Permanent standard time | almost nobody |
| Current law | 115 million |
| Permanent DST | **226 million** |

To be fair to permanent DST, it nearly abolishes the early-sunset problem: days with sunset before 5pm drop from 44 a year to essentially none. That is a real benefit and it is why people want it. The price is 136 days a year of sunrises after 7:30am, against 22 under permanent standard time. A trade, not a mistake. [2]

## Solving for the map

Here is the part I had not seen done. Treat it as an optimisation: give every county an integer offset, chosen to put as many people as close to solar noon as possible, and add a penalty every time two neighbouring counties end up on different offsets so the result does not shatter into confetti. [3]

**Surprise one: keeping the map tidy is nearly free.**

The obvious objection to fitting clocks to the sun is that you would end up with a patchwork nobody could live with. You do not. Longitude bands are naturally contiguous, so a tidy map and an accurate map are almost the same map.

Concretely: forcing the solution to be as geographically tidy as today's zones costs the average American **about one second** of extra distance from solar noon. Not one minute. One second. The fitted map on the right at the top of this post has ten contiguous regions against today's nine, and strands exactly as many counties in enclaves as the current system does: three.

**Surprise two: the average American barely gains.** This is the one that argues against my own framing.

Today's boundaries turn out to be close to as good as whole-hour offsets allow. Redrawing every line in the country moves the typical person about **2.4 minutes** closer to the sun. I had written a much more exciting sentence before I checked that number.

The gain is real, but it is concentrated. The number of people living more than half an hour from solar noon falls from **58 million to under 5 million**. So the case for redrawing zones was never that everyone gains. It is that a small minority is badly served and almost none of them need to be. That is a narrower claim than I started with, and I think it is the true one.

## The hour is the wrong unit

Even the fitted map still spans 61 minutes inside its Eastern band. That is not the optimiser failing. Whole-hour offsets can only ever get you within half an hour of solar noon in either direction, so a 60-minute spread is the hard floor of the entire system.

Which is the tidiest way I can put the whole thing. The hour being debated is exactly the resolution of the thing doing the debating. Both sides are arguing about adding or subtracting one unit of a quantity whose irreducible internal variation is already one unit.

## What this is not

Solar alignment is not the only job a time zone does. Sharing an offset with the city you trade with is worth something real, and none of this measures it. The optimisation is a measuring instrument for how much of the misalignment is structural rather than chosen, not a proposal, and I am not campaigning for Indianapolis to join Central.

The number I keep returning to is that Indianapolis sunrise. On 31 October, the last full day of daylight saving this year, the sun there comes up at 8:12am. Nothing currently on the table moves that by more than an hour in either direction, and one of the two options makes it worse.

---

## Notes

**[1] How it was built.** Census TIGER county boundaries, with the sun computed at each county's Census *centre of population* rather than its geometric centroid. That distinction matters more than it sounds: a centroid for a large western county can sit tens of kilometres of longitude from where anyone actually lives, and since the metric is longitude-driven that would bias the result directly. Time zones come from the IANA database looked up at that point, so Arizona, the Navajo Nation and the two dozen counties that straddle a boundary all resolve from geometry rather than from my assumptions. Solar positions are NREL's Solar Position Algorithm via pvlib, over 1.1 million county-days, stored as UTC instants and converted to local clock time only at the end so that all four scenarios share one astronomical layer. Sign convention: clock noon minus true solar noon, so positive means the sun runs early. [Code and data.](https://github.com/tyler-martin-12/us-time-policy)

**[2] Arizona and Hawaii.** I model permanent DST as applying everywhere, including the two states that do not currently observe it. The real bills exempt them. I did it uniformly because it makes a cleaner comparison, with every county moving by the same hour, so the map shows geography rather than geography plus a carve-out. Exempting them leaves 8.5 million people, 2.6% of the population, where they are and pulls the national figures down slightly. It does not change the argument: both states sit around 27 minutes west of their meridians, middling by national standards rather than extreme.

**[3] The optimiser, and how much to trust it.** An integer program over the county adjacency graph, solved with CP-SAT, minimising population-weighted distance from solar noon plus a penalty per mismatched county boundary. The penalty weight is swept rather than picked, since picking it would amount to choosing the answer. Only the low-penalty solutions are proved optimal; above that the solver returns good-but-unproven answers with gaps of 2 to 37 percent. So the shape of the trade-off is trustworthy and any one specific map is not.

**[4] The validation caught a problem, and it was not where I expected.** I checked the solar calculations against published sunrise and sunset times for five sites spanning the failure modes. My first reference source failed by up to five minutes at Anchorage. But the pattern was diagnostic rather than alarming: solar noon agreed to within 2 seconds and civil twilight to 3, while only sunrise and sunset drifted, systematically, growing with latitude. That is not what a broken calculation looks like. I switched to USNO, the authoritative source, and found the convenient API was itself 95 to 231 seconds off on sunrise. The reference was wrong, not the code. That still left pvlib's own sunrise helper drifting to 164 seconds at Anchorage near the equinoxes, with the sign flipping either side of them. Sunrise was fine, and that asymmetry ruled out a threshold error, since a bad threshold moves sunrise and sunset together. Computing the crossings from the hour angle instead brought the worst case to 37 seconds. Everything now sits within 68 seconds of USNO, of which about 30 is USNO's own rounding to the minute.

---

## Notes for Tyler, delete before publishing

- **~1,530 words in the body**, down from 2,220, with roughly 700 more in the
  four end notes. The path-not-conclusion material (validation story, build
  detail, solver caveats) is all in notes now.
- **Numbers made concrete:** 0.02 population-weighted minutes is now "about one
  second", 17.5% to 1.4% is "58 million to under 5 million", and the 34.8% and
  68.2% shares are now 115 million and 226 million people. Verified against
  `metrics.csv`.
- **Sign convention** is now taught through Indianapolis (1:45pm solar noon in
  June, 12:54pm in January) against Chicago (12:00 exactly in January), rather
  than stated as a rule. Both figures come straight from the solar layer.
- **Figures, in order.** Copy into `public/images/blog/redrawing-americas-time-zones/`.
  1. Hero: `fig_c_before_after_offset_annual_mean.png`, renamed to
     `fig_c_before_after.png` to match frontmatter.
  2. `fig_a_zone_spread.png` in "How far off is everyone".
  3. `signed_solar_offset_four_panel_offset_annual_mean.png` after the proposals
     table, the only place permanent DST is shown rather than tabulated.
- If it still runs long, "The hour is the wrong unit" could fold into the
  closing section, though it is the best line in the piece.
