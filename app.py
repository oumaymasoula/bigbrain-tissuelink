"""Streamlit interface for metadata-first BigBrain cutouts."""
import hashlib
import json
from io import BytesIO
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas
from labelme_import import build_import_export, map_physical_polygon_to_view, validate_labelme_annotation
from polygon_annotations import (
    append_polygon_files_to_bundle,
    build_polygon_export,
    map_crop_polygon_to_source,
    polygon_objects,
)

from bigbrain_cutout import (
    Bounds,
    DEFAULT_BOUNDS,
    MAX_BYTES,
    available_sections,
    display_plane,
    export_crop,
    fetch_crop,
    map_preview_rect_to_source,
    map_source_bounds_to_preview_rect,
)

OVERVIEW_RESOLUTION_MM = 0.128
OVERVIEW_MAX_BYTES = 5 * 1024 * 1024
DISPLAY_MAX_PX = 900

st.set_page_config(page_title="BigBrain TissueLink — Legacy Cutout", layout="wide")
st.title("BigBrain TissueLink — Legacy Cutout")
st.caption("Public BigBrain histology retrieval — not patient MRI and not a clinical tool.")

workflow = st.selectbox(
    "Workflow",
    ["Retrieve a detailed section crop", "Explore registered detailed section #3458"],
    key="workflow",
)
if workflow == "Explore registered detailed section #3458":
    from registered_section_demo import render_registered_demo

    render_registered_demo()
    st.stop()


@st.cache_data(show_spinner=False)
def load_section_catalog():
    return available_sections()


@st.cache_data(show_spinner=False)
def load_overview(section_id: str):
    info = next(item for item in load_section_catalog() if item["id"] == section_id)
    b = info["bounds_mm"]
    bounds = Bounds(b["min_x"], b["min_y"], b["min_z"], b["max_x"], b["max_y"], b["max_z"])
    image, _, _ = fetch_crop(bounds, resolution_mm=OVERVIEW_RESOLUTION_MM, max_bytes=OVERVIEW_MAX_BYTES, section_id=section_id)
    plane, slice_index, raw_range = display_plane(image)
    return plane, image.affine.copy(), image.shape, image.header.get_zooms()[:3], slice_index, raw_range


def section_bounds(info):
    b = info["bounds_mm"]
    if info["label"].startswith("#3458"):
        return Bounds(*DEFAULT_BOUNDS)
    return Bounds(-2.0, b["min_y"], -2.0, 0.0, b["max_y"], 0.0)


def source_bounds_tuple(bounds: Bounds):
    return tuple(float(value) for value in bounds.__dict__.values())


def make_drawing(rect):
    if not rect or rect["width"] <= 0 or rect["height"] <= 0:
        return None
    return {
        "version": "5.3.0",
        "objects": [{
            "type": "Rect",
            "left": float(rect["left"]),
            "top": float(rect["top"]),
            "width": float(rect["width"]),
            "height": float(rect["height"]),
            "scaleX": 1.0,
            "scaleY": 1.0,
            "originX": "left",
            "originY": "top",
            "fill": "rgba(255, 0, 0, 0.12)",
            "stroke": "#ff0000",
            "strokeWidth": 2,
        }],
        "background": "",
    }


def rect_signature(rect):
    if not rect:
        return None
    return tuple(round(float(rect[key]), 6) for key in ("left", "top", "width", "height"))


def view_geometry(full_size, zoom, pan_x, pan_y):
    full_width, full_height = full_size
    window_width = max(1.0, full_width / zoom)
    window_height = max(1.0, full_height / zoom)
    available_x = full_width - window_width
    available_y = full_height - window_height
    origin_x = (full_width - window_width) / 2.0 + float(pan_x) / 100.0 * available_x / 2.0
    origin_y = (full_height - window_height) / 2.0 + float(pan_y) / 100.0 * available_y / 2.0
    return (origin_x, origin_y), (window_width, window_height)


try:
    catalog = load_section_catalog()
except Exception as exc:
    st.error(f"Could not load public section metadata: {exc}")
    st.stop()

labels = [item["label"] for item in catalog]
default_index = next((index for index, label in enumerate(labels) if label.startswith("#3458")), 0)
selected_label = st.selectbox("1. Choose section", labels, index=default_index)
selected = catalog[labels.index(selected_label)]
section_id = selected["id"]

