# Photo Enhance — Product Roadmap

Re-evaluated 2026-07-19 against the current application rather than the original
2026-07-15 audit. This roadmap prioritizes visible editing value and measured
image quality. An unchecked count is not a measure of product completeness.

## Current state

Photo Enhance is a dependable, feature-complete MVP rather than an unfinished
prototype.

- The web editor provides explainable Auto corrections, nature adjustments,
  creative presets, finishing controls, live before/after comparison, downloads,
  refresh restoration, and an ephemeral recent-edits tray.
- The CLI handles single photos, batches, recursion, output formats and quality,
  metadata policy, correction modes, stage switches, dry runs, JSON summaries,
  custom presets, and labeled comparison exports.
- Input protection, atomic output, collision handling, orientation, ICC/EXIF/DPI
  behavior, unsupported fidelity cases, upload limits, and user-facing failures
  are explicit.
- The CLI and web UI share an immutable, analyzed enhancement pipeline with
  versioned preset validation and reproducible settings.
- Packaging, installed-wheel smoke tests, macOS/Linux CI, linting, formatting,
  typing, coverage, vulnerability checks, and dependency updates are established.
- The suite currently contains 137 passing tests.

The product no longer needs to progress by completing every historical audit
idea. New work should improve photographs, editing flow, or a demonstrated user
workflow.

## Now — Prove and improve real-photo quality

Treat the remaining quality and test ideas as one coordinated workstream, not a
collection of independent chores.

- [ ] Assemble a small, redistributable evaluation set of roughly 12–20 images:
  portraits, landscapes, snow, sunsets, night scenes, dominant-color scenes,
  low contrast, already-correct photos, and representative bird photography.
- [ ] Review Auto, nature controls, and selected presets on that set at normal
  viewing size and 100% detail. Record reviewed before/after examples alongside
  useful measurements rather than relying on synthetic arrays alone.
- [ ] Capture before/after tonal range, shadow clipping, highlight clipping,
  color-cast movement, and a practical perceptual-difference measure.
- [ ] Fix only failures demonstrated by the evaluation set. Candidate changes
  include luminance-only levels, stronger dominant-color safeguards, clipping
  caps, already-correct-image confidence, and gentler levels/CLAHE interaction.
- [ ] Convert demonstrated failures into focused regressions covering outcomes,
  determinism, valid pixels, input immutability, and the smallest meaningful set
  of black, white, constant, tiny, noisy, dark, and bright edge cases.
- [ ] Measure runtime and peak memory on common phone/camera resolutions. Add
  tiled or bounded-memory processing only where measurements show a real need.

Definition of done: the reviewed corpus looks consistently better or stays
appropriately unchanged, known failure modes are documented, and automated
metrics prevent the observed regressions without pretending to score beauty.

## Now — Make editing easier

These are the highest-value visible product additions not represented by the
old backlog.

1. [x] Add clear **Reset to Auto** and **Reset all** actions. Reset restores
   the analyzed recommendation without re-uploading the source.
2. [ ] Add session-scoped undo and redo for adjustment changes. Start with a
   bounded in-memory recipe history; do not duplicate full-resolution pixels.
3. [ ] Add 100% inspection with zoom and pan so detail, denoise, grain, and
   sharpening decisions can be judged accurately.
4. [ ] Add web export controls for JPEG/WebP format and quality. Keep web exports
   metadata-free unless a separate, explicit privacy decision changes that.
5. [ ] Add a non-destructive recipe manifest that can be saved, inspected, and
   applied to another compatible source in the CLI before considering broader
   preset-management features.

## Next — Strengthen real workflows

These should follow observation of actual use rather than the existence of a
checkbox.

- [ ] Decide whether copying the current recipe to another web upload solves a
  frequent workflow; if so, add it without persistent browser storage.
- [ ] Decide whether users need synchronized batch recipes between the web UI
  and CLI, then define one versioned interchange format if justified.
- [ ] Publish a small before/after gallery from the reviewed evaluation images
  so prospective users can judge the tool without installing it.
- [ ] Consolidate troubleshooting and algorithm limitations around problems
  encountered during real evaluation or user reports. Avoid speculative manuals.

## Later — Demand-driven extensions

Do not build these simply because they are technically interesting.

- [ ] `.cube` LUT import: proceed when users have LUT-based workflows that the
  existing versioned preset format cannot represent.
- [ ] RAW import: proceed when camera-file demand justifies `rawpy`, demosaicing
  choices, camera white balance, larger memory use, and platform support costs.
- [ ] Real-ESRGAN or another ML enhancer: keep separate from the classical local
  pipeline and require a clear restoration/upscaling use case plus benchmarks.

The existing detail and denoise controls already cover conservative local
sharpening and noise reduction. Further work there belongs in the real-photo
quality loop, not in a separate feature initiative.

## Explicit non-goals for now

- Persistent browser or disk storage for uploaded originals
- User accounts, cloud processing, or remote photo transfer
- Building a general-purpose replacement for Lightroom or Photoshop
- Expanding tests, documentation, or architecture without a specific product,
  quality, safety, or maintenance outcome

## Completed foundation

The original audit work is complete enough to stop tracking line by line:

- Input protection and truthful failure behavior
- Deliberate image-fidelity and metadata contract
- CLI, web, image-I/O, and installed-package coverage
- Accessible upload, editing, comparison, feedback, and download flows
- Full CLI usability and automation controls
- Shared pipeline, typed/versioned presets, user preset directory, and logging
- Packaging metadata, CI, coverage, type/lint checks, dependency auditing, and
  semantic-versioned release guidance

Historical implementation details remain available in `CHANGELOG.md` and Git
history. This file should remain a product roadmap, not return to being an
exhaustive audit ledger.
