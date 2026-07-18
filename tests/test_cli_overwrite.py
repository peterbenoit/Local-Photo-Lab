import json

import cv2
import numpy as np
from click.testing import CliRunner
from PIL import Image

from photo_enhance.cli import main


def _write_test_image(path) -> None:
    x = np.linspace(20, 220, 16, dtype=np.uint8)
    img = np.dstack(
        [
            np.tile(x, (16, 1)),
            np.full((16, 16), 100, dtype=np.uint8),
            np.tile(x[:, np.newaxis], (1, 16)),
        ]
    )
    cv2.imwrite(str(path), img)


def test_single_file_uses_default_output_name(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    result = CliRunner().invoke(main, [str(photo)])

    output = tmp_path / "photo_enhanced.jpg"
    assert result.exit_code == 0
    assert f"OK   photo.jpg -> {output}" in result.output
    assert output.is_file()


def test_single_file_writes_custom_output(tmp_path):
    photo = tmp_path / "photo.jpg"
    output = tmp_path / "custom.webp"
    _write_test_image(photo)

    result = CliRunner().invoke(main, [str(photo), "-o", str(output), "--quality", "83"])

    assert result.exit_code == 0
    assert output.is_file()
    with Image.open(output) as saved:
        assert saved.format == "WEBP"


def test_output_format_rewrites_extension_and_encodes_requested_format(tmp_path):
    photo = tmp_path / "photo.jpg"
    requested = tmp_path / "export.anything"
    _write_test_image(photo)

    result = CliRunner().invoke(
        main,
        [str(photo), "-o", str(requested), "--format", "png"],
    )

    output = requested.with_suffix(".png")
    assert result.exit_code == 0
    assert output.is_file()
    assert not requested.exists()
    with Image.open(output) as saved:
        assert saved.format == "PNG"


def test_quality_rejects_incompatible_forced_format(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    result = CliRunner().invoke(
        main,
        [str(photo), "--format", "png", "--quality", "90"],
    )

    assert result.exit_code == 2
    assert "--quality can only be combined with --format jpeg or webp" in result.output


def test_single_file_applies_selected_preset(tmp_path):
    photo = tmp_path / "photo.jpg"
    plain_output = tmp_path / "plain.png"
    preset_output = tmp_path / "preset.png"
    _write_test_image(photo)

    runner = CliRunner()
    plain = runner.invoke(main, [str(photo), "-o", str(plain_output)])
    preset = runner.invoke(
        main,
        [str(photo), "-o", str(preset_output), "--preset", "high_contrast_bw"],
    )

    assert plain.exit_code == 0
    assert preset.exit_code == 0
    plain_pixels = cv2.imread(str(plain_output))
    preset_pixels = cv2.imread(str(preset_output))
    assert not np.array_equal(plain_pixels, preset_pixels)
    assert np.array_equal(preset_pixels[..., 0], preset_pixels[..., 1])
    assert np.array_equal(preset_pixels[..., 1], preset_pixels[..., 2])


def test_strength_modes_produce_different_bounded_results(tmp_path):
    photo = tmp_path / "photo.jpg"
    gentle_output = tmp_path / "gentle.png"
    strong_output = tmp_path / "strong.png"
    _write_test_image(photo)

    runner = CliRunner()
    gentle = runner.invoke(
        main,
        [str(photo), "-o", str(gentle_output), "--mode", "gentle"],
    )
    strong = runner.invoke(
        main,
        [str(photo), "-o", str(strong_output), "--mode", "strong"],
    )

    assert gentle.exit_code == 0
    assert strong.exit_code == 0
    assert not np.array_equal(cv2.imread(str(gentle_output)), cv2.imread(str(strong_output)))


def test_individual_auto_stages_can_be_disabled(tmp_path, monkeypatch):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)
    received = {}

    from photo_enhance import cli

    def capture_options(_input_path, _output_path, _preset, **kwargs):
        received.update(kwargs)

    monkeypatch.setattr(cli, "_process_one", capture_options)

    result = CliRunner().invoke(
        main,
        [
            str(photo),
            "--no-white-balance",
            "--no-levels",
            "--no-local-contrast",
        ],
    )

    assert result.exit_code == 0
    assert received["white_balance"] is False
    assert received["levels"] is False
    assert received["local_contrast"] is False


def test_missing_input_path_is_rejected_by_click(tmp_path):
    missing = tmp_path / "missing.jpg"

    result = CliRunner().invoke(main, [str(missing)])

    assert result.exit_code == 2
    assert "Path" in result.output
    assert "does not exist" in result.output


def test_list_presets_does_not_require_an_input_path():
    result = CliRunner().invoke(main, ["--list-presets"])

    assert result.exit_code == 0
    assert "bird_natural: Bird Natural" in result.output
    assert "Faithful plumage color" in result.output
    assert "warm_film: Warm Film" in result.output


def test_dry_run_reports_single_output_without_reading_or_writing(tmp_path):
    photo = tmp_path / "not-actually-an-image.jpg"
    output = tmp_path / "planned" / "result.jpg"
    photo.write_text("dry run should not decode this")

    result = CliRunner().invoke(main, [str(photo), "-o", str(output), "--dry-run"])

    assert result.exit_code == 0
    assert result.output == f"DRY  {photo.name} -> {output}\n"
    assert not output.parent.exists()


def test_batch_dry_run_reports_supported_files_without_creating_output(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "one.jpg").write_text("planning only")
    (input_dir / "notes.txt").write_text("unsupported")

    result = CliRunner().invoke(
        main,
        [str(input_dir), "--batch", "-o", str(output_dir), "--dry-run"],
    )

    assert result.exit_code == 0
    assert f"DRY  one.jpg -> {output_dir / 'one.jpg'}" in result.output
    assert "Summary: 1 processed, 1 skipped, 0 failed" in result.output
    assert not output_dir.exists()


def test_recursive_batch_preserves_relative_directories_and_ignores_output_tree(tmp_path):
    input_dir = tmp_path / "input"
    nested_dir = input_dir / "year" / "trip"
    output_dir = input_dir / "enhanced"
    nested_dir.mkdir(parents=True)
    output_dir.mkdir()
    _write_test_image(nested_dir / "bird.jpg")
    _write_test_image(output_dir / "old.jpg")

    result = CliRunner().invoke(
        main,
        [str(input_dir), "--batch", "--recursive", "-o", str(output_dir)],
    )

    assert result.exit_code == 0
    assert (output_dir / "year" / "trip" / "bird.jpg").is_file()
    assert not (output_dir / "enhanced" / "old.jpg").exists()
    assert "Summary: 1 processed, 0 skipped, 0 failed" in result.output


def test_recursive_requires_batch_mode(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    result = CliRunner().invoke(main, [str(photo), "--recursive"])

    assert result.exit_code == 2
    assert "--recursive requires --batch" in result.output


def test_folder_requires_batch_flag(tmp_path):
    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 2
    assert "INPUT_PATH must be a file" in result.output


def test_batch_requires_folder_input(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    result = CliRunner().invoke(main, [str(photo), "--batch"])

    assert result.exit_code == 2
    assert "--batch requires INPUT_PATH to be a folder" in result.output


def test_empty_batch_reports_no_supported_images_without_creating_output(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    result = CliRunner().invoke(main, [str(input_dir), "--batch", "-o", str(output_dir)])

    assert result.exit_code == 0
    assert result.output == f"No supported images found in {input_dir}\n"
    assert not output_dir.exists()


def test_single_file_refuses_to_overwrite_input_by_default(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    runner = CliRunner()
    result = runner.invoke(main, [str(photo), "-o", str(photo)])

    assert result.exit_code != 0
    assert "overwrite" in result.output.lower()


def test_single_file_overwrite_flag_allows_it(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    runner = CliRunner()
    result = runner.invoke(main, [str(photo), "-o", str(photo), "--overwrite"])

    assert result.exit_code == 0


def test_batch_refuses_output_dir_matching_input_dir_by_default(tmp_path):
    _write_test_image(tmp_path / "photo.jpg")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--batch", "-o", str(tmp_path)])

    assert result.exit_code != 0
    assert "overwrite" in result.output.lower()


def test_batch_overwrite_flag_allows_matching_output_dir(tmp_path):
    _write_test_image(tmp_path / "photo.jpg")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--batch", "-o", str(tmp_path), "--overwrite"])

    assert result.exit_code == 0


def test_single_file_refuses_to_replace_existing_output_by_default(tmp_path):
    photo = tmp_path / "photo.jpg"
    output = tmp_path / "existing.jpg"
    _write_test_image(photo)
    output.write_bytes(b"keep me")

    result = CliRunner().invoke(main, [str(photo), "-o", str(output)])

    assert result.exit_code != 0
    assert "already exists" in result.output.lower()
    assert output.read_bytes() == b"keep me"


def test_single_file_overwrite_flag_replaces_existing_output(tmp_path):
    photo = tmp_path / "photo.jpg"
    output = tmp_path / "existing.jpg"
    _write_test_image(photo)
    output.write_bytes(b"replace me")

    result = CliRunner().invoke(main, [str(photo), "-o", str(output), "--overwrite"])

    assert result.exit_code == 0
    assert output.read_bytes() != b"replace me"


def test_batch_skips_existing_outputs_and_prints_summary(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    _write_test_image(input_dir / "one.jpg")
    _write_test_image(input_dir / "two.jpg")
    (input_dir / "notes.txt").write_text("not an image")
    (output_dir / "one.jpg").write_bytes(b"keep me")

    result = CliRunner().invoke(main, [str(input_dir), "--batch", "-o", str(output_dir)])

    assert result.exit_code == 0
    assert "1 processed, 2 skipped, 0 failed" in result.output
    assert (output_dir / "one.jpg").read_bytes() == b"keep me"
    assert (output_dir / "two.jpg").exists()


def test_batch_failure_returns_nonzero_and_continues(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_test_image(input_dir / "bad.jpg")
    _write_test_image(input_dir / "good.jpg")

    from photo_enhance import cli

    real_process_one = cli._process_one

    def fail_one(input_path, output_path, preset, **kwargs):
        if input_path.name == "bad.jpg":
            raise OSError("simulated write failure")
        real_process_one(input_path, output_path, preset, **kwargs)

    monkeypatch.setattr(cli, "_process_one", fail_one)

    result = CliRunner().invoke(main, [str(input_dir), "--batch", "-o", str(output_dir)])

    assert result.exit_code == 1
    assert "FAIL bad.jpg" in result.output
    assert "1 processed, 0 skipped, 1 failed" in result.output
    assert (output_dir / "good.jpg").exists()


def test_batch_json_summary_is_machine_readable_and_suppresses_status_lines(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_test_image(input_dir / "photo.jpg")

    result = CliRunner().invoke(
        main,
        [str(input_dir), "--batch", "-o", str(output_dir), "--json-summary"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["processed"] == 1
    assert payload["failed"] == 0
    assert payload["items"][0]["status"] == "processed"
    assert "OK   " not in result.output


def test_keyboard_interrupt_exits_130(tmp_path, monkeypatch):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    from photo_enhance import cli

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_process_one", interrupt)

    result = CliRunner().invoke(main, [str(photo)])

    assert result.exit_code == 130
    assert "output was not installed" in result.output
    assert not (tmp_path / "photo_enhanced.jpg").exists()


def test_unknown_preset_is_rejected_by_click(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    result = CliRunner().invoke(main, [str(photo), "--preset", "not-real"])

    assert result.exit_code != 0
    assert "invalid value for '--preset'" in result.output.lower()


def test_strip_metadata_removes_exif(tmp_path):
    photo = tmp_path / "photo.jpg"
    output = tmp_path / "enhanced.jpg"
    image = Image.new("RGB", (16, 16), (120, 120, 120))
    exif = Image.Exif()
    exif[315] = "Test Artist"
    image.save(photo, exif=exif)

    result = CliRunner().invoke(main, [str(photo), "-o", str(output), "--strip-metadata"])

    assert result.exit_code == 0
    with Image.open(output) as saved:
        assert not saved.getexif()


def test_metadata_strip_policy_removes_exif(tmp_path):
    photo = tmp_path / "photo.jpg"
    output = tmp_path / "enhanced.jpg"
    image = Image.new("RGB", (16, 16), (120, 120, 120))
    exif = Image.Exif()
    exif[315] = "Test Artist"
    image.save(photo, exif=exif)

    result = CliRunner().invoke(
        main,
        [str(photo), "-o", str(output), "--metadata", "strip"],
    )

    assert result.exit_code == 0
    with Image.open(output) as saved:
        assert not saved.getexif()


def test_quality_is_validated_by_click(tmp_path):
    photo = tmp_path / "photo.jpg"
    _write_test_image(photo)

    result = CliRunner().invoke(main, [str(photo), "--quality", "101"])

    assert result.exit_code != 0
    assert "101 is not in the range 1<=x<=100" in result.output


def test_unsupported_transparency_returns_friendly_cli_error(tmp_path):
    photo = tmp_path / "transparent.png"
    Image.new("RGBA", (8, 8), (100, 120, 140, 100)).save(photo)

    result = CliRunner().invoke(main, [str(photo)])

    assert result.exit_code != 0
    assert "Error: Transparent images are not supported yet" in result.output
    assert result.exception is not None
