import nibabel as nib
import numpy as np
import pytest
import hashlib
import tempfile
from streamlit.testing.v1 import AppTest
from pathlib import Path

from template_roi_workflow import (
    EXPECTED_AFFINE, EXPECTED_SHAPE, SUPPORTED_TEMPLATE,
    validate_binary_roi, verified_example,
)


def valid_roi():
    data = np.zeros(EXPECTED_SHAPE, dtype=np.uint8)
    data[90:92, 110:112, 90:92] = 1
    return nib.Nifti1Image(data, EXPECTED_AFFINE)


def serialized_roi(image):
    with tempfile.NamedTemporaryFile(suffix=".nii.gz") as stream:
        nib.save(image, stream.name)
        stream.seek(0)
        return stream.read()


def test_binary_roi_requires_explicit_exact_template_declaration():
    with pytest.raises(ValueError, match="Explicit ICBM 2009c"):
        validate_binary_roi(valid_roi(), 1024, "MNI")


def test_binary_roi_rejects_wrong_affine_nonfinite_and_nonbinary_values():
    wrong_affine = valid_roi()
    wrong_affine.set_sform(np.diag([2, 2, 2, 1]))
    with pytest.raises(ValueError, match="affine"):
        validate_binary_roi(wrong_affine, 1024, SUPPORTED_TEMPLATE)

    nonfinite = np.zeros(EXPECTED_SHAPE, dtype=np.float32)
    nonfinite[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        validate_binary_roi(nib.Nifti1Image(nonfinite, EXPECTED_AFFINE), 1024, SUPPORTED_TEMPLATE)

    nonbinary = np.zeros(EXPECTED_SHAPE, dtype=np.uint8)
    nonbinary[0, 0, 0] = 2
    with pytest.raises(ValueError, match="binary"):
        validate_binary_roi(nib.Nifti1Image(nonbinary, EXPECTED_AFFINE), 1024, SUPPORTED_TEMPLATE)


def test_verified_example_loads_end_to_end_without_transform():
    result = verified_example()
    assert result["metadata"]["status"] == "technical_checks_passed_anatomical_review_pending"
    assert result["metadata"]["fetch"]["mask_nonpadding_overlap_voxels"] == 62268
    assert result["input_image"].shape == EXPECTED_SHAPE
    assert result["output_image"].shape == (70, 70, 70)


def test_verified_example_gates_and_then_enables_upload_ui():
    page = Path(__file__).resolve().parents[1] / "pages/2_Experimental_ROI.py"
    app = AppTest.from_file(str(page), default_timeout=20).run()
    assert not app.exception
    assert len(app.get("file_uploader")) == 0
    app.button[0].click().run()
    assert not app.exception
    assert any("loaded end to end" in item.value for item in app.success)
    assert len(app.get("file_uploader")) == 1
    assert any(item.value == "3. Inspect placement" for item in app.subheader)
    assert any(item.value == "1. Load technically verified CerebrA example" for item in app.subheader)
    download_labels = [item.label for item in app.get("download_button")]
    assert "Download source ROI overlay PNG" in download_labels
    assert "Download transformed ROI overlay PNG" in download_labels
    assert "Download source binary ROI NIfTI" in download_labels
    assert "Download transformed ROI NIfTI" in download_labels


def test_switching_between_two_different_uploads_clears_stale_result_and_preserves_collection():
    page = Path(__file__).resolve().parents[1] / "pages/2_Experimental_ROI.py"
    first = valid_roi()
    second_data = np.zeros(EXPECTED_SHAPE, dtype=np.uint8)
    second_data[40:44, 60:63, 70:75] = 1
    second = nib.Nifti1Image(second_data, EXPECTED_AFFINE)
    first_bytes = serialized_roi(first)
    second_bytes = serialized_roi(second)
    first_sha = hashlib.sha256(first_bytes).hexdigest()
    second_sha = hashlib.sha256(second_bytes).hexdigest()
    assert first_sha != second_sha

    app = AppTest.from_file(str(page), default_timeout=20).run()
    app.button[0].click().run()
    app.file_uploader[0].set_value([
        ("first_roi.nii.gz", first_bytes, "application/gzip"),
        ("second_roi.nii.gz", second_bytes, "application/gzip"),
    ]).run()
    assert not app.exception
    assert app.session_state["roi_active_upload_signature"] == first_sha
    assert "roi_workflow" not in app.session_state

    output_one_data = np.zeros((70, 70, 70), dtype=np.uint8)
    output_one_data[2:5, 3:7, 4:9] = 1
    output_one = nib.Nifti1Image(output_one_data, np.diag([2.0, 2.0, 2.0, 1.0]))
    app.session_state["roi_workflow"] = {
        "kind": "uploaded binary ROI",
        "input_image": first,
        "output_image": output_one,
        "provenance": {"input_sha256": first_sha},
        "signature": "output-one-sha",
        "selected_filename": "first_roi.nii.gz",
        "input_sha256": first_sha,
        "output_sha256": "output-one-sha",
    }
    app.session_state["patch_collection"] = {
        "preserved-patch": {
            "patch_id": "preserved-patch",
            "metadata": {},
            "raw_nifti": b"nifti",
            "unmarked_png": b"unmarked",
            "marked_png": b"marked",
        }
    }
    app.run()
    displayed = "\n".join(item.value for item in app.markdown)
    assert "Currently displayed result: `first_roi.nii.gz`" in displayed
    assert f"Displayed result input checksum: `{first_sha}`" in displayed
    assert "Displayed transformed output checksum: `output-one-sha`" in displayed

    app.selectbox[1].select(1).run()
    assert not app.exception
    assert app.session_state["roi_active_upload_signature"] == second_sha
    assert "roi_workflow" not in app.session_state
    assert "preserved-patch" in app.session_state["patch_collection"]
    displayed = "\n".join(item.value for item in app.markdown)
    assert "Selected file: `second_roi.nii.gz`" in displayed
    assert f"Selected input checksum: `{second_sha}`" in displayed
    assert not any(item.label == "Fetch bounded patch at this mask location" for item in app.button)

    output_two_data = np.zeros((70, 70, 70), dtype=np.uint8)
    output_two_data[20:24, 30:35, 40:46] = 1
    output_two = nib.Nifti1Image(output_two_data, np.diag([2.0, 2.0, 2.0, 1.0]))
    assert not np.array_equal(output_one_data, output_two_data)
    app.session_state["roi_workflow"] = {
        "kind": "uploaded binary ROI",
        "input_image": second,
        "output_image": output_two,
        "provenance": {"input_sha256": second_sha},
        "signature": "output-two-sha",
        "selected_filename": "second_roi.nii.gz",
        "input_sha256": second_sha,
        "output_sha256": "output-two-sha",
    }
    app.run()
    assert not app.exception
    displayed = "\n".join(item.value for item in app.markdown)
    assert "Currently displayed result: `second_roi.nii.gz`" in displayed
    assert f"Displayed result input checksum: `{second_sha}`" in displayed
    assert "Displayed transformed output checksum: `output-two-sha`" in displayed
    assert "output-one-sha" not in displayed
    assert "preserved-patch" in app.session_state["patch_collection"]
