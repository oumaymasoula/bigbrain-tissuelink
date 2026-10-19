"""Audit the preserved CerebrA left-precentral BigBrainWarp experiment.

This script consumes the already transformed mask.  It never reruns the
BigBrainWarp transform and refuses to overwrite any review artifact.
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
from external_roi_feasibility import image_geometry, sample_image_mask_on_patch, sample_section_plane


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "external_roi_feasibility" / "cerebra"
ATLAS = OUT / "mni_icbm152_CerebrA_tal_nlin_sym_09c.nii"
ROI = OUT / "cerebra_left_precentral_label86_roi.nii.gz"
ICBM_INPUT = OUT / "tpl-icbm_desc-cerebra_left_precentral.nii"
TRANSFORMED = OUT / "tpl-bigbrain_desc-cerebra_left_precentral_histological.nii.gz"
BIGBRAIN = ROOT / "outputs" / "spatial_feasibility" / "full8_200um_optbal.nii.gz"
REFERENCE_MINC = OUT / "ref_resampled.mnc"
LABEL = 86


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def reserve(path: Path) -> Path:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def normalize(plane: np.ndarray, categorical: bool = False) -> np.ndarray:
    values = np.asarray(plane, dtype=float)
    if categorical:
        return np.where(values > 0, 45 + (values * 37) % 190, 0).astype(np.uint8)
    nonzero = values[values != 0]
    low, high = np.percentile(nonzero if len(nonzero) else values, [1, 99])
    return np.clip((values - low) * 255 / max(high - low, 1), 0, 255).astype(np.uint8)


def overlay_view(background: np.ndarray, mask: np.ndarray, title: str, output: Path, categorical: bool = False) -> None:
    if output.exists():
        return
    gray = normalize(background, categorical=categorical).T
    rgb = np.repeat(gray[..., None], 3, axis=2)
    selected = np.asarray(mask, dtype=bool).T
    rgb[selected] = (235, 55, 55)
    canvas = Image.fromarray(rgb)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, min(canvas.width, 900), 28), fill=(0, 0, 0))
    draw.text((8, 7), title, fill=(255, 255, 0))
    canvas.save(output)


def sample_mask_plane(mask: nib.spatialimages.SpatialImage, reference: nib.spatialimages.SpatialImage, y_index: int) -> np.ndarray:
    shape = (reference.shape[0], reference.shape[2])
    ii, kk = np.indices(shape, dtype=float)
    ijk = np.column_stack((ii.ravel(), np.full(ii.size, y_index), kk.ravel()))
    world = nib.affines.apply_affine(reference.affine, ijk)
    source = np.rint(nib.affines.apply_affine(np.linalg.inv(mask.affine), world)).astype(int)
    valid = np.all((source >= 0) & (source < np.asarray(mask.shape[:3])), axis=1)
    data = np.asarray(mask.dataobj)
    sampled = np.zeros(len(source), dtype=bool)
    sampled[valid] = data[tuple(source[valid].T)] != 0
    return sampled.reshape(shape)


def main() -> None:
    atlas = nib.load(ATLAS)
    roi = nib.load(ROI)
    icbm_input = nib.load(ICBM_INPUT)
    transformed = nib.load(TRANSFORMED)
    bigbrain = nib.load(BIGBRAIN)
    atlas_data = np.asarray(atlas.dataobj)
    roi_data = np.asarray(roi.dataobj)
    transformed_data = np.asarray(transformed.dataobj)

    if atlas.shape != icbm_input.shape or not np.array_equal(atlas.affine, icbm_input.affine):
        raise RuntimeError("CerebrA atlas and BigBrainWarp input are not on the same exact grid")
    if not np.array_equal(roi_data, atlas_data == LABEL):
        raise RuntimeError("saved ROI is not exactly CerebrA label 86")

    source_y = int(np.argmax(np.count_nonzero(roi_data, axis=(0, 2))))
    source_world_y = float(nib.affines.apply_affine(atlas.affine, [0, source_y, 0])[1])
    overlay_view(atlas_data[:, source_y, :], roi_data[:, source_y, :],
                 f"CerebrA label 86 · left Precentral · source Y={source_world_y:.3f} mm",
                 OUT / "cerebra_left_precentral_source_template_review.png", categorical=True)

    transformed_y = int(np.argmax(np.count_nonzero(transformed_data, axis=(0, 2))))
    transformed_world_y = float(nib.affines.apply_affine(transformed.affine, [0, transformed_y, 0])[1])
    bigbrain_y = int(np.rint(nib.affines.apply_affine(np.linalg.inv(bigbrain.affine), [0, transformed_world_y, 0])[1]))
    if not 0 <= bigbrain_y < bigbrain.shape[1]:
        raise RuntimeError("selected transformed-mask plane falls outside BigBrain reconstruction")
    bigbrain_plane = np.asarray(bigbrain.dataobj[:, bigbrain_y, :])
    bigbrain_mask = sample_mask_plane(transformed, bigbrain, bigbrain_y)
    actual_bigbrain_y = float(nib.affines.apply_affine(bigbrain.affine, [0, bigbrain_y, 0])[1])
    overlay_view(bigbrain_plane, bigbrain_mask,
                 f"Transformed CerebrA left Precentral on BigBrain 200 um · Y={actual_bigbrain_y:.3f} mm",
                 OUT / "cerebra_left_precentral_bigbrain_review.png")

    plane_results = []
    for section in section_catalogue():
        test = sample_section_plane(transformed, section, spacing_mm=2.0)
        plane_results.append({
            "section_number": section["section_number"], "section_id": section["id"],
            "source_url": section["source_url"], "section_plane_y_mm": section["section_plane_y_mm"],
            "plane_test": test,
        })
    intersecting = [row for row in plane_results if row["plane_test"].get("nonzero_pixels", 0)]
    if not intersecting:
        raise RuntimeError("no registered section intersects the transformed mask")

    selected = intersecting[0]
    point = np.asarray(selected["plane_test"]["first_nonzero_world_xyz_mm"], dtype=float)
    y = float(selected["section_plane_y_mm"])
    bounds = Bounds(float(point[0] - 1), y - 0.04, float(point[2] - 1), float(point[0] + 1), y + 0.04, float(point[2] + 1))
    patch, _, _ = fetch_crop(bounds, resolution_mm=0.01, max_bytes=5 * 1024 * 1024, section_id=selected["section_id"])
    patch_data = np.asarray(patch.dataobj)
    mask_on_patch = sample_image_mask_on_patch(transformed, patch)
    nonpadding = (patch_data > 0) & (patch_data < 255)
    overlap_by_y = [int(np.count_nonzero(mask_on_patch[:, i, :] & nonpadding[:, i, :])) for i in range(patch.shape[1])]
    patch_y = int(np.argmax(overlap_by_y))
    overlay_view(patch_data[:, patch_y, :], mask_on_patch[:, patch_y, :],
                 f"Section #{selected['section_number']} · transformed-mask overlap · patch Y index {patch_y}",
                 OUT / "cerebra_left_precentral_section_patch_review.png")
    patch_path = reserve(OUT / "cerebra_left_precentral_section_patch.nii.gz")
    nib.save(patch, patch_path)

    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "technical_checks_passed_anatomical_review_pending",
        "atlas_identity": {
            "name": "CerebrA cortical atlas", "release_file": ATLAS.name,
            "space_from_release_filename_and_header": "mni_icbm152 tal_nlin_sym_09c",
            "label": LABEL, "label_name": "Precentral", "hemisphere": "left",
            "label_table_columns": "RH Label=35; LH Labels=86",
            "atlas_sha256": sha256(ATLAS), "label_table_sha256": sha256(OUT / "CerebrA_LabelDetails.csv"),
        },
        "compatibility": {
            "exact_grid_match_with_bigbrainwarp_input": True,
            "shape_equal": atlas.shape == icbm_input.shape,
            "affine_array_equal": bool(np.array_equal(atlas.affine, icbm_input.affine)),
            "source_affine": atlas.affine.tolist(), "orientation": list(nib.aff2axcodes(atlas.affine)),
            "roi_is_exact_label_86_mask": True,
        },
        "transform": {
            "direction": "ICBM2009c symmetric input to BigBrain histological output; upstream icbm_to_bigbrain.sh inverts BigBrainHist-to-ICBM2009sym-nonlin.xfm",
            "interpolation": "nearest-neighbour",
            "command_provenance_limit": "No CerebrA transform shell log was saved. Direction follows the fixed upstream script; nearest-neighbour is supported by the saved binary output and reference-MINC history, but the exact invocation cannot be quoted verbatim.",
            "input": image_geometry(icbm_input), "output": image_geometry(transformed),
            "input_sha256": sha256(ICBM_INPUT), "output_sha256": sha256(TRANSFORMED),
            "reference_minc_sha256": sha256(REFERENCE_MINC),
        },
        "review_views": {
            "source": "cerebra_left_precentral_source_template_review.png",
            "bigbrain": "cerebra_left_precentral_bigbrain_review.png",
            "source_world_y_mm": source_world_y, "bigbrain_world_y_mm": actual_bigbrain_y,
            "anatomical_status": "not independently reviewed",
        },
        "intersecting_section_count": len(intersecting),
        "intersecting_sections": [{"section_number": x["section_number"], "section_id": x["section_id"], "plane_y_mm": x["section_plane_y_mm"], "nonzero_pixels": x["plane_test"]["nonzero_pixels"]} for x in intersecting],
        "section_plane_results": plane_results,
        "fetch": {
            "section_number": selected["section_number"], "section_id": selected["section_id"],
            "selected_world_xyz_mm": point.tolist(), "requested_bounds_mm": list(bounds.__dict__.values()),
            "patch_shape_xyz": list(patch.shape[:3]), "patch_affine": patch.affine.tolist(),
            "patch_voxel_size_mm_xyz": list(map(float, patch.header.get_zooms()[:3])),
            "mask_nonpadding_overlap_by_y": overlap_by_y, "mask_nonpadding_overlap_voxels": int(sum(overlap_by_y)),
            "patch_sha256": sha256(patch_path), "anatomical_status": "not independently reviewed",
        },
    }
    reserve(OUT / "cerebra_left_precentral_feasibility.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"intersections": len(intersecting), "selected_section": selected["section_number"], "overlap_voxels": sum(overlap_by_y)}, indent=2))


if __name__ == "__main__":
    main()
