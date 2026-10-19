"""Polygon annotation mapping and bundle helpers for BigBrain crops."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import numpy as np


def polygon_objects(canvas_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return polygon objects from a drawable-canvas JSON document."""
    if not canvas_json:
        return []
    result = []
    for index, obj in enumerate(canvas_json.get("objects", [])):
        if str(obj.get("type", "")).lower() != "polygon":
            continue
        points = obj.get("points")
        if not isinstance(points, list) or len(points) < 3:
            continue
        normalized = []
        left = float(obj.get("left", 0.0))
        top = float(obj.get("top", 0.0))
        scale_x = float(obj.get("scaleX", 1.0)) * (-1.0 if obj.get("flipX") else 1.0)
        scale_y = float(obj.get("scaleY", 1.0)) * (-1.0 if obj.get("flipY") else 1.0)
        angle = np.deg2rad(float(obj.get("angle", 0.0)))
        cos_angle, sin_angle = float(np.cos(angle)), float(np.sin(angle))
        for point in points:
            if isinstance(point, dict):
                point = [point.get("x"), point.get("y")]
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError(f"polygon {index} contains an invalid vertex")
            # Fabric's serialized polygon points in the installed component
            # are canvas coordinates when pathOffset is absent. When a
            # pathOffset is present, they are local object coordinates.
            if obj.get("pathOffset") is None:
                local_x = (float(point[0]) - left) * scale_x
                local_y = (float(point[1]) - top) * scale_y
            else:
                path_offset = obj["pathOffset"]
                local_x = (float(point[0]) - float(path_offset.get("x", 0.0))) * scale_x
                local_y = (float(point[1]) - float(path_offset.get("y", 0.0))) * scale_y
            x, y = left + cos_angle * local_x - sin_angle * local_y, top + sin_angle * local_x + cos_angle * local_y
            if not np.isfinite([x, y]).all():
                raise ValueError(f"polygon {index} contains a non-finite vertex")
            normalized.append([x, y])
        result.append({"index": index, "points": normalized})
    return result


def map_crop_polygon_to_source(
    points_xy: list[list[float]],
    crop_shape: tuple[int, ...],
    crop_affine: np.ndarray,
    canvas_size: tuple[int, int],
    plane_index: int,
) -> dict[str, list[list[float]]]:
    """Map canvas pixels to crop voxel indices and physical coordinates.

    The crop visualization is ``Image.fromarray(data[:, y, :].T)``. Thus
    canvas ``(u, v)`` maps to crop voxel ``(i_x=u, i_y=plane, i_z=v)``.
    Coordinates are kept fractional until export so the mapping is auditable.
    """
    width, height = [float(value) for value in canvas_size]
    if width <= 0 or height <= 0:
        raise ValueError("annotation canvas dimensions must be positive")
    source_vertices = []
    physical_vertices = []
    for u, v in points_xy:
        if not np.isfinite([u, v]).all() or not (0.0 <= float(u) < width and 0.0 <= float(v) < height):
            raise ValueError("polygon vertex is outside the confirmed crop canvas")
        ix = float(u) * (int(crop_shape[0]) / width)
        iz = float(v) * (int(crop_shape[2]) / height)
        voxel = [ix, float(plane_index), iz]
        source_vertices.append(voxel)
        physical_vertices.append(
            (np.asarray(crop_affine, dtype=float) @ np.array([*voxel, 1.0]))[:3].tolist()
        )
    return {
        "canvas_vertices_xy": points_xy,
        "nifti_voxel_vertices_xyz": source_vertices,
        "physical_vertices_mm": physical_vertices,
    }


def build_polygon_export(
    *,
    section_id: str,
    section_label: str,
    source_url: str,
    coordinate_space: str,
    requested_bounds: dict[str, float],
    requested_resolution_mm: float,
    crop_shape: tuple[int, ...],
    actual_voxel_size_mm: list[float],
    affine: np.ndarray,
    plane_index: int,
    canvas_size: tuple[int, int],
    polygons: list[dict[str, Any]],
    image_filename: str = "bigbrain_crop.nii.gz",
) -> dict[str, Any]:
    """Build a self-describing polygon sidecar for a downloaded crop."""
    return {
        "format": "bigbrain-cutout-polygons-v1",
        "section_id": section_id,
        "section_label": section_label,
        "source_url": source_url,
        "coordinate_space": coordinate_space,
        "requested_bounds_mm": requested_bounds,
        "requested_resolution_mm": float(requested_resolution_mm),
        "actual_shape_voxels": list(crop_shape),
        "actual_voxel_size_mm": [float(value) for value in actual_voxel_size_mm],
        "image_filename": image_filename,
        "selected_plane": {"axis": "y", "index": int(plane_index)},
        "affine": np.asarray(affine, dtype=float).tolist(),
        "display_mapping": {
            "display_image": "data[:, selected_plane, :].T",
            "display_pixel_order": "(u,v)=(x right,y down)",
            "to_nifti_index": "(i_x,i_y,i_z)=(u,selected_plane,v)",
            "transpose": True,
            "flip_x": False,
            "flip_z": False,
            "display_canvas_size_px": list(canvas_size),
            "note": "display contrast is visualization-only; NIfTI values remain raw",
        },
        "polygons": polygons,
        "warning": "User labels are annotations, not verified anatomical labels; no 3D registration is claimed.",
    }


def append_polygon_files_to_bundle(
    bundle_path: Path,
    output_dir: Path,
    polygon_export: dict[str, Any],
) -> Path:
    """Append annotation and mapping JSON to an existing export ZIP."""
    annotations_path = output_dir / "polygon_annotations.json"
    mapping_path = output_dir / "polygon_mapping.json"
    annotations_path.write_text(json.dumps(polygon_export, indent=2) + "\n", encoding="utf-8")
    mapping_path.write_text(
        json.dumps(
            {
                "format": polygon_export["format"],
                "section_id": polygon_export["section_id"],
                "coordinate_space": polygon_export["coordinate_space"],
                "source_url": polygon_export["source_url"],
                "image_filename": polygon_export["image_filename"],
                "actual_shape_voxels": polygon_export["actual_shape_voxels"],
                "actual_voxel_size_mm": polygon_export["actual_voxel_size_mm"],
                "affine": polygon_export["affine"],
                "selected_plane": polygon_export["selected_plane"],
                "display_mapping": polygon_export["display_mapping"],
                "polygon_file": annotations_path.name,
                "polygon_file_sha256": hashlib.sha256(annotations_path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary = bundle_path.with_name(bundle_path.name + ".tmp")
    with zipfile.ZipFile(bundle_path, "r") as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.write(annotations_path, annotations_path.name)
        target.write(mapping_path, mapping_path.name)
    os.replace(temporary, bundle_path)
    return bundle_path
