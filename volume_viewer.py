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
from bigbrain_cutout import Bounds, MAX_BYTES, display_plane, fetch_crop, map_source_bounds_to_preview_rect
from bigbrain_cutout import section_catalogue
from registered_section_demo import (
    OVERVIEW_MAX_BYTES,
    OVERVIEW_RESOLUTION_MM,
    map_section_pixel_to_world,
    map_section_world_to_pixel,
    registered_context,
    registered_overview,
    section_display_array,
    world_to_grid_pixel,
    add_rect,
)
from display_utils import _display_grayscale, has_intensity_variation, rgb_with_crosshair
from patch_collection import COLLECTION_MAX_BYTES, add_entry, annotation_plane_from_image, bind_unmarked_png_metadata, collection_bytes, collection_visual_report_filename, collection_visual_report_html, collection_zip_bytes, manual_patch_region_context, patch_id_for
from labelme_import import build_import_package, validate_labelme_annotation
from labelme_coco import build_coco_package
from collection_replay import replay_collection, reopen_collection
from collection_ui import render_collection_review, render_start_new_collection
from section_status import filter_section_status_rows, section_status_rows
from patch_sampling import (
    MAX_ESTIMATED_BYTES,
    MAX_PATCH_COUNT,
    MAX_REQUEST_COUNT,
    PatchSizeXZ,
    RectangleXZ,
    estimated_bytes_per_patch,
    footprint_bounds,
    generate_regular_grid,
    generate_seeded_random,
    plan_metadata,
)
from patch_statistics import compute_patch_statistics
from selection_sync import invalidate_current_selection, selection_sync_report
from region_navigation import (
    VERIFIED_SECTION_INTERSECTIONS,
    central_nonzero_display_pixel,
    fetch_region_mask_plane,
    mask_plane_intersects,
    region_catalogue_entry,
    sample_mask_to_section_display,
)


ROOT = Path(__file__).resolve().parent
MRI = VolumeSpec("donor MRI", ROOT / "outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz")
HIST = VolumeSpec("native histology", ROOT / "outputs/spatial_feasibility/full8_200um_optbal.nii.gz")
REGISTERED_NAVIGATION_TARGETS = ("volume_viewer.py", "pages/1_Validation.py", "pages/2_Experimental_ROI.py")


