from pathlib import Path


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