if st.session_state.get("section_id") != section_id:
    st.session_state["section_id"] = section_id
    for key in (
        "crop", "crop_signature", "confirmed_signature", "confirm_crop",
        "selection_bounds", "numeric_signature", "mapped_signature",
        "last_canvas_signature", "labelme_import", "labelme_import_signature",
        "labelme_import_error", "polygon_canvas", "polygon_labels",
        "polygon_export", "polygon_export_signature",
    ):
        st.session_state.pop(key, None)
    st.session_state["view_reset_token"] = st.session_state.get("view_reset_token", 0) + 1

with st.expander("Section metadata", expanded=True):
    st.write({
        "identifier": section_id,
        "source": selected["source_url"],
        "coordinate_space": "BigBrain microscopic template (histology)",
        "bounds_mm": selected["bounds_mm"],
        "supported_voxel_sizes_mm": [item["voxel_size_mm"] for item in selected["resolutions"]],
        "metadata_only": "yes — image data is not downloaded for this catalog",
    })

try:
    overview, overview_affine, overview_shape, overview_zooms, overview_slice, overview_range = load_overview(section_id)
except Exception as exc:
    st.error(f"Overview download failed for this section: {exc}")
    st.stop()

full_display_width = min(DISPLAY_MAX_PX, overview.shape[1])
full_display_height = max(1, round(overview.shape[0] * full_display_width / overview.shape[1]))
overview_image = Image.fromarray(overview.T).resize((full_display_width, full_display_height), Image.Resampling.NEAREST)
st.caption(
    f"Overview: requested {OVERVIEW_RESOLUTION_MM:g} mm; actual voxel size "
    f"{[float(x) for x in overview_zooms[:3]]} mm; y-slice {overview_slice}; "
    f"raw range {overview_range}; display {full_display_width}×{full_display_height}px. "
    f"Budget: {OVERVIEW_MAX_BYTES:,} bytes."
)

st.subheader("2. Select area")
st.caption("The rectangle is mapped from displayed pixels through the overview affine into source x/z bounds. Zoom and pan are view controls only; they do not change the selected physical bounds.")
reset_view = st.button("Reset view", key=f"reset-view-{section_id}")
view_reset_token = st.session_state.get("view_reset_token", 0)
if reset_view:
    st.session_state["view_reset_token"] = view_reset_token + 1
    st.rerun()
view_controls = st.columns(3)
with view_controls[0]:
    zoom = st.slider("Overview zoom", 1.0, 4.0, 1.0, 0.25, key=f"view_zoom-{view_reset_token}")
with view_controls[1]:
    pan_x = st.slider("Pan horizontal (%)", -100, 100, 0, 5, key=f"view_pan_x-{view_reset_token}")
with view_controls[2]:
    pan_y = st.slider("Pan vertical (%)", -100, 100, 0, 5, key=f"view_pan_y-{view_reset_token}")

view_origin, view_size = view_geometry((full_display_width, full_display_height), zoom, pan_x, pan_y)
view_box = (
    round(view_origin[0]),
    round(view_origin[1]),
    round(view_origin[0] + view_size[0]),
    round(view_origin[1] + view_size[1]),
)
view_image_raw = overview_image.crop(view_box)
display_width = min(DISPLAY_MAX_PX, view_image_raw.width)
display_height = max(1, round(view_image_raw.height * display_width / view_image_raw.width))
view_image = view_image_raw.resize((display_width, display_height), Image.Resampling.NEAREST)

if "selection_bounds" not in st.session_state:
    st.session_state["selection_bounds"] = source_bounds_tuple(section_bounds(selected))
selection_values = st.session_state["selection_bounds"]
initial_rect = map_source_bounds_to_preview_rect(
    (selection_values[0], selection_values[2], selection_values[3], selection_values[5]),
    overview_affine,
    overview_shape,
    (full_display_width, full_display_height),
    view_origin=view_origin,
    view_size=view_size,
    canvas_size=(display_width, display_height),
)
if st.session_state.get("last_canvas_signature") is None:
    st.session_state["last_canvas_signature"] = rect_signature(initial_rect)
