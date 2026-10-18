import numpy as np
import pytest

from bigbrain_cutout import Bounds, map_preview_rect_to_source, map_source_bounds_to_preview_rect


def test_invalid_bounds_rejected():
    with pytest.raises(ValueError):
        Bounds(1, 0, 0, 0, 1, 1).validate()


def test_nan_bounds_rejected():
    with pytest.raises(ValueError):
        Bounds(np.nan, 0, 0, 1, 1, 1).validate()


def test_budget_is_explicit():
    from bigbrain_cutout import MAX_BYTES
    assert MAX_BYTES == 10 * 1024 * 1024


def test_preview_rectangle_maps_all_four_edges():
    affine = np.array([[0.1, 0, 0, -20], [0, 0.02, 0, -0.87], [0, 0, 0.2, -10], [0, 0, 0, 1]], dtype=float)
    mapped = map_preview_rect_to_source({"left": 5, "top": 2, "width": 10, "height": 4}, affine, (100, 1, 200), (50, 25))
    assert mapped[:4] == pytest.approx((-19.2, -6.0, -17.6, 2.0))
    assert len(mapped[4]) == 4


def test_source_bounds_round_trip_through_zoomed_view():
    affine = np.array([[0.1, 0, 0, -20], [0, 0.02, 0, -0.87], [0, 0, -0.2, 10], [0, 0, 0, 1]], dtype=float)
    source_bounds = (-19.2, -6.0, -17.6, 2.0)
    rect = map_source_bounds_to_preview_rect(source_bounds, affine, (100, 1, 200), (50, 25), view_origin=(10, 5), view_size=(25, 12.5), canvas_size=(50, 25))
    mapped = map_preview_rect_to_source(rect, affine, (100, 1, 200), (50, 25), view_origin=(10, 5), view_size=(25, 12.5), canvas_size=(50, 25))
    assert mapped[:4] == pytest.approx(source_bounds)
