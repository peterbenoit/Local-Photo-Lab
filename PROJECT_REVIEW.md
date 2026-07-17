# Photo Enhance — Project Review and Improvement Backlog

Reviewed 2026-07-15. This backlog is based on the current implementation, tests,
documentation, and built package artifacts. Priorities reflect risk and value:
P0 protects photos and prevents incorrect behavior; P1 makes the MVP dependable;
P2 improves product quality; P3 contains larger, optional capabilities.

## Baseline verified

- [x] Confirm the core pipeline is shared by the CLI and web UI rather than duplicated.
- [x] Run the existing suite: all 10 tests pass.
- [x] Confirm `uv.lock` resolves cleanly and matches `pyproject.toml`.
- [x] Build both the source distribution and wheel successfully.
- [x] Confirm the wheel contains the HTML template and all four preset JSON files.
- [x] Confirm the project has one small, understandable module per major responsibility.

## P0 — Protect inputs and make failures truthful

- [x] Refuse to process when a single-file output resolves to the input path; never overwrite an original implicitly.
- [x] Refuse or require an explicit `--overwrite` when a batch output directory is the input directory, because current output names can replace source files.
- [x] Write each output to a temporary file and atomically rename it only after encoding succeeds, so an interruption cannot leave a corrupt final file.
- [x] Add collision handling (`error`, `skip`, or explicit overwrite) instead of silently replacing an existing output.
- [x] Return a non-zero CLI exit status when any batch item fails, while still processing the remaining files.
- [x] Print a batch summary with processed, skipped, and failed counts.
- [x] Validate `clip_percent`, CLAHE clip limit, tile size, image shape, channel count, and dtype at the public API boundary with actionable errors.
- [x] Validate preset names with a Click choice and return a friendly web form error for an unknown or tampered preset instead of a server error.
- [x] Replace `app.run(debug=True, ...)` with an explicit safe default: debug off and host fixed to `127.0.0.1`; enable development debugging only through an opt-in flag or environment variable.
- [x] Add friendly handlers for oversized uploads (`413`), malformed images, decoding failures, enhancement failures, and encoding failures.
- [x] Enforce a decoded pixel/dimension limit in addition to the 20 MB compressed upload limit to prevent excessive memory use from highly compressed images.
- [x] Catch expected image/IO exceptions specifically; do not let a broad `except Exception` make programming defects look like skipped photos.

## P0 — Preserve image fidelity intentionally

- [x] Decide and document the supported pixel contract: the current pipeline converts every input to 8-bit, three-channel RGB/BGR.
- [x] Preserve alpha for PNG and WebP, or reject transparent inputs clearly instead of silently flattening them.
- [x] Preserve 16-bit PNG/TIFF data through an appropriate pipeline, or detect and warn before down-converting to 8-bit.
- [x] Handle EXIF orientation deliberately with `ImageOps.exif_transpose()` and normalize/remove the orientation tag after rotating pixels.
- [x] Preserve ICC profiles so colors do not change unexpectedly in color-managed viewers.
- [x] Decide whether to preserve XMP, DPI, comments, and other format metadata; document what is retained and what is dropped.
- [x] Add `--strip-metadata` for privacy-sensitive exports, especially to remove embedded GPS data, and document that EXIF is currently preserved by default.
- [x] Use format-aware save settings instead of Pillow defaults; expose JPEG/WebP quality and avoid unnecessary recompression where possible.
- [x] Keep the web result in the source format when feasible, or clearly disclose that the preview/export is converted to JPEG without source metadata or transparency.
- [x] Add regression tests for orientation, EXIF, ICC, alpha, grayscale, CMYK, 16-bit input, and format-specific output behavior.

## P1 — Prove all user-facing paths

