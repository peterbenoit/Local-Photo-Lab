"""CLI entry point: enhance <input> [-o output] [--preset name] [--batch]"""

import json
from pathlib import Path

import click
import cv2
from PIL import Image, UnidentifiedImageError

from photo_enhance.auto_levels import AutoSettings, analyze_auto, auto_enhance
from photo_enhance.imageio_utils import is_supported_image, load_bgr, save_bgr
from photo_enhance.nature import NatureSettings, analyze_nature, apply_nature_adjustments
from photo_enhance.presets import (
    apply_preset,
    apply_preset_with_defaults,
    list_presets,
    list_preset_choices,
    load_preset,
)

PROCESSING_ERRORS = (
    OSError,
    ValueError,
    cv2.error,
    UnidentifiedImageError,
    Image.DecompressionBombError,
)

OUTPUT_FORMAT_SUFFIXES = {
    "jpeg": ".jpg",
    "png": ".png",
    "tiff": ".tiff",
    "bmp": ".bmp",
    "webp": ".webp",
}

MODE_STRENGTHS = {"gentle": 0.65, "standard": 1.0, "strong": 1.25}


def _bounded_scale(value: float, scale: float) -> float:
    return min(1.0, max(0.0, value * scale))


def _auto_settings_for_cli(
    settings: AutoSettings,
    *,
    mode: str,
    white_balance: bool,
    levels: bool,
    local_contrast: bool,
) -> AutoSettings:
    scale = MODE_STRENGTHS[mode]
    return AutoSettings(
        white_balance=_bounded_scale(settings.white_balance, scale) if white_balance else 0.0,
        levels=_bounded_scale(settings.levels, scale) if levels else 0.0,
        local_contrast=_bounded_scale(settings.local_contrast, scale) if local_contrast else 0.0,
    )


def _nature_settings_for_cli(settings: NatureSettings, *, mode: str) -> NatureSettings:
    scale = MODE_STRENGTHS[mode]
    return NatureSettings(
        shadows=_bounded_scale(settings.shadows, scale),
        highlights=_bounded_scale(settings.highlights, scale),
        vibrance=_bounded_scale(settings.vibrance, scale),
        detail=_bounded_scale(settings.detail, scale),
        denoise=_bounded_scale(settings.denoise, scale),
    )


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


def _print_presets() -> None:
    """Print stable preset IDs alongside the names and descriptions people see in the UI."""
    for preset in list_preset_choices():
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
    preset: dict | None,
    *,
    strip_metadata: bool = False,
    quality: int | None = None,
    mode: str = "standard",
    white_balance: bool = True,
    levels: bool = True,
    local_contrast: bool = True,
) -> None:
    img, metadata = load_bgr(input_path)
    auto_analysis = analyze_auto(img)
    auto_settings = _auto_settings_for_cli(
        auto_analysis.settings,
        mode=mode,
        white_balance=white_balance,
        levels=levels,
        local_contrast=local_contrast,
    )
    base = auto_enhance(img, settings=auto_settings)
    nature = _nature_settings_for_cli(analyze_nature(base), mode=mode)
    if preset is not None and preset.get("defaults"):
        # Nature presets intentionally replace Auto's nature-stage recommendations.
        result = apply_preset_with_defaults(base, preset)
    else:
        result = apply_preset(base, preset) if preset is not None else base
        result = apply_nature_adjustments(
            result,
            shadows=nature.shadows,
            highlights=nature.highlights,
            vibrance=nature.vibrance,
            detail=nature.detail,
            denoise=nature.denoise,
        )
    save_bgr(output_path, result, metadata=None if strip_metadata else metadata, quality=quality)


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-o", "--output", "output", type=click.Path(path_type=Path), default=None,
              help="Output file (single mode) or output folder (--batch mode).")
@click.option("--preset", "preset_name", type=click.Choice(list_presets()), default=None,
              help=f"Optional nature or creative preset. Available: {', '.join(list_presets())}")
@click.option("--batch", is_flag=True, default=False, help="Treat input as a folder of photos.")
@click.option("--recursive", is_flag=True, default=False,
              help="Include nested folders in batch mode and preserve their relative paths.")
@click.option("--overwrite", is_flag=True, default=False,
              help="Allow replacing source photos or existing output files.")
@click.option("--strip-metadata", is_flag=True, default=False,
              help="Legacy shorthand for --metadata strip.")
@click.option("--metadata", type=click.Choice(("preserve", "strip")), default="preserve",
              show_default=True, help="Preserve supported metadata or strip it from output.")
@click.option("--quality", type=click.IntRange(1, 100), default=None, metavar="1-100",
              help="JPEG/WebP output quality (defaults: JPEG 92, WebP 90).")
