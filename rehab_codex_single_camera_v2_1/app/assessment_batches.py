"""Explicitly selected local assessment rounds, independent of historical scores."""
import copy
from uuid import uuid4

from .assessment import build_body_profile, session_value
from .domain import SOURCES, CONTEXTS, utc_now
from .exercises import exercise_spec


ITEM_STATUSES = {'PENDING': '待评估', 'ASSESSED': '已评估', 'REVIEW': '需补测',
                 'IN_PROGRESS': '进行中', 'SKIPPED': '已跳过'}
SCOPE_KEYS = ('participant_id', 'source_kind', 'usage_context')


def scope_key(scope):
    if (not isinstance(scope, dict) or not isinstance(scope.get('participant_id'), str)
            or not scope['participant_id'].strip() or len(scope['participant_id']) > 200
            or not isinstance(scope.get('source_kind'), str) or scope['source_kind'] not in SOURCES
            or not isinstance(scope.get('usage_context'), str) or scope['usage_context'] not in CONTEXTS):
        raise ValueError('请明确当前用户、输入来源和使用情境')
    return {k: scope[k] for k in SCOPE_KEYS}


def new_batch(scope, items):
    scope = scope_key(scope)
    if not isinstance(items, list) or not items or len(items) > 500:
        raise ValueError('请至少选择一个评估项目')
    rows, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('评估项目无效')
        eid, side = item.get('exercise_id'), item.get('side')
        exercise_spec(eid)
        if side not in ('left', 'right') or (eid, side) in seen:
            raise ValueError('评估侧别无效，或项目重复')
        seen.add((eid, side))
        rows.append({'key': eid+':'+side, 'exercise_id': eid, 'side': side, 'skip_reason': None})
    return dict(scope, id=uuid4().hex, revision=1, status='ACTIVE', created_utc=utc_now(),
                closed_utc=None, items=rows, schema_version=1)


def batch_view(batch, sessions):
    result = copy.deepcopy(batch)
    for item in result['items']:
        spec = exercise_spec(item['exercise_id'])
        candidates = [s for s in sessions if s.get('assessment_batch_id') == batch['id']
                      and s.get('assessment_entry_key') == item['key'] and s.get('scene_id') == 'rehab'
                      and session_value(s, 'submode') == 'assessment'
                      and session_value(s, 'exercise_id') == item['exercise_id']
                      and session_value(s, 'side') == item['side']
                      and all(session_value(s, k) == batch[k] for k in SCOPE_KEYS)]
        latest = max(candidates, key=lambda s: (s.get('start_utc') or '', s.get('id') or ''), default=None)
        status, measured = 'PENDING', None
        if latest:
            if latest.get('status') == 'RUNNING':
                status = 'IN_PROGRESS'
            else:
                profile = build_body_profile([latest], **scope_key(batch))
                measured = next(i for i in profile['items'] if (i['exercise_id'], i['side']) == (item['exercise_id'], item['side']))
                status = 'ASSESSED' if measured['status'] == 'ASSESSED' else 'REVIEW'
        if item['skip_reason']:
            status = 'SKIPPED'
        item.update(label=spec['label'], status=status, status_label=ITEM_STATUSES[status],
                    session_id=latest.get('id') if latest else None, attempt_count=len(candidates),
                    measurement=measured)
    result['assessed_count'] = sum(i['status'] == 'ASSESSED' for i in result['items'])
    result['skipped_count'] = sum(i['status'] == 'SKIPPED' for i in result['items'])
    result['review_count'] = sum(i['status'] == 'REVIEW' for i in result['items'])
    result['remaining_count'] = sum(i['status'] in ('PENDING', 'REVIEW', 'IN_PROGRESS') for i in result['items'])
    return result


def validate_binding(batch, scope, exercise_id, side, entry_key):
    if batch is None or batch.get('status') != 'ACTIVE' or scope_key(batch) != scope_key(scope):
        raise ValueError('评估清单已结束或不属于当前用户和来源，请重新选择')
    item = next((i for i in batch['items'] if i['key'] == entry_key), None)
    if item is None or (item['exercise_id'], item['side']) != (exercise_id, side) or item['skip_reason']:
        raise ValueError('评估清单项目已跳过或与当前动作、侧别不一致')
    return item