- [x] Add CLI tests with Click's test runner for single-file success, presets, default naming, custom output, bad input types, and overwrite protection.
- [ ] Add batch CLI tests for mixed files, empty folders, per-file failures, summaries, output collisions, and exit codes.
- [x] Add `imageio_utils.py` round-trip tests for every advertised extension.
- [ ] Add Flask test-client coverage for the index, valid upload, missing upload, invalid image, invalid preset, oversized request, and enhancement failure.
- [x] Add a packaged-wheel smoke test that installs the wheel and runs both console entry points; source-tree tests alone cannot catch missing package data.
- [ ] Replace weak implementation-coupled assertions with outcome tests based on luminance, clipping, color error, and perceptual difference.
- [ ] Add edge-case tests for all-black, all-white, constant-color, tiny, very large, noisy, extremely dark, and extremely bright images.
- [ ] Add property-style tests asserting output shape/dtype, finite values, valid channel range, determinism, and no mutation of the input array.
- [ ] Establish a small, redistributable reference-image corpus and store expected quality metrics or reviewed golden outputs.
- [ ] Add test coverage reporting and set an initial threshold that includes `cli.py`, `web.py`, and `imageio_utils.py`, not only the CV functions.
- [ ] Add linting and formatting configuration, then enforce it in local checks and CI.
- [ ] Add static type checking for public functions and replace the untyped preset `dict` with a typed model or `TypedDict`.
- [ ] Add CI for supported Python versions on macOS, plus at least one Linux packaging/test job if cross-platform support is intended.
- [ ] Add a dependency vulnerability and stale-version check to CI, with automated update proposals for direct dependencies.

## P1 — Make enhancement quality measurable

- [ ] Build a representative evaluation set covering portraits, landscapes, snow, sunsets, night scenes, dominant-color scenes, low contrast, and already-correct photos.
- [ ] Review whether per-channel auto levels after gray-world balancing over-neutralizes intentional color and move to luminance-only levels if evaluation supports it.
- [ ] Add safeguards for gray-world failure cases such as sunsets, stage lighting, underwater images, and frames dominated by one color.
- [ ] Measure clipped-shadow and clipped-highlight percentages before and after enhancement and cap adjustments when clipping becomes excessive.
- [ ] Avoid unnecessary processing of already well-exposed, well-balanced images by calculating confidence and applying bounded correction strengths.
- [ ] Tune the combined levels-plus-CLAHE stages to prevent halos, noise amplification, and excessive local contrast.
- [ ] Add skin-tone checks to the evaluation set so white balance and presets do not create implausible faces.
- [ ] Record enhancement decisions and useful metrics in a result object for debugging and optional CLI reporting.
- [ ] Benchmark runtime and peak memory for common phone/camera resolutions, including the largest accepted web upload.
- [ ] Downsample for histogram analysis and/or process in bounded-memory tiles where benchmarks show meaningful savings.

## P1 — Improve the web experience and accessibility

- [x] Add visible `<label>` elements for the file input and preset selector.
- [x] Wrap primary content in `<main>` and give the result area an appropriate heading.
- [x] Give errors `role="alert"` (or an assertive live region), move focus to them after submission, and associate upload errors with the file control.
- [x] Add a polite status region for processing and completion so assistive technology announces state changes.
- [x] Replace the hard-coded error color with light/dark theme tokens that meet WCAG AA contrast in both color schemes.
- [x] Verify visible keyboard focus and 44-by-44-pixel target sizing for every interactive control.
- [x] Preserve the selected preset when the form is re-rendered after success or error.
- [x] Add a download button with a meaningful filename and the chosen format/quality settings.
- [x] Add a draggable before/after comparison slider while retaining a keyboard-accessible side-by-side mode.
- [x] Add drag-and-drop as a progressive enhancement without removing the native file input.
- [x] Show image dimensions, output format, preset, and processing time with the result.
- [x] Avoid embedding two large base64 images directly in the HTML; use short-lived in-memory result URLs or browser-side object URLs with explicit cleanup.
- [x] Prevent accidental duplicate submissions and show a processing state for large photos.
- [x] Preserve results across refresh using a redirect-after-post or a clearly documented ephemeral-result model.
- [x] Add a short privacy note explaining localhost scope, metadata handling, temporary memory use, and that debug mode must remain disabled.

## P1 — Strengthen CLI usability

- [ ] Add `--list-presets` that prints each preset's display name and description, not only its internal identifier.
- [ ] Add `--dry-run` to show selected inputs and output paths without writing files.
- [ ] Add optional recursive folder processing while preserving relative directory structure.
- [ ] Add explicit `--format`, `--quality`, and metadata-policy options with validated combinations.
- [ ] Expose bounded correction strength controls or named modes such as `gentle`, `standard`, and `strong`.
- [ ] Allow individual white-balance, levels, and CLAHE stages to be disabled for diagnosis and user preference.
- [ ] Add a progress indicator for large batches that degrades cleanly in non-interactive logs.
- [ ] Support machine-readable JSON summaries for automation.
- [ ] Ensure Ctrl-C produces no partial output and exits with the conventional interruption status.

