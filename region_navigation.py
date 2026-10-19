"""Bounded, provenance-first region navigation for the BigBrain space.

This module deliberately supports only the installed siibra cortical-layer
parcellation used in the feasibility evidence. It does not create a
registration, infer labels, or treat a mask-plane intersection as anatomical
validation.
"""
from __future__ import annotations

from typing import Any

import numpy as np


PARCELLATION_NAME = "Cortical layer segmentation of the BigBrain model"
REGION_NAME = "cortical layer 1 left"
REGION_THRESHOLD = 0.0
REGION_RESOLUTION_REQUEST_MM = (0.2, 0.2, 0.2)
REGION_FETCH_MAX_BYTES = 20 * 1024 * 1024

# These are real bounded mask-plane checks recorded in
# outputs/region_feasibility/evidence.json. Other catalogue sections remain
# untested until explicitly checked; they are not silently treated as hits.
VERIFIED_SECTION_INTERSECTIONS = {
    3458: {
        "section_id": "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        "plane_y_mm": -0.8595,
        "nonzero_mask_voxels": 12638,
    },
    3500: {
        "section_id": "73c1fa55-d099-4854-8cda-c9a403c6080a--b0738367ed7b5255928960dd9b97f16f",
        "plane_y_mm": -0.0195,
        "nonzero_mask_voxels": 18872,
    },
}


def region_catalogue_entry() -> dict[str, Any]:
    """Return the one supported atlas region and its explicit provenance."""
    return {
        "parcellation": PARCELLATION_NAME,
        "region": REGION_NAME,
        "threshold": REGION_THRESHOLD,
        "status": "real bounded mask-plane evidence available",
        "space": "BigBrain microscopic template (histology)",
        "license": "CC BY-NC-SA 4.0",
        "publication": "https://doi.org/10.1371/journal.pbio.3000678",
        "provider": "https://neuroglancer.humanbrainproject.eu/precomputed/BigBrainRelease.2015/2022_map_release/cortical_layers_left",
    }


def fetch_region_mask_plane(
    region_name: str,
    section_plane_y_mm: float,
    *,
    x_bounds: tuple[float, float] = (-70.67, 68.44),
    z_bounds: tuple[float, float] = (-58.78, 62.11),
    resolution_mm: tuple[float, float, float] = REGION_RESOLUTION_REQUEST_MM,
    max_bytes: int = REGION_FETCH_MAX_BYTES,
):
    """Fetch one bounded real mask plane in the selected section's Y slab."""
    if region_name != REGION_NAME:
        raise ValueError(f"unsupported region: {region_name}")
    import siibra
    from siibra.locations import BoundingBox

    parcellation = siibra.get_parcellation(PARCELLATION_NAME)
    region = parcellation.get_region(region_name)
    space = list(region.spaces)[0]
    mask = region.get_regional_mask(space, threshold=REGION_THRESHOLD)
    half_thickness = 0.12
    voi = BoundingBox(
        [x_bounds[0], section_plane_y_mm - half_thickness, z_bounds[0]],
        [x_bounds[1], section_plane_y_mm + half_thickness, z_bounds[1]],
        space=space,
    )
    image = mask.fetch(
        format="image",
        resolution_mm=resolution_mm,
        voi=voi,
        max_bytes=max_bytes,
    )
    if image is None:
        raise RuntimeError("the region-mask provider returned no image")
    return image, {
        **region_catalogue_entry(),
        "parcellation_id": parcellation.id,
        "region_id": region.id,
        "space_id": space.id,
        "requested_resolution_mm": list(resolution_mm),
        "actual_resolution_mm": [float(v) for v in image.header.get_zooms()[:3]],
        "mask_plane_y_mm": float(section_plane_y_mm),
        "mask_plane_shape": [int(v) for v in image.shape[:3]],
        "mask_plane_affine": np.asarray(image.affine, dtype=float).tolist(),
        "mask_nonzero_voxels": int(np.count_nonzero(np.asanyarray(image.dataobj))),
    }


def mask_plane_intersects(mask_image) -> bool:
    """Return true only when the fetched mask plane contains nonzero voxels."""
    return bool(np.any(np.asanyarray(mask_image.dataobj) > 0))


