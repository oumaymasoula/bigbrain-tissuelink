"""Strict validation and coordinate mapping for one Labelme PNG/JSON pair."""
from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


EXPECTED_MAPPING = {
    "annotation_pixel_order": ["u", "v"],
    "nifti_index_order": ["i_x", "i_y", "i_z"],
    "formula": {"i_x": "v", "i_y": "selected_plane", "i_z": "u"},
    "transpose": True,
    "flip_x": False,
    "flip_z": False,
}


def _load_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not np.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def validate_labelme_annotation(
    annotation_bytes: bytes,
    mapping_bytes: bytes,
    image_bytes: bytes,
    *,
    image_filename: str,
    expected_section_id: str,
    expected_source_url: str | None = None,
    expected_coordinate_space: str = "bigbrain",
) -> dict[str, Any]:
    """Validate one Labelme JSON, mapping report, and exact raw PNG pair."""
    annotation = _load_json(annotation_bytes, "Labelme annotation")
    mapping = _load_json(mapping_bytes, "annotation mapping metadata")
    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
    except Exception as exc:
        raise ValueError(f"annotation image cannot be opened: {exc}") from exc

    if image.format != "PNG":
        raise ValueError(f"annotation image must be PNG; got {image.format or 'unknown format'}")
    if image.mode != "L":
        raise ValueError(f"annotation image must be unchanged 8-bit grayscale mode L; got {image.mode}")
    width, height = image.size

    source = mapping.get("source_identity")
    if not isinstance(source, dict):
        raise ValueError("mapping metadata lacks source_identity")
    _require_equal(source.get("section_id"), expected_section_id, "section identifier")
    _require_equal(source.get("coordinate_space"), expected_coordinate_space, "coordinate space")
    if not source.get("source_url"):
        raise ValueError("mapping metadata lacks the source URL")
    if expected_source_url is not None:
        _require_equal(source.get("source_url"), expected_source_url, "source URL")
    if not source.get("source_nifti_sha256"):
        raise ValueError("mapping metadata lacks the source NIfTI checksum")

    annotation_meta = mapping.get("annotation_image")
    if not isinstance(annotation_meta, dict):
        raise ValueError("mapping metadata lacks annotation_image")
    _require_equal(annotation_meta.get("filename"), Path(image_filename).name, "annotation image filename")
    _require_equal(annotation_meta.get("shape_rows_cols"), [height, width], "annotation image dimensions")
    _require_equal(annotation_meta.get("dtype"), "uint8", "annotation image dtype")
    expected_sha = annotation_meta.get("sha256")
    actual_sha = hashlib.sha256(image_bytes).hexdigest()
    _require_equal(expected_sha, actual_sha, "annotation image checksum")
    _require_equal(annotation_meta.get("pixel_values_unchanged"), True, "raw pixel preservation flag")
    _require_equal(annotation_meta.get("mapping_contract"), EXPECTED_MAPPING, "annotation mapping contract")

    image_path = annotation.get("imagePath")
    if not isinstance(image_path, str) or Path(image_path).name != Path(image_filename).name:
        raise ValueError("Labelme imagePath does not identify the uploaded annotation image")
    if annotation.get("imageData") is not None:
        raise ValueError("embedded Labelme imageData is unsupported; upload the matching original PNG")
    _require_equal(annotation.get("imageWidth"), width, "Labelme imageWidth")
    _require_equal(annotation.get("imageHeight"), height, "Labelme imageHeight")

    source_shape = mapping.get("nifti_shape")
    if not isinstance(source_shape, list) or len(source_shape) != 3:
        raise ValueError("mapping metadata lacks a 3D nifti_shape")
    plane = mapping.get("selected_plane")
    if not isinstance(plane, dict) or plane.get("axis") != "y":
        raise ValueError("only a selected y section-thickness plane is supported")
    plane_index = int(plane.get("index", -1))
    if plane_index < 0 or plane_index >= int(source_shape[1]):
        raise ValueError("selected y plane is outside the source NIfTI")
    affine = np.asarray(mapping.get("source_affine", mapping.get("affine")), dtype=float)
    if affine.shape != (4, 4) or not np.all(np.isfinite(affine)):
        raise ValueError("mapping metadata lacks a finite 4×4 source affine")

    shapes = annotation.get("shapes")
    if not isinstance(shapes, list) or not shapes:
        raise ValueError("Labelme annotation contains no shapes")
    polygons: list[dict[str, Any]] = []
    for shape_index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise ValueError(f"shape {shape_index} is not an object")
        if shape.get("shape_type") != "polygon":
            raise ValueError(f"shape {shape_index} uses unsupported shape_type {shape.get('shape_type')!r}; only polygon is supported")
        points = shape.get("points")
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError(f"polygon {shape_index} must contain at least three vertices")
        normalized: list[list[float]] = []
        for point_index, point in enumerate(points):
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"polygon {shape_index} vertex {point_index} must be [x, y]")
            u = _finite_number(point[0], f"polygon {shape_index} vertex {point_index} x")
            v = _finite_number(point[1], f"polygon {shape_index} vertex {point_index} y")
            if not (0 <= u < width and 0 <= v < height):
                raise ValueError(f"polygon {shape_index} vertex {point_index} is outside the {width}×{height} image")
            normalized.append([u, v])
        polygons.append({"label": str(shape.get("label", "")), "points": normalized, "shape_type": "polygon"})

    mapped_polygons = []
    for polygon in polygons:
        voxel_vertices = [[point[1], plane_index, point[0]] for point in polygon["points"]]
        physical_vertices = [
            (affine @ np.array([*voxel, 1.0], dtype=float))[:3].tolist()
            for voxel in voxel_vertices
        ]
        mapped_polygons.append({
            "label": polygon["label"],
            "shape_type": "polygon",
            "pixel_vertices_xy": polygon["points"],
            "nifti_voxel_vertices_xyz": voxel_vertices,
            "physical_vertices_mm": physical_vertices,
        })

    return {
        "annotation": annotation,
        "mapping": mapping,
        "image": image,
        "image_bytes": image_bytes,
        "polygons": mapped_polygons,
        "section_id": source["section_id"],
        "source_url": source["source_url"],
        "coordinate_space": source["coordinate_space"],
        "plane_index": plane_index,
        "affine": affine,
    }


