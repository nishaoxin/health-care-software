"""Preview-only, observed comfort baselines; never clinical limits or goals."""
from __future__ import annotations

import math
from statistics import median

from .quality import angle_delta


def validate_start_value(plan, value):
    if plan['exercise_id'] == 'shoulder_adduction':
        # Engineering feasibility: the outbound threshold must fit below the
        # start angle and outside the existing +/-5 degree return band. This
        # is not a prescribed arm-raising angle or a clinical normal range.
        if value <= plan['raising_delta_deg'] + 5.:
            raise ValueError('当前起点接近垂臂，无法区分内收与回位；请先舒适侧抬臂再记录起点。'
                             '若舒适幅度不足，不要勉强扩大动作。')


def stable_preview_value(history, metric, *, now_time, track_key, circular=False):
    # Require a continuous suffix. Filtering out missing samples would falsely
    # make an occluded/unstable posture look like a one-second hold.
    run = []
    for observation in history:
        value = observation.value(metric)
        if (observation.status != 'VALID' or observation.track_key != track_key or value is None or
                not math.isfinite(value) or not -1e-8 <= now_time-observation.time_s <= 1.2+1e-8):
            run = []
            continue
        if run and not 0 < observation.time_s-run[-1][0] <= .5:
            run = []
        run.append((observation.time_s, value))
    if len(run) < 5 or run[-1][0]-run[0][0] < .8-1e-8 or now_time-run[-1][0] > .3:
        raise ValueError('请让所测关节清楚可见，在舒适姿势稳定保持约 1 秒后记录')
    reference = run[0][1]
    values = [reference+angle_delta(v, reference) if circular else v for _, v in run]
    if max(values)-min(values) > 6:
        raise ValueError('关节画面尚不稳定；请保持舒适姿势，不要追求最大幅度')
    value = median(values)
    return angle_delta(value, 0) if circular else value


def provenance(controller):
    plan, pose = controller.setup['plan'], controller.latest_pose
    return {'source_ref': controller.source['ref'], 'source_kind': controller.context.source_kind,
            'usage_context': controller.context.usage_context, 'preview_epoch': controller.context.epoch,
            'frame_size': list(pose.size), 'schema_id': pose.schema_id,
            'model_manifest_id': pose.model_manifest_id, 'track_key': controller.latest_observation.track_key,
            'exercise_id': plan['exercise_id'],
            'side': plan['side'], 'view': controller.setup['view'], 'participant_id': plan['participant_id']}
