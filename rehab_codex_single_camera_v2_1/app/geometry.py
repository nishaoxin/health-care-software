from __future__ import annotations

import math
from geometry_reference import angle_deg, knee_flexion_projection_deg, observed_interval_s
from camera_reference import display_to_raw_normalized


def in_roi(point, roi):
    if point is None or roi is None or len(roi) != 4:
        return False
    x, y = point
    x1, y1, x2, y2 = roi
    return x1 <= x <= x2 and y1 <= y <= y2


def valid_roi(roi):
    return (isinstance(roi, (tuple, list)) and len(roi) == 4 and
            all(isinstance(x, (int, float)) and math.isfinite(x) for x in roi) and
            0 <= roi[0] < roi[2] <= 1 and 0 <= roi[1] < roi[3] <= 1 and
            roi[2] - roi[0] >= .02 and roi[3] - roi[1] >= .02)


def compatible_reports(a, b):
    keys = ('scene_id', 'exercise_id', 'side', 'profile_id', 'profile_version',
            'source_ref', 'source_kind', 'usage_context', 'rule_version', 'model_manifest_id',
            'preprocess_version', 'preprocessing_hash', 'plan_hash', 'participant_id')
    return all(a.get(k) is not None and a.get(k) == b.get(k) for k in keys)
