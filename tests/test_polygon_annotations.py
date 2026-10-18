import json
import zipfile

import numpy as np
import pytest

from polygon_annotations import (
    append_polygon_files_to_bundle,
    build_polygon_export,
    map_crop_polygon_to_source,
    polygon_objects,
)


def test_canvas_polygon_vertices_include_fabric_transform():
    canvas = {
        "objects": [{
            "type": "polygon",
            "left": 50,
            "top": 40,
            "scaleX": 2,
            "scaleY": 3,
            "pathOffset": {"x": 5, "y": 5},
            "points": [{"x": 5, "y": 5}, {"x": 10, "y": 5}, {"x": 5, "y": 10}],
        }]
    }
    assert polygon_objects(canvas)[0]["points"] == [[50.0, 40.0], [60.0, 40.0], [50.0, 55.0]]


def test_canvas_component_points_without_path_offset_are_canvas_pixels():
    canvas = {"objects": [{"type": "Polygon", "left": 125, "top": 127, "width": 160, "height": 165,
                            "points": [{"x": 45, "y": 44.5}, {"x": 205, "y": 169.5}, {"x": 100, "y": 209.5}]}]}
    assert polygon_objects(canvas)[0]["points"] == [[45.0, 44.5], [205.0, 169.5], [100.0, 209.5]]


def test_crop_polygon_mapping_preserves_axis_contract_and_affine():
    mapped = map_crop_polygon_to_source(
        [[10, 20], [30, 20], [10, 40]],
        (100, 2, 200),
        np.array([[0.1, 0, 0, -10], [0, 0.02, 0, -1], [0, 0, 0.2, -20], [0, 0, 0, 1]], dtype=float),
        (100, 100),
        1,
    )
    assert mapped["nifti_voxel_vertices_xyz"] == [[20.0, 1.0, 20.0], [20.0, 1.0, 60.0], [40.0, 1.0, 20.0]]
    assert mapped["physical_vertices_mm"][0] == [-8.0, -0.98, -16.0]


def test_crop_polygon_out_of_bounds_is_rejected():
    with pytest.raises(ValueError, match="outside"):
        map_crop_polygon_to_source([[-1, 2], [3, 4], [5, 6]], (10, 2, 10), np.eye(4), (10, 10), 1)


def test_polygon_files_are_added_to_existing_bundle(tmp_path):
    bundle = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("bigbrain_crop.nii.gz", b"raw")
    payload = build_polygon_export(
        section_id="section",
        section_label="section",
        source_url="https://example.test/source",
        coordinate_space="bigbrain",
        requested_bounds={"min_x": 0},
        requested_resolution_mm=0.01,
        crop_shape=(10, 2, 10),
        actual_voxel_size_mm=[0.01, 0.02, 0.01],
        affine=np.eye(4),
        plane_index=1,
        canvas_size=(100, 100),
        polygons=[{"label": "landmark", "canvas_vertices_xy": [[1, 2, 3]],}],
    )
    append_polygon_files_to_bundle(bundle, tmp_path, payload)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert {"bigbrain_crop.nii.gz", "polygon_annotations.json", "polygon_mapping.json"} <= names
        assert json.loads(archive.read("polygon_annotations.json"))["polygons"][0]["label"] == "landmark"
