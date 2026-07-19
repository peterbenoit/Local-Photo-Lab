"""CLI entry point: enhance <input> [-o output] [--preset name] [--batch]"""

import json
import logging
from pathlib import Path

import click
import cv2
from PIL import Image, UnidentifiedImageError

from photo_enhance.comparison import build_comparison
from photo_enhance.imageio_utils import is_supported_image, load_bgr, save_bgr
from photo_enhance.nature import NatureSettings
from photo_enhance.pipeline import EnhancementError, EnhancementOptions, enhance_image
from photo_enhance.presets import Preset, list_preset_choices, list_presets, load_preset

PROCESSING_ERRORS = (
    OSError,
    ValueError,
    cv2.error,
    UnidentifiedImageError,
    Image.DecompressionBombError,
    EnhancementError,
)

OUTPUT_FORMAT_SUFFIXES = {
    "jpeg": ".jpg",
    "png": ".png",
    "tiff": ".tiff",
    "bmp": ".bmp",
    "webp": ".webp",
}

MODE_STRENGTHS = {"gentle": 0.65, "standard": 1.0, "strong": 1.25}
LOGGER = logging.getLogger("photo_enhance")


def _configure_logging(verbose: bool) -> None:
    LOGGER.handlers.clear()
    if not verbose:
        LOGGER.addHandler(logging.NullHandler())
        LOGGER.setLevel(logging.WARNING)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def _output_path(
    input_path: Path,
    output: Path | None,
    is_batch: bool,
    *,
    input_root: Path | None = None,
    output_format: str | None = None,
) -> Path:
    if output is None:
        result = input_path.with_stem(input_path.stem + "_enhanced")
    elif is_batch:
        relative_path = input_path.relative_to(input_root) if input_root else Path(input_path.name)
        result = output / relative_path
    else:
        result = output
    return result.with_suffix(OUTPUT_FORMAT_SUFFIXES[output_format]) if output_format else result


def _comparison_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_before-after.jpg")


def _print_presets(preset_dir: Path | None = None) -> None:
    """Print stable preset IDs alongside the names and descriptions people see in the UI."""
    for preset in list_preset_choices(preset_dir):
        click.echo(f"{preset['id']}: {preset['name']}")
        if preset["description"]:
            click.echo(f"  {preset['description']}")


def _echo_batch(message: str, *, index: int, total: int, json_summary: bool) -> None:
    if json_summary:
        return
    stream = click.get_text_stream("stdout")
    prefix = f"[{index}/{total}] " if stream.isatty() else ""
    click.echo(f"{prefix}{message}")


def _emit_json(payload: dict) -> None:
    click.echo(json.dumps(payload, sort_keys=True))


def _process_one(
    input_path: Path,
    output_path: Path,
    preset: Preset | None,
    *,
    strip_metadata: bool = False,
    quality: int | None = None,
    mode: str = "standard",
    white_balance: bool = True,
    levels: bool = True,
    local_contrast: bool = True,
    comparison_path: Path | None = None,
    comparison_layout: str = "horizontal",
    comparison_size: int = 2400,
) -> None:
    img, metadata = load_bgr(input_path)
    defaults = preset.get("defaults", {}) if preset is not None else {}
    nature_settings = None
    if defaults:
        nature_settings = NatureSettings(
            shadows=defaults.get("shadows", 0) / 100.0,
            highlights=defaults.get("highlights", 0) / 100.0,
            vibrance=defaults.get("vibrance", 0) / 100.0,
            detail=defaults.get("detail", 0) / 100.0,
            denoise=defaults.get("denoise", 0) / 100.0,
        )
    options = EnhancementOptions(
        preset=preset,
        preset_intensity=defaults.get("intensity", 100) / 100.0,
        auto_scale=MODE_STRENGTHS[mode],
        nature_scale=1.0 if defaults else MODE_STRENGTHS[mode],
        nature_settings=nature_settings,
        white_balance=white_balance,
        levels=levels,
        local_contrast=local_contrast,
        temperature=defaults.get("temperature", 0) / 100.0,
        fade=defaults.get("fade", 0) / 100.0,
        vignette=defaults.get("vignette", 0) / 100.0,
        grain=defaults.get("grain", 0) / 100.0,
    )
    result = enhance_image(img, options)
    LOGGER.info(
        "recipe input=%s auto_white_balance=%.2f auto_levels=%.2f "
        "auto_local_contrast=%.2f shadows=%.2f highlights=%.2f vibrance=%.2f "
        "detail=%.2f denoise=%.2f color_cast=%.4f neutral_fraction=%.4f",
        input_path,
        result.auto_settings.white_balance,
        result.auto_settings.levels,
        result.auto_settings.local_contrast,
        result.nature_settings.shadows,
        result.nature_settings.highlights,
        result.nature_settings.vibrance,
        result.nature_settings.detail,
        result.nature_settings.denoise,
        result.auto_analysis.metrics.color_cast,
        result.auto_analysis.metrics.neutral_fraction,
    )
    save_bgr(
        output_path,
        result.image,
        metadata=None if strip_metadata else metadata,
        quality=quality,
    )
    if comparison_path is not None:
        comparison = build_comparison(
            img,
            result.image,
            layout=comparison_layout,
            max_panel_dimension=comparison_size,
        )
        save_bgr(comparison_path, comparison, metadata=None, quality=92)


