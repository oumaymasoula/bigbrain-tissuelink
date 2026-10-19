import nibabel as nib
import numpy as np

from registered_section_demo import map_section_pixel_to_world, map_section_world_to_pixel, world_to_grid_pixel


def test_section_display_mapping_preserves_xz_axis_order_and_centres():
    image = nib.Nifti1Image(
        np.zeros((5, 2, 7), dtype=np.uint8),
        np.array([[0.2, 0, 0, -10], [0, 0.02, 0, -1], [0, 0, 0.3, 20], [0, 0, 0, 1]], dtype=float),
    )
    mapped = map_section_pixel_to_world(image, (6, 4), (7, 5), -0.98)
    assert mapped["source_voxel_xyz_continuous"] == [4.0, 1.0, 6.0]
    assert np.allclose(mapped["world_xyz_mm"], [-9.2, -0.98, 21.8])
    assert mapped["transpose"] is True
    assert mapped["flip_x"] is False
    assert mapped["flip_z"] is False


def test_world_to_grid_pixel_uses_nearest_pixel_without_axis_swap():
    x_axis = np.array([-2.0, -1.0, 0.0, 1.0])
    z_axis = np.array([10.0, 11.0, 12.0])
    assert world_to_grid_pixel((-0.6, 11.6), x_axis, z_axis) == (1, 2)
    assert world_to_grid_pixel((-20.0, 30.0), x_axis, z_axis) == (0, 2)


def test_section_world_to_display_mapping_round_trips_asymmetric_point():
    image = nib.Nifti1Image(
        np.zeros((5, 2, 7), dtype=np.uint8),
        np.array([[0.2, 0, 0, -10], [0, 0.02, 0, -1], [0, 0, 0.3, 20], [0, 0, 0, 1]], dtype=float),
    )
    world = [-9.4, -0.98, 20.9]
    mapped = map_section_world_to_pixel(image, world, (700, 500))
    round_trip = map_section_pixel_to_world(image, mapped["display_pixel_uv"], (700, 500), world[1])
    assert np.allclose(round_trip["world_xyz_mm"], world)
