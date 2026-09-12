"""Frozen personal reference periods; descriptive comparison, never diagnosis."""
from statistics import median

from .assessment import finite_number, session_value
from .domain import digest, utc_now
from .longitudinal import build_longitudinal_history, compare_conditions, METRICS, _date
from .silver_store import scope_key, text

METRIC_CHOICES = ('outbound_s', 'completed', 'range_deg')
QUALITY_MIN = .6  # Engineering visibility gate, not accuracy or a clinical cut-off.


def in_scope(session, scope):
    return all(session_value(session, k) == v for k, v in scope_key(scope).items())


def value_for(session, metric):
    if metric not in METRIC_CHOICES:
        raise ValueError('请选择起立/出程时间、完整次数或可观察幅度')
    history = build_longitudinal_history([session], session['id'])
    row = history['rows'][0]
    ratio = row['valid_ratio']
    if (session.get('status') not in ('FINISHED', 'COMPLETED') or row['data_state'] in ('TIME_UNKNOWN', 'UNKNOWN_STATUS')
            or ratio is None or ratio < QUALITY_MIN or (row['values']['completed'] or 0) < 1
            or (finite_number((session.get('summary') or {}).get('valid_s')) or 0) <= 0):
        return None
    return row['values'][metric]


def build_reference(sessions, ids, metric, contexts, *, revision=1):
    if not 3 <= len(set(ids)) <= 5 or len(set(ids)) != len(ids):
        raise ValueError('请选择 3～5 次互不重复的合格记录作为固定参考期')
    records = [next((s for s in sessions if s['id'] == sid), None) for sid in ids]
    if any(s is None for s in records):
        raise ValueError('参考记录不存在')
    anchor = records[0]
    if session_value(anchor, 'exercise_id') not in ('sit_to_stand', 'shoulder_abduction'):
        raise ValueError('首版参考期仅支持居家坐站和肩外展')
    condition = contexts.get(anchor['id'])
    if not condition:
        raise ValueError('请先人工记录每次任务的椅子、扶物与任务协议条件')
    values = []
    for s in records:
        if contexts.get(s['id']) != condition or compare_conditions(anchor, s)['status'] != 'MATCH':
            raise ValueError('参考期的机位、任务、椅子或支撑条件不同/缺失，不能合并')
        value = value_for(s, metric)
        if value is None:
            raise ValueError('参考记录质量不足或所选指标缺测，请选择其他记录')
        values.append(value)
    return dict(id=digest(dict(ids=ids, metric=metric, revision=revision)), revision=revision, metric=metric,
                session_ids=list(ids), session_fingerprints={s['id']: digest(s) for s in records},
                manual_conditions=condition, reference_value=median(values), created_utc=utc_now(),
                algorithm='fixed-reference-median-1', quality_min=QUALITY_MIN)


def change_card(sessions, reference, current_id, contexts):
    result = dict(status='BUILDING', message='建立个人参考中；需要 3～5 次相同条件的合格记录',
                  reference=None, current=None, delta=None, percent=None, current_id=current_id)
    if not reference:
        return result
    lookup = {s['id']: s for s in sessions}
    refs = [lookup.get(sid) for sid in reference['session_ids']]
    current = lookup.get(current_id)
    if current is None or any(s is None or digest(s) != reference['session_fingerprints'][s['id']] for s in refs):
        return dict(result, status='STALE', message='记录缺失或已改变；请重新核对固定参考期')
    if any(contexts.get(s['id']) != reference['manual_conditions'] for s in refs):
        return dict(result, status='STALE', message='参考期的人工条件记录已修改，请重新建立参考期')
    if current_id in reference['session_ids']:
        return dict(result, status='OVERLAP', message='当前记录不能同时属于参考期，请选择之后的新记录')
    if _date(current.get('start_utc')) is None or any(_date(s.get('end_utc')) is None or
            _date(current['start_utc']) <= _date(s['end_utc']) for s in refs):
        return dict(result, status='OVERLAP', message='本次任务时间必须在固定参考期之后，且不能重叠')
    compared = compare_conditions(refs[0], current)
    if compared['status'] != 'MATCH' or contexts.get(current_id) != reference['manual_conditions']:
        return dict(result, status='CONDITIONS_CHANGED', message='条件变化或未记录，暂不直接比较',
                    differences=compared['differences'], missing=compared['missing'])
    value = value_for(current, reference['metric'])
    if value is None:
        return dict(result, status='INSUFFICIENT', message='本次有效数据不足，不能据此评价身体变化')
    base = reference['reference_value']
    delta = value-base
    return dict(result, status='OBSERVED', reference=base, current=value, delta=delta,
                percent=100*delta/base if base != 0 else None, metric=reference['metric'],
                metric_label=METRICS[reference['metric']], reference_id=reference['id'],
                message='本次与固定参考记录存在数值差异；未估计重复测量误差，不作身体退步或风险判断',
                valid_ratio=current['summary'].get('valid_ratio'), updated_utc=utc_now())
