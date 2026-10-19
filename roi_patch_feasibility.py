"""Separate ROI-to-registered-section feasibility demonstration.

This script is intentionally outside the Streamlit workflow.  Stage 1 starts
from a previously verified real #3458 provider patch and tests extraction in
BigBrain reference space only.  Stage 2 is an audit of the existing external
MRI execution prerequisites; it does not invent a template coordinate or run
registration when the documented runtime is unavailable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw

from bigbrain_cutout import Bounds, fetch_crop, section_catalogue


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "roi_patch_feasibility"
SECTION_NUMBER = 3458
SECTION_ID = "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126"
# Selected from the preserved, real-data exact-plane audit, not inferred from
# a section number or a coordinate range.
KNOWN_TISSUE_WORLD_XYZ_MM = np.array([-38.56517693785311, -0.8594999999999994, 9.204207252302027])
ROI_AFFINE = np.array(
    [[0.2, 0.0, 0.0, -40.0], [0.0, 0.02, 0.0, -0.8695], [0.0, 0.0, 0.2, 8.0], [0, 0, 0, 1]],
    dtype=float,
)
ROI_SHAPE = (20, 2, 20)
REQUESTED_RESOLUTION_MM = 0.01
MAX_BYTES = 5 * 1024 * 1024


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_array(value: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(value).tobytes(order="C"))


def voxel_centres(image: nib.spatialimages.SpatialImage) -> np.ndarray:
    shape = tuple(int(v) for v in image.shape[:3])
    grid = np.indices(shape, dtype=float).reshape(3, -1).T
    return (np.asarray(image.affine, dtype=float) @ np.c_[grid, np.ones(len(grid))].T).T[:, :3]


def make_roi() -> nib.Nifti1Image:
    # A small binary box around the documented tissue point.  This is an
    # extraction ROI, not a tissue or anatomical segmentation.
    inverse = np.linalg.inv(ROI_AFFINE)
    voxel = np.rint((inverse @ np.r_[KNOWN_TISSUE_WORLD_XYZ_MM, 1.0])[:3]).astype(int)
    mask = np.zeros(ROI_SHAPE, dtype=np.uint8)
    for dx in range(-2, 3):
        for dz in range(-2, 3):
            x, _, z = voxel + np.array([dx, 0, dz])
            for y in range(ROI_SHAPE[1]):
                if 0 <= x < ROI_SHAPE[0] and 0 <= z < ROI_SHAPE[2]:
                    mask[x, y, z] = 1
    return nib.Nifti1Image(mask, ROI_AFFINE, header=nib.Nifti1Header())


def roi_world_bounds() -> tuple[np.ndarray, np.ndarray]:
    corners = np.array(
        [[x, y, z] for x in (0, ROI_SHAPE[0] - 1) for y in (0, ROI_SHAPE[1] - 1) for z in (0, ROI_SHAPE[2] - 1)],
        dtype=float,
    )
    world = (ROI_AFFINE @ np.c_[corners, np.ones(len(corners))].T).T[:, :3]
    return world.min(axis=0), world.max(axis=0)


def section_candidates() -> list[dict]:
    minimum, maximum = roi_world_bounds()
    candidates = []
    for section in section_catalogue():
        bounds = section["bounds_mm"]
        intersects = (
            bounds["max_x"] >= minimum[0] and bounds["min_x"] <= maximum[0]
            and bounds["max_y"] + 1e-9 >= minimum[1] and bounds["min_y"] - 1e-9 <= maximum[1]
            and bounds["max_z"] >= minimum[2] and bounds["min_z"] <= maximum[2]
        )
        if intersects:
            candidates.append({
                "section_number": section["section_number"],
                "section_id": section["id"],
                "section_plane_y_mm": section["section_plane_y_mm"],
                "source_url": section["source_url"],
                "criterion": "ROI world AABB intersects documented section bounds; exact tissue overlap tested only after fetch",
            })
    return candidates


def sample_roi_on_patch(roi: nib.spatialimages.SpatialImage, patch: nib.spatialimages.SpatialImage, y_index: int) -> np.ndarray:
    """Sample binary ROI with nearest-neighbour at each patch voxel centre."""
    roi_data = np.asarray(roi.dataobj)
    patch_shape = tuple(int(v) for v in patch.shape[:3])
    indices = np.indices(patch_shape, dtype=float).reshape(3, -1).T
    world = (np.asarray(patch.affine) @ np.c_[indices, np.ones(len(indices))].T).T[:, :3]
    source = (np.linalg.inv(np.asarray(roi.affine)) @ np.c_[world, np.ones(len(world))].T).T[:, :3]
    nearest = np.rint(source).astype(int)
    valid = np.all((nearest >= 0) & (nearest < np.asarray(roi_data.shape)), axis=1)
    sampled = np.zeros(len(indices), dtype=np.uint8)
    sampled[valid] = roi_data[nearest[valid, 0], nearest[valid, 1], nearest[valid, 2]].astype(np.uint8)
    return sampled.reshape(patch_shape)[:, y_index, :]


def overlay(patch: nib.spatialimages.SpatialImage, roi_plane: np.ndarray, output: Path) -> None:
    data = np.asarray(patch.dataobj)
    y_index = int(np.argmax([np.std(data[:, i, :]) for i in range(data.shape[1])]))
    plane = data[:, y_index, :].astype(float)
    low, high = np.percentile(plane, [1, 99])
    gray = np.clip((plane - low) * 255 / max(high - low, 1), 0, 255).astype(np.uint8).T
    rgb = np.repeat(gray[..., None], 3, axis=2)
    # display is horizontal source z, vertical source x; overlay mask follows
    # the same transpose, with no flip or geometric resampling.
    mask = roi_plane.T.astype(bool)
    rgb[mask] = (255, 55, 55)
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    draw.text((8, 8), f"#3458 ROI extraction · y index {y_index}", fill=(255, 255, 0))
    image.save(output)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    roi = make_roi()
    nib.save(roi, OUT / "stage1_binary_roi.nii.gz")
    roi_min, roi_max = roi_world_bounds()
    candidates = section_candidates()
    if not any(item["section_id"] == SECTION_ID for item in candidates):
        raise RuntimeError("the known #3458 tissue ROI did not intersect its documented section bounds")

    section = next(item for item in candidates if item["section_id"] == SECTION_ID)
    half_x = 1.0
    half_z = 1.0
    bounds = Bounds(
        float(KNOWN_TISSUE_WORLD_XYZ_MM[0] - half_x),
        float(section["section_plane_y_mm"] - 0.04),
        float(KNOWN_TISSUE_WORLD_XYZ_MM[2] - half_z),
        float(KNOWN_TISSUE_WORLD_XYZ_MM[0] + half_x),
        float(section["section_plane_y_mm"] + 0.04),
        float(KNOWN_TISSUE_WORLD_XYZ_MM[2] + half_z),
    )
    patch, _, section_bounds = fetch_crop(bounds, resolution_mm=REQUESTED_RESOLUTION_MM, max_bytes=MAX_BYTES, section_id=SECTION_ID)
    patch_data = np.asarray(patch.dataobj)
    y_index = int(np.argmax([np.std(patch_data[:, i, :]) for i in range(patch_data.shape[1])]))
    roi_plane = sample_roi_on_patch(roi, patch, y_index)
    overlap = int(np.count_nonzero(roi_plane & (patch_data[:, y_index, :] != 255)))
    patch_world = voxel_centres(patch)
    patch_min, patch_max = patch_world.min(axis=0), patch_world.max(axis=0)
    patch_serialized = (OUT / "stage1_patch.nii.gz")
    nib.save(patch, patch_serialized)
    overlay(patch, roi_plane, OUT / "stage1_roi_patch_overlay.png")
    metadata = {
        "stage": "1_bigbrain_space_extraction",
        "status": "passed_extraction_checks",
        "anatomical_interpretation": "not tested; ROI is an extraction fixture around a previously verified tissue patch",
        "section_number": SECTION_NUMBER,
        "section_id": SECTION_ID,
        "provider": section["source_url"],
        "roi_source": "preserved exact-plane audit selected nonzero provider voxel",
        "known_tissue_world_xyz_mm": KNOWN_TISSUE_WORLD_XYZ_MM.tolist(),
        "roi_affine": ROI_AFFINE.tolist(),
        "roi_shape_xyz": list(ROI_SHAPE),
        "roi_world_bounds_mm": [*roi_min.tolist(), *roi_max.tolist()],
        "intersection_candidates": candidates,
        "section_bounds_mm": [section_bounds.minpoint[0], section_bounds.minpoint[1], section_bounds.minpoint[2], section_bounds.maxpoint[0], section_bounds.maxpoint[1], section_bounds.maxpoint[2]],
        "requested_patch_bounds_mm": list(bounds.__dict__.values()),
        "patch_shape_xyz": list(patch.shape),
        "patch_affine": np.asarray(patch.affine).tolist(),
        "patch_voxel_size_mm_xyz": [float(v) for v in patch.header.get_zooms()[:3]],
        "patch_world_extent_voxel_centres_mm": [*patch_min.tolist(), *patch_max.tolist()],
        "patch_slice_index_y": y_index,
        "patch_slice_centre_world_y_mm": float(patch_world.reshape(patch.shape[:3] + (3,))[:, y_index, :, 1].mean()),
        "roi_patch_overlap_nonbackground_voxels": overlap,
        "patch_raw_array_sha256": sha256_array(patch_data),
        "roi_raw_array_sha256": sha256_array(np.asarray(roi.dataobj)),
        "patch_nifti_sha256": sha256_bytes(patch_serialized.read_bytes()),
        "mapping": {
            "roi_and_patch_world_mm": "full affine voxel-centre coordinates",
            "roi_sampling": "nearest-neighbour at patch voxel centres",
            "display": "patch data[:, y, :].T; horizontal source z, vertical source x; no flip",
            "overlap_definition": "ROI mask sampled on fetched patch plane and intersected with non-background value != 255",
        },
        "reproducible_command": "./.venv/bin/python roi_patch_feasibility.py",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / "stage1_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"section": SECTION_NUMBER, "candidates": len(candidates), "patch_shape": list(patch.shape), "roi_patch_overlap_nonbackground_voxels": overlap, "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
