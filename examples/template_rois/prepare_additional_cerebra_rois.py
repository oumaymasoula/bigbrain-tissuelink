#!/usr/bin/env python3
"""Create upload-ready binary ROI examples from the preserved CerebrA atlas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ATLAS_PATH = (
    PROJECT_ROOT
    / "outputs/external_roi_feasibility/cerebra"
    / "mni_icbm152_CerebrA_tal_nlin_sym_09c.nii"
)
OUTPUT_DIR = Path(__file__).resolve().parent

EXPECTED_SHAPE = (193, 229, 193)
EXPECTED_AFFINE = np.array(
    [
        [1.0, 0.0, 0.0, -96.0],
        [0.0, 1.0, 0.0, -132.0],
        [0.0, 0.0, 1.0, -78.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)
TEMPLATE_NAME = (
    "ICBM 2009c nonlinear symmetric (MNI152, tal_nlin_sym_09c), 1 mm"
)

ROIS = (
    ("right_precentral", "Precentral", "right", 35),
    ("left_postcentral", "Postcentral", "left", 64),
    ("right_cuneus", "Cuneus", "right", 43),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    atlas = nib.load(ATLAS_PATH)
    if atlas.shape != EXPECTED_SHAPE:
        raise ValueError(f"Unexpected atlas shape: {atlas.shape}")
    if not np.array_equal(atlas.affine, EXPECTED_AFFINE):
        raise ValueError(f"Unexpected atlas affine:\n{atlas.affine}")

    atlas_data = np.asanyarray(atlas.dataobj)
    for slug, region, hemisphere, label in ROIS:
        nifti_path = OUTPUT_DIR / (
            f"cerebra_{slug}_icbm2009c_sym_1mm_binary_roi.nii.gz"
        )
        provenance_path = OUTPUT_DIR / f"cerebra_{slug}_provenance.json"
        if nifti_path.exists() or provenance_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing output for {slug}"
            )

        mask = np.asarray(atlas_data == label, dtype=np.uint8)
        nonzero = int(np.count_nonzero(mask))
        if nonzero == 0:
            raise ValueError(f"CerebrA label {label} has no voxels")

        image = nib.Nifti1Image(mask, atlas.affine)
        image.set_qform(atlas.affine, code=1)
        image.set_sform(atlas.affine, code=1)
        image.header.set_data_dtype(np.uint8)
        image.header.set_xyzt_units("mm")
        nib.save(image, nifti_path)

        saved = nib.load(nifti_path)
        saved_data = np.asanyarray(saved.dataobj)
        unique_values = np.unique(saved_data).astype(int).tolist()
        if saved.shape != EXPECTED_SHAPE:
            raise ValueError(f"Saved shape mismatch for {nifti_path.name}")
        if not np.array_equal(saved.affine, EXPECTED_AFFINE):
            raise ValueError(f"Saved affine mismatch for {nifti_path.name}")
        if unique_values != [0, 1]:
            raise ValueError(
                f"Saved values are not binary for {nifti_path.name}: {unique_values}"
            )

        provenance = {
            "file": nifti_path.name,
            "roi": f"CerebrA {region}",
            "hemisphere": hemisphere,
            "source_label": label,
            "source_atlas_file": ATLAS_PATH.name,
            "extraction": f"binary mask where source atlas label == {label}",
            "template": TEMPLATE_NAME,
            "shape_xyz": list(EXPECTED_SHAPE),
            "voxel_size_mm_xyz": [1.0, 1.0, 1.0],
            "affine": EXPECTED_AFFINE.tolist(),
            "binary_values": unique_values,
            "nonzero_voxels": nonzero,
            "sha256": sha256(nifti_path),
            "anatomical_status": "Awaiting independent review",
        }
        provenance_path.write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{nifti_path.name}: label={label}, voxels={nonzero}, "
            f"sha256={provenance['sha256']}"
        )


if __name__ == "__main__":
    main()
