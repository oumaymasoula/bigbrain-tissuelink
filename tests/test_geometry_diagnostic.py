import nibabel as nib
import numpy as np

from geometry_diagnostic import render_world_grid_pair, sample_world_xz_grid


def test_full_affine_sampling_uses_asymmetric_axis_permuting_landmarks(tmp_path):
    data = np.zeros((4, 2, 5), dtype=np.uint16)
    for x in range(4):
        for y in range(2):
            for z in range(5):
                data[x, y, z] = 1000 + 100 * x + 10 * y + z
    # Source x/z are permuted into world x/z, with an off-diagonal x/z term.
    affine = np.array([[0.0, 0.0, 0.5, 10.0], [0.0, 0.2, 0.0, -1.0], [0.4, 0.0, 0.1, 20.0], [0, 0, 0, 1]], dtype=float)
    image = nib.Nifti1Image(data, affine)
    x_axis = np.array([10.5, 11.0])
    z_axis = np.array([20.5, 21.0])
    sampled, meta = sample_world_xz_grid(image, -0.8, x_axis, z_axis)
    # (u=0,v=0) is source (x=1,y=1,z=1); (u=1,v=1) is source (2,1,2).
    assert sampled[0, 0] == 1111
    assert sampled[1, 1] == 1212
    assert meta["source_affine"] == affine.tolist()
    assert meta["sampling"].startswith("full inverse affine")


def test_rendered_pair_marks_same_off_centre_grid_pixel(tmp_path):
    first = np.zeros((5, 7), dtype=np.uint8)
    second = np.zeros((5, 7), dtype=np.uint8)
    paths = render_world_grid_pair(first, second, np.arange(7.0), np.arange(5.0), (5.0, 1.0), tmp_path)
    assert set(paths) == {
        "registered", "histology", "paired", "checkerboard", "opacity",
        "registered_clean", "histology_clean",
    }
    assert all((tmp_path / name).exists() for name in (
        "registered_world_grid_selected.png",
        "histology_world_grid_selected.png",
        "paired_world_grid_selected.png",
    ))
