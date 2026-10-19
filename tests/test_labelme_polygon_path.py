import io
import json
import tempfile
import zipfile

import nibabel as nib
import numpy as np
from PIL import Image

from labelme_import import EXPECTED_MAPPING, build_import_package, validate_labelme_annotation


def _fixture():
    shape = (5, 3, 7)
    data = np.zeros(shape, dtype=np.uint16)
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                data[x, y, z] = 1000 * x + 100 * y + z
    affine = np.array(
        [[0.8, 0.1, 0.2, -4.0], [0.0, 0.5, 0.1, -1.0], [0.1, 0.0, 0.7, 2.0], [0, 0, 0, 1]],
        dtype=float,
    )
    plane = data[:, 2, :].T
    image_buffer = io.BytesIO()
    Image.fromarray(np.clip(plane, 0, 255).astype(np.uint8), mode="L").save(image_buffer, format="PNG")
    image_bytes = image_buffer.getvalue()
    import hashlib
    mapping = {
        "collection_patch_id": "patch-nonsquare",
        "section_id": "section-test",
        "provider_url": "https://example.invalid/provider",
        "coordinate_space": "bigbrain",
        "source_array_sha256": hashlib.sha256(data.tobytes(order="C")).hexdigest(),
        "actual_shape_xyz": list(shape),
        "actual_affine": affine.tolist(),
        "unmarked_png_filename": "patch-nonsquare_unmarked_plane.png",
        "unmarked_png_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "unmarked_png_shape_rows_cols": list(plane.shape),
        "annotation_png_mapping": {
            "source_plane_expression": "data[:,2,:].T",
            "source_slice_index_y": 2,
        },
    }
    annotation = {
        "version": "5.7.0",
        "flags": {},
        "shapes": [{
            "label": "asymmetric_landmark",
            "points": [[1.0, 1.0], [4.0, 1.0], [3.0, 5.0]],
            "shape_type": "polygon",
        }],
        "imagePath": "patch-nonsquare_unmarked_plane.png",
        "imageData": None,
        "imageHeight": plane.shape[0],
        "imageWidth": plane.shape[1],
    }
    metadata = {
        **mapping,
        "source_identity": {
            "section_id": mapping["section_id"],
            "source_url": mapping["provider_url"],
            "coordinate_space": mapping["coordinate_space"],
            "source_nifti_sha256": mapping["source_array_sha256"],
        },
        "annotation_image": {
            "filename": mapping["unmarked_png_filename"],
            "shape_rows_cols": mapping["unmarked_png_shape_rows_cols"],
            "dtype": "uint8",
            "sha256": mapping["unmarked_png_sha256"],
            "pixel_values_unchanged": True,
            "mapping_contract": EXPECTED_MAPPING,
        },
        "nifti_shape": list(shape),
        "source_affine": affine.tolist(),
        "selected_plane": {"axis": "y", "index": 2, "source_array_plane": "data[:,2,:]"},
    }
    return data, affine, annotation, metadata, image_bytes


def test_non_square_nonzero_plane_maps_as_png_u_v_to_x_y_z_and_world():
    data, affine, annotation, metadata, image_bytes = _fixture()
    validated = validate_labelme_annotation(
        json.dumps(annotation).encode(), json.dumps(metadata).encode(), image_bytes,
        image_filename="patch-nonsquare_unmarked_plane.png",
        expected_section_id="section-test", expected_source_url="https://example.invalid/provider",
        expected_patch_id="patch-nonsquare",
    )
    polygon = validated["polygons"][0]
    assert polygon["nifti_voxel_vertices_xyz"] == [[1.0, 2, 1.0], [4.0, 2, 1.0], [3.0, 2, 5.0]]
    expected_world = (affine @ np.array([4.0, 2.0, 1.0, 1.0]))[:3]
    assert np.allclose(polygon["physical_vertices_mm"][1], expected_world)
    assert data[4, 2, 1] == 4201


def test_label_mask_has_one_selected_y_slice_and_correct_crop_affine():
    _, affine, annotation, metadata, image_bytes = _fixture()
    validated = validate_labelme_annotation(
        json.dumps(annotation).encode(), json.dumps(metadata).encode(), image_bytes,
        image_filename="patch-nonsquare_unmarked_plane.png", expected_section_id="section-test",
        expected_patch_id="patch-nonsquare",
    )
    package = build_import_package(validated)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        with tempfile.NamedTemporaryFile(suffix=".nii.gz") as handle:
            handle.write(archive.read("label_mask.nii.gz"))
            handle.flush()
            mask = nib.load(handle.name)
            values = np.asanyarray(mask.dataobj)
        # The assertion also verifies the mask remains non-square and
        # single-plane.
        assert mask.shape == (5, 1, 7)
        expected_affine = affine.copy()
        expected_affine[:3, 3] = (affine @ np.array([0.0, 2.0, 0.0, 1.0]))[:3]
        assert np.allclose(mask.affine, expected_affine)
        assert set(np.unique(values)) <= {0, 1}
        assert values[2, 0, 2] == 1  # PNG (u=2,v=2) -> NIfTI (x=2,y=2,z=2)
        assert values[0, 0, 0] == 0
        exported = json.loads(archive.read("polygon_annotations.json"))
        assert exported["selected_plane"] == {"axis": "y", "index": 2}
        assert json.loads(archive.read("label_table.json"))[1] == {"id": 1, "label": "asymmetric_landmark"}
        assert exported["external_tool_round_trip"].startswith("not completed")


def test_collection_patch_id_and_png_mismatch_are_rejected():
    _, _, annotation, metadata, image_bytes = _fixture()
    with np.testing.assert_raises_regex(ValueError, "collection patch ID"):
        validate_labelme_annotation(
            json.dumps(annotation).encode(), json.dumps(metadata).encode(), image_bytes,
            image_filename="patch-nonsquare_unmarked_plane.png", expected_section_id="section-test",
            expected_patch_id="patch-other",
        )
