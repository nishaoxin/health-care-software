"""Small reference functions; not a clinical measurement library."""
from __future__ import annotations

import math
from collections.abc import Sequence


def _point(value: Sequence[float]) -> tuple[float, float] | None:
    try:
        if len(value) != 2:
            return None
        x, y = float(value[0]), float(value[1])
        return (x, y) if math.isfinite(x) and math.isfinite(y) else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalized_to_pixels(point: Sequence[float], width: int, height: int) -> tuple[float, float] | None:
    """Restore equal x/y units before measuring angles in a non-square image."""
    p = _point(point)
    if p is None or width <= 0 or height <= 0:
        return None
    return p[0] * width, p[1] * height


def angle_deg(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float | None:
    """Return the unsigned internal angle at B, or None for invalid geometry."""
    points = [_point(p) for p in (a, b, c)]
    if any(p is None for p in points):
        return None
    aa, bb, cc = points
    assert aa is not None and bb is not None and cc is not None
    u = (aa[0] - bb[0], aa[1] - bb[1])
    v = (cc[0] - bb[0], cc[1] - bb[1])
    denom = math.hypot(*u) * math.hypot(*v)
    if denom <= 1e-12:
        return None
    cosine = (u[0] * v[0] + u[1] * v[1]) / denom
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def knee_flexion_projection_deg(hip: Sequence[float], knee: Sequence[float], ankle: Sequence[float]) -> float | None:
    """180-internal-angle convention; does not measure signed hyperextension."""
    internal = angle_deg(hip, knee, ankle)
    return None if internal is None else 180.0 - internal


def observed_interval_s(
    previous_time_s: float,
    current_time_s: float,
    previous_state: str,
    current_state: str,
    *,
    same_track: bool,
    previous_valid: bool,
    current_valid: bool,
    max_gap_s: float = 0.5,
) -> float:
    """Conservative valid observation duration, not inferred time out of view.

    Callers must also invalidate continuity on sequence/epoch changes and must
    not equate a camera track with a person's cross-camera identity.
    """
    if not (same_track and previous_valid and current_valid):
        return 0.0
    if previous_state != current_state or current_state in {"UNKNOWN", "OFFLINE", "PAUSED"}:
        return 0.0
    try:
        dt = float(current_time_s) - float(previous_time_s)
        if not all(math.isfinite(v) for v in (previous_time_s, current_time_s, max_gap_s)):
            return 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return dt if 0.0 < dt <= max_gap_s else 0.0
