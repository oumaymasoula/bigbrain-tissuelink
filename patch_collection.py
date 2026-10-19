"""Session-scoped collection helpers for fetched detailed patches."""
from __future__ import annotations

import csv
import base64
import html
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Mapping

import numpy as np

from collection_replay import build_manifest


COLLECTION_MAX_BYTES = 50 * 1024 * 1024


def manual_patch_region_context(region_info: Mapping) -> dict:
    """Return atlas context without asserting membership for a manual patch."""
    return {
        "patch_region_membership": "not established",
        "atlas_context": {
            "parcellation": region_info.get("parcellation"),
            "region": region_info.get("region"),
            "coordinate_space": region_info.get("space"),
            "probability_threshold": region_info.get("threshold"),
            "status": "context only; membership not established",
            "diagnostic_status": "unresolved atlas overlay diagnostics are separate and are not used for manual patch attribution",
        },
    }


def annotation_plane_from_image(image, slice_index: int = 0) -> tuple[np.ndarray, dict]:
    """Build the unmarked annotation PNG plane and its independent mapping.

    This is intentionally separate from the interactive registered-section
    display convention.  Scientific NIfTI data are ``(x, y, z)``; this plane
    is ``data[:, slice_index, :].T`` so ``PNG[v, u]`` is
    ``data[u, slice_index, v]``: PNG columns are source X and rows are
    source Z. Only display normalization is applied.
    """
    data = np.asanyarray(image.dataobj)
    if data.ndim != 3 or not 0 <= int(slice_index) < data.shape[1]:
        raise ValueError(f"annotation plane requires a 3-D image and valid y slice; got {data.shape}")
    plane_xz = np.asarray(data[:, int(slice_index), :])
    finite = plane_xz[np.isfinite(plane_xz)]
    if finite.size == 0:
        display = np.zeros(plane_xz.T.shape, dtype=np.uint8)
        low, high = 0.0, 0.0
    else:
        low, high = np.percentile(finite, [1.0, 99.0])
        if high <= low:
            low, high = float(finite.min()), float(finite.max())
        if high <= low:
            display = np.zeros(plane_xz.T.shape, dtype=np.uint8)
        else:
            display = np.clip((plane_xz.astype(np.float32) - low) * 255.0 / (high - low), 0, 255).astype(np.uint8).T
    return display, {
        "source_plane_expression": f"data[:,{int(slice_index)},:].T",
        "source_slice_index_y": int(slice_index),
        "png_shape_rows_cols": [int(value) for value in display.shape],
        "png_horizontal_source_axis": "x",
        "png_vertical_source_axis": "z",
        "pixel_to_nifti_voxel": "(u, v) -> (u, slice_index_y, v)",
        "transpose": True,
        "flip_horizontal": False,
        "flip_vertical": False,
        "display_normalization": "independent 1st–99th percentile linear uint8 conversion",
        "normalization_low": float(low),
        "normalization_high": float(high),
        "scientific_values_preserved": True,
    }


