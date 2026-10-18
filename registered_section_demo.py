"""MRI/200 µm/registered-section demonstration for BigBrain section #3458.

This module is deliberately an optional branch of the existing downloader UI.
It uses the provider's documented reference-space affine and does not perform
registration or claim anatomical correspondence.
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from bigbrain_cutout import Bounds, MAX_BYTES, display_plane, fetch_crop, get_section
from volume_alignment import (
    _display_uint8,
    _sample_plane,
    common_world_bounds,
    load_volume,
    nearest_voxel_for_world,
    volume_metadata,
    VolumeSpec,
)


SECTION_ID = "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126"
SECTION_URL = "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed"
OVERVIEW_RESOLUTION_MM = 0.128
OVERVIEW_MAX_BYTES = 5 * 1024 * 1024
ROOT = Path(__file__).resolve().parent
MRI_SPEC = VolumeSpec("donor MRI", ROOT / "outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz")
HIST_SPEC = VolumeSpec("native histology", ROOT / "outputs/spatial_feasibility/full8_200um_optbal.nii.gz")


@st.cache_resource(show_spinner=False)
def registered_context():
    section = get_section(SECTION_ID)
    bbox = section.get_boundingbox(clip=False)
    provider = next(iter(section._providers.values()))
    provider_volume = next(iter(provider._fragments.values()))
    # Bootstrap the official provider metadata once, before any image fetch.
    info = provider_volume._info if provider_volume._info is not None else None
    if info is None:
        provider_volume._bootstrap()
        info = provider_volume._info
    scale = provider_volume.scales[0]
    return section, bbox, provider, provider_volume, info, scale


@st.cache_resource(show_spinner=False)
def registered_volumes():
    return load_volume(MRI_SPEC), load_volume(HIST_SPEC)


@st.cache_data(show_spinner=False)
def registered_overview(bounds_values: tuple[float, ...]):
    bounds = Bounds(*bounds_values)
    image, _, _ = fetch_crop(
        bounds,
        resolution_mm=OVERVIEW_RESOLUTION_MM,
        max_bytes=OVERVIEW_MAX_BYTES,
        section_id=SECTION_ID,
    )
    plane, plane_index, raw_range = display_plane(image)
    return image, plane, plane_index, raw_range


def image_bytes(image) -> bytes:
    # nibabel's NIfTI writer expects a filesystem filename in the installed
    # version; keep this temporary and local so the ZIP remains in memory.
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as handle:
        nib.save(image, handle.name)
        handle.flush()
        return Path(handle.name).read_bytes()


def png_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def raw_array_sha256(image) -> str:
    """Hash source voxel bytes, separately from the serialized NIfTI file."""
    return hashlib.sha256(np.asanyarray(image.dataobj).tobytes(order="C")).hexdigest()


def map_section_pixel_to_world(image, pixel_uv: tuple[float, float], display_size: tuple[int, int], world_y: float) -> dict:
    """Map displayed section (u=z, v=x) to world using voxel centres."""
    plane, _, _ = display_plane(image)
    width, height = display_size
    u, v = pixel_uv
    z_index = float(np.clip(u, 0, width - 1)) * (plane.shape[1] - 1) / max(1, width - 1)
    x_index = float(np.clip(v, 0, height - 1)) * (plane.shape[0] - 1) / max(1, height - 1)
    inverse = np.linalg.inv(np.asarray(image.affine, dtype=float))
    y_index = float((inverse @ np.r_[0.0, world_y, 0.0, 1.0])[1])
    world = (np.asarray(image.affine, dtype=float) @ np.r_[x_index, y_index, z_index, 1.0])[:3]
    return {
        "display_pixel_uv": [float(u), float(v)],
        "source_voxel_xyz_continuous": [x_index, y_index, z_index],
        "world_xyz_mm": world.astype(float).tolist(),
        "mapping": "display u -> source z, display v -> source x; y is the documented section centre; voxel centres",
        "transpose": True,
        "flip_x": False,
        "flip_z": False,
    }


def world_to_grid_pixel(world_xz: tuple[float, float], x_axis: np.ndarray, z_axis: np.ndarray) -> tuple[int, int]:
    if len(x_axis) < 2 or len(z_axis) < 2:
        raise ValueError("reference display axes must contain at least two samples")
    return (
        int(np.clip(np.rint((world_xz[0] - x_axis[0]) / (x_axis[1] - x_axis[0])), 0, len(x_axis) - 1)),
        int(np.clip(np.rint((world_xz[1] - z_axis[0]) / (z_axis[1] - z_axis[0])), 0, len(z_axis) - 1)),
    )


def add_marker(array: np.ndarray, pixel: tuple[int, int], colour=(255, 255, 0)) -> np.ndarray:
    result = np.repeat(array[..., None], 3, axis=2).astype(np.uint8)
    u, v = pixel
    if 0 <= u < result.shape[1]:
        result[:, u] = colour
    if 0 <= v < result.shape[0]:
        result[v, :] = colour
    return result


def add_rect(array: np.ndarray, rect: tuple[int, int, int, int], colour=(0, 255, 255)) -> np.ndarray:
    result = Image.fromarray(array).convert("RGB")
    ImageDraw.Draw(result).rectangle(rect, outline=colour, width=3)
    return np.asarray(result)


def render_registered_demo() -> None:
    st.subheader("Explore registered detailed section #3458")
    st.warning(
        "Reference-space demonstration only. The section is registered in the documented BigBrain reference space, "
        "but this does not establish exact anatomical correspondence, especially with the donor MRI. "
        "Anatomical status: Not independently reviewed. No registration or uncertainty estimate is applied."
    )
    try:
        section, bbox, provider, provider_volume, info, scale = registered_context()
        mri, hist = registered_volumes()
    except Exception as exc:
        st.error(f"Could not load the documented section/provider metadata or local volumes: {exc}")
        return

    bbox_values = tuple(float(v) for v in (*bbox.minpoint, *bbox.maxpoint))
    section_y_center = float((bbox.minpoint[1] + bbox.maxpoint[1]) / 2.0)
    # Use a point inside both volumes to determine the independent Y slice;
    # X/Z selection is done below and never silently copied between sources.
    section_x_center = float((bbox.minpoint[0] + bbox.maxpoint[0]) / 2.0)
    section_z_center = float((bbox.minpoint[2] + bbox.maxpoint[2]) / 2.0)
    slice_probe = np.array([section_x_center, section_y_center, section_z_center])
    mri_voxel, mri_y_center = nearest_voxel_for_world(mri, slice_probe)
    hist_voxel, hist_y_center = nearest_voxel_for_world(hist, slice_probe)
    st.write({
        "section_id": SECTION_ID,
        "provider": SECTION_URL,
        "documented_section_plane_center_y_mm": section_y_center,
        "MRI_sampled_slice_center_y_mm": float(mri_y_center[1]),
        "MRI_sampled_voxel_index_for_slice": mri_voxel.tolist(),
        "histology_200um_sampled_slice_center_y_mm": float(hist_y_center[1]),
        "histology_200um_sampled_voxel_index_for_slice": hist_voxel.tolist(),
        "anatomical_status": "Not independently reviewed",
    })
    st.caption("The section centre is not silently substituted for an arbitrary MRI location. MRI and 200 µm slices are sampled independently at their nearest voxel centres.")

    overview_image, overview_plane, overview_slice, overview_range = registered_overview(bbox_values)
    display_width = min(900, overview_plane.shape[1])
    display_height = max(1, round(overview_plane.shape[0] * display_width / overview_plane.shape[1]))
    overview_display = np.asarray(Image.fromarray(overview_plane.T).resize((display_width, display_height), Image.Resampling.NEAREST))
    st.markdown("### 1. Select X/Z on the registered section overview")
    st.caption(f"Registered section overview: requested {OVERVIEW_RESOLUTION_MM} mm; actual voxel size {[float(x) for x in overview_image.header.get_zooms()[:3]]} mm; displayed plane index y={overview_slice}; raw range {overview_range}.")
    clicked = streamlit_image_coordinates(overview_display, width=display_width, key="registered-section-overview")
    if clicked:
        mapped = map_section_pixel_to_world(overview_image, (clicked["x"], clicked["y"]), (display_width, display_height), section_y_center)
        st.session_state["registered_demo_point"] = mapped
    point = st.session_state.get("registered_demo_point")
    if point is None:
        point = map_section_pixel_to_world(overview_image, (display_width / 2, display_height / 2), (display_width, display_height), section_y_center)
        st.info("Click the overview to choose an X/Z location. The centre marker shown before clicking is only a navigation default and is not an MRI selection.")
    st.write({"selected_section_world_xyz_mm": [round(float(v), 6) for v in point["world_xyz_mm"]], "selected_section_mapping": point["mapping"]})

    common = common_world_bounds([mri, hist])
    x_min = max(float(common["min"][0]), float(bbox.minpoint[0]))
    x_max = min(float(common["max"][0]), float(bbox.maxpoint[0]))
    z_min = max(float(common["min"][2]), float(bbox.minpoint[2]))
    z_max = min(float(common["max"][2]), float(bbox.maxpoint[2]))
    grid_step = 0.2
    x_axis = np.arange(x_min, x_max + grid_step * 0.5, grid_step)
    z_axis = np.arange(z_min, z_max + grid_step * 0.5, grid_step)
    mri_plane, _ = _sample_plane(mri, float(mri_y_center[1]), x_axis, z_axis)
    hist_plane, _ = _sample_plane(hist, float(hist_y_center[1]), x_axis, z_axis)
    mri_view = _display_uint8(mri_plane)
    hist_view = _display_uint8(hist_plane)
    selected_xz = (float(point["world_xyz_mm"][0]), float(point["world_xyz_mm"][2]))
    grid_pixel = world_to_grid_pixel(selected_xz, x_axis, z_axis)
    hist_marked = add_marker(hist_view, grid_pixel)

    st.markdown("### 2. Reference views at the documented section plane")
    st.caption("Yellow crosshair = selected section X/Z. The two source slices have separate sampled Y centres shown above. These are reference-space views, not anatomical validation.")
    mri_col, hist_col = st.columns(2)
    with mri_col:
        st.image(add_marker(mri_view, grid_pixel), caption="Donor MRI — visualization contrast only", use_container_width=True)
    with hist_col:
        st.image(hist_marked, caption="Reconstructed histology — 200 µm — visualization contrast only", use_container_width=True)

    neighbourhood_half = st.slider(
        "Reference neighbourhood half-width (mm)", 2.0, 20.0, 5.0, 1.0,
        key="registered-reference-neighbourhood",
    )
    local_x = np.arange(max(x_min, selected_xz[0] - neighbourhood_half), min(x_max, selected_xz[0] + neighbourhood_half) + grid_step * 0.5, grid_step)
    local_z = np.arange(max(z_min, selected_xz[1] - neighbourhood_half), min(z_max, selected_xz[1] + neighbourhood_half) + grid_step * 0.5, grid_step)
    if len(local_x) >= 2 and len(local_z) >= 2:
        local_mri, _ = _sample_plane(mri, float(mri_y_center[1]), local_x, local_z)
        local_hist, _ = _sample_plane(hist, float(hist_y_center[1]), local_x, local_z)
        local_pixel = world_to_grid_pixel(selected_xz, local_x, local_z)
        st.markdown("### Selected reference neighbourhood")
        st.caption(f"Both panels cover the same displayed physical field of view ({len(local_x) * grid_step:g} × {len(local_z) * grid_step:g} mm approximately). Enlarging the 200 µm volume does not reveal individual cells.")
        ncols = st.columns(2)
        with ncols[0]:
            st.image(add_marker(_display_uint8(local_mri), local_pixel), caption="MRI neighbourhood — visualization contrast only", use_container_width=True)
        with ncols[1]:
            st.image(add_marker(_display_uint8(local_hist), local_pixel), caption="200 µm histology neighbourhood — visualization contrast only", use_container_width=True)

    half_x = st.number_input("Detailed patch half-width X (mm)", 0.25, 2.0, 1.0, 0.25, key="registered-half-x")
    half_z = st.number_input("Detailed patch half-width Z (mm)", 0.25, 2.0, 1.0, 0.25, key="registered-half-z")
    requested = Bounds(
        max(float(bbox.minpoint[0]), selected_xz[0] - half_x), float(bbox.minpoint[1]), max(float(bbox.minpoint[2]), selected_xz[1] - half_z),
        min(float(bbox.maxpoint[0]), selected_xz[0] + half_x), float(bbox.maxpoint[1]), min(float(bbox.maxpoint[2]), selected_xz[1] + half_z),
    )
    requested.validate()
    rect = world_to_grid_pixel((requested.min_x, requested.min_z), x_axis, z_axis) + world_to_grid_pixel((requested.max_x, requested.max_z), x_axis, z_axis)
    hist_with_footprint = add_rect(hist_marked, (min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])))
    st.image(hist_with_footprint, caption="Reconstructed histology with registered detailed-patch footprint (cyan)", use_container_width=True)

    resolution = st.selectbox("Detailed request resolution (mm)", [0.01, 0.02, 0.1], index=0, key="registered-resolution")
    st.caption("The existing 10 MiB request budget is retained. The provider's actual returned resolution is authoritative; no coarser result is silently substituted.")
    if st.button("Fetch registered detailed patch", type="primary"):
        try:
            with st.spinner("Fetching bounded registered section patch…"):
                patch, patch_section, _ = fetch_crop(requested, resolution_mm=resolution, max_bytes=MAX_BYTES, section_id=SECTION_ID)
            st.session_state["registered_patch"] = (patch, patch_section, requested, resolution, point)
        except Exception as exc:
            st.error(f"Detailed registered-section fetch failed: {exc}")

    saved_patch = st.session_state.get("registered_patch")
    if saved_patch:
        patch, patch_section, patch_bounds, requested_resolution, patch_point = saved_patch
        patch_plane, patch_slice, patch_range = display_plane(patch)
        actual_zooms = [float(v) for v in patch.header.get_zooms()[:3]]
        patch_source = Image.fromarray(patch_plane.T)
        source_width, source_height = patch_source.size
        display_scale = min(1.0, 800.0 / source_width, 800.0 / source_height)
        patch_display = np.asarray(patch_source.resize((max(1, round(source_width * display_scale)), max(1, round(source_height * display_scale))), Image.Resampling.NEAREST))
        st.markdown("### 3. Registered detailed section")
        st.success("Bounded detailed patch retrieved from the registered provider.")
        st.write({
            "requested_bounds_mm": list(patch_bounds.__dict__.values()),
            "requested_resolution_mm": requested_resolution,
            "actual_returned_voxels": list(patch.shape),
            "actual_returned_voxel_size_mm": actual_zooms,
            "provider_selected_plane_index": patch_slice,
            "raw_range": patch_range,
            "estimated_uncompressed_bytes": int(np.asanyarray(patch.dataobj).nbytes),
        })
        st.image(patch_display, caption=f"Registered detailed section #3458 — actual returned resolution {actual_zooms} mm; visualization contrast only", use_container_width=True)
        st.info("Reference-space placement is documented, but anatomical status remains Not independently reviewed. The 200 µm volume and MRI are not treated as cellular-equivalent or perfectly registered.")

        metadata = {
            "status": "reference_space_placement_not_independently_reviewed",
            "section_id": SECTION_ID,
            "section_label": patch_section.name,
            "provider_url": SECTION_URL,
            "coordinate_space": "BigBrain microscopic template / documented registered-section reference space",
            "section_plane": {
                "min_y_mm": float(bbox.minpoint[1]), "max_y_mm": float(bbox.maxpoint[1]), "centre_y_mm": section_y_center,
                "provider_bbox_mm": {"min": list(map(float, bbox.minpoint)), "max": list(map(float, bbox.maxpoint))},
            },
            "selected_location": patch_point,
            "sampled_slice_centres": {
                "mri": mri_y_center.tolist(), "histology_200um": hist_y_center.tolist(),
                "detailed_patch_source": [float(v) for v in patch.affine[:3, 3]],
            },
            "sources": {
                "mri": str(MRI_SPEC.path), "histology_200um": str(HIST_SPEC.path), "detailed_provider": SECTION_URL,
                "siibra_version": "1.0.1-alpha.25",
            },
            "provider_metadata": {"info": info, "transform_nm": np.asarray(provider_volume.transform_nm).tolist(), "scale_key": scale.key, "scale_resolution_nm": np.asarray(scale.res_nm).tolist(), "scale_affine_mm": np.asarray(scale.affine).tolist(), "dataset_order": info.get("dataset_order")},
            "mapping": {
                "section_display_to_world": patch_point["mapping"],
                "provider_to_nifti": "siibra shift_ng_transfrom plus explicit zyx->xyz transpose in NeuroglancerScale.fetch",
                "world_to_200um": "inverse of local full8_200um_optbal.nii.gz affine; nearest source voxel for displayed slice",
                "interpolation": "none for exported detailed patch; MRI/200 µm views are independently sampled nearest-neighbour display planes",
                "flip_x": False, "flip_z": False, "transpose": True,
            },
            "patch": {
                "requested_bounds_mm": list(patch_bounds.__dict__.values()), "requested_resolution_mm": requested_resolution,
                "actual_shape_xyz": list(patch.shape), "actual_voxel_size_mm_xyz": actual_zooms,
                "actual_affine": np.asarray(patch.affine).tolist(), "display_plane_index_y": patch_slice,
                "raw_values_preserved": True,
                "exported_nifti_sha256": hashlib.sha256(image_bytes(patch)).hexdigest(),
                "source_array_sha256": raw_array_sha256(patch),
            },
            "anatomical_review": "Not independently reviewed; reference-space placement does not establish exact anatomical correspondence, especially with MRI.",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("registered_section_3458_raw.nii.gz", image_bytes(patch))
            archive.writestr("registered_section_3458_visualization.png", png_bytes(patch_display))
            archive.writestr("reconstructed_histology_200um_footprint.png", png_bytes(hist_with_footprint))
            archive.writestr("metadata.json", json.dumps(metadata, indent=2) + "\n")
            archive.writestr("README.txt", "Raw NIfTI values are preserved. PNG files are visualization-only. Placement is reference-space only and not independently reviewed.\n")
        st.download_button("Download MRI–200 µm–registered-section package", bundle.getvalue(), "registered_section_3458_demo.zip", "application/zip")
