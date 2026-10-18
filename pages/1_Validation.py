"""Independent point-pair review; deliberately separate from the main explorer."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw

from volume_alignment import (
    _display_uint8,
    _sample_plane,
    common_world_bounds,
    display_pixel_to_world,
    load_volume,
    volume_metadata,
    VolumeSpec,
)


def rgb_with_crosshair(view: np.ndarray, u: int, v: int) -> np.ndarray:
    result = np.repeat(view[..., None], 3, axis=2).astype(np.uint8)
    if 0 <= u < result.shape[1]:
        result[:, u] = (255, 255, 0)
    if 0 <= v < result.shape[0]:
        result[v, :] = (255, 255, 0)
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
    draw.text((result.width - 24, 26), "R", fill=(255, 255, 0))
    draw.text((8, 26), "L", fill=(255, 255, 0))
    draw.text((result.width - 24, result.height - 35), "S", fill=(255, 255, 0))
    draw.text((8, result.height - 35), "I", fill=(255, 255, 0))
    return np.asarray(result)


ROOT = Path(__file__).resolve().parents[1]
MRI = VolumeSpec("donor MRI", ROOT / "outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz")
HIST = VolumeSpec("native histology", ROOT / "outputs/spatial_feasibility/full8_200um_optbal.nii.gz")

st.set_page_config(page_title="BigBrain TissueLink — Alignment review", layout="wide")
st.title("BigBrain TissueLink")
st.caption("Alignment review · advanced")
st.caption("Advanced validation page — independent MRI/histology point pairs")
st.warning(
    "Validation only. This page records independently selected points; it does not estimate registration accuracy, "
    "create a registration, or connect high-resolution sections."
)
st.info(
    "How to read this: a click selects a displayed world coordinate; the magenta MRI box is a sampling voxel, "
    "not an uncertainty radius; a saved discrepancy is a coordinate-test measurement, not anatomical accuracy."
)

if not MRI.path.exists() or not HIST.path.exists():
    st.error("The local feasibility volumes are missing.")
    st.stop()

mri = load_volume(MRI)
hist = load_volume(HIST)
common = common_world_bounds([mri, hist])
st.caption(
    "Transform/template: official final histological processing-space world coordinates; single donor; "
    "MRI native voxel size %.3f mm, reconstructed histology native voxel size %.3f mm. "
    "Expected registration error: unavailable."
    % (mri.header.get_zooms()[0], hist.header.get_zooms()[0])
)

names = [
    "P1 superior", "P2 central", "P3 lateral", "P4 left", "P5 right",
    "P6 inferior", "P7 anterior", "P8 posterior", "P9 deep", "P10 edge",
]
defaults = {
    "P1 superior": [0.0, -25.7922, 45.0], "P2 central": [0.0, -25.7922, 0.0],
    "P3 lateral": [-32.0, -25.7922, -12.0], "P4 left": [-45.0, -25.7922, 20.0],
    "P5 right": [45.0, -25.7922, 20.0], "P6 inferior": [0.0, -25.7922, -35.0],
    "P7 anterior": [0.0, -10.0, 10.0], "P8 posterior": [0.0, -45.0, 10.0],
    "P9 deep": [12.0, -25.7922, -8.0], "P10 edge": [-55.0, -25.7922, 35.0],
}
if "validation_pairs" not in st.session_state:
    st.session_state.validation_pairs = {}
if "validation_pending" not in st.session_state:
    st.session_state.validation_pending = {}

name = st.selectbox("Landmark candidate", names)
world_y = st.slider("Shared world Y slice (mm)", float(common["min"][1]), float(common["max"][1]), -25.7922, 0.2)
step = st.select_slider("Display spacing", options=[0.2, 0.4, 0.8], value=0.4, format_func=lambda x: f"{x:.1f} mm/pixel")
low, high = st.slider("Display contrast (visualization only)", 0.0, 100.0, (1.0, 99.0), 0.5)
x_axis = np.arange(common["min"][0], common["max"][0] + step * 0.5, step)
z_axis = np.arange(common["min"][2], common["max"][2] + step * 0.5, step)
mri_plane, _ = _sample_plane(mri, world_y, x_axis, z_axis)
hist_plane, _ = _sample_plane(hist, world_y, x_axis, z_axis)
mri_view = _display_uint8(mri_plane, low, high)
hist_view = _display_uint8(hist_plane, low, high)

active = st.radio("Select independently in", ["MRI", "Histology"], horizontal=True)
existing = st.session_state.validation_pairs.get(name, {})
pending = st.session_state.validation_pending.get((name, active.lower()))
point = existing.get(active.lower()) or pending
if point is None:
    d = defaults[name]
    point = [float(d[0]), float(world_y), float(d[2])]
u = int(np.clip(round((point[0] - x_axis[0]) / step), 0, len(x_axis) - 1))
v = int(np.clip(round((point[2] - z_axis[0]) / step), 0, len(z_axis) - 1))

left, right = st.columns(2)
with left:
    st.markdown("### Reference MRI")
    st.caption("RAS: L/R in-plane, I/S in-plane; A/P is the shared Y slice")
    st.image(add_orientation_labels(add_scale_bar(rgb_with_crosshair(mri_view, u, v), step), "MRI · visual report"), use_container_width=True)
with right:
    st.markdown("### Reconstructed histology — 200 µm")
    st.caption("RAS: L/R in-plane, I/S in-plane; A/P is the shared Y slice")
    st.image(add_orientation_labels(add_scale_bar(rgb_with_crosshair(hist_view, u, v), step), "Histology · visual report"), use_container_width=True)

clicked = streamlit_image_coordinates(mri_view if active == "MRI" else hist_view, width=int(mri_view.shape[1]), key=f"validation_picker_{active}_{name}")
if clicked:
    _, selected = display_pixel_to_world(x_axis, z_axis, world_y, (clicked["x"], clicked["y"]))
    st.session_state.validation_pending[(name, active.lower())] = selected
    st.rerun()

if pending is None and active.lower() not in existing:
    st.info(f"Click the {active} image to create an independent point. The displayed candidate is only a navigation default.")
st.write(f"Selected {active} point: X={point[0]:.2f}, Y={point[1]:.2f}, Z={point[2]:.2f} mm")
reviewer = st.text_input("Reviewer", value="")
observation = st.text_input("Observation", value="")
save_allowed = active.lower() in existing or pending is not None
if st.button(f"Save {active} point", disabled=not save_allowed):
    item = dict(st.session_state.validation_pairs.get(name, {}))
    item[active.lower()] = [float(value) for value in point]
    item["reviewer"] = reviewer
    item["observation"] = observation
    item["status"] = "Unreviewed" if not ("mri" in item and "histology" in item) else "Reviewed by independent point selection"
    st.session_state.validation_pairs[name] = item
    st.success(f"Saved the {active} point independently. The other modality was not auto-filled.")

saved = st.session_state.validation_pairs.get(name, {})
if "mri" in saved and "histology" in saved:
    delta = np.asarray(saved["mri"], dtype=float) - np.asarray(saved["histology"], dtype=float)
    distance = float(np.linalg.norm(delta))
    st.metric("Landmark discrepancy", f"{distance:.1f} mm", help="Rounded for display; not a whole-brain accuracy score.")
    st.caption("Arrow/discrepancy is the difference between two independently selected points; it is not a registration residual.")
else:
    st.caption("Unreviewed: select and save one point in each modality before computing a discrepancy.")

rows = []
distances = []
for candidate in names:
    item = st.session_state.validation_pairs.get(candidate, {})
    distance = None
    if "mri" in item and "histology" in item:
        distance = float(np.linalg.norm(np.asarray(item["mri"]) - np.asarray(item["histology"])))
        distances.append(distance)
    rows.append({"landmark": candidate, "discrepancy_mm": "—" if distance is None else f"{distance:.1f}", "status": item.get("status", "Unreviewed"), "reviewer": item.get("reviewer", "")})
st.subheader("Landmark review table")
st.dataframe(rows, use_container_width=True, hide_index=True)
if distances:
    st.caption(f"Coordinate-test distribution only: median {np.median(distances):.1f} mm; range {min(distances):.1f}–{max(distances):.1f} mm. Not anatomical accuracy.")
else:
    st.caption("No independently reviewed pairs saved yet; all candidates remain Unreviewed.")

export = {
    "status": "independent_point_pair_review",
    "transform": "official final histological processing-space world coordinates",
    "source_identities": {"mri": str(MRI.path), "histology": str(HIST.path)},
    "orientation": {"mri": volume_metadata(mri)["orientation"], "histology": volume_metadata(hist)["orientation"]},
    "pairs": st.session_state.validation_pairs,
    "interpretation": "Numerical discrepancies are coordinate-test measurements, not anatomical accuracy or registration uncertainty.",
}
st.download_button("Export landmark review JSON", json.dumps(export, indent=2) + "\n", "landmark_review.json", "application/json")
