import io
import hashlib
import tempfile
import zipfile

import nibabel as nib
import numpy as np
import pytest

from collection_replay import build_manifest, import_collection_archive, replay_collection, reopen_collection
from patch_collection import collection_zip_bytes, patch_id_for
from bigbrain_cutout import Bounds


def _nifti_bytes(data, affine):
    image = nib.Nifti1Image(np.asarray(data), np.asarray(affine, dtype=float))
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as handle:
        nib.save(image, handle.name)
        handle.seek(0)
        return handle.read()


def _entry(section_id="3458", data=None):
    data = np.asarray(data if data is not None else np.arange(4, dtype=np.uint8).reshape(2, 1, 2))
    affine = np.diag([0.008, 0.02, 0.008, 1.0])
    raw = _nifti_bytes(data, affine)
    metadata = {
        "section_id": section_id,
        "section_number": section_id,
        "section_name": f"#{section_id}",
        "provider_url": "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed",
        "coordinate_space": "bigbrain",
        "requested_bounds_mm": [-1.0, -0.87, -1.0, 1.0, -0.85, 1.0],
        "requested_resolution_mm": 0.01,
        "request_budget_bytes": 10 * 1024 * 1024,
        "actual_shape_xyz": list(data.shape),
        "actual_voxel_size_mm_xyz": [0.008, 0.02, 0.008],
        "actual_affine": affine.tolist(),
        "source_array_sha256": hashlib.sha256(data.tobytes(order="C")).hexdigest(),
        "exported_nifti_sha256": hashlib.sha256(raw).hexdigest(),
    }
    return {
        "patch_id": patch_id_for(raw, metadata),
        "user_label": "untrusted label",
        "user_note": "untrusted note",
        "metadata": metadata,
        "raw_nifti": raw,
        "unmarked_png": b"png",
        "marked_png": b"marked",
    }


def test_reopen_new_manifest_checks_scientific_files_without_fetching():
    entry = _entry()
    report = reopen_collection(collection_zip_bytes({entry["patch_id"]: entry}))
    assert report["legacy_adapter"] is False
    assert report["manifest"]["schema_version"] == "1.0"
    assert report["reports"][0]["status"] == "reopened"


def test_import_collection_archive_restores_retained_files_and_patch_provenance():
    manual = _entry("3458")
    roi = _entry("3146", np.full((2, 1, 2), 7, dtype=np.uint8))
    roi["metadata"].update({
        "workflow": "experimental_template_roi",
        "input_roi_filename": "cerebra_left_precentral_icbm2009c_sym_1mm_binary_roi.nii.gz",
        "input_roi_sha256": "abc123",
        "supported_template": "ICBM 2009c nonlinear symmetric 1 mm",
        "anatomical_status": "Awaiting independent review",
    })
    roi["source_roi_overlay_png"] = b"source-overlay"
    roi["transformed_roi_overlay_png"] = b"transformed-overlay"
    source = {manual["patch_id"]: manual, roi["patch_id"]: roi}
    restored = import_collection_archive(collection_zip_bytes(source))
    assert restored["warnings"] == []
    assert set(restored["collection"]) == set(source)
    for patch_id, original in source.items():
        imported = restored["collection"][patch_id]
        assert imported["raw_nifti"] == original["raw_nifti"]
        assert imported["unmarked_png"] == original["unmarked_png"]
        assert imported["marked_png"] == original["marked_png"]
        assert imported["metadata"] == original["metadata"]
        assert imported["user_label"] == original["user_label"]
        assert imported["user_note"] == original["user_note"]
    assert restored["collection"][roi["patch_id"]]["source_roi_overlay_png"] == b"source-overlay"
    assert restored["collection"][roi["patch_id"]]["transformed_roi_overlay_png"] == b"transformed-overlay"


def test_reopen_legacy_export_uses_compatibility_adapter():
    entry = _entry()
    archive = collection_zip_bytes({entry["patch_id"]: entry})
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                if info.filename != "manifest.json":
                    target.writestr(info, source.read(info))
    report = reopen_collection(output.getvalue())
    assert report["legacy_adapter"] is True
    assert report["manifest"]["patches"][0]["compatibility_warnings"]


def test_import_older_roi_archive_identifies_missing_retained_overlays():
    entry = _entry("3146")
    entry["metadata"]["workflow"] = "experimental_template_roi"
    archive = collection_zip_bytes({entry["patch_id"]: entry})
    restored = import_collection_archive(archive)
    assert len(restored["collection"]) == 1
    assert any("older archive has no retained source ROI overlay" in warning for warning in restored["warnings"])


def test_corrupt_and_unsafe_archives_are_rejected():
    with pytest.raises(ValueError, match="valid ZIP"):
        reopen_collection(b"not a zip")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../escape.txt", "no")
    with pytest.raises(ValueError, match="unsafe archive path"):
        reopen_collection(output.getvalue())


def test_missing_parameters_are_unsupported_without_fetch():
    entry = _entry()
    manifest = build_manifest({entry["patch_id"]: entry})
    manifest["patches"][0].pop("requested_resolution_mm")
    called = []
    result = replay_collection(manifest, lambda *args, **kwargs: called.append(1))
    assert result[0]["status"] == "unsupported"
    assert not called


def test_successful_replay_compares_array_shape_affine_and_serialization():
    entry = _entry()
    manifest = build_manifest({entry["patch_id"]: entry})
    image = nib.Nifti1Image(np.arange(4, dtype=np.uint8).reshape(2, 1, 2), np.diag([0.008, 0.02, 0.008, 1.0]))
    result = replay_collection(manifest, lambda bounds, **kwargs: (image, None, None))
    assert result[0]["status"] == "reproduced"
    assert result[0]["shape_match"] is True
    assert result[0]["affine_match"] is True
    assert result[0]["resolution_match"] is True
    assert result[0]["raw_array_checksum_match"] is True
    assert "serialized_file_checksum_match" in result[0]


def test_changed_result_and_partial_failure_are_reported_separately():
    first = _entry("3458")
    second = _entry("3500", np.full((2, 1, 2), 9, dtype=np.uint8))
    manifest = build_manifest({first["patch_id"]: first, second["patch_id"]: second})
    def fetcher(bounds: Bounds, **kwargs):
        if kwargs["section_id"] == "3500":
            raise RuntimeError("provider unavailable")
        changed = nib.Nifti1Image(np.zeros((2, 1, 2), dtype=np.uint8), np.diag([0.008, 0.02, 0.008, 1.0]))
        return changed, None, None
    result = replay_collection(manifest, fetcher)
    assert [item["status"] for item in result] == ["changed", "failed"]
