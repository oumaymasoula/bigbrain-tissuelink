import nibabel as nib
import numpy as np

from external_roi_feasibility import sample_nearest, sample_section_plane


def test_sample_nearest_uses_full_affine_and_preserves_asymmetric_voxel():
    data = np.zeros((4, 3, 5), dtype=np.uint8)
    data[2, 1, 4] = 1
    affine = np.array(
        [[0.0, 0.0, 2.0, -10.0], [0.0, 1.5, 0.0, -3.0], [1.0, 0.0, 0.0, 7.0], [0, 0, 0, 1]],
        dtype=float,
    )
    image = nib.Nifti1Image(data, affine)
    world = nib.affines.apply_affine(affine, np.array([[2, 1, 4], [0, 0, 0]], dtype=float))
    assert sample_nearest(image, world).tolist() == [1, 0]


def test_section_plane_samples_exact_world_y_without_voxel_center_coincidence():
    data = np.zeros((5, 3, 5), dtype=np.uint8)
    data[2, 1, 3] = 1
    image = nib.Nifti1Image(data, np.diag([2.0, 2.0, 2.0, 1.0]))
    section = {
        "bounds_mm": {"min_x": 0.0, "max_x": 8.0, "min_z": 0.0, "max_z": 8.0},
        "section_plane_y_mm": 2.4,
    }
    result = sample_section_plane(image, section, spacing_mm=2.0)
    assert result["status"] == "exact_plane_nonzero"
    assert result["nonzero_pixels"] > 0
    assert result["plane_y_mm"] == 2.4
