# sunweather

**Generate a 6-band grid animation of solar activity from NOAA SUVI data.**  
This CLI tool fetches the latest extreme ultraviolet (EUV) imagery from NOAA SWPC’s SUVI archive and creates an animated MP4, AVI, or GIF showing the solar corona across 6 wavelengths.

---

## Installation

```bash
pip install sunweather
```

> Requires: Python 3.8+, `ffmpeg` in PATH

---

## Usage

```bash
sunweather [options]
```

### Basic Example

```bash
sunweather -o sun.mp4
```

Creates a 6-band grid animation as an MP4 (`sun.mp4`) using the most recent frames available.  
Uses a fast AVI intermediate and re-encodes with `libx264` for high visual quality.

---

## Options

| Option               | Description                                                   |
|----------------------|---------------------------------------------------------------|
| `-o, --output`       | Output filename (`.mp4`, `.avi`, or `.gif`). Default: `suvi_grid.mp4` |
| `--fps`              | Frames per second. Default: `20`                              |
| `--frames`           | Max frames to use (per band). Defaults to what all bands share |
| `--retries`          | Retry attempts per image. Default: `3`                        |
| `--strict`           | Fail hard if any image is missing.     |
| `--keep`             | Keep downloaded frames instead of using a temp folder         |
| `--keep-avi`         | Preserve the temporary `.avi` file used before MP4 encoding.   |
| `--debug`            | Enable verbose logging.                     |

---

## Output

- Produces a 2×3 grid of concurrent SUVI images across these bands:
  - 94 Å, 131 Å, 171 Å, 195 Å, 284 Å, 304 Å
- All frames are temporally aligned, with automatic gap-filling for any missing wavelengths.
- MP4 output uses high-quality H.264 encoding via FFmpeg with `-crf 18 -preset slow`.
- AVI output (via `-o output.avi`) uses fast Xvid encoding with wide compatibility.
- GIF output is supported but not recommended due to large file size (>100MB).

---

## Requirements

- **Python**: 3.8 or higher
- **Dependencies**: Automatically handled by `pip`:
  - `httpx[http2]`, `tqdm`, `Pillow`, `numpy`
- **ffmpeg**: Must be installed and available in your system `PATH`.

To install `ffmpeg`:

**Ubuntu/Debian:**

```bash
sudo apt install ffmpeg
```

**Termux (Android):**

```bash
pkg install ffmpeg
```

**Windows:**
```ps1
winget install ffmpeg
# OR
choco install ffmpeg
```
---

## Example Output

![Example Video](https://i.imgur.com/3Vt35bU.mp4)

---

## License

MIT © 2025 [DJ Stomp](https://github.com/DJStompZone)

---

## Source & Issues

GitHub: [https://github.com/DJStompZone/sunweather](https://github.com/DJStompZone/sunweather)
