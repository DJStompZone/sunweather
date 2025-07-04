# spaceweather

**Generate a 6-band grid animation of solar activity from NOAA SUVI data.**  
This CLI tool fetches the latest extreme ultraviolet (EUV) imagery from NOAA SWPC’s SUVI archive and creates an animated AVI or GIF showing the solar corona across 6 wavelengths.

---

## Installation

```bash
pip install spaceweather
```

> Requires: Python 3.8+, `ffmpeg` in PATH

---

## Usage

```bash
spaceweather [options]
```

### Basic Example

```bash
spaceweather -o sun.avi
```

Creates a 6-band grid animation as an AVI (`sun.avi`) using the most recent frames available.

---

## Options

| Option               | Description                                                   |
|----------------------|---------------------------------------------------------------|
| `-o, --output`       | Output filename (`.avi` or `.gif`). Default: `suvi_grid.avi` |
| `--fps`              | Frames per second. Default: `15`                             |
| `--frames`           | Max frames to use (per band). Defaults to what all bands share |
| `--retries`          | Retry attempts per image. Default: `3`                       |
| `--strict`           | Fail hard if any image is missing. Default: soft fallback    |
| `--keep`             | Keep downloaded frames instead of using a temp folder        |
| `--debug`            | Enable verbose logging                                       |

---

## Output

- Produces a 2×3 grid of concurrent SUVI images across these bands:
  - 94 Å, 131 Å, 171 Å, 195 Å, 284 Å, 304 Å
- All frames are temporally aligned, with automatic gap-filling for any missing wavelengths.
- Default output is a high-efficiency Xvid AVI (under 1MB), compatible with most platforms.

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

---

## Example Output

![Example Video](https://i.imgur.com/3Vt35bU.mp4)

---

## License

MIT © [DJ Stomp](https://github.com/DJStompZone)

---

## Source & Issues

GitHub: [https://github.com/DJStompZone/spaceweather](https://github.com/DJStompZone/spaceweather)
