"""Session-scoped collection helpers for fetched detailed patches."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from typing import Mapping


COLLECTION_MAX_BYTES = 50 * 1024 * 1024


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
            "PNG planes are visualization/annotation aids; NIfTI values and affines "
            "are the scientific data. Collection state is session-scoped and is not "
            "saved across browser sessions unless this ZIP is downloaded.\n",
        )
    return output.getvalue()