canvas = st_canvas(
    fill_color="rgba(255, 0, 0, 0.12)",
    stroke_width=2,
    stroke_color="#ff0000",
    background_image=view_image,
    update_streamlit=True,
    height=display_height,
    width=display_width,
    drawing_mode="rect",
    initial_drawing=make_drawing(initial_rect),
    key=f"canvas-{section_id}",
)

if canvas.json_data is not None and not canvas.json_data.get("objects"):
    st.session_state.pop("selection_bounds", None)
    st.session_state.pop("mapped_signature", None)
    selection_values = source_bounds_tuple(section_bounds(selected))
else:
    objects = [obj for obj in (canvas.json_data or {}).get("objects", []) if str(obj.get("type", "")).lower() == "rect"]
    if objects:
        obj = objects[-1]
        rect = {
            "left": float(obj["left"]),
            "top": float(obj["top"]),
            "width": float(obj.get("width", 0) * obj.get("scaleX", 1)),
            "height": float(obj.get("height", 0) * obj.get("scaleY", 1)),
        }
        raw_signature = rect_signature(rect)
        if raw_signature != st.session_state.get("last_canvas_signature"):
            mapped = map_preview_rect_to_source(
                rect,
                overview_affine,
                overview_shape,
                (full_display_width, full_display_height),
                view_origin=view_origin,
                view_size=view_size,
                canvas_size=(display_width, display_height),
            )
            selection_values = (
                mapped[0], selected["bounds_mm"]["min_y"], mapped[1],
                mapped[2], selected["bounds_mm"]["max_y"], mapped[3],
            )
            st.session_state["selection_bounds"] = selection_values
            st.session_state["mapped_signature"] = tuple(round(float(value), 9) for value in selection_values)
            st.session_state["last_canvas_signature"] = raw_signature

selection_values = tuple(float(value) for value in selection_values)
selection_rect = map_source_bounds_to_preview_rect(
    (selection_values[0], selection_values[2], selection_values[3], selection_values[5]),
    overview_affine,
    overview_shape,
    (full_display_width, full_display_height),
    view_origin=view_origin,
    view_size=view_size,
    canvas_size=(display_width, display_height),
)
st.info(
    f"Selected source bounds: x=[{selection_values[0]:.6f}, {selection_values[3]:.6f}] mm; "
    f"y=[{selection_values[1]:.6f}, {selection_values[4]:.6f}] mm; "
    f"z=[{selection_values[2]:.6f}, {selection_values[5]:.6f}] mm. "
    f"Displayed rectangle: {selection_rect['width']:.1f}×{selection_rect['height']:.1f} px."
)

with st.expander("Advanced: numeric source bounds", expanded=False):
    numeric = st.columns(6)
    bound_labels = ["min x", "min y", "min z", "max x", "max y", "max z"]
    widget_signature = tuple(round(value, 9) for value in selection_values)
    if st.session_state.get("numeric_signature") != widget_signature:
        for index, value in enumerate(selection_values):
            st.session_state[f"advanced-{section_id}-{bound_labels[index]}"] = value
        st.session_state["numeric_signature"] = widget_signature
    numeric_vals = tuple(
        float(numeric[i].number_input(bound_labels[i], format="%.6f", key=f"advanced-{section_id}-{bound_labels[i]}"))
        for i in range(6)
    )

if numeric_vals != selection_values:
    st.session_state["selection_bounds"] = numeric_vals
    st.session_state["numeric_signature"] = tuple(round(value, 9) for value in numeric_vals)
    st.rerun()

st.subheader("3. Preview crop")
resolution = st.selectbox("Requested resolution (mm)", [0.01, 0.1], index=0, key=f"resolution-{section_id}")
coarse_resolution = resolution > 0.01
if coarse_resolution:
    st.warning("This is coarser than the validated 0.01 mm request. The provider's returned voxel size will be shown after retrieval.")
    accept_coarse = st.checkbox(
        "I explicitly accept retrieving a coarser resolution for this preview",
        key=f"accept-coarse-{section_id}",
    )
else:
    accept_coarse = True
current_signature = (section_id, *numeric_vals, resolution)
if "crop" in st.session_state and st.session_state.get("crop_signature") != current_signature:
    st.session_state.pop("crop", None)
    st.session_state.pop("polygon_canvas", None)
    st.session_state.pop("polygon_labels", None)
    st.session_state.pop("polygon_export", None)
    st.session_state.pop("polygon_export_signature", None)
    st.session_state["confirmed_signature"] = None
    st.session_state["confirm_crop"] = False
    st.warning("Selection parameters changed; the previous preview and export confirmation were invalidated.")

