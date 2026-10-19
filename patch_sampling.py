"""Deterministic, bounded sampling plans for one registered section."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import version
from typing import Iterable

import numpy as np


SAMPLER_ALGORITHM = "numpy.random.Generator(PCG64)"
SAMPLER_VERSION = "1.0"
MAX_PATCH_COUNT = 8
MAX_REQUEST_COUNT = 8
MAX_ESTIMATED_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class RectangleXZ:
    min_x: float
    min_z: float
    max_x: float
    max_z: float

    def validate(self) -> None:
        values = np.asarray(list(asdict(self).values()), dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("sampling rectangle coordinates must be finite")
        if self.max_x <= self.min_x or self.max_z <= self.min_z:
            raise ValueError("sampling rectangle must have positive X and Z extent")


@dataclass(frozen=True)
class PatchSizeXZ:
    width_x: float
    height_z: float

    def validate(self) -> None:
        if not np.all(np.isfinite([self.width_x, self.height_z])) or self.width_x <= 0 or self.height_z <= 0:
            raise ValueError("patch dimensions must be finite and positive")


def _validate_plan_limits(rectangle: RectangleXZ, patch_size: PatchSizeXZ, count: int) -> None:
    rectangle.validate()
    patch_size.validate()
    if count < 1 or count > MAX_PATCH_COUNT:
        raise ValueError(f"patch count must be between 1 and {MAX_PATCH_COUNT}")
    if patch_size.width_x > rectangle.max_x - rectangle.min_x or patch_size.height_z > rectangle.max_z - rectangle.min_z:
        raise ValueError("patch footprint does not fit inside the sampling rectangle")


def validate_centres(centres: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return finite unique centres, rejecting duplicate requests."""
    result = [(float(x), float(z)) for x, z in centres]
    if not all(np.all(np.isfinite(point)) for point in result):
        raise ValueError("sampling centres must be finite")
    keys = [(round(x, 12), round(z, 12)) for x, z in result]
    if len(set(keys)) != len(keys):
        raise ValueError("sampling plan contains duplicate patch centres")
    return result


def generate_regular_grid(
    rectangle: RectangleXZ,
    patch_size: PatchSizeXZ,
    spacing_x: float,
    spacing_z: float,
) -> list[tuple[float, float]]:
    """Generate centres whose complete footprints stay inside the rectangle."""
    if spacing_x <= 0 or spacing_z <= 0 or not np.all(np.isfinite([spacing_x, spacing_z])):
        raise ValueError("grid spacing must be finite and positive")
    available_x = rectangle.max_x - rectangle.min_x - patch_size.width_x
    available_z = rectangle.max_z - rectangle.min_z - patch_size.height_z
    count_x = int(np.floor(available_x / spacing_x + 1e-12)) + 1
    count_z = int(np.floor(available_z / spacing_z + 1e-12)) + 1
    count = count_x * count_z
    _validate_plan_limits(rectangle, patch_size, count)
    x0 = rectangle.min_x + patch_size.width_x / 2.0
    z0 = rectangle.min_z + patch_size.height_z / 2.0
    return validate_centres(
        (x0 + ix * spacing_x, z0 + iz * spacing_z)
        for ix in range(count_x)
        for iz in range(count_z)
    )


def generate_seeded_random(
    rectangle: RectangleXZ,
    patch_size: PatchSizeXZ,
    count: int,
    seed: int,
) -> list[tuple[float, float]]:
    """Generate reproducible centres using recorded PCG64 draws."""
    _validate_plan_limits(rectangle, patch_size, count)
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    x_low = rectangle.min_x + patch_size.width_x / 2.0
    x_high = rectangle.max_x - patch_size.width_x / 2.0
    z_low = rectangle.min_z + patch_size.height_z / 2.0
    z_high = rectangle.max_z - patch_size.height_z / 2.0
    centres: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for _ in range(count * 10):
        point = tuple(float(value) for value in rng.uniform([x_low, z_low], [x_high, z_high]))
        key = (round(point[0], 12), round(point[1], 12))
        if key not in seen:
            seen.add(key)
            centres.append(point)
        if len(centres) == count:
            return centres
    raise RuntimeError("could not generate the requested number of unique random centres")


def footprint_bounds(center: tuple[float, float], patch_size: PatchSizeXZ, y_min: float, y_max: float) -> dict[str, float]:
    patch_size.validate()
    x, z = center
    return {
        "min_x": float(x - patch_size.width_x / 2.0),
        "min_y": float(y_min),
        "min_z": float(z - patch_size.height_z / 2.0),
        "max_x": float(x + patch_size.width_x / 2.0),
        "max_y": float(y_max),
        "max_z": float(z + patch_size.height_z / 2.0),
    }


def estimated_bytes_per_patch(patch_size: PatchSizeXZ, resolution_mm: float, y_thickness_mm: float) -> int:
    if resolution_mm <= 0 or y_thickness_mm <= 0:
        raise ValueError("resolution and Y thickness must be positive")
    voxels = int(np.ceil(patch_size.width_x / resolution_mm)) * int(np.ceil(y_thickness_mm / resolution_mm)) * int(np.ceil(patch_size.height_z / resolution_mm))
    return max(1, voxels)


def plan_metadata(
    method: str,
    rectangle: RectangleXZ,
    patch_size: PatchSizeXZ,
    centres: list[tuple[float, float]],
    resolution_mm: float,
    seed: int | None = None,
    spacing_x: float | None = None,
    spacing_z: float | None = None,
) -> dict:
    if method not in {"regular_grid", "seeded_random"}:
        raise ValueError(f"unsupported sampling method: {method}")
    return {
        "method": method,
        "rectangle_xz_mm": asdict(rectangle),
        "patch_dimensions_mm": asdict(patch_size),
        "spacing_mm": {"x": spacing_x, "z": spacing_z} if method == "regular_grid" else None,
        "count": len(centres),
        "seed": seed,
        "generator_algorithm": SAMPLER_ALGORITHM if method == "seeded_random" else None,
        "generator_version": SAMPLER_VERSION if method == "seeded_random" else None,
        "numpy_version": version("numpy"),
        "centres_xz_mm": [[float(x), float(z)] for x, z in centres],
        "edge_handling": "reject centres whose complete footprint leaves the selected rectangle",
        "overlap_policy": "overlap allowed and recorded; duplicate centres rejected",
        "background_filtering": "none; every requested centre is retained regardless of returned intensity",
        "requested_resolution_mm": float(resolution_mm),
    }
