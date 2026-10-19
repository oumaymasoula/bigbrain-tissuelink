"""Bounded BigBrain histology crop CLI and export helpers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image

SECTION_ID = "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126"
SECTION_LABEL = "#3458: selected 1 micron scans of BigBrain histological sections (v1.0) (cell body staining)"
SPACE = "bigbrain"
SOURCE_URL = "https://search.kg.ebrains.eu/instances/73c1fa55-d099-4854-8cda-c9a403c6080a"
LICENSE = "CC BY-NC-SA 4.0 (BigBrain dataset; verify current terms at source)"
MAX_BYTES = 10 * 1024 * 1024
# This 2 mm crop was checked at 10 µm request resolution: y=1 contains tissue
# with a non-degenerate 8-bit intensity range; y=0 is the section background.
DEFAULT_BOUNDS = (-20.0, -0.87, -20.0, -18.0, -0.85, -18.0)
SECTION_QUERY_BOUNDS = (-100.0, -100.0, -100.0, 100.0, 100.0, 100.0)


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def validate(self) -> None:
        if not np.all(np.isfinite(np.asarray(list(asdict(self).values()), dtype=float))):
            raise ValueError("all bounds must be finite")
        if self.max_x <= self.min_x or self.max_y <= self.min_y or self.max_z <= self.min_z:
            raise ValueError("bounds must have strictly positive width in every axis")

    def to_bbox(self):
        from siibra.locations import BoundingBox
        self.validate()
        return BoundingBox([self.min_x, self.min_y, self.min_z], [self.max_x, self.max_y, self.max_z], space=SPACE)


def _section_number(label: str) -> int:
    try:
        return int(label.split("#", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return 10**9


def _provider_metadata(section):
    """Read only the official provider metadata for one configured section."""
    provider = next(iter(section._providers.values()))
    volume = next(iter(provider._fragments.values()))
    if volume._info is None:
        volume._bootstrap()
    info = volume._info or {}
    return provider, volume, info


@lru_cache(maxsize=1)
def available_sections():
    """Return configured, registered sections without downloading image data.

    The siibra feature query is restricted to ``CellbodyStainedSection`` and
    records are retained only when the configured provider identifies the
    registered-section endpoint. Raw or unaligned providers are excluded; no
    URL or coordinate is constructed from a section number.
    """
    import siibra
    from siibra.locations import BoundingBox
    query = BoundingBox(SECTION_QUERY_BOUNDS[:3], SECTION_QUERY_BOUNDS[3:], space=SPACE)
    result = []
    for section in siibra.features.get(query, "CellbodyStainedSection"):
        bbox = section.get_boundingbox(clip=False)
        provider, volume, info = _provider_metadata(section)
        source_url = str(provider._init_url)
        if "/registered_sections/" not in source_url:
            continue
        resolutions = []
        for scale in info.get("scales", []):
            resolutions.append({
                "key": scale["key"],
                "voxel_size_mm": [float(value) / 1_000_000.0 for value in scale["resolution"]],
            })
        bounds_mm = {
            "min_x": float(bbox.minpoint[0]), "min_y": float(bbox.minpoint[1]), "min_z": float(bbox.minpoint[2]),
            "max_x": float(bbox.maxpoint[0]), "max_y": float(bbox.maxpoint[1]), "max_z": float(bbox.maxpoint[2]),
        }
        result.append({
            "id": section.id,
            "label": section.name,
            "section_number": _section_number(section.name),
            "source_url": source_url,
            "coordinate_space": getattr(section.space, "name", str(section.space)),
            "bounds_mm": bounds_mm,
            "section_plane_y_mm": (bounds_mm["min_y"] + bounds_mm["max_y"]) / 2.0,
            "resolutions": resolutions,
            "dataset_order": list(info.get("dataset_order", [])),
            "provider_transform_nm": np.asarray(volume.transform_nm, dtype=float).tolist(),
            "provider_class": type(provider).__name__,
            "registration_status": "registered provider metadata",
            "metadata_retrieval_status": "verified from installed siibra configuration",
            "real_fetch_verification_status": "not verified in this session",
            "section": section,
        })
    return tuple(sorted(result, key=lambda item: item["section_number"]))


def section_catalogue():
    """Return JSON-safe metadata for the registered-section catalogue."""
    return tuple({key: value for key, value in item.items() if key != "section"} for item in available_sections())


def get_section(section_id: str = SECTION_ID):
    for item in available_sections():
        if item["id"] == section_id:
            return item["section"]
    raise ValueError(f"section {section_id} is not available in the public metadata")


def fetch_crop(bounds: Bounds, resolution_mm: float = 0.01, max_bytes: int = MAX_BYTES, section_id: str = SECTION_ID):
    if resolution_mm <= 0:
        raise ValueError("resolution_mm must be positive; -1/full resolution is intentionally not used")
    os.environ.setdefault("SIIBRA_MAX_FETCH_SIZE_BYTES", str(max_bytes))
    section = get_section(section_id)
    section_bounds = section.get_boundingbox(clip=False)
    requested = bounds.to_bbox()
    if not requested.intersection(section_bounds):
        raise ValueError("requested bounds have an empty intersection with the selected section")
    image = section.fetch(voi=requested, resolution_mm=resolution_mm, max_bytes=max_bytes)
    if image.shape[0] == 0 or image.shape[2] == 0:
        raise RuntimeError("siibra returned an empty crop")
    return image, section, section_bounds


def display_plane(image) -> tuple[np.ndarray, int, tuple[int, int]]:
    """Return the most informative section-thickness slice for visualization only."""
    data = np.asarray(image.dataobj)
    scores = [float(np.std(data[:, index, :])) for index in range(data.shape[1])]
    slice_index = int(np.argmax(scores))
    plane = data[:, slice_index, :]
    low, high = np.percentile(plane, [1, 99])
    if high <= low:
        display = plane.astype(np.uint8, copy=False)
    else:
        display = np.clip((plane.astype(np.float32) - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)
    return display, slice_index, (int(plane.min()), int(plane.max()))


def map_preview_rect_to_source(rect, affine, source_shape, display_size, view_origin=(0.0, 0.0), view_size=None, canvas_size=None):
    """Map all four display rectangle edges to source x/z coordinates.

    The displayed overview is ``plane.T``: display horizontal is source z and
    display vertical is source x. ``display_size`` is ``(width, height)``.
    """
    if not rect:
        return None
    canvas_width, canvas_height = canvas_size or display_size
    window_width, window_height = view_size or display_size
    left = min(float(rect["left"]), float(rect["left"] + rect["width"]))
    right = max(float(rect["left"]), float(rect["left"] + rect["width"]))
    top = min(float(rect["top"]), float(rect["top"] + rect["height"]))
    bottom = max(float(rect["top"]), float(rect["top"] + rect["height"]))
    full_u0 = float(view_origin[0]) + left * window_width / canvas_width
    full_u1 = float(view_origin[0]) + right * window_width / canvas_width
    full_v0 = float(view_origin[1]) + top * window_height / canvas_height
    full_v1 = float(view_origin[1]) + bottom * window_height / canvas_height
    scale_u = source_shape[2] / display_size[0]
    scale_v = source_shape[0] / display_size[1]
    u0, u1 = full_u0 * scale_u, full_u1 * scale_u
    v0, v1 = full_v0 * scale_v, full_v1 * scale_v
    corners = [affine @ np.array([v, 0.0, u, 1.0]) for u, v in ((u0, v0), (u1, v0), (u0, v1), (u1, v1))]
    xs = [float(point[0]) for point in corners]
    zs = [float(point[2]) for point in corners]
    return min(xs), min(zs), max(xs), max(zs), corners


def map_source_bounds_to_preview_rect(bounds_xz, affine, source_shape, display_size, view_origin=(0.0, 0.0), view_size=None, canvas_size=None):
    """Map source x/z bounds back into the current displayed overview view."""
    canvas_width, canvas_height = canvas_size or display_size
    window_width, window_height = view_size or display_size
    min_x, min_z, max_x, max_z = [float(value) for value in bounds_xz]
    inverse = np.linalg.inv(np.asarray(affine, dtype=float))
    source_points = [
        np.array([x, 0.0, z, 1.0])
        for x in (min_x, max_x)
        for z in (min_z, max_z)
    ]
    display_points = []
    for point in source_points:
        voxel = inverse @ point
        full_u = voxel[2] * display_size[0] / source_shape[2]
        full_v = voxel[0] * display_size[1] / source_shape[0]
        display_points.append((
            (full_u - view_origin[0]) * canvas_width / window_width,
            (full_v - view_origin[1]) * canvas_height / window_height,
        ))
    left = min(point[0] for point in display_points)
    top = min(point[1] for point in display_points)
    right = max(point[0] for point in display_points)
    bottom = max(point[1] for point in display_points)
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def export_crop(image, section, requested: Bounds, actual_dir: Path, resolution_mm: float) -> Path:
    actual_dir.mkdir(parents=True, exist_ok=True)
    nifti_path = actual_dir / "bigbrain_crop.nii.gz"
    png_path = actual_dir / "bigbrain_crop_preview.png"
    metadata_path = actual_dir / "metadata.json"
    zip_path = actual_dir / "bigbrain_cutout_bundle.zip"
    nib.save(image, nifti_path)
    data = np.asanyarray(image.dataobj)
    # Visualization only: retain scientific values in NIfTI; normalize PNG for viewing.
    plane, slice_index, raw_range = display_plane(image)
    Image.fromarray(plane).save(png_path)
    affine = np.asarray(image.affine).tolist()
    actual = {
        "shape_voxels": list(image.shape),
        "voxel_size_mm": [float(v) for v in image.header.get_zooms()[:3]],
        "affine": affine,
        "dtype": str(data.dtype),
        "uncompressed_bytes_estimate": int(data.nbytes),
    }
    affine_array = np.asarray(image.affine, dtype=float)
    center_points = np.array([
        affine_array @ np.array([x, y, z, 1.0])
        for x in (0, image.shape[0] - 1)
        for y in (0, image.shape[1] - 1)
        for z in (0, image.shape[2] - 1)
    ])[:, :3]
    center_bounds = [center_points.min(axis=0).tolist(), center_points.max(axis=0).tolist()]
    half_extent = 0.5 * np.abs(affine_array[:3, :3]).sum(axis=1)
    edge_bounds = [(center_points.min(axis=0) - half_extent).tolist(), (center_points.max(axis=0) + half_extent).tolist()]
    zero_thickness_planes = [int(index) for index in range(data.shape[1]) if not np.any(data[:, index, :])]
    metadata = {
        "section_id": section.id,
        "section_label": section.name,
        "source_url": next(iter(section._providers.values()))._init_url,
        "coordinate_space": SPACE,
        "requested_bounds_mm": asdict(requested),
        "actual": actual,
        "requested_resolution_mm": resolution_mm,
        "resolution_note": "siibra selected the nearest provider resolution; actual voxel size is authoritative",
        "orientation": "source affine; array axes are x,y,z and y is the one-section-thickness axis",
        "clipping_padding": {
            "project_added_padding": False,
            "provider_zero_filled_thickness_planes": zero_thickness_planes,
            "note": "siibra may return zero-filled planes when a requested voxel interval extends beyond the provider's one-sample section thickness; no plane is squeezed or discarded",
        },
        "voxel_convention": {
            "affine_maps_voxel_centres": True,
            "actual_voxel_centre_bounds_mm": center_bounds,
            "actual_voxel_edge_bounds_mm": edge_bounds,
            "edge_note": "edge bounds extend half a voxel beyond the outer voxel centres along each physical axis",
        },
        "software": {"siibra": "1.0.1-alpha.25", "python": sys.version.split()[0], "nibabel": nib.__version__},
        "retrieval_date_utc": datetime.now(timezone.utc).isoformat(),
        "license": LICENSE,
        "scientific_export": "NIfTI preserves the original uint8 voxel values",
        "png_note": "visualization preview, not the scientific export",
        "visualization": {
            "slice_axis": "y",
            "slice_index": slice_index,
            "raw_intensity_range": list(raw_range),
            "contrast": "percentile 1-99 linear stretch for PNG only; NIfTI is unmodified",
        },
        "reproduction_command": (
            ".venv/bin/python bigbrain_cutout.py --out outputs/verified_patch "
            f"--section-id {section.id} --resolution-mm {resolution_mm:.17g} --max-bytes {MAX_BYTES} --bounds "
            f"{requested.min_x:.17g} {requested.min_y:.17g} {requested.min_z:.17g} "
            f"{requested.max_x:.17g} {requested.max_y:.17g} {requested.max_z:.17g}"
        ),
    }
    metadata["sha256_nifti"] = hashlib.sha256(nifti_path.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in (nifti_path, png_path, metadata_path):
            zf.write(path, path.name)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one bounded public BigBrain histology crop")
    parser.add_argument("--out", type=Path, default=Path("outputs/verified_patch"))
    parser.add_argument("--resolution-mm", type=float, default=0.01)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--section-id", default=SECTION_ID)
    parser.add_argument("--bounds", type=float, nargs=6, metavar=("MIN_X", "MIN_Y", "MIN_Z", "MAX_X", "MAX_Y", "MAX_Z"), default=DEFAULT_BOUNDS)
    args = parser.parse_args()
    try:
        bounds = Bounds(*args.bounds)
        image, section, _ = fetch_crop(bounds, args.resolution_mm, args.max_bytes, args.section_id)
        bundle = export_crop(image, section, bounds, args.out, args.resolution_mm)
        print(json.dumps({"section_id": section.id, "shape": image.shape, "affine": image.affine.tolist(), "bundle": str(bundle)}, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: crop could not be fulfilled: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
