import json
from pathlib import Path

import pytest
from PIL import Image

from labelme_import import EXPECTED_MAPPING, map_physical_polygon_to_view, validate_labelme_annotation


ROOT = Path(__file__).parents[1]
FIXTURE_DIR = ROOT / "outputs" / "annotation_feasibility"


def fixture_bytes():
    annotation = (FIXTURE_DIR / "bigbrain_crop_y1_raw.json").read_bytes()
    mapping = json.loads((FIXTURE_DIR / "mapping_report.json").read_text())
    # The preserved feasibility artifact predates the corrected PNG contract.
    # Keep it unchanged on disk and adapt only this test input.
    mapping["annotation_image"]["mapping_contract"] = EXPECTED_MAPPING
    return annotation, json.dumps(mapping).encode(), (FIXTURE_DIR / "bigbrain_crop_y1_raw.png").read_bytes()


def test_labelme_fixture_maps_and_preserves_label():
    annotation, mapping, image = fixture_bytes()
    validated = validate_labelme_annotation(
        annotation,
        mapping,
        image,
        image_filename="bigbrain_crop_y1_raw.png",
        expected_section_id="73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        expected_source_url="https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed",
    )
    assert validated["image"].size == (251, 251)
    assert validated["polygons"][0]["label"] == "fissure_adjacent_tissue_example"
    assert validated["polygons"][0]["nifti_voxel_vertices_xyz"][0] == [170.0, 1, 170.0]
    assert validated["polygons"][0]["nifti_voxel_vertices_xyz"][1] == [231.0, 1, 181.0]


def test_wrong_image_checksum_is_rejected():
    annotation, mapping, image = fixture_bytes()
    from io import BytesIO
    wrong_output = BytesIO()
    wrong_image = Image.open(BytesIO(image)).copy()
    wrong_image.putpixel((0, 0), (wrong_image.getpixel((0, 0)) + 1) % 256)
    wrong_image.save(wrong_output, format="PNG")
    with pytest.raises(ValueError, match="checksum"):
        validate_labelme_annotation(
            annotation, mapping, wrong_output.getvalue(), image_filename="bigbrain_crop_y1_raw.png",
            expected_section_id="73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        )


def test_wrong_dimensions_are_rejected():
    annotation, mapping, _ = fixture_bytes()
    from io import BytesIO
    output = BytesIO()
    Image.new("L", (250, 251), 0).save(output, format="PNG")
    with pytest.raises(ValueError, match="dimensions"):
        validate_labelme_annotation(
            annotation, mapping, output.getvalue(), image_filename="bigbrain_crop_y1_raw.png",
            expected_section_id="73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        )


def test_wrong_source_identity_is_rejected():
    annotation, mapping, image = fixture_bytes()
    with pytest.raises(ValueError, match="section identifier"):
        validate_labelme_annotation(
            annotation, mapping, image, image_filename="bigbrain_crop_y1_raw.png",
            expected_section_id="wrong-section",
        )


def test_unsupported_shape_and_nonfinite_vertex_are_rejected():
    annotation, mapping, image = fixture_bytes()
    data = json.loads(annotation)
    data["shapes"][0]["shape_type"] = "rectangle"
    with pytest.raises(ValueError, match="unsupported shape_type"):
        validate_labelme_annotation(
            json.dumps(data).encode(), mapping, image, image_filename="bigbrain_crop_y1_raw.png",
            expected_section_id="73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        )
    data["shapes"][0]["shape_type"] = "polygon"
    data["shapes"][0]["points"][0][0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        validate_labelme_annotation(
            json.dumps(data).encode(), mapping, image, image_filename="bigbrain_crop_y1_raw.png",
            expected_section_id="73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
        )


def test_zoom_and_pan_map_same_physical_polygon():
    annotation, mapping, image = fixture_bytes()
    validated = validate_labelme_annotation(
        annotation, mapping, image, image_filename="bigbrain_crop_y1_raw.png",
        expected_section_id="73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126",
    )
    polygon = validated["polygons"][0]["physical_vertices_mm"]
    affine = validated["mapping"]["source_affine"]
    base = map_physical_polygon_to_view(polygon, affine, (251, 1, 251), (251, 251), canvas_size=(251, 251))
    zoomed = map_physical_polygon_to_view(
        polygon, affine, (251, 1, 251), (251, 251), view_origin=(50, 30), view_size=(125.5, 125.5), canvas_size=(251, 251)
    )
    assert len(base) == len(zoomed) == 5
    assert base != zoomed
    assert polygon == validated["polygons"][0]["physical_vertices_mm"]
