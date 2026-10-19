"""Strict validation and coordinate mapping for one Labelme PNG/JSON pair."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw


EXPECTED_MAPPING = {
    "annotation_pixel_order": ["u", "v"],
    "nifti_index_order": ["i_x", "i_y", "i_z"],
    "formula": {"i_x": "u", "i_y": "selected_plane", "i_z": "v"},
    "transpose": True,
    "flip_x": False,
    "flip_z": False,
}


def _collection_mapping_adapter(mapping: dict[str, Any], image_filename: str, image_bytes: bytes) -> dict[str, Any]:
    """Adapt collection ``metadata.json`` into the strict Labelme contract.

    The adapter is deliberately metadata-only: it never follows provider URLs
    or trusts a path supplied by an imported archive.
    """
    patch_id = mapping.get("collection_patch_id") or mapping.get("patch_id")
    png_mapping = mapping.get("annotation_png_mapping")
    if not patch_id or not isinstance(png_mapping, dict):
        raise ValueError(
            "collection metadata must contain collection_patch_id and annotation_png_mapping; "
            "this export cannot be safely bound to a Labelme image"
        )
    filename = mapping.get("unmarked_png_filename")
    png_sha = mapping.get("unmarked_png_sha256")
    png_shape = mapping.get("unmarked_png_shape_rows_cols")
    if not filename or not png_sha or not isinstance(png_shape, list):
        raise ValueError(
            "collection metadata lacks exact unmarked PNG filename, checksum or dimensions; "
            "export a collection with the current metadata schema"
        )
    canonical = {
        "source_identity": {
            "section_id": mapping.get("section_id"),
            "source_url": mapping.get("provider_url"),
            "coordinate_space": mapping.get("coordinate_space"),
            "source_nifti_sha256": mapping.get("source_array_sha256"),
        },
        "annotation_image": {
            "filename": filename,
            "shape_rows_cols": png_shape,
            "dtype": "uint8",
            "sha256": png_sha,
            "pixel_values_unchanged": True,
            "mapping_contract": EXPECTED_MAPPING,
        },
        "nifti_shape": mapping.get("actual_shape_xyz"),
        "source_affine": mapping.get("actual_affine"),
        "selected_plane": {
            "axis": "y",
            "index": png_mapping.get("source_slice_index_y"),
            "source_array_plane": png_mapping.get("source_plane_expression"),
        },
        "collection_patch_id": patch_id,
        "compatibility_adapter": "collection_metadata_v1",
    }
    if hashlib.sha256(image_bytes).hexdigest() != png_sha:
        # Keep this early and explicit so a wrong file is not interpreted as a
        # malformed polygon or a dimensions-only match.
        raise ValueError("annotation image checksum does not match collection patch metadata")
    if Path(image_filename).name != Path(str(filename)).name:
        raise ValueError(f"annotation image filename mismatch: expected {filename!r}, got {image_filename!r}")
    return canonical


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
    expected_patch_id: str | None = None,
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

    if "source_identity" not in mapping:
        mapping = {**mapping, **_collection_mapping_adapter(mapping, image_filename, image_bytes)}
    if expected_patch_id is not None:
        _require_equal(mapping.get("collection_patch_id"), expected_patch_id, "collection patch ID")

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
        voxel_vertices = [[point[0], plane_index, point[1]] for point in polygon["points"]]
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
        "patch_id": mapping.get("collection_patch_id"),
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
        "patch_id": validated.get("patch_id"),
        "annotation_image": {
            "filename": validated["mapping"]["annotation_image"]["filename"],
            "sha256": validated["mapping"]["annotation_image"]["sha256"],
            "shape_rows_cols": validated["mapping"]["annotation_image"]["shape_rows_cols"],
        },
        "transformation_provenance": {
            "labelme_pixel_order": "(u,v)=(x,y), origin top-left raster convention",
            "to_nifti_index": "(i_x,i_y,i_z)=(u,selected_plane,v)",
            "operation": "transpose only; no flip, resize, rotation, or registration",
        },
        "polygons": validated["polygons"],
        "warning": "Labels are user annotation labels, not verified anatomical labels; 3D anatomical alignment is not claimed.",
    }
    return (json.dumps(result, indent=2) + "\n").encode("utf-8")


def _nifti_bytes(array: np.ndarray, affine: np.ndarray) -> bytes:
    image = nib.Nifti1Image(np.asarray(array, dtype=np.uint16), np.asarray(affine, dtype=float))
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as handle:
        nib.save(image, handle.name)
        handle.flush()
        return Path(handle.name).read_bytes()


def build_label_mask(validated: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Rasterize polygons onto one selected Y plane and return NIfTI bytes."""
    image = validated["image"]
    width, height = image.size
    mask_2d = Image.new("I", (width, height), 0)
    draw = ImageDraw.Draw(mask_2d)
    label_table = [{"id": 0, "label": "background"}]
    for label_id, polygon in enumerate(validated["polygons"], start=1):
        rounded = [(int(round(point[0])), int(round(point[1]))) for point in polygon["pixel_vertices_xy"]]
        draw.polygon(rounded, fill=label_id)
        label_table.append({"id": label_id, "label": polygon["label"]})
    mask_array_2d = np.asarray(mask_2d, dtype=np.uint16)
    mask_xyz = mask_array_2d.T[:, None, :]
    affine = np.asarray(validated["affine"], dtype=float).copy()
    plane = int(validated["plane_index"])
    affine[:3, 3] = (np.asarray(validated["affine"], dtype=float) @ np.array([0.0, plane, 0.0, 1.0]))[:3]
    metadata = {
        "shape_xyz": [int(value) for value in mask_xyz.shape],
        "affine": affine.tolist(),
        "selected_plane": {"axis": "y", "index": plane},
        "label_table": label_table,
        "rasterization": {
            "pixel_centres": "Labelme integer coordinates are pixel centres; vertices are rounded to nearest pixel for rasterization",
            "overlap": "later polygons in Labelme order overwrite earlier polygons",
            "out_of_bounds": "rejected during validation",
            "extrusion": "none; mask has one Y slice only",
        },
    }
    return _nifti_bytes(mask_xyz, affine), metadata


def build_import_package(validated: dict[str, Any]) -> bytes:
    """Build a self-contained polygon JSON + labelled mask package."""
    mask_bytes, mask_metadata = build_label_mask(validated)
    polygon_json = json.loads(build_import_export(validated).decode("utf-8"))
    polygon_json["label_mask"] = mask_metadata
    polygon_json["external_tool_round_trip"] = "not completed; native Labelme JSON schema validated without GUI evidence"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("polygon_annotations.json", json.dumps(polygon_json, indent=2) + "\n")
        archive.writestr("label_mask.nii.gz", mask_bytes)
        archive.writestr("label_table.json", json.dumps(mask_metadata["label_table"], indent=2) + "\n")
        archive.writestr("source_annotation.png", validated["image_bytes"])
        archive.writestr(
            "README.txt",
            "Native Labelme polygon import for one collection patch.\n\n"
            "PNG (u,v) uses origin at the top-left and maps to NIfTI "
            "(i_x,i_y,i_z)=(u, selected_y, v). The selected Y plane is not "
            "extruded. Vertices are preserved in polygon_annotations.json; "
            "mask rasterization rounds vertices to nearest pixel and later "
            "polygons overwrite earlier ones. Out-of-bounds vertices and "
            "unsupported shapes are rejected. Labels are user labels, not "
            "verified anatomical labels.\n",
        )
    return output.getvalue()