## P2 — Clarify architecture and extension points

- [ ] Introduce an immutable enhancement-options object instead of adding more positional parameters to `auto_enhance()`.
- [ ] Separate pipeline orchestration from individual transforms so both entry points can request the same validation, metrics, and error model.
- [ ] Define and validate a versioned preset schema, including required channels, monotonic control-point coordinates, bounds, duplicate points, and saturation range.
- [ ] Display preset names/descriptions from JSON rather than deriving labels from filenames.
- [ ] Cache validated preset LUTs rather than rebuilding them for every image in a batch.
- [ ] Add a controlled user-preset directory with clear precedence and errors; never execute preset content.
- [ ] Add structured logging behind a verbose flag while keeping normal CLI output concise.
- [ ] Document the public Python API and decide which functions are stable enough to export from `photo_enhance.__init__`.
- [ ] Add a package `__version__` sourced from project metadata for diagnostic output.

## P2 — Packaging, documentation, and repository hygiene

- [ ] Add the actual `LICENSE` file promised by `pyproject.toml`.
- [ ] Exclude `.claude/settings.local.json` and editor-local configuration from the source distribution; the current sdist includes them.
- [ ] Decide whether `.vscode/` belongs in the sdist; keep useful shared launch settings in Git but omit them from published artifacts if distributing publicly.
- [ ] Resolve the Python support mismatch: README says Python 3.12 is required while `pyproject.toml` declares 3.11 and newer.
- [ ] Decide whether the package is macOS-only; if not, document and test the actual supported platforms.
- [ ] Make the optional web dependency behavior friendly: `photo-enhance-web` should explain how to install the `web` extra instead of failing with `ModuleNotFoundError`.
- [ ] Add authors, project URLs, classifiers, keywords, and a typed license expression if the package will be published.
- [ ] Keep `TASKS.md` accurate by marking the already-created first commit complete and separating historical MVP completion from future work.
- [ ] Add a concise developer guide covering environment setup, tests, formatting, type checks, builds, and release steps.
- [ ] Add real before/after examples with permission-compatible source images; the current `examples/` policy ignores the very assets users need to assess quality.
- [ ] Document algorithm limitations, lossy transformations, supported modes/bit depths, output naming, overwrite policy, and metadata/privacy behavior.
- [ ] Add a troubleshooting section for OpenCV/Pillow install issues, unsupported/corrupt images, memory limits, and unexpectedly strong corrections.
- [ ] Adopt semantic versioning and release notes that distinguish user-visible changes, fixes, compatibility changes, and known limitations.

## P3 — Optional v2 capabilities

- [ ] Add RAW import with `rawpy` behind an optional extra, including camera white-balance selection and documented demosaic/output behavior.
- [ ] Add `.cube` LUT import with parser validation, color-space documentation, and interpolation tests.
- [ ] Add side-by-side comparison export to the CLI with labels and configurable layout.
- [ ] Evaluate a conservative denoise/sharpen stage separately from exposure and color correction; keep it opt-in until quality data supports a default.
- [ ] Evaluate an optional Real-ESRGAN integration as a separate extra/process so the classical CPU-only MVP stays lightweight.
- [ ] Add a non-destructive recipe/manifest export so an enhancement can be reproduced later from the original.
- [ ] Add a low-priority recent-edits tray for the latest configurable number of photos. Start with the existing capped in-memory sessions rather than browser persistence; restore each surviving session's current look/intensity, provide Remove/Clear controls and explicit retention/privacy copy, and let entries expire on restart or eviction. Keep originals outside persistent application-managed storage and require a demonstrated need plus explicit opt-in before considering `localStorage`, IndexedDB, or disk persistence.

## Recommended delivery order

- [x] Milestone 1: complete all P0 items and their regression tests before processing irreplaceable photo libraries.
- [ ] Milestone 2: add CLI/web/image-I/O coverage, CI, a reference-image corpus, and measurable quality guardrails.
- [ ] Milestone 3: deliver download/export, accessible form feedback, overwrite controls, and configurable enhancement strength.
- [ ] Milestone 4: improve color/metadata fidelity and formalize presets and pipeline options.
- [ ] Milestone 5: choose P3 features only from demonstrated user needs and benchmark evidence.
