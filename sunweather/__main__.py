#!/usr/bin/env python3
"""
6-band SUVI grid → high-quality MP4 (AVI intermediate)

▪ Scrapes 094,131,171,195,284,304 angstrom images
▪ Builds a 2 × 3 grid per timestamp/frame
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
BANDS:      Final[List[str]]  = ["094", "131", "171", "195", "284", "304"]
GRID_ORDER: Final[List[str]]  = BANDS[:]
BASE_URL:   Final[str]        = "https://services.swpc.noaa.gov/images/animations/suvi/primary/"
HREF_RE:    Final[re.Pattern] = re.compile(r'href="(or_suvi-[^"]+\.png)"')
HEADERS                     = {
    "referer":    "https://www.swpc.noaa.gov/",
    "user-agent": "Mozilla/5.0 (+SUVI-grid-AVI)",
}
FFMPEG_OPTS = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]

# ─── helpers: scraping & downloading ────────────────────────────────────────
def scrape_band(band: str) -> List[str]:
    """Return sorted PNG URLs for a wavelength band."""
    url = f"{BASE_URL}{band}/"
    text = httpx.get(url, headers=HEADERS, timeout=30).text
    rels = [m for m in HREF_RE.findall(text) if m.startswith("or_suvi")]
    rels.sort()                                      # ISO timestamp = lexical
    return [urljoin(url, rel) for rel in rels]

async def _grab(client, url: str, dest: pathlib.Path, tries: int, strict: bool):
    delay = 2.0
    for attempt in range(1, tries + 1):
        try:
            r = await client.get(url, timeout=30+delay)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return
        except (httpx.HTTPStatusError, httpx.ProtocolError):
            if attempt == tries:
                if strict:
                    raise RuntimeError(f"Give-up {dest.name} after {tries} tries")
                logging.warning("Skipping %s", dest.name)
                return
            await asyncio.sleep(delay)
            delay *= 2

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

# ─── helpers: gap-fill & grid composition ───────────────────────────────────
def nearest_tile(idx: int, band: str, table):
    for j in range(idx, -1, -1):
        p = table.get(j, {}).get(band)
        if p and p.exists():
            return p
    for j in range(idx + 1, max(table) + 1):
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

# ─── encoding helpers ───────────────────────────────────────────────────────
def encode_avi(frames: List[Image.Image], outfile: pathlib.Path, fps: int, verbose: bool = False):
    """Encode PNG frames → Xvid-AVI (fast)."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        for i, img in enumerate(tqdm(frames, desc="PNG→seq", unit="img")):
            img.save(tmp / f"f{i:05d}.png")
        
        ffmpeg_command = [
                *FFMPEG_OPTS[slice(verbose and 2 or None)],
                "-framerate", str(fps),
                "-i", str(tmp / "f%05d.png"),
                "-c:v", "mpeg4",
                "-vtag", "xvid",
                "-q:v",  "2",
                str(outfile),
        ]
        logging.debug(f"{ffmpeg_command=}")
        subprocess.run(ffmpeg_command, check=True)
    finally:
        shutil.rmtree(tmp)

def encode_mp4_from_avi(avi_file: pathlib.Path, mp4_file: pathlib.Path, verbose: bool = False):
    """Re-encode AVI → MP4 (libx264 CRF-18 slow)."""
    ffmpeg_command = [
            *FFMPEG_OPTS[slice(verbose and 2 or None)],
            "-i", str(avi_file),
            "-vf", "scale=1920:-2",
            "-c:v", "libx264",
            "-crf",  "18",
            "-preset", "slow",
            str(mp4_file),
    ]
    logging.debug(f"{ffmpeg_command=}")
    subprocess.run(ffmpeg_command, check=True)

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
    p = argparse.ArgumentParser("SUVI grid → MP4 (AVI intermediate) / GIF")
    p.add_argument("-o", "--output", type=pathlib.Path,
                   default=pathlib.Path("suvi_grid.mp4"))
    p.add_argument("--fps",      type=int, default=20)
    p.add_argument("--frames",   type=int)
    p.add_argument("--retries",  type=int, default=3)
    p.add_argument("--keep",     action="store_true", help="keep PNG frames dir")
    p.add_argument("--keep-avi", action="store_true", help="keep intermediate AVI")
    p.add_argument("--strict",   action="store_true")
    p.add_argument("--debug",    action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARN,
        format="%(levelname)s: %(message)s",
    )

    # 1. scrape listings
    per_band = {b: scrape_band(b) for b in BANDS}
    min_len  = min(map(len, per_band.values()))
    use_len  = min(args.frames or min_len, min_len)
    logging.info("Using last %d frames (min=%d)", use_len, min_len)

    # 2. URLs to grab
    urls = {b: lst[-use_len:] for b, lst in per_band.items()}

    # 3. download PNGs
    workdir = pathlib.Path("frames") if args.keep else pathlib.Path(tempfile.mkdtemp())
    meta    = asyncio.run(download_all(urls, workdir, args.retries, args.strict))

    # 4. compose grids
    grids: List[Image.Image] = []
    for i in tqdm(range(use_len), desc="Composing", unit="frame"):
        for band in GRID_ORDER:
            pth = meta[i].get(band)
            if not pth or not pth.exists():
                pth = nearest_tile(i, band, meta)
                if not pth:
                    if args.strict:
                        raise RuntimeError(f"Missing {band}_{i}")
                    break
                meta[i][band] = pth
        else:
            grids.append(compose_grid(meta[i]))

    if len(grids) < 2:
        raise SystemExit("Not enough frames to encode.")

    # 5. encode path logic
    suffix = args.output.suffix.lower()
    if suffix == ".gif":
        build_gif(grids, args.output, args.fps)
    elif suffix == ".mp4":
        avi_tmp = args.output.with_suffix(".avi")
        encode_avi(grids, avi_tmp, args.fps, verbose=args.debug)
        encode_mp4_from_avi(avi_tmp, args.output, verbose=args.debug)
        if not args.keep_avi:
            avi_tmp.unlink(missing_ok=True)
    else:  # fallback: raw AVI
        encode_avi(grids, args.output, args.fps, verbose=args.debug)

    logging.debug("Saved → %s", args.output.resolve())
    print(f"Saved → {args.output.resolve()}")

if __name__ == "__main__":
    main()
