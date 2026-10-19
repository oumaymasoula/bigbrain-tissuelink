"""Full-affine world-grid comparison for registered overview diagnostics.

This is intentionally separate from the TissueLink interface.  It samples two
NIfTI-like images onto the same world X/Z grid at one requested world Y plane.
The source arrays and affines are never modified; display conversion is only
used when writing the inspection PNGs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw

from volume_alignment import _display_uint8, common_world_bounds


SELECTED_WORLD_XYZ_MM = (-24.40545688637588, -0.8595, 28.791557760299625)


def sample_world_xz_grid(
    image,
    world_y: float,
    x_axis: np.ndarray,
    z_axis: np.ndarray,
    *,
    fill_value: float = 0.0,
) -> tuple[np.ndarray, dict]:
    """Nearest-voxel sample using the complete source affine.

    Returned shape is ``(len(z_axis), len(x_axis))``: rows are world Z and
    columns are world X.  Off-diagonal affine terms are included by applying
    the full inverse affine to every world-grid point.
    """
    x_axis = np.asarray(x_axis, dtype=float)
    z_axis = np.asarray(z_axis, dtype=float)
    if x_axis.ndim != 1 or z_axis.ndim != 1 or len(x_axis) < 2 or len(z_axis) < 2:
        raise ValueError("world axes must be one-dimensional arrays with at least two samples")
    world_x, world_z = np.meshgrid(x_axis, z_axis, indexing="xy")
    world = np.stack(
        [world_x.ravel(), np.full(world_x.size, float(world_y)), world_z.ravel()],
        axis=1,
    )
    inverse = np.linalg.inv(np.asarray(image.affine, dtype=float))
    source_continuous = (inverse @ np.c_[world, np.ones(len(world))].T).T[:, :3]
    source_index = np.rint(source_continuous).astype(int)
    shape = np.asarray(image.shape[:3], dtype=int)
    valid = np.all((source_index >= 0) & (source_index < shape), axis=1)
    values = np.full(len(world), fill_value, dtype=np.float32)
    data = np.asanyarray(image.dataobj)
    values[valid] = np.asarray(data[tuple(source_index[valid].T)], dtype=np.float32)
    sampled_source_y = np.unique(
        (np.asarray(image.affine, dtype=float) @ np.c_[source_index[valid], np.ones(valid.sum())].T).T[:, 1]
    )
    return values.reshape(len(z_axis), len(x_axis)), {
        "world_y_mm": float(world_y),
        "grid_x_min_mm": float(x_axis[0]),
        "grid_x_max_mm": float(x_axis[-1]),
        "grid_z_min_mm": float(z_axis[0]),
        "grid_z_max_mm": float(z_axis[-1]),
        "grid_spacing_x_mm": float(np.median(np.diff(x_axis))),
        "grid_spacing_z_mm": float(np.median(np.diff(z_axis))),
        "grid_shape_rows_cols": [int(len(z_axis)), int(len(x_axis))],
        "source_shape_xyz": [int(value) for value in image.shape[:3]],
        "source_affine": np.asarray(image.affine, dtype=float).tolist(),
        "source_orientation": "".join(nib.aff2axcodes(image.affine)),
        "valid_sample_count": int(valid.sum()),
        "invalid_sample_count": int((~valid).sum()),
        "source_y_centres_mm": [float(value) for value in sampled_source_y],
        "sampling": "full inverse affine, nearest source voxel centre, no interpolation",
    }


def _mark(image: np.ndarray, uv: tuple[int, int]) -> np.ndarray:
    result = np.repeat(_display_uint8(image)[..., None], 3, axis=2)
    u, v = uv
    if 0 <= u < result.shape[1]:
        result[:, u, :] = [255, 255, 0]
    if 0 <= v < result.shape[0]:
        result[v, :, :] = [255, 255, 0]
    return result


def _checkerboard(first: np.ndarray, second: np.ndarray, tile: int = 32) -> np.ndarray:
    first_rgb = np.repeat(_display_uint8(first)[..., None], 3, axis=2)
    second_rgb = np.repeat(_display_uint8(second)[..., None], 3, axis=2)
    rows, cols = np.indices(first.shape)
    choose_first = ((rows // tile) + (cols // tile)) % 2 == 0
    result = np.empty_like(first_rgb)
    result[choose_first] = first_rgb[choose_first]
    result[~choose_first] = second_rgb[~choose_first]
    return result


def _opacity_overlay(first: np.ndarray, second: np.ndarray, opacity: float = 0.5) -> np.ndarray:
    first_rgb = np.repeat(_display_uint8(first)[..., None], 3, axis=2).astype(np.float32)
    second_rgb = np.repeat(_display_uint8(second)[..., None], 3, axis=2).astype(np.float32)
    # Red = registered overview; cyan = reconstructed histology.
    first_rgb[..., 1:] *= 0.25
    second_rgb[..., 0] *= 0.25
    return np.clip((1.0 - opacity) * first_rgb + opacity * second_rgb, 0, 255).astype(np.uint8)


def render_world_grid_pair(
    first: np.ndarray,
    second: np.ndarray,
    x_axis: np.ndarray,
    z_axis: np.ndarray,
    selected_world_xz: tuple[float, float],
    output_dir: Path,
    labels: tuple[str, str] = ("Registered overview", "Histology 200 µm"),
) -> dict[str, str]:
    """Save separately marked panels and a labelled side-by-side comparison."""
    if first.shape != second.shape:
        raise ValueError(f"comparison arrays must share a shape, got {first.shape} and {second.shape}")
    output_dir.mkdir(parents=True, exist_ok=True)
    u = int(np.clip(np.rint((selected_world_xz[0] - x_axis[0]) / np.median(np.diff(x_axis))), 0, len(x_axis) - 1))
    v = int(np.clip(np.rint((selected_world_xz[1] - z_axis[0]) / np.median(np.diff(z_axis))), 0, len(z_axis) - 1))
    panels = [_mark(first, (u, v)), _mark(second, (u, v))]
    paths = {}
    for key, panel in zip(("registered", "histology"), panels):
        path = output_dir / f"{key}_world_grid_selected.png"
        Image.fromarray(panel).save(path)
        paths[key] = str(path)

    gap, title_height = 24, 42
    height, width = panels[0].shape[:2]
    paired = Image.new("RGB", (width * 2 + gap, height + title_height), "white")
    paired.paste(Image.fromarray(panels[0]), (0, title_height))
    paired.paste(Image.fromarray(panels[1]), (width + gap, title_height))
    draw = ImageDraw.Draw(paired)
    draw.text((8, 8), labels[0], fill="black")
    draw.text((width + gap + 8, 8), labels[1], fill="black")
    draw.text((8, height + title_height - 16), f"horizontal world X: {x_axis[0]:.2f} … {x_axis[-1]:.2f} mm · vertical world Z", fill="black")
    draw.text((width + gap + 8, height + title_height - 16), f"horizontal world X: {x_axis[0]:.2f} … {x_axis[-1]:.2f} mm · vertical world Z", fill="black")
    paired_path = output_dir / "paired_world_grid_selected.png"
    paired.save(paired_path)
    paths["paired"] = str(paired_path)
    checker_path = output_dir / "checkerboard_world_grid_clean.png"
    Image.fromarray(_checkerboard(first, second)).save(checker_path)
    paths["checkerboard"] = str(checker_path)
    opacity_path = output_dir / "opacity_world_grid_clean.png"
    Image.fromarray(_opacity_overlay(first, second)).save(opacity_path)
    paths["opacity"] = str(opacity_path)
    for key, array in (("registered_clean", _display_uint8(first)), ("histology_clean", _display_uint8(second))):
        path = output_dir / f"{key}_world_grid.png"
        Image.fromarray(array).save(path)
        paths[key] = str(path)
    return paths


def diagnostic_metadata(first_meta: dict, second_meta: dict, selected_world_xyz_mm: tuple[float, float, float], paths: dict[str, str]) -> dict:
    x0 = first_meta["grid_x_min_mm"]
    z0 = first_meta["grid_z_min_mm"]
    dx = first_meta["grid_spacing_x_mm"]
    dz = first_meta["grid_spacing_z_mm"]
    selected_uv = [
        int(np.clip(np.rint((selected_world_xyz_mm[0] - x0) / dx), 0, first_meta["grid_shape_rows_cols"][1] - 1)),
        int(np.clip(np.rint((selected_world_xyz_mm[2] - z0) / dz), 0, first_meta["grid_shape_rows_cols"][0] - 1)),
    ]
    return {
        "selected_world_xyz_mm": [float(value) for value in selected_world_xyz_mm],
        "selected_point_shared_grid_uv": selected_uv,
        "comparison": "same world X/Z grid, same bounds, spacing and orientation",
        "registered_overview": first_meta,
        "histology_200um": second_meta,
        "display": {
            "horizontal_axis": "world X",
            "vertical_axis": "world Z",
            "marker": "selected world point projected onto the shared grid",
            "contrast": "independent 1st–99th percentile display conversion only",
        },
        "outputs": paths,
        "anatomical_status": "alignment inspection only; not anatomical validation",
    }


def run_real_diagnostic(output_dir: Path, selected_world_xyz_mm: tuple[float, float, float] = SELECTED_WORLD_XYZ_MM) -> dict:
    """Fetch #3458 overview and compare it with the local 200 µm volume."""
    from registered_section_demo import registered_context, registered_overview, registered_volumes

    section, bbox, provider, provider_volume, provider_info, provider_scale = registered_context()
    overview, _, _, _ = registered_overview(tuple(float(v) for v in (*bbox.minpoint, *bbox.maxpoint)))
    _, histology = registered_volumes()
    hist_bounds = common_world_bounds([histology])
    x_axis = np.arange(max(float(bbox.minpoint[0]), hist_bounds["min"][0]), min(float(bbox.maxpoint[0]), hist_bounds["max"][0]) + 0.2 * 0.5, 0.2)
    z_axis = np.arange(max(float(bbox.minpoint[2]), hist_bounds["min"][2]), min(float(bbox.maxpoint[2]), hist_bounds["max"][2]) + 0.2 * 0.5, 0.2)
    if not (len(x_axis) >= 2 and len(z_axis) >= 2):
        raise ValueError("registered overview and 200 µm volume have no usable common X/Z grid")
    first, first_meta = sample_world_xz_grid(overview, selected_world_xyz_mm[1], x_axis, z_axis)
    second, second_meta = sample_world_xz_grid(histology, selected_world_xyz_mm[1], x_axis, z_axis)
    paths = render_world_grid_pair(first, second, x_axis, z_axis, (selected_world_xyz_mm[0], selected_world_xyz_mm[2]), output_dir)
    metadata = diagnostic_metadata(first_meta, second_meta, selected_world_xyz_mm, paths)
    metadata["section"] = {
        "section_number": 3458,
        "section_id": getattr(section, "id", None) or "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        "provider_url": "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed",
        "reference_space": "BigBrain microscopic template (histology) / documented reference-space coordinates",
        "provider_transform_nm": np.asarray(provider_volume.transform_nm).tolist(),
        "provider_scale_key": provider_scale.key,
        "provider_scale_resolution_nm": np.asarray(provider_scale.res_nm).tolist(),
        "provider_dataset_order": provider_info.get("dataset_order"),
        "provider_metadata_source": "provider info and transform.json via installed siibra",
    }
    metadata["sampled_y"] = {
        "requested_world_y_mm": float(selected_world_xyz_mm[1]),
        "registered_overview_source_y_centres_mm": first_meta.get("source_y_centres_mm", []),
        "histology_200um_source_y_centres_mm": second_meta.get("source_y_centres_mm", []),
        "policy": "nearest source voxel centre after full affine inversion",
    }
    metadata["shared_grid"] = {
        "x_axis_mm": [float(x_axis[0]), float(x_axis[-1])],
        "z_axis_mm": [float(z_axis[0]), float(z_axis[-1])],
        "spacing_mm": [0.2, 0.2],
        "shape_rows_cols": [int(len(z_axis)), int(len(x_axis))],
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/geometry_diagnostic"))
    args = parser.parse_args()
    metadata = run_real_diagnostic(args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "shared_grid": metadata["shared_grid"], "outputs": metadata["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