def patch_id_for(raw_nifti: bytes, metadata: Mapping) -> str:
    """Return a deterministic ID for one source patch and its geometry."""
    identity = {
        "section_id": metadata.get("section_id"),
        "requested_bounds_mm": metadata.get("requested_bounds_mm"),
        "actual_affine": metadata.get("actual_affine"),
        "actual_voxel_size_mm_xyz": metadata.get("actual_voxel_size_mm_xyz"),
        "source_array_sha256": metadata.get("source_array_sha256"),
    }
    digest = hashlib.sha256(
        raw_nifti + json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"patch-{digest[:16]}"


def bind_unmarked_png_metadata(metadata: Mapping, patch_id: str, png_bytes: bytes, shape_rows_cols: tuple[int, int] | list[int]) -> dict:
    """Record the exact collection PNG identity needed for annotation import."""
    return {
        **dict(metadata),
        "collection_patch_id": str(patch_id),
        "unmarked_png_filename": f"{patch_id}_unmarked_plane.png",
        "unmarked_png_sha256": hashlib.sha256(png_bytes).hexdigest(),
        "unmarked_png_shape_rows_cols": [int(value) for value in shape_rows_cols],
        "unmarked_png_dtype": "uint8",
    }


def entry_bytes(entry: Mapping) -> int:
    return sum(len(entry.get(name, b"")) for name in (
        "raw_nifti", "unmarked_png", "marked_png",
        "source_roi_overlay_png", "transformed_roi_overlay_png",
    ))


def collection_bytes(collection: Mapping[str, Mapping]) -> int:
    return sum(entry_bytes(entry) for entry in collection.values())


def _report_value(value) -> str:
    """Escape a scalar or structured value for an offline HTML report."""
    if value is None or value == "" or value == [] or value == {}:
        return "Not recorded"
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(str(value), quote=True)


def _embedded_png(value: bytes | None, alt: str) -> str:
    if not value:
        return '<p class="missing">Not recorded</p>'
    encoded = base64.b64encode(value).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" alt="{html.escape(alt, quote=True)}">'


def collection_visual_report_html(collection: Mapping[str, Mapping]) -> bytes:
    """Build a self-contained, offline visual report from retained collection data."""
    cards = []
    for patch_id, entry in collection.items():
        metadata = dict(entry.get("metadata", {}))
        transform = metadata.get("transform_provenance")
        transform = transform if isinstance(transform, Mapping) else {}
        atlas_identity = transform.get("atlas_identity")
        atlas_identity = atlas_identity if isinstance(atlas_identity, Mapping) else {}
        route = "Template ROI" if metadata.get("workflow") == "experimental_template_roi" else "Manual browsing"
        if route == "Template ROI" and atlas_identity:
            roi_name = " ".join(
                str(value) for value in (
                    atlas_identity.get("hemisphere"), atlas_identity.get("label_name")
                ) if value
            ) or None
        else:
            roi_name = metadata.get("roi_name")
        template = transform.get("template_identity") or metadata.get("supported_template")
        provenance = transform.get("template_provenance") or metadata.get("roi_provenance")
        input_filename = transform.get("original_filename") or metadata.get("input_roi_filename")
        input_checksum = metadata.get("input_roi_sha256") or transform.get("input_sha256")
        transform_block = transform.get("transform") if isinstance(transform.get("transform"), Mapping) else {}
        output_checksum = transform.get("output_sha256") or transform_block.get("output_sha256")
        container_digest = transform.get("container_digest")
        command = transform.get("executed_command_argv") or transform.get("executed_inner_command")
        interpolation = transform.get("interpolation") or transform_block.get("interpolation")
        direction = transform.get("direction") or transform_block.get("direction")
        if route == "Manual browsing":
            manual_na = "Not applicable — manual selection"
            roi_name = manual_na
            template = manual_na
            provenance = manual_na
            input_filename = manual_na
            input_checksum = manual_na
            output_checksum = manual_na
            container_digest = manual_na
            command = manual_na
            interpolation = manual_na
            direction = manual_na
        review = metadata.get("anatomical_status") or metadata.get("anatomical_review") or transform.get("anatomical_status")
        mapping = metadata.get("annotation_plane_mapping") or metadata.get("annotation_png_mapping")
        bounds = metadata.get("requested_bounds_mm")
        physical_size = None
        if isinstance(bounds, (list, tuple)) and len(bounds) == 6:
            physical_size = [
                float(bounds[3]) - float(bounds[0]),
                float(bounds[4]) - float(bounds[1]),
                float(bounds[5]) - float(bounds[2]),
            ]
        coords = metadata.get("selected_mask_world_xyz_mm") or metadata.get("selected_patch_world_point") or metadata.get("sampling_centre_xz_mm")
        marked = entry.get("marked_png")
        unmarked = entry.get("unmarked_png")
        cards.append(f"""
        <article class="patch">
          <h2>{_report_value(entry.get('user_label') or patch_id)}</h2>
          <p class="route">Starting route: {_report_value(route)}</p>
          <div class="grid">
            <section><h3>Patch identity</h3><dl>
              <dt>Patch ID</dt><dd>{_report_value(patch_id)}</dd>
              <dt>Section ID</dt><dd>{_report_value(metadata.get('section_id'))}</dd>
              <dt>Section number/name</dt><dd>{_report_value(metadata.get('section_number') or metadata.get('section_name') or metadata.get('section_label'))}</dd>
              <dt>BigBrain coordinates</dt><dd>{_report_value(coords)}</dd>
              <dt>Physical bounds (mm)</dt><dd>{_report_value(bounds)}</dd>
              <dt>Physical size X/Y/Z (mm)</dt><dd>{_report_value(physical_size)}</dd>
              <dt>Actual shape</dt><dd>{_report_value(metadata.get('actual_shape_xyz'))}</dd>
              <dt>Actual voxel spacing (mm)</dt><dd>{_report_value(metadata.get('actual_voxel_size_mm_xyz'))}</dd>
              <dt>Source plane</dt><dd>{_report_value(mapping)}</dd>
              <dt>User note</dt><dd>{_report_value(entry.get('user_note'))}</dd>
              <dt>Retained source files</dt><dd>{_report_value(metadata.get('report_source_files'))}</dd>
            </dl></section>
            <section><h3>ROI and processing provenance</h3><dl>
              <dt>ROI name</dt><dd>{_report_value(roi_name)}</dd>
              <dt>Input filename</dt><dd>{_report_value(input_filename)}</dd>
              <dt>Supported template</dt><dd>{_report_value(template)}</dd>
              <dt>ROI provenance</dt><dd>{_report_value(provenance)}</dd>
              <dt>Input ROI SHA-256</dt><dd>{_report_value(input_checksum)}</dd>
              <dt>Transformed output SHA-256</dt><dd>{_report_value(output_checksum)}</dd>
              <dt>Patch array SHA-256</dt><dd>{_report_value(metadata.get('source_array_sha256'))}</dd>
              <dt>Exported NIfTI SHA-256</dt><dd>{_report_value(metadata.get('exported_nifti_sha256'))}</dd>
              <dt>Container digest</dt><dd>{_report_value(container_digest)}</dd>
              <dt>Command</dt><dd>{_report_value(command)}</dd>
              <dt>Interpolation / direction</dt><dd>{_report_value({'interpolation': interpolation, 'direction': direction})}</dd>
              <dt>Anatomical-review status</dt><dd>{_report_value(review)}</dd>
            </dl></section>
          </div>
          <div class="images">
            <figure>{_embedded_png(unmarked, 'Unmarked source-plane preview')}<figcaption>Unmarked source-plane preview</figcaption></figure>
            <figure>{_embedded_png(marked, 'Marked patch preview')}<figcaption>Marked patch preview</figcaption></figure>
            <figure>{_embedded_png(entry.get('source_roi_overlay_png'), 'Source ROI overlay')}<figcaption>Source ROI overlay</figcaption></figure>
            <figure>{_embedded_png(entry.get('transformed_roi_overlay_png'), 'Transformed ROI overlay')}<figcaption>Transformed ROI overlay</figcaption></figure>
          </div>
        </article>""")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BigBrain TissueLink visual report</title><style>
body{{font-family:Arial,sans-serif;color:#102238;background:#f7f9fc;margin:0;padding:2rem;line-height:1.45}}main{{max-width:1200px;margin:auto}}h1,h2,h3{{color:#102238}}.notice{{background:#fff8e7;border:1px solid #ead79c;padding:1rem;border-radius:10px}}.patch{{background:white;border:1px solid #dbe4ec;border-radius:14px;padding:1.25rem;margin:1.25rem 0;page-break-inside:avoid}}.route{{color:#087f8c;font-weight:bold}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}}dl{{display:grid;grid-template-columns:minmax(130px,0.7fr) minmax(0,1.3fr);gap:.35rem .75rem}}dt{{font-weight:bold}}dd{{margin:0;overflow-wrap:anywhere}}.images{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem;margin-top:1rem}}figure{{margin:0;border:1px solid #dbe4ec;padding:.6rem;border-radius:8px}}img{{display:block;width:100%;height:auto}}figcaption{{font-weight:bold;margin-top:.4rem}}.missing{{color:#63748a;font-style:italic}}
</style></head><body><main><h1>BigBrain TissueLink visual report</h1>
<p><strong>Collection overview:</strong> {len(collection)} patch(es).</p>
<p><strong>Two tissue-selection routes:</strong> Manual browsing starts from a registered histology section and a user-selected tissue location. Template ROI starts from a validated binary mask on the supported ICBM2009c symmetric template, transforms it to BigBrain space, identifies intersecting registered sections, and selects a bounded patch at mask coverage. Each patch below retains its own route and provenance.</p>
<p class="notice"><strong>Reference-tissue notice:</strong> BigBrain is reference tissue from one donor. MRI–histology alignment and ROI placement are not clinical findings and may require independent anatomical review.</p>
{''.join(cards) if cards else '<p>No patches recorded.</p>'}</main></body></html>"""
    return document.encode("utf-8")


def collection_visual_report_filename(now: datetime | None = None) -> str:
    """Return a unique, sortable UTC filename without changing report content."""
    moment = now or datetime.now(timezone.utc)
    return f"bigbrain_tissuelink_visual_report_{moment.strftime('%Y%m%dT%H%M%S%fZ')}.html"


def collection_zip_filename(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return f"bigbrain_tissuelink_collection_{moment.strftime('%Y%m%dT%H%M%S%fZ')}.zip"


def add_entry(collection: dict, entry: Mapping, max_bytes: int = COLLECTION_MAX_BYTES) -> str:
    """Add an entry, rejecting duplicates and over-budget collections."""
    patch_id = str(entry["patch_id"])
    if patch_id in collection:
        raise ValueError(f"patch {patch_id} is already in the collection")
    projected = collection_bytes(collection) + entry_bytes(entry)
    if projected > max_bytes:
        raise ValueError(f"collection limit exceeded ({projected:,} > {max_bytes:,} bytes)")
    collection[patch_id] = dict(entry)
    return patch_id


def collection_zip_bytes(collection: Mapping[str, Mapping]) -> bytes:
    """Build one portable ZIP with raw data, annotation-ready planes and manifest."""
    output = io.BytesIO()
    fieldnames = (
        "patch_id", "user_label", "section_id", "section_number", "source_url",
        "coordinate_space", "requested_bounds_mm", "actual_shape_xyz",
        "actual_voxel_size_mm_xyz", "actual_affine", "source_array_sha256",
        "exported_nifti_sha256", "note",
    )
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        rows = []
        for patch_id, entry in collection.items():
            metadata = dict(entry["metadata"])
            prefix = f"patches/{patch_id}"
            archive.writestr(f"{prefix}/{patch_id}.nii.gz", entry["raw_nifti"])
            archive.writestr(f"{prefix}/{patch_id}_unmarked_plane.png", entry["unmarked_png"])
            archive.writestr(f"{prefix}/{patch_id}_marked_preview.png", entry["marked_png"])
            if entry.get("source_roi_overlay_png"):
                archive.writestr(f"{prefix}/{patch_id}_source_roi_overlay.png", entry["source_roi_overlay_png"])
            if entry.get("transformed_roi_overlay_png"):
                archive.writestr(f"{prefix}/{patch_id}_transformed_roi_overlay.png", entry["transformed_roi_overlay_png"])
            archive.writestr(f"{prefix}/metadata.json", json.dumps(metadata, indent=2) + "\n")
            rows.append({
                "patch_id": patch_id,
                "user_label": entry.get("user_label", ""),
                "section_id": metadata.get("section_id", ""),
                "section_number": metadata.get("section_number", ""),
                "source_url": metadata.get("provider_url", ""),
                "coordinate_space": metadata.get("coordinate_space", ""),
                "requested_bounds_mm": json.dumps(metadata.get("requested_bounds_mm", []), separators=(",", ":")),
                "actual_shape_xyz": json.dumps(metadata.get("actual_shape_xyz", []), separators=(",", ":")),
                "actual_voxel_size_mm_xyz": json.dumps(metadata.get("actual_voxel_size_mm_xyz", []), separators=(",", ":")),
                "actual_affine": json.dumps(metadata.get("actual_affine", []), separators=(",", ":")),
                "source_array_sha256": metadata.get("source_array_sha256", ""),
                "exported_nifti_sha256": metadata.get("exported_nifti_sha256", ""),
                "note": entry.get("user_note", ""),
            })
        manifest = io.StringIO()
        writer = csv.DictWriter(manifest, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr("manifest.csv", manifest.getvalue())
        archive.writestr("manifest.json", json.dumps(build_manifest(collection), indent=2) + "\n")
        archive.writestr(
            "README.txt",
            "BigBrain TissueLink patch collection\n\n"
            "Each patch contains a raw native-grid NIfTI, an unmarked display plane "
            "for external annotation, a separate marked preview, and metadata.json.\n"
            "The unmarked plane is the contrast-adjusted data[:,y_slice,:].T view, "
            "where y_slice is the recorded source slice index: PNG[v,u] comes "
            "from source data[u,y_slice,v], with columns as source X and rows "
            "as source Z; see metadata.json "
            "for the separate PNG-pixel-to-NIfTI mapping.\n"
            "PNG planes are visualization/annotation aids; NIfTI values and affines "
            "are the scientific data. Collection state is session-scoped and is not "
            "saved across browser sessions unless this ZIP is downloaded.\n",
        )
    return output.getvalue()
