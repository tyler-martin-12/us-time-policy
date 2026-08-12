# LinkedIn post, ready to paste

**Images:** two, as a carousel.

1. `fig_c_before_after.png`: today vs a fitted map. Blue to white reads instantly and matches the opening line.
2. `fig_a_zone_spread.png`: every county against the 60-minute reference bar, for anyone who swipes.

Both are in the blog repo at `public/images/blog/redrawing-americas-time-zones/`.

**Link:** https://tyler-alexander-martin.com/blog/redrawing-americas-time-zones/

Put it in the first comment, not the body. LinkedIn suppresses reach on posts with outbound links.

---

## Post body

I spent a weekend trying to redraw America's time zones to fit the sun, and got two answers I did not expect.

Setup: the daylight saving debate is about applying one hour, uniformly, to the whole country. But how far your clock already sits from your sun varies enormously. On 15 June this year the sun over Indianapolis peaked at 1:45 in the afternoon. Four hours west in Chicago, it peaks at noon.

Washington County, Maine and Ontonagon County, Michigan share a time zone and sit 87 minutes apart. Eastern spans 87 minutes end to end, Central 80, Mountain 66. Three of the four zones are internally wider than the hour being voted on.

So I set it up as an optimisation over all 3,143 counties: give each one an offset that puts as many people as close to solar noon as possible, while using no more mismatched borders between neighbouring counties than today's map already does.

Surprise one: keeping the map tidy is nearly free. Today's zones disagree across 246 of the 8,933 borders between neighbouring counties. The fitted map uses 241. It is not a compromise with tidiness, it draws fewer lines than the system we have, and the alignment it gives up for that is about half a second per person. The patchwork objection to per-place time zones is just wrong, because longitude bands are naturally contiguous.

Surprise two, which argues against my own thesis: today's boundaries are already close to as good as whole-hour offsets allow. Redrawing every line in the country moves the average American 2.4 minutes closer to the sun. The entire gain sits in the tail, where the badly-served population drops from 58 million to 2 million.

None of the underlying observation is new. Chronobiologists have made this case for years, and a 2022 project already picked the best offset for each US state. What I had not found was the same question asked county by county with the cost of a messy map priced in.

Write-up and code in the comments.

---

## First comment

Full write-up, with the methodology: https://tyler-alexander-martin.com/blog/redrawing-americas-time-zones/

Code and data: https://github.com/tyler-martin-12/us-time-policy

Prior work worth reading, since the core observation is not mine: Roenneberg et al. (2019) in Frontiers in Physiology on artificial time zones, and Giuntella & Mazzonna (2019) in the Journal of Health Economics, who use US time zone borders to show an extra hour of evening light costs about 19 minutes of sleep a night. Stefano Maggiolo mapped clock-versus-sun offset worldwide back in 2014.

Method: solar positions from NREL's SPA via pvlib over 1.1 million county-days, validated against USNO to within 68 seconds. County points are Census centres of population rather than geometric centroids, which matters because the metric is longitude-driven and a centroid can sit far from where anyone lives. Zones resolved from geometry, using OpenStreetMap's boundaries with IANA names, so they reflect the clocks people keep rather than the legal lines in 49 CFR 71; the two differ in two Alabama counties and the check is in the repo. The optimiser is CP-SAT over the county adjacency graph, constrained to use no more mismatched county borders than today's map already does. The chosen map is committed with its hash and a script that re-derives every published number from it without a solver.

---

## Notes on the draft

- **~300 words**, which is long for LinkedIn but the two surprises need room. If you want it shorter, cut the Maine/Michigan paragraph: the Indianapolis line already establishes the problem.
- **First two lines carry it.** LinkedIn truncates at roughly 210 characters, so everything before "Setup:" is what most people see.
- **Leads with the optimisation, not the misalignment.** The misalignment maps have been done before, including at world scale. The solved map has not.
- **Credits prior work in the body**, not only the comment. One line removes the entire class of "this is well known" replies and makes the original part legible.
- **Keeps the finding that undercuts the thesis.** Surprise two is the most credible thing in the post precisely because it is inconvenient.
- **No call to action.** The last line before the sign-off is the argument, which prompts better than asking for thoughts.
