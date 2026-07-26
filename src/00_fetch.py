"""Stage 0: fetch raw source data into data/raw/, once.

Every downstream stage assumes these files are present and byte-identical to
what was recorded in the manifest. Nothing here parses anything; parsing is
stage 1's job. This script's only responsibilities are: get the bytes, prove
they are intact, and never fetch them twice.

Caching contract (NOTES.md §11):
  - data/raw/manifest.json records url, sha256, bytes and fetch time per file.
  - A file is considered good if it exists and its sha256 matches the manifest.
    Good files are skipped, so a normal run makes zero network requests.
  - The checksum guards against local corruption and truncated downloads. It is
    deliberately NOT a pin on upstream content: Census reissues these files, and
    silently failing forever because a vintage was refreshed would be worse than
    noticing. Use --check-remote to detect upstream drift without downloading,
    and --force to deliberately re-fetch.

Usage:
    uv run src/00_fetch.py                 # fetch anything missing or corrupt
    uv run src/00_fetch.py --check-remote  # report upstream drift, download nothing
    uv run src/00_fetch.py --force         # re-download everything
    uv run src/00_fetch.py --only tiger_counties
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
MANIFEST = RAW / "manifest.json"

CHUNK = 1 << 20  # 1 MiB
TIMEOUT = 60


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    filename: str
    why: str


SOURCES: tuple[Source, ...] = (
    Source(
        key="tiger_counties",
        url="https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip",
        filename="tl_2020_us_county.zip",
        why="County boundaries (2020 vintage). Read directly from the zip by geopandas; "
        "also the source of the adjacency graph for stage 2.",
    ),
    Source(
        key="centers_of_population",
        url="https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt",
        filename="CenPop2020_Mean_CO.txt",
        why="2020 county centers of population. The point each county's solar layer is "
        "computed at. NOT geometric centroids, which misplace large western counties "
        "and would bias a longitude-driven metric.",
    ),
    Source(
        key="county_population",
        url="https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/"
        "counties/totals/co-est2025-alldata.csv",
        filename="co-est2025-alldata.csv",
        why="Vintage 2025 county population estimates, for population weighting. "
        "Filter to SUMLEV==050 and use POPESTIMATE2025.",
    ),
)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    try:
        return json.loads(MANIFEST.read_text())
    except json.JSONDecodeError:
        print("  ! manifest.json is unreadable; treating every file as unverified")
        return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def human(n: int | None) -> str:
    if n is None:
        return "?"
    mb = n / 1_048_576
    return f"{mb:,.1f} MiB" if mb >= 1 else f"{n:,} B"


def download(src: Source, dest: Path) -> None:
    """Stream to a .part file, then rename. An interrupted download must never
    leave a short file in place that a later run would hash and trust."""
    part = dest.with_suffix(dest.suffix + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(src.url, stream=True, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        expected = resp.headers.get("Content-Length")
        expected_n = int(expected) if expected and expected.isdigit() else None
        written = 0
        with part.open("wb") as fh:
            for block in resp.iter_content(CHUNK):
                fh.write(block)
                written += len(block)
    if expected_n is not None and written != expected_n:
        part.unlink(missing_ok=True)
        raise OSError(
            f"{src.key}: truncated download, got {written} bytes, expected {expected_n}"
        )
    part.replace(dest)
    print(f"  downloaded {human(written)}")


def remote_head(src: Source) -> tuple[int | None, str | None]:
    resp = requests.head(src.url, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    cl = resp.headers.get("Content-Length")
    return (int(cl) if cl and cl.isdigit() else None, resp.headers.get("Last-Modified"))


def check_remote(sources: tuple[Source, ...], manifest: dict) -> int:
    """Cheap upstream drift detection: compare recorded size/Last-Modified against
    a HEAD request. Reports only; never writes."""
    drifted = 0
    for src in sources:
        rec = manifest.get(src.key)
        print(f"\n{src.key}")
        if rec is None:
            print("  not fetched yet")
            continue
        try:
            size, last_mod = remote_head(src)
        except requests.RequestException as exc:
            print(f"  ! HEAD failed: {exc}")
            continue
        same_size = size is None or size == rec.get("bytes")
        same_mod = last_mod is None or last_mod == rec.get("http_last_modified")
        if same_size and same_mod:
            print(f"  unchanged ({human(size)})")
        else:
            drifted += 1
            print("  DRIFT")
            print(f"    local  {human(rec.get('bytes'))}  {rec.get('http_last_modified')}")
            print(f"    remote {human(size)}  {last_mod}")
    if drifted:
        print(
            f"\n{drifted} source(s) changed upstream. Re-fetch deliberately with "
            "--force, and expect downstream numbers to move."
        )
    else:
        print("\nAll sources match the manifest.")
    return drifted


def fetch(sources: tuple[Source, ...], manifest: dict, force: bool) -> dict:
    for src in sources:
        dest = RAW / src.filename
        rec = manifest.get(src.key)
        print(f"\n{src.key}  ->  data/raw/{src.filename}")

        if not force and dest.exists() and rec and rec.get("sha256"):
            actual = sha256_of(dest)
            if actual == rec["sha256"]:
                print(f"  cached, checksum ok ({human(dest.stat().st_size)})")
                continue
            print("  ! checksum mismatch against manifest, re-downloading")
        elif not force and dest.exists() and not rec:
            # Present but unrecorded: adopt it rather than re-download, but say so,
            # because its provenance is unproven.
            digest = sha256_of(dest)
            print(f"  present but unrecorded; adopting (sha256 {digest[:12]}…)")
            manifest[src.key] = {
                "url": src.url,
                "filename": src.filename,
                "sha256": digest,
                "bytes": dest.stat().st_size,
                "fetched_at": None,
                "http_last_modified": None,
                "note": "adopted from disk, not downloaded by this script",
            }
            continue

        try:
            last_mod = remote_head(src)[1]
        except requests.RequestException:
            last_mod = None
        download(src, dest)
        manifest[src.key] = {
            "url": src.url,
            "filename": src.filename,
            "sha256": sha256_of(dest),
            "bytes": dest.stat().st_size,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "http_last_modified": last_mod,
            "why": src.why,
        }
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    ap.add_argument(
        "--check-remote",
        action="store_true",
        help="report upstream size/Last-Modified drift, download nothing",
    )
    ap.add_argument("--only", metavar="KEY", help="restrict to one source key")
    args = ap.parse_args()

    sources = SOURCES
    if args.only:
        sources = tuple(s for s in SOURCES if s.key == args.only)
        if not sources:
            print(f"no such source: {args.only}", file=sys.stderr)
            print("known:", ", ".join(s.key for s in SOURCES), file=sys.stderr)
            return 2

    RAW.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    if args.check_remote:
        return 0 if check_remote(sources, manifest) == 0 else 1

    manifest = fetch(sources, manifest, force=args.force)
    save_manifest(manifest)

    total = sum(manifest[k]["bytes"] for k in manifest)
    print(f"\n{len(manifest)} source(s) cached, {human(total)} total")
    print(f"manifest: {MANIFEST.relative_to(MANIFEST.parent.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
