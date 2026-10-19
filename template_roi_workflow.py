"""Experimental, provenance-first ICBM2009c ROI workflow.

The preserved CerebrA example is loaded, never transformed again. New uploads
are accepted only with an explicit template declaration and each Docker run is
written to a unique evidence directory with complete stdout/stderr logs.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from bigbrain_cutout import Bounds, fetch_crop, section_catalogue
from external_roi_feasibility import image_geometry, sample_image_mask_on_patch, sample_section_plane


ROOT = Path(__file__).resolve().parent
CEREBRA = ROOT / "outputs/external_roi_feasibility/cerebra"
RUNS = ROOT / "outputs/external_roi_runs"
REFERENCE = ROOT / "outputs/external_roi_feasibility/input_icbm2009c_template_mask.nii"
BIGBRAIN = ROOT / "outputs/spatial_feasibility/full8_200um_optbal.nii.gz"
IMAGE = "docker.io/caseypaquola/bigbrainwarp@sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614"
IMAGE_DIGEST = "sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614"
TRANSFORM_SHA256 = "154124103eba32e8c1dab21cb996d43d9046bd6c06d31dc2cefb19539b505104"
GRID_SHA256 = {
    "grid_0": "d8781a6dd3cde6669f6fa0fdf8b13089935a8e86b816b54acfc3164177e6378e",
    "grid_1": "b35001aebad81b0a0715c3b2e4aecfd760e7436ad2986c1496f1363684dc48a0",
    "grid_2": "60823988f6e1abe1080f8007f6dce9f731727622d947524aa8541b904c477492",
    "grid_3": "fa97075c8cb0782706c9927297b003b0aa3fb3e504560a98e74bb8d678537948",
}
SUPPORTED_TEMPLATE = "ICBM 2009c nonlinear symmetric (MNI152, tal_nlin_sym_09c), 1 mm"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_NONZERO_VOXELS = 2_000_000
EXPECTED_SHAPE = (193, 229, 193)
EXPECTED_AFFINE = np.array([[1, 0, 0, -96], [0, 1, 0, -132], [0, 0, 1, -78], [0, 0, 0, 1]], dtype=float)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def validate_binary_roi(image: nib.spatialimages.SpatialImage, serialized_size: int, template_declaration: str) -> dict[str, Any]:
    if template_declaration != SUPPORTED_TEMPLATE:
        raise ValueError("Explicit ICBM 2009c nonlinear symmetric template identification is required")
    if serialized_size <= 0 or serialized_size > MAX_UPLOAD_BYTES:
        raise ValueError(f"ROI upload must be 1–{MAX_UPLOAD_BYTES:,} bytes")
    if image.ndim != 3 or tuple(image.shape) != EXPECTED_SHAPE:
        raise ValueError(f"ROI must have exact shape {EXPECTED_SHAPE}; got {image.shape}")
    affine = np.asarray(image.affine, dtype=float)
    if not np.all(np.isfinite(affine)) or not np.allclose(affine, EXPECTED_AFFINE, atol=1e-6, rtol=0):
        raise ValueError("ROI affine does not exactly match the supported ICBM2009c symmetric 1 mm grid")
    data = np.asanyarray(image.dataobj)
    if not np.all(np.isfinite(data)):
        raise ValueError("ROI contains non-finite values")
    values = np.unique(data)
    if not set(values.tolist()).issubset({0, 1, False, True}) or len(values) < 2:
        raise ValueError(f"ROI must contain both binary values 0 and 1; found {values.tolist()[:10]}")
    nonzero = int(np.count_nonzero(data))
    if nonzero > MAX_NONZERO_VOXELS:
        raise ValueError(f"ROI contains {nonzero:,} nonzero voxels; limit is {MAX_NONZERO_VOXELS:,}")
    return {
        "shape_xyz": list(image.shape), "affine": affine.tolist(),
        "voxel_size_mm_xyz": list(map(float, image.header.get_zooms()[:3])),
        "finite": True, "binary_values": [0, 1], "nonzero_voxels": nonzero,
        "serialized_bytes": serialized_size, "template_declaration": template_declaration,
        "header_identity_warning": "Header geometry validates compatibility only; template identity comes from the user's explicit declaration and provenance record.",
    }


def load_nifti_bytes(value: bytes, filename: str = "upload.nii") -> nib.Nifti1Image:
    suffix = ".nii.gz" if filename.lower().endswith(".nii.gz") else ".nii"
    with tempfile.NamedTemporaryFile(suffix=suffix) as stream:
        stream.write(value)
        stream.flush()
        loaded = nib.load(stream.name)
        return nib.Nifti1Image(np.asanyarray(loaded.dataobj), loaded.affine, header=loaded.header)


def verified_example() -> dict[str, Any]:
    metadata_path = CEREBRA / "cerebra_left_precentral_feasibility.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    files = {
        "input": CEREBRA / "tpl-icbm_desc-cerebra_left_precentral.nii",
        "output": CEREBRA / "tpl-bigbrain_desc-cerebra_left_precentral_histological.nii.gz",
        "patch": CEREBRA / "cerebra_left_precentral_section_patch.nii.gz",
    }
    expected = {
        "input": metadata["transform"]["input_sha256"],
        "output": metadata["transform"]["output_sha256"],
        "patch": metadata["fetch"]["patch_sha256"],
    }
    actual = {name: sha256_file(path) for name, path in files.items()}
    if actual != expected:
        raise ValueError(f"preserved example checksum mismatch: {actual}")
    input_image = nib.load(files["input"])
    validate_binary_roi(input_image, files["input"].stat().st_size, SUPPORTED_TEMPLATE)
    output_image = nib.load(files["output"])
    if set(np.unique(np.asanyarray(output_image.dataobj)).tolist()) != {0.0, 1.0}:
        raise ValueError("preserved transformed example is not binary")
    if metadata["fetch"]["mask_nonpadding_overlap_voxels"] <= 0:
        raise ValueError("preserved example has no verified patch overlap")
    return {"metadata": metadata, "input_image": input_image, "output_image": output_image, "files": files, "checksums": actual}


def run_transform(upload: bytes, filename: str, template_provenance: str) -> dict[str, Any]:
    if not template_provenance.strip():
        raise ValueError("Template provenance is required")
    image = load_nifti_bytes(upload, filename)
    validation = validate_binary_roi(image, len(upload), SUPPORTED_TEMPLATE)
    input_sha = sha256_bytes(upload)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / f"{stamp}-{input_sha[:12]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    input_path = run_dir / "input_roi.nii"
    nib.save(image, input_path)
    desc = f"uploaded_binary_roi_{input_sha[:12]}"
    container_work = "/work"
    inner = [
        "-lc",
        "source /BigBrainWarp/scripts/init.sh && /BigBrainWarp/scripts/icbm_to_bigbrain.sh "
        f"{container_work}/input_roi.nii histological nearest 2 {desc} {container_work}",
    ]
    command = ["docker", "run", "--rm", "--entrypoint", "/bin/bash", "-v", f"{run_dir.resolve()}:{container_work}", IMAGE, *inner]
    started = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr + "\nTIMEOUT after 600 seconds\n", encoding="utf-8")
        timeout_manifest = {
            "started_at_utc": started.isoformat(), "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "timeout", "original_filename": filename, "input_sha256": input_sha,
            "template_identity": SUPPORTED_TEMPLATE, "template_provenance": template_provenance.strip(),
            "validation": validation, "container_image": IMAGE, "container_digest": IMAGE_DIGEST,
            "executed_command_argv": command, "executed_inner_command": inner,
            "interpolation": "nearest-neighbour", "transform_sha256": TRANSFORM_SHA256,
            "transform_grid_sha256": GRID_SHA256, "stdout_log": "stdout.log", "stderr_log": "stderr.log",
            "anatomical_status": "Awaiting independent review",
        }
        (run_dir / "manifest.json").write_text(json.dumps(timeout_manifest, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(f"transform timed out; complete partial logs retained at {run_dir}") from exc
    (run_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    output_path = run_dir / f"tpl-bigbrain_desc-{desc}_histological.nii"
    manifest = {
        "started_at_utc": started.isoformat(), "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "completed" if completed.returncode == 0 and output_path.exists() else "failed",
        "original_filename": filename, "input_sha256": input_sha,
        "template_identity": SUPPORTED_TEMPLATE, "template_provenance": template_provenance.strip(),
        "validation": validation, "container_image": IMAGE, "container_digest": IMAGE_DIGEST,
        "executed_command_argv": command, "executed_inner_command": inner,
        "return_code": completed.returncode, "interpolation": "nearest-neighbour",
        "direction": "ICBM2009c symmetric to BigBrain histological; upstream script uses -invert_transformation",
        "transform_sha256": TRANSFORM_SHA256, "transform_grid_sha256": GRID_SHA256,
        "stdout_log": "stdout.log", "stderr_log": "stderr.log",
        "anatomical_status": "Awaiting independent review",
    }
    if output_path.exists():
        transformed = nib.load(output_path)
        values = np.unique(np.asanyarray(transformed.dataobj))
        if not set(values.tolist()).issubset({0, 1, 0.0, 1.0}):
            manifest["status"] = "failed_nonbinary_output"
        manifest["output_sha256"] = sha256_file(output_path)
        manifest["output_geometry"] = image_geometry(transformed)
        manifest["output_file"] = output_path.name
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if manifest["status"] != "completed":
        raise RuntimeError(f"transform failed; evidence retained at {run_dir}")
    return {"manifest": manifest, "run_dir": run_dir, "input_image": image, "output_image": nib.load(output_path)}


def intersecting_sections(transformed: nib.spatialimages.SpatialImage) -> list[dict[str, Any]]:
    rows = []
    for section in section_catalogue():
        test = sample_section_plane(transformed, section, spacing_mm=2.0)
        if test.get("nonzero_pixels", 0):
            rows.append({**section, "coverage_nonzero_samples": test["nonzero_pixels"], "first_nonzero_world_xyz_mm": test["first_nonzero_world_xyz_mm"]})
    return rows


def fetch_mask_patch(transformed: nib.spatialimages.SpatialImage, section: dict[str, Any], half_width_mm: float = 1.0) -> dict[str, Any]:
    point = np.asarray(section["first_nonzero_world_xyz_mm"], dtype=float)
    y = float(section["section_plane_y_mm"])
    bounds = Bounds(float(point[0] - half_width_mm), y - 0.04, float(point[2] - half_width_mm), float(point[0] + half_width_mm), y + 0.04, float(point[2] + half_width_mm))
    patch, _, _ = fetch_crop(bounds, resolution_mm=0.01, max_bytes=5 * 1024 * 1024, section_id=section["id"])
    data = np.asanyarray(patch.dataobj)
    mask = sample_image_mask_on_patch(transformed, patch)
    nonpadding = (data > 0) & (data < 255)
    overlap = [int(np.count_nonzero(mask[:, i, :] & nonpadding[:, i, :])) for i in range(patch.shape[1])]
    return {"patch": patch, "mask": mask, "bounds": bounds, "point": point.tolist(), "overlap_by_y": overlap, "slice_index": int(np.argmax(overlap))}
