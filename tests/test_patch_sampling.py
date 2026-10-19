import pytest

from patch_sampling import (
    MAX_PATCH_COUNT,
    PatchSizeXZ,
    RectangleXZ,
    estimated_bytes_per_patch,
    footprint_bounds,
    generate_regular_grid,
    generate_seeded_random,
    plan_metadata,
    validate_centres,
)


def rectangle():
    return RectangleXZ(-4.0, 10.0, 4.0, 18.0)


def size():
    return PatchSizeXZ(2.0, 2.0)


def test_regular_grid_is_deterministic_bounded_and_records_centres():
    centres = generate_regular_grid(rectangle(), size(), 2.0, 4.0)
    assert centres == [(-3.0, 11.0), (-3.0, 15.0), (-1.0, 11.0), (-1.0, 15.0), (1.0, 11.0), (1.0, 15.0), (3.0, 11.0), (3.0, 15.0)]
    metadata = plan_metadata("regular_grid", rectangle(), size(), centres, 0.1, spacing_x=2.0, spacing_z=4.0)
    assert metadata["centres_xz_mm"] == [[-3.0, 11.0], [-3.0, 15.0], [-1.0, 11.0], [-1.0, 15.0], [1.0, 11.0], [1.0, 15.0], [3.0, 11.0], [3.0, 15.0]]


def test_seeded_random_replays_exactly_and_stays_inside_edges():
    first = generate_seeded_random(rectangle(), size(), 4, seed=123)
    second = generate_seeded_random(rectangle(), size(), 4, seed=123)
    assert first == second
    assert len(set(first)) == 4
    for x, z in first:
        assert -3.0 <= x <= 3.0
        assert 11.0 <= z <= 17.0


def test_limits_bounds_duplicates_and_estimate_are_explicit():
    with pytest.raises(ValueError, match="does not fit"):
        generate_seeded_random(rectangle(), PatchSizeXZ(9.0, 2.0), 1, seed=1)
    with pytest.raises(ValueError, match="between 1"):
        generate_seeded_random(rectangle(), size(), MAX_PATCH_COUNT + 1, seed=1)
    bounds = footprint_bounds((0.0, 14.0), size(), -0.87, -0.85)
    assert bounds == {"min_x": -1.0, "min_y": -0.87, "min_z": 13.0, "max_x": 1.0, "max_y": -0.85, "max_z": 15.0}
    assert estimated_bytes_per_patch(size(), 0.1, 0.02) == 400
    with pytest.raises(ValueError, match="duplicate"):
        validate_centres([(0.0, 1.0), (0.0, 1.0)])