def validate_navigation_targets(root: Path = ROOT) -> None:
    """Fail early if a sidebar target is not a registered local page."""
    missing = [target for target in REGISTERED_NAVIGATION_TARGETS if not (root / target).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing registered Streamlit page(s): {missing}")


validate_navigation_targets()

st.set_page_config(page_title="BigBrain TissueLink", layout="wide")
st.markdown(
    """
    <style>
    :root { --ink:#102238; --muted:#63748a; --teal:#087f8c; --teal-soft:#e9f7f7; --line:#dbe4ec; --warm:#fff8e7; }
    [data-testid="stSidebar"] { border-right: 1px solid var(--line); }
    [data-testid="stSidebarNav"] a { color: var(--ink); border-radius: 9px; }
    [data-testid="stSidebarNav"] a:hover { background: #dceff0; color: #075c65; }
    [data-testid="stSidebarNav"] a:focus-visible { outline: 3px solid #65bfc5; outline-offset: 2px; }
    [data-testid="stSidebarNav"] a[aria-current="page"] { background: #d4eeee; color: #075c65; font-weight: 750; }
    [data-testid="stSidebarNav"] span { font-weight: 600; }
    [data-testid="stCaptionContainer"] { color: var(--muted); }
    [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { color: var(--ink); }
    [data-testid="stAlert"] { color: var(--ink); }
    [data-testid="stButton"] button { color: var(--ink); background: #fff; border: 1px solid #b8c8d5; }
    [data-testid="stButton"] button:hover { color: #075c65; border-color: #087f8c; background: #e9f7f7; }
    [data-testid="stButton"] button:focus-visible { outline: 3px solid #65bfc5; outline-offset: 2px; }
    [data-testid="stButton"] button:disabled { color: #718096; background: #edf1f4; border-color: #d3dce3; }
    [data-testid="stExpander"] details { border-color: var(--line); background: #fff; }
    [data-testid="stExpander"] summary { color: var(--ink); }
    [data-baseweb="select"] > div { background: #fff; color: var(--ink); border-color: #b8c8d5; }
    [data-baseweb="select"] [role="option"] { color: var(--ink); background: #fff; }
    [data-baseweb="select"] [role="option"][aria-selected="true"] { background: #d4eeee; color: #075c65; }
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input { color: var(--ink); background: #fff; }
    .tl-hero { padding: 1.2rem 1.45rem 1rem; border: 1px solid var(--line); border-radius: 18px; background: linear-gradient(135deg,#ffffff 0%,#eef8f8 100%); box-shadow: 0 8px 24px rgba(16,34,56,.06); margin-bottom: 1rem; }
    .tl-kicker { color: var(--teal); font-size:.78rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; margin-bottom:.35rem; }
    .tl-hero h1 { color: var(--ink); font-size:2.1rem; line-height:1.1; margin:0; }
    .tl-hero p { color:var(--muted); font-size:1rem; margin:.55rem 0 0; max-width: 760px; }
    .tl-steps { display:grid; grid-template-columns:repeat(4,1fr); gap:.6rem; margin: .85rem 0 1.25rem; }
    .tl-step { background:#fff; border:1px solid var(--line); border-radius:12px; padding:.7rem .8rem; min-height:62px; }
    .tl-step b { display:block; color:var(--teal); font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; }
    .tl-step span { color:var(--ink); font-weight:650; font-size:.9rem; }
    .tl-section { color:var(--ink); font-weight:750; font-size:1.25rem; margin: .8rem 0 .25rem; }
    .tl-note { color:var(--muted); font-size:.88rem; }
    .tl-status { display:inline-block; border-radius:999px; padding:.25rem .6rem; background:var(--teal-soft); color:#08646d; font-size:.78rem; font-weight:700; }
    @media (max-width: 760px) { .tl-steps { grid-template-columns:repeat(2,1fr); } .tl-hero h1 { font-size:1.65rem; } }
    </style>
    <div class="tl-hero">
      <div class="tl-kicker">BigBrain reference anatomy</div>
      <h1>MRI–Histology Explorer</h1>
      <p>Explore a shared MRI–histology location, choose a registered tissue section, and export a bounded patch with its spatial provenance.</p>
    </div>
    <div class="tl-steps">
      <div class="tl-step"><b>01 · Navigate</b><span>Find a location</span></div>
      <div class="tl-step"><b>02 · Choose</b><span>Select a tissue area</span></div>
      <div class="tl-step"><b>03 · Inspect</b><span>Preview the patch</span></div>
      <div class="tl-step"><b>04 · Export</b><span>Download raw data</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning("Reference data from one donor; anatomical alignment is imperfect.")
st.caption("Public reference data only · not patient MRI · raw scientific values are preserved in exports")
with st.expander("Limitations and provenance", expanded=False):
    st.write(
        "This is reference-anatomy inspection, not patient MRI, arbitrary participant MRI, registration, "
        "or a clinical tool. Matching world coordinates do not guarantee matching anatomy. The detailed "
        "siibra section is linked by documented reference-space geometry only and remains Not independently reviewed."
    )
with st.expander("How to use TissueLink", expanded=True):
    st.markdown(
        """
        **1. Choose a registered section**
        Select the available histology section. This chooses its physical plane, not the patch location.

        **2. Find a location**
        Click either compact MRI or 200 µm histology overview. The yellow crosshair moves to that shared reference-space location.

        **3. Choose the tissue area**
        In the large registered-section image, click a visible dark tissue area. The cyan rectangle shows exactly what will be fetched.

        **4. Preview and export**
        Click **Fetch this selected detailed patch**, inspect the returned resolution and bounds, then download the ZIP. The NIfTI contains raw values; PNGs are visualizations.
        """
    )

with st.expander("Advanced features", expanded=False):
    st.write(
        "Optional technical tools include alignment review, atlas-context diagnostics, bounded multi-patch sampling, "
        "descriptive intensity statistics, collection replay, and Labelme/COCO annotation export. These controls do "
        "not change the primary demonstration path: choose tissue → inspect → collect → export. Unreviewed outputs "
        "remain explicitly marked and do not establish anatomical correctness."
    )

render_start_new_collection("manual")


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


def add_orientation_labels(view: np.ndarray, title: str, horizontal_labels=("L", "R"), vertical_labels=("I", "S")) -> np.ndarray:
    result = Image.fromarray(view).convert("RGB")
    draw = ImageDraw.Draw(result)
    draw.rectangle((0, 0, result.width - 1, 22), fill=(0, 0, 0))
    draw.text((8, 5), title, fill=(255, 255, 255))
    # Labels describe the displayed axes, not the underlying array axes.
    draw.text((result.width - 24, 26), horizontal_labels[1], fill=(255, 255, 0))
    draw.text((8, 26), horizontal_labels[0], fill=(255, 255, 0))
    draw.text((result.width - 24, result.height - 35), vertical_labels[1], fill=(255, 255, 0))
    draw.text((8, result.height - 35), vertical_labels[0], fill=(255, 255, 0))
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
    """Package one raw registered-section patch and its provenance."""
    section_number = saved["metadata"].get("section_number", "selected")
    report = io.BytesIO()
    with zipfile.ZipFile(report, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"registered_section_{section_number}_raw.nii.gz", saved["raw_nifti"])
        archive.writestr(f"registered_section_{section_number}_visualization.png", saved["patch_png"])
        archive.writestr("reconstructed_histology_200um_footprint.png", saved["footprint_png"])
        archive.writestr("metadata.json", json.dumps(saved["metadata"], indent=2) + "\n")
        archive.writestr("README.txt", "Raw NIfTI values are preserved. PNG files are visualization-only. Reference-space placement is not independently reviewed and is not a claim of exact MRI correspondence.\n")
    return report.getvalue()


if not MRI.path.exists() or not HIST.path.exists():
    st.error("The two local feasibility volumes are missing. Run the feasibility download first.")
    st.stop()

if "patch_collection" not in st.session_state:
    st.session_state.patch_collection = {}

mri, hist = get_images()
common = common_world_bounds([mri, hist])
catalogue = section_catalogue()
if not catalogue:
    st.error("No registered detailed sections are available from the installed siibra configuration.")
    st.stop()

section_options = [f"#{item['section_number']} · {item['section_plane_y_mm']:.4f} mm" for item in catalogue]
st.markdown('<div class="tl-section">1. Choose a registered section</div>', unsafe_allow_html=True)
st.markdown('<div class="tl-note">This sets the documented histology plane. You will choose the patch location in the section image later.</div>', unsafe_allow_html=True)
with st.container(border=True):
    section_option = st.selectbox(
        "Registered section",
        section_options,
        index=next((index for index, item in enumerate(catalogue) if item["section_number"] == 3458), 0),
        key="registered-section-option",
        label_visibility="visible",
    )
selected_catalogue = catalogue[section_options.index(section_option)]
selected_section_id = selected_catalogue["id"]
selected_section_number = selected_catalogue["section_number"]
selected_section_label = selected_catalogue["label"]
if st.session_state.get("selected_registered_section_id") != selected_section_id:
    if "selected_registered_section_id" in st.session_state:
        invalidate_current_selection(st.session_state)
        st.session_state.pop("volume_viewer_last_section_click", None)
        st.session_state.pop("region_mask_image", None)
        st.session_state.pop("region_mask_metadata", None)
        st.session_state.pop("region_mask_display", None)
        st.session_state.pop("region_mask_display_metadata", None)
        for sampler_key in (
            "sampling_plan",
            "sampling_results",
            "sampling_section_id",
        ):
            st.session_state.pop(sampler_key, None)
    st.session_state.selected_registered_section_id = selected_section_id
    # Section selection is an explicit navigation action: align both reference
    # views to the documented section plane before rendering them.
    st.session_state.world_y_slice = float(selected_catalogue["section_plane_y_mm"])
    st.session_state.registered_navigation_active = True
verified_sections = st.session_state.get("registered_fetch_verified_ids", set())
fetch_status = "verified in this session" if selected_section_id in verified_sections else "not yet verified in this session"
st.markdown(
    f'<span class="tl-status">Section #{selected_section_number} · Y≈{selected_catalogue["section_plane_y_mm"]:.4f} mm · fetch {fetch_status}</span>',
    unsafe_allow_html=True,
)

with st.expander("Section coverage and evidence status", expanded=False):
    st.caption(
        "Informational catalogue only. Discovery, patch-fetch evidence, export-integrity checks and independent anatomical review are separate dimensions. "
        "A successful patch does not validate an entire section; untested sections remain Unknown."
    )
    status_rows = section_status_rows(
        catalogue,
        current_fetch_ids=st.session_state.get("registered_fetch_verified_ids", set()),
        collection=st.session_state.patch_collection,
    )
    y_values = [float(row["world_Y_mm"]) for row in status_rows]
    status_filter = st.selectbox(
        "Show sections with evidence in",
        ["All", "Discovered", "Fetch evidence", "Export integrity", "Independent anatomical review"],
        key="section-status-filter",
    )
    y_filter = st.slider(
        "World Y range (mm)",
        min_value=float(min(y_values)),
        max_value=float(max(y_values)),
        value=(float(min(y_values)), float(max(y_values))),
        key="section-status-y-range",
    )
    filtered_status_rows = filter_section_status_rows(status_rows, status_filter, y_filter)
    st.caption(f"Showing {len(filtered_status_rows)} of {len(status_rows)} discovered registered sections.")
    st.dataframe(
        [
            {
                "Section": row["section"],
                "World Y (mm)": row["world_Y_mm"],
                "Provider metadata": row["discovered"],
                "Real fetch evidence": row["fetch_evidence"],
                "Export integrity": row["export_integrity"],
                "Independent anatomy review": row["anatomical_review"],
                "Evidence references": "; ".join(
                    str(row[key]) for key in (
                        "discovered_evidence", "fetch_evidence_reference", "export_evidence_reference", "anatomical_review_evidence"
                    ) if str(row[key]) not in {"No fetch evidence recorded", "No export-integrity evidence recorded", "No independent anatomical review"}
                ),
            }
            for row in filtered_status_rows
        ],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Advanced · dates, software versions and exact section IDs", expanded=False):
        st.dataframe(filtered_status_rows, use_container_width=True, hide_index=True)

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
    if isinstance(pending_location, dict):
        st.session_state.location_x_input = float(pending_location["x"])
        st.session_state.location_z_input = float(pending_location["z"])
        st.session_state.world_y_slice = float(pending_location["y"])
    else:
        st.session_state.location_x_input = float(pending_location[0])
        st.session_state.location_z_input = float(pending_location[1])
if "pending_registered_reference" in st.session_state:
    pending_reference = st.session_state.pop("pending_registered_reference")
    st.session_state.location_x_input = pending_reference[0]
    st.session_state.location_z_input = pending_reference[1]
    st.session_state.world_y_slice = pending_reference[2]
    st.session_state.current_section_selection_world = [
        float(pending_reference[0]), float(pending_reference[2]), float(pending_reference[1])
    ]

# Navigation buttons request a change for the next run.  They never mutate
# the key of an already-instantiated slider in the current run.
if "pending_world_y_navigation" in st.session_state:
    st.session_state.world_y_slice = float(st.session_state.pop("pending_world_y_navigation"))
st.session_state.setdefault("world_y_slice", -25.7922)
if st.button(f"Align reference views to section #{selected_section_number} plane", key="navigate-selected-section"):
    try:
        _, section_bbox_for_navigation, *_ = registered_context(selected_section_id)
        section_plane_y = float((section_bbox_for_navigation.minpoint[1] + section_bbox_for_navigation.maxpoint[1]) / 2.0)
        st.session_state.world_y_slice = section_plane_y
        st.session_state.registered_navigation_active = True
        st.rerun()
    except Exception as exc:
        st.error(f"Could not navigate to registered section #{selected_section_number}: {exc}")
with st.expander("Advanced · display controls", expanded=False):
    st.caption("These controls affect navigation and visualization only; exported scientific values are unchanged.")
    world_y = st.slider("Reference slice Y (mm)", float(common["min"][1]), float(common["max"][1]), step=0.2, key="world_y_slice")

    section_distances = []
    for item in catalogue:
        min_y = item["bounds_mm"]["min_y"]
        max_y = item["bounds_mm"]["max_y"]
        intersects = min_y <= world_y <= max_y
        section_distances.append({
            "section": f"#{item['section_number']}",
            "plane_y_mm": round(item["section_plane_y_mm"], 4),
            "distance_mm": round(0.0 if intersects else abs(item["section_plane_y_mm"] - world_y), 4),
            "relation": "intersects selected slice" if intersects else "nearby plane",
        })
    section_distances.sort(key=lambda item: (item["distance_mm"], item["section"]))
    with st.expander("Available section planes at this MRI location", expanded=False):
        st.caption("Distance is measured along reference-space Y. A nearby plane is not the exact selected location.")
        st.dataframe(section_distances[:12], use_container_width=True, hide_index=True)
        nearest = section_distances[0]
        if nearest["relation"] == "nearby plane" and st.button(f"Navigate to nearby section {nearest['section']} plane", key="navigate-nearest-section"):
            st.session_state.pending_world_y_navigation = nearest["plane_y_mm"]
            st.session_state.registered_navigation_active = True
            st.rerun()

    step = st.select_slider("Overview grid spacing", options=[0.2, 0.4, 0.8], value=0.2, format_func=lambda value: f"{value:.1f} mm/pixel")
    contrast_low, contrast_high = st.slider("Display contrast (visualization only)", 0.0, 100.0, (1.0, 99.0), 0.5)
    st.caption("Contrast changes the preview appearance only. Raw image values and scientific exports are preserved.")
    if contrast_high <= contrast_low:
        st.error("The upper contrast percentile must be greater than the lower percentile.")
        st.stop()

    x_world = st.number_input("Crosshair world X (mm)", min_value=float(common["min"][0]), max_value=float(common["max"][0]), step=step, key="location_x_input")
    z_world = st.number_input("Crosshair world Z (mm)", min_value=float(common["min"][2]), max_value=float(common["max"][2]), step=step, key="location_z_input")

# Once a detailed-section point has been chosen, it is the single active
# selection for every display.  This prevents a stale numeric-widget value
# from driving the MRI marker while the lower whole-section marker uses the
# newer section click.
active_selection_world = st.session_state.get("current_section_selection_world")
if active_selection_world is not None and len(active_selection_world) == 3:
    x_world, world_y, z_world = (float(value) for value in active_selection_world)

if st.session_state.get("registered_navigation_active"):
    selected_plane_y = float(selected_catalogue["section_plane_y_mm"])
    if abs(float(world_y) - selected_plane_y) <= 1e-6:
        st.caption(
            f"Reference views aligned to registered section #{selected_section_number}: "
            f"documented plane Y≈{selected_plane_y:.4f} mm; displayed slice centre Y={float(world_y):.4f} mm."
        )
    else:
        st.warning(
            f"Reference views are currently sampled at Y={float(world_y):.4f} mm, while section "
            f"#{selected_section_number} is at documented Y≈{selected_plane_y:.4f} mm. "
            f"Click ‘Align reference views to section #{selected_section_number} plane’ before using the linked views."
        )

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

st.markdown('<div class="tl-section">2. Find a location</div>', unsafe_allow_html=True)
st.caption("Click either compact overview to move the shared crosshair. Both panels show the same physical X/Z field of view.")
col1, col2 = st.columns(2)
with col1:
    st.markdown("### MRI overview — 0.444 mm")
    st.caption(
        f"Compact navigation · display contrast only · RAS X/Z · selected world "
        f"({x_world:.2f}, {world_y:.2f}, {z_world:.2f}) mm · display UV ({x_pixel}, {z_pixel})"
    )
    mri_click = streamlit_image_coordinates(mri_navigation, width=int(mri_navigation.shape[1]), key="location_picker_mri")
with col2:
    st.markdown("### Histology overview — 200 µm; cells not resolved")
    st.caption(
        f"Compact navigation · display contrast only · RAS X/Z · selected world "
        f"({x_world:.2f}, {world_y:.2f}, {z_world:.2f}) mm · display UV ({x_pixel}, {z_pixel})"
    )
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
            # A new reference click supersedes any refined section point.
            # The next render carries this X/Z through the verified inverse
            # provider geometry, or reports it as out of bounds.
            invalidate_current_selection(st.session_state)
            st.rerun()
with st.expander("Advanced · display mapping and diagnostics", expanded=False):
    st.caption(
        f"Physical display mapping: horizontal world X ({x_axis[0]:.2f} to {x_axis[-1]:.2f} mm), "
        f"vertical world Z ({z_axis[0]:.2f} to {z_axis[-1]:.2f} mm), {step:.2f} mm per display pixel; "
        "no display flip or axis swap; horizontal L/R and vertical I/S follow RAS; "
        "A/P is the shared out-of-plane world-Y slice."
    )
    st.info(
        "The magenta outline marks the containing MRI sampling voxel; it is not an uncertainty estimate. "
        "No documented registration-uncertainty radius is available. The 200 µm reconstruction does not provide cellular detail."
    )

st.markdown('<div class="tl-section">3. Inspect the linked location</div>', unsafe_allow_html=True)
st.caption(
    "These are cropped neighbourhoods around the selected world point. Their physical coverage is identical; "
    "they are not anatomical registration results. Display enlargement does not fetch finer histology or reveal individual cells."
)
half_width_mm = st.slider("Neighbourhood size (half-width in mm)", 1.0, 20.0, 5.0, 0.5)
half = max(1, int(round(half_width_mm / step)))
x0, x1 = max(0, x_pixel - half), min(mri_view.shape[1], x_pixel + half + 1)
z0, z1 = max(0, z_pixel - half), min(mri_view.shape[0], z_pixel + half + 1)
mri_neighbour = mri_view[z0:z1, x0:x1]
hist_neighbour = hist_view[z0:z1, x0:x1]
coverage_mm = [(x1 - x0 - 1) * step, (z1 - z0 - 1) * step]
st.caption(f"Selected world point: X={x_world:.2f}, Y={world_y:.2f}, Z={z_world:.2f} mm · neighbourhood coverage: {coverage_mm[0]:.2f} × {coverage_mm[1]:.2f} mm")
neigh1, neigh2 = st.columns(2)
with neigh1:
    st.markdown("### Reference MRI neighbourhood · centered on shared point")
    st.caption(f"World XYZ: ({x_world:.2f}, {world_y:.2f}, {z_world:.2f}) mm · source display UV: ({x_pixel}, {z_pixel})")
    st.image(rgb_with_crosshair(mri_neighbour, x_pixel - x0, z_pixel - z0), use_container_width=True)
with neigh2:
    st.markdown("### Reconstructed histology — 200 µm neighbourhood · centered on shared point")
    st.caption(f"World XYZ: ({x_world:.2f}, {world_y:.2f}, {z_world:.2f}) mm · source display UV: ({x_pixel}, {z_pixel})")
    st.image(rgb_with_crosshair(hist_neighbour, x_pixel - x0, z_pixel - z0), use_container_width=True)

st.markdown('<div class="tl-section">4. Choose the detailed patch area</div>', unsafe_allow_html=True)
st.caption(
    "This stage uses the selected section's documented reference-space geometry. "
    "The MRI and 200 µm views are sampled at the displayed shared location, while the detailed-section "
    "X/Z selection is made independently on the registered overview. No Labelme files or annotation uploads are required."
)
# The selected registered section is part of the main workflow, not an
# optional gate. Keeping this path visible makes selection → fetch → export
# available without requiring a second control before the overview renders.
explore_registered = True
if explore_registered:
    registered_display_stage = "provider metadata"
    try:
        section, section_bbox, provider, provider_volume, provider_info, provider_scale = registered_context(selected_section_id)
        section_bounds_values = tuple(float(value) for value in (*section_bbox.minpoint, *section_bbox.maxpoint))
        section_y = float((section_bbox.minpoint[1] + section_bbox.maxpoint[1]) / 2.0)
        section_x = float((section_bbox.minpoint[0] + section_bbox.maxpoint[0]) / 2.0)
        section_z = float((section_bbox.minpoint[2] + section_bbox.maxpoint[2]) / 2.0)
        mri_section_voxel, mri_section_center = nearest_voxel_for_world(mri, np.array([section_x, section_y, section_z]))
        hist_section_voxel, hist_section_center = nearest_voxel_for_world(hist, np.array([section_x, section_y, section_z]))
        st.caption(
            f"Section plane centre: Y={section_y:.4f} mm · sampled MRI slice centre Y={mri_section_center[1]:.4f} mm · "
            f"sampled 200 µm histology slice centre Y={hist_section_center[1]:.4f} mm."
        )
        with st.expander("Advanced · section identity and sampled slice centres", expanded=False):
            st.write({
                "section": f"#{selected_section_number}",
                "section_id": selected_section_id,
                "provider": selected_catalogue["source_url"],
                "documented_section_plane_centre_y_mm": section_y,
                "MRI_sampled_slice_centre_mm": mri_section_center.tolist(),
                "histology_200um_sampled_slice_centre_mm": hist_section_center.tolist(),
                "anatomical_status": "Not independently reviewed",
            })
        st.caption(
            "Reference-space placement only; anatomical correspondence has not been independently reviewed. "
            "The 200 µm volume is not cellular-equivalent, and no new registration is applied."
        )

        registered_display_stage = "overview provider fetch"
        section_image, section_plane, section_slice, section_range = registered_overview(section_bounds_values, selected_section_id)
        registered_display_stage = "overview rendering"
        section_display_raw, section_display_mapping = section_display_array(section_image)
        section_source = Image.fromarray(section_display_raw)
        fit_scale = min(900 / section_source.width, 620 / section_source.height, 1.0)
        section_display_width = max(1, round(section_source.width * fit_scale))
        section_display_height = max(1, round(section_source.height * fit_scale))
        section_display = np.asarray(section_source.resize((section_display_width, section_display_height), Image.Resampling.NEAREST))
        with st.expander("Optional · atlas region navigation", expanded=False):
            region_info = region_catalogue_entry()
            st.caption(
                f"Supported region: {region_info['region']} · {region_info['parcellation']} · "
                f"space: {region_info['space']} · threshold: {region_info['threshold']}"
            )
            st.caption(
                "This is an experimental geometry diagnostic. A finite-Y slab overlap is not "
                "an exact-plane intersection or a validated tissue-targeting overlay."
            )
            verified_rows = [
                {
                    "section": f"#{number}",
                    "plane Y (mm)": values["plane_y_mm"],
                    "nonzero mask voxels": values["nonzero_mask_voxels"],
                    "status": "nonzero finite-Y slab; exact-plane audit required",
                }
                for number, values in VERIFIED_SECTION_INTERSECTIONS.items()
            ]
            st.dataframe(verified_rows, use_container_width=True, hide_index=True)
            st.caption("Only these sections have bounded mask-slab evidence for this region; other catalogue sections are untested.")
            if st.button("Check selected section against region mask", key="check-region-mask"):
                try:
                    with st.spinner("Fetching bounded atlas mask plane…"):
                        region_mask, region_metadata = fetch_region_mask_plane(
                            region_info["region"], section_y,
                        )
                    st.session_state.region_mask_image = region_mask
                    st.session_state.region_mask_metadata = {
                        **region_metadata,
                        "section_id": selected_section_id,
                        "section_number": selected_section_number,
                    }
                    exact_mask_display, exact_metadata = sample_mask_to_section_display(
                        region_mask,
                        section_image,
                        section_y,
                        (section_display_height, section_display_width),
                    )
                    st.session_state.region_mask_display = exact_mask_display
                    st.session_state.region_mask_display_metadata = exact_metadata
                except Exception as exc:
                    st.error(f"Region-mask provider check failed: {exc}")
            region_mask = st.session_state.get("region_mask_image")
            region_metadata = st.session_state.get("region_mask_metadata")
            if region_metadata and region_metadata.get("section_id") == selected_section_id and region_mask is not None:
                if mask_plane_intersects(region_mask):
                    exact_metadata = st.session_state.get("region_mask_display_metadata", {})
                    exact_mask_display = st.session_state.get("region_mask_display")
                    exact_count = int(exact_metadata.get("exact_plane_nonzero_pixels", 0))
                    st.info(
                        f"The bounded mask slab contains {region_metadata['mask_nonzero_voxels']:,} nonzero voxels. "
                        f"Exact section-plane sampling finds {exact_count:,} display pixels. "
                        "Slab overlap is not exact-plane intersection."
                    )
                    if exact_mask_display is not None and exact_count:
                        selected_mask_pixel = central_nonzero_display_pixel(exact_mask_display)
                        st.warning(
                            "Atlas overlay display is paused: the exact-plane mask still reaches "
                            "background-like overview pixels. The clean section overview below remains "
                            "unmarked; this mask must not be used to choose a tissue patch."
                        )
                        if selected_mask_pixel is not None:
                            st.caption(
                                f"Numerical diagnostic only · example actual nonzero mask pixel: display UV={selected_mask_pixel}. "
                                "The saved red diagnostic is evidence for review, not a tissue-targeting overlay."
                            )
                    else:
                        st.warning(
                            "The mask slab overlaps this section's Y neighbourhood, but exact-plane sampling "
                            "found no nonzero pixels. No region-targeted patch is implied."
                        )
                    st.caption(
                        f"Mask actual resolution: {region_metadata['actual_resolution_mm']} mm; "
                        "categorical sampling used both full affines on the exact documented section plane."
                    )
                else:
                    st.warning(
                        f"No nonzero region-mask voxels were found on section #{selected_section_number}'s bounded plane. "
                        "No region-targeted patch is implied."
                    )
        st.markdown(f"#### Choose a detailed patch location in section #{selected_section_number}")
        st.caption(
            f"#{selected_section_number} · requested overview {OVERVIEW_RESOLUTION_MM:g} mm · actual voxel size "
            f"{[float(value) for value in section_image.header.get_zooms()[:3]]} mm · "
            f"provider plane index y={section_slice} · raw range {section_range} · fitted display {section_display_width}×{section_display_height}px · budget {OVERVIEW_MAX_BYTES:,} bytes."
        )
        registered_half_x = st.number_input("Detailed patch half-width X (mm)", 0.25, 2.0, 1.0, 0.25, key="volume-viewer-registered-half-x")
        registered_half_z = st.number_input("Detailed patch half-width Z (mm)", 0.25, 2.0, 1.0, 0.25, key="volume-viewer-registered-half-z")
        registered_resolution = st.selectbox("Detailed patch requested resolution (mm)", [0.01, 0.02, 0.1], index=0, key="volume-viewer-registered-resolution")
        point_was_selected = "volume_viewer_section_point" in st.session_state
        section_point = st.session_state.get("volume_viewer_section_point")
        reference_point_available = False
        if section_point is None:
            reference_xz = (float(x_world), float(z_world))
            reference_in_section = (
                float(section_bbox.minpoint[0]) <= reference_xz[0] <= float(section_bbox.maxpoint[0])
                and float(section_bbox.minpoint[2]) <= reference_xz[1] <= float(section_bbox.maxpoint[2])
            )
            if reference_in_section:
                try:
                    section_point = map_section_world_to_pixel(
                        section_image, (reference_xz[0], section_y, reference_xz[1]),
                        (section_display_width, section_display_height),
                    )
                    reference_point_available = True
                except ValueError:
                    section_point = None
            if section_point is None:
                section_point = map_section_pixel_to_world(
                    section_image, (section_display_width / 2, section_display_height / 2),
                    (section_display_width, section_display_height), section_y,
                )
        selected_section_world = [float(value) for value in section_point["world_xyz_mm"]]
        selected_x, selected_z = selected_section_world[0], selected_section_world[2]
        requested_section_bounds = Bounds(
            max(float(section_bbox.minpoint[0]), selected_x - registered_half_x), float(section_bbox.minpoint[1]), max(float(section_bbox.minpoint[2]), selected_z - registered_half_z),
            min(float(section_bbox.maxpoint[0]), selected_x + registered_half_x), float(section_bbox.maxpoint[1]), min(float(section_bbox.maxpoint[2]), selected_z + registered_half_z),
        )
        requested_section_bounds.validate()

        # Use the exact current detailed-section point for the lower whole-
        # section marker, rather than a possibly stale reference-widget value.
        lower_marker_world = [float(value) for value in selected_section_world]
        selection_sync = selection_sync_report(
            section_point,
            lower_marker_world,
            requested_section_bounds.__dict__,
        )
        st.markdown("#### Current selection synchronization")
        st.write(selection_sync)
        if not selection_sync["same_current_world_point"]:
            st.warning(
                "The detailed-section point and lower reconstruction marker are currently different. "
                "Click the detailed section again or use the reference-plane navigation action before fetching."
            )

        section_rect = map_source_bounds_to_preview_rect(
            (requested_section_bounds.min_x, requested_section_bounds.min_z,
             requested_section_bounds.max_x, requested_section_bounds.max_z),
            section_image.affine, section_image.shape,
            (section_display_width, section_display_height),
        )
        section_pixel = (
            int(np.clip(round(section_point["display_pixel_uv"][0]), 0, section_display_width - 1)),
            int(np.clip(round(section_point["display_pixel_uv"][1]), 0, section_display_height - 1)),
        )
        st.caption(
            f"Current selection · section display UV ({section_pixel[0]}, {section_pixel[1]}) · "
            f"world XYZ ({selected_x:.4f}, {selected_section_world[1]:.4f}, {selected_z:.4f}) mm · "
            "section display horizontal=source Z, vertical=source X; no display flips"
        )
        selection_display = rgb_with_crosshair(section_display, section_pixel[0], section_pixel[1])
        selection_display = add_rect(
            selection_display,
            (
                int(round(section_rect["left"])), int(round(section_rect["top"])),
                int(round(section_rect["left"] + section_rect["width"])),
                int(round(section_rect["top"] + section_rect["height"])),
            ),
        )
        st.markdown("### Choose where to fetch the detailed patch")
        st.caption(
            "Click a visible dark tissue area in the image below. This chooses the centre of the detailed patch, "
            "not a new section. Yellow = selected point; cyan = the exact requested patch footprint. "
            f"Requested footprint: {2 * registered_half_x:g} × {2 * registered_half_z:g} mm."
        )
        st.caption(
            "This is the registered detailed-section overview. Its image appearance is not expected to match the "
            "MRI or 200 µm overview pixel-for-pixel; the linked relationship here is the documented world-coordinate placement."
        )
        if section_range[0] == section_range[1]:
            st.error(
                "This section overview has no intensity variation at the selected plane, so there is no visible tissue "
                "location to select. Choose another registered section; no background patch will be exported."
            )
        section_click = streamlit_image_coordinates(selection_display, width=section_display_width, key="volume-viewer-section-overview")
        section_click_key = None
        if section_click:
            section_click_key = (
                round(float(section_click.get("x", 0.0)), 2),
                round(float(section_click.get("y", 0.0)), 2),
            )
        if section_click and section_click_key != st.session_state.get("volume_viewer_last_section_click"):
            st.session_state["volume_viewer_last_section_click"] = section_click_key
            mapped_section_point = map_section_pixel_to_world(
                section_image, (section_click["x"], section_click["y"]),
                (section_display_width, section_display_height), section_y,
            )
            st.session_state["volume_viewer_section_point"] = mapped_section_point
            st.session_state["pending_registered_reference"] = (
                float(mapped_section_point["world_xyz_mm"][0]),
                float(mapped_section_point["world_xyz_mm"][2]),
                section_y,
            )
            st.session_state["registered_navigation_active"] = True
            st.session_state.pop("volume_viewer_registered_patch", None)
            st.session_state.pop("volume_viewer_registered_signature", None)
            st.session_state.current_section_selection_world = [
                float(mapped_section_point["world_xyz_mm"][0]),
                float(mapped_section_point["world_xyz_mm"][1]),
                float(mapped_section_point["world_xyz_mm"][2]),
            ]
            st.rerun()
        if point_was_selected:
            st.success("Patch centre selected. The cyan rectangle is the area that the Fetch button will request.")
            st.info(
                "World-coordinate selection is synchronized. The lower image is a whole-section reference view; "
                "its marker and cyan footprint use the same world point, but matching coordinates do not guarantee matching anatomy."
            )
        elif reference_point_available:
            st.info("The current reference X/Z point is inside this section and has been carried into the overview. Click the image to refine it.")
        else:
            st.info("The current reference X/Z point is outside this section. Click inside the section image to choose a valid tissue location.")
        whole_section_u, whole_section_v = world_to_grid_pixel((selected_x, selected_z), x_axis, z_axis)
        with st.expander("Advanced · selected point mapping", expanded=False):
            st.write({
                "selected_section_world_xyz_mm": selected_section_world,
                "registered_section_display_uv": section_point["display_pixel_uv"],
                "whole_section_display_uv": [whole_section_u, whole_section_v],
                "reference_display_uv": [x_pixel, z_pixel],
                "section_to_world_transform": section_point["mapping"],
                "whole_section_to_world_transform": "horizontal world X, vertical world Z; sampled common grid",
                "all_current_world_points_equal": bool(
                    np.allclose(selected_section_world, [x_world, world_y, z_world], atol=1e-6, rtol=0.0)
                ),
            })
        footprint_x0, footprint_z0 = world_to_grid_pixel((requested_section_bounds.min_x, requested_section_bounds.min_z), x_axis, z_axis)
        footprint_x1, footprint_z1 = world_to_grid_pixel((requested_section_bounds.max_x, requested_section_bounds.max_z), x_axis, z_axis)
        hist_footprint = add_rect(
            rgb_with_crosshair(hist_view, whole_section_u, whole_section_v),
            (min(footprint_x0, footprint_x1), min(footprint_z0, footprint_z1), max(footprint_x0, footprint_x1), max(footprint_z0, footprint_z1)),
        )
        hist_footprint = add_scale_bar(hist_footprint, step)
        st.image(hist_footprint, caption="Histology overview — 200 µm; cells not resolved · detailed patch footprint in cyan", width=420)
        st.caption(
            f"Whole-section marker · display UV ({whole_section_u}, {whole_section_v}) · "
            f"world XYZ ({selected_x:.4f}, {selected_section_world[1]:.4f}, {selected_z:.4f}) mm · "
            "whole-section display horizontal=world X, vertical=world Z. The footprint uses provider geometry; "
            "it is not a claim of exact tissue correspondence."
        )

        with st.expander("Experimental · sample patches within this rectangle", expanded=False):
            st.warning(
                "This samples a geometric rectangle on one registered section; it is not anatomical-region sampling. "
                "No background filtering is applied, so every requested centre remains in the plan."
            )
            st.caption(
                "Footprints must fit fully inside the rectangle. Overlap is allowed and recorded. "
                f"The current limits are {MAX_PATCH_COUNT} patches, {MAX_REQUEST_COUNT} requests and "
                f"{MAX_ESTIMATED_BYTES / (1024 * 1024):g} MiB estimated raw data."
            )
            sample_col1, sample_col2 = st.columns(2)
            with sample_col1:
                sample_min_x = st.number_input("Rectangle min X (mm)", value=float(requested_section_bounds.min_x), key="sampling-min-x")
                sample_max_x = st.number_input("Rectangle max X (mm)", value=float(requested_section_bounds.max_x), key="sampling-max-x")
                sample_width_x = st.number_input("Patch width X (mm)", min_value=0.01, max_value=2.0, value=min(1.0, max(0.01, float(requested_section_bounds.max_x - requested_section_bounds.min_x))), step=0.01, key="sampling-width-x")
            with sample_col2:
                sample_min_z = st.number_input("Rectangle min Z (mm)", value=float(requested_section_bounds.min_z), key="sampling-min-z")
                sample_max_z = st.number_input("Rectangle max Z (mm)", value=float(requested_section_bounds.max_z), key="sampling-max-z")
                sample_height_z = st.number_input("Patch height Z (mm)", min_value=0.01, max_value=2.0, value=min(1.0, max(0.01, float(requested_section_bounds.max_z - requested_section_bounds.min_z))), step=0.01, key="sampling-height-z")
            sample_method = st.selectbox("Sampling method", ["Regular grid", "Seeded random"], key="sampling-method")
            if sample_method == "Regular grid":
                grid_col1, grid_col2 = st.columns(2)
                with grid_col1:
                    sample_spacing_x = st.number_input("Grid spacing X (mm)", min_value=0.01, max_value=10.0, value=1.0, step=0.01, key="sampling-spacing-x")
                with grid_col2:
                    sample_spacing_z = st.number_input("Grid spacing Z (mm)", min_value=0.01, max_value=10.0, value=1.0, step=0.01, key="sampling-spacing-z")
                sample_count = None
                sample_seed = None
            else:
                sample_count = st.number_input("Random patch count", min_value=1, max_value=MAX_PATCH_COUNT, value=4, step=1, key="sampling-count")
                sample_seed = st.number_input("Random seed", min_value=0, value=3458, step=1, key="sampling-seed")
                sample_spacing_x = sample_spacing_z = None
            sample_resolution = st.selectbox("Sampling request resolution (mm)", [0.01, 0.02, 0.1], index=1, key="sampling-resolution")
            sample_rectangle = RectangleXZ(sample_min_x, sample_min_z, sample_max_x, sample_max_z)
            sample_size = PatchSizeXZ(sample_width_x, sample_height_z)
            sample_estimated = estimated_bytes_per_patch(sample_size, sample_resolution, max(0.02, float(section_bbox.maxpoint[1] - section_bbox.minpoint[1])))
            st.caption(f"Estimated raw bytes per request: {sample_estimated:,}; total is checked before retrieval.")
            if st.button("Generate sampling plan", key="sampling-generate-plan"):
                try:
                    if not (
                        float(section_bbox.minpoint[0]) <= sample_rectangle.min_x
                        and sample_rectangle.max_x <= float(section_bbox.maxpoint[0])
                        and float(section_bbox.minpoint[2]) <= sample_rectangle.min_z
                        and sample_rectangle.max_z <= float(section_bbox.maxpoint[2])
                    ):
                        raise ValueError("sampling rectangle must stay inside the selected section bounds")
                    if sample_method == "Regular grid":
                        centres = generate_regular_grid(sample_rectangle, sample_size, sample_spacing_x, sample_spacing_z)
                        method = "regular_grid"
                    else:
                        centres = generate_seeded_random(sample_rectangle, sample_size, int(sample_count), int(sample_seed))
                        method = "seeded_random"
                    total_estimated = sample_estimated * len(centres)
                    if len(centres) > MAX_REQUEST_COUNT or total_estimated > MAX_ESTIMATED_BYTES:
                        raise ValueError(
                            f"sampling plan exceeds limits: {len(centres)} requests and {total_estimated:,} estimated bytes"
                        )
                    plan = plan_metadata(
                        method,
                        sample_rectangle,
                        sample_size,
                        centres,
                        sample_resolution,
                        seed=int(sample_seed) if sample_seed is not None else None,
                        spacing_x=sample_spacing_x,
                        spacing_z=sample_spacing_z,
                    )
                    plan.update({
                        "section_id": selected_section_id,
                        "section_number": selected_section_number,
                        "section_plane_y_mm": section_y,
                        "y_bounds_mm": [float(section_bbox.minpoint[1]), float(section_bbox.maxpoint[1])],
                        "estimated_bytes_per_patch": sample_estimated,
                        "estimated_total_bytes": total_estimated,
                    })
                    st.session_state.sampling_plan = plan
                    st.session_state.sampling_results = []
                    st.session_state.sampling_section_id = selected_section_id
                    st.success(f"Generated {len(centres)} stored patch centre(s). Review the footprints before retrieval.")
                except (ValueError, RuntimeError) as exc:
                    st.error(f"Sampling plan rejected: {exc}")

            sampling_plan = st.session_state.get("sampling_plan")
            if sampling_plan and sampling_plan.get("section_id") == selected_section_id:
                sampling_preview = np.asarray(section_display).copy()
                for centre in sampling_plan["centres_xz_mm"]:
                    bounds = footprint_bounds(
                        (float(centre[0]), float(centre[1])),
                        PatchSizeXZ(**sampling_plan["patch_dimensions_mm"]),
                        float(section_bbox.minpoint[1]),
                        float(section_bbox.maxpoint[1]),
                    )
                    rect = map_source_bounds_to_preview_rect(
                        (bounds["min_x"], bounds["min_z"], bounds["max_x"], bounds["max_z"]),
                        section_image.affine, section_image.shape,
                        (section_display_width, section_display_height),
                    )
                    sampling_preview = add_rect(
                        sampling_preview,
                        (int(round(rect["left"])), int(round(rect["top"])), int(round(rect["left"] + rect["width"])), int(round(rect["top"] + rect["height"]))),
                        colour=(0, 180, 255),
                    )
                st.image(sampling_preview, caption="Sampling plan preview — every cyan footprint is a requested patch", use_container_width=True)
                st.write({
                    "section_id": sampling_plan["section_id"],
                    "method": sampling_plan["method"],
                    "requested_patch_count": sampling_plan["count"],
                    "stored_centres_xz_mm": sampling_plan["centres_xz_mm"],
                    "edge_handling": sampling_plan["edge_handling"],
                    "overlap_policy": sampling_plan["overlap_policy"],
                    "background_filtering": sampling_plan["background_filtering"],
                })
                if st.button("Fetch sampling plan", type="primary", key="sampling-fetch-plan"):
                    results = []
                    with st.status("Retrieving bounded sampling patches…", expanded=True) as sampling_status:
                        for index, centre in enumerate(sampling_plan["centres_xz_mm"]):
                            bounds_dict = footprint_bounds(
                                (float(centre[0]), float(centre[1])),
                                PatchSizeXZ(**sampling_plan["patch_dimensions_mm"]),
                                sampling_plan["y_bounds_mm"][0], sampling_plan["y_bounds_mm"][1],
                            )
                            requested = Bounds(**bounds_dict)
                            result = {
                                "index": index,
                                "centre_xz_mm": [float(centre[0]), float(centre[1])],
                                "requested_bounds_mm": bounds_dict,
                            }
                            try:
                                sampling_status.write(f"Request {index + 1}/{sampling_plan['count']}")
                                patch, patch_section, _ = fetch_crop(
                                    requested,
                                    resolution_mm=float(sampling_plan["requested_resolution_mm"]),
                                    max_bytes=MAX_BYTES,
                                    section_id=selected_section_id,
                                )
                                raw = np.asanyarray(patch.dataobj)
                                result.update({
                                    "status": "background_only" if not has_intensity_variation(raw) else "retrieved",
                                    "shape_xyz": [int(value) for value in patch.shape],
                                    "actual_voxel_size_mm_xyz": [float(value) for value in patch.header.get_zooms()[:3]],
                                })
                                if result["status"] == "retrieved":
                                    raw_nifti = nifti_bytes(patch)
                                    display_raw, display_mapping = section_display_array(patch)
                                    annotation, annotation_mapping = annotation_plane_from_image(patch, slice_index=display_mapping["slice_index"])
                                    descriptive_statistics = compute_patch_statistics(
                                        raw,
                                        preferred_y=display_mapping["slice_index"],
                                        declared_background_values=(255,),
                                    )
                                    metadata = {
                                        "status": "reference_space_placement_not_independently_reviewed",
                                        "section_id": selected_section_id,
                                        "section_number": selected_section_number,
                                        "section_name": selected_section_label,
                                        "provider_url": selected_catalogue["source_url"],
                                        "coordinate_space": "BigBrain microscopic template / documented registered-section reference space",
                                        "requested_bounds_mm": list(requested.__dict__.values()),
                                        "requested_resolution_mm": float(sampling_plan["requested_resolution_mm"]),
                                        "actual_shape_xyz": [int(value) for value in patch.shape],
                                        "actual_voxel_size_mm_xyz": [float(value) for value in patch.header.get_zooms()[:3]],
                                        "actual_affine": np.asarray(patch.affine).tolist(),
                                        "source_array_sha256": hashlib.sha256(raw.tobytes(order="C")).hexdigest(),
                                        "exported_nifti_sha256": sha256_bytes(raw_nifti),
                                        "sampling_plan": sampling_plan,
                                        "sampling_centre_xz_mm": [float(centre[0]), float(centre[1])],
                                        "annotation_png_mapping": annotation_mapping,
                                        "descriptive_patch_statistics": descriptive_statistics,
                                        "raw_values_preserved": True,
                                        "anatomical_review": "Not independently reviewed",
                                    }
                                    metadata.update(manual_patch_region_context(region_info))
                                    patch_id = patch_id_for(raw_nifti, metadata)
                                    marked_preview = rgb_with_crosshair(
                                        display_raw,
                                        display_raw.shape[1] // 2,
                                        display_raw.shape[0] // 2,
                                    )
                                    unmarked_png = png_bytes(annotation)
                                    collection_metadata = bind_unmarked_png_metadata(
                                        metadata, patch_id, unmarked_png, annotation.shape
                                    )
                                    add_entry(st.session_state.patch_collection, {
                                        "patch_id": patch_id,
                                        "user_label": f"sample-{selected_section_number}-{index + 1}",
                                        "user_note": "Generated by bounded rectangle sampling; not an anatomical-region label.",
                                        "metadata": collection_metadata,
                                        "raw_nifti": raw_nifti,
                                        "unmarked_png": unmarked_png,
                                        "marked_png": png_bytes(marked_preview),
                                    })
                                    result["patch_id"] = patch_id
                            except Exception as exc:
                                result.update({"status": "failed", "error": str(exc)})
                            results.append(result)
                    st.session_state.sampling_results = results
                    sampling_status.update(label="Sampling retrieval finished", state="complete")
                if st.session_state.get("sampling_results"):
                    st.dataframe(st.session_state.sampling_results, use_container_width=True, hide_index=True)

        registered_signature = (tuple(round(value, 6) for value in selected_section_world), float(registered_half_x), float(registered_half_z), float(registered_resolution))
        if st.session_state.get("volume_viewer_registered_signature") != registered_signature:
            st.session_state.pop("volume_viewer_registered_patch", None)
        if st.button("Fetch this selected detailed patch", type="primary", disabled=not (point_was_selected or reference_point_available), key="volume-viewer-fetch-registered"):
            try:
                with st.spinner(f"Fetching bounded registered section #{selected_section_number} patch…"):
                    detailed_patch, detailed_section, _ = fetch_crop(
                        requested_section_bounds, resolution_mm=registered_resolution,
                        max_bytes=MAX_BYTES, section_id=selected_section_id,
                    )
                raw_patch = np.asanyarray(detailed_patch.dataobj)
                if not has_intensity_variation(raw_patch):
                    st.session_state.pop("volume_viewer_registered_patch", None)
                    st.session_state.pop("volume_viewer_registered_signature", None)
                    st.error(
                        f"The provider returned a constant/background patch for section #{selected_section_number} "
                        f"(shape {tuple(raw_patch.shape)}, value {raw_patch.flat[0] if raw_patch.size else 'empty'}). "
                        "No detailed export was created. Click a tissue-containing area in the section overview and try again."
                    )
                    st.stop()
                st.session_state["volume_viewer_registered_signature"] = registered_signature
                st.session_state["volume_viewer_registered_patch"] = (detailed_patch, detailed_section, requested_section_bounds, section_point)
                st.session_state.setdefault("registered_fetch_verified_ids", set()).add(selected_section_id)
            except Exception as exc:
                st.error(f"Registered section #{selected_section_number} fetch failed: {exc}")

        registered_patch_state = st.session_state.get("volume_viewer_registered_patch")
        if registered_patch_state and st.session_state.get("volume_viewer_registered_signature") == registered_signature:
            detailed_patch, detailed_section, actual_bounds, selected_point = registered_patch_state
            detailed_display_raw, detailed_display_mapping = section_display_array(detailed_patch)
            patch_source = Image.fromarray(detailed_display_raw)
            annotation_plane, annotation_mapping = annotation_plane_from_image(
                detailed_patch, slice_index=detailed_display_mapping["slice_index"]
            )
            descriptive_statistics = compute_patch_statistics(
                np.asanyarray(detailed_patch.dataobj),
                preferred_y=detailed_display_mapping["slice_index"],
                declared_background_values=(255,),
            )
            detailed_zooms = [float(value) for value in detailed_patch.header.get_zooms()[:3]]
            detail_zoom = st.slider("Detailed patch display enlargement (visual only)", 1.0, 4.0, 2.0, 0.25, key="volume-viewer-detail-zoom")
            patch_display = np.asarray(patch_source.resize((max(1, round(patch_source.width * detail_zoom)), max(1, round(patch_source.height * detail_zoom))), Image.Resampling.NEAREST))
            patch_display = add_orientation_labels(
                # The image has been enlarged for display.  One displayed
                # pixel now represents native horizontal spacing / zoom;
                # using native spacing here would understate the bar length.
                add_scale_bar(patch_display, detailed_zooms[2] / detail_zoom),
                f"Registered detailed section #{selected_section_number} · raw values",
            )
            detailed_nifti = nifti_bytes(detailed_patch)
            detailed_metadata = {
                "status": "reference_space_placement_not_independently_reviewed",
                "section_label": f"#{selected_section_number}",
                "section_number": selected_section_number,
                "section_name": selected_section_label,
                "section_id": selected_section_id,
                "provider_url": selected_catalogue["source_url"],
                "coordinate_space": "BigBrain microscopic template / documented registered-section reference space",
                "section_plane": {
                    "centre_y_mm": section_y,
                    "min_y_mm": float(section_bbox.minpoint[1]),
                    "max_y_mm": float(section_bbox.maxpoint[1]),
                },
                "selected_location": selected_point,
                "section_plane_probe_centres": {
                    "mri": mri_section_center.tolist(),
                    "histology_200um": hist_section_center.tolist(),
                    "description": "nearest voxel centres at the documented section-plane probe, retained for provenance",
                },
                "selected_patch_world_point": {
                    "requested_world_xyz_mm": [float(value) for value in selected_point["world_xyz_mm"]],
                    "mri_voxel_index_xyz": np.asarray(nearest_voxel_for_world(mri, np.asarray(selected_point["world_xyz_mm"]))[0], dtype=int).tolist(),
                    "mri_voxel_centre_mm": nearest_voxel_for_world(mri, np.asarray(selected_point["world_xyz_mm"]))[1].tolist(),
                    "histology_200um_voxel_index_xyz": np.asarray(nearest_voxel_for_world(hist, np.asarray(selected_point["world_xyz_mm"]))[0], dtype=int).tolist(),
                    "histology_200um_voxel_centre_mm": nearest_voxel_for_world(hist, np.asarray(selected_point["world_xyz_mm"]))[1].tolist(),
                    "detailed_section_first_voxel_centre_mm": np.asarray(detailed_patch.affine[:3, 3], dtype=float).tolist(),
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
                    "display": detailed_display_mapping,
                    "annotation_png": annotation_mapping,
                },
                "annotation_png_mapping": annotation_mapping,
                "descriptive_patch_statistics": descriptive_statistics,
                "raw_values_preserved": True,
                "source_array_sha256": hashlib.sha256(np.asanyarray(detailed_patch.dataobj).tobytes(order="C")).hexdigest(),
                "exported_nifti_sha256": sha256_bytes(detailed_nifti),
                "anatomical_review": "Not independently reviewed; reference-space placement does not establish exact MRI correspondence.",
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            detailed_metadata.update(manual_patch_region_context(region_info))
            st.markdown("## 5. Review and export the detailed patch")
            st.success(f"Bounded real-data patch retrieved from the registered #{selected_section_number} provider.")
            st.markdown(
                f"**Actual returned pixel size: {detailed_patch.shape[2]} × {detailed_patch.shape[0]} pixels (horizontal Z × vertical X)**  "
                f"\n**Native display spacing: {detailed_zooms[2]:g} × {detailed_zooms[0]:g} mm (horizontal × vertical)**"
            )
            st.caption("Display enlargement changes only the visualization size. It does not fetch finer data. The exported NIfTI remains at the provider's actual native resolution.")
            st.write({
                "requested_bounds_mm": list(actual_bounds.__dict__.values()),
                "requested_resolution_mm": float(registered_resolution),
                "actual_shape_xyz": [int(value) for value in detailed_patch.shape],
                "actual_voxel_size_mm_xyz": detailed_zooms,
                "provider_plane_index_y": detailed_display_mapping["slice_index"],
                "raw_range": detailed_display_mapping["raw_range"],
                "estimated_uncompressed_bytes": int(np.asanyarray(detailed_patch.dataobj).nbytes),
            })
            st.image(patch_display, caption=f"Registered detailed section #{selected_section_number} — actual returned resolution {detailed_zooms} mm; visualization contrast only", use_container_width=True)
            collection_patch_id = patch_id_for(detailed_nifti, detailed_metadata)
            review_decision, review_reason = "Not recorded", ""
            with st.expander("Optional · descriptive intensity statistics", expanded=False):
                st.caption(
                    "Computed from the raw scientific data plane, excluding declared provider padding value 255. "
                    "These descriptions are not tissue-quality or anatomical verdicts and do not discard patches."
                )
                st.write(descriptive_statistics)
                review_decision = st.selectbox(
                    "Your review decision",
                    ["Not recorded", "Keep", "Exclude"],
                    key=f"patch-review-decision-{collection_patch_id}",
                )
                review_reason = st.text_area(
                    "Your reason (optional)",
                    key=f"patch-review-reason-{collection_patch_id}",
                    help="Record your own decision; this is not an automatic tissue or anatomy classification.",
                )
            detailed_metadata["user_review"] = {
                "decision": review_decision,
                "reason": review_reason,
                "interpretation": "user-provided note; not an automatic quality or anatomical label",
            }
            registered_package = {"raw_nifti": detailed_nifti, "patch_png": png_bytes(patch_display), "footprint_png": png_bytes(hist_footprint), "metadata": detailed_metadata}
            st.download_button("Download registered MRI → section patch package", registered_patch_report_bytes(registered_package), f"registered_section_{selected_section_number}_patch.zip", "application/zip", key="volume-viewer-download-registered")
            st.markdown("### Add this patch to your collection")
            st.caption(
                f"Patch ID {collection_patch_id} · collection uses up to {COLLECTION_MAX_BYTES / (1024 * 1024):g} MiB in this browser session. "
                "Changing sections does not remove saved entries; refreshing the browser does."
            )
            collection_label = st.text_input("Patch label", value=f"section-{selected_section_number}", key=f"collection-label-{collection_patch_id}")
            collection_note = st.text_area("Patch note (optional; not an anatomical label)", value="", key=f"collection-note-{collection_patch_id}")
            if st.button("Add patch to collection", key=f"collection-add-{collection_patch_id}"):
                unmarked_png = png_bytes(annotation_plane)
                collection_entry = {
                    "patch_id": collection_patch_id,
                    "user_label": collection_label.strip() or collection_patch_id,
                    "user_note": collection_note,
                    "metadata": bind_unmarked_png_metadata(
                        detailed_metadata, collection_patch_id, unmarked_png, annotation_plane.shape
                    ),
                    "raw_nifti": detailed_nifti,
                    "unmarked_png": unmarked_png,
                    "marked_png": png_bytes(patch_display),
                }
                try:
                    add_entry(st.session_state.patch_collection, collection_entry)
                    st.success(f"Added {collection_patch_id} to the collection.")
                except ValueError as exc:
                    st.warning(str(exc))
        else:
            st.info("No detailed patch fetched yet. Choose a section, click tissue in the fitted section image, then click ‘Fetch this selected detailed patch’. ")
    except Exception as exc:
        st.error(f"Registered section #{selected_section_number} {registered_display_stage} failed: {exc}")

st.markdown("## Patch collection")
collection_current_patch_ready = bool(st.session_state.get("volume_viewer_registered_patch"))
if not collection_current_patch_ready:
    st.button(
        "Add patch to collection",
        disabled=True,
        key="collection-add-disabled",
        help="Fetch a detailed patch successfully first; then this button becomes available below its preview.",
    )
    st.caption("Fetch a detailed patch first. The Add button will appear directly below its preview.")
if st.session_state.patch_collection:
    total_collection_bytes = collection_bytes(st.session_state.patch_collection)
    st.caption(
        f"{len(st.session_state.patch_collection)} saved patch(es) · {total_collection_bytes / (1024 * 1024):.2f} MiB of "
        f"{COLLECTION_MAX_BYTES / (1024 * 1024):g} MiB session budget. Saved entries are separate from the current selection."
    )
    for patch_id, entry in list(st.session_state.patch_collection.items()):
        metadata = entry["metadata"]
        label = entry.get("user_label") or patch_id
        with st.expander(f"{label} · {metadata.get('section_label', metadata.get('section_number', 'section'))}", expanded=False):
            preview_col, detail_col = st.columns([1, 2])
            with preview_col:
                st.image(entry["unmarked_png"], caption="Unmarked annotation plane", use_container_width=True)
            with detail_col:
                st.write({
                    "patch_id": patch_id,
                    "section_id": metadata.get("section_id"),
                    "physical_bounds_mm": metadata.get("requested_bounds_mm"),
                    "actual_shape_xyz": metadata.get("actual_shape_xyz"),
                    "actual_voxel_size_mm_xyz": metadata.get("actual_voxel_size_mm_xyz"),
                    "note": entry.get("user_note", ""),
                })
                if st.button("Remove this patch", key=f"collection-remove-{patch_id}"):
                    st.session_state.patch_collection.pop(patch_id, None)
                    st.rerun()
else:
    st.info("No patches saved yet. Fetch a detailed tissue patch, then choose ‘Add patch to collection’.")

with st.expander("Advanced · import native Labelme polygon", expanded=False):
    st.caption(
        "This optional path accepts native Labelme polygon JSON for one exact collection patch. "
        "Upload the JSON, that patch's metadata.json, and the unchanged unmarked PNG. "
        "The selected patch ID, PNG checksum, dimensions and mapping must all match."
    )
    if not st.session_state.patch_collection:
        st.info("Fetch and add a detailed patch to the collection before importing a polygon.")
    else:
        import_patch_id = st.selectbox(
            "Collection patch to annotate",
            list(st.session_state.patch_collection),
            format_func=lambda patch_id: f"{patch_id} · section {st.session_state.patch_collection[patch_id]['metadata'].get('section_number', '?')}",
            key="labelme-import-patch-id",
        )
        import_entry = st.session_state.patch_collection[import_patch_id]
        import_metadata = import_entry["metadata"]
        st.caption(
            f"Expected PNG: {import_metadata.get('unmarked_png_filename', 'metadata field missing')} · "
            f"checksum: {str(import_metadata.get('unmarked_png_sha256', 'missing'))[:16]}…"
        )
        labelme_json_upload = st.file_uploader("Native Labelme polygon JSON", type=["json"], key="labelme-native-json")
        labelme_mapping_upload = st.file_uploader("Matching collection metadata.json", type=["json"], key="labelme-native-metadata")
        labelme_png_upload = st.file_uploader("Exact unmarked collection PNG", type=["png"], key="labelme-native-png")
        if labelme_json_upload and labelme_mapping_upload and labelme_png_upload:
            import_signature = (
                import_patch_id,
                hashlib.sha256(labelme_json_upload.getvalue()).hexdigest(),
                hashlib.sha256(labelme_mapping_upload.getvalue()).hexdigest(),
                hashlib.sha256(labelme_png_upload.getvalue()).hexdigest(),
            )
            if st.session_state.get("native_labelme_import_signature") != import_signature:
                st.session_state.pop("native_labelme_import", None)
                st.session_state.pop("native_labelme_import_error", None)
                st.session_state.native_labelme_import_signature = import_signature
                try:
                    validated_import = validate_labelme_annotation(
                        labelme_json_upload.getvalue(),
                        labelme_mapping_upload.getvalue(),
                        labelme_png_upload.getvalue(),
                        image_filename=labelme_png_upload.name,
                        expected_section_id=str(import_metadata.get("section_id")),
                        expected_source_url=str(import_metadata.get("provider_url")),
                        expected_coordinate_space=str(import_metadata.get("coordinate_space")),
                        expected_patch_id=import_patch_id,
                    )
                    st.session_state.native_labelme_import = validated_import
                except ValueError as exc:
                    st.session_state.native_labelme_import_error = str(exc)
            if st.session_state.get("native_labelme_import_error"):
                st.error(f"Labelme annotation rejected: {st.session_state.native_labelme_import_error}")
            imported = st.session_state.get("native_labelme_import")
            if imported:
                st.success("Polygon accepted for this exact collection patch; user labels are preserved, not interpreted anatomically.")
                original = imported["image"].convert("L")
                overlay = original.convert("RGB")
                draw = ImageDraw.Draw(overlay)
                for polygon in imported["polygons"]:
                    points = [tuple(point) for point in polygon["pixel_vertices_xy"]]
                    draw.polygon(points, outline=(255, 0, 0), width=2)
                    if points and polygon["label"]:
                        draw.text(points[0], polygon["label"], fill=(255, 0, 0))
                st.write({
                    "patch_id": imported["patch_id"],
                    "section_id": imported["section_id"],
                    "annotated_y_plane_index": imported["plane_index"],
                    "polygon_count": len(imported["polygons"]),
                    "pixel_to_nifti": "(u,v) -> (i_x=u, i_y=selected_y, i_z=v)",
                    "external_tool_round_trip": "not yet independently verified",
                })
                image_col, overlay_col = st.columns(2)
                with image_col:
                    st.image(original, caption="Original unmarked PNG — unchanged", use_container_width=True)
                with overlay_col:
                    st.image(overlay, caption="Imported polygon overlay — display only", use_container_width=True)
                st.download_button(
                    "Download polygon + labelled mask package",
                    data=build_import_package(imported),
                    file_name=f"{import_patch_id}_labelme_polygon_import.zip",
                    mime="application/zip",
                    key=f"labelme-import-download-{import_patch_id}",
                )
                st.download_button(
                    "Export COCO instance-segmentation package",
                    data=build_coco_package(imported, import_entry["raw_nifti"], import_metadata),
                    file_name=f"{import_patch_id}_labelme_coco.zip",
                    mime="application/zip",
                    key=f"labelme-coco-download-{import_patch_id}",
                    help="COCO stores pixel polygons only; the package also includes the canonical NIfTI and TissueLink metadata.",
                )

with st.expander("Reopen or re-fetch a collection", expanded=False):
    st.caption(
        "Upload a TissueLink collection ZIP to inspect it locally. Reopen never fetches data. "
        "Re-fetch uses only recorded registered-section IDs and bounded parameters; imported URLs, labels and notes are treated as untrusted metadata."
    )
    replay_upload = st.file_uploader(
        "Collection ZIP",
        type=["zip"],
        key="collection-replay-upload",
        help="Existing pre-manifest exports are read through a compatibility adapter.",
    )
    if replay_upload is not None:
        replay_bytes = replay_upload.getvalue()
        if st.button("Reopen collection (inspect only)", key="collection-reopen"):
            try:
                st.session_state.collection_reopen_report = reopen_collection(replay_bytes)
                st.session_state.pop("collection_replay_report", None)
            except ValueError as exc:
                st.error(f"Collection could not be reopened: {exc}")
        reopened = st.session_state.get("collection_reopen_report")
        if reopened:
            st.write({
                "manifest_version": reopened["manifest"].get("schema_version"),
                "compatibility_adapter_used": reopened["legacy_adapter"],
                "patch_count": len(reopened["manifest"].get("patches", [])),
                "member_count": reopened["member_count"],
            })
            st.dataframe(reopened["reports"], use_container_width=True, hide_index=True)
            patches = reopened["manifest"].get("patches", [])
            estimate = sum(int(p.get("request_budget_bytes", MAX_BYTES)) for p in patches)
            st.info(
                f"Estimated re-fetch work: {len(patches)} bounded request(s), up to {estimate / (1024 * 1024):.2f} MiB. "
                "No request is made until you click Re-fetch collection."
            )
            if st.button("Re-fetch collection", type="primary", key="collection-refetch"):
                progress = st.progress(0, text="Starting bounded replay…")
                try:
                    reports = replay_collection(
                        reopened["manifest"],
                        fetch_crop,
                        progress=lambda current, total: progress.progress(current / max(total, 1), text=f"Re-fetched {current}/{total} patch(es)"),
                    )
                    st.session_state.collection_replay_report = reports
                except ValueError as exc:
                    st.error(f"Collection replay was rejected: {exc}")
                finally:
                    progress.empty()
            if st.session_state.get("collection_replay_report"):
                st.markdown("#### Replay results")
                st.dataframe(st.session_state.collection_replay_report, use_container_width=True, hide_index=True)

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
        st.session_state.pending_location = {"x": point[0], "y": point[1], "z": point[2]}
        st.session_state.last_location_click = None
        st.rerun()
    with st.expander("Saved metadata JSON", expanded=False):
        st.json(saved["metadata"])
    st.download_button("Export location report (ZIP)", data=location_report_bytes(saved), file_name=f"{saved_name}_location_report.zip", mime="application/zip")

st.info("Independent corresponding-point checks, arrow discrepancies, and the 8–10-landmark validation table are on the separate Validation page. This main page answers one question: what is at this shared reference-space location?")

render_collection_review("manual")