def map_physical_polygon_to_view(
    physical_vertices_mm: list[list[float]],
    overview_affine: np.ndarray,
    overview_shape: tuple[int, ...],
    display_size: tuple[int, int],
    *,
    view_origin: tuple[float, float] = (0.0, 0.0),
    view_size: tuple[float, float] | None = None,
    canvas_size: tuple[int, int] | None = None,
) -> list[list[float]]:
    """Map section physical x/z vertices into current overview canvas pixels."""
    canvas_width, canvas_height = canvas_size or display_size
    window_width, window_height = view_size or display_size
    inverse = np.linalg.inv(np.asarray(overview_affine, dtype=float))
    mapped = []
    for point in physical_vertices_mm:
        world = np.array([point[0], point[1], point[2], 1.0], dtype=float)
        voxel = inverse @ world
        full_u = voxel[2] * display_size[0] / overview_shape[2]
        full_v = voxel[0] * display_size[1] / overview_shape[0]
        mapped.append([
            (full_u - view_origin[0]) * canvas_width / window_width,
            (full_v - view_origin[1]) * canvas_height / window_height,
        ])
    return mapped


def build_import_export(validated: dict[str, Any]) -> bytes:
    """Serialize imported pixels, physical mapping, and provenance as JSON."""
    result = {
        "format": "bigbrain-cutout-labelme-import-v1",
        "section_id": validated["section_id"],
        "source_url": validated["source_url"],
        "coordinate_space": validated["coordinate_space"],
        "selected_plane": {"axis": "y", "index": validated["plane_index"]},
        "transformation_provenance": {
            "labelme_pixel_order": "(u,v)=(x,y), origin top-left raster convention",
            "to_nifti_index": "(i_x,i_y,i_z)=(v,selected_plane,u)",
            "operation": "transpose only; no flip, resize, rotation, or registration",
        },
        "polygons": validated["polygons"],
        "warning": "Labels are user annotation labels, not verified anatomical labels; 3D anatomical alignment is not claimed.",
    }
    return (json.dumps(result, indent=2) + "\n").encode("utf-8")
