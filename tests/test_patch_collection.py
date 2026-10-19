import csv
import io
import json
import zipfile

import pytest

from patch_collection import add_entry, collection_bytes, collection_zip_bytes, patch_id_for


def _entry(section_id: str, value: bytes):
    metadata = {
        "section_id": section_id,
        "section_number": section_id,
        "provider_url": f"https://example.invalid/{section_id}",
        "coordinate_space": "bigbrain",
        "requested_bounds_mm": [-1, -1, -1, 1, 1, 1],
        "actual_shape_xyz": [2, 1, 2],
        "actual_voxel_size_mm_xyz": [0.008, 0.02, 0.008],
        "actual_affine": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        "source_array_sha256": value.hex(),
        "exported_nifti_sha256": value.hex(),
    }
    return {
        "patch_id": patch_id_for(value, metadata),
        "user_label": section_id,
        "user_note": "review note",
        "metadata": metadata,
        "raw_nifti": value,
        "unmarked_png": b"unmarked-" + value,
        "marked_png": b"marked-" + value,
    }


def test_two_sections_duplicate_rejection_and_removal():
    collection = {}
    first = _entry("3458", b"first")
    second = _entry("3500", b"second")
    add_entry(collection, first, max_bytes=1024)
    add_entry(collection, second, max_bytes=1024)
    assert set(collection) == {first["patch_id"], second["patch_id"]}
    assert collection_bytes(collection) == sum(len(first[name]) + len(second[name]) for name in ("raw_nifti", "unmarked_png", "marked_png"))
    with pytest.raises(ValueError, match="already"):
        add_entry(collection, first, max_bytes=1024)
    collection.pop(first["patch_id"])
    assert list(collection) == [second["patch_id"]]


def test_collection_budget_is_enforced():
    collection = {}
    entry = _entry("3458", b"0123456789")
    with pytest.raises(ValueError, match="limit"):
        add_entry(collection, entry, max_bytes=1)


def test_collection_zip_contains_raw_unmarked_marked_metadata_and_manifest():
    first = _entry("3458", b"first")
    second = _entry("3500", b"second")
    archive_bytes = collection_zip_bytes({first["patch_id"]: first, second["patch_id"]: second})
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = set(archive.namelist())
        assert "manifest.csv" in names
        assert "README.txt" in names
        for entry in (first, second):
            prefix = f"patches/{entry['patch_id']}"
            assert f"{prefix}/{entry['patch_id']}.nii.gz" in names
            assert f"{prefix}/{entry['patch_id']}_unmarked_plane.png" in names
            assert f"{prefix}/{entry['patch_id']}_marked_preview.png" in names
            metadata = json.loads(archive.read(f"{prefix}/metadata.json"))
            assert metadata["section_id"] == entry["metadata"]["section_id"]
        rows = list(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode())))
        assert {row["section_id"] for row in rows} == {"3458", "3500"}
