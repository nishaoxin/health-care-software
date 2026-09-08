"""Read-only personal assessment summaries derived from saved session payloads.

An item is the latest ended attempt for one exercise/anatomical side. Failed
attempts replace the current result; historical successes are never substituted.
No cross-session angle averages, clinical scores, or automatic targets are made.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import math
import re
from statistics import median

from .domain import clean_json, digest
from .exercises import exercise_spec, EXERCISE_IDS, UNSUPPORTED_COVERAGE


STATUS_LABELS = {'ASSESSED': '已评估', 'NOT_ASSESSED': '未评估', 'UNAVAILABLE': '本次不可用'}
COMPARISON_NOTE = '仅为已观察到的二维投影测量；模型、机位、动作、侧别或规则条件不同，不宜直接比较。'


def finite_number(value):
    """Missing/nonfinite/boolean values are never measurements or counts."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def anonymous_participant(participant_id):
    if not isinstance(participant_id, str) or not participant_id.strip():
        return None
    if re.fullmatch(r'anon-[0-9a-f]{16}', participant_id):
        return participant_id
    return 'anon-' + digest({'participant_id': participant_id})[:16]


def _config(session):
    return session.get('config_snapshot') or {}


def session_value(session, key):
    # A present null is an explicit missing value, not permission to use a default.
    if key in session:
        return session[key]
    return (_config(session).get('plan') or {}).get(key)


def session_conditions(session):
    """Keep provenance, including unknown conditions, without deriving identity."""
    config = _config(session)
    keys = ('source_ref', 'profile_id', 'profile_version', 'time_basis', 'model_manifest_id',
            'schema_id', 'keypoint_order_version', 'coordinate_space', 'rule_version',
            'preprocess_version', 'preprocessing_hash', 'pose_backend', 'target_kind', 'measurement_contract')
    result = {key: session.get(key, config.get(key)) for key in keys}
    result.update(view=session.get('view', config.get('view')),
                  placement_revision=session.get('placement_revision', config.get('placement_revision')),
                  actual_size=(session.get('actual_capture') or {}).get('size'),
                  backend=session.get('backend'))
    return clean_json(copy.deepcopy(result))


def _angle_bounds(primary_metric):
    # Hip abduction is signed; an observed adduction/stance offset may be negative.
    return (-180, 180) if primary_metric == 'hip_abduction_deg' or primary_metric.endswith('_excursion_deg') else (0, 180)


def _valid_range(value, primary_metric):
    if not isinstance(value, dict):
        return None
    low, high, span = (finite_number(value.get(k)) for k in ('min_deg', 'max_deg', 'range_deg'))
    if low is None or high is None or span is None:
        return None
    lower_bound, upper_bound = _angle_bounds(primary_metric)
    if not lower_bound <= low <= high <= upper_bound or span < 0 or not math.isclose(high-low, span, abs_tol=.2):
        return None
    return {'min_deg': low, 'max_deg': high, 'range_deg': span}


def _legacy_range(session, primary_metric):
    """Use medians of three consecutive valid samples; never bridge missing data.

    This is a report-time statistic, distinct from the original engine output.
    A solitary noisy peak, a repetition count or the last metric cannot be a ROM.
    """
    windows, run = [], []
    previous_time = None
    plan = _config(session).get('plan') or {}
    max_gap = finite_number(plan.get('max_gap_s'))
    max_gap = max_gap if max_gap is not None and max_gap > 0 else .5
    lower_bound, upper_bound = _angle_bounds(primary_metric)
    for row in session.get('metrics') or []:
        if not isinstance(row, dict):
            run, previous_time = [], None
            continue
        metric = (row.get('metrics') or {}).get(primary_metric) or {}
        value = finite_number(metric.get('value')) if isinstance(metric, dict) and metric.get('valid') is True else None
        t = finite_number(row.get('time_s'))
        if (row.get('observation_status') not in ('VALID', 'PARTIAL_OBSERVABLE')
                or value is None or not lower_bound <= value <= upper_bound
                or row.get('annotation_origin') == 'human'):
            run, previous_time = [], None
            continue
        if t is not None and previous_time is not None and (t <= previous_time or t-previous_time > max_gap):
            run = []
        previous_time = t
        run.append(value)
        if len(run) >= 3:
            windows.append(median(run[-3:]))
    if not windows:
        return None
    low, high = min(windows), max(windows)
    return {'min_deg': low, 'max_deg': high, 'range_deg': high-low}


def session_motion_range(session):
    """Return (range or None, evidence source or None), compatible with old saves."""
    summary = session.get('summary') or {}
    exercise_id = session_value(session, 'exercise_id')
    if exercise_id not in EXERCISE_IDS:
        return None, None
    spec = exercise_spec(exercise_id)
    primary = summary.get('primary_metric') or spec['metric']
    # A renamed/unrecognised metric cannot silently acquire this action's meaning.
    if primary != spec['metric']:
        return None, None
    ratio = finite_number(summary.get('valid_ratio'))
    if ratio is not None and not 0 < ratio <= 1:
        return None, None
    if 'motion_range' in summary:
        if summary.get('motion_range_valid') is False:
            return None, None
        if 'valid_sample_count' in summary:
            sample_count = finite_number(summary['valid_sample_count'])
            if sample_count is None or sample_count < 3:
                return None, None
        result = _valid_range(summary['motion_range'], primary)
        return (result, 'summary') if result is not None else (None, None)
    result = _legacy_range(session, primary)
    return (result, 'metrics') if result is not None else (None, None)


