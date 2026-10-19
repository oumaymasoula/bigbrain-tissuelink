#!/usr/bin/env python3
"""Build the offline demonstration report from retained TissueLink artifacts."""

from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from external_roi_feasibility import sample_image_mask_on_patch
from collection_replay import import_collection_archive
from patch_collection import annotation_plane_from_image, collection_visual_report_html, collection_zip_bytes


MANUAL_ZIP = ROOT / "outputs/collection_regenerated/bigbrain_tissuelink_collection_corrected_v3.zip"
ROI_DIR = ROOT / "outputs/external_roi_feasibility/cerebra"


def png_bytes(array: np.ndarray) -> bytes:
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()


def translucent_mask_overlay(gray: np.ndarray, mask_xz: np.ndarray) -> np.ndarray:
    rgb = np.repeat(gray[..., None], 3, axis=2)
    sampled = np.asarray(mask_xz, dtype=bool).T
    red = np.asarray((235, 55, 55), dtype=np.float32)
    rgb[sampled] = (0.65 * rgb[sampled].astype(np.float32) + 0.35 * red).astype(np.uint8)
    edge = sampled.copy()
    interior = sampled.copy()
    interior[1:, :] &= sampled[:-1, :]
    interior[:-1, :] &= sampled[1:, :]
    interior[:, 1:] &= sampled[:, :-1]
    interior[:, :-1] &= sampled[:, 1:]
    edge &= ~interior
    rgb[edge] = red.astype(np.uint8)
    return rgb


def manual_entry() -> tuple[str, dict]:
    with zipfile.ZipFile(MANUAL_ZIP) as archive:
        row = next(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode("utf-8"))))
        patch_id = row["patch_id"]
        prefix = f"patches/{patch_id}"
        metadata = json.loads(archive.read(f"{prefix}/metadata.json"))
        metadata["report_source_files"] = [
            str(MANUAL_ZIP.relative_to(ROOT)),
            f"{prefix}/metadata.json",
            f"{prefix}/{patch_id}.nii.gz",
            f"{prefix}/{patch_id}_unmarked_plane.png",
            f"{prefix}/{patch_id}_marked_preview.png",
        ]
        return patch_id, {
            "patch_id": patch_id,
            "user_label": "Manual tissue selection · section 3458",
            "user_note": "Retained collection patch; reference-space placement not independently reviewed.",
            "metadata": metadata,
            "raw_nifti": archive.read(f"{prefix}/{patch_id}.nii.gz"),
            "unmarked_png": archive.read(f"{prefix}/{patch_id}_unmarked_plane.png"),
            "marked_png": archive.read(f"{prefix}/{patch_id}_marked_preview.png"),
        }


