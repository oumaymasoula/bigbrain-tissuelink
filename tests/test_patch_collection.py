import csv
import io
import json
import zipfile

import pytest
import nibabel as nib
import numpy as np

from patch_collection import add_entry, annotation_plane_from_image, collection_bytes, collection_zip_bytes, patch_id_for
from volume_alignment import voxel_center_world


def test_annotation_png_mapping_uses_data_y0_transpose_with_asymmetric_pixels():
    data = np.zeros((3, 2, 4), dtype=np.uint16)
    for x in range(3):
        for y in range(2):
            for z in range(4):
                data[x, y, z] = 100 * x + 10 * y + z
    affine = np.array(
        [[0.2, 0.0, 0.03, -1.0], [0.0, 0.02, 0.0, -0.5], [0.0, 0.0, 0.3, 2.0], [0, 0, 0, 1]],
        dtype=float,
    )
    image = nib.Nifti1Image(data, affine)
    display, mapping = annotation_plane_from_image(image, slice_index=0)
    plane = data[:, 0, :].T
    low, high = np.percentile(plane, [1.0, 99.0])
    expected = np.clip((plane.astype(np.float32) - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)
    assert np.array_equal(display, expected)
    assert display.shape == (4, 3)
    assert mapping["source_plane_expression"] == "data[:,0,:].T"
    assert mapping["png_horizontal_source_axis"] == "x"
    assert mapping["png_vertical_source_axis"] == "z"
    assert mapping["pixel_to_nifti_voxel"] == "(u, v) -> (u, slice_index_y, v)"
    u, v = 2, 1
    source_index = (u, 0, v)
    assert data[source_index] == 201  # the off-centre PNG pixel is source (x=2,y=0,z=1)
    assert display[v, u] == expected[v, u]
    assert np.allclose(voxel_center_world(image, np.asarray(source_index)), [-0.57, -0.5, 2.3])


def test_annotation_png_mapping_records_nonzero_y_slice():
    data = np.zeros((2, 3, 5), dtype=np.uint16)
    for x in range(2):
        for y in range(3):
            for z in range(5):
                data[x, y, z] = 100 * x + 10 * y + z
    image = nib.Nifti1Image(data, np.eye(4))
    display, mapping = annotation_plane_from_image(image, slice_index=2)
    assert mapping["source_plane_expression"] == "data[:,2,:].T"
    assert mapping["source_slice_index_y"] == 2
    assert mapping["pixel_to_nifti_voxel"] == "(u, v) -> (u, slice_index_y, v)"
    assert data[1, 2, 4] == 124
    assert display[4, 1] > display[0, 0]


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
