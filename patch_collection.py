"""Session-scoped collection helpers for fetched detailed patches."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from typing import Mapping

import numpy as np


COLLECTION_MAX_BYTES = 50 * 1024 * 1024


def annotation_plane_from_image(image, slice_index: int = 0) -> tuple[np.ndarray, dict]:
    """Build the unmarked annotation PNG plane and its independent mapping.

    This is intentionally separate from the interactive registered-section
    display convention.  Scientific NIfTI data are ``(x, y, z)``; this plane
    is ``data[:, slice_index, :].T`` so ``PNG[v, u]`` is
    ``data[u, slice_index, v]``: PNG columns are source X and rows are
    source Z. Only display normalization is applied.
    """
    data = np.asanyarray(image.dataobj)
    if data.ndim != 3 or not 0 <= int(slice_index) < data.shape[1]:
        raise ValueError(f"annotation plane requires a 3-D image and valid y slice; got {data.shape}")
    plane_xz = np.asarray(data[:, int(slice_index), :])
    finite = plane_xz[np.isfinite(plane_xz)]
    if finite.size == 0:
        display = np.zeros(plane_xz.T.shape, dtype=np.uint8)
        low, high = 0.0, 0.0
    else:
        low, high = np.percentile(finite, [1.0, 99.0])
        if high <= low:
            low, high = float(finite.min()), float(finite.max())
        if high <= low:
            display = np.zeros(plane_xz.T.shape, dtype=np.uint8)
        else:
            display = np.clip((plane_xz.astype(np.float32) - low) * 255.0 / (high - low), 0, 255).astype(np.uint8).T
    return display, {
        "source_plane_expression": f"data[:,{int(slice_index)},:].T",
        "source_slice_index_y": int(slice_index),
        "png_shape_rows_cols": [int(value) for value in display.shape],
        "png_horizontal_source_axis": "x",
        "png_vertical_source_axis": "z",
        "pixel_to_nifti_voxel": "(u, v) -> (u, slice_index_y, v)",
        "transpose": True,
        "flip_horizontal": False,
        "flip_vertical": False,
        "display_normalization": "independent 1st–99th percentile linear uint8 conversion",
        "normalization_low": float(low),
        "normalization_high": float(high),
        "scientific_values_preserved": True,
    }


def patch_id_for(raw_nifti: bytes, metadata: Mapping) -> str:
    """Return a deterministic ID for one source patch and its geometry."""
    identity = {
        "section_id": metadata.get("section_id"),
        "requested_bounds_mm": metadata.get("requested_bounds_mm"),
        "actual_affine": metadata.get("actual_affine"),
        "actual_voxel_size_mm_xyz": metadata.get("actual_voxel_size_mm_xyz"),
        "source_array_sha256": metadata.get("source_array_sha256"),
    }
    digest = hashlib.sha256(
        raw_nifti + json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"patch-{digest[:16]}"


def entry_bytes(entry: Mapping) -> int:
    return sum(len(entry.get(name, b"")) for name in ("raw_nifti", "unmarked_png", "marked_png"))


def collection_bytes(collection: Mapping[str, Mapping]) -> int:
    return sum(entry_bytes(entry) for entry in collection.values())


def add_entry(collection: dict, entry: Mapping, max_bytes: int = COLLECTION_MAX_BYTES) -> str:
    """Add an entry, rejecting duplicates and over-budget collections."""
    patch_id = str(entry["patch_id"])
    if patch_id in collection:
        raise ValueError(f"patch {patch_id} is already in the collection")
    projected = collection_bytes(collection) + entry_bytes(entry)
    if projected > max_bytes:
        raise ValueError(f"collection limit exceeded ({projected:,} > {max_bytes:,} bytes)")
    collection[patch_id] = dict(entry)
    return patch_id


def collection_zip_bytes(collection: Mapping[str, Mapping]) -> bytes:
    """Build one portable ZIP with raw data, annotation-ready planes and manifest."""
    output = io.BytesIO()
    fieldnames = (
        "patch_id", "user_label", "section_id", "section_number", "source_url",
        "coordinate_space", "requested_bounds_mm", "actual_shape_xyz",
        "actual_voxel_size_mm_xyz", "actual_affine", "source_array_sha256",
        "exported_nifti_sha256", "note",
    )
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        rows = []
        for patch_id, entry in collection.items():
            metadata = dict(entry["metadata"])
            prefix = f"patches/{patch_id}"
            archive.writestr(f"{prefix}/{patch_id}.nii.gz", entry["raw_nifti"])
            archive.writestr(f"{prefix}/{patch_id}_unmarked_plane.png", entry["unmarked_png"])
            archive.writestr(f"{prefix}/{patch_id}_marked_preview.png", entry["marked_png"])
            archive.writestr(f"{prefix}/metadata.json", json.dumps(metadata, indent=2) + "\n")
            rows.append({
                "patch_id": patch_id,
                "user_label": entry.get("user_label", ""),
                "section_id": metadata.get("section_id", ""),
                "section_number": metadata.get("section_number", ""),
                "source_url": metadata.get("provider_url", ""),
                "coordinate_space": metadata.get("coordinate_space", ""),
                "requested_bounds_mm": json.dumps(metadata.get("requested_bounds_mm", []), separators=(",", ":")),
                "actual_shape_xyz": json.dumps(metadata.get("actual_shape_xyz", []), separators=(",", ":")),
                "actual_voxel_size_mm_xyz": json.dumps(metadata.get("actual_voxel_size_mm_xyz", []), separators=(",", ":")),
                "actual_affine": json.dumps(metadata.get("actual_affine", []), separators=(",", ":")),
                "source_array_sha256": metadata.get("source_array_sha256", ""),
                "exported_nifti_sha256": metadata.get("exported_nifti_sha256", ""),
                "note": entry.get("user_note", ""),
            })
        manifest = io.StringIO()
        writer = csv.DictWriter(manifest, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr("manifest.csv", manifest.getvalue())
        archive.writestr(
            "README.txt",
            "BigBrain TissueLink patch collection\n\n"
            "Each patch contains a raw native-grid NIfTI, an unmarked display plane "
            "for external annotation, a separate marked preview, and metadata.json.\n"
            "The unmarked plane is the contrast-adjusted data[:,y_slice,:].T view, "
            "where y_slice is the recorded source slice index: PNG[v,u] comes "
            "from source data[u,y_slice,v], with columns as source X and rows "
            "as source Z; see metadata.json "
            "for the separate PNG-pixel-to-NIfTI mapping.\n"
            "PNG planes are visualization/annotation aids; NIfTI values and affines "
            "are the scientific data. Collection state is session-scoped and is not "
            "saved across browser sessions unless this ZIP is downloaded.\n",
        )
    return output.getvalue()