def _time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _ended(session):
    end = _time(session.get('end_utc'))
    start = _time(session.get('start_utc'))
    return (session.get('status') in ('FINISHED', 'INTERRUPTED', 'COMPLETED')
            and end is not None and (start is None or end >= start))


def _count(summary, key):
    value = finite_number(summary.get(key))
    return int(value) if value is not None and value >= 0 and value == int(value) else None


def _issues(session):
    result = []
    for rep in session.get('repetitions') or []:
        for issue in rep.get('issues') or []:
            if not isinstance(issue, dict):
                continue
            evidence = copy.deepcopy(issue)
            evidence.update(session_id=session.get('id'), repetition_number=rep.get('number'))
            result.append(evidence)
    return clean_json(result)


def build_body_profile(sessions, participant_id, source_kind='LIVE_CAMERA', usage_context='SELF_USE') -> dict:
    """Produce the current exercise registry × two sides for one person/source/use.

    ``participant_id`` is an explicit local identifier, never a pose track ID.
    Consumers must use ``participant_label`` for display. Missing IDs match no one.
    ``conditions`` describe each source record; no comparability is presumed.
    """
    selected = {}
    if isinstance(participant_id, str) and participant_id.strip():
        for session in sessions:
            if (not isinstance(session, dict) or session.get('scene_id') != 'rehab'
                    or session_value(session, 'submode') != 'assessment'
                    or session_value(session, 'participant_id') != participant_id
                    or session.get('source_kind') != source_kind
                    or session.get('usage_context') != usage_context or not _ended(session)):
                continue
            key = session_value(session, 'exercise_id'), session_value(session, 'side')
            if key[0] not in EXERCISE_IDS or key[1] not in ('left', 'right'):
                continue
            # Latest end time, then start/id for deterministic ordering of unsorted input.
            order = (_time(session['end_utc']), _time(session.get('start_utc')) or _time(session['end_utc']), str(session.get('id', '')))
            if key not in selected or order > selected[key][0]:
                selected[key] = order, session
    items = []
    for exercise_id in EXERCISE_IDS:
        spec = exercise_spec(exercise_id)
        for side in ('left', 'right'):
            item = {'exercise_id': exercise_id, 'exercise_label': spec['label'], 'joint': spec['joint'],
                    'side': side, 'primary_metric': spec['metric'], 'primary_metric_label': spec['metric_label'],
                    'status': 'NOT_ASSESSED', 'reason': '尚无当前参与者、来源和使用情境的已结束评估',
                    'session_id': None, 'session_status': None, 'stop_reason': None,
                    'start_utc': None, 'end_utc': None, 'conditions': {},
                    'valid_ratio': None, 'completed': None, 'partial': None, 'invalid': None,
                    'motion_range': None, 'motion_range_source': None, 'issues': [],
                    'experimental': spec['experimental'], 'measurement_note': spec['guide']}
            entry = selected.get((exercise_id, side))
            if entry is not None:
                session = entry[1]
                summary = session.get('summary') or {}
                motion_range, evidence_source = session_motion_range(session)
                ratio = finite_number(summary.get('valid_ratio'))
                item.update(session_id=session.get('id'), start_utc=session.get('start_utc'), end_utc=session.get('end_utc'),
                            session_status=session.get('status'), stop_reason=session.get('stop_reason'),
                            conditions=session_conditions(session), valid_ratio=ratio if ratio is not None and 0 <= ratio <= 1 else None,
                            completed=_count(summary, 'completed'), partial=_count(summary, 'partial'), invalid=_count(summary, 'invalid'),
                            motion_range=motion_range, motion_range_source=evidence_source, issues=_issues(session))
                if motion_range is not None and session.get('id'):
                    item.update(status='ASSESSED', reason=None)
                else:
                    # Legacy saves lacking a range and usable samples remain unassessed.
                    legacy_missing = 'motion_range' not in summary and ratio != 0
                    item.update(status='NOT_ASSESSED' if legacy_missing else 'UNAVAILABLE',
                                reason='本次缺少可追溯的有效测量；旧记录需至少三个连续有效指标样本', motion_range=None)
            item['status_label'] = STATUS_LABELS[item['status']]
            items.append(item)
    return clean_json({'schema_version': 1, 'participant_id': participant_id,
                       'participant_label': anonymous_participant(participant_id),
                       'source_kind': source_kind, 'usage_context': usage_context,
                       'total_items': len(items), 'assessed_count': sum(i['status'] == 'ASSESSED' for i in items),
                       'items': items, 'comparison_note': COMPARISON_NOTE,
                       'unsupported_coverage': [{'label': label, 'reason': reason} for label, reason in UNSUPPORTED_COVERAGE]})


def build_training_reference(profile, exercise_id, side) -> dict:
    """Freeze one assessment item for a training session; never prescribe a target.

    Save the returned JSON in ``assessment_reference``. It describes the original
    assessment, not current training conditions or evidence of improvement.
    """
    for item in profile['items']:
        if item['exercise_id'] == exercise_id and item['side'] == side:
            result = copy.deepcopy(item)
            result.update({key: copy.deepcopy(profile.get(key)) for key in
                           ('schema_version', 'participant_id', 'participant_label', 'source_kind', 'usage_context')})
            result['comparison_note'] = COMPARISON_NOTE
            if result['status'] != 'ASSESSED':
                result['motion_range'] = None
            return clean_json(result)
    raise ValueError('未找到所选动作与侧别的身体评估项')
