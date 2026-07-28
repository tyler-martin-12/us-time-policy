"""Stage 7: build a single review page.

Renders the LinkedIn post and the blog draft into one HTML file styled like the
live blog, written into data/out/ so the figures resolve as relative URLs off
the same static server. Images are referenced rather than base64-inlined: the
figures run to several MB and this page is served, not emailed.

Usage:
    uv run --with markdown src/70_preview.py
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
OUT = ROOT / "data" / "out"

HERO = "fig_c_before_after_offset_annual_mean.png"
FIG_SPREAD = "fig_a_zone_spread.png"
FIG_PANELS = "signed_solar_offset_four_panel_offset_annual_mean.png"
FIG_TWO = "fig_b_two_counties.png"

CSS = """
:root{--cream:#faf6f0;--warm:#fff9f2;--ink:#1a1208;--bark:#3d2b1f;--rust:#b85c38;
--dust:#c9b49a;--mist:#e8ddd0;--sage:#7a8c6e}
*{box-sizing:border-box}
body{margin:0;background:var(--cream);color:var(--ink);
font-family:Georgia,'Times New Roman',serif;font-size:18px;line-height:1.75}
.wrap{max-width:760px;margin:0 auto;padding:2.5rem 1.25rem 6rem}
.banner{background:var(--ink);color:var(--cream);padding:.6rem 1.25rem;
font-family:ui-monospace,Menlo,monospace;font-size:.72rem;letter-spacing:.09em;
text-transform:uppercase;text-align:center}
h1{font-size:2.5rem;line-height:1.15;margin:.4rem 0 .6rem;letter-spacing:-.01em}
h2{font-size:1.42rem;margin:2.8rem 0 .9rem;line-height:1.25}
h3{font-size:1.1rem;margin:2rem 0 .6rem}
p{margin:0 0 1.15rem}
a{color:var(--rust)}
blockquote{margin:1.4rem 0;padding:.6rem 0 .6rem 1.2rem;
border-left:3px solid var(--dust);font-style:italic;color:var(--bark)}
table{border-collapse:collapse;width:100%;margin:1.5rem 0;font-size:.94rem}
th,td{text-align:left;padding:.55rem .7rem;border-bottom:1px solid var(--mist)}
th{font-family:ui-monospace,Menlo,monospace;font-size:.72rem;letter-spacing:.06em;
text-transform:uppercase;color:var(--bark)}
figure{margin:2rem -3.5rem}
figure img{width:100%;height:auto;display:block;border-radius:10px;
border:1px solid var(--mist);box-shadow:0 12px 32px rgba(61,43,31,.10)}
figcaption{margin-top:.5rem;text-align:center;color:var(--bark);font-size:.8rem;
font-style:italic}
@media(max-width:900px){figure{margin:1.6rem 0}}
.card{background:var(--warm);border:1px solid var(--mist);border-radius:14px;
padding:1.6rem 1.8rem;margin:0 0 2rem}
.card p{margin:0 0 .95rem}
.card p:last-child{margin-bottom:0}
.kicker{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;
letter-spacing:.11em;text-transform:uppercase;color:var(--sage);margin-bottom:.5rem}
.meta{font-family:ui-monospace,Menlo,monospace;font-size:.7rem;letter-spacing:.06em;
text-transform:uppercase;color:var(--dust)}
hr{border:0;border-top:1px solid var(--mist);margin:3.2rem 0}
.rule{margin:3rem 0;text-align:center;color:var(--dust);letter-spacing:.6em}
strong{font-weight:700}
"""


def md(text: str) -> str:
    return markdown.markdown(text, extensions=["tables", "sane_lists"])


def figure(src: str, caption: str) -> str:
    return f'<figure><img src="{src}" alt=""><figcaption>{caption}</figcaption></figure>'


def linkedin_body() -> str:
    raw = (NOTES / "LINKEDIN_POST.md").read_text()
    body = raw.split("\n---\n", 1)[1].split("## First comment", 1)[0]
    return md(body.strip())


def blog_body() -> tuple[str, str, str]:
    raw = (NOTES / "BLOG_POST_DRAFT.md").read_text()
    _, fm, rest = raw.split("---", 2)
    title = re.search(r'^title:\s*"(.+)"', fm, re.M).group(1)
    desc = re.search(r'^description:\s*"(.+)"', fm, re.M).group(1)
    body = rest.split("## Notes for Tyler", 1)[0].rstrip().rstrip("-").rstrip()
    return title, desc, body


def main() -> int:
    title, desc, body = blog_body()

    # Figures placed at the documented positions rather than by hand, so the page
    # cannot drift from notes/BLOG_POST_DRAFT.md if the sections move.
    body = body.replace(
        "## How far off is everyone",
        "## How far off is everyone\n\n@@FIG_SPREAD@@",
        1,
    )
    body = body.replace(
        "## Solving for the map",
        "@@FIG_PANELS@@\n\n## Solving for the map",
        1,
    )
    html_body = md(body)
    html_body = html_body.replace(
        "<p>@@FIG_SPREAD@@</p>",
        figure(FIG_SPREAD, "Every US county by how far its clock sits from the sun, "
                           "against the 60 minutes under debate."),
    ).replace(
        "<p>@@FIG_PANELS@@</p>",
        figure(FIG_PANELS, "All four regimes on one fixed scale. Permanent DST, "
                           "panel 3, goes solid blue."),
    )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preview — {title}</title><style>{CSS}</style></head><body>
<div class="banner">Draft preview &middot; not published &middot; tyler-alexander-martin.com</div>
<div class="wrap">

<div class="kicker">1 &middot; LinkedIn post</div>
<div class="card">{linkedin_body()}</div>
<p class="meta">Carousel image 1</p>
{figure(HERO, "Today versus a map fitted to the sun.")}
<p class="meta">Carousel image 2</p>
{figure(FIG_SPREAD, "Zone spread against the 60-minute reference.")}

<div class="rule">&#10022;</div>

<div class="kicker">2 &middot; Blog post</div>
<h1>{title}</h1>
<p class="meta">{desc}</p>
{figure(HERO, "Left: where every US county's clock sits relative to its sun today. "
              "Right: one fixed offset per county, fitted to the sun.")}
{html_body}

<hr>
<p class="meta">Also available: {FIG_TWO} (optional opener) &middot;
January variants of both maps &middot; metrics.csv, zone_spread.csv,
optimize_sweep.csv in the same directory.</p>
</div></body></html>"""

    dest = OUT / "preview.html"
    dest.write_text(page)
    print(f"wrote {dest.relative_to(ROOT)}  ({len(page) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