def roi_entry() -> tuple[str, dict]:
    feasibility_path = ROI_DIR / "cerebra_left_precentral_feasibility.json"
    feasibility = json.loads(feasibility_path.read_text(encoding="utf-8"))
    fetch = feasibility["fetch"]
    patch_path = ROI_DIR / "cerebra_left_precentral_section_patch.nii.gz"
    source_overlay_path = ROI_DIR / "cerebra_left_precentral_source_template_review.png"
    transformed_overlay_path = ROI_DIR / "cerebra_left_precentral_bigbrain_review.png"
    transformed_mask_path = ROI_DIR / "tpl-bigbrain_desc-cerebra_left_precentral_histological.nii.gz"
    patch_bytes = patch_path.read_bytes()
    if hashlib.sha256(patch_bytes).hexdigest() != fetch["patch_sha256"]:
        raise ValueError("saved CerebrA patch checksum does not match its feasibility record")
    overlap_by_y = fetch["mask_nonpadding_overlap_by_y"]
    documented_planes = [index for index, count in enumerate(overlap_by_y) if int(count) > 0]
    if len(documented_planes) != 1:
        raise ValueError(f"source plane is not uniquely documented: {documented_planes}")
    source_y = documented_planes[0]
    patch_image = nib.load(patch_path)
    transformed_mask = nib.load(transformed_mask_path)
    unmarked, mapping = annotation_plane_from_image(patch_image, source_y)
    mask_on_patch = sample_image_mask_on_patch(transformed_mask, patch_image)
    overlay = translucent_mask_overlay(unmarked, mask_on_patch[:, source_y, :])
    patch_id = "patch-cerebra-left-precentral-section-3146"
    metadata = {
        "workflow": "experimental_template_roi",
        "anatomical_status": "Awaiting independent review",
        "section_id": fetch["section_id"],
        "section_number": fetch["section_number"],
        "coordinate_space": "BigBrain microscopic template (histology)",
        "requested_bounds_mm": fetch["requested_bounds_mm"],
        "selected_mask_world_xyz_mm": fetch["selected_world_xyz_mm"],
        "actual_shape_xyz": fetch["patch_shape_xyz"],
        "actual_voxel_size_mm_xyz": fetch["patch_voxel_size_mm_xyz"],
        "actual_affine": fetch["patch_affine"],
        "exported_nifti_sha256": fetch["patch_sha256"],
        "input_roi_filename": "tpl-icbm_desc-cerebra_left_precentral.nii",
        "supported_template": "ICBM 2009c nonlinear symmetric (MNI152, tal_nlin_sym_09c), 1 mm",
        "input_roi_sha256": feasibility["transform"]["input_sha256"],
        "roi_name": "CerebrA left Precentral (label 86)",
        "roi_provenance": feasibility["atlas_identity"],
        "transform_provenance": feasibility,
        "annotation_plane_mapping": {
            **mapping,
            "plane_selection_evidence": "unique nonzero entry in saved fetch.mask_nonpadding_overlap_by_y",
            "saved_overlap_by_y": overlap_by_y,
        },
        "report_source_files": [
            str(feasibility_path.relative_to(ROOT)),
            str(patch_path.relative_to(ROOT)),
            str(source_overlay_path.relative_to(ROOT)),
            str(transformed_overlay_path.relative_to(ROOT)),
            str(transformed_mask_path.relative_to(ROOT)),
        ],
    }
    return patch_id, {
        "patch_id": patch_id,
        "user_label": "Template ROI · CerebrA left Precentral · section 3146",
        "user_note": "Technical transform and overlap evidence; anatomical placement awaits independent review.",
        "metadata": metadata,
        "raw_nifti": patch_bytes,
        "unmarked_png": png_bytes(unmarked),
        "marked_png": png_bytes(overlay),
        "source_roi_overlay_png": source_overlay_path.read_bytes(),
        "transformed_roi_overlay_png": transformed_overlay_path.read_bytes(),
    }


def main() -> None:
    manual_id, manual = manual_entry()
    roi_id, roi = roi_entry()
    collection = {manual_id: manual, roi_id: roi}
    output_dir = ROOT / "outputs/demonstration"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = output_dir / f"bigbrain_tissuelink_demonstration_report_{stamp}.html"
    output.write_bytes(collection_visual_report_html(collection))
    archive = output_dir / f"bigbrain_tissuelink_demonstration_collection_{stamp}.zip"
    archive.write_bytes(collection_zip_bytes(collection))
    restored = import_collection_archive(archive.read_bytes())
    if set(restored["collection"]) != set(collection):
        raise ValueError("round-trip collection identities differ")
    for patch_id, original in collection.items():
        imported = restored["collection"][patch_id]
        for key in ("raw_nifti", "unmarked_png", "marked_png"):
            if imported[key] != original[key]:
                raise ValueError(f"{patch_id}: round-trip mismatch for {key}")
        if imported["metadata"] != original["metadata"]:
            raise ValueError(f"{patch_id}: round-trip metadata mismatch")
    reopened_report = output_dir / f"bigbrain_tissuelink_reopened_report_{stamp}.html"
    reopened_report.write_bytes(collection_visual_report_html(restored["collection"]))
    verification = output_dir / f"bigbrain_tissuelink_verification_{stamp}.json"
    verification.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": "existing saved manual collection and preserved CerebrA feasibility outputs",
        "transform_or_tissue_fetch_performed": False,
        "collection_zip": str(archive),
        "initial_html": str(output),
        "reopened_html": str(reopened_report),
        "patch_ids": list(collection),
        "round_trip_status": "passed",
        "inspection": restored["inspection"]["reports"],
        "warnings": restored["warnings"],
    }, indent=2), encoding="utf-8")
    print(json.dumps({"html": str(output), "zip": str(archive), "reopened_html": str(reopened_report), "verification": str(verification)}))


if __name__ == "__main__":
    main()