@click.option("--format", "output_format", type=click.Choice(tuple(OUTPUT_FORMAT_SUFFIXES)),
              default=None, help="Force the output format and filename extension.")
@click.option("--mode", type=click.Choice(tuple(MODE_STRENGTHS)), default="standard",
              show_default=True, help="Set the overall strength of automatic corrections.")
@click.option("--white-balance/--no-white-balance", default=True,
              help="Enable or disable Auto white balance.")
@click.option("--levels/--no-levels", default=True,
              help="Enable or disable Auto levels.")
@click.option("--local-contrast/--no-local-contrast", default=True,
              help="Enable or disable Auto local contrast.")
@click.option("--list-presets", "list_presets_requested", is_flag=True, default=False,
              help="List preset IDs, display names, and descriptions, then exit.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show selected input and output paths without reading or writing photos.")
@click.option("--json-summary", is_flag=True, default=False,
              help="Emit one machine-readable JSON result instead of normal status lines.")
def main(
    input_path: Path | None,
    output: Path | None,
    preset_name: str | None,
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
) -> None:
    """Auto-enhance a photo (or a folder of photos with --batch)."""
    if list_presets_requested:
        _print_presets()
        return
    if input_path is None:
        raise click.UsageError("Missing argument 'INPUT_PATH'.")
    if recursive and not batch:
        raise click.UsageError("--recursive requires --batch.")
    if quality is not None and output_format not in {None, "jpeg", "webp"}:
        raise click.UsageError("--quality can only be combined with --format jpeg or webp.")

    preset = load_preset(preset_name) if preset_name else None
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
        entries = sorted(
            p
            for p in candidates
            if p.is_file()
            and not (
                exclude_output_tree
                and p.resolve().is_relative_to(output_root)
            )
        )
        files = [p for p in entries if is_supported_image(p)]
        if not files:
            if json_summary:
                _emit_json({
                    "mode": "batch",
                    "input": str(input_path),
                    "processed": 0,
                    "skipped": len(entries),
                    "failed": 0,
                    "items": [],
                })
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
            if out_path.exists() and not overwrite:
                skipped += 1
                items.append({
                    "input": str(file_path),
                    "output": str(out_path),
                    "status": "skipped",
                    "error": "output already exists",
                })
                _echo_batch(
                    f"SKIP {file_path.name} (output already exists: {out_path})",
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
                continue
            if dry_run:
                processed += 1
                items.append({
                    "input": str(file_path),
                    "output": str(out_path),
                    "status": "planned",
                })
                _echo_batch(
                    f"DRY  {file_path.name} -> {out_path}",
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
                )
                processed += 1
                items.append({
                    "input": str(file_path),
                    "output": str(out_path),
                    "status": "processed",
                })
                _echo_batch(
                    f"OK   {file_path.name} -> {out_path}",
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
            except KeyboardInterrupt:
                if not json_summary:
                    click.echo("Interrupted; the current output was not installed.", err=True)
                raise click.exceptions.Exit(130)
            except PROCESSING_ERRORS as exc:
                failed += 1
                items.append({
                    "input": str(file_path),
                    "output": str(out_path),
                    "status": "failed",
                    "error": str(exc),
                })
                _echo_batch(
                    f"FAIL {file_path.name} ({exc})",
                    index=index,
                    total=len(files),
                    json_summary=json_summary,
                )
        if json_summary:
            _emit_json({
                "mode": "batch",
                "input": str(input_path),
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "items": items,
            })
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
        if out_path.resolve() == input_path.resolve() and not overwrite:
            raise click.UsageError(
                "Output path is the same as the input file, which would overwrite the original. "
                "Pass --overwrite to allow this, or choose a different -o."
            )
        if out_path.exists() and not overwrite:
            raise click.UsageError(
                f"Output already exists: {out_path}. Pass --overwrite to replace it, "
                "or choose a different -o."
            )
        if dry_run:
            if json_summary:
                _emit_json({
                    "mode": "single",
                    "input": str(input_path),
                    "output": str(out_path),
                    "status": "planned",
                })
            else:
                click.echo(f"DRY  {input_path.name} -> {out_path}")
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
            )
        except KeyboardInterrupt:
            if not json_summary:
                click.echo("Interrupted; the output was not installed.", err=True)
            raise click.exceptions.Exit(130)
        except PROCESSING_ERRORS as exc:
            raise click.ClickException(str(exc)) from exc
        if json_summary:
            _emit_json({
                "mode": "single",
                "input": str(input_path),
                "output": str(out_path),
                "status": "processed",
            })
        else:
            click.echo(f"OK   {input_path.name} -> {out_path}")


if __name__ == "__main__":
    main()
