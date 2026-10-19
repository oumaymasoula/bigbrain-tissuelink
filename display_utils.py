"""Display-only adapters for scientific image views."""
from __future__ import annotations

import numpy as np


def _display_grayscale(view: np.ndarray) -> np.ndarray:
    """Convert display input to 2-D only; never mutate source data."""
    array = np.asarray(view)
    if array.ndim == 3 and 1 in array.shape:
        array = np.squeeze(array)
    if array.ndim != 2:
        raise ValueError(f"display overlay requires a 2-D grayscale array; got shape {array.shape}")
    return array


def _display_rgb(view: np.ndarray) -> np.ndarray:
    """Return RGB display pixels without changing source values or geometry.

    Grayscale inputs are replicated into three display channels. RGB/RGBA
    inputs retain their first three channels. This is strictly a rendering
    adapter: scientific arrays and affines remain untouched.
    """
    array = np.asarray(view)
    if array.ndim == 3 and 1 in array.shape:
        array = np.squeeze(array)
    if array.ndim == 2:
        return np.repeat(array[..., None], 3, axis=2).astype(np.uint8)
    if array.ndim == 3 and array.shape[2] in (3, 4):
        return np.asarray(array[..., :3], dtype=np.uint8)
    raise ValueError(f"display image requires 2-D grayscale or RGB/RGBA input; got shape {array.shape}")


def rgb_with_crosshair(view: np.ndarray, u: int, v: int, colour=(255, 255, 0)) -> np.ndarray:
    """Overlay a display marker on grayscale or RGB/RGBA pixels."""
    result = _display_rgb(view).copy()
    if 0 <= u < result.shape[1]:
        result[:, u] = colour
    if 0 <= v < result.shape[0]:
        result[v, :] = colour
    return result


def has_intensity_variation(data: np.ndarray) -> bool:
    """Return whether a fetched scientific array contains finite variation."""
    array = np.asarray(data)
    return bool(array.size and np.all(np.isfinite(array)) and np.ptp(array) > 0)