if st.button("Preview exact selected area", type="primary", disabled=not accept_coarse):
    try:
        requested = Bounds(*numeric_vals)
        requested.validate()
        with st.spinner("Fetching bounded crop…"):
            image, section, _ = fetch_crop(requested, resolution_mm=resolution, max_bytes=MAX_BYTES, section_id=section_id)
        st.session_state["crop"] = (image, section, requested, resolution)
        st.session_state["crop_signature"] = current_signature
        st.session_state["confirmed_signature"] = None
        st.session_state["confirm_crop"] = False
        st.rerun()
    except Exception as exc:
        st.error(f"Crop failed for this section: {exc}. No other section will be substituted.")

if "crop" in st.session_state and st.session_state.get("crop_signature") == current_signature:
    image, section, requested, actual_resolution = st.session_state["crop"]
    crop_plane, crop_slice, crop_range = display_plane(image)
    actual_zooms = [float(x) for x in image.header.get_zooms()[:3]]
    crop_pixels = Image.fromarray(crop_plane.T)
    physical_width = max(1e-9, image.shape[2] * actual_zooms[2])
    physical_height = max(1e-9, image.shape[0] * actual_zooms[0])
    preview_width = min(800, max(160, image.shape[2]))
    preview_height = max(1, round(preview_width * physical_height / physical_width))
    crop_display = crop_pixels.resize((preview_width, preview_height), Image.Resampling.NEAREST)
    overview_with_rect = view_image.copy()
    draw = ImageDraw.Draw(overview_with_rect)
    draw.rectangle(
        (selection_rect["left"], selection_rect["top"], selection_rect["left"] + selection_rect["width"], selection_rect["top"] + selection_rect["height"]),
        outline="#ff0000",
        width=3,
    )
    st.success("Preview succeeded. Inspect the exact selected area below before confirming export.")
    st.write({
        "requested_bounds_mm": list(requested.__dict__.values()),
        "requested_resolution_mm": actual_resolution,
        "actual_voxels": list(image.shape),
        "actual_voxel_size_mm": actual_zooms,
        "visualization_slice": f"y={crop_slice}",
        "raw_slice_range": crop_range,
        "estimated_uncompressed_bytes": int(np.asanyarray(image.dataobj).nbytes),
        "preview_physical_aspect_ratio": f"{physical_width:g}:{physical_height:g}",
    })
    st.caption("Visualization contrast only: 1st–99th percentile linear stretch. Scientific NIfTI export keeps raw source values. Preview pixels are displayed with physical x/z aspect preserved.")
    left, right = st.columns(2)
    with left:
        st.image(overview_with_rect, caption="Overview with the selected rectangle")
    with right:
        st.image(crop_display, caption="Exact selected-area preview (visualization contrast only)", width="content")
    confirmed = st.checkbox("I inspected this successful preview and confirm this crop", key="confirm_crop")
    if confirmed:
        st.session_state["confirmed_signature"] = current_signature
    if st.button("Prepare download bundle", disabled=st.session_state.get("confirmed_signature") != current_signature):
        bundle = export_crop(image, section, requested, Path("outputs/ui_export"), actual_resolution)
        st.download_button("4. Download ZIP", data=bundle.read_bytes(), file_name=bundle.name, mime="application/zip")

    if st.session_state.get("confirmed_signature") == current_signature:
        st.subheader("4. Draw polygons on the confirmed crop")
        st.caption(
            "Draw one or more polygons on the exact displayed crop. The canvas toolbar supports edit, resize, "
            "delete and zoom/pan of the view. Labels are user annotations, not verified anatomical labels."
        )
        st.info(
            "The image below uses visualization contrast only. Polygon coordinates are retained in canvas pixels "
            "and mapped to the raw NIfTI crop through its affine; changing the section, bounds or resolution resets them."
        )
        polygon_key = f"polygon-canvas-{hash(current_signature)}"
        canvas = st_canvas(
            fill_color="rgba(0, 255, 255, 0.18)",
            stroke_width=3,
            stroke_color="#00ffff",
            background_image=crop_display,
            background_image_fit="stretch",
            update_streamlit=True,
            height=preview_height,
            width=preview_width,
            drawing_mode="polygon",
            initial_drawing=st.session_state.get("polygon_canvas"),
            key=polygon_key,
        )
        if canvas.json_data is not None:
            previous = st.session_state.get("polygon_canvas")
            if canvas.json_data != previous:
                st.session_state["polygon_canvas"] = canvas.json_data
                st.session_state.pop("polygon_export", None)
                st.session_state.pop("polygon_export_signature", None)
                st.rerun()

        canvas_polygons = polygon_objects(st.session_state.get("polygon_canvas"))
        labels_state = list(st.session_state.get("polygon_labels", []))
        while len(labels_state) < len(canvas_polygons):
            labels_state.append(f"polygon_{len(labels_state) + 1}")
        if len(labels_state) > len(canvas_polygons):
            labels_state = labels_state[:len(canvas_polygons)]
        if canvas_polygons:
            st.write(f"{len(canvas_polygons)} polygon(s) on this crop")
            label_columns = st.columns(min(3, len(canvas_polygons)))
            for index, polygon in enumerate(canvas_polygons):
                with label_columns[index % len(label_columns)]:
                    labels_state[index] = st.text_input(
                        f"Polygon {index + 1} label",
                        value=labels_state[index],
                        key=f"polygon-label-{hash(current_signature)}-{index}",
                    )
            st.session_state["polygon_labels"] = labels_state

            mapped_polygons = []
            for polygon, label in zip(canvas_polygons, labels_state):
                mapped = map_crop_polygon_to_source(
                    polygon["points"],
                    image.shape,
                    np.asarray(image.affine, dtype=float),
                    (preview_width, preview_height),
                    crop_slice,
                )
                mapped["label"] = label
                mapped["shape_type"] = "polygon"
                mapped_polygons.append(mapped)

            annotation_export = build_polygon_export(
                section_id=section.id,
                section_label=section.name,
                source_url=selected["source_url"],
                coordinate_space="bigbrain",
                requested_bounds=requested.__dict__,
                requested_resolution_mm=actual_resolution,
                crop_shape=image.shape,
                actual_voxel_size_mm=actual_zooms,
                affine=image.affine,
                plane_index=crop_slice,
                canvas_size=(preview_width, preview_height),
                polygons=mapped_polygons,
            )
            annotation_export["crop_signature"] = [str(value) for value in current_signature]
            st.session_state["polygon_export"] = annotation_export
            crop_annotation_overlay = crop_display.convert("RGB").copy()
            crop_annotation_draw = ImageDraw.Draw(crop_annotation_overlay)
            overview_annotation_overlay = view_image.copy().convert("RGB")
            overview_annotation_draw = ImageDraw.Draw(overview_annotation_overlay)
            for mapped in mapped_polygons:
                canvas_points = [tuple(point) for point in mapped["canvas_vertices_xy"]]
                crop_annotation_draw.polygon(canvas_points, outline="#00ffff", width=3)
                overview_points = map_physical_polygon_to_view(
                    mapped["physical_vertices_mm"],
                    overview_affine,
                    overview_shape,
                    (full_display_width, full_display_height),
                    view_origin=view_origin,
                    view_size=view_size,
                    canvas_size=(display_width, display_height),
                )
                overview_annotation_draw.polygon(
                    [tuple(point) for point in overview_points], outline="#00ffff", width=3
                )
            st.json({
                "labels": [polygon["label"] for polygon in mapped_polygons],
                "canvas_vertices_xy": [polygon["canvas_vertices_xy"] for polygon in mapped_polygons],
                "nifti_voxel_vertices_xyz": [polygon["nifti_voxel_vertices_xyz"] for polygon in mapped_polygons],
            })
            left, right = st.columns(2)
            with left:
                st.image(crop_annotation_overlay, caption="Confirmed crop with polygon overlays")
            with right:
                st.image(overview_annotation_overlay, caption="Section overview with mapped polygon overlays")
            st.caption("Cyan outlines are user-drawn polygons. Their labels and coordinates are exported; no anatomical interpretation is inferred.")
            if st.button("Prepare annotated download ZIP", type="primary"):
                annotation_dir = Path("outputs/ui_annotation_export")
                bundle = export_crop(image, section, requested, annotation_dir, actual_resolution)
                bundle = append_polygon_files_to_bundle(bundle, annotation_dir, annotation_export)
                st.session_state["polygon_export_signature"] = current_signature
                st.download_button(
                    "4. Download image + polygons ZIP",
                    data=bundle.read_bytes(),
                    file_name=bundle.name,
                    mime="application/zip",
                )
        else:
            st.caption("No polygons yet. Choose the polygon tool, click vertices, and close the polygon by clicking the first vertex.")

