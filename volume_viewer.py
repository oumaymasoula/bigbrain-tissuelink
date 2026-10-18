"""Experimental linked viewer for the official MRI and native histology volumes only."""
from __future__ import annotations

import json
import io
import zipfile
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import nibabel as nib
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw

from volume_alignment import (
    VolumeSpec,
    _display_uint8,
    _sample_plane,
    common_world_bounds,
    display_pixel_to_world,
    load_volume,
    nearest_voxel_for_world,
    native_neighbourhood_crop,
    volume_metadata,
)
from bigbrain_cutout import Bounds, MAX_BYTES, display_plane, fetch_crop
from registered_section_demo import (
    OVERVIEW_MAX_BYTES,
    OVERVIEW_RESOLUTION_MM,
    SECTION_ID,
    SECTION_URL,
    map_section_pixel_to_world,
    registered_context,
    registered_overview,
    world_to_grid_pixel,
    add_rect,
)


ROOT = Path(__file__).resolve().parent
MRI = VolumeSpec("donor MRI", ROOT / "outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz")
HIST = VolumeSpec("native histology", ROOT / "outputs/spatial_feasibility/full8_200um_optbal.nii.gz")
REGISTERED_NAVIGATION_TARGETS = ("volume_viewer.py", "pages/1_Validation.py")


