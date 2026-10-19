import numpy as np

from display_utils import rgb_with_crosshair
from selection_sync import invalidate_current_selection, selection_sync_report


def test_off_centre_selection_report_uses_same_world_point_and_fetch_bounds():
    section_point = {
        "display_pixel_uv": [137.25, 82.5],
        "world_xyz_mm": [-31.125, -0.8595, 22.75],
    }
    bounds = {
        "min_x": -32.125,
        "min_y": -0.8695,
        "min_z": 21.75,
        "max_x": -30.125,
        "max_y": -0.8495,
        "max_z": 23.75,
    }
    report = selection_sync_report(section_point, [-31.125, -0.8595, 22.75], bounds)
    assert report["clicked_section_pixel_uv"] == [137.25, 82.5]
    assert report["same_current_world_point"] is True
    assert report["next_fetch_bounds_mm"] == list(bounds.values())


def test_new_selection_invalidates_patch_but_preserves_collection():
    state = {
        "volume_viewer_section_point": {"world_xyz_mm": [1, 2, 3]},
        "volume_viewer_registered_patch": object(),
        "volume_viewer_registered_signature": object(),
        "patch_collection": {"patch-keep": object()},
        "current_section_selection_world": [4, 5, 6],
    }
    invalidate_current_selection(state)
    assert "volume_viewer_section_point" not in state
    assert "volume_viewer_registered_patch" not in state
    assert "volume_viewer_registered_signature" not in state
    assert "patch-keep" in state["patch_collection"]
    assert "current_section_selection_world" not in state


def test_rendered_non_square_overlay_uses_uv_columns_and_rows():
    # Exercise the actual RGB overlay path, not only inverse coordinate helpers.
    source = np.zeros((7, 5), dtype=np.uint8)
    rendered = rgb_with_crosshair(source, u=3, v=5)
    assert rendered.shape == (7, 5, 3)
    assert np.all(rendered[:, 3, :] == [255, 255, 0])
    assert np.all(rendered[5, :, :] == [255, 255, 0])
    assert rendered[1, 1].tolist() == [0, 0, 0]
