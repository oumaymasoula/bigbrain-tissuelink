import numpy as np
import nibabel as nib

from volume_alignment import common_world_bounds, display_pixel_to_world, native_neighbourhood_crop, nearest_voxel_for_world, world_bounds


def test_display_pixel_to_world_uses_explicit_x_z_axes_without_flip():
    pixels, world = display_pixel_to_world(
        np.asarray([-10.0, -9.8, -9.6]), np.asarray([4.0, 4.2, 4.4]), -25.0, (1.2, 0.1)
    )
    assert pixels == [1, 0]
    assert world == [-9.8, -25.0, 4.0]


def test_common_world_bounds_uses_voxel_centres():
    first = nib.Nifti1Image(np.zeros((3, 3, 3), dtype=np.float32), np.diag([1, 1, 1, 1]))
    second = nib.Nifti1Image(np.zeros((3, 3, 3), dtype=np.float32), np.array([[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float))
    assert world_bounds(first)["min"] == [0.0, 0.0, 0.0]
    assert common_world_bounds([first, second]) == {"min": [1.0, 0.0, 0.0], "max": [2.0, 2.0, 2.0]}


def test_nearest_voxel_reports_actual_displayed_center():
    image = nib.Nifti1Image(np.zeros((5, 5, 5), dtype=np.float32), np.diag([2, 2, 2, 1]))
    index, center = nearest_voxel_for_world(image, np.array([2.9, 4.1, 6.0]))
    assert index.tolist() == [1, 2, 3]
    np.testing.assert_allclose(center, [2, 4, 6])


def test_native_neighbourhood_crop_translates_affine_and_preserves_values():
    data = np.arange(5 * 4 * 6, dtype=np.float32).reshape(5, 4, 6)
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    image = nib.Nifti1Image(data, affine)
    crop, info = native_neighbourhood_crop(image, np.array([4.0, 6.0, 8.0]), 2.0)
    np.testing.assert_array_equal(np.asanyarray(crop.dataobj), data[1:4, 2:3, 1:4])
    np.testing.assert_allclose(crop.affine, affine @ np.array([[1, 0, 0, 1], [0, 1, 0, 2], [0, 0, 1, 1], [0, 0, 0, 1]], dtype=float))
    assert info["crop_shape_xyz"] == [3, 1, 3]