st.subheader("5. Import Labelme annotation")
st.caption(
    "Upload the Labelme JSON, its matching mapping_report.json, and the unchanged raw annotation PNG. "
    "Dimensions alone are not sufficient: the mapping metadata checksum and selected section identity must match."
)
annotation_upload = st.file_uploader("Labelme annotation JSON", type=["json"], key=f"labelme-json-{section_id}")
mapping_upload = st.file_uploader("Annotation-image mapping metadata JSON", type=["json"], key=f"labelme-mapping-{section_id}")
image_upload = st.file_uploader("Original raw annotation PNG", type=["png"], key=f"labelme-image-{section_id}")

if annotation_upload and mapping_upload and image_upload:
    annotation_bytes = annotation_upload.getvalue()
    mapping_bytes = mapping_upload.getvalue()
    image_bytes = image_upload.getvalue()
    import_signature = tuple(
        hashlib.sha256(value).hexdigest()
        for value in (annotation_bytes, mapping_bytes, image_bytes)
    )
    if st.session_state.get("labelme_import_signature") != import_signature:
        st.session_state.pop("labelme_import", None)
        st.session_state.pop("labelme_import_error", None)
        st.session_state["labelme_import_signature"] = import_signature
        try:
            st.session_state["labelme_import"] = validate_labelme_annotation(
                annotation_bytes,
                mapping_bytes,
                image_bytes,
                image_filename=image_upload.name,
                expected_section_id=section_id,
                expected_source_url=selected["source_url"],
            )
        except Exception as exc:
            st.session_state["labelme_import_error"] = str(exc)

