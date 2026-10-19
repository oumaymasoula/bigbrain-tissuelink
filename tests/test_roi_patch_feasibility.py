import nibabel as nib
import numpy as np

from roi_patch_feasibility import ROI_AFFINE, sample_roi_on_patch


def test_roi_sampling_uses_full_affines_and_nearest_neighbour():
    roi_affine = np.array(
        [[0.0, 0.0, 0.2, -4.0], [0.0, 0.02, 0.0, -0.9], [0.2, 0.0, 0.0, 2.0], [0, 0, 0, 1]],
        dtype=float,
    )
    roi_data = np.zeros((5, 2, 5), dtype=np.uint8)
    roi_data[3, 1, 2] = 1
    roi = nib.Nifti1Image(roi_data, roi_affine)
    patch_affine = np.array(
        [[0.1, 0.0, 0.0, -3.75], [0.0, 0.02, 0.0, -0.9], [0.0, 0.0, 0.1, 2.15], [0, 0, 0, 1]],
        dtype=float,
    )
    patch = nib.Nifti1Image(np.zeros((8, 2, 8), dtype=np.uint8), patch_affine)
    sampled = sample_roi_on_patch(roi, patch, y_index=1)
    assert sampled.shape == (8, 8)
    assert int(np.count_nonzero(sampled)) == 4
    assert np.argwhere(sampled).tolist() == [[1, 4], [1, 5], [2, 4], [2, 5]]


def test_stage1_roi_affine_is_explicit_and_mm_ordered():
    assert ROI_AFFINE.shape == (4, 4)
    assert np.allclose(ROI_AFFINE[0, :3], [0.2, 0.0, 0.0])
    assert np.allclose(ROI_AFFINE[1, :3], [0.0, 0.02, 0.0])
    assert np.allclose(ROI_AFFINE[2, :3], [0.0, 0.0, 0.2])
