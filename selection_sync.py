"""Pure helpers for detailed-section selection state and diagnostics."""
from __future__ import annotations

import numpy as np


CURRENT_SELECTION_KEYS = (
    "volume_viewer_section_point",
    "volume_viewer_registered_patch",
    "volume_viewer_registered_signature",
)


def invalidate_current_selection(state: dict) -> None:
    """Remove only the active selection and result, preserving collections."""
    for key in CURRENT_SELECTION_KEYS:
        state.pop(key, None)
    # Do not retain the display-only point after a new reference click.
    state.pop("current_section_selection_world", None)


def selection_sync_report(section_point: dict, lower_marker_world: list[float], fetch_bounds: dict) -> dict:
    """Describe the exact point and bounds used by the current render/fetch."""
    mapped_world = [float(value) for value in section_point["world_xyz_mm"]]
    lower_world = [float(value) for value in lower_marker_world]
    return {
        "clicked_section_pixel_uv": [float(value) for value in section_point["display_pixel_uv"]],
        "mapped_section_world_xyz_mm": mapped_world,
        "lower_reconstruction_marker_world_xyz_mm": lower_world,
        "next_fetch_bounds_mm": [float(value) for value in fetch_bounds.values()],
        "same_current_world_point": bool(np.allclose(mapped_world, lower_world, atol=1e-6, rtol=0.0)),
    }
