from pathlib import Path

import numpy as np

from display_utils import has_intensity_variation, rgb_with_crosshair


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_volume_viewer_navigation_targets_are_registered_pages():
    targets = ("volume_viewer.py", "pages/1_Validation.py")
    assert all((PROJECT_ROOT / target).is_file() for target in targets)


def test_shared_navigation_defines_only_the_two_intended_pages():
    source = (PROJECT_ROOT / "navigation.py").read_text()
    assert "st.navigation" in source
    assert 'st.Page("volume_viewer.py"' in source
    assert 'st.Page("pages/1_Validation.py"' in source
    assert 'title="MRI–Histology Explorer"' in source
    assert 'title="Alignment review (advanced)"' in source
    assert "st.page_link" not in source
    assert 'app.py' not in source


def test_page_content_has_no_competing_navigation_menu():
    for filename in ("volume_viewer.py", "pages/1_Validation.py"):
        source = (PROJECT_ROOT / filename).read_text()
        assert "st.page_link" not in source
        assert "st.navigation" not in source


def test_explorer_uses_catalogued_registered_sections():
    source = (PROJECT_ROOT / "volume_viewer.py").read_text()
    assert "section_catalogue" in source
    assert "Choose a registered section" in source
    assert "explore_registered = True" in source
    assert 'key="explore-registered"' not in source
    assert "real_fetch_verification_status" in (PROJECT_ROOT / "bigbrain_cutout.py").read_text()
    assert "Navigate to nearby section" in source
    assert 'streamlit_image_coordinates(selection_display' in source
    assert 'st.image(overview_marked' not in source
    assert "map_source_bounds_to_preview_rect" in source
    assert 'st.session_state.pop("volume_viewer_registered_patch", None)' in source


def test_reopen_location_restores_saved_world_y_slice():
    source = (PROJECT_ROOT / "volume_viewer.py").read_text()
    assert 'st.session_state.world_y_slice = float(pending_location["y"])' in source
    assert 'st.session_state.pending_location = {"x": point[0], "y": point[1], "z": point[2]}' in source


def test_rgb_registered_overview_can_receive_display_crosshair():
    """RGB provider overviews use a display adapter, not the scientific array path."""
    rgb = np.zeros((782, 900, 3), dtype=np.uint8)
    rgb[..., 0] = 17
    marked = rgb_with_crosshair(rgb, 450, 391)

    assert marked.shape == rgb.shape
    assert marked.dtype == np.uint8
    np.testing.assert_array_equal(marked[0, 0], [17, 0, 0])
    np.testing.assert_array_equal(marked[391, 450], [255, 255, 0])


def test_constant_provider_patch_is_not_treated_as_tissue():
    assert not has_intensity_variation(np.full((63, 1, 251), 255, dtype=np.uint8))
    assert has_intensity_variation(np.array([[[0, 255]]], dtype=np.uint8))


def test_registered_overview_click_is_deduplicated_before_fetch_button():
    source = (PROJECT_ROOT / "volume_viewer.py").read_text()
    assert "volume_viewer_last_section_click" in source
    assert "section_click_key != st.session_state.get(\"volume_viewer_last_section_click\")" in source
