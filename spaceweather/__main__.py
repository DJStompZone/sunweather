#!/usr/bin/env python3
"""
6-band SUVI grid → tiny AVI

• Scrapes 094,131,171,195,284,304 angstrom wavelengths
• Builds a 2×3 grid per timestamp
• Encodes to Xvid-AVI by default
• Pass a .gif filename if you really want an animated GIF instead
"""

from __future__ import annotations
import argparse, asyncio, logging, pathlib, re, tempfile, subprocess, os, shutil
from typing import Final, Dict, List
from urllib.parse import urljoin

import httpx
from PIL import Image
import numpy as np
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm

# ─── constants ──────────────────────────────────────────────────────────────
BANDS: Final[List[str]] = ["094", "131", "171", "195", "284", "304"]
GRID_ORDER: Final[List[str]] = BANDS[:]
BASE_URL: Final[str] = "https://services.swpc.noaa.gov/images/animations/suvi/primary/"
HREF_RE: Final[re.Pattern[str]] = re.compile(r'href="(or_suvi-[^"]+\.png)"')
HEADERS = {
    "referer": "https://www.swpc.noaa.gov/",
    "user-agent": "Mozilla/5.0 (+SUVI-grid-AVI)",
}
# ---------------------------------------------------------------------------


def scrape_band(band: str) -> List[str]:
    """Fetch and return sorted PNG URLs for a wavelength band."""
    url = f"{BASE_URL}{band}/"
    r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    rels = [m for m in HREF_RE.findall(r.text) if m.startswith("or_suvi")]
    rels.sort()  # ISO timestamp → lexicographic
    return [urljoin(url, rel) for rel in rels]


# ─── async downloader with retry/back-off ───────────────────────────────────
async def _grab(client, url: str, dest: pathlib.Path, tries: int, strict: bool):
    delay = 1.0
    for attempt in range(1, tries + 1):
        try:
            r = await client.get(url, timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)
            logging.debug("✓ %s (try %d)", dest.name, attempt)
            return
        except (httpx.HTTPStatusError, httpx.ProtocolError):
            if attempt == tries:
                msg = f"give-up {dest.name} after {tries} tries"
                if strict:
                    raise RuntimeError(msg)
                logging.info(msg)
                return
            await asyncio.sleep(delay)
            delay *= 2
        except Exception:
            if strict:
                raise
            logging.exception("skip %s (unexpected)", dest.name)
            return


async def download_all(
    url_matrix: Dict[str, List[str]],
    outdir: pathlib.Path,
    tries: int,
    strict: bool,
) -> Dict[int, Dict[str, pathlib.Path]]:
    meta: Dict[int, Dict[str, pathlib.Path]] = {}
    outdir.mkdir(parents=True, exist_ok=True)
    tasks = []
    async with httpx.AsyncClient(http2=True, headers=HEADERS) as client:
        for band, urls in url_matrix.items():
            for idx, url in enumerate(urls):
                dest = outdir / f"{band}_{idx}.png"
                meta.setdefault(idx, {})[band] = dest
                tasks.append(_grab(client, url, dest, tries, strict))
        await tqdm_asyncio.gather(*tasks, desc="Downloading", unit="img")
    return meta


# ─── helpers: gap-fill & composition ────────────────────────────────────────
def nearest_tile(idx: int, band: str, table):
    for j in range(idx, -1, -1):          # backward
        p = table.get(j, {}).get(band)
        if p and p.exists():
            return p
    for j in range(idx + 1, max(table) + 1):  # forward
        p = table.get(j, {}).get(band)
        if p and p.exists():
            return p
    return None


def compose_grid(row: Dict[str, pathlib.Path]) -> Image.Image:
    imgs = [Image.open(row[b]).convert("RGB") for b in GRID_ORDER]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * 3, h * 2))
    for i, img in enumerate(imgs):
        r, c = divmod(i, 3)
        canvas.paste(img, (c * w, r * h))
    return canvas


# ─── encoding ───────────────────────────────────────────────────────────────
def encode_avi(
    frames: List[Image.Image],
    outfile: pathlib.Path,
    fps: int,
    max_w: int = 1280,
):
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        for i, img in enumerate(tqdm(frames, desc="Writing PNG seq", unit="img")):
            if img.width > max_w:
                h_new = int(img.height * max_w / img.width)
                img = img.resize((max_w, h_new), Image.LANCZOS)
            img.save(tmp / f"f{i:05d}.png")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(tmp / "f%05d.png"),
            "-c:v", "mpeg4",
            "-vtag", "xvid",
            "-q:v", "5",
            str(outfile)
        ]
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp)


def build_gif(frames, outfile: pathlib.Path, fps: int):
    frames[0].save(
        outfile,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
        disposal=2,
    )


# ─── main ───────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser("SUVI grid → tiny AVI / optional GIF")
    p.add_argument("-o", "--output", type=pathlib.Path, default="suvi_grid.avi")
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--frames", type=int, default=None)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARN,
        format="%(levelname)s: %(message)s",
    )

    # 1. scrape listings
    per_band = {b: scrape_band(b) for b in BANDS}
    min_len = min(len(lst) for lst in per_band.values())
    use_len = min(args.frames or min_len, min_len)
    logging.info("Using last %d frames (min available %d)", use_len, min_len)

    # 2. build URL matrix
    urls = {b: lst[-use_len:] for b, lst in per_band.items()}

    # 3. download
    workdir = pathlib.Path("frames") if args.keep else pathlib.Path(tempfile.mkdtemp())
    meta = asyncio.run(download_all(urls, workdir, args.retries, args.strict))

    # 4. gap-fill & compose
    grids: List[Image.Image] = []
    for i in tqdm(range(use_len), desc="Composing", unit="frame"):
        for band in GRID_ORDER:
            if not (p := meta[i].get(band)) or not p.exists():
                repl = nearest_tile(i, band, meta)
                if not repl:
                    if args.strict:
                        raise RuntimeError(f"Missing {band}_{i}")
                    break
                meta[i][band] = repl
        else:
            grids.append(compose_grid(meta[i]))

    if len(grids) < 2:
        raise SystemExit("Not enough frames to encode.")

    # 5. encode
    if args.output.suffix.lower() == ".gif":
        build_gif(grids, args.output, args.fps)
    else:
        encode_avi(grids, args.output, args.fps)
    logging.info("Saved → %s", args.output.resolve())


if __name__ == "__main__":
    main()
