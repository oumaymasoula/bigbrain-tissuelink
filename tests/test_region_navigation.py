import nibabel as nib
import numpy as np

from region_navigation import (
    central_nonzero_display_pixel,
    mask_plane_intersects,
    overlay_mask_on_section_display,
    sample_mask_to_section_display,
)
from registered_section_demo import section_display_array


def test_region_mask_intersection_requires_nonzero_voxel():
    empty = nib.Nifti1Image(np.zeros((3, 2, 4), dtype=np.uint8), np.eye(4))
    filled = nib.Nifti1Image(np.zeros((3, 2, 4), dtype=np.uint8), np.eye(4))
    filled_data = np.asanyarray(filled.dataobj)
    filled_data[2, 0, 3] = 1
    filled = nib.Nifti1Image(filled_data, np.eye(4))
    assert not mask_plane_intersects(empty)
    assert mask_plane_intersects(filled)


def test_mask_overlay_uses_full_affines_and_section_xz_display_convention():
    section = nib.Nifti1Image(np.zeros((5, 1, 7), dtype=np.uint8), np.eye(4))
    mask_affine = np.array(
        [[0, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1]], dtype=float
    )
    mask_data = np.zeros((7, 1, 5), dtype=np.uint8)
    mask_data[4, 0, 3] = 1  # world=(3,0,4), section display u=z=4, v=x=3
    mask = nib.Nifti1Image(mask_data, mask_affine)
    overlay = overlay_mask_on_section_display(mask, section, np.zeros((5, 7), dtype=np.uint8))
    assert tuple(overlay[3, 4]) == (255, 55, 55)


def test_exact_plane_sampler_uses_non_square_display_and_full_affines():
    # Source section is x/y/z=(4, 2, 6); the display is deliberately resized
    # to a non-square (5, 9) image with horizontal=z and vertical=x.
    section_affine = np.array(
        [[1.0, 0.0, 0.25, 10.0], [0.1, 1.0, 0.2, -5.0], [0.0, 0.0, 2.0, 20.0], [0, 0, 0, 1]],
        dtype=float,
    )
    section = nib.Nifti1Image(np.zeros((4, 2, 6), dtype=np.uint8), section_affine)
    # Mask voxel (x=2,y=1,z=4) is the known landmark. Its world point is
    # sampled by the section grid at the exact section plane Y= -3.1.
    world = section_affine @ np.array([2.0, 1.0, 4.0, 1.0])
    mask_affine = np.array(
        [[0.0, 0.0, 1.0, world[0] - 4.0], [0.0, 1.0, 0.0, world[1] - 1.0], [1.0, 0.0, 0.0, world[2] - 2.0], [0, 0, 0, 1]],
        dtype=float,
    )
    mask_data = np.zeros((5, 3, 5), dtype=np.uint8)
    mask_data[2, 1, 4] = 1
    mask = nib.Nifti1Image(mask_data, mask_affine)
    sampled, metadata = sample_mask_to_section_display(mask, section, float(world[1]), (5, 9))
    assert sampled.shape == (5, 9)
    assert metadata["interpolation"] == "nearest-neighbor categorical"
    pixel = central_nonzero_display_pixel(sampled)
    assert pixel is not None
    # The known source landmark maps to display u=z and v=x after resizing.
    assert pixel == (round(4 * 8 / 5), round(2 * 4 / 3))
    assert sampled[pixel[1], pixel[0]] == 1


def test_slab_overlap_is_not_exact_plane_intersection():
    section = nib.Nifti1Image(np.zeros((3, 3, 3), dtype=np.uint8), np.eye(4))
    mask_data = np.zeros((3, 3, 3), dtype=np.uint8)
    mask_data[1, 1, 1] = 1
    mask = nib.Nifti1Image(mask_data, np.eye(4))
    # A slab around Y=1 contains the voxel, but a plane at Y=1.49 is
    # categorized by nearest-neighbour at Y=1 only if its samples land there;
    # at Y=1.51 they correctly land on the empty Y=2 plane.
    sampled, metadata = sample_mask_to_section_display(mask, section, 1.51, (3, 3))
    assert mask_plane_intersects(mask)
    assert metadata["exact_plane_nonzero_pixels"] == 0
    assert not np.any(sampled)


def test_actual_section_renderer_preserves_asymmetric_landmark_axes():
    data = np.zeros((4, 1, 6), dtype=np.uint16)
    data[2, 0, 4] = 123
    image = nib.Nifti1Image(data, np.eye(4))
    displayed, mapping = section_display_array(image)
    assert displayed.shape == (6, 4)
    assert displayed[4, 2] == 255
    assert displayed[0, 0] == 0
    assert mapping["display_horizontal_source_axis"] == "z"
    assert mapping["display_vertical_source_axis"] == "x"
    assert mapping["transpose"] is True
