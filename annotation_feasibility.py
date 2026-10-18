"""Create and validate a small Labelme feasibility fixture from an existing crop.

This intentionally does not download data. It uses the already validated UI export.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw

from bigbrain_cutout import LICENSE, SECTION_ID, SOURCE_URL, SPACE

PROVIDER_SOURCE_URL = "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed"


INPUT = Path("outputs/ui_export/bigbrain_crop.nii.gz")
OUT = Path("outputs/annotation_feasibility")
PLANE_INDEX_Y = 1
# Asymmetric polygon near the visible tissue/background fissure boundary in the
# existing crop. Labelme coordinates are (image x, image y) = (u, v).
POLYGON = [
    [170.0, 170.0],
    [231.0, 181.0],
    [225.0, 222.0],
    [194.0, 236.0],
    [158.0, 211.0],
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image = nib.load(str(INPUT))
    data = np.asanyarray(image.dataobj)
    if data.ndim != 3 or data.shape[1] <= PLANE_INDEX_Y:
        raise RuntimeError(f"expected a 3D crop with y plane {PLANE_INDEX_Y}, got {data.shape}")
    if data.dtype != np.uint8:
        raise RuntimeError(f"expected unchanged uint8 source values, got {data.dtype}")

    # NIfTI array indices are (i_x, i_y, i_z). A conventional 2D image uses
    # rows=v and columns=u, so transpose source x/z into (row=z, col=x).
    source_plane_xz = data[:, PLANE_INDEX_Y, :]
    annotation_pixels = source_plane_xz.T.copy()
    raw_png = OUT / "bigbrain_crop_y1_raw.png"
    Image.fromarray(annotation_pixels, mode="L").save(raw_png)

    overlay = Image.fromarray(annotation_pixels, mode="L").convert("RGB")
    draw = ImageDraw.Draw(overlay)
    draw.polygon([tuple(point) for point in POLYGON], outline=(255, 0, 0), width=2)
    overlay_path = OUT / "bigbrain_crop_y1_polygon_overlay.png"
    overlay.save(overlay_path)

    height, width = annotation_pixels.shape
    if not all(0 <= x < width and 0 <= y < height for x, y in POLYGON):
        raise RuntimeError("polygon is clipped by the annotation image bounds")

    affine = np.asarray(image.affine, dtype=float)
    nifti_indices = [[int(round(v)), PLANE_INDEX_Y, int(round(u))] for u, v in POLYGON]
    physical_vertices = [
        (affine @ np.array([ix, iy, iz, 1.0]))[:3].tolist()
        for ix, iy, iz in nifti_indices
    ]
    labelme = {
        "version": "5.7.0",
        "flags": {},
        "shapes": [{
            "label": "fissure_adjacent_tissue_example",
            "points": POLYGON,
            "group_id": None,
            "description": "Asymmetric fixture polygon near visible tissue/background fissure boundary; not an anatomical label.",
            "shape_type": "polygon",
            "flags": {},
            "mask": None,
        }],
        "imagePath": raw_png.name,
        "imageData": None,
        "imageHeight": int(height),
        "imageWidth": int(width),
    }
    (OUT / "bigbrain_crop_y1_raw.json").write_text(json.dumps(labelme, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "fixture_validated_without_external_labelme_round_trip",
        "input_nifti": str(INPUT),
        "source_identity": {
            "section_id": SECTION_ID,
            "source_url": PROVIDER_SOURCE_URL,
            "catalog_url": SOURCE_URL,
            "coordinate_space": SPACE,
            "coordinate_space_label": "BigBrain microscopic template (histology)",
            "license": LICENSE,
            "source_nifti_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        },
        "section_id": SECTION_ID,
        "coordinate_space": SPACE,
        "nifti_shape": list(image.shape),
        "source_affine": np.asarray(image.affine, dtype=float).tolist(),
        "selected_plane": {"axis": "y", "index": PLANE_INDEX_Y, "source_array_plane": "data[:, 1, :]"},
        "annotation_image": {
            "path": raw_png.name,
            "shape_rows_cols": [int(height), int(width)],
            "dtype": str(annotation_pixels.dtype),
            "filename": raw_png.name,
            "sha256": hashlib.sha256(raw_png.read_bytes()).hexdigest(),
            "pixel_values_unchanged": bool(np.array_equal(annotation_pixels, source_plane_xz.T)),
            "mapping": "annotation pixel (u, v) -> NIfTI voxel index (i_x=v, i_y=1, i_z=u); transpose only, no flip",
            "mapping_contract": {
                "annotation_pixel_order": ["u", "v"],
                "nifti_index_order": ["i_x", "i_y", "i_z"],
                "formula": {"i_x": "v", "i_y": "selected_plane", "i_z": "u"},
                "transpose": True,
                "flip_x": False,
                "flip_z": False,
            },
        },
        "labelme_polygon_pixels_xy": POLYGON,
        "mapped_nifti_voxel_indices_xyz": nifti_indices,
        "mapped_physical_vertices_mm": physical_vertices,
        "all_vertices_inside_image": True,
        "no_3d_alignment_claim": True,
    }
    (OUT / "mapping_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
