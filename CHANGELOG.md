# Changelog

All notable changes to this project are logged here, newest first.

## 2026-07-16 — CLI path and image-format coverage

- Added Click-runner regressions for default and custom output paths, preset
  selection, missing inputs, and incorrect file/folder mode combinations.
- Confirmed each advertised image extension through the existing parameterized
  BGR `uint8` save/load round-trip coverage and reconciled both completed P1
  items in the project backlog. The suite now has 84 tests.

## 2026-07-16 — Lean session URLs and refresh restoration

- Replaced base64 preview data inside JSON with private, no-store session image
  URLs. A measured 1600×1200 upload response fell from 4,538,264 bytes to 536
  bytes—a 99.99% reduction—while the JPEGs transfer as normal image resources.
- Session memory now retains the base enhanced array plus encoded before/current
  previews instead of both full image arrays and transient base64 strings.
- Downloads use the same short-lived result resource with a server-provided
  attachment filename and `nosniff` response protection.
- The opaque session ID is stored in the page URL. Refreshing restores the
  original/current previews, selected filter, intensity, details, and download
  while the in-memory session still exists; expired sessions degrade to a clear
  status and remove the stale URL parameter.
- Filter requests carry monotonic revisions. A slower, older request receives
  `409` and cannot replace a newer result; superseded image URLs also expire.
- Added transport-size, image response, download header, refresh state,
  expiration, and stale-revision regressions. The suite now has 78 tests.

## 2026-07-16 — Drag-and-drop and interactive comparison

- Added file drag-and-drop as progressive enhancement over the unchanged native
  file input. File drops reuse the existing upload, validation, busy, error,
  and stale-request handling paths.
- Added a before/after reveal controlled by a native range input stretched over
  the image. It supports pointer, touch, arrow keys, Home, and End without a
  custom gesture library and exposes a changing accessible value description.
- Added an explicit comparison-view toggle. The original side-by-side view
  remains available and is the automatic fallback when JavaScript is disabled.
- The visual divider and 44-pixel handle update immediately during input; no
  decorative transition delays interaction or requires a reduced-motion branch.
- Converted the inline browser code to an ES module and added structure and
  behavior regressions plus a rendered-template JavaScript syntax check. The
  suite now has 73 tests.
- Corrected the comparison direction so the original is always left of the
  divider and the enhanced result is always right (`before | after`), including
  visible labels and assistive-technology value text.

## 2026-07-16 — Accessible results and downloads

- Added a skip link, main landmark, enhancement-controls legend, named results
  section, and semantic result details.
- Upload errors are associated with the file input and receive focus after a
  failed submission. Processing updates use a polite atomic status region;
  successful uploads move focus to the new results heading.
- Added light/dark error and focus tokens, a persistent visible focus indicator,
  and 44-pixel minimum interactive target sizing.
- The result now reports dimensions, source format, JPEG preview format, active
  filter, and processing time returned by Flask rather than inferred in the UI.
- Added a download link for the currently displayed result with a sanitized,
  descriptive filename that follows filter changes.
- Guarded duplicate uploads, exposed busy state to assistive technology, and
  invalidated stale filter responses when a new photo is uploaded.
- Added HTML structure, response metadata, filename sanitization, and filtered
  download-name regressions. The suite now has 72 tests.

## 2026-07-16 — Explicit image fidelity and metadata controls

- CLI and web decoding now share one Pillow-based path. EXIF orientation is
  applied to pixels and removed from retained metadata, preventing incorrect or
  double rotation in downstream viewers.
- EXIF (including GPS), ICC profiles, and DPI metadata are preserved by default
  for compatible CLI output formats. New `--strip-metadata` removes them for
  privacy-sensitive exports.
- Transparent and greater-than-8-bit inputs now fail with actionable messages
  instead of silently losing alpha or bit depth. Grayscale and CMYK inputs are
  explicitly supported through conversion to the documented 8-bit BGR contract.