def validate_navigation_targets(root: Path = ROOT) -> None:
    """Fail early if a sidebar target is not a registered local page."""
    missing = [target for target in REGISTERED_NAVIGATION_TARGETS if not (root / target).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing registered Streamlit page(s): {missing}")


validate_navigation_targets()

st.set_page_config(page_title="BigBrain TissueLink", layout="wide")
st.title("BigBrain TissueLink")
st.caption("MRI–Histology Explorer")
st.warning("Reference data from one donor; anatomical alignment is imperfect.")
with st.expander("Limitations and provenance", expanded=False):
    st.write(
        "This is reference-anatomy inspection, not patient MRI, arbitrary participant MRI, registration, "
        "or a clinical tool. Matching world coordinates do not guarantee matching anatomy. The detailed "
        "siibra section is linked by documented reference-space geometry only and remains Not independently reviewed."
    )


@st.cache_resource
def get_images():
    return load_volume(MRI), load_volume(HIST)


@st.cache_data
def plane_views(world_y: float, x_min: float, x_max: float, z_min: float, z_max: float, step: float, low_percentile: float, high_percentile: float):
    x_axis = np.arange(x_min, x_max + step * 0.5, step)
    z_axis = np.arange(z_min, z_max + step * 0.5, step)
    mri, hist = get_images()
    mri_plane, _ = _sample_plane(mri, world_y, x_axis, z_axis)
    hist_plane, _ = _sample_plane(hist, world_y, x_axis, z_axis)
    return _display_uint8(mri_plane, low_percentile, high_percentile), _display_uint8(hist_plane, low_percentile, high_percentile), x_axis, z_axis


def overlay_view(mri_view: np.ndarray, hist_view: np.ndarray, opacity: float) -> np.ndarray:
    """Blend the display-only views; raw volume data are never changed."""
    mri_rgb = np.repeat(mri_view[..., None], 3, axis=2).astype(np.float32)
    hist_rgb = np.repeat(hist_view[..., None], 3, axis=2).astype(np.float32)
    # Red MRI + cyan histology makes disagreement visible without implying a label.
    mri_rgb[..., 1:] *= 0.25
    hist_rgb[..., 0] *= 0.25
    return np.clip((1.0 - opacity) * mri_rgb + opacity * hist_rgb, 0, 255).astype(np.uint8)


def _display_grayscale(view: np.ndarray) -> np.ndarray:
    """Convert display input to 2-D only; never mutate or resample source data."""
    array = np.asarray(view)
    if array.ndim == 3 and 1 in array.shape:
        array = np.squeeze(array)
    if array.ndim != 2:
        raise ValueError(f"display overlay requires a 2-D grayscale array; got shape {array.shape}")
    return array


def rgb_with_crosshair(view: np.ndarray, u: int, v: int, colour=(255, 255, 0)) -> np.ndarray:
    gray = _display_grayscale(view)
    result = np.repeat(gray[..., None], 3, axis=2).astype(np.uint8)
    if 0 <= u < result.shape[1]:
        result[:, u] = colour
    if 0 <= v < result.shape[0]:
        result[v, :] = colour
    return result


def compact_display(view: np.ndarray, max_width: int = 420) -> tuple[np.ndarray, float]:
    """Make navigation imagery compact while returning its pixel scale."""
    image = Image.fromarray(_display_grayscale(view) if view.ndim != 3 else view)
    if image.width <= max_width:
        return np.asarray(image), 1.0
    scale = max_width / image.width
    return np.asarray(image.resize((max_width, max(1, round(image.height * scale))), Image.Resampling.NEAREST)), scale


def checkerboard_view(mri_view: np.ndarray, hist_view: np.ndarray, tile: int = 32) -> np.ndarray:
    result = np.empty((*mri_view.shape, 3), dtype=np.uint8)
    rows, cols = np.indices(mri_view.shape)
    choose_mri = ((rows // tile) + (cols // tile)) % 2 == 0
    mri_rgb = np.repeat(mri_view[..., None], 3, axis=2)
    hist_rgb = np.repeat(hist_view[..., None], 3, axis=2)
    result[choose_mri] = mri_rgb[choose_mri]
    result[~choose_mri] = hist_rgb[~choose_mri]
    return result


def add_scale_bar(view: np.ndarray, step: float, physical_mm: float = 10.0) -> np.ndarray:
    result = Image.fromarray(view).convert("RGB")
    draw = ImageDraw.Draw(result)
    pixels = max(1, min(view.shape[1] - 24, int(round(physical_mm / step))))
    x0, y0 = 12, view.shape[0] - 18
    draw.line((x0, y0, x0 + pixels, y0), fill=(255, 255, 0), width=3)
    draw.text((x0, y0 - 16), f"{pixels * step:.1f} mm", fill=(255, 255, 0))
    return np.asarray(result)


def add_orientation_labels(view: np.ndarray, title: str) -> np.ndarray:
    result = Image.fromarray(view).convert("RGB")
    draw = ImageDraw.Draw(result)
    draw.rectangle((0, 0, result.width - 1, 22), fill=(0, 0, 0))
    draw.text((8, 5), title, fill=(255, 255, 255))
    # Displayed plane is world X/Z. In RAS, X is left/right and Z is
    # inferior/superior; A/P is the shared out-of-plane world-Y slice.
    draw.text((result.width - 24, 26), "R", fill=(255, 255, 0))
    draw.text((8, 26), "L", fill=(255, 255, 0))
    draw.text((result.width - 24, result.height - 35), "S", fill=(255, 255, 0))
    draw.text((8, result.height - 35), "I", fill=(255, 255, 0))
    return np.asarray(result)


def add_mri_voxel_box(view: np.ndarray, u: int, v: int, step: float, voxel_size_mm: list[float]) -> np.ndarray:
    """Mark the MRI sampling voxel; this is not registration uncertainty."""
    result = Image.fromarray(view).convert("RGB")
    draw = ImageDraw.Draw(result)
    half_x = max(1, int(round(voxel_size_mm[0] / (2.0 * step))))
    half_z = max(1, int(round(voxel_size_mm[2] / (2.0 * step))))
    draw.rectangle((u - half_x, v - half_z, u + half_x, v + half_z), outline=(255, 0, 255), width=2)
    return np.asarray(result)


def neighbourhood(view: np.ndarray, u: int, v: int, half_width_mm: float, step: float):
    half = max(1, int(round(half_width_mm / step)))
    x0, x1 = max(0, u - half), min(view.shape[1], u + half + 1)
    z0, z1 = max(0, v - half), min(view.shape[0], v + half + 1)
    return view[z0:z1, x0:x1], {"pixel_bounds_uv": [x0, z0, x1 - 1, z1 - 1], "coverage_mm": [(x1 - x0 - 1) * step, (z1 - z0 - 1) * step]}


def png_bytes(view: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(view).save(buffer, format="PNG")
    return buffer.getvalue()


def nifti_bytes(image) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as temporary:
        nib.save(image, temporary.name)
        temporary.seek(0)
        return temporary.read()


@st.cache_data
def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def location_report_bytes(saved: dict) -> bytes:
    report = io.BytesIO()
    with zipfile.ZipFile(report, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("location_metadata.json", json.dumps(saved["metadata"], indent=2) + "\n")
        archive.writestr("reference_mri_neighbourhood.png", saved["mri_neighbourhood_png"])
        archive.writestr("reconstructed_histology_200um_neighbourhood.png", saved["histology_neighbourhood_png"])
        archive.writestr("reference_mri_overview_visualization.png", saved["mri_overview_png"])
        archive.writestr("reconstructed_histology_overview_visualization.png", saved["histology_overview_png"])
        archive.writestr("scientific_reference_mri_neighbourhood.nii.gz", saved["mri_nifti"])
        archive.writestr("scientific_reconstructed_histology_neighbourhood.nii.gz", saved["histology_nifti"])
        archive.writestr("README.txt", "PNG files are visual reports only. NIfTI files are native-grid scientific crops; see location_metadata.json.\n")
    return report.getvalue()


def registered_patch_report_bytes(saved: dict) -> bytes:
    """Package one raw #3458 patch and its reference-space provenance."""
    report = io.BytesIO()
    with zipfile.ZipFile(report, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("registered_section_3458_raw.nii.gz", saved["raw_nifti"])
        archive.writestr("registered_section_3458_visualization.png", saved["patch_png"])
        archive.writestr("reconstructed_histology_200um_footprint.png", saved["footprint_png"])
        archive.writestr("metadata.json", json.dumps(saved["metadata"], indent=2) + "\n")
        archive.writestr("README.txt", "Raw NIfTI values are preserved. PNG files are visualization-only. Reference-space placement is not independently reviewed and is not a claim of exact MRI correspondence.\n")
    return report.getvalue()


if not MRI.path.exists() or not HIST.path.exists():
    st.error("The two local feasibility volumes are missing. Run the feasibility download first.")
    st.stop()

mri, hist = get_images()
common = common_world_bounds([mri, hist])

with st.expander("Advanced · source and technical metadata", expanded=False):
    st.caption("Sources: official donor MRI `3D_MRI/nii/mri_to_blk_aligned.nii.gz` and native histological-space `full8_200um_optbal.nii.gz`.")
    st.info("This viewer reports reference-space inspection, not a whole-brain accuracy score.")
    meta_col1, meta_col2 = st.columns(2)
    with meta_col1:
        st.write(f"MRI: orientation {volume_metadata(mri)['orientation']}; voxel size {volume_metadata(mri)['voxel_size_mm_xyz']} mm; shape {volume_metadata(mri)['shape_xyz']}")
    with meta_col2:
        st.write(f"Histology: orientation {volume_metadata(hist)['orientation']}; voxel size {volume_metadata(hist)['voxel_size_mm_xyz']} mm; shape {volume_metadata(hist)['shape_xyz']}")

if "location_x_input" not in st.session_state:
    st.session_state.location_x_input = float((common["min"][0] + common["max"][0]) / 2)
if "location_z_input" not in st.session_state:
    st.session_state.location_z_input = float((common["min"][2] + common["max"][2]) / 2)
if "saved_locations" not in st.session_state:
    st.session_state.saved_locations = {}
if "last_location_click" not in st.session_state:
    st.session_state.last_location_click = None
if "pending_location" in st.session_state:
    pending_location = st.session_state.pop("pending_location")
    st.session_state.location_x_input = pending_location[0]
    st.session_state.location_z_input = pending_location[1]
if "pending_registered_reference" in st.session_state:
    pending_reference = st.session_state.pop("pending_registered_reference")
    st.session_state.location_x_input = pending_reference[0]
    st.session_state.location_z_input = pending_reference[1]
    st.session_state.world_y_slice = pending_reference[2]

st.session_state.setdefault("world_y_slice", -25.7922)
if st.button("Navigate to section #3458", key="navigate-section-3458"):
    try:
        _, section_bbox_for_navigation, *_ = registered_context()
        section_plane_y = float((section_bbox_for_navigation.minpoint[1] + section_bbox_for_navigation.maxpoint[1]) / 2.0)
        st.session_state.world_y_slice = section_plane_y
        st.session_state.registered_navigation_active = True
        st.rerun()
    except Exception as exc:
        st.error(f"Could not navigate to registered section #3458: {exc}")
world_y = st.slider("Shared world Y slice (mm)", float(common["min"][1]), float(common["max"][1]), step=0.2, key="world_y_slice")
if st.session_state.get("registered_navigation_active"):
    st.caption(f"Navigation target active: registered section #3458 plane at exact Y≈{world_y:.4f} mm; MRI and 200 µm views use their separate nearest sampled voxel centres.")
step = st.select_slider("Inspection grid spacing (mm)", options=[0.2, 0.4, 0.8], value=0.2, format_func=lambda value: f"{value:.1f} mm/pixel")
contrast_low, contrast_high = st.slider("Display contrast percentiles (visualization only)", 0.0, 100.0, (1.0, 99.0), 0.5)
if contrast_high <= contrast_low:
    st.error("The upper contrast percentile must be greater than the lower percentile.")
    st.stop()

x_world = st.number_input("Crosshair world X (mm)", min_value=float(common["min"][0]), max_value=float(common["max"][0]), step=step, key="location_x_input")
z_world = st.number_input("Crosshair world Z (mm)", min_value=float(common["min"][2]), max_value=float(common["max"][2]), step=step, key="location_z_input")

mri_view, hist_view, x_axis, z_axis = plane_views(world_y, common["min"][0], common["max"][0], common["min"][2], common["max"][2], step, contrast_low, contrast_high)
x_pixel = int(np.clip(round((x_world - x_axis[0]) / step), 0, len(x_axis) - 1))
z_pixel = int(np.clip(round((z_world - z_axis[0]) / step), 0, len(z_axis) - 1))
mri_display = add_mri_voxel_box(
    rgb_with_crosshair(mri_view, x_pixel, z_pixel), x_pixel, z_pixel, step,
    volume_metadata(mri)["voxel_size_mm_xyz"],
)
mri_display = add_orientation_labels(add_scale_bar(mri_display, step), "Reference MRI · visual report")
hist_display = add_orientation_labels(add_scale_bar(rgb_with_crosshair(hist_view, x_pixel, z_pixel), step), "Histology 200 µm · visual report")
mri_navigation, mri_display_scale = compact_display(mri_display)
hist_navigation, hist_display_scale = compact_display(hist_display)

st.subheader("1. Find a location")
st.caption("Click either compact overview to move the shared crosshair. Both panels show the same physical X/Z field of view.")
col1, col2 = st.columns(2)
with col1:
    st.markdown("### MRI overview — 0.444 mm")
    st.caption("Compact navigation · display contrast only · RAS X/Z")
    mri_click = streamlit_image_coordinates(mri_navigation, width=int(mri_navigation.shape[1]), key="location_picker_mri")
with col2:
    st.markdown("### Histology overview — 200 µm; cells not resolved")
    st.caption("Compact navigation · display contrast only · RAS X/Z")
    hist_click = streamlit_image_coordinates(hist_navigation, width=int(hist_navigation.shape[1]), key="location_picker_histology")
for modality, click in (("mri", mri_click), ("histology", hist_click)):
    if click:
        scale = mri_display_scale if modality == "mri" else hist_display_scale
        [u, v], world = display_pixel_to_world(
            x_axis, z_axis, world_y,
            (click["x"] / scale, click["y"] / scale),
        )
        click_key = [modality, u, v]
        if click_key != st.session_state.last_location_click:
            st.session_state.last_location_click = click_key
            st.session_state.pending_location = [world[0], world[2]]
            st.rerun()
st.caption(
    f"Physical display contract: horizontal axis = world X ({x_axis[0]:.2f} to {x_axis[-1]:.2f} mm), "
    f"vertical axis = world Z ({z_axis[0]:.2f} to {z_axis[-1]:.2f} mm), {step:.2f} mm per display pixel; "
    "no display flip or axis swap is applied; horizontal L/R and vertical I/S follow RAS; "
    "A/P is the shared out-of-plane world-Y slice; scale bars are visualization-only."
)
st.info(
    "The magenta outline is the containing MRI voxel (sampling footprint only). "
    "A documented registration-uncertainty radius is unavailable, so no uncertainty circle is drawn. "
    "The displayed 200 µm reconstruction does not provide cellular detail."
)

st.subheader("2. Inspect the linked location")
st.info("The enlarged views cover the same physical neighbourhood. Enlarging 200 µm histology does not reveal individual cells.")
half_width_mm = st.slider("Neighbourhood half-width (same physical coverage)", 1.0, 20.0, 5.0, 0.5)
half = max(1, int(round(half_width_mm / step)))
x0, x1 = max(0, x_pixel - half), min(mri_view.shape[1], x_pixel + half + 1)
z0, z1 = max(0, z_pixel - half), min(mri_view.shape[0], z_pixel + half + 1)
mri_neighbour = mri_view[z0:z1, x0:x1]
hist_neighbour = hist_view[z0:z1, x0:x1]
coverage_mm = [(x1 - x0 - 1) * step, (z1 - z0 - 1) * step]
st.caption(f"Selected world point: X={x_world:.2f}, Y={world_y:.2f}, Z={z_world:.2f} mm · neighbourhood coverage: {coverage_mm[0]:.2f} × {coverage_mm[1]:.2f} mm")
neigh1, neigh2 = st.columns(2)
with neigh1:
    st.markdown("### Reference MRI neighbourhood")
    st.image(rgb_with_crosshair(mri_neighbour, x_pixel - x0, z_pixel - z0), use_container_width=True)
with neigh2:
    st.markdown("### Reconstructed histology — 200 µm neighbourhood")
    st.image(rgb_with_crosshair(hist_neighbour, x_pixel - x0, z_pixel - z0), use_container_width=True)

st.subheader("3. Select a registered detailed section")
st.caption(
    "This optional stage uses the documented reference-space placement for registered section #3458. "
    "The MRI and 200 µm views are sampled at the displayed shared location, while the detailed-section "
    "X/Z selection is made independently on the registered overview. No Labelme files or annotation uploads are required."
)
explore_registered = st.checkbox("Explore available registered section #3458", value=True, key="explore-registered-3458")
if explore_registered:
    try:
        section, section_bbox, provider, provider_volume, provider_info, provider_scale = registered_context()
        section_bounds_values = tuple(float(value) for value in (*section_bbox.minpoint, *section_bbox.maxpoint))
        section_y = float((section_bbox.minpoint[1] + section_bbox.maxpoint[1]) / 2.0)
        section_x = float((section_bbox.minpoint[0] + section_bbox.maxpoint[0]) / 2.0)
        section_z = float((section_bbox.minpoint[2] + section_bbox.maxpoint[2]) / 2.0)
        mri_section_voxel, mri_section_center = nearest_voxel_for_world(mri, np.array([section_x, section_y, section_z]))
        hist_section_voxel, hist_section_center = nearest_voxel_for_world(hist, np.array([section_x, section_y, section_z]))
        st.write({
            "section": "#3458",
            "section_id": SECTION_ID,
            "provider": SECTION_URL,
            "documented_section_plane_centre_y_mm": section_y,
            "MRI_sampled_slice_centre_mm": mri_section_center.tolist(),
            "histology_200um_sampled_slice_centre_mm": hist_section_center.tolist(),
            "anatomical_status": "Not independently reviewed",
        })
        st.warning(
            "Reference-space placement does not establish exact anatomical correspondence, especially with MRI. "
            "The 200 µm volume is not cellular-equivalent. No uncertainty circle or new registration is applied."
        )

        section_image, section_plane, section_slice, section_range = registered_overview(section_bounds_values)
        section_source = Image.fromarray(section_plane.T)
        section_display_width = min(900, section_source.width)
        section_display_height = max(1, round(section_source.height * section_display_width / section_source.width))
        section_display = np.asarray(section_source.resize((section_display_width, section_display_height), Image.Resampling.NEAREST))
        st.markdown("#### Available section: #3458")
        st.caption(
            f"#3458 · requested overview {OVERVIEW_RESOLUTION_MM:g} mm · actual voxel size "
            f"{[float(value) for value in section_image.header.get_zooms()[:3]]} mm · "
            f"provider plane index y={section_slice} · raw range {section_range} · budget {OVERVIEW_MAX_BYTES:,} bytes."
        )
        section_click = streamlit_image_coordinates(section_display, width=section_display_width, key="volume-viewer-section-3458")
        if section_click:
            mapped_section_point = map_section_pixel_to_world(
                section_image, (section_click["x"], section_click["y"]),
                (section_display_width, section_display_height), section_y,
            )
            st.session_state["volume_viewer_section_point"] = mapped_section_point
            # Apply the documented section X/Z point to the linked reference
            # views on the next rerun. Y is the exact section plane; the
            # source-specific sampled centres remain separately reported.
            st.session_state["pending_registered_reference"] = (
                float(mapped_section_point["world_xyz_mm"][0]),
                float(mapped_section_point["world_xyz_mm"][2]),
                section_y,
            )
            st.session_state["registered_navigation_active"] = True
            st.rerun()
        section_point = st.session_state.get("volume_viewer_section_point")
        if section_point is None:
            section_point = map_section_pixel_to_world(
                section_image, (section_display_width / 2, section_display_height / 2),
                (section_display_width, section_display_height), section_y,
            )
            st.info("The centre marker is only a navigation default. Click the section overview to choose the detailed-patch X/Z location.")
        selected_section_world = [float(value) for value in section_point["world_xyz_mm"]]
        st.write({"selected_section_world_xyz_mm": selected_section_world, "mapping": section_point["mapping"]})

        overview_marked = np.repeat(section_display[..., None], 3, axis=2).astype(np.uint8)
        section_pixel = (int(round(section_point["display_pixel_uv"][0] * section_display_width / section_display_width)), int(round(section_point["display_pixel_uv"][1] * section_display_height / section_display_height)))
        overview_marked = rgb_with_crosshair(overview_marked, section_pixel[0], section_pixel[1])
        st.image(overview_marked, caption="Registered section #3458 — visualization contrast only; yellow crosshair is the selected X/Z location", use_container_width=True)

        registered_half_x = st.number_input("Detailed patch half-width X (mm)", 0.25, 2.0, 1.0, 0.25, key="volume-viewer-registered-half-x")
        registered_half_z = st.number_input("Detailed patch half-width Z (mm)", 0.25, 2.0, 1.0, 0.25, key="volume-viewer-registered-half-z")
        registered_resolution = st.selectbox("Detailed patch requested resolution (mm)", [0.01, 0.02, 0.1], index=0, key="volume-viewer-registered-resolution")
        selected_x, selected_z = selected_section_world[0], selected_section_world[2]
        requested_section_bounds = Bounds(
            max(float(section_bbox.minpoint[0]), selected_x - registered_half_x), float(section_bbox.minpoint[1]), max(float(section_bbox.minpoint[2]), selected_z - registered_half_z),
            min(float(section_bbox.maxpoint[0]), selected_x + registered_half_x), float(section_bbox.maxpoint[1]), min(float(section_bbox.maxpoint[2]), selected_z + registered_half_z),
        )
        requested_section_bounds.validate()
        footprint_x0, footprint_z0 = world_to_grid_pixel((requested_section_bounds.min_x, requested_section_bounds.min_z), x_axis, z_axis)
        footprint_x1, footprint_z1 = world_to_grid_pixel((requested_section_bounds.max_x, requested_section_bounds.max_z), x_axis, z_axis)
        hist_footprint = add_rect(
            rgb_with_crosshair(hist_view, x_pixel, z_pixel),
            (min(footprint_x0, footprint_x1), min(footprint_z0, footprint_z1), max(footprint_x0, footprint_x1), max(footprint_z0, footprint_z1)),
        )
        hist_footprint = add_scale_bar(hist_footprint, step)
        st.image(hist_footprint, caption="Histology overview — 200 µm; cells not resolved · detailed patch footprint in cyan", width=420)
        st.caption("The footprint is placed by provider geometry in shared reference coordinates; it is not a claim of exact tissue correspondence.")

        registered_signature = (tuple(round(value, 6) for value in selected_section_world), float(registered_half_x), float(registered_half_z), float(registered_resolution))
        if st.session_state.get("volume_viewer_registered_signature") != registered_signature:
            st.session_state.pop("volume_viewer_registered_patch", None)
        if st.button("Fetch selected registered detailed patch", type="primary", key="volume-viewer-fetch-registered"):
            try:
                with st.spinner("Fetching bounded registered section #3458 patch…"):
                    detailed_patch, detailed_section, _ = fetch_crop(
                        requested_section_bounds, resolution_mm=registered_resolution,
                        max_bytes=MAX_BYTES, section_id=SECTION_ID,
                    )
                st.session_state["volume_viewer_registered_signature"] = registered_signature
                st.session_state["volume_viewer_registered_patch"] = (detailed_patch, detailed_section, requested_section_bounds, section_point)
            except Exception as exc:
                st.error(f"Registered section #3458 fetch failed: {exc}")

        registered_patch_state = st.session_state.get("volume_viewer_registered_patch")
        if registered_patch_state and st.session_state.get("volume_viewer_registered_signature") == registered_signature:
            detailed_patch, detailed_section, actual_bounds, selected_point = registered_patch_state
            detailed_plane, detailed_slice, detailed_range = display_plane(detailed_patch)
            patch_source = Image.fromarray(detailed_plane.T)
            detailed_zooms = [float(value) for value in detailed_patch.header.get_zooms()[:3]]
            detail_zoom = st.slider("Detailed patch display enlargement (visual only)", 1.0, 4.0, 2.0, 0.25, key="volume-viewer-detail-zoom")
            patch_display = np.asarray(patch_source.resize((max(1, round(patch_source.width * detail_zoom)), max(1, round(patch_source.height * detail_zoom))), Image.Resampling.NEAREST))
            patch_display = add_orientation_labels(add_scale_bar(patch_display, detailed_zooms[0]), "Registered detailed section #3458 · raw values")
            detailed_nifti = nifti_bytes(detailed_patch)
            detailed_metadata = {
                "status": "reference_space_placement_not_independently_reviewed",
                "section_label": "#3458",
                "section_id": SECTION_ID,
                "provider_url": SECTION_URL,
                "coordinate_space": "BigBrain microscopic template / documented registered-section reference space",
                "section_plane": {
                    "centre_y_mm": section_y,
                    "min_y_mm": float(section_bbox.minpoint[1]),
                    "max_y_mm": float(section_bbox.maxpoint[1]),
                },
                "selected_location": selected_point,
                "sampled_voxel_centres": {
                    "mri": mri_section_center.tolist(),
                    "histology_200um": hist_section_center.tolist(),
                    "detailed_section_first_voxel": np.asarray(detailed_patch.affine[:3, 3], dtype=float).tolist(),
                },
                "requested_bounds_mm": list(actual_bounds.__dict__.values()),
                "requested_resolution_mm": float(registered_resolution),
                "actual_shape_xyz": [int(value) for value in detailed_patch.shape],
                "actual_voxel_size_mm_xyz": detailed_zooms,
                "actual_affine": np.asarray(detailed_patch.affine).tolist(),
                "provider_metadata": {
                    "info": provider_info,
                    "transform_nm": np.asarray(provider_volume.transform_nm).tolist(),
                    "scale_key": provider_scale.key,
                    "scale_resolution_nm": np.asarray(provider_scale.res_nm).tolist(),
                    "dataset_order": provider_info.get("dataset_order"),
                },
                "mapping": {
                    "section_display": selected_point["mapping"],
                    "provider_to_nifti": "siibra NeuroglancerScale.fetch applies provider zyx-to-NIfTI xyz reordering",
                    "overview_to_reference": "provider affine; no display flip or extra registration",
                    "interpolation": "none for detailed export; display planes are independently sampled",
                    "transpose": True,
                    "flip_x": False,
                    "flip_z": False,
                },
                "raw_values_preserved": True,
                "source_array_sha256": hashlib.sha256(np.asanyarray(detailed_patch.dataobj).tobytes(order="C")).hexdigest(),
                "exported_nifti_sha256": sha256_bytes(detailed_nifti),
                "anatomical_review": "Not independently reviewed; reference-space placement does not establish exact MRI correspondence.",
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            st.markdown("## 4. Detailed tissue patch")
            st.success("Bounded real-data patch retrieved from the registered #3458 provider.")
            st.markdown(
                f"**Actual returned pixel size: {detailed_patch.shape[2]} × {detailed_patch.shape[0]} pixels (X × Z plane)**  "
                f"\n**Native voxel size: {detailed_zooms[0]:g} × {detailed_zooms[2]:g} mm**"
            )
            st.caption("Display enlargement changes only the visualization size. It does not fetch finer data. The exported NIfTI remains at the provider's actual native resolution.")
            st.write({
                "requested_bounds_mm": list(actual_bounds.__dict__.values()),
                "requested_resolution_mm": float(registered_resolution),
                "actual_shape_xyz": [int(value) for value in detailed_patch.shape],
                "actual_voxel_size_mm_xyz": detailed_zooms,
                "provider_plane_index_y": detailed_slice,
                "raw_range": detailed_range,
                "estimated_uncompressed_bytes": int(np.asanyarray(detailed_patch.dataobj).nbytes),
            })
            st.image(patch_display, caption=f"Registered detailed section #3458 — actual returned resolution {detailed_zooms} mm; visualization contrast only", use_container_width=True)
            registered_package = {"raw_nifti": detailed_nifti, "patch_png": png_bytes(patch_display), "footprint_png": png_bytes(hist_footprint), "metadata": detailed_metadata}
            st.download_button("Download registered MRI → section patch package", registered_patch_report_bytes(registered_package), "registered_section_3458_patch.zip", "application/zip", key="volume-viewer-download-registered")
        else:
            st.info("Select an available section and fetch a detailed tissue patch.")
    except Exception as exc:
        st.error(f"Could not load the registered #3458 metadata or overview: {exc}")

with st.expander("Optional comparison views", expanded=False):
    overlay_opacity = st.slider("Histology opacity in red/cyan overlay", 0.0, 1.0, 0.5, 0.05)
    st.caption("Red = Reference MRI. Cyan = reconstructed histology. These are display colours, not tissue labels.")
    tab1, tab2 = st.tabs(["Opacity overlay", "Checkerboard"])
    with tab1:
        st.image(overlay_view(mri_view, hist_view, overlay_opacity), use_container_width=True)
    with tab2:
        st.image(checkerboard_view(mri_view, hist_view), use_container_width=True)

with st.expander("Advanced diagnostics", expanded=False):
    st.subheader("Displayed voxel centres")
    for label, image in (("MRI", mri), ("native histology", hist)):
        voxel, center = nearest_voxel_for_world(image, np.array([x_world, world_y, z_world]))
        st.write(f"{label}: voxel index xyz={voxel.tolist()}, displayed voxel centre mm={center.tolist()}")
    st.write({"MRI_affine": np.asarray(mri.affine).tolist(), "histology_affine": np.asarray(hist.affine).tolist()})

st.subheader("Save or reopen a location")
location_name = st.text_input("Location name", value="review_location")
observation = st.text_area("Observation (not an anatomical label)", value="")
mri_voxel, mri_center = nearest_voxel_for_world(mri, np.array([x_world, world_y, z_world]))
hist_voxel, hist_center = nearest_voxel_for_world(hist, np.array([x_world, world_y, z_world]))
mri_crop, mri_crop_info = native_neighbourhood_crop(mri, np.array([x_world, world_y, z_world]), half_width_mm)
hist_crop, hist_crop_info = native_neighbourhood_crop(hist, np.array([x_world, world_y, z_world]), half_width_mm)
mri_nifti = nifti_bytes(mri_crop)
histology_nifti = nifti_bytes(hist_crop)
location_metadata = {
    "name": location_name.strip() or "unnamed_location",
    "observation": observation,
    "status": "shared_coordinate_location",
    "coordinate_space": "official final histological processing-space world coordinates",
    "requested_world_xyz_mm": [float(x_world), float(world_y), float(z_world)],
    "displayed_voxel_centres": {"mri": mri_center.tolist(), "histology": hist_center.tolist()},
    "raw_voxel_indices_xyz": {"mri": mri_voxel.tolist(), "histology": hist_voxel.tolist()},
    "neighbourhood": {"coverage_mm": coverage_mm, "pixel_bounds_uv": [x0, z0, x1 - 1, z1 - 1]},
    "visual_report": {
        "status": "visualization_only",
        "files": ["reference_mri_neighbourhood.png", "reconstructed_histology_200um_neighbourhood.png", "reference_mri_overview_visualization.png", "reconstructed_histology_overview_visualization.png"],
        "contrast_adjusted": True,
        "orientation_labels": "L/R horizontal and I/S vertical in RAS; A/P is the shared out-of-plane Y slice",
        "mri_voxel_box": "magenta outline is MRI sampling footprint, not registration uncertainty",
        "scale_bar": "10 mm where it fits",
        "selection_marked": True,
    },
    "scientific_data_export": {
        "status": "native_grid_crop",
        "files": ["scientific_reference_mri_neighbourhood.nii.gz", "scientific_reconstructed_histology_neighbourhood.nii.gz"],
        "interpolation": "none",
        "values": "direct source data-proxy values; no display contrast, squeeze, or resampling",
        "mri": mri_crop_info,
        "histology": hist_crop_info,
        "source_sha256": {"mri": sha256_file(str(MRI.path)), "histology": sha256_file(str(HIST.path))},
        "export_sha256": {"mri": sha256_bytes(mri_nifti), "histology": sha256_bytes(histology_nifti)},
    },
    "grid_step_mm": float(step),
    "display_contract": {"horizontal": "world X", "vertical": "world Z", "orientation": "RAS", "no_flip": True, "no_axis_swap": True},
    "sources": {"mri": str(MRI.path), "histology": str(HIST.path)},
    "visual_contrast_percentiles": [float(contrast_low), float(contrast_high)],
    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    "warning": "Shared coordinates are not a validated anatomical correspondence.",
}
if st.button("Save location", type="primary"):
    st.session_state.saved_locations[location_metadata["name"]] = {
        "metadata": location_metadata,
        "mri_neighbourhood_png": png_bytes(mri_neighbour),
        "histology_neighbourhood_png": png_bytes(hist_neighbour),
        "mri_overview_png": png_bytes(mri_display),
        "histology_overview_png": png_bytes(hist_display),
        "mri_nifti": mri_nifti,
        "histology_nifti": histology_nifti,
    }
    output_dir = ROOT / "outputs/spatial_feasibility/location_review"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{location_metadata['name']}_location_report.zip").write_bytes(location_report_bytes(st.session_state.saved_locations[location_metadata["name"]]))
    st.success(f"Saved `{location_metadata['name']}`. This is a shared-coordinate inspection location, not an independently matched landmark pair.")
if st.session_state.saved_locations:
    saved_name = st.selectbox("Saved locations", list(st.session_state.saved_locations))
    saved = st.session_state.saved_locations[saved_name]
    if st.button("Reopen selected location"):
        point = saved["metadata"]["requested_world_xyz_mm"]
        st.session_state.pending_location = [point[0], point[2]]
        st.session_state.last_location_click = None
        st.rerun()
    with st.expander("Saved metadata JSON", expanded=False):
        st.json(saved["metadata"])
    st.download_button("Export location report (ZIP)", data=location_report_bytes(saved), file_name=f"{saved_name}_location_report.zip", mime="application/zip")

st.info("Independent corresponding-point checks, arrow discrepancies, and the 8–10-landmark validation table are on the separate Validation page. This main page answers one question: what is at this shared reference-space location?")
