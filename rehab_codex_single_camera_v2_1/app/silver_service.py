"""Adapters over existing saved evidence; no extra inference or hidden monitoring."""
import copy
from datetime import datetime

from .change_cards import build_reference, change_card, in_scope
from .domain import utc_now, SOURCES, CONTEXTS, SCENES, EXERCISES
from .assessment import session_value
from .silver_store import scope_key, text


def scoped_events(events, sessions, scope):
    owners = {s['id']: s for s in sessions}
    result = []
    for e in events:
        s = owners.get(e.get('run_id'))
        if s and in_scope(s, scope):
            result.append(e)
        elif all(e.get(k) == v for k, v in scope.items()):
            result.append(e)
    return result


def safe_event(event):
    # Never expose video, skeletons, paths, raw coordinates or device IDs.
    keys = ('id', 'status', 'message', 'rule_id', 'created_utc', 'source_kind', 'usage_context',
            'scene_id', 'human_ack_time', 'human_claim_time', 'human_resolved_time', 'history')
    result = {k: copy.deepcopy(event.get(k)) for k in keys}
    result['origin'] = 'REPLAY' if event.get('source_kind') == 'REPLAY_FILE' else (
        'TEST_EVENT' if event.get('source_kind') == 'SYNTHETIC' else 'REALTIME_VISUAL')
    return result


def snapshot(care, clinical, controller, scope, *, family=False):
    scope = scope_key(scope)
    policy = care.policy(scope)
    if family and not policy['grants']:
        raise ValueError('未获共享授权或授权已撤销')
    sessions = [s for s in clinical.list_sessions() if in_scope(s, scope)]
    active = controller.session if controller and controller.session and in_scope(controller.session, scope) else None
    if active:
        sessions = [s for s in sessions if s['id'] != active['id']]
        sessions.append(dict(active, summary=controller.summary()))
    now = datetime.now().astimezone()
    today = []
    for s in sessions:
        try:
            at = datetime.fromisoformat(s['start_utc']).astimezone()
            if at.date() == now.date():
                today.append(s)
        except (ValueError, KeyError, TypeError):
            continue
    coverage = sum(max(0, (s.get('summary') or {}).get('valid_s') or 0) for s in today)
    elapsed = sum(max(0, (s.get('summary') or {}).get('observed_span_s') or 0) for s in today)
    tasks = [dict(t, session_id=s['id'], source_kind=s['source_kind'], usage_context=s['usage_context'],
                  demo_thresholds=(s.get('summary') or {}).get('demo_thresholds', False))
             for s in today for t in (s.get('summary') or {}).get('tasks', s.get('tasks', []))]
    state = controller.state if active else 'INACTIVE'
    owner_scope = dict(participant_id=(controller.setup.get('plan') or {}).get('participant_id'),
                       source_kind=(controller.source or {}).get('kind'),
                       usage_context=(controller.source or {}).get('usage_context')) if controller else {}
    if controller and owner_scope == scope and not active and controller.state in ('PRIVACY_PAUSED', 'OFFLINE', 'ERROR', 'SAVE_FAILED'):
        state = controller.state
    scene = controller.context.scene_id if active and controller.context else None
    events = scoped_events(clinical.list_events(), sessions, scope)
    requests = care.records(scope, 'request')
    feedback = care.records(scope, 'feedback')
    grants = set(policy['grants']) if family else {'summary', 'requests', 'safety', 'changes', 'checklist'}
    result = dict(scope=scope, refreshed_utc=utc_now(), channel='LOCAL_ROLE', family=family,
                  policy=policy, state=state, active_scene=scene, other_scenes='未监测',
                  live_summary={k: v for k, v in controller.summary().items() if k in
                      ('phase', 'message', 'reminder_due', 'demo_thresholds')} if active and 'summary' in grants else {},
                  requests=[r for r in requests if ('checklist' if r['kind'] == 'checklist' else 'requests') in grants],
                  events=[safe_event(e) for e in events] if 'safety' in grants else [],
                  feedback=[f for f in feedback if not family or ('changes' in grants and f['shared'])])
    if 'summary' in grants:
        result['daily'] = dict(valid_s=coverage, observed_span_s=elapsed,
            valid_ratio=coverage/elapsed if elapsed else None, date=now.date().isoformat(),
            training_sessions=sum(s.get('status') in ('FINISHED', 'COMPLETED') and s.get('scene_id') == 'rehab'
                                 and session_value(s, 'submode') == 'training' for s in today), tasks=tasks,
            note='仅汇总今日开始的会话内可见时段；其他时间未知，不代表全天正常。')
    result['change_cards'] = []
    contexts = {r['id']: r['values'] for r in care.records(scope, 'conditions')}
    for record in care.records(scope, 'card'):
        shared = next((f for f in feedback if f['id'] == record['id'] and f['shared']), None)
        if not family or ('changes' in grants and shared):
            reference = care.get(scope, 'reference', record['reference_id'])
            result['change_cards'].append(change_card(sessions, reference, record['id'], contexts))
    if not family:
        result['sessions'] = [dict(id=s['id'], start_utc=s.get('start_utc'), status=s.get('status'),
            label=EXERCISES.get(session_value(s, 'exercise_id'), SCENES.get(s.get('scene_id'), '未知')),
            side=session_value(s, 'side'), source_kind=s['source_kind'], usage_context=s['usage_context'])
            for s in sessions if s.get('scene_id') == 'rehab']
        result['contexts'] = care.records(scope, 'conditions')
        result['references'] = care.records(scope, 'reference')
    return result


