"""Re-run bounded validation against siibra directly and record evidence."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from bigbrain_cutout import Bounds, DEFAULT_BOUNDS, MAX_BYTES, SECTION_ID, get_section


def package_versions():
    import numpy
    import siibra
    import streamlit

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "siibra": getattr(siibra, "__version__", "unknown"),
        "numpy": numpy.__version__,
        "nibabel": nib.__version__,
        "streamlit": streamlit.__version__,
    }


def direct_fetch(section_id: str, bounds: Bounds, resolution: float):
    section = get_section(section_id)
    image = section.fetch(voi=bounds.to_bbox(), resolution_mm=resolution, max_bytes=MAX_BYTES)
    return image


def image_facts(image):
    data = np.asanyarray(image.dataobj)
    return {
        "shape": list(image.shape),
        "dtype": str(data.dtype),
        "voxel_size_mm": [float(v) for v in image.header.get_zooms()[:3]],
        "affine": np.asarray(image.affine).tolist(),
        "finite_range": [float(np.nanmin(data)), float(np.nanmax(data))],
        "sha256_raw_nifti": hashlib.sha256(nib.Nifti1Image(np.asarray(data), image.affine, image.header).to_bytes()).hexdigest()
        if hasattr(nib.Nifti1Image(np.asarray(data), image.affine, image.header), "to_bytes") else None,
    }


def main():
    out = Path("outputs/direct_validation")
    out.mkdir(parents=True, exist_ok=True)
    bundle_image = nib.load("outputs/ui_export/bigbrain_crop.nii.gz")
    bounds = Bounds(*DEFAULT_BOUNDS)
    direct = direct_fetch(SECTION_ID, bounds, 0.01)
    exported = np.asanyarray(bundle_image.dataobj)
    direct_data = np.asanyarray(direct.dataobj)
    comparison = {
        "section_id": SECTION_ID,
        "source_url": "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed",
        "bounds_mm": list(DEFAULT_BOUNDS),
        "requested_resolution_mm": 0.01,
        "max_bytes": MAX_BYTES,
        "versions": package_versions(),
        "export": image_facts(bundle_image),
        "direct_siibra": image_facts(direct),
        "raw_array_equal": bool(np.array_equal(exported, direct_data)),
        "shape_equal": bool(exported.shape == direct_data.shape),
        "affine_equal_with_nifti_float32_tolerance": bool(np.allclose(bundle_image.affine, direct.affine, rtol=0, atol=1e-6)),
        "affine_max_abs_difference": float(np.max(np.abs(bundle_image.affine - direct.affine))),
        "voxel_size_equal": bool(np.allclose(bundle_image.header.get_zooms()[:3], direct.header.get_zooms()[:3], rtol=0, atol=1e-6)),
        "max_abs_raw_difference": int(np.max(np.abs(exported.astype(np.int16) - direct_data.astype(np.int16)))),
        "resolution_tests": [],
    }
    for requested in (0.01, 0.1):
        image = direct_fetch(SECTION_ID, bounds, requested)
        comparison["resolution_tests"].append({
            "requested_mm": requested,
            "returned_shape": list(image.shape),
            "returned_voxel_size_mm": [float(v) for v in image.header.get_zooms()[:3]],
            "estimated_uncompressed_bytes": int(np.asanyarray(image.dataobj).nbytes),
        })
    (out / "direct_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparison, indent=2))
    if not all(comparison[key] for key in ("raw_array_equal", "shape_equal", "affine_equal_with_nifti_float32_tolerance", "voxel_size_equal")):
        raise SystemExit("direct comparison failed")


if __name__ == "__main__":
    main()
