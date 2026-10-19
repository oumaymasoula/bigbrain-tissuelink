"""Shared Streamlit controls for collection lifecycle, export and reopening."""

from __future__ import annotations

import io

import streamlit as st
from PIL import Image

from collection_replay import import_collection_archive
from patch_collection import (
    collection_visual_report_filename,
    collection_visual_report_html,
    collection_zip_bytes,
    collection_zip_filename,
)


def _clear_session_collection_state() -> None:
    generation = int(st.session_state.get("collection_session_generation", 0)) + 1
    st.session_state.clear()
    st.session_state.patch_collection = {}
    st.session_state.collection_session_generation = generation
    st.session_state.collection_fresh_notice = True


def render_start_new_collection(key_prefix: str) -> None:
    """Offer a deliberate, save-first fresh-session action."""
    st.session_state.setdefault("patch_collection", {})
    pending_key = f"{key_prefix}_new_collection_pending"
    if st.button("Start a new collection", key=f"{key_prefix}-start-new"):
        st.session_state[pending_key] = True
    if st.session_state.get(pending_key):
        collection = st.session_state.patch_collection
        if collection:
            st.warning(
                f"The current collection contains {len(collection)} patch(es). Save the scientific ZIP and/or visual HTML report before clearing if you want to keep them on your computer."
            )
            save_zip, save_html = st.columns(2)
            with save_zip:
                st.download_button(
                    "Save current collection ZIP before clearing",
                    collection_zip_bytes(collection),
                    collection_zip_filename(),
                    "application/zip",
                    key=f"{key_prefix}-save-before-clear-zip",
                )
            with save_html:
                st.download_button(
                    "Save current visual report before clearing",
                    collection_visual_report_html(collection),
                    collection_visual_report_filename(),
                    "text/html",
                    key=f"{key_prefix}-save-before-clear-html",
                )
        else:
            st.info("The current collection is empty. Starting fresh will clear route selections, queued uploads and previews.")
        confirm, cancel = st.columns(2)
        with confirm:
            if st.button("Confirm: clear session and start fresh", type="primary", key=f"{key_prefix}-confirm-new"):
                _clear_session_collection_state()
                st.rerun()
        with cancel:
            if st.button("Cancel", key=f"{key_prefix}-cancel-new"):
                st.session_state.pop(pending_key, None)
                st.rerun()
    if st.session_state.pop("collection_fresh_notice", False):
        st.success("Started a new empty collection. Saved files and project outputs were not changed.")


def render_collection_review(key_prefix: str) -> None:
    """Render the final review, save and safe local reopen section."""
    st.session_state.setdefault("patch_collection", {})
    collection = st.session_state.patch_collection
    st.markdown("## Review, save and reopen your collection")
    st.caption(
        "Downloads must be saved on your computer. The ZIP is the scientific collection and the supported file for reopening. "
        "The HTML is a portable, read-only visual report; reopening HTML does not restore an editable app session."
    )
    st.write(f"**Collection count:** {len(collection)} patch(es)")
    if collection:
        columns = st.columns(min(3, len(collection)))
        for index, (patch_id, entry) in enumerate(collection.items()):
            metadata = entry.get("metadata", {})
            with columns[index % len(columns)]:
                preview = entry.get("marked_png") or entry.get("unmarked_png")
                if preview:
                    try:
                        with Image.open(io.BytesIO(preview)) as image:
                            image.verify()
                        st.image(preview, width="stretch")
                    except Exception:
                        st.caption("Preview not available in this archive.")
                st.markdown(f"**{entry.get('user_label') or patch_id}**")
                st.caption(f"Section {metadata.get('section_number') or metadata.get('section_id') or 'Not recorded'} · {patch_id}")
        zip_col, html_col = st.columns(2)
        with zip_col:
            st.download_button(
                "Download collection ZIP",
                collection_zip_bytes(collection),
                collection_zip_filename(),
                "application/zip",
                key=f"{key_prefix}-final-zip",
            )
        with html_col:
            st.download_button(
                "Download visual report HTML",
                collection_visual_report_html(collection),
                collection_visual_report_filename(),
                "text/html",
                key=f"{key_prefix}-final-html",
            )
        st.info(
            "NIfTI contains the raw patch and spatial geometry. The unmarked PNG supports visual inspection and external annotation. "
            "Metadata records location, resolution, source and review status. Figure preparation requires checking resolution, orientation, scale and source attribution. "
            "Annotation and analysis are downstream tasks; exports are not claims of publication readiness or anatomical validation."
        )
    else:
        st.info("No patches are currently collected. Complete either route and add a patch before exporting.")

    st.markdown("### Reopen saved collection")
    show_reopen = st.checkbox(
        "Show collection ZIP import",
        value=False,
        key=f"{key_prefix}-show-reopen",
        help="Use this only with a collection ZIP previously exported by this app.",
    )
    if not show_reopen:
        st.caption("Enable ZIP import above when you want to restore a saved editable collection.")
        return
    uploaded = st.file_uploader(
        "Import a BigBrain TissueLink collection ZIP",
        type=["zip"],
        key=f"{key_prefix}-reopen-upload",
        help="This reads retained files locally. It does not rerun transforms or fetch tissue.",
    )
    replace = st.checkbox("Replace the current collection instead of merging", value=False, key=f"{key_prefix}-reopen-replace")
    if st.button("Reopen saved collection ZIP", disabled=uploaded is None, key=f"{key_prefix}-reopen-button"):
        try:
            restored = import_collection_archive(uploaded.getvalue())
            if replace:
                st.session_state.patch_collection = dict(restored["collection"])
            else:
                st.session_state.patch_collection.update(restored["collection"])
            st.session_state[f"{key_prefix}_reopen_result"] = restored
            st.success(f"Restored {len(restored['collection'])} patch(es) locally without fetching tissue or rerunning transforms.")
        except Exception as exc:
            st.error(f"Collection ZIP could not be reopened: {exc}")
    restored = st.session_state.get(f"{key_prefix}_reopen_result")
    if restored:
        for warning in restored["warnings"]:
            st.warning(warning)
        reports = restored["inspection"]["reports"]
        if reports:
            st.dataframe(reports, width="stretch", hide_index=True)