def execute(care, clinical, controller, scope, operation='refresh', *, family=False, channel='LOCAL_ROLE', **kw):
    scope = scope_key(scope)
    if family and operation not in ('refresh', 'respond', 'event'):
        raise ValueError('家庭角色不能更改本人计划、参考期或共享授权')
    sessions = [s for s in clinical.list_sessions() if in_scope(s, scope)]
    selected = {s['id']: s for s in sessions}
    extra = {}
    if operation == 'consent':
        care.consent(scope, kw['recipient'], kw['grants'], kw['revision'])
    elif operation == 'request':
        care.create_request(scope, kw['kind'], kw['note'], kw['request_id'])
    elif operation == 'respond':
        care.transition_request(scope, kw['id'], kw['action'], kw.get('note'), kw['revision'], family=family, channel=channel)
    elif operation == 'event':
        event = next((e for e in scoped_events(clinical.list_events(), sessions, scope) if e['id'] == kw['id']), None)
        if event is None:
            raise ValueError('事件不属于当前用户与来源')
        actor = care.authorize(scope, 'safety') if family else '本人/本机工作人员'
        status = kw['status']
        if status == 'RESOLVED' and event['status'] != 'CLAIMED':
            raise ValueError('请先查看并认领，再记录处理结果')
        if event['status'] != status:
            clinical.transition_event(event['id'], status, actor, kw.get('note', ''))
    elif operation == 'conditions':
        ids = kw['ids']
        if not ids or any(sid not in selected for sid in ids):
            raise ValueError('请选择本人的已保存报告')
        condition = {k: text(kw[k], 120) for k in ('protocol', 'chair', 'support')}
        for sid in ids:
            old = care.get(scope, 'conditions', sid)
            care.save(scope, 'conditions', dict(id=sid, values=condition, evidence_method='MANUAL_ATTESTATION'),
                      expected_revision=(old or {}).get('revision', 0))
    elif operation == 'reference':
        contexts = {r['id']: r['values'] for r in care.records(scope, 'conditions')}
        reference = build_reference(sessions, kw['ids'], kw['metric'], contexts,
                                    revision=len(care.records(scope, 'reference'))+1)
        # References are append-only; their version is explicit, never a rolling baseline.
        care.save(scope, 'reference', dict(reference, reference_revision=reference['revision']))
    elif operation == 'compare':
        reference = care.get(scope, 'reference', kw.get('reference_id'))
        contexts = {r['id']: r['values'] for r in care.records(scope, 'conditions')}
        extra['card'] = change_card(sessions, reference, kw['current_id'], contexts)
        if kw['current_id'] not in selected:
            raise ValueError('当前报告不存在')
        old = care.get(scope, 'card', kw['current_id'])
        care.save(scope, 'card', dict(id=kw['current_id'], reference_id=kw.get('reference_id')),
                  expected_revision=(old or {}).get('revision', 0))
    elif operation == 'feedback':
        if kw['id'] not in selected:
            raise ValueError('请选择本人的已保存报告再记录感受')
        care.feedback(scope, kw['id'], kw['feeling'], kw['share'])
    elif operation != 'refresh':
        raise ValueError('未知银发操作')
    return dict(snapshot(care, clinical, controller, scope, family=family), operation=operation,
                request_id=kw.get('request_id'), **extra)
