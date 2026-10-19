import io
import json
import zipfile

from labelme_coco import build_coco_package
from tests.test_labelme_polygon_path import _fixture
from labelme_import import validate_labelme_annotation


def test_coco_adapter_keeps_pixel_annotations_and_canonical_geometry():
    _, _, annotation, metadata, image_bytes = _fixture()
    validated = validate_labelme_annotation(
        json.dumps(annotation).encode(), json.dumps(metadata).encode(), image_bytes,
        image_filename="patch-nonsquare_unmarked_plane.png", expected_section_id="section-test",
        expected_patch_id="patch-nonsquare",
    )
    package = build_coco_package(validated, b"canonical-nifti", metadata)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        coco = json.loads(archive.read("annotations/instances_patch-nonsquare.json"))
        assert coco["images"] == [{"id": 1, "file_name": "patch-nonsquare_unmarked_plane.png", "width": 5, "height": 7}]
        assert coco["annotations"][0]["segmentation"] == [[1.0, 1.0, 4.0, 1.0, 3.0, 5.0]]
        assert coco["annotations"][0]["iscrowd"] == 0
        assert archive.read("canonical/patch-nonsquare.nii.gz") == b"canonical-nifti"
        canonical = json.loads(archive.read("canonical/patch-nonsquare_metadata.json"))
        assert canonical["adapter_status"].startswith("pixel-only")
        assert "source_affine" in canonical["tissuelink_metadata"]
