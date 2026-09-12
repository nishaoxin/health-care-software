"""Preview-only, observed comfort baselines; never clinical limits or goals."""
from __future__ import annotations

import copy
import math
from statistics import median

from .quality import angle_delta

# A baseline may be reused only while every condition a person can re-verify on
# screen is unchanged. A tracker id is explicitly not an identity and a new
# preview epoch is not a new posture, so neither may force a repeat recording;
# the explicit final acknowledgement still covers "same person, same position".
REUSABLE_CONDITIONS = ('source_ref', 'source_kind', 'usage_context', 'frame_size', 'schema_id',
                       'model_manifest_id', 'exercise_id', 'side', 'view', 'participant_id')


def validate_start_value(plan, value):
    if plan['exercise_id'] == 'shoulder_adduction':
        # Engineering feasibility: the outbound threshold must fit below the
        # start angle and outside the existing +/-5 degree return band. This
        # is not a prescribed arm-raising angle or a clinical normal range.
        if value <= plan['raising_delta_deg'] + 5.:
            raise ValueError('当前起点接近垂臂，无法区分内收与回位；请先舒适侧抬臂再记录起点。'
                             '若舒适幅度不足，不要勉强扩大动作。')


def stable_preview_value(history, metric, *, now_time, track_key, circular=False, tolerance=6):
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
    if max(values)-min(values) > tolerance:
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


def stable_conditions(record):
    """The reusable subset of a provenance or binding, or None when incomplete."""
    if not isinstance(record, dict) or any(record.get(key) in (None, '') for key in REUSABLE_CONDITIONS):
        return None
    result = {key: copy.deepcopy(record[key]) for key in REUSABLE_CONDITIONS}
    if 'auxiliary' in record:
        auxiliary = record['auxiliary'] if isinstance(record['auxiliary'], dict) else {}
        result['auxiliary'] = {key: copy.deepcopy(auxiliary.get(key)) for key in ('frame_size', 'source_ref')}
    return result


def same_conditions(left, right):
    """True only with complete, matching evidence on both sides."""
    recorded = stable_conditions(left)
    return recorded is not None and recorded == stable_conditions(right)


def preparation_binding(controller):
    c = controller
    if c.context is None or c.latest_pose is None or c.latest_observation is None:
        return None
    binding = provenance(c)
    if c.dual_config:
        auxiliary = c.latest_pose.paired_pose
        obs = c.latest_secondary_observation
        binding['auxiliary'] = dict(track_key=obs.track_key if obs else None,
                                    frame_size=list(auxiliary.size) if auxiliary else None,
                                    source_ref=auxiliary.context.source_ref if auxiliary else None)
    return binding
