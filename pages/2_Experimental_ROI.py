"""Experimental ICBM2009c binary-ROI workflow."""
from __future__ import annotations

import hashlib
import tempfile

import nibabel as nib
import numpy as np
import streamlit as st
from PIL import Image

from patch_collection import add_entry, annotation_plane_from_image, bind_unmarked_png_metadata, collection_visual_report_filename, collection_visual_report_html, collection_zip_bytes, patch_id_for
from collection_ui import render_collection_review, render_start_new_collection
from template_roi_workflow import (
    BIGBRAIN, CEREBRA, REFERENCE, SUPPORTED_TEMPLATE, fetch_mask_patch, intersecting_sections,
    run_transform, verified_example,
)


st.set_page_config(page_title="Experimental template ROI · BigBrain TissueLink", layout="wide")
st.title("Experimental template ROI")
st.warning("Anatomical placement awaiting independent review")
st.caption("Technical transform and overlap evidence only. This workflow does not establish anatomical correctness.")
st.session_state.setdefault("patch_collection", {})
selected_upload_name = None
selected_upload_sha256 = None

with st.container(border=True):
    st.markdown("#### What does this workflow do?")
    st.write(
        "An ROI (region of interest) is a binary 3-D mask: 1 means the selected brain region and 0 means outside it. "
        "This workflow maps that mask from the exact supported ICBM2009c reference template into BigBrain, finds "
        "registered histology sections that cross it, and lets you inspect and export a small tissue patch."
    )
    st.info(
        "This is not for uploading an ordinary anatomical MRI, patient scan, photograph or segmentation in another "
        "MNI template. It does not create an ROI automatically."
    )


def png_bytes(array: np.ndarray) -> bytes:
    import io
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()


def nifti_bytes(image: nib.spatialimages.SpatialImage) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as stream:
        nib.save(image, stream.name)
        stream.seek(0)
        return stream.read()


def display_plane(background: nib.spatialimages.SpatialImage, mask: nib.spatialimages.SpatialImage, y_index: int) -> np.ndarray:
    bg = np.asarray(background.dataobj[:, y_index, :], dtype=float)
    finite = bg[np.isfinite(bg)]
    low, high = np.percentile(finite, [1, 99]) if finite.size else (0, 1)
    gray = np.clip((bg - low) * 255 / max(high - low, 1), 0, 255).astype(np.uint8).T
    rgb = np.repeat(gray[..., None], 3, axis=2)
    mask_data = np.asarray(mask.dataobj)
    if background.shape == mask.shape and np.array_equal(background.affine, mask.affine):
        sampled = mask_data[:, y_index, :].T != 0
    else:
        ii, kk = np.indices((background.shape[0], background.shape[2]), dtype=float)
        ijk = np.column_stack((ii.ravel(), np.full(ii.size, y_index), kk.ravel()))
        world = nib.affines.apply_affine(background.affine, ijk)
        source = np.rint(nib.affines.apply_affine(np.linalg.inv(mask.affine), world)).astype(int)
        valid = np.all((source >= 0) & (source < np.asarray(mask.shape[:3])), axis=1)
        values = np.zeros(len(source), dtype=bool)
        values[valid] = mask_data[tuple(source[valid].T)] != 0
        sampled = values.reshape(background.shape[0], background.shape[2]).T
    # Keep the underlying anatomy visible. The translucent fill communicates
    # categorical mask membership; the solid edge shows its sampled boundary.
    red = np.asarray((235, 55, 55), dtype=np.float32)
    rgb[sampled] = (0.55 * rgb[sampled].astype(np.float32) + 0.45 * red).astype(np.uint8)
    interior = sampled.copy()
    interior[1:, :] &= sampled[:-1, :]
    interior[:-1, :] &= sampled[1:, :]
    interior[:, 1:] &= sampled[:, :-1]
    interior[:, :-1] &= sampled[:, 1:]
    rgb[sampled & ~interior] = red.astype(np.uint8)
    return rgb