def sample_mask_to_section_display(
    mask_image,
    section_image,
    section_plane_y_mm: float,
    display_shape: tuple[int, int],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Sample a categorical mask on the exact displayed section plane.

    The section renderer is display-only ``data[x, y, z].T``: display
    ``(u, v)`` is source ``(z, x)``.  For every display pixel we construct
    the corresponding section voxel ``x/z`` coordinates, solve the full
    section affine for the requested world Y, transform that world point
    through the full mask affine, and use nearest-neighbour categorical
    sampling.  This is intentionally different from projecting every
    nonzero voxel in a finite Y slab.
    """
    height, width = (int(display_shape[0]), int(display_shape[1]))
    if height < 1 or width < 1:
        raise ValueError("display_shape must contain positive dimensions")
    section_affine = np.asarray(section_image.affine, dtype=float)
    mask_affine = np.asarray(mask_image.affine, dtype=float)
    if section_affine.shape != (4, 4) or mask_affine.shape != (4, 4):
        raise ValueError("section and mask affines must be 4x4")
    if abs(section_affine[1, 1]) < 1e-12:
        raise ValueError("section affine cannot solve source Y from world Y")

    # Source display geometry: horizontal z, vertical x.  Resize maps pixel
    # centres over the source index extent, preserving the existing renderer.
    x = np.linspace(0.0, max(0, section_image.shape[0] - 1), height)
    z = np.linspace(0.0, max(0, section_image.shape[2] - 1), width)
    zz, xx = np.meshgrid(z, x, indexing="xy")
    y = (
        float(section_plane_y_mm)
        - section_affine[1, 0] * xx
        - section_affine[1, 2] * zz
        - section_affine[1, 3]
    ) / section_affine[1, 1]
    section_voxels = np.stack([xx, y, zz, np.ones_like(xx)], axis=-1)
    world = section_voxels @ section_affine.T
    mask_voxels = world @ np.linalg.inv(mask_affine).T
    nearest = np.rint(mask_voxels[..., :3]).astype(int)
    mask_shape = np.asarray(mask_image.shape[:3], dtype=int)
    valid = np.all((nearest >= 0) & (nearest < mask_shape), axis=-1)
    sampled = np.zeros((height, width), dtype=np.uint8)
    mask_data = np.asanyarray(mask_image.dataobj)
    if np.any(valid):
        valid_indices = nearest[valid]
        sampled[valid] = np.asarray(mask_data[tuple(valid_indices.T)] > REGION_THRESHOLD, dtype=np.uint8)
    metadata = {
        "status": "exact section-plane sample",
        "interpolation": "nearest-neighbor categorical",
        "section_plane_y_mm": float(section_plane_y_mm),
        "display_shape_rows_cols": [height, width],
        "display_horizontal_source_axis": "z",
        "display_vertical_source_axis": "x",
        "transpose": True,
        "flip_horizontal": False,
        "flip_vertical": False,
        "section_affine": section_affine.tolist(),
        "mask_affine": mask_affine.tolist(),
        "valid_sample_pixels": int(np.count_nonzero(valid)),
        "exact_plane_nonzero_pixels": int(np.count_nonzero(sampled)),
    }
    return sampled, metadata


def central_nonzero_display_pixel(mask_display: np.ndarray) -> tuple[int, int] | None:
    """Choose an actual nonzero display pixel nearest the nonzero centroid."""
    coordinates = np.argwhere(np.asarray(mask_display) > 0)
    if coordinates.size == 0:
        return None
    centroid = coordinates.mean(axis=0)
    selected = coordinates[np.argmin(np.sum((coordinates - centroid) ** 2, axis=1))]
    v, u = (int(value) for value in selected)
    return u, v


def overlay_display_mask(display_gray: np.ndarray, mask_display: np.ndarray) -> np.ndarray:
    """Render a 2-D diagnostic mask without changing image geometry."""
    base = np.asarray(display_gray)
    mask = np.asarray(mask_display)
    if base.ndim != 2 or mask.shape != base.shape:
        raise ValueError(f"display and mask must be matching 2-D arrays, got {base.shape} and {mask.shape}")
    rgb = np.repeat(np.clip(base, 0, 255).astype(np.uint8)[..., None], 3, axis=2)
    rgb[mask > 0] = (220, 45, 45)
    return rgb


def overlay_mask_on_section_display(mask_image, section_image, display_gray: np.ndarray) -> np.ndarray:
    """Project nonzero mask voxels onto a section display using both affines.

    ``display_gray`` is the visualization-only ``data[:, y, :].T`` plane:
    display horizontal is source Z and display vertical is source X. The
    source arrays and affines are never modified.
    """
    base = np.asarray(display_gray)
    if base.ndim != 2:
        raise ValueError(f"display_gray must be 2-D, got {base.shape}")
    rgb = np.repeat(base[..., None], 3, axis=2).astype(np.uint8, copy=True)
    mask = np.argwhere(np.asanyarray(mask_image.dataobj) > 0)
    if mask.size == 0:
        return rgb
    inverse = np.linalg.inv(np.asarray(section_image.affine, dtype=float))
    mask_affine = np.asarray(mask_image.affine, dtype=float)
    sx, _, sz = section_image.shape[:3]
    height, width = base.shape
    stride = max(1, len(mask) // 6000)
    for index in mask[::stride]:
        world = mask_affine @ np.r_[index, 1.0]
        voxel = inverse @ np.r_[world[:3], 1.0]
        u = round(float(voxel[2]) * (width - 1) / max(1, sz - 1))
        v = round(float(voxel[0]) * (height - 1) / max(1, sx - 1))
        if 0 <= u < width and 0 <= v < height:
            rgb[v, u] = (255, 55, 55)
    return rgb
