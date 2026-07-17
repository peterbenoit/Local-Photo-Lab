"""Optional finishing effects applied after auto-enhancement and creative presets."""

import numpy as np


_CHUNK_ROWS = 128


def _validate_image(img: np.ndarray) -> None:
    if not isinstance(img, np.ndarray):
        raise TypeError("img must be a NumPy array")
    if img.ndim != 3 or img.shape[2] != 3 or img.shape[0] == 0 or img.shape[1] == 0:
        raise ValueError("img must have non-empty shape (height, width, 3)")
    if img.dtype != np.uint8:
        raise ValueError("img must use uint8 pixels in the 0-255 range")


def _validate_strength(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite number from 0 to 1")
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be from 0 to 1")
    return float(value)


def _validate_signed_strength(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite number from -1 to 1")
    if not -1 <= value <= 1:
        raise ValueError(f"{name} must be from -1 to 1")
    return float(value)


def apply_finishing(
    img: np.ndarray,
    *,
    temperature: float = 0.0,
    fade: float = 0.0,
    vignette: float = 0.0,
    grain: float = 0.0,
    grain_seed: int = 0,
) -> np.ndarray:
    """Apply bounded color and texture finishing to a BGR uint8 image.

    Work is performed in row chunks to avoid allocating full-resolution float
    masks or noise arrays for large accepted web images.
    """
    _validate_image(img)
    temperature = _validate_signed_strength("temperature", temperature)
    fade = _validate_strength("fade", fade)
    vignette = _validate_strength("vignette", vignette)
    grain = _validate_strength("grain", grain)
    if isinstance(grain_seed, bool) or not isinstance(grain_seed, int):
        raise ValueError("grain_seed must be an integer")

    result = img.copy()
    height, width = result.shape[:2]

    if temperature != 0 or fade > 0:
        channel_scale = np.array(
            [1.0 - 0.18 * temperature, 1.0, 1.0 + 0.18 * temperature],
            dtype=np.float32,
        )
        contrast = 1.0 - 0.18 * fade
        black_lift = 20.0 * fade
        for start in range(0, height, _CHUNK_ROWS):
            stop = min(start + _CHUNK_ROWS, height)
            stripe = result[start:stop].astype(np.float32)
            stripe = stripe * channel_scale
            stripe = stripe * contrast + black_lift
            result[start:stop] = np.clip(stripe, 0, 255).astype(np.uint8)

    if vignette > 0:
        x_squared = np.linspace(-1.0, 1.0, width, dtype=np.float32) ** 2
        y_positions = np.linspace(-1.0, 1.0, height, dtype=np.float32)
        for start in range(0, height, _CHUNK_ROWS):
            stop = min(start + _CHUNK_ROWS, height)
            radius = np.sqrt(
                (y_positions[start:stop, np.newaxis] ** 2 + x_squared[np.newaxis, :]) / 2.0
            )
            falloff = np.clip((radius - 0.12) / 0.88, 0.0, 1.0) ** 1.6
            mask = 1.0 - vignette * 0.7 * falloff
            stripe = result[start:stop].astype(np.float32)
            result[start:stop] = np.clip(stripe * mask[:, :, np.newaxis], 0, 255).astype(
                np.uint8
            )

    if grain > 0:
        rng = np.random.default_rng(grain_seed)
        sigma = 18.0 * grain
        for start in range(0, height, _CHUNK_ROWS):
            stop = min(start + _CHUNK_ROWS, height)
            noise = rng.normal(0.0, sigma, size=(stop - start, width, 1)).astype(np.float32)
            stripe = result[start:stop].astype(np.float32)
            result[start:stop] = np.clip(stripe + noise, 0, 255).astype(np.uint8)

    return result
