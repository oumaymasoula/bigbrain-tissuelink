"""Reproduce the bounded exact-plane atlas-mask audit for section #3458."""
from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from bigbrain_cutout import Bounds, MAX_BYTES, fetch_crop
from registered_section_demo import (
    map_section_pixel_to_world,
    registered_context,
    registered_overview,
    section_display_array,
    HIST_SPEC,
)
from region_navigation import (
    REGION_NAME,
    central_nonzero_display_pixel,
    fetch_region_mask_plane,
    overlay_display_mask,
    sample_mask_to_section_display,
)


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs/region_feasibility"
SECTION_ID = "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _, bbox, _, _, _, _ = registered_context(SECTION_ID)
    section_y = float((bbox.minpoint[1] + bbox.maxpoint[1]) / 2.0)
    section_image, _, section_slice, section_range = registered_overview(
        tuple(float(value) for value in (*bbox.minpoint, *bbox.maxpoint)), SECTION_ID
    )
    section_display, display_mapping = section_display_array(section_image)
    display_size = (int(section_display.shape[1]), int(section_display.shape[0]))
    mask_image, mask_meta = fetch_region_mask_plane(REGION_NAME, section_y)
    mask_display, exact_meta = sample_mask_to_section_display(
        mask_image, section_image, section_y, (display_size[1], display_size[0])
    )
    selected_uv = central_nonzero_display_pixel(mask_display)
    if selected_uv is None:
        raise RuntimeError("exact section plane contains no nonzero mask pixel")
    selected_point = map_section_pixel_to_world(
        section_image, selected_uv, display_size, section_y
    )
    x, _, z = (float(value) for value in selected_point["world_xyz_mm"])
    patch_bounds = Bounds(
        max(float(bbox.minpoint[0]), x - 1.0), float(bbox.minpoint[1]), max(float(bbox.minpoint[2]), z - 1.0),
        min(float(bbox.maxpoint[0]), x + 1.0), float(bbox.maxpoint[1]), min(float(bbox.maxpoint[2]), z + 1.0),
    )
    patch, _, _ = fetch_crop(patch_bounds, resolution_mm=0.01, max_bytes=MAX_BYTES, section_id=SECTION_ID)
    intersects = (
        patch_bounds.min_x <= x <= patch_bounds.max_x
        and patch_bounds.min_z <= z <= patch_bounds.max_z
    )
    overlay = overlay_display_mask(section_display, mask_display)
    background_like = (np.asarray(section_display) > 245) & (mask_display > 0)

    # Independent source-reconstruction check. Build one world grid from the
    # section display convention, then sample the 200 um reconstruction at
    # those same requested world coordinates. The intensity sample is linear;
    # the categorical mask sample remains nearest-neighbour.
    section_affine = np.asarray(section_image.affine, dtype=float)
    height, width = section_display.shape
    x_index = np.linspace(0.0, section_image.shape[0] - 1, height)
    z_index = np.linspace(0.0, section_image.shape[2] - 1, width)
    zz, xx = np.meshgrid(z_index, x_index, indexing="xy")
    yy = (
        section_y - section_affine[1, 0] * xx - section_affine[1, 2] * zz - section_affine[1, 3]
    ) / section_affine[1, 1]
    section_voxels = np.stack([xx, yy, zz, np.ones_like(xx)], axis=-1)
    world_grid = section_voxels @ section_affine.T
    histology = nib.load(str(HIST_SPEC.path))
    hist_inverse = np.linalg.inv(np.asarray(histology.affine, dtype=float))
    hist_voxels = (world_grid.reshape(-1, 4) @ hist_inverse.T)[:, :3]
    hist_values = map_coordinates(
        np.asarray(histology.dataobj, dtype=np.float32),
        hist_voxels.T,
        order=1,
        mode="constant",
        cval=0.0,
    ).reshape(height, width)
    hist_finite = hist_values[np.isfinite(hist_values)]
    hist_low, hist_high = np.percentile(hist_finite, [1.0, 99.0])
    hist_display = np.clip((hist_values - hist_low) / max(1e-12, hist_high - hist_low) * 255.0, 0, 255).astype(np.uint8)
    mask_display_u8 = np.where(mask_display > 0, 255, 0).astype(np.uint8)
    paired = Image.new("RGB", (width * 2, height), "white")
    paired.paste(Image.fromarray(hist_display, mode="L").convert("RGB"), (0, 0))
    mask_rgb = np.zeros((height, width, 3), dtype=np.uint8)
    mask_rgb[..., :] = 255
    mask_rgb[mask_display > 0] = (200, 35, 35)
    paired.paste(Image.fromarray(mask_rgb, mode="RGB"), (width, 0))
    paired.save(OUT / "section_3458_source_reconstruction_vs_mask_same_world_grid.png")
    Image.fromarray(overlay).save(OUT / "section_3458_region_exact_plane_diagnostic.png")
    Image.fromarray((mask_display * 255).astype(np.uint8)).save(OUT / "section_3458_region_exact_plane_mask.png")
    audit = {
        "status": "experimental exact-plane audit",
        "section_number": 3458,
        "section_id": SECTION_ID,
        "region": REGION_NAME,
        "provider_transform": "registered-section provider geometry; no new registration",
        "mask_source": mask_meta,
        "section_overview": {
            "shape_xyz": [int(v) for v in section_image.shape[:3]],
            "affine": np.asarray(section_image.affine, dtype=float).tolist(),
            "slice_index_y": int(section_slice),
            "raw_range": [int(v) for v in section_range],
            "display_shape_rows_cols": [int(v) for v in section_display.shape],
            "display_mapping": display_mapping,
            "plane_y_mm": section_y,
        },
        "source_reconstruction_check": {
            "source": str(HIST_SPEC.path),
            "source_identity": "full8_200um_optbal.nii.gz",
            "source_shape_xyz": [int(v) for v in histology.shape[:3]],
            "source_affine": np.asarray(histology.affine, dtype=float).tolist(),
            "source_units": list(histology.header.get_xyzt_units()),
            "common_grid_shape_rows_cols": [height, width],
            "common_grid_world_y_requested_mm": section_y,
            "intensity_interpolation": "linear in source voxel coordinates",
            "mask_interpolation": "nearest-neighbor categorical",
            "same_requested_world_y": True,
            "histology_nearest_slice_center_y_mm": float(histology.affine[1, 3] + round((section_y - histology.affine[1, 3]) / histology.affine[1, 1]) * histology.affine[1, 1]),
            "interpretation": "paired rendering check only; raw intensity differences are not alignment evidence",
        },
        "slab_overlap": {
            "mask_nonzero_voxels": int(mask_meta["mask_nonzero_voxels"]),
            "interpretation": "finite Y slab overlap only; not exact-plane intersection",
        },
        "exact_plane": exact_meta,
        "display_mismatch_check": {
            "section_background_threshold": ">245 on the raw overview display",
            "exact_plane_mask_pixels_on_background_like_display": int(np.count_nonzero(background_like)),
            "fraction_of_exact_plane_mask_pixels_on_background_like_display": float(
                np.count_nonzero(background_like) / max(1, np.count_nonzero(mask_display))
            ),
            "interpretation": "diagnostic mismatch remains; no tissue constraint or correction was applied",
        },
        "selected_actual_nonzero_display_pixel_uv": [int(v) for v in selected_uv],
        "selected_actual_nonzero_world_xyz_mm": selected_point["world_xyz_mm"],
        "selected_point_mapping": selected_point,
        "patch": {
            "bounds_mm": patch_bounds.__dict__,
            "shape_xyz": [int(v) for v in patch.shape[:3]],
            "affine": np.asarray(patch.affine, dtype=float).tolist(),
            "actual_resolution_mm": [float(v) for v in patch.header.get_zooms()[:3]],
            "non_background_voxels": int(np.count_nonzero(np.asanyarray(patch.dataobj) != 255)),
            "intersects_exact_plane_selected_mask_voxel": bool(intersects),
            "scientific_values_preserved": True,
        },
        "hemisphere": "provider identity is cortical layer 1 left; no hemisphere inferred from an x-coordinate",
        "anatomical_status": "Not independently reviewed; rendering and numerical geometry only",
        "conclusion": "Rendering consistency is supported; the cause of anatomical disagreement is not established.",
    }
    (OUT / "region_exact_plane_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({
        "selected_uv": selected_uv,
        "selected_world_xyz_mm": selected_point["world_xyz_mm"],
        "slab_nonzero": mask_meta["mask_nonzero_voxels"],
        "exact_plane_nonzero": exact_meta["exact_plane_nonzero_pixels"],
        "patch_shape": patch.shape,
        "patch_actual_resolution_mm": [float(v) for v in patch.header.get_zooms()[:3]],
        "patch_intersects_selected_mask_voxel": intersects,
    }, indent=2))


if __name__ == "__main__":
    main()
