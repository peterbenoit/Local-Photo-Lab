import numpy as np

from photo_enhance.finishing import apply_finishing


def test_zero_finishing_is_a_noop_without_mutating_input():
    image = np.full((32, 32, 3), 128, dtype=np.uint8)

    result = apply_finishing(image)

    assert np.array_equal(result, image)
    assert result is not image


def test_vignette_darkens_edges_while_preserving_center():
    image = np.full((101, 101, 3), 200, dtype=np.uint8)

    result = apply_finishing(image, vignette=1.0)

    assert result[0, 0].mean() < 80
    assert result[50, 50].mean() == 200


def test_grain_is_visible_and_deterministic_for_a_session_seed():
    image = np.full((64, 64, 3), 128, dtype=np.uint8)

    first = apply_finishing(image, grain=0.6, grain_seed=42)
    second = apply_finishing(image, grain=0.6, grain_seed=42)

    assert first.std() > 3
    assert np.array_equal(first, second)
    assert np.array_equal(first[:, :, 0], first[:, :, 1])
    assert first.dtype == np.uint8


def test_temperature_shifts_red_and_blue_channels_in_opposite_directions():
    image = np.full((16, 16, 3), 128, dtype=np.uint8)

    warm = apply_finishing(image, temperature=1.0)
    cool = apply_finishing(image, temperature=-1.0)

    assert warm[:, :, 2].mean() > warm[:, :, 0].mean()
    assert cool[:, :, 0].mean() > cool[:, :, 2].mean()
    assert np.all(warm[:, :, 1] == 128)
    assert np.all(cool[:, :, 1] == 128)


def test_fade_lifts_blacks_and_softens_whites():
    image = np.zeros((8, 16, 3), dtype=np.uint8)
    image[:, 8:] = 255

    result = apply_finishing(image, fade=1.0)

    assert result[:, :8].mean() > 0
    assert result[:, 8:].mean() < 255