- Added format-aware output settings: JPEG quality 92, WebP quality 90,
  optimized PNG, and LZW-compressed TIFF. New `--quality 1-100` controls JPEG
  and WebP exports.
- Web previews now disclose that results are metadata-free 8-bit JPEGs.
- Added advertised-format round trips and regressions for orientation, EXIF,
  ICC, DPI, alpha, grayscale, CMYK, 16-bit grayscale/RGB, metadata stripping,
  CLI error handling, and quality validation. The suite now has 70 tests.

## 2026-07-16 — Safer output and truthful failures

- CLI output is now encoded to a same-directory temporary file and atomically
  moved into place, preventing a failed or interrupted save from leaving a
  partial destination file.
- Existing outputs are preserved by default. Single-file mode reports an error;
  batch mode skips collisions. `--overwrite` explicitly opts into replacement.
- Batch processing now distinguishes skipped files from failed images, continues
  through expected image and I/O errors, prints processed/skipped/failed totals,
  and exits non-zero when any image fails.
- `--preset` now uses Click choice validation, producing a concise usage error
  before processing starts when a preset name is invalid.
- The public enhancement functions now validate BGR shape, non-empty dimensions,
  `uint8` dtype, clipping percentage, CLAHE clip limit, and tile size.
- Web uploads now enforce a 40-megapixel decoded-image cap and 12,000-pixel
  per-side cap before OpenCV decoding, in addition to the 20 MB upload cap.
  Oversized, malformed, decode, enhancement, filter, and preview-encoding
  failures return friendly JSON errors.
- Expanded the suite from 25 to 52 tests for output collisions, atomic-save
  cleanup, batch summaries and exit codes, parameter validation, decoded image
  limits, and web error responses.

## 2026-07-15 — Web UI usability pass: upload once, tweak filters live

Driven by feedback that the first version's web UI required re-uploading the
photo every time the filter changed, and that filter options weren't exposed
at selection time.

- **Stateful sessions instead of stateless form posts.** `web.py` now holds
  the decoded original image and its base auto-enhanced version in an
  in-memory dict keyed by a UUID (`_sessions`, capped at 20 entries, FIFO
  eviction), returned to the browser as `session_id`. Replaced the old single
  `/enhance` route with `/upload` (decode + auto-enhance once, return
  `session_id` + before/after) and `/apply` (look up the session, apply a
  preset at a given intensity, return only the new "after" image). Changing
  the preset or intensity no longer re-uploads or re-decodes the file.
- **Per-filter option:** added a universal 0-100% intensity slider
  (`apply_preset_blended()` in `presets.py`, an `cv2.addWeighted` blend
  between the un-filtered and fully-filtered result). Chose one slider that
  works identically for every preset over per-preset parameter schemas, to
  ship usability improvements without redesigning the preset JSON format.
  Revisit if a single slider proves too blunt — noted in `TASKS.md`.
- **Preset dropdown now shows real names/descriptions** (`list_preset_choices()`
  in `presets.py`) instead of deriving a label from the filename.
- Rewrote `templates/index.html` with vanilla JS (`fetch`, no framework):
  upload triggers `/upload` via `FormData`; preset/intensity changes trigger
  `/apply` via JSON `fetch`, with a request token to discard stale responses
  if the user changes the slider again before a prior request returns.
- **Folded in two P0 fixes from `PROJECT_REVIEW.md`** (a review backlog file
  the project owner added; full backlog now tracked in `TASKS.md`, everything
  else deferred):
  - `web.py` no longer runs with `debug=True` by default — debug is off
    unless `PHOTO_ENHANCE_DEBUG=1` is set, and host is fixed to `127.0.0.1`.
  - `cli.py` now refuses to let a single-file output overwrite its input, and
    refuses batch mode when the output folder resolves to the input folder,
    both unless `--overwrite` is explicitly passed. This was a real bug: batch
    mode's default per-file naming (`output_dir / input_path.name`) would
    have silently overwritten source photos if `-o` pointed at the same
    folder as the input.
