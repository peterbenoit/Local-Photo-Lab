# Photo Auto-Enhance

A local Python tool that auto-corrects photo levels/white balance/contrast using
classical image processing (no ML model, no cloud calls), with optional nature
and creative filter presets on top.

Two ways to use it:

- **Web UI** — upload a photo once, compare visual look previews, and adjust
  Auto's actual white-balance, levels, and local-contrast recipe alongside
  wildlife lighting/detail controls, warmth, fade, vignette, and grain without
  re-uploading. It runs entirely on `localhost`; nothing leaves the machine.
- **CLI** — enhance one photo or batch-process a folder.

See [`photo-auto-enhance-spec.md`](photo-auto-enhance-spec.md) for the original
design spec, [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md) for the outstanding review
backlog, and [`CHANGELOG.md`](CHANGELOG.md) for build progress.

## Requirements

- macOS (Intel or Apple Silicon), the currently tested platform
- Python 3.11 or newer; local development is pinned to 3.12 via `.python-version`
- [`uv`](https://docs.astral.sh/uv/) — if you don't have it: `brew install uv`

## Setup

```bash
uv sync --extra web
```

This creates `.venv/`, installs the pinned Python 3.12, and installs all dependencies
(including Flask for the web UI).

## Running the web UI

**Easiest: VS Code Run button.** Open this folder in VS Code, open the Run and Debug
panel (⇧⌘D), select **"Web UI"**, and press the green play button. It starts the
server and opens `http://127.0.0.1:5050` in your browser automatically.

**Or from the terminal:**

```bash
uv run photo-enhance-web
```

Then open http://127.0.0.1:5050. Upload a photo once. Choosing a visual look or
moving an adjustment slider reprocesses the already-uploaded image. The server
keeps the last 20 uploaded sessions in memory; restarting it clears them.

Auto analyzes a bounded copy of the source, measures tonal range, color cast,
contrast, saturation, and noise, and sets the editor controls to the exact
values used for rendering. White balance, levels, local contrast, shadows,
highlight recovery, vibrance, detail, and denoise therefore begin at different
values for different photos. Moving any of them re-renders from the source
pixels; setting all corrections to zero produces an uncorrected result.

Optional vignette and film-grain controls are applied after the chosen filter.
Warmth and matte-fade controls can also fine-tune the color temperature and
black point. All finishing settings update the live preview and downloaded JPEG
and are restored with the rest of the short-lived session state.

The Nature & Wildlife group includes Bird Natural, Feather Detail, Backlit
Bird, Woodland, and Overcast looks. Choosing one loads restrained defaults for
shadow lift, highlight recovery, vibrance, feather detail, noise reduction, and
finishing controls. Every value remains independently adjustable, and Auto plus
the existing creative looks remain available unchanged.

The result can also be downloaded as a labeled before/after comparison JPEG.
Each panel is bounded to 2,400 pixels on its longest side so comparison exports
remain practical even for very large source photos.

Web previews are converted to 8-bit JPEG and do not contain source metadata.
Transparent images and images above 8 bits per channel are rejected with an
explanation instead of being silently flattened or down-converted. After
processing, the page shows dimensions, source/output format, active filter, and
processing time, and provides a download link for the currently displayed JPEG.
Photos can be selected with the native file input or dropped onto the upload
area. Results default to a draggable before/after reveal; use its native range
control with touch, pointer, or arrow keys, or switch to the side-by-side view.

Preview images and downloads use short-lived, private in-memory URLs instead of
being embedded as base64 inside JSON responses. The current opaque session ID is
kept in the address bar, so refreshing restores the photo, chosen filter, and
all adjustment settings while the server still holds that session. Results
expire when evicted from the 20-session limit or when the server restarts.

By default the Flask dev server runs with debug off. For local debugging,
set `PHOTO_ENHANCE_DEBUG=1` before starting it.

## Running the CLI

```bash
# Single photo, writes photo_enhanced.jpg next to the original
uv run photo-enhance path/to/photo.jpg

# With a creative preset
uv run photo-enhance path/to/photo.jpg --preset warm_film

# Use gentler automatic corrections or disable a stage that does not suit the photo
uv run photo-enhance path/to/photo.jpg --mode gentle --no-white-balance

# With bird-oriented tonal and detail defaults
uv run photo-enhance path/to/bird.jpg --preset bird_natural

# Browse preset IDs with their display names and descriptions
uv run photo-enhance --list-presets

# Privacy-sensitive WebP export: remove metadata and choose quality
uv run photo-enhance path/to/photo.jpg --format webp --metadata strip --quality 90

# Batch process a folder, writing to an output folder
uv run photo-enhance path/to/folder --batch -o path/to/output_folder

# Preview the files and destinations without decoding or writing photos
uv run photo-enhance path/to/folder --batch -o path/to/output_folder --dry-run

# Include nested folders and recreate their relative structure under the output
uv run photo-enhance path/to/folder --batch --recursive -o path/to/output_folder

# Return one JSON batch result for a script instead of human status lines
uv run photo-enhance path/to/folder --batch -o path/to/output_folder --json-summary
```

Nature presets: `bird_natural`, `feather_detail`, `backlit_bird`, `woodland`,
and `overcast`. Creative presets: `warm_film`, `cool_moody`,
`high_contrast_bw`, `faded_vintage`, `golden_hour`, `teal_ember`,
`cross_process`, and `soft_portrait`. They are defined in
`src/photo_enhance/preset_data/`; nature presets also bundle their intended
lighting, color, detail, and denoise defaults.

The CLI applies EXIF orientation to the pixels and removes the orientation tag
so viewers cannot rotate the result twice. By default it preserves EXIF
(including GPS), ICC profiles, and DPI where the output format supports them.
Use `--strip-metadata` to remove all three. XMP, comments, thumbnails, and other
container-specific metadata are not guaranteed to survive.

JPEG exports default to quality 92, WebP to quality 90, PNG uses optimized
lossless compression, and TIFF uses LZW compression. `--quality 1-100` is
available for JPEG and WebP outputs. Use `--format jpeg|png|tiff|bmp|webp` to
force the encoded format and corresponding filename extension for one photo or
an entire batch. `--metadata preserve|strip` makes the metadata policy explicit;
the older `--strip-metadata` flag remains as shorthand.

By default, the CLI refuses to let an output path overwrite its input (single
file, or a batch output folder that resolves to the input folder) — pass
`--overwrite` to allow it explicitly.

Use `--dry-run` to inspect supported inputs, output paths, collisions, and the
batch summary without reading image contents or creating the output folder.
Add `--recursive` in batch mode to include nested folders. When an output folder
is supplied, each photo's relative directory structure is recreated there; an
output tree inside the input folder is excluded from future recursive runs.

Automatic corrections default to `--mode standard`; `gentle` scales the
analyzed recipe down and `strong` increases it within the same safe 0–100%
bounds. `--no-white-balance`, `--no-levels`, and `--no-local-contrast` disable
individual Auto stages for difficult lighting or diagnosis. A selected preset
still keeps its authored look and nature-adjustment defaults.

Interactive batches prefix status with the current and total file count; logs
retain stable one-line statuses and a final summary. `--json-summary` replaces
those lines with one JSON object containing totals and per-file results. Ctrl-C
exits with status 130, and the atomic writer does not install the interrupted
photo's temporary output.

## Supported image contract

The enhancement pipeline accepts and returns non-empty NumPy arrays with shape
`(height, width, 3)`, BGR channel order, and `uint8` pixels in the 0–255 range.
JPEG, PNG, TIFF, BMP, and WebP files are supported. Grayscale and CMYK sources
are converted to that contract. Alpha/transparency and images above 8 bits per
channel are currently rejected because accepting them would silently discard
data. RAW files remain out of scope.

## Running tests

```bash
uv run pytest
```

## macOS setup notes

- `opencv-python` and `Pillow` both ship prebuilt wheels for `arm64` and `x86_64`
  Macs — `uv sync` just works, no compiling.
- Project is pinned to Python 3.12 (not the newest 3.14) specifically because
  `opencv-python` wheel coverage for very new Python versions can lag behind —
  3.12 is the safe, well-supported choice.
- **RAW support (stretch goal, not yet implemented):** if `rawpy` gets added later,
  it wraps `libraw`, which on Apple Silicon sometimes needs to be installed via
  Homebrew first (`brew install libraw`) before `pip install rawpy` behaves
  correctly. Do this before adding the dependency, not after hitting a build error.

## Project structure

```
photo-enhance/
├── README.md
├── LICENSE                   # MIT license
├── CHANGELOG.md              # log of changes made
├── pyproject.toml
├── .vscode/launch.json       # VS Code Run button config
├── src/photo_enhance/
│   ├── cli.py                 # CLI entry point
│   ├── web.py                 # Flask web UI entry point
│   ├── templates/index.html   # web UI page
│   ├── auto_levels.py         # white balance + levels + CLAHE
│   ├── nature.py              # wildlife tone, vibrance, detail, and denoise controls
│   ├── finishing.py           # warmth, fade, vignette, and grain
│   ├── presets.py             # preset loading/application
│   ├── imageio_utils.py       # PIL/OpenCV bridge + EXIF handling
│   └── preset_data/*.json     # tone-curve preset definitions
├── tests/
└── examples/                  # drop before/after sample images here (gitignored)
```

## Project boundaries

Photo Enhance stays local: no cloud processing, user accounts, or required ML
model dependency. Larger optional capabilities—including RAW support,
Real-ESRGAN integration, and `.cube` LUT files—remain tracked as possible future
work in [PROJECT_REVIEW.md](PROJECT_REVIEW.md).

## Use it on copies

- Keep your originals backed up. The CLI avoids overwriting inputs unless you
  pass `--overwrite`, but that flag can replace files permanently.
- Enhancement is heuristic. Auto limits white balance when it cannot find
  enough neutral-looking pixels, but difficult lighting, dominant colors, or
  extreme exposure can produce unwanted color shifts, clipping, or contrast.
  Review every result before replacing or publishing a photo.
- Output may be lossy or discard source information. This is a photo-finishing
  tool, not an archival, restoration, or forensic workflow.
- The CLI preserves supported EXIF metadata—including GPS—by default. Use
  `--strip-metadata` before sharing when location or camera data is sensitive.
  Web previews and downloads are metadata-free JPEGs.
- The web interface uses Flask's development server on `127.0.0.1`. Do not
  expose it to a public network or treat it as a production web service.

## License

Released under the [MIT License](LICENSE). The software is provided as-is,
without warranty; see the license text for the complete terms.