st.subheader("1. Load technically verified CerebrA example")
st.write(
    "Recommended first step. Everything needed is already saved locally: a binary mask for the left precentral "
    "region, its preserved BigBrain transform, section-intersection results and one verified patch. You do not "
    "need to download or upload anything."
)
st.caption("Clicking the button verifies checksums and opens the example. It does not rerun Docker or overwrite the saved transform.")
if st.button("Load technically verified CerebrA example", type="primary"):
    try:
        example = verified_example()
        st.session_state.roi_workflow = {
            "kind": "verified CerebrA example", "input_image": example["input_image"],
            "output_image": example["output_image"], "provenance": example["metadata"],
            "signature": example["checksums"]["output"],
            "selected_filename": example["files"]["input"].name,
            "input_sha256": example["checksums"]["input"],
            "output_sha256": example["checksums"]["output"],
        }
        st.session_state.roi_example_verified = True
        st.session_state.pop("roi_intersections", None)
        st.session_state.pop("roi_patch", None)
        st.success("Verified example loaded end to end from preserved checksums; no transform was repeated.")
    except Exception as exc:
        st.session_state.roi_example_verified = False
        st.error(f"Verified example rejected: {exc}")

render_start_new_collection("roi")

st.subheader("2. New binary NIfTI ROI upload")
if not st.session_state.get("roi_example_verified"):
    st.info("First click “Load technically verified CerebrA example” above. New uploads are intentionally locked until that local example passes verification.")
else:
    st.caption(
        "A format example and provenance record are available in the project folder "
        "`examples/template_rois/`. Use the Load button above for that CerebrA example; do not upload it again unless "
        "you intentionally want a new transform run."
    )
    st.markdown(
        """
        Use this only for **your own binary mask**, saved as `.nii` or `.nii.gz`, when you know it is already on the
        exact **ICBM 2009c nonlinear symmetric 1 mm** grid.

        Accepted: a 3-D mask containing only 0 and 1, shape `193 × 229 × 193`, with the documented affine.

        Not accepted: a raw T1 MRI, DICOM files, a mask from MNI152 2006, asymmetric MNI, another voxel size,
        probabilistic values, or a NIfTI whose template identity is unknown.
        """
    )
    st.info(
        "To enable the transform button, complete all three required items below: "
        "(1) confirm the template identity, (2) enter template provenance, and "
        "(3) upload at least one binary NIfTI ROI. You may click + again to keep "
        "the first file and add more files to the queue."
    )
    template = st.selectbox("Declared source template", [SUPPORTED_TEMPLATE])
    identity_confirmed = st.checkbox("I explicitly identify this ROI as being in the selected template; I understand the NIfTI header alone cannot prove template identity.")
    provenance = st.text_area(
        "Template provenance (required)",
        placeholder=(
            "Example: CerebrA atlas; region and hemisphere; CerebrA label; "
            "binary extraction method; ICBM2009c nonlinear symmetric 1 mm source."
        ),
        help="Record the generating dataset, registration procedure, source URL/identifier and responsible person or pipeline.",
    )
    st.session_state.setdefault("roi_uploader_generation", 0)
    if st.button("Remove all queued ROI files", type="secondary"):
        st.session_state.roi_uploader_generation += 1
        st.session_state.pop("roi_active_upload_signature", None)
        st.session_state.pop("roi_workflow", None)
        st.session_state.pop("roi_intersections", None)
        st.session_state.pop("roi_patch", None)
        st.session_state.pop("roi_patch_section", None)
        st.session_state.pop("roi_selected_section_id", None)
        st.success("Queued ROI files and their current preview were removed. Collected patches were preserved.")
    uploads = st.file_uploader(
        "Upload only binary ROI files ending in .nii or .nii.gz",
        type=["nii", "gz"],
        accept_multiple_files=True,
        help="Select one file, then click + to add another. Files remain queued and are transformed one at a time.",
        key=f"roi-uploads-{st.session_state.roi_uploader_generation}",
    )
    upload = None
    if uploads:
        st.success(f"{len(uploads)} ROI file{'s' if len(uploads) != 1 else ''} queued. Click + to add another without removing the current files.")
        active_index = st.selectbox(
            "ROI to validate and transform now",
            options=range(len(uploads)),
            format_func=lambda index: uploads[index].name,
        )
        upload = uploads[active_index]
        active_upload_signature = hashlib.sha256(upload.getvalue()).hexdigest()
        selected_upload_name = upload.name
        selected_upload_sha256 = active_upload_signature
        if st.session_state.get("roi_active_upload_signature") != active_upload_signature:
            st.session_state.roi_active_upload_signature = active_upload_signature
            st.session_state.pop("roi_workflow", None)
            st.session_state.pop("roi_intersections", None)
            st.session_state.pop("roi_patch", None)
            st.session_state.pop("roi_patch_section", None)
            st.session_state.pop("roi_selected_section_id", None)
        st.markdown(
            f"**Selected file:** `{selected_upload_name}`  \n"
            f"**Selected input SHA-256:** `{selected_upload_sha256}`"
        )
    requirements = {
        "Template identity confirmed": identity_confirmed,
        "Template provenance entered": bool(provenance.strip()),
        "At least one binary NIfTI queued": upload is not None,
    }
    st.markdown("**Required before validation:**")
    for requirement, complete in requirements.items():
        st.write(f"{'✅' if complete else '⬜'} {requirement}")
    ready_to_transform = all(requirements.values())
    if not ready_to_transform:
        missing = [name.lower() for name, complete in requirements.items() if not complete]
        st.warning("The button is disabled because this is still missing: " + ", ".join(missing) + ".")
    transform_label = f"Validate and transform {upload.name}" if upload is not None else "Validate and transform selected ROI"
    if st.button(transform_label, disabled=not ready_to_transform):
        try:
            with st.status(f"Processing {upload.name}…", expanded=True) as processing_status:
                st.write("Validating the selected binary ROI and running its transform. Previous previews are unavailable during processing.")
                result = run_transform(upload.getvalue(), upload.name, provenance)
                processing_status.update(label=f"Completed {upload.name}", state="complete", expanded=False)
            st.session_state.roi_workflow = {
                "kind": "uploaded binary ROI", "input_image": result["input_image"],
                "output_image": result["output_image"], "provenance": result["manifest"],
                "signature": result["manifest"]["output_sha256"], "run_dir": str(result["run_dir"]),
                "selected_filename": upload.name,
                "input_sha256": result["manifest"]["input_sha256"],
                "output_sha256": result["manifest"]["output_sha256"],
            }
            st.session_state.pop("roi_intersections", None)
            st.session_state.pop("roi_patch", None)
            st.success(f"Transform completed. Complete evidence and logs: {result['run_dir']}")
        except Exception as exc:
            st.error(str(exc))

