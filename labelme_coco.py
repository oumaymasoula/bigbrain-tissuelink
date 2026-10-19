"""Small, pixel-only COCO instance-segmentation adapter for Labelme imports."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any


def _polygon_area(points: list[list[float]]) -> float:
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        / 2.0
    )


def build_coco_package(
    validated: dict[str, Any],
    canonical_nifti_bytes: bytes,
    canonical_metadata: dict[str, Any],
) -> bytes:
    """Build COCO JSON plus unchanged canonical TissueLink data.

    COCO segmentation coordinates are image pixels only. The NIfTI and full
    metadata are included as separate canonical files; COCO itself carries no
    affine or world-coordinate semantics.
    """
    image = validated["image"]
    width, height = image.size
    patch_id = validated.get("patch_id") or "labelme-import"
    filename = Path(validated["mapping"]["annotation_image"]["filename"]).name
    labels: list[str] = []
    for polygon in validated["polygons"]:
        label = polygon["label"] or "__unnamed__"
        if label not in labels:
            labels.append(label)
    categories = [
        {"id": index, "name": label, "supercategory": "user_annotation"}
        for index, label in enumerate(labels, start=1)
    ]
    category_ids = {label: category["id"] for label, category in zip(labels, categories)}
    annotations = []
    for annotation_id, polygon in enumerate(validated["polygons"], start=1):
        points = polygon["pixel_vertices_xy"]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        annotations.append({
            "id": annotation_id,
            "image_id": 1,
            "category_id": category_ids[polygon["label"] or "__unnamed__"],
            "segmentation": [[coordinate for point in points for coordinate in point]],
            "area": _polygon_area(points),
            "bbox": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
            "iscrowd": 0,
        })
    coco = {
        "info": {
            "description": "BigBrain TissueLink Labelme polygon export",
            "version": "1.0",
            "patch_id": patch_id,
            "coordinate_note": "COCO values are PNG pixels only; use the canonical NIfTI and metadata for voxel/world geometry",
        },
        "licenses": [],
        "images": [{"id": 1, "file_name": filename, "width": width, "height": height}],
        "annotations": annotations,
        "categories": categories,
    }
    canonical = {
        "adapter": "labelme_to_coco_instance_segmentation",
        "adapter_status": "pixel-only; canonical NIfTI and metadata retained",
        "patch_id": patch_id,
        "source_annotation": filename,
        "tissuelink_metadata": canonical_metadata,
        "world_geometry_location": f"canonical/{patch_id}_metadata.json",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"images/{filename}", validated["image_bytes"])
        archive.writestr(f"annotations/instances_{patch_id}.json", json.dumps(coco, indent=2) + "\n")
        archive.writestr(f"canonical/{patch_id}.nii.gz", canonical_nifti_bytes)
        archive.writestr(f"canonical/{patch_id}_metadata.json", json.dumps(canonical, indent=2) + "\n")
        archive.writestr(
            "README.txt",
            "COCO instance-segmentation adapter for one Labelme polygon import.\n\n"
            "The COCO JSON contains PNG pixel polygons, categories, bounding "
            "boxes, areas and iscrowd=0. COCO does not preserve NIfTI affine, "
            "voxel indices or world millimetres. Use the canonical NIfTI and "
            "TissueLink metadata in canonical/ for spatial interpretation. "
            "Labels are user annotations, not anatomical labels.\n",
        )
    return output.getvalue()
