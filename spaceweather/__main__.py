#!/usr/bin/env python3
"""
DJ Stomp SUVI-GIF Forge — LIVE edition (v1.1)
Scrape NOAA’s SUVI 284 Å directory, download all current frames, and bake a GIF.

Author : DJ Stomp <85457381+DJStompZone@users.noreply.github.com>
License: MIT
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib
import re
import tempfile
from typing import Final, Sequence
from urllib.parse import urljoin

import httpx
from PIL import Image
from tqdm.asyncio import tqdm_asyncio

# ─────────────── CONSTANTS ───────────────
DIR_URL: Final[str] = (
    "https://services.swpc.noaa.gov/images/animations/suvi/primary/284/"
)
CONCURRENCY_DEFAULT: Final[int] = 8
FPS: Final[int] = 4  # frames-per-second in the final GIF
HREF_RE: Final[re.Pattern[str]] = re.compile(r'href="([^"]+\.png)"', re.I)
HEADERS: Final[dict[str, str]] = {
    "referer": "https://www.swpc.noaa.gov/",
    "user-agent": "Mozilla/5.0 (+DJ Stomp SUVI-gif-forge)",
}
# ──────────────────────────────────────────


def extract_png_urls(html: str, dir_url: str) -> list[str]:
    """Grab .png hrefs from a directory listing, return absolute URLs (sorted)."""
    rel_links = HREF_RE.findall(html)
    # Drop the duplicate convenience symlink
    rel_links = [l for l in rel_links if not l.endswith("latest.png")]
    full = sorted(urljoin(dir_url, l) for l in rel_links)
    logging.debug("Parsed %d PNG links from listing", len(full))
    return full


async def _fetch(client: httpx.AsyncClient, url: str, dest: pathlib.Path) -> None:
    """Download one frame to *dest*."""
    logging.debug("GET %s", url)
    r = await client.get(url, timeout=30)
    r.raise_for_status()
    dest.write_bytes(r.content)
    logging.debug("✅ wrote %s (%d bytes)", dest.name, len(r.content))


async def download_all(
    urls: Sequence[str], out_dir: pathlib.Path, concurrency: int
) -> list[pathlib.Path]:
    """Concurrent fetch of *urls* → *out_dir* (returns sorted file paths)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    limits = httpx.Limits(max_connections=concurrency)
    async with httpx.AsyncClient(
        limits=limits, http2=True, headers=HEADERS, follow_redirects=True
    ) as client:
        jobs = [_fetch(client, u, out_dir / pathlib.Path(u).name) for u in urls]
        await tqdm_asyncio.gather(*jobs, desc="Downloading", unit="frame")
    files = sorted(out_dir.glob("*.png"))
    logging.debug("Downloaded %d frames total", len(files))
    return files


def assemble_gif(frames: Sequence[pathlib.Path], gif_path: pathlib.Path) -> None:
    """Stitch *frames* → animated GIF (infinite loop)."""
    logging.info("Assembling GIF (%d frames) …", len(frames))
    imgs = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frames]
    imgs[0].save(
        gif_path,
        save_all=True,
        append_images=imgs[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=False,
    )
    logging.debug("GIF writing complete")


def cli() -> None:
    p = argparse.ArgumentParser(
        description="Live-scrape SUVI 284 Å frames and build an animated GIF."
    )
    p.add_argument(
        "--dir-url",
        default=DIR_URL,
        help="Directory listing to scrape (default: SUVI 284 primary)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        default="suvi_284_live.gif",
        help="Output GIF filename",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=CONCURRENCY_DEFAULT,
        help="Max simultaneous downloads",
    )
    p.add_argument(
        "--keep",
        action="store_true",
        help="Retain downloaded PNGs (otherwise a temp dir is used)",
    )
    p.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable verbose DEBUG logging",
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # ── 1. Scrape listing ──
    logging.info("Scraping %s …", args.dir_url)
    r = httpx.get(args.dir_url, timeout=30, headers=HEADERS, follow_redirects=True)
    logging.debug("HTTP %s, %d bytes", r.status_code, len(r.content))
    r.raise_for_status()

    urls = extract_png_urls(r.text, args.dir_url)
    if not urls:
        raise SystemExit("No PNG links found — did NOAA change the page format?")
    logging.info("Found %d frames", len(urls))

    # ── 2. Download ──
    workspace = pathlib.Path("frames") if args.keep else pathlib.Path(tempfile.mkdtemp())
    logging.debug("Using workspace %s", workspace)
    frames = asyncio.run(download_all(urls, workspace, args.concurrency))
    logging.info("Frames stored in %s", workspace.resolve())

    # ── 3. Build GIF ──
    assemble_gif(frames, args.output)
    logging.info("GIF created → %s", args.output.resolve())


if __name__ == "__main__":
    cli()
