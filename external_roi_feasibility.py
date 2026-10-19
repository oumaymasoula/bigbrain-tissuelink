"""Separate external-template ROI feasibility audit.

This module does not participate in the Streamlit application.  It consumes
the exact template mask and the bounded BigBrainWarp output produced by the
verified Docker image, samples every discovered registered section plane on
the output's world X/Z grid, and optionally fetches one real patch only after
the exact-plane sample contains mask voxels.

The distributed ICBM file is a binary template-space mask, not an anatomical
landmark or a participant ROI.  Its nonzero values are therefore reported as
technical mask membership only.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw

from bigbrain_cutout import Bounds, fetch_crop, section_catalogue


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "outputs" / "external_roi_feasibility" / "input_icbm2009c_template_mask.nii"
DEFAULT_TRANSFORMED = ROOT / "outputs" / "external_roi_feasibility" / "transformed_bigbrain_roi_2mm.nii"
DEFAULT_OUTPUT = ROOT / "outputs" / "external_roi_feasibility"
IMAGE_DIGEST = "sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614"
REQUESTED_RESOLUTION_MM = 0.01
MAX_BYTES = 5 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_geometry(image: nib.spatialimages.SpatialImage) -> dict[str, Any]:
    data = np.asarray(image.dataobj)
    ijk = np.argwhere(data != 0)
    if len(ijk):
        world = nib.affines.apply_affine(np.asarray(image.affine, dtype=float), ijk)
        bounds = [world.min(axis=0).tolist(), world.max(axis=0).tolist()]
    else:
        bounds = [None, None]
    return {
        "shape_xyz": [int(value) for value in image.shape[:3]],
        "dtype": str(data.dtype),
        "affine": np.asarray(image.affine, dtype=float).tolist(),
        "voxel_size_mm_xyz": [float(value) for value in image.header.get_zooms()[:3]],
        "value_min": float(np.min(data)),
        "value_max": float(np.max(data)),
        "nonzero_voxels": int(np.count_nonzero(data)),
        "nonzero_world_bounds_mm": bounds,
    }


def sample_nearest(mask: nib.spatialimages.SpatialImage, world_xyz: np.ndarray) -> np.ndarray:
    """Sample a mask at world points using the full affine and nearest neighbour."""
    world_xyz = np.asarray(world_xyz, dtype=float).reshape(-1, 3)
    inverse = np.linalg.inv(np.asarray(mask.affine, dtype=float))
    voxel = nib.affines.apply_affine(inverse, world_xyz)
    nearest = np.rint(voxel).astype(int)
    shape = np.asarray(mask.shape[:3], dtype=int)
    valid = np.all((nearest >= 0) & (nearest < shape), axis=1)
    values = np.zeros(len(world_xyz), dtype=np.uint8)
    data = np.asarray(mask.dataobj)
    values[valid] = (data[tuple(nearest[valid].T)] != 0).astype(np.uint8)
    return values


def _axis_grid(low: float, high: float, spacing: float) -> np.ndarray:
    values = np.arange(float(low), float(high) + spacing * 0.5, spacing, dtype=float)
    if not len(values) or values[-1] < high:
        values = np.append(values, float(high))
    return values


def sample_section_plane(mask: nib.spatialimages.SpatialImage, section: dict[str, Any], spacing_mm: float) -> dict[str, Any]:
    """Sample one documented section plane at exact world Y, categorically."""
    bounds = section["bounds_mm"]
    mask_bounds = image_geometry(mask)["nonzero_world_bounds_mm"]
    if mask_bounds[0] is None:
        return {"status": "no_mask_values", "sampled_pixels": 0, "nonzero_pixels": 0}
    min_x = max(float(bounds["min_x"]), float(mask_bounds[0][0]))
    max_x = min(float(bounds["max_x"]), float(mask_bounds[1][0]))
    min_z = max(float(bounds["min_z"]), float(mask_bounds[0][2]))
    max_z = min(float(bounds["max_z"]), float(mask_bounds[1][2]))
    if min_x > max_x or min_z > max_z:
        return {"status": "no_xz_extent_overlap", "sampled_pixels": 0, "nonzero_pixels": 0}
    xs = _axis_grid(min_x, max_x, spacing_mm)
    zs = _axis_grid(min_z, max_z, spacing_mm)
    xx, zz = np.meshgrid(xs, zs, indexing="ij")
    plane_y = float(section["section_plane_y_mm"])
    world = np.column_stack((xx.ravel(), np.full(xx.size, plane_y), zz.ravel()))
    sampled = sample_nearest(mask, world).reshape(xx.shape)
    points = world[sampled.ravel() != 0]
    return {
        "status": "exact_plane_nonzero" if len(points) else "exact_plane_zero",
        "plane_y_mm": plane_y,
        "grid_spacing_mm": float(spacing_mm),
        "grid_shape_xz": [int(len(xs)), int(len(zs))],
        "world_x_bounds_mm": [float(xs[0]), float(xs[-1])],
        "world_z_bounds_mm": [float(zs[0]), float(zs[-1])],
        "sampled_pixels": int(sampled.size),
        "nonzero_pixels": int(np.count_nonzero(sampled)),
        "first_nonzero_world_xyz_mm": points[0].tolist() if len(points) else None,
        "mask_sampling": "full mask affine; world Y fixed to documented section plane; nearest-neighbour",
    }


def sample_image_mask_on_patch(mask: nib.spatialimages.SpatialImage, patch: nib.spatialimages.SpatialImage) -> np.ndarray:
    shape = tuple(int(value) for value in patch.shape[:3])
    ijk = np.indices(shape, dtype=float).reshape(3, -1).T
    world = nib.affines.apply_affine(np.asarray(patch.affine, dtype=float), ijk)
    return sample_nearest(mask, world).reshape(shape)


def _display_plane(image: nib.spatialimages.SpatialImage, y_index: int) -> np.ndarray:
    data = np.asarray(image.dataobj)
    plane = np.asarray(data[:, y_index, :], dtype=float)
    low, high = np.percentile(plane, [1, 99])
    return np.clip((plane - low) * 255.0 / max(high - low, 1.0), 0, 255).astype(np.uint8).T


def save_view(image: nib.spatialimages.SpatialImage, y_index: int, output: Path, title: str, mask_plane: np.ndarray | None = None) -> None:
    gray = _display_plane(image, y_index)
    rgb = np.repeat(gray[..., None], 3, axis=2)
    if mask_plane is not None:
        overlay = np.asarray(mask_plane, dtype=bool).T
        edge = overlay.copy()
        edge[1:, :] &= ~overlay[:-1, :]
        edge[:, 1:] |= overlay[:, 1:] & ~overlay[:, :-1]
        red = np.asarray((235, 55, 55), dtype=np.uint8)
        if float(np.mean(overlay)) < 0.9:
            rgb[overlay] = (0.65 * rgb[overlay].astype(np.float32) + 0.35 * red).astype(np.uint8)
        rgb[edge] = red
    canvas = Image.fromarray(rgb)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, min(canvas.width, 700), 24), fill=(0, 0, 0))
    draw.text((8, 6), title, fill=(255, 255, 0))
    canvas.save(output)


def run(input_path: Path = DEFAULT_INPUT, transformed_path: Path = DEFAULT_TRANSFORMED, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = nib.load(str(input_path))
    transformed = nib.load(str(transformed_path))
    template_geometry = image_geometry(template)
    transformed_geometry = image_geometry(transformed)
    template_data = np.asarray(template.dataobj)
    transformed_data = np.asarray(transformed.dataobj)

    template_y = int(np.argmax([np.count_nonzero(template_data[:, index, :]) for index in range(template_data.shape[1])]))
    transformed_y = int(np.argmax([np.count_nonzero(transformed_data[:, index, :]) for index in range(transformed_data.shape[1])]))
    save_view(template, template_y, output_dir / "input_template_mask_view.png", f"ICBM2009c template mask · y index {template_y}")
    save_view(transformed, transformed_y, output_dir / "transformed_bigbrain_roi_view.png", f"BigBrain transformed mask · y index {transformed_y}")

    plane_results: list[dict[str, Any]] = []
    for section in section_catalogue():
        result = sample_section_plane(transformed, section, spacing_mm=2.0)
        plane_results.append({
            "section_number": section["section_number"],
            "section_id": section["id"],
            "source_url": section["source_url"],
            "section_plane_y_mm": section["section_plane_y_mm"],
            "section_bounds_mm": section["bounds_mm"],
            "plane_test": result,
        })

    intersecting = [item for item in plane_results if item["plane_test"].get("nonzero_pixels", 0) > 0]
    fetch_result: dict[str, Any] | None = None
    if intersecting:
        selected = intersecting[0]
        point = np.asarray(selected["plane_test"]["first_nonzero_world_xyz_mm"], dtype=float)
        half_x = half_z = 1.0
        plane_y = float(selected["section_plane_y_mm"])
        bounds = Bounds(float(point[0] - half_x), plane_y - 0.04, float(point[2] - half_z), float(point[0] + half_x), plane_y + 0.04, float(point[2] + half_z))
        patch, _, section_bounds = fetch_crop(bounds, resolution_mm=REQUESTED_RESOLUTION_MM, max_bytes=MAX_BYTES, section_id=selected["section_id"])
        patch_data = np.asarray(patch.dataobj)
        mask_on_patch = sample_image_mask_on_patch(transformed, patch)
        # This is only a conservative provider-padding exclusion for this
        # diagnostic.  It is not a tissue-quality classifier or segmentation.
        nonpadding = (patch_data > 0) & (patch_data < 255)
        per_slice = [int(np.count_nonzero(mask_on_patch[:, index, :] & nonpadding[:, index, :])) for index in range(patch_data.shape[1])]
        patch_y = int(np.argmax(per_slice)) if per_slice else 0
        save_view(patch, patch_y, output_dir / "section_patch_mask_overlay.png", f"Section #{selected['section_number']} patch · y index {patch_y}", mask_on_patch[:, patch_y, :])
        patch_path = output_dir / "section_patch.nii.gz"
        nib.save(patch, str(patch_path))
        fetch_result = {
            "status": "fetched_after_exact_plane_membership",
            "section_number": selected["section_number"],
            "section_id": selected["section_id"],
            "selected_world_xyz_mm": point.tolist(),
            "requested_bounds_mm": list(bounds.__dict__.values()),
            "section_bounds_mm": [
                float(value)
                for value in (list(section_bounds.minpoint.coordinate) + list(section_bounds.maxpoint.coordinate))
            ],
            "patch_shape_xyz": [int(value) for value in patch.shape[:3]],
            "patch_affine": np.asarray(patch.affine, dtype=float).tolist(),
            "patch_voxel_size_mm_xyz": [float(value) for value in patch.header.get_zooms()[:3]],
            "mask_nonzero_patch_voxels": int(np.count_nonzero(mask_on_patch)),
            "mask_nonbackground_overlap_voxels_by_y": per_slice,
            "provider_padding_exclusion": "exact values 0 and 255 excluded for this observed patch only; this is not tissue classification",
            "patch_nonpadding_voxels": int(np.count_nonzero(nonpadding)),
            "patch_nonpadding_value_range": [int(patch_data[nonpadding].min()), int(patch_data[nonpadding].max())] if np.any(nonpadding) else None,
            "selected_patch_y_index": patch_y,
            "patch_raw_array_sha256": hashlib.sha256(np.ascontiguousarray(patch_data).tobytes()).hexdigest(),
            "patch_nifti_sha256": sha256_file(patch_path),
            "provider": selected["source_url"],
            "anatomical_status": "not independently reviewed",
        }

    metadata = {
        "stage": "2_external_template_roi_feasibility",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "technical_status": "exact_plane_candidates_tested",
        "anatomical_status": "not independently reviewed",
        "template_identity": {
            "path": input_path.name,
            "distributed_asset": "tpl-icbm_desc-t1_tal_nlin_sym_09c_mask.mnc",
            "space": "ICBM2009c nonlinear symmetric / ICBM2009sym",
            "construction": "the distributed binary template mask copied from the pinned BigBrainWarp image; no anatomical ROI or filename-based landmark assumption",
            "geometry": template_geometry,
            "serialized_sha256": sha256_file(input_path),
        },
        "transform_identity": {
            "image_digest": IMAGE_DIGEST,
            "script": "BigBrainWarp/scripts/icbm_to_bigbrain.sh",
            "direction": "ICBM input to BigBrain histological output using BigBrainHist-to-ICBM2009sym-nonlin.xfm with -invert_transformation",
            "interpolation": "nearest-neighbour",
            "warnings": "upstream script emitted command-not-found warnings at lines 60 and 64 from invisible characters; output completed with container exit 0",
        },
        "transformed_output": {
            "path": transformed_path.name,
            "geometry": transformed_geometry,
            "serialized_sha256": sha256_file(transformed_path),
            "output_resolution_mm": 2.0,
            "reference": "tpl-bigbrain_desc-cls_1000um.nii geometry resampled to 2 mm by the upstream script",
        },
        "section_plane_results": plane_results,
        "intersecting_section_count": len(intersecting),
        "intersecting_sections": [{"section_number": item["section_number"], "section_id": item["section_id"], "plane_y_mm": item["section_plane_y_mm"]} for item in intersecting],
        "anatomical_landmark_review": {
            "status": "not_prepared",
            "reason": "The bundled CREATORS_mni_icbm152.txt records provenance and licensing only; it does not document an independently identifiable anatomical landmark. No template coordinate was invented or promoted to an anatomical label.",
            "expert_action": "Supply a documented template landmark before creating a candidate BigBrain counterpart.",
        },
        "fetch_result": fetch_result,
        "technical_vs_anatomical": "Nonzero nearest-neighbour mask samples and patch overlap establish only a reproducible technical extraction relationship. They do not establish anatomical correspondence or validate the template-to-donor mapping.",
        "reproducible_commands": [
            "docker pull docker.io/caseypaquola/bigbrainwarp@sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614",
            "source /BigBrainWarp/scripts/init.sh",
            "/BigBrainWarp/scripts/icbm_to_bigbrain.sh $icbmTemplate histological nearest 2 stage2_template_mask /work/out",
            ".venv/bin/python external_roi_feasibility.py",
        ],
    }
    (output_dir / "external_roi_stage2_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    result = run()
    print(json.dumps({"intersecting_section_count": result["intersecting_section_count"], "intersecting_sections": result["intersecting_sections"], "fetch_result": result["fetch_result"]}, indent=2))
