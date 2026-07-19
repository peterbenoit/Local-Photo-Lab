"""Build labeled before/after comparison images for web and CLI exports."""

import cv2
import numpy as np


def _validate_image(name: str, image: np.ndarray) -> None:
    if (
        not isinstance(image, np.ndarray)
        or image.ndim != 3
        or image.shape[2] != 3
        or image.shape[0] == 0
        or image.shape[1] == 0
        or image.dtype != np.uint8
    ):
        raise ValueError(f"{name} must be a non-empty BGR uint8 image")


def build_comparison(
    before: np.ndarray,
    after: np.ndarray,
    *,
    layout: str = "horizontal",
    max_panel_dimension: int = 2400,
) -> np.ndarray:
    """Return a labeled horizontal or vertical comparison image."""
    _validate_image("before", before)
    _validate_image("after", after)
    if layout not in {"horizontal", "vertical"}:
        raise ValueError("layout must be horizontal or vertical")
    if (
        isinstance(max_panel_dimension, bool)
        or not isinstance(max_panel_dimension, int)
        or max_panel_dimension <= 0
    ):
        raise ValueError("max_panel_dimension must be a positive integer")

    before_panel = before
    after_panel = after
    if before_panel.shape[:2] != after_panel.shape[:2]:
        after_panel = cv2.resize(
            after_panel,
            (before_panel.shape[1], before_panel.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    height, width = before_panel.shape[:2]
    scale = min(1.0, max_panel_dimension / max(height, width))
    if scale < 1.0:
        panel_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        before_panel = cv2.resize(before_panel, panel_size, interpolation=cv2.INTER_AREA)
        after_panel = cv2.resize(after_panel, panel_size, interpolation=cv2.INTER_AREA)
        height, width = before_panel.shape[:2]

    header_height = 48
    gap = 12
    background = (15, 17, 20)
    label_color = (234, 242, 245)
    if layout == "horizontal":
        canvas = np.full(
            (height + header_height, width * 2 + gap, 3),
            background,
            dtype=np.uint8,
        )
        canvas[header_height:, :width] = before_panel
        canvas[header_height:, width + gap :] = after_panel
        label_positions = (("BEFORE", (14, 32)), ("AFTER", (width + gap + 14, 32)))
    else:
        second_header = header_height + height + gap
        canvas = np.full(
            (height * 2 + header_height * 2 + gap, width, 3),
            background,
            dtype=np.uint8,
        )
        canvas[header_height : header_height + height] = before_panel
        canvas[second_header + header_height :] = after_panel
        label_positions = (("BEFORE", (14, 32)), ("AFTER", (14, second_header + 32)))

    for label, position in label_positions:
        cv2.putText(
            canvas,
            label,
            position,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            label_color,
            2,
            cv2.LINE_AA,
        )
    return canvas
