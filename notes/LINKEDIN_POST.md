# LinkedIn post

**Images:** two, as a carousel.
1. `fig_c_before_after_offset_annual_mean.png`, today vs fitted. Blue to white
   reads instantly and matches the new opening.
2. `fig_a_zone_spread.png`, the zone spread against the 60-minute bar, for
   anyone who swipes.

**Length:** ~210 words. First two lines carry it, since LinkedIn truncates around
210 characters.

---

I spent a weekend trying to redraw America's time zones to fit the sun, and got two answers I did not expect.

Setup: the DST debate is about applying one hour, uniformly, to the whole country. But how far your clock already sits from your sun varies enormously. Washington County, Maine and Ontonagon County, Michigan share a time zone and sit 87 minutes apart. Eastern spans 87 minutes end to end, Central 80, Mountain 66. Three of four zones are internally wider than the hour being voted on.

So I set it up as an optimisation over all 3,143 counties: pick one offset each to minimise how far people live from solar noon, with a penalty for every pair of neighbouring counties that disagree.

Surprise one: keeping the map tidy is nearly free. Fitting the sun properly while staying as contiguous as today's zones costs 0.02 minutes of alignment. The patchwork objection to per-place time zones is wrong, because longitude bands are naturally contiguous.

Surprise two, which cuts against my own thesis: today's boundaries are already close to as good as whole-hour offsets allow. Redrawing every line in the country buys the average American 2.4 minutes. The entire gain is in the tail, where the badly-served share falls from 17.5% to 1.4%.

None of the underlying observation is new. Chronobiologists have made this argument for years. What I had not seen was anyone actually solve for the map.

Method and code below.

---

## First comment (post immediately after)

Full write-up: [BLOG LINK]

Prior work worth reading, because the core observation is not mine: Roenneberg
et al. (2019) in Frontiers in Physiology on artificial time zones, and Giuntella
& Mazzonna (2019) in the Journal of Health Economics, who use US time zone
borders to show an extra hour of evening light costs about 19 minutes of sleep a
night. Stefano Maggiolo mapped solar-versus-clock offset worldwide back in 2014.

Method: solar positions from NREL's SPA via pvlib over 1.1 million county-days,
validated against USNO to within 68 seconds. County points are Census centres of
population, not geometric centroids, which matters because the metric is
longitude-driven and a centroid can sit far from where anyone lives. Zones
resolved from the IANA database so Arizona falls out correctly. Optimisation is
CP-SAT over the county adjacency graph with the contiguity penalty swept rather
than picked.

---

## Notes on the draft

- **Leads with the optimisation, not the misalignment.** The misalignment maps
  are the part that has been done before, including at world scale. The solved
  map is the part that has not.
- **Credits the prior work in the body, not just the comment.** "None of the
  underlying observation is new" costs one line and removes the whole class of
  "actually, this is well known" replies. It also makes the novel bit legible.
- **Includes the finding that undercuts the thesis.** Surprise two is the most
  credible thing in the post precisely because it is inconvenient.
- **No call to action.** The last line before the method is the argument.
- Cut the Indianapolis 8:12am detail from this version. It is good but the post
  can only carry one concrete hook and the two counties do it better.