workflow = st.session_state.get("roi_workflow")
if (
    workflow
    and workflow.get("kind") == "uploaded binary ROI"
    and selected_upload_sha256
    and workflow.get("input_sha256") != selected_upload_sha256
):
    st.session_state.pop("roi_workflow", None)
    st.session_state.pop("roi_intersections", None)
    st.session_state.pop("roi_patch", None)
    st.session_state.pop("roi_patch_section", None)
    workflow = None

st.subheader("Current ROI processing state")
if selected_upload_name:
    st.write(f"Selected file: `{selected_upload_name}`")
    st.write(f"Selected input checksum: `{selected_upload_sha256}`")
if workflow:
    st.success("Processing status: completed; this result is eligible for placement inspection and section fetching.")
    st.write(f"Currently displayed result: `{workflow.get('selected_filename', 'preserved CerebrA example')}`")
    st.write(f"Displayed result input checksum: `{workflow.get('input_sha256', 'not recorded')}`")
    st.write(f"Displayed transformed output checksum: `{workflow.get('output_sha256', workflow.get('signature'))}`")
elif selected_upload_name:
    st.warning("Processing status: not completed for the selected file. No ROI overlay or fetch controls are displayed.")
else:
    st.info("Processing status: no uploaded ROI selected. Load the preserved example or select an upload.")