- Added `tests/test_web.py` (Flask test client: index page, upload
  success/failure, apply success/failure, unknown preset, no-preset case) and
  `tests/test_cli_overwrite.py` (all four overwrite-protection paths via
  Click's `CliRunner`). Extended `tests/test_presets.py` for
  `list_preset_choices()` and `apply_preset_blended()` at 0%/50%/100%.
  Full suite: 25/25 passing.
- Moved `flask` into the `dev` dependency group (in addition to the `web`
  extra) so `uv sync` without `--extra web` still installs what the test
  suite needs to import `photo_enhance.web`.
- Verified manually in-browser (Claude Browser tooling, since native file
  pickers can't be scripted): uploaded a synthetic test photo once, then
  switched preset and dragged intensity twice, confirmed via the network log
  that exactly one `/upload` call ever fired.
- Merged `PROJECT_REVIEW.md`'s full backlog into `TASKS.md`, organized by the
  original P0-P3 priority, so open items aren't only tracked in a
  loose top-level file.

## 2026-07-15 — Initial scaffold

- Set up repo structure per spec: `src/photo_enhance/`, `tests/`, `examples/`.
- Pinned project to Python 3.12 via `uv` (`.python-version`), chosen over the
  system default 3.14 for safer `opencv-python` wheel compatibility.
- `git init` — local repo only, no remote configured yet.
- Implemented core pipeline (`auto_levels.py`):
  - `gray_world_white_balance()` — per-channel mean scaling to a neutral gray.
  - `auto_levels()` — per-channel percentile black/white point stretch (default
    0.5% clip each end).
  - `apply_clahe()` — CLAHE on the LAB L channel only, to avoid per-channel
    color shifts.
  - `auto_enhance()` — combines the three in sequence.
- Implemented preset system (`presets.py`):
  - JSON-defined per-channel tone curves (linear interpolation between control
    points) plus a saturation multiplier.
  - Shipped 4 presets: `warm_film`, `cool_moody`, `high_contrast_bw`,
    `faded_vintage`.
- Implemented `imageio_utils.py` — PIL/OpenCV bridging with EXIF byte
  preservation on load/save.
- Implemented CLI (`cli.py`) — `enhance <input> [-o output] [--preset name]
  [--batch]`, single-file and batch/folder modes, skips unsupported files in
  batch mode instead of crashing.
- Added a local Flask web UI (`web.py` + `templates/index.html`) as an addition
  beyond the original spec's CLI-only design — decision made because the CLI
  alone was judged unlikely to get revisited without a visual entry point.
  Runs on `localhost:5050`, in-memory processing, no persistence, no network
  calls.
- Added `.vscode/launch.json` so the web UI can be started with VS Code's Run
  button instead of a typed command.
- Added tests: `test_auto_levels.py` (white balance, levels, CLAHE, full
  pipeline) and `test_presets.py` (LUT interpolation, preset application).
- **Bug found and fixed:** `preset_data/` was originally named `presets/`,
  colliding with the `presets.py` module in the same package. Python resolved
  `photo_enhance.presets` to the module, not the directory, so
  `importlib.resources.files()` silently looked in the wrong place and
  `list_presets()` returned nothing. Renamed the directory to `preset_data/`
  to remove the collision. Caught by the test suite (`test_presets.py`), not
  by chance.
- Verified end-to-end: `uv sync --extra web` installs clean; full pytest suite
  (10 tests) passes; CLI single-file, `--preset`, and `--batch` (with a mixed
  file-type folder, including one non-image file that's skipped without
  crashing) all confirmed against a synthetic test photo, with measurable
  contrast increase (std 44 → 75) and channel rebalancing; Flask web UI
  confirmed serving the form with all four presets listed and `/enhance`
  returning valid before/after JPEG data URIs for both no-preset and
  preset-selected submissions.
