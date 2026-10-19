import numpy as np

from patch_statistics import choose_valid_plane, compute_patch_statistics


def test_constant_plane_is_described_without_being_discarded():
    data = np.full((5, 2, 7), 12, dtype=np.uint16)
    result = compute_patch_statistics(data, preferred_y=1, declared_background_values=(255,))
    assert result["status"] == "constant"
    assert result["slice_index_y"] == 1
    assert result["percentiles_usable"]["p50"] == 12.0


def test_padding_plane_is_excluded_and_valid_plane_is_selected():
    data = np.full((5, 2, 7), 255, dtype=np.uint8)
    data[:, 1, :] = np.arange(35, dtype=np.uint8).reshape(5, 7)
    assert choose_valid_plane(data, preferred_y=0, declared_padding_values=(255,)) == 1
    result = compute_patch_statistics(data, preferred_y=0, declared_background_values=(255,))
    assert result["slice_index_y"] == 1
    assert result["declared_background_fraction_of_finite"] == 0.0
    assert result["status"] == "variable"


def test_textured_plane_reports_sharpness_and_no_false_quality_label():
    data = np.zeros((7, 1, 7), dtype=np.uint16)
    data[:, 0, :] = np.indices((7, 7)).sum(axis=0) % 2 * 100
    result = compute_patch_statistics(data, preferred_y=0, declared_background_values=(255,))
    assert result["sharpness"]["value"] is not None
    assert "quality" not in result
    assert result["status"] == "variable"


def test_saturation_is_storage_endpoint_fraction():
    data = np.array([[[0, 1, 255], [2, 255, 4]]], dtype=np.uint8)
    result = compute_patch_statistics(data, declared_background_values=(254,))
    assert result["saturation"]["low_fraction"] > 0
    assert result["saturation"]["high_fraction"] > 0
