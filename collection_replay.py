"""Safe inspection and replay of TissueLink patch-collection exports.

The replay manifest is a parameter record, not an executable recipe.  URLs
are provenance only; fetching is restricted to the configured registered
section provider and uses the recorded section ID.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import json
import posixpath
import tempfile
import zipfile
from typing import Callable, Mapping

import nibabel as nib
import numpy as np

from bigbrain_cutout import Bounds, MAX_BYTES


MANIFEST_SCHEMA_VERSION = "1.0"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_MEMBER_BYTES = 60 * 1024 * 1024
MAX_PATCHES = 100
AFFINE_ATOL_MM = 1e-5
VOXEL_SIZE_ATOL_MM = 1e-6
SUPPORTED_PROVIDER_HOSTS = frozenset({"1um.brainatlas.eu"})


def _software_versions() -> dict[str, str]:
    names = ("numpy", "nibabel", "siibra", "streamlit")
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    return versions


def _json(value):
    return json.loads(json.dumps(value, default=str))


def build_manifest(collection: Mapping[str, Mapping], software_versions: Mapping[str, str] | None = None) -> dict:
    """Build a versioned, non-executable replay manifest from collection entries."""
    patches = []
    for patch_id, entry in collection.items():
        metadata = dict(entry.get("metadata", {}))
        bounds = metadata.get("requested_bounds_mm")
        expected_shape = metadata.get("expected_shape_xyz", metadata.get("actual_shape_xyz"))
        expected_affine = metadata.get("expected_affine", metadata.get("actual_affine"))
        provider_url = str(metadata.get("provider_url", ""))
        patches.append({
            "patch_id": str(patch_id),
            "section_id": metadata.get("section_id"),
            "provider": "siibra-registered-section",
            "provider_url": provider_url,
            "coordinate_space": metadata.get("coordinate_space"),
            "requested_bounds_mm": _json(bounds),
            "requested_resolution_mm": metadata.get("requested_resolution_mm"),
            "request_budget_bytes": int(metadata.get("request_budget_bytes", MAX_BYTES)),
            "expected_shape_xyz": _json(expected_shape),
            "expected_affine": _json(expected_affine),
            "actual_resolution_mm_xyz": _json(metadata.get("actual_voxel_size_mm_xyz")),
            "source_array_sha256": metadata.get("source_array_sha256"),
            "exported_nifti_sha256": metadata.get("exported_nifti_sha256"),
            "annotation_png_mapping": _json(metadata.get("annotation_png_mapping")),
            "software_versions": _json(metadata.get("software_versions", software_versions or _software_versions())),
            "source_identity": {
                "section_number": metadata.get("section_number"),
                "section_name": metadata.get("section_name"),
                "retrieved_at_utc": metadata.get("retrieved_at_utc"),
            },
        })
    return {
        "schema": "bigbrain-tissuelink.collection-replay",
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_role": "bounded replay parameters and scientific expectations",
        "created_by": "BigBrain TissueLink",
        "software_versions": _json(software_versions or _software_versions()),
        "limits": {
            "max_request_bytes": MAX_BYTES,
            "max_archive_bytes": MAX_ARCHIVE_BYTES,
            "max_decompressed_bytes": MAX_DECOMPRESSED_BYTES,
            "max_patch_count": MAX_PATCHES,
        },
        "patches": patches,
    }


def _safe_member(name: str) -> None:
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError(f"unsafe archive path: {name!r}")
    normalized = posixpath.normpath(name)
    if normalized == "." or normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"unsafe archive path: {name!r}")


def _safe_patch_id(patch_id: str) -> None:
    if not patch_id or patch_id in {".", ".."} or "/" in patch_id or "\\" in patch_id or ".." in patch_id:
        raise ValueError(f"unsafe patch ID: {patch_id!r}")


def _read_zip(archive_bytes: bytes) -> dict[str, bytes]:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"archive exceeds {MAX_ARCHIVE_BYTES:,} byte limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("uploaded collection is not a valid ZIP archive") from exc
    members: dict[str, bytes] = {}
    total = 0
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_PATCHES * 8 + 10:
            raise ValueError("archive contains too many members")
        for info in infos:
            _safe_member(info.filename)
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"archive member exceeds size limit: {info.filename}")
            total += info.file_size
            if total > MAX_DECOMPRESSED_BYTES:
                raise ValueError("archive decompressed size exceeds limit")
            if info.filename in members:
                raise ValueError(f"duplicate archive member: {info.filename}")
            members[info.filename] = archive.read(info)
    return members


def _legacy_manifest(members: Mapping[str, bytes]) -> dict:
    """Adapt pre-manifest collection ZIPs without changing their originals."""
    patches = []
    for name, raw_metadata in members.items():
        if not name.startswith("patches/") or not name.endswith("/metadata.json"):
            continue
        metadata = json.loads(raw_metadata.decode("utf-8"))
        patch_id = name.split("/", 2)[1]
        entry = build_manifest({patch_id: {"metadata": metadata}})["patches"][0]
        entry["compatibility_warnings"] = [
            "legacy export has no explicit replay manifest; fields were adapted from metadata.json",
            "legacy export may not contain request budget, expected shape, or software versions",
        ]
        patches.append(entry)
    if not patches:
        raise ValueError("collection contains no compatible patch metadata")
    return {
        "schema": "bigbrain-tissuelink.collection-replay",
        "schema_version": "legacy-adapter-1",
        "manifest_role": "compatibility view of a pre-manifest export; originals preserved",
        "software_versions": {},
        "limits": {"max_request_bytes": MAX_BYTES, "max_patch_count": MAX_PATCHES},
        "patches": patches,
    }


def _manifest(members: Mapping[str, bytes]) -> tuple[dict, bool]:
    if "manifest.json" in members:
        try:
            manifest = json.loads(members["manifest.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("manifest.json is not valid UTF-8 JSON") from exc
        if manifest.get("schema") != "bigbrain-tissuelink.collection-replay":
            raise ValueError("unsupported collection manifest schema")
        if not isinstance(manifest.get("patches"), list):
            raise ValueError("manifest patches must be a list")
        return manifest, False
    return _legacy_manifest(members), True


def _nifti(raw: bytes):
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as handle:
        handle.write(raw)
        handle.flush()
        loaded = nib.load(handle.name)
        # Materialize before the temporary file disappears; replay inspection
        # must not retain a path into the uploaded archive's transient storage.
        return nib.Nifti1Image(np.asanyarray(loaded.dataobj), loaded.affine, loaded.header.copy())


def _nifti_bytes(image) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as handle:
        nib.save(image, handle.name)
        handle.seek(0)
        return handle.read()


def reopen_collection(archive_bytes: bytes) -> dict:
    """Inspect a ZIP locally; never fetches data or executes imported content."""
    members = _read_zip(archive_bytes)
    manifest, legacy = _manifest(members)
    patches = manifest["patches"]
    if len(patches) > MAX_PATCHES:
        raise ValueError(f"collection has too many patches ({len(patches)} > {MAX_PATCHES})")
    reports = []
    for patch in patches:
        patch_id = str(patch.get("patch_id", ""))
        try:
            _safe_patch_id(patch_id)
        except ValueError as exc:
            reports.append({"patch_id": patch_id, "status": "changed", "errors": [str(exc)], "section_id": patch.get("section_id")})
            continue
        prefix = f"patches/{patch_id}/"
        raw_name = f"{prefix}{patch_id}.nii.gz"
        metadata_name = f"{prefix}metadata.json"
        errors = []
        if not patch_id or raw_name not in members or metadata_name not in members:
            errors.append("missing patch NIfTI or metadata")
        raw = members.get(raw_name)
        if raw is not None:
            archived_checksum = hashlib.sha256(raw).hexdigest()
            expected_serialized = patch.get("exported_nifti_sha256")
            if expected_serialized and archived_checksum != expected_serialized:
                errors.append("serialized NIfTI checksum differs from manifest")
            try:
                image = _nifti(raw)
                raw_checksum = hashlib.sha256(np.asanyarray(image.dataobj).tobytes(order="C")).hexdigest()
                if patch.get("source_array_sha256") and raw_checksum != patch["source_array_sha256"]:
                    errors.append("raw-array checksum differs from manifest")
                if patch.get("expected_shape_xyz") and list(image.shape) != list(patch["expected_shape_xyz"]):
                    errors.append("shape differs from manifest")
                if patch.get("expected_affine") and not np.allclose(image.affine, patch["expected_affine"], atol=AFFINE_ATOL_MM, rtol=0):
                    errors.append("affine differs from manifest tolerance")
            except Exception as exc:
                errors.append(f"NIfTI inspection failed: {exc}")
        reports.append({"patch_id": patch_id, "status": "reopened" if not errors else "changed", "errors": errors, "section_id": patch.get("section_id")})
    return {"manifest": manifest, "legacy_adapter": legacy, "reports": reports, "member_count": len(members)}


def import_collection_archive(archive_bytes: bytes) -> dict:
    """Restore retained collection files locally without fetching or executing content."""
    members = _read_zip(archive_bytes)
    inspection = reopen_collection(archive_bytes)
    labels: dict[str, dict] = {}
    if "manifest.csv" in members:
        try:
            labels = {row.get("patch_id", ""): row for row in csv.DictReader(io.StringIO(members["manifest.csv"].decode("utf-8")))}
        except (UnicodeDecodeError, csv.Error):
            labels = {}
    collection = {}
    warnings = []
    for report in inspection["reports"]:
        patch_id = report["patch_id"]
        if report["status"] != "reopened":
            warnings.append(f"{patch_id}: not restored because scientific inspection reported {report['errors']}")
            continue
        prefix = f"patches/{patch_id}"
        metadata = json.loads(members[f"{prefix}/metadata.json"].decode("utf-8"))
        unmarked_name = f"{prefix}/{patch_id}_unmarked_plane.png"
        marked_name = f"{prefix}/{patch_id}_marked_preview.png"
        source_overlay_name = f"{prefix}/{patch_id}_source_roi_overlay.png"
        transformed_overlay_name = f"{prefix}/{patch_id}_transformed_roi_overlay.png"
        missing = [name for name in (unmarked_name, marked_name) if name not in members]
        if missing:
            warnings.append(f"{patch_id}: older archive is missing preview file(s): {', '.join(missing)}")
        if metadata.get("workflow") == "experimental_template_roi":
            for name, label in ((source_overlay_name, "source ROI overlay"), (transformed_overlay_name, "transformed ROI overlay")):
                if name not in members:
                    warnings.append(f"{patch_id}: older archive has no retained {label}; report will show Not recorded")
        row = labels.get(patch_id, {})
        entry = {
            "patch_id": patch_id,
            "user_label": row.get("user_label") or patch_id,
            "user_note": row.get("note") or "",
            "metadata": metadata,
            "raw_nifti": members[f"{prefix}/{patch_id}.nii.gz"],
            "unmarked_png": members.get(unmarked_name, b""),
            "marked_png": members.get(marked_name, b""),
        }
        if source_overlay_name in members:
            entry["source_roi_overlay_png"] = members[source_overlay_name]
        if transformed_overlay_name in members:
            entry["transformed_roi_overlay_png"] = members[transformed_overlay_name]
        collection[patch_id] = entry
    if inspection["legacy_adapter"]:
        warnings.append("Older archive: no explicit replay manifest; compatible fields were adapted and missing information remains Not recorded.")
    return {"collection": collection, "warnings": warnings, "inspection": inspection}


def _unsupported_reason(patch: Mapping) -> str | None:
    required = ("section_id", "requested_bounds_mm", "requested_resolution_mm", "request_budget_bytes", "expected_shape_xyz", "expected_affine", "actual_resolution_mm_xyz", "source_array_sha256")
    missing = [name for name in required if patch.get(name) in (None, "")]
    if missing:
        return f"missing replay parameters: {', '.join(missing)}"
    if patch.get("provider") != "siibra-registered-section":
        return f"unsupported provider: {patch.get('provider')!r}"
    url = str(patch.get("provider_url", ""))
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in SUPPORTED_PROVIDER_HOSTS:
        return "provider URL is not an allowed registered-section provenance URL"
    try:
        bounds = Bounds(*[float(value) for value in patch["requested_bounds_mm"]])
        bounds.validate()
        if float(patch["request_budget_bytes"]) > MAX_MEMBER_BYTES:
            return "recorded request budget exceeds replay limit"
    except (TypeError, ValueError) as exc:
        return f"invalid replay bounds or budget: {exc}"
    return None


def replay_collection(manifest: Mapping, fetcher: Callable, progress: Callable[[int, int], None] | None = None) -> list[dict]:
    """Re-fetch recorded patches through an injected, bounded fetcher."""
    patches = list(manifest.get("patches", []))
    if len(patches) > MAX_PATCHES:
        raise ValueError("manifest patch count exceeds replay limit")
    reports = []
    for index, patch in enumerate(patches, start=1):
        patch_id = str(patch.get("patch_id", ""))
        try:
            _safe_patch_id(patch_id)
        except ValueError as exc:
            reports.append({"patch_id": patch_id, "section_id": patch.get("section_id"), "status": "unsupported", "reason": str(exc)})
            if progress:
                progress(index, len(patches))
            continue
        unsupported = _unsupported_reason(patch)
        if unsupported:
            report = {"patch_id": patch_id, "section_id": patch.get("section_id"), "status": "unsupported", "reason": unsupported}
            reports.append(report)
            if progress:
                progress(index, len(patches))
            continue
        try:
            bounds = Bounds(*[float(value) for value in patch["requested_bounds_mm"]])
            image, *_ = fetcher(bounds, resolution_mm=float(patch["requested_resolution_mm"]), max_bytes=min(int(patch["request_budget_bytes"]), MAX_BYTES), section_id=str(patch["section_id"]))
            data = np.asanyarray(image.dataobj)
            raw_checksum = hashlib.sha256(data.tobytes(order="C")).hexdigest()
            shape_match = list(image.shape) == list(patch["expected_shape_xyz"])
            affine_match = np.allclose(image.affine, patch["expected_affine"], atol=AFFINE_ATOL_MM, rtol=0)
            actual_resolution = [float(value) for value in image.header.get_zooms()[:3]]
            resolution_match = np.allclose(actual_resolution, patch["actual_resolution_mm_xyz"], atol=VOXEL_SIZE_ATOL_MM, rtol=0)
            scientific_match = shape_match and affine_match and resolution_match and raw_checksum == patch["source_array_sha256"]
            report = {
                "patch_id": patch_id,
                "section_id": patch["section_id"],
                "status": "reproduced" if scientific_match else "changed",
                "shape_match": shape_match,
                "affine_match": affine_match,
                "resolution_match": resolution_match,
                "raw_array_checksum_match": raw_checksum == patch["source_array_sha256"],
                "archived_serialized_nifti_sha256": patch.get("exported_nifti_sha256"),
                "replayed_serialized_nifti_sha256": hashlib.sha256(_nifti_bytes(image)).hexdigest(),
                "replayed_raw_array_sha256": raw_checksum,
                "actual_shape_xyz": list(image.shape),
                "actual_affine": np.asarray(image.affine).tolist(),
                "actual_resolution_mm_xyz": actual_resolution,
                "comparison_tolerance": {"affine_atol_mm": AFFINE_ATOL_MM, "voxel_size_atol_mm": VOXEL_SIZE_ATOL_MM},
            }
            report["serialized_file_checksum_match"] = bool(
                patch.get("exported_nifti_sha256")
                and report["replayed_serialized_nifti_sha256"] == patch["exported_nifti_sha256"]
            )
        except Exception as exc:
            report = {"patch_id": patch_id, "section_id": patch.get("section_id"), "status": "failed", "reason": str(exc)}
        reports.append(report)
        if progress:
            progress(index, len(patches))
    return reports
