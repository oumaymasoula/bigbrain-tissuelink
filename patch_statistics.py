"""Descriptive statistics for one scientific detailed-patch plane.

These metrics describe stored intensity values only.  They are not tissue
quality, cell-density, tissue-fraction, tear, fold, or anatomical-validity
measurements.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np


STATISTICS_VERSION = "1.0"
DEFAULT_DECLARED_PADDING_VALUES = (255,)


def _plane_candidates(data: np.ndarray, declared_padding_values: tuple[float, ...]) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for y in range(data.shape[1]):
        plane = np.asarray(data[:, y, :])
        finite = np.isfinite(plane)
        usable = finite & ~np.isin(plane, declared_padding_values)
        count = int(np.count_nonzero(usable))
        variation = float(np.ptp(plane[usable])) if count else 0.0
        candidates.append((count, variation))
    return candidates


def choose_valid_plane(
    data: np.ndarray,
    preferred_y: int | None = None,
    declared_padding_values: Iterable[float] = DEFAULT_DECLARED_PADDING_VALUES,
) -> int:
    """Choose a non-padding Y plane, preferring the renderer's selected plane.

    A preferred plane is accepted only when it has finite non-padding values.
    Otherwise the plane with the most usable pixels and then greatest range is
    selected.  This excludes known provider padding without modifying data.
    """
    array = np.asarray(data)
    if array.ndim != 3 or array.shape[1] == 0:
        raise ValueError(f"patch statistics require a non-empty 3-D array; got {array.shape}")
    padding = tuple(float(value) for value in declared_padding_values)
    candidates = _plane_candidates(array, padding)
    if preferred_y is not None and 0 <= int(preferred_y) < array.shape[1] and candidates[int(preferred_y)][0] > 0:
        return int(preferred_y)
    return max(range(array.shape[1]), key=lambda index: (candidates[index][0], candidates[index][1]))


def _percentiles(values: np.ndarray) -> dict[str, float | None]:
    if values.size == 0:
        return {key: None for key in ("p01", "p05", "p50", "p95", "p99")}
    result = np.percentile(values, [1, 5, 50, 95, 99])
    return {key: float(value) for key, value in zip(("p01", "p05", "p50", "p95", "p99"), result)}


def _sharpness(plane: np.ndarray, usable: np.ndarray) -> float | None:
    """Mean squared 4-neighbour Laplacian on valid interior pixels."""
    if min(plane.shape) < 3:
        return None
    centre = usable[1:-1, 1:-1]
    valid = centre & usable[:-2, 1:-1] & usable[2:, 1:-1] & usable[1:-1, :-2] & usable[1:-1, 2:]
    if not np.any(valid):
        return None
    laplacian = (
        -4.0 * plane[1:-1, 1:-1]
        + plane[:-2, 1:-1]
        + plane[2:, 1:-1]
        + plane[1:-1, :-2]
        + plane[1:-1, 2:]
    )
    return float(np.mean(np.square(laplacian[valid], dtype=np.float64)))


def compute_patch_statistics(
    data: np.ndarray,
    *,
    preferred_y: int | None = None,
    declared_background_values: Iterable[float] = DEFAULT_DECLARED_PADDING_VALUES,
) -> dict:
    """Compute descriptive metrics for a valid scientific X/Z plane.

    The background fraction is the number of finite plane pixels equal to one
    of the explicitly declared background/padding values divided by all finite
    plane pixels.  Percentiles and sharpness use finite pixels excluding those
    declared values.  Integer saturation is the fraction at the dtype's exact
    minimum or maximum; floating-point saturation is reported as unavailable.
    """
    array = np.asarray(data)
    if array.ndim != 3 or array.shape[1] == 0:
        raise ValueError(f"patch statistics require a non-empty 3-D array; got {array.shape}")
    padding = tuple(float(value) for value in declared_background_values)
    y = choose_valid_plane(array, preferred_y, padding)
    plane = np.asarray(array[:, y, :])
    finite = np.isfinite(plane)
    declared_background = finite & np.isin(plane, padding)
    usable = finite & ~declared_background
    values = np.asarray(plane[usable], dtype=np.float64)
    finite_count = int(np.count_nonzero(finite))
    usable_count = int(np.count_nonzero(usable))
    constant = usable_count > 0 and float(np.ptp(values)) == 0.0
    if np.issubdtype(plane.dtype, np.integer):
        limits = np.iinfo(plane.dtype)
        saturation = {
            "low_fraction": float(np.count_nonzero(usable & (plane == limits.min)) / max(1, usable_count)),
            "high_fraction": float(np.count_nonzero(usable & (plane == limits.max)) / max(1, usable_count)),
            "definition": "usable pixels exactly equal to the integer dtype minimum/maximum",
        }
    else:
        saturation = {
            "low_fraction": None,
            "high_fraction": None,
            "definition": "not reported for floating-point data; no storage endpoints are assumed",
        }
    result = {
        "statistics_version": STATISTICS_VERSION,
        "source": "raw scientific NIfTI data plane; display overlays and enlargement are excluded",
        "plane_expression": f"data[:,{y},:]",
        "slice_index_y": y,
        "shape_xz": [int(plane.shape[0]), int(plane.shape[1])],
        "dtype": str(plane.dtype),
        "declared_background_values": [float(value) for value in padding],
        "provider_padding_excluded": True,
        "finite_pixel_count": finite_count,
        "usable_pixel_count": usable_count,
        "nonfinite_fraction": float(np.count_nonzero(~finite) / plane.size),
        "declared_background_fraction_of_finite": float(np.count_nonzero(declared_background) / max(1, finite_count)),
        "status": "empty_or_padding" if usable_count == 0 else ("constant" if constant else "variable"),
        "percentiles_usable": _percentiles(values),
        "saturation": saturation,
        "sharpness": {
            "name": "mean_squared_4-neighbour_laplacian",
            "value": _sharpness(np.asarray(plane, dtype=np.float64), usable),
            "formula": "mean((4*c - up - down - left - right)^2) over valid interior pixels",
            "excluded": "nonfinite and declared background/padding pixels, plus any interior touching them",
        },
    }
    return result