if workflow:
    source = workflow["input_image"]
    transformed = workflow["output_image"]
    source_data = np.asarray(source.dataobj)
    output_data = np.asarray(transformed.dataobj)
    source_y = int(np.argmax(np.count_nonzero(source_data, axis=(0, 2))))
    output_y = int(np.argmax(np.count_nonzero(output_data, axis=(0, 2))))
    if workflow["kind"] == "verified CerebrA example":
        reference = nib.load(CEREBRA / "mni_icbm152_CerebrA_tal_nlin_sym_09c.nii")
        source_caption = f"Original CerebrA atlas label 86 (left Precentral) · source 1 mm grid · Y index {source_y}"
    else:
        reference = nib.load(REFERENCE)
        source_caption = f"Input ROI on exact supported ICBM2009c template mask · source 1 mm grid · Y index {source_y}"
    bigbrain = nib.load(BIGBRAIN)
    output_world_y = float(nib.affines.apply_affine(transformed.affine, [0, output_y, 0])[1])
    bigbrain_y = int(np.rint(nib.affines.apply_affine(np.linalg.inv(bigbrain.affine), [0, output_world_y, 0])[1]))

    st.subheader("3. Inspect placement")
    st.error(
        "The transformed red shape is a coarse technical mask, not an exact anatomical boundary. "
        "Its 2 mm voxels and nearest-neighbour interpolation create blocky edges. Use it to find candidate sections only."
    )
    st.markdown(
        "**Overlay legend:** translucent red = voxels inside the binary ROI; solid red edge = sampled ROI boundary; "
        "grayscale/white = reference anatomy outside the ROI. Red is not an error, disease, activation, or anatomical validation."
    )
    source_overlay = display_plane(reference, source, source_y)
    transformed_overlay = display_plane(bigbrain, transformed, bigbrain_y)
    left, right = st.columns(2)
    with left:
        st.image(source_overlay, caption=source_caption, use_container_width=True)
        st.download_button(
            "Download source ROI overlay PNG",
            png_bytes(source_overlay),
            "source_roi_overlay.png",
            "image/png",
            key=f"source-overlay-download-{workflow['signature']}",
        )
    with right:
        st.image(
            transformed_overlay,
            caption=f"Coarse 2 mm transformed ROI on BigBrain 200 µm reconstruction · world Y≈{output_world_y:.3f} mm · candidate placement only",
            use_container_width=True,
        )
        st.download_button(
            "Download transformed ROI overlay PNG",
            png_bytes(transformed_overlay),
            "transformed_roi_on_bigbrain_overlay.png",
            "image/png",
            key=f"transformed-overlay-download-{workflow['signature']}",
        )
    data_col1, data_col2 = st.columns(2)
    with data_col1:
        st.download_button(
            "Download source binary ROI NIfTI",
            nifti_bytes(source),
            "source_binary_roi.nii.gz",
            "application/gzip",
            key=f"source-roi-download-{workflow['signature']}",
            help="Scientific 3-D mask: values 0 outside the ROI and 1 inside it.",
        )
    with data_col2:
        st.download_button(
            "Download transformed ROI NIfTI",
            nifti_bytes(transformed),
            "transformed_roi_bigbrain_histological.nii.gz",
            "application/gzip",
            key=f"transformed-roi-download-{workflow['signature']}",
            help="Scientific transformed mask in BigBrain histological space; anatomical placement remains awaiting review.",
        )
    st.caption("PNG files are visual explanations. NIfTI files are the scientific 3-D masks. Visual placement remains Awaiting independent review.")
    with st.expander("Why are the two red shapes different?", expanded=True):
        st.write(
            "The left ROI is the original 1 mm CerebrA label. The right ROI was nonlinearly transformed and then sampled "
            "on a 2 mm BigBrain grid using nearest-neighbour interpolation so it stays binary. That coarser grid makes "
            "the boundary look stepped and can change its displayed outline. This test demonstrates technical coordinate "
            "mapping and section coverage; an expert has not confirmed the anatomical placement."
        )
    inspected = st.checkbox("I inspected both placements and want to continue to section coverage.", key=f"roi-inspected-{workflow['signature']}")

    if inspected:
        if st.button("Compute intersecting available sections"):
            try:
                st.session_state.roi_intersections = intersecting_sections(transformed)
            except Exception as exc:
                st.error(f"Section coverage failed: {exc}")
        sections = st.session_state.get("roi_intersections")
        if sections is not None:
            st.subheader("4. Intersecting registered sections and coverage")
            st.caption(f"{len(sections)} of the available registered-section planes contain sampled mask coverage at 2 mm.")
            st.dataframe([{"Section": x["section_number"], "World Y (mm)": x["section_plane_y_mm"], "Nonzero 2 mm samples": x["coverage_nonzero_samples"]} for x in sections], hide_index=True, use_container_width=True)
            if sections:
                labels = [f"#{x['section_number']} · Y={x['section_plane_y_mm']:.4f} mm · coverage {x['coverage_nonzero_samples']}" for x in sections]
                selected_label = st.selectbox("Intersecting section", labels)
                selected = sections[labels.index(selected_label)]
                if st.session_state.get("roi_selected_section_id") != selected["id"]:
                    st.session_state.roi_selected_section_id = selected["id"]
                    st.session_state.pop("roi_patch", None)
                    st.session_state.pop("roi_patch_section", None)
                half_width = st.number_input("Bounded patch half-width X/Z (mm)", 0.25, 1.0, 1.0, 0.25)
                st.write({"actual_mask_location_world_xyz_mm": selected["first_nonzero_world_xyz_mm"], "anatomical_status": "Awaiting independent review"})
                if st.button("Fetch bounded patch at this mask location", type="primary"):
                    try:
                        st.session_state.roi_patch = fetch_mask_patch(transformed, selected, half_width)
                        st.session_state.roi_patch_section = selected
                    except Exception as exc:
                        st.error(f"Bounded fetch failed: {exc}")

    fetched = st.session_state.get("roi_patch")
    selected = st.session_state.get("roi_patch_section")
    if fetched and selected:
        patch = fetched["patch"]
        patch_data = np.asarray(patch.dataobj)
        y_index = fetched["slice_index"]
        patch_view = display_plane(patch, nib.Nifti1Image(fetched["mask"].astype(np.uint8), patch.affine), y_index)
        st.subheader("5. Bounded patch preview")
        st.image(patch_view, caption=f"Section #{selected['section_number']} · mask/non-padding overlap by Y {fetched['overlap_by_y']}", use_container_width=True)
        raw_nifti = nifti_bytes(patch)
        annotation, mapping = annotation_plane_from_image(patch, y_index)
        metadata = {
            "workflow": "experimental_template_roi", "anatomical_status": "Awaiting independent review",
            "section_id": selected["id"], "section_number": selected["section_number"],
            "section_label": selected["label"], "provider_url": selected["source_url"],
            "coordinate_space": "BigBrain microscopic template (histology)",
            "requested_bounds_mm": list(fetched["bounds"].__dict__.values()),
            "selected_mask_world_xyz_mm": fetched["point"], "actual_shape_xyz": list(patch.shape),
            "actual_voxel_size_mm_xyz": list(map(float, patch.header.get_zooms()[:3])),
            "actual_affine": patch.affine.tolist(), "mask_nonpadding_overlap_by_y": fetched["overlap_by_y"],
            "input_roi_sha256": workflow["provenance"].get("input_sha256", workflow["provenance"].get("transform", {}).get("input_sha256")),
            "input_roi_filename": workflow.get("selected_filename"),
            "supported_template": SUPPORTED_TEMPLATE,
            "transform_provenance": workflow["provenance"], "annotation_plane_mapping": mapping,
            "source_array_sha256": hashlib.sha256(np.ascontiguousarray(patch_data).tobytes()).hexdigest(),
            "exported_nifti_sha256": hashlib.sha256(raw_nifti).hexdigest(),
        }
        patch_id = patch_id_for(raw_nifti, metadata)
        st.download_button("Download raw bounded patch", raw_nifti, f"{patch_id}.nii.gz", "application/gzip")
        label = st.text_input("Patch label", value=f"roi-section-{selected['section_number']}", key=f"roi-label-{patch_id}")
        note = st.text_area("Patch note", key=f"roi-note-{patch_id}")
        if st.button("Add patch to collection", key=f"roi-add-{patch_id}"):
            unmarked = png_bytes(annotation)
            entry = {"patch_id": patch_id, "user_label": label, "user_note": note,
                     "metadata": bind_unmarked_png_metadata(metadata, patch_id, unmarked, annotation.shape),
                     "raw_nifti": raw_nifti, "unmarked_png": unmarked, "marked_png": png_bytes(patch_view),
                     "source_roi_overlay_png": png_bytes(source_overlay),
                     "transformed_roi_overlay_png": png_bytes(transformed_overlay)}
            try:
                add_entry(st.session_state.patch_collection, entry)
                st.success(f"Added {patch_id}. Export it from the existing collection controls in MRI–Histology Explorer.")
            except ValueError as exc:
                st.warning(str(exc))

    with st.expander("Complete transform provenance", expanded=False):
        st.json(workflow["provenance"])

render_collection_review("roi")