if st.session_state.get("labelme_import_error"):
    st.error(f"Labelme annotation rejected: {st.session_state['labelme_import_error']}")

if st.session_state.get("labelme_import"):
    imported = st.session_state["labelme_import"]
    imported_image = imported["image"]
    imported_overlay = imported_image.convert("RGB").copy()
    imported_draw = ImageDraw.Draw(imported_overlay)
    overview_import_overlay = view_image.copy()
    overview_draw = ImageDraw.Draw(overview_import_overlay)
    st.success("Labelme annotation accepted for the selected section and exact raw annotation image.")
    st.write({
        "section_id": imported["section_id"],
        "coordinate_space": imported["coordinate_space"],
        "selected_plane": f"y={imported['plane_index']}",
        "polygon_count": len(imported["polygons"]),
        "warning": "User labels are not verified anatomical labels; 3D anatomical alignment is not claimed.",
    })
    for polygon in imported["polygons"]:
        points = [tuple(point) for point in polygon["pixel_vertices_xy"]]
        imported_draw.polygon(points, outline=(255, 0, 0), width=2)
        overview_points = map_physical_polygon_to_view(
            polygon["physical_vertices_mm"],
            overview_affine,
            overview_shape,
            (full_display_width, full_display_height),
            view_origin=view_origin,
            view_size=view_size,
            canvas_size=(display_width, display_height),
        )
        overview_draw.polygon([tuple(point) for point in overview_points], outline="#00ffff", width=3)
        st.caption(f"Label preserved: {polygon['label'] or '(unnamed)'}; cyan outline shows its mapped overview location.")
    left, right = st.columns(2)
    with left:
        st.image(imported_image, caption="Unchanged uploaded annotation image")
    with right:
        st.image(imported_overlay, caption="Annotation image with imported polygon overlay")
    st.image(overview_import_overlay, caption="Current overview view with mapped polygon; zoom/pan do not change its physical location")
    st.download_button(
        "Download mapped Labelme provenance JSON",
        data=build_import_export(imported),
        file_name="bigbrain_labelme_import_mapping.json",
        mime="application/json",
    )