@click.command()
@click.version_option(package_name="photo-enhance")
@click.argument("input_path", type=click.Path(exists=True, path_type=Path), required=False)
@click.option(
    "-o",
    "--output",
    "output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (single mode) or output folder (--batch mode).",
)
@click.option(
    "--preset",
    "preset_name",
    type=str,
    default=None,
    help=f"Optional nature or creative preset. Available: {', '.join(list_presets())}",
)
@click.option(
    "--preset-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Load validated JSON presets from this folder before built-ins.",
)
@click.option("--batch", is_flag=True, default=False, help="Treat input as a folder of photos.")
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help="Include nested folders in batch mode and preserve their relative paths.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Allow replacing source photos or existing output files.",
)
@click.option(
    "--strip-metadata", is_flag=True, default=False, help="Legacy shorthand for --metadata strip."
)
@click.option(
    "--metadata",
    type=click.Choice(("preserve", "strip")),
    default="preserve",
    show_default=True,
    help="Preserve supported metadata or strip it from output.",
)
@click.option(
    "--quality",
    type=click.IntRange(1, 100),
    default=None,
    metavar="1-100",
    help="JPEG/WebP output quality (defaults: JPEG 92, WebP 90).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(tuple(OUTPUT_FORMAT_SUFFIXES)),
    default=None,
    help="Force the output format and filename extension.",
)
@click.option(
    "--mode",
    type=click.Choice(tuple(MODE_STRENGTHS)),
    default="standard",
    show_default=True,
    help="Set the overall strength of automatic corrections.",
)
@click.option(
    "--white-balance/--no-white-balance", default=True, help="Enable or disable Auto white balance."
)
@click.option("--levels/--no-levels", default=True, help="Enable or disable Auto levels.")
@click.option(
    "--local-contrast/--no-local-contrast",
    default=True,
    help="Enable or disable Auto local contrast.",
)
@click.option(
    "--list-presets",
    "list_presets_requested",
    is_flag=True,
    default=False,
    help="List preset IDs, display names, and descriptions, then exit.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show selected input and output paths without reading or writing photos.",
)
@click.option(
    "--json-summary",
    is_flag=True,
    default=False,
    help="Emit one machine-readable JSON result instead of normal status lines.",
)
@click.option(
    "--comparison",
    is_flag=True,
    default=False,
    help="Also write a labeled before/after comparison JPEG.",
)
@click.option(
    "--comparison-layout",
    type=click.Choice(("horizontal", "vertical")),
    default="horizontal",
    show_default=True,
    help="Arrange the comparison panels side by side or stacked.",
)
@click.option(
    "--comparison-size",
    type=click.IntRange(320, 8000),
    default=2400,
    show_default=True,
    metavar="PIXELS",
    help="Maximum width or height of each comparison panel.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Log the measured recipe and correction strengths for each photo.",
)
def main(
    input_path: Path | None,
    output: Path | None,
    preset_name: str | None,
    preset_dir: Path | None,
    batch: bool,
    recursive: bool,
    overwrite: bool,
    strip_metadata: bool,
    metadata: str,
    quality: int | None,
    output_format: str | None,
    mode: str,
    white_balance: bool,
    levels: bool,
    local_contrast: bool,
    list_presets_requested: bool,
    dry_run: bool,
    json_summary: bool,
    comparison: bool,
    comparison_layout: str,
    comparison_size: int,
    verbose: bool,
) -> None:
    """Auto-enhance a photo (or a folder of photos with --batch)."""
    _configure_logging(verbose)
    if list_presets_requested:
        try:
            _print_presets(preset_dir)
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--preset-dir") from exc
        return
    if input_path is None:
        raise click.UsageError("Missing argument 'INPUT_PATH'.")
    if recursive and not batch:
        raise click.UsageError("--recursive requires --batch.")
    if quality is not None and output_format not in {None, "jpeg", "webp"}:
        raise click.UsageError("--quality can only be combined with --format jpeg or webp.")

    try:
        preset = load_preset(preset_name, preset_dir) if preset_name else None
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--preset") from exc
    should_strip_metadata = strip_metadata or metadata == "strip"

    if batch:
        if not input_path.is_dir():
            raise click.UsageError("--batch requires INPUT_PATH to be a folder.")
        if output is not None and output.resolve() == input_path.resolve() and not overwrite:
            raise click.UsageError(
                "Output folder is the same as the input folder, which would overwrite your "
                "source photos. Pass --overwrite to allow this, or choose a different -o."
            )
        candidates = input_path.rglob("*") if recursive else input_path.iterdir()
        output_root = output.resolve() if output is not None else None
        input_root = input_path.resolve()
        exclude_output_tree = (
            recursive
            and output_root is not None
            and output_root != input_root
            and output_root.is_relative_to(input_root)
        )
        excluded_root = output_root if exclude_output_tree else None
        entries = sorted(
            p
            for p in candidates
            if p.is_file()
            and not (excluded_root is not None and p.resolve().is_relative_to(excluded_root))
        )
        files = [p for p in entries if is_supported_image(p)]
        if not files:
            if json_summary:
                _emit_json(
                    {
                        "mode": "batch",
                        "input": str(input_path),
                        "processed": 0,
                        "skipped": len(entries),
                        "failed": 0,
                        "items": [],
                    }
                )
            else:
                click.echo(f"No supported images found in {input_path}")
            return
        processed = 0
        skipped = len(entries) - len(files)
        failed = 0
        items = []
        for index, file_path in enumerate(files, start=1):
            out_path = _output_path(
                file_path,
                output,
                is_batch=True,
                input_root=input_path if recursive and output is not None else None,
                output_format=output_format,
            )
            comparison_out = _comparison_path(out_path) if comparison else None
            existing_path = next(
                (path for path in (out_path, comparison_out) if path is not None and path.exists()),
                None,
            )
            if existing_path is not None and not overwrite:
                skipped += 1
                items.append(
                    {
                        "input": str(file_path),
                        "output": str(out_path),
                        **(
                            {"comparison": str(comparison_out)}
                            if comparison_out is not None
                            else {}
                        ),
                        "status": "skipped",
                        "error": "output already exists",
                    }
                )
                _echo_batch(
                    f"SKIP {file_path.name} (output already exists: {existing_path})",
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
                continue
            if dry_run:
                processed += 1
                items.append(
                    {
                        "input": str(file_path),
                        "output": str(out_path),
                        **(
                            {"comparison": str(comparison_out)}
                            if comparison_out is not None
                            else {}
                        ),
                        "status": "planned",
                    }
                )
                _echo_batch(
                    f"DRY  {file_path.name} -> {out_path}"
                    + (f" + {comparison_out}" if comparison_out is not None else ""),
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
                continue
            try:
                _process_one(
                    file_path,
                    out_path,
                    preset,
                    strip_metadata=should_strip_metadata,
                    quality=quality,
                    mode=mode,
                    white_balance=white_balance,
                    levels=levels,
                    local_contrast=local_contrast,
                    comparison_path=comparison_out,
                    comparison_layout=comparison_layout,
                    comparison_size=comparison_size,
                )
                processed += 1
                items.append(
                    {
                        "input": str(file_path),
                        "output": str(out_path),
                        **(
                            {"comparison": str(comparison_out)}
                            if comparison_out is not None
                            else {}
                        ),
                        "status": "processed",
                    }
                )
                _echo_batch(
                    f"OK   {file_path.name} -> {out_path}"
                    + (f" + {comparison_out}" if comparison_out is not None else ""),
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
            except KeyboardInterrupt:
                if not json_summary:
                    click.echo("Interrupted; the current output was not installed.", err=True)
                raise click.exceptions.Exit(130) from None
            except PROCESSING_ERRORS as exc:
                failed += 1
                items.append(
                    {
                        "input": str(file_path),
                        "output": str(out_path),
                        **(
                            {"comparison": str(comparison_out)}
                            if comparison_out is not None
                            else {}
                        ),
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                _echo_batch(
                    f"FAIL {file_path.name} ({exc})",
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
        if json_summary:
            _emit_json(
                {
                    "mode": "batch",
                    "input": str(input_path),
                    "processed": processed,
                    "skipped": skipped,
                    "failed": failed,
                    "items": items,
                }
            )
        else:
            click.echo(f"Summary: {processed} processed, {skipped} skipped, {failed} failed")
        if failed:
            raise click.exceptions.Exit(1)
    else:
        if not input_path.is_file():
            raise click.UsageError("INPUT_PATH must be a file (use --batch for a folder).")
        out_path = _output_path(
            input_path,
            output,
            is_batch=False,
            output_format=output_format,
        )
        comparison_out = _comparison_path(out_path) if comparison else None
        if out_path.resolve() == input_path.resolve() and not overwrite:
            raise click.UsageError(
                "Output path is the same as the input file, which would overwrite the original. "
                "Pass --overwrite to allow this, or choose a different -o."
            )
        existing_path = next(
            (path for path in (out_path, comparison_out) if path is not None and path.exists()),
            None,
        )
        if existing_path is not None and not overwrite:
            raise click.UsageError(
                f"Output already exists: {existing_path}. Pass --overwrite to replace it, "
                "or choose a different -o."
            )
        if dry_run:
            if json_summary:
                _emit_json(
                    {
                        "mode": "single",
                        "input": str(input_path),
                        "output": str(out_path),
                        **(
                            {"comparison": str(comparison_out)}
                            if comparison_out is not None
                            else {}
                        ),
                        "status": "planned",
                    }
                )
            else:
                click.echo(
                    f"DRY  {input_path.name} -> {out_path}"
                    + (f" + {comparison_out}" if comparison_out is not None else "")
                )
            return
        try:
            _process_one(
                input_path,
                out_path,
                preset,
                strip_metadata=should_strip_metadata,
                quality=quality,
                mode=mode,
                white_balance=white_balance,
                levels=levels,
                local_contrast=local_contrast,
                comparison_path=comparison_out,
                comparison_layout=comparison_layout,
                comparison_size=comparison_size,
            )
        except KeyboardInterrupt:
            if not json_summary:
                click.echo("Interrupted; the output was not installed.", err=True)
            raise click.exceptions.Exit(130) from None
        except PROCESSING_ERRORS as exc:
            raise click.ClickException(str(exc)) from exc
        if json_summary:
            _emit_json(
                {
                    "mode": "single",
                    "input": str(input_path),
                    "output": str(out_path),
                    **({"comparison": str(comparison_out)} if comparison_out is not None else {}),
                    "status": "processed",
                }
            )
        else:
            click.echo(
                f"OK   {input_path.name} -> {out_path}"
                + (f" + {comparison_out}" if comparison_out is not None else "")
            )


if __name__ == "__main__":
    main()
