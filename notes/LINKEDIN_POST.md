# LinkedIn post

**Graphic:** `fig_a_zone_spread.png` (1800x1290). Self-contained: the claim is
readable without the caption.

**Length:** ~190 words. LinkedIn truncates around 210 characters, so the first
two lines have to carry it alone.

---

Washington County, Maine and Ontonagon County, Michigan are in the same time zone.

At noon, the sun over Maine passed overhead half an hour ago. Over Michigan it is still most of an hour away.

That gap is 87 minutes. Congress has spent years arguing about 60.

I ran the numbers for all 3,143 US counties: where the sun actually is when the clock says noon, under current law, under permanent standard time, and under permanent DST.

Three of the four continental time zones are internally more spread out than the hour the whole debate is about. Eastern spans 87 minutes, Central 80, Mountain 66. Only Pacific, the narrowest, comes in under at 39.

So the framing is off. "DST or standard time" is a single hour applied uniformly to a country whose internal misalignment is already bigger than that hour. Whichever side wins, Indianapolis still gets an 8:12am sunrise at the end of October, and Maine still gets 4pm sunsets.

The interesting variable was never which hour. It is where the lines are drawn.

Method, data and code in the comments.

---

## First comment (post immediately after)

Full write-up with the methodology: [BLOG LINK]

Solar positions from NREL's SPA via pvlib, validated against USNO to within a
minute across five sites and five dates. County centres are Census centres of
population rather than geometric centroids, which matters a lot for large
western counties. Time zones resolved from the IANA database, so Arizona and the
Navajo Nation fall out correctly instead of needing hand-coded exceptions.

---

## Notes on the draft

- **Opens on the two counties, not the thesis.** The abstract claim
  ("misalignment varies more than the debated hour") is not interesting until
  you have seen one concrete instance of it.
- **The Pacific exception is in the post, not buried.** Anyone who checks will
  find it, and finding it themselves after we hid it would cost more than
  stating it.
- **No call to action, no "thoughts?"** The last line is the argument, which is
  a better prompt than asking for engagement.
- **Indianapolis 8:12am is the detail people will quote back.** It is real: 31
  October 2026, the last full day of DST.
- Consider posting the graphic alone, no link in the body. LinkedIn suppresses
  posts with outbound links, hence the link in the first comment.
