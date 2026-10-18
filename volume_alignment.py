"""Experimental volume-level BigBrain MRI/histology inspection.

This module only relates the official donor MRI and the official native
histological reconstruction through their documented final-histological-space
world coordinates. It does not connect high-resolution siibra sections and it
does not claim anatomical correspondence.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw


@dataclass(frozen=True)
class VolumeSpec:
    name: str
    path: Path


def load_volume(spec: VolumeSpec):
    return nib.load(str(spec.path))


def volume_metadata(image) -> dict:
    """Return header facts used by the inspection viewer."""
    return {
        "shape_xyz": [int(value) for value in image.shape[:3]],
        "voxel_size_mm_xyz": [float(value) for value in image.header.get_zooms()[:3]],
        "orientation": "".join(nib.aff2axcodes(image.affine)),
        "affine": np.asarray(image.affine, dtype=float).tolist(),
    }


def voxel_center_world(image, voxel_xyz: np.ndarray) -> np.ndarray:
    return (np.asarray(image.affine, dtype=float) @ np.r_[voxel_xyz, 1.0])[:3]


def world_bounds(image) -> dict[str, list[float]]:
    shape = np.asarray(image.shape[:3], dtype=int)
    corners = []
    for ix in (0, int(shape[0] - 1)):
        for iy in (0, int(shape[1] - 1)):
            for iz in (0, int(shape[2] - 1)):
                corners.append(voxel_center_world(image, np.array([ix, iy, iz])))
    points = np.asarray(corners)
    return {
        "min": points.min(axis=0).astype(float).tolist(),
        "max": points.max(axis=0).astype(float).tolist(),
    }


def common_world_bounds(images: list) -> dict[str, list[float]]:
    bounds = [world_bounds(image) for image in images]
    minimum = np.max(np.asarray([item["min"] for item in bounds]), axis=0)
    maximum = np.min(np.asarray([item["max"] for item in bounds]), axis=0)
    if np.any(maximum <= minimum):
        raise ValueError("the two volumes have no overlapping voxel-centre world bounds")
    return {"min": minimum.tolist(), "max": maximum.tolist()}


def nearest_voxel_for_world(image, world_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    inverse = np.linalg.inv(np.asarray(image.affine, dtype=float))
    homogeneous = inverse @ np.r_[np.asarray(world_xyz, dtype=float), 1.0]
    voxel = np.rint(homogeneous[:3]).astype(int)
    shape = np.asarray(image.shape[:3], dtype=int)
    if np.any(voxel < 0) or np.any(voxel >= shape):
        raise ValueError(f"world point {world_xyz.tolist()} is outside the volume")
    return voxel, voxel_center_world(image, voxel)


def native_neighbourhood_crop(image, world_xyz: np.ndarray, half_width_mm: float):
    """Extract a native-grid 3-D neighbourhood with one source Y voxel.

    The selected plane is represented by the nearest source Y voxel. X and Z
    are expanded symmetrically in native voxels, and the returned affine is
    translated to the crop's first voxel centre. Values are taken directly
    from the image data proxy without display contrast or interpolation.
    """
    voxel, centre = nearest_voxel_for_world(image, np.asarray(world_xyz, dtype=float))
    zooms = np.asarray(image.header.get_zooms()[:3], dtype=float)
    radius_x = max(1, int(np.ceil(float(half_width_mm) / zooms[0])))
    radius_z = max(1, int(np.ceil(float(half_width_mm) / zooms[2])))
    shape = np.asarray(image.shape[:3], dtype=int)
    x0, x1 = max(0, voxel[0] - radius_x), min(shape[0], voxel[0] + radius_x + 1)
    y0, y1 = int(voxel[1]), int(voxel[1] + 1)
    z0, z1 = max(0, voxel[2] - radius_z), min(shape[2], voxel[2] + radius_z + 1)
    array = np.asarray(image.dataobj[slice(x0, x1), slice(y0, y1), slice(z0, z1)])
    translation = np.eye(4, dtype=float)
    translation[:3, 3] = [x0, y0, z0]
    affine = np.asarray(image.affine, dtype=float) @ translation
    crop = nib.Nifti1Image(array, affine)
    crop.header.set_zooms(tuple(float(value) for value in zooms))
    crop.header.set_xyzt_units(*image.header.get_xyzt_units())
    info = {
        "source_voxel_index_xyz": voxel.tolist(),
        "source_voxel_center_world_mm": centre.tolist(),
        "source_voxel_size_mm_xyz": zooms.tolist(),
        "source_header_dtype": str(image.header.get_data_dtype()),
        "crop_voxel_bounds_half_open_xyz": [[int(x0), int(x1)], [int(y0), int(y1)], [int(z0), int(z1)]],
        "crop_shape_xyz": [int(value) for value in array.shape],
        "loaded_value_dtype": str(array.dtype),
        "crop_affine": affine.tolist(),
        "y_selection": "one nearest source Y voxel; no interpolation",
        "value_operation": "direct source data-proxy values; no contrast adjustment, squeeze, or resampling",
        "clipped": bool(x0 == 0 or x1 == shape[0] or z0 == 0 or z1 == shape[2]),
    }
    return crop, info


def display_pixel_to_world(
    x_axis: np.ndarray,
    z_axis: np.ndarray,
    world_y: float,
    pixel_uv: tuple[float, float] | list[float],
) -> tuple[list[int], list[float]]:
    """Map displayed (u, v) to the explicit common X/Y/Z world grid."""
    u = int(np.clip(round(float(pixel_uv[0])), 0, len(x_axis) - 1))
    v = int(np.clip(round(float(pixel_uv[1])), 0, len(z_axis) - 1))
    return [u, v], [float(x_axis[u]), float(world_y), float(z_axis[v])]


def _sample_plane(image, world_y: float, x_axis: np.ndarray, z_axis: np.ndarray) -> tuple[np.ndarray, dict]:
    world_x, world_z = np.meshgrid(x_axis, z_axis, indexing="xy")
    world = np.stack(
        [world_x.ravel(), np.full(world_x.size, world_y), world_z.ravel()], axis=1
    )
    inverse = np.linalg.inv(np.asarray(image.affine, dtype=float))
    voxels = (inverse @ np.c_[world, np.ones(len(world))].T).T[:, :3]
    indices = np.rint(voxels).astype(int)
    shape = np.asarray(image.shape[:3], dtype=int)
    valid = np.all((indices >= 0) & (indices < shape), axis=1)
    plane = np.zeros(len(world), dtype=np.float32)
    data = np.asanyarray(image.dataobj)
    plane[valid] = np.asarray(data[tuple(indices[valid].T)], dtype=np.float32)
    return plane.reshape(len(z_axis), len(x_axis)), {
        "world_y_requested": float(world_y),
        "world_y_voxel_centres": sorted(set(float(value) for value in world[valid, 1])) if np.any(valid) else [],
        "grid_x_min": float(x_axis[0]),
        "grid_x_max": float(x_axis[-1]),
        "grid_z_min": float(z_axis[0]),
        "grid_z_max": float(z_axis[-1]),
        "grid_shape_rows_cols": [int(len(z_axis)), int(len(x_axis))],
    }


def _display_uint8(array: np.ndarray, low_percentile: float = 1.0, high_percentile: float = 99.0) -> np.ndarray:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)
    low, high = np.percentile(finite, [low_percentile, high_percentile])
    if high <= low:
        low, high = float(finite.min()), float(finite.max())
    if high <= low:
        return np.zeros(array.shape, dtype=np.uint8)
    return np.clip((array - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)


def render_inspection(
    mri,
    histology,
    output_dir: Path,
    world_y: float,
    crosshair_world: tuple[float, float] | None = None,
    grid_step_mm: float = 0.2,
) -> dict:
    """Write side-by-side and world-grid overlay images for inspection only."""
    common = common_world_bounds([mri, histology])
    x_axis = np.arange(common["min"][0], common["max"][0] + grid_step_mm * 0.5, grid_step_mm)
    z_axis = np.arange(common["min"][2], common["max"][2] + grid_step_mm * 0.5, grid_step_mm)
    mri_plane, mri_meta = _sample_plane(mri, world_y, x_axis, z_axis)
    hist_plane, hist_meta = _sample_plane(histology, world_y, x_axis, z_axis)
    mri_view = _display_uint8(mri_plane)
    hist_view = _display_uint8(hist_plane)

    output_dir.mkdir(parents=True, exist_ok=True)
    gap = 24
    panel_w, panel_h = mri_view.shape[1], mri_view.shape[0]
    side = Image.new("RGB", (panel_w * 2 + gap, panel_h + 42), "white")
    side.paste(Image.fromarray(mri_view).convert("RGB"), (0, 42))
    side.paste(Image.fromarray(hist_view).convert("RGB"), (panel_w + gap, 42))
    draw = ImageDraw.Draw(side)
    draw.text((8, 8), "MRI — alignment inspection", fill="black")
    draw.text((panel_w + gap + 8, 8), "native histology — alignment inspection", fill="black")
    if crosshair_world is not None:
        x_world, z_world = crosshair_world
        x_pixel = int(round((x_world - x_axis[0]) / grid_step_mm))
        z_pixel = int(round((z_world - z_axis[0]) / grid_step_mm)) + 42
        if 0 <= x_pixel < panel_w and 42 <= z_pixel < panel_h + 42:
            for offset in (0, panel_w + gap):
                draw.line((offset + x_pixel, 42, offset + x_pixel, panel_h + 41), fill=(255, 255, 0), width=1)
                draw.line((offset, z_pixel, offset + panel_w - 1, z_pixel), fill=(255, 255, 0), width=1)
    side.save(output_dir / "volume_side_by_side.png")

    overlay = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
    overlay[..., 0] = mri_view
    overlay[..., 1] = hist_view
    overlay[..., 2] = hist_view
    overlay_image = Image.fromarray(overlay, mode="RGB")
    if crosshair_world is not None:
        x_world, z_world = crosshair_world
        x_pixel = int(round((x_world - x_axis[0]) / grid_step_mm))
        z_pixel = int(round((z_world - z_axis[0]) / grid_step_mm))
        if 0 <= x_pixel < panel_w and 0 <= z_pixel < panel_h:
            draw = ImageDraw.Draw(overlay_image)
            draw.line((x_pixel, 0, x_pixel, panel_h - 1), fill=(255, 255, 0), width=1)
            draw.line((0, z_pixel, panel_w - 1, z_pixel), fill=(255, 255, 0), width=1)
    overlay_image.save(output_dir / "volume_world_overlay.png")

    selected = {}
    for name, image in (("mri", mri), ("histology", histology)):
        voxel, center = nearest_voxel_for_world(
            image,
            np.array([crosshair_world[0], world_y, crosshair_world[1]])
            if crosshair_world is not None
            else np.array([x_axis[len(x_axis) // 2], world_y, z_axis[len(z_axis) // 2]]),
        )
        selected[name] = {
            "voxel_index_xyz": voxel.tolist(),
            "voxel_center_world_mm": center.tolist(),
        }
    report = {
        "status": "alignment_inspection_not_validated_correspondence",
        "relationship": "official final histological processing-space world coordinates",
        "world_y_requested_mm": float(world_y),
        "common_voxel_center_bounds_mm": common,
        "grid_step_mm": float(grid_step_mm),
        "mri_plane": mri_meta,
        "histology_plane": hist_meta,
        "mri_header": volume_metadata(mri),
        "histology_header": volume_metadata(histology),
        "displayed_voxel_centres": selected,
        "images": ["volume_side_by_side.png", "volume_world_overlay.png"],
        "warning": "Display contrast is visualization only; this is not anatomical validation or registration.",
    }
    (output_dir / "alignment_inspection.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bounded MRI/native-histology alignment inspection views")
    parser.add_argument("--mri", type=Path, default=Path("outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz"))
    parser.add_argument("--histology", type=Path, default=Path("outputs/spatial_feasibility/full8_200um_optbal.nii.gz"))
    parser.add_argument("--out", type=Path, default=Path("outputs/spatial_feasibility/alignment_inspection"))
    parser.add_argument("--world-y", type=float, default=-25.792221575975418)
    args = parser.parse_args()
    report = render_inspection(load_volume(VolumeSpec("mri", args.mri)), load_volume(VolumeSpec("histology", args.histology)), args.out, args.world_y)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
