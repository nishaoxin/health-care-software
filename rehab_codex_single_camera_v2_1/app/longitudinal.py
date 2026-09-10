"""Read-only longitudinal views of recorded conditions, never clinical progress.

Exact stable values are compared. No baseline tolerance, missing-data defaults,
or retrospective clinical interpretation is introduced. Input payloads stay intact.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from statistics import median

from .assessment import finite_number, session_conditions, session_motion_range, session_value
from .domain import SOURCES, CONTEXTS, digest
from .exercises import EXERCISE_IDS, exercise_spec
from .movement_timing import timing_for_plan, TIMING_VERSION


COMPARISON_VERSION = 'recorded-conditions-2'
SCOPE_KEYS = ('participant_id', 'source_kind', 'usage_context', 'exercise_id', 'side', 'submode')
METRICS = {'range_deg': '观察幅度 °', 'peak_angle_deg': '最大投影角 °', 'completed': '完整次数',
           'outbound_s': '出程中位数 s', 'endpoint_dwell_s': '峰区 / 站位停留中位数 s',
           'return_s': '回程中位数 s', 'target_hold_s': '已观察连续保持中位数 s'}
TIMED = ('outbound_s', 'endpoint_dwell_s', 'return_s', 'target_hold_s')
DATA_LABELS = {'OBSERVED': '有完整动作与测量', 'PARTIAL': '中断记录', 'RUNNING': '尚未结束',
               'NO_VALID_MEASUREMENT': '无有效角度测量', 'NO_COMPLETE_REPETITION': '无完整动作',
               'TIME_UNKNOWN': '日期信息不足', 'UNKNOWN_STATUS': '结束状态不明'}
COMPARISON_LABELS = {'MATCH': '记录条件一致', 'DIFFERENT': '记录条件不同', 'UNKNOWN': '比较条件缺失'}
CONDITION_LABELS = {
    'source_ref': '来源引用', 'profile_id': '机位标识', 'view': '拍摄方向', 'placement_revision': '放置版本',
    'actual_size': '实际画面尺寸', 'rois': '原图区域', 'model_manifest_id': '模型清单', 'schema_id': '骨架定义',
    'coordinate_space': '坐标空间', 'keypoint_order_version': '关节点顺序版本', 'joint_order': '关节点名称顺序',
    'pose_backend': '姿态组件', 'target_kind': '测量对象', 'rule_version': '规则版本',
    'preprocess_version': '预处理版本', 'preprocessing_hash': '预处理参数', 'time_basis': '输入时钟',
    'backend': '相机接口', 'requested_capture': '请求拍摄参数', 'measurement_contract': '动作测量定义',
    'calibration': '坐站数值基线', 'joint_baseline': '关节数值基线', 'movement_timing_version': '时间算法版本',
    'timing_plan': '人工时间安排', 'plan.target_reps': '每组次数', 'plan.target_sets': '组数',
    'plan.target_angle_deg': '人工角度目标', 'plan.rest_between_sets_s': '组间休息',
    'plan.allowed_elbow_flexion_deg': '屈肘阈值', 'plan.allowed_trunk_tilt_deg': '躯干倾斜阈值',
    'plan.use_of_hands': '扶物安排', 'plan.needs_companion': '陪同要求', 'plan.ready_s': '准备确认时间',
    'plan.dwell_s': '阶段确认时间', 'plan.max_gap_s': '连续观察间隔上限', 'plan.rest_deg': '回位阈值',
    'plan.raising_delta_deg': '出程阈值', 'plan.issue_hold_s': '问题持续阈值'}
CONDITION_LABELS.update(capture_mode='单摄 / 双摄', dual_camera='双摄分工与配对条件',
                        **{'dual_camera.frontal': '正面逐路测量条件', 'dual_camera.sagittal': '侧面逐路测量条件'})
NOTE = ('只核对记录中可核查的条件；仍需人工核对真实机位、姿势、支撑和使用安排。'
        '未记录的变化无法由相同参数证明不存在。数值变化不自动解释为康复改善。')


def _scope(session):
    return {key: session_value(session, key) for key in SCOPE_KEYS}


def _present(value):
    if value is None or value == '':
        return False
    if isinstance(value, dict):
        return all(_present(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(_present(v) for v in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return finite_number(value) is not None
    return True


def _normalized(value):
    if isinstance(value, dict):
        return {k: _normalized(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalized(v) for v in value]
    if type(value) is float and value.is_integer():
        return int(value)
    return value


def condition_snapshot(session):
    config = session.get('config_snapshot') or {}
    plan = config.get('plan') or {}
    recorded = session_conditions(session)
    values, missing = {}, []

    def add(key, value, valid=True, *, nullable=False):
        values[key] = copy.deepcopy(value)
        if not valid or (not nullable and not _present(value)):
            missing.append(key)

    for key in ('source_ref', 'profile_id', 'view', 'model_manifest_id', 'schema_id', 'coordinate_space',
                'keypoint_order_version', 'pose_backend', 'target_kind', 'rule_version', 'preprocess_version',
                'preprocessing_hash', 'time_basis', 'measurement_contract'):
        value = recorded.get(key)
        add(key, value, isinstance(value, str) and bool(value.strip()))
    from .dual_view import capture_conditions
    capture = capture_conditions(session)
    add('capture_mode', capture['capture_mode'], capture['capture_mode'] in ('single', 'dual'))
    for key in ('dual_camera', 'dual_camera.frontal', 'dual_camera.sagittal'):
        value = capture[key]
        valid = True
        if isinstance(value, dict) and key == 'dual_camera':
            valid = (value.get('primary_view') in ('frontal', 'sagittal')
                     and value.get('secondary_view') in ('frontal', 'sagittal')
                     and value['primary_view'] != value['secondary_view']
                     and value.get('same_participant_manually_confirmed') is True
                     and finite_number(value.get('max_receive_delta_s')) is not None and value['max_receive_delta_s'] > 0)
        elif isinstance(value, dict):
            size = value.get('size')
            valid = isinstance(size, (tuple, list)) and len(size) == 2 and all(type(v) is int and v > 0 for v in size)
        add(key, value, valid)
    for key, value in _scope(session).items():
        add(key, value, isinstance(value, str) and bool(value.strip()))
    add('scene_id', session.get('scene_id'))
    revision = recorded.get('placement_revision')
    add('placement_revision', revision, type(revision) is int and revision >= 1)
    size = recorded.get('actual_size')
    add('actual_size', size, isinstance(size, (list, tuple)) and len(size) == 2
        and all(type(v) is int and v > 0 for v in size))
    order = session.get('joint_order')
    add('joint_order', order, isinstance(order, list) and bool(order) and all(isinstance(v, str) and v for v in order))
    rois = config.get('rois')
    add('rois', rois, isinstance(rois, dict))
    if session.get('source_kind') == 'LIVE_CAMERA':
        add('backend', session.get('backend'), type(session.get('backend')) is int)
        capture = session.get('requested_capture')
        add('requested_capture', capture, isinstance(capture, dict) and all(finite_number(capture.get(k)) is not None
             and capture[k] > 0 for k in ('width', 'height', 'fps')))
    else:
        values.update(backend='not_applicable', requested_capture='not_applicable')
    spec = exercise_spec(session_value(session, 'exercise_id')) if session_value(session, 'exercise_id') in EXERCISE_IDS else {}
    calibration = plan.get('calibration')
    if session_value(session, 'exercise_id') == 'sit_to_stand':
        fields = ('seated_knee', 'standing_knee', 'seated_hip_y', 'standing_hip_y')
        calibration = {k: (calibration or {}).get(k) for k in fields}
        add('calibration', calibration, all(finite_number(v) is not None for v in calibration.values()))
    else:
        add('calibration', {}, 'calibration' in plan and isinstance(calibration, dict))
    baseline = plan.get('joint_baseline')
    if baseline:
        kept = {k: baseline.get(k) for k in ('rest_value', 'raw_metric')}
        valid = finite_number(kept['rest_value']) is not None and isinstance(kept['raw_metric'], str)
        if spec.get('directional_calibration'):
            kept['direction_sign'] = baseline.get('direction_sign')
            valid = valid and type(kept['direction_sign']) is int and kept['direction_sign'] in (-1, 1)
        add('joint_baseline', kept, valid)
    else:
        add('joint_baseline', {}, 'joint_baseline' in plan and isinstance(baseline, dict) and not spec.get('baseline_required'))
    numbers = ('target_reps', 'target_sets', 'ready_s', 'dwell_s', 'max_gap_s', 'rest_deg', 'raising_delta_deg', 'issue_hold_s')
    nullable = ('target_angle_deg', 'rest_between_sets_s', 'allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg')
    for key in numbers + nullable:
        value = plan.get(key)
        valid = key in plan and (value is None and key in nullable or finite_number(value) is not None)
        if key in ('target_reps', 'target_sets'):
            valid = type(value) is int and value > 0
        add('plan.'+key, value, valid, nullable=key in nullable)
    for key in ('use_of_hands', 'needs_companion'):
        value = plan.get(key)
        add('plan.'+key, value, type(value) is bool if key == 'needs_companion' else value in ('not_recorded', 'allowed', 'not_allowed', 'used_hands'))
    try:
        values['timing_plan'] = timing_for_plan(plan)
    except (ValueError, KeyError, TypeError):
        add('timing_plan', None, False)
    # A missing timing version denotes legacy data, not newly measured durations.
    version = session.get('movement_timing_version')
    add('movement_timing_version', version, version is None or isinstance(version, str) and bool(version), nullable=True)
    values = _normalized(values)
    return {'version': COMPARISON_VERSION, 'origin': 'derived_from_saved_snapshot', 'values': values,
            'missing': sorted(set(missing)), 'signature': digest(values) if not missing else None}


def _compare(a, b):
    absent = set(a['missing']) | set(b['missing'])
    differences = [key for key in a['values'].keys() | b['values'].keys()
                   if key not in absent and a['values'].get(key) != b['values'].get(key)]
    return {'status': 'DIFFERENT' if differences else 'UNKNOWN' if absent else 'MATCH',
            'differences': sorted(differences), 'missing': sorted(absent)}


def compare_conditions(a, b):
    return _compare(condition_snapshot(a), condition_snapshot(b))


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except ValueError:
        return None


def build_longitudinal_history(sessions, anchor_id):
    anchor = next((s for s in sessions if s.get('id') == anchor_id), None)
    if anchor is None:
        raise ValueError('基准报告不存在，请重新选择')
    scope = _scope(anchor)
    if (anchor.get('scene_id') != 'rehab' or scope['exercise_id'] not in EXERCISE_IDS
            or scope['side'] not in ('left', 'right') or scope['submode'] not in ('assessment', 'training')
            or scope['source_kind'] not in SOURCES or scope['usage_context'] not in CONTEXTS
            or not isinstance(scope['participant_id'], str) or not scope['participant_id'].strip()):
        raise ValueError('此报告没有完整的用户、来源、动作或侧别信息，不能作为纵向基准')
    matching = [s for s in sessions if s.get('scene_id') == 'rehab' and _scope(s) == scope]
    matching.sort(key=lambda s: (_date(s.get('start_utc')) is None,
                                 _date(s.get('start_utc')) or datetime.max.replace(tzinfo=timezone.utc), str(s.get('id'))))
    anchor_conditions = condition_snapshot(anchor)
    rows = []
    for session in matching:
        summary, status = session.get('summary') or {}, session.get('status')
        conditions = condition_snapshot(session)
        motion, origin = session_motion_range(session)
        completed = summary.get('completed')
        completed = completed if type(completed) is int and completed >= 0 else None
        ratio = finite_number(summary.get('valid_ratio'))
        ratio = ratio if ratio is not None and 0 <= ratio <= 1 else None
        start, end = _date(session.get('start_utc')), _date(session.get('end_utc'))
        data_state = ('RUNNING' if status == 'RUNNING' else
                      'TIME_UNKNOWN' if start is None or end is None or end < start else 'PARTIAL' if status == 'INTERRUPTED' else
                      'UNKNOWN_STATUS' if status not in ('FINISHED', 'COMPLETED') else
                      'NO_COMPLETE_REPETITION' if completed is None or completed == 0 else
                      'NO_VALID_MEASUREMENT' if motion is None else 'OBSERVED')
        values = dict(range_deg=motion['range_deg'] if motion else None,
                      peak_angle_deg=motion['max_deg'] if motion else None, completed=completed)
        counts = {}
        reps = [r for r in session.get('repetitions') or [] if r.get('completion_status') == 'COMPLETE']
        for key in TIMED:
            samples = []
            for rep in reps:
                timing = rep.get('movement_timing') or {}
                metric = timing.get(key) or {}
                value = finite_number(metric.get('value')) if metric.get('valid') is True else None
                if (session.get('movement_timing_version') == TIMING_VERSION and timing.get('version') == TIMING_VERSION
                        and value is not None and value >= 0):
                    samples.append(value)
            values[key] = median(samples) if samples else None
            counts[key] = dict(measured=len(samples), complete_repetitions=len(reps))
        rows.append(dict(session_id=session['id'], start_utc=session.get('start_utc'), end_utc=session.get('end_utc'),
                         status=status, stop_reason=session.get('stop_reason'), data_state=data_state, valid_ratio=ratio,
                         values=values, timing_counts=counts, motion_evidence_source=origin,
                         conditions=conditions, comparison=_compare(anchor_conditions, conditions)))
    result = dict(schema_version=1, comparison_version=COMPARISON_VERSION, scope=scope, anchor_id=anchor_id,
                  exercise_label=exercise_spec(scope['exercise_id'])['label'], note=NOTE, rows=rows,
                  chart_policy='Only ended records with complete repetitions, usable angles, dates and MATCH conditions; gaps break lines.')
    result['fingerprint'] = digest(result)
    return result


def plot_series(history, metric):
    if metric not in METRICS:
        raise ValueError('未知历史指标')
    segments, current = [], []
    for index, row in enumerate(history['rows']):
        value = finite_number(row['values'].get(metric))
        if row['comparison']['status'] == 'MATCH' and row['data_state'] == 'OBSERVED' and value is not None:
            current.append((index, value))
        else:
            if current:
                segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments
