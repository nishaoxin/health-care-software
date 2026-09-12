import copy
import sqlite3
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.silver_store import SilverStore
from app.silver_service import execute, snapshot
from app.change_cards import build_reference, change_card
from app.storage import Storage
from app.activity import ActivityEngine
from app.settings import default_setup
from app.domain import digest
from app.runtime import Runtime
from test_app_scenes import observed
from test_longitudinal import saved_session, later


SCOPE = dict(participant_id='p', source_kind='SYNTHETIC', usage_context='TEST')


@pytest.fixture
def care(tmp_path):
    return SilverStore(tmp_path/'support.sqlite3')


def test_requests_survive_reopen_and_retries_do_not_duplicate(care):
    first = care.create_request(SCOPE, 'help', '需要帮助', 'one')
    assert care.create_request(SCOPE, 'help', '需要帮助', 'one') == first
    assert len(SilverStore(care.path).records(SCOPE, 'request')) == 1
    assert first['remote_delivery'] == 'NOT_CONNECTED'
    with pytest.raises(ValueError):
        care.create_request(SCOPE, 'contact', 'changed', 'one')


def test_permissions_and_ack_claim_resolution_are_independent(care):
    r = care.create_request(SCOPE, 'help', '请联系', 'one')
    with pytest.raises(ValueError):
        care.transition_request(SCOPE, r['id'], 'ack', '', 1, family=True)
    care.consent(SCOPE, '家人甲', ['requests'], 0)
    r = care.transition_request(SCOPE, r['id'], 'ack', '', 1, family=True)
    assert r['status'] == 'ACKNOWLEDGED' and len(r['history']) == 1
    assert care.transition_request(SCOPE, r['id'], 'ack', '', 1, family=True) == r
    with pytest.raises(ValueError):
        care.transition_request(SCOPE, r['id'], 'resolve', 'done', r['revision'], family=True)
    r = care.transition_request(SCOPE, r['id'], 'claim', '准备联系', r['revision'], family=True)
    with pytest.raises(ValueError):
        care.transition_request(SCOPE, r['id'], 'resolve', '', r['revision'], family=True)
    r = care.transition_request(SCOPE, r['id'], 'resolve', '已电话联系，本人表示希望休息', r['revision'], family=True)
    assert r['status'] == 'RESOLVED'
    assert len(r['history']) == 3 and all(h['channel'] == 'LOCAL_ROLE' for h in r['history'])
    care.consent(SCOPE, '', [], 1)
    with pytest.raises(ValueError):
        care.authorize(SCOPE, 'requests')
    assert care.records(dict(SCOPE, participant_id='other'), 'request') == []


def test_checklist_needs_owner_acceptance(care):
    care.consent(SCOPE, '家人', ['checklist'], 0)
    r = care.create_request(SCOPE, 'checklist', '移走通道杂物', 'c')
    for action in ('ack', 'claim', 'submit'):
        r = care.transition_request(SCOPE, r['id'], action, '完成记录', r['revision'], family=True)
    assert r['status'] == 'AWAITING_CONFIRMATION'
    with pytest.raises(ValueError):
        care.transition_request(SCOPE, r['id'], 'confirm', '好', r['revision'], family=True)
    r = care.transition_request(SCOPE, r['id'], 'confirm', '本人确认通道已清理', r['revision'])
    assert r['status'] == 'RESOLVED'


def test_concurrent_revision_conflicts_and_write_failure_are_not_success(care):
    r = care.create_request(SCOPE, 'contact', '请联系', 'one')
    def save(n):
        try:
            return care.save(SCOPE, 'request', dict(r, note=str(n)), expected_revision=1)
        except ValueError:
            return None
    with ThreadPoolExecutor(2) as pool:
        assert sum(v is not None for v in pool.map(save, [1, 2])) == 1
    with sqlite3.connect(care.path) as db:
        db.execute("CREATE TRIGGER fail BEFORE INSERT ON records BEGIN SELECT RAISE(FAIL,'test full'); END")
    with pytest.raises(sqlite3.Error):
        care.create_request(SCOPE, 'help', 'write fails', 'two')
    assert care.get(SCOPE, 'request', 'two') is None


def test_family_projection_hides_unshared_data_and_scopes_events(care, tmp_path):
    clinical = Storage(tmp_path/'clinical.sqlite3')
    try:
        care.create_request(SCOPE, 'help', 'private', 'one')
        care.feedback(SCOPE, 'saved', '今天较累', False)
        care.consent(SCOPE, '家人', ['summary'], 0)
        d = snapshot(care, clinical, None, SCOPE, family=True)
        assert not d['requests'] and not d['feedback'] and not d['events']
        assert d['daily']['valid_ratio'] is None and d['state'] == 'INACTIVE'
        assert 'sessions' not in d and 'contexts' not in d
        clinical.save_event(dict(id='e', status='OPEN', participant_id='other', source_kind='SYNTHETIC', usage_context='TEST'))
        assert snapshot(care, clinical, None, SCOPE)['events'] == []
        with pytest.raises(ValueError):
            execute(care, clinical, None, SCOPE, 'consent', family=True, recipient='x', grants=['requests'], revision=1)
        care.consent(SCOPE, '', [], 1)
        with pytest.raises(ValueError):
            snapshot(care, clinical, None, SCOPE, family=True)
    finally:
        clinical.close()


def reference_records(saved_session):
    sessions = [later(saved_session, sid=str(i), day=i+1) for i in range(4)]
    contexts = {s['id']: dict(protocol='same five reps', chair='blue', support='none') for s in sessions}
    return sessions, contexts


def test_reference_is_fixed_separate_and_rejects_changed_conditions(saved_session):
    sessions, contexts = reference_records(saved_session)
    reference = build_reference(sessions, ['0', '1', '2'], 'completed', contexts)
    assert change_card(sessions, reference, '3', contexts)['status'] == 'OBSERVED'
    assert change_card(sessions, reference, '0', contexts)['status'] == 'OVERLAP'
    before = copy.deepcopy(reference)
    contexts['3']['chair'] = 'other'
    assert change_card(sessions, reference, '3', contexts)['status'] == 'CONDITIONS_CHANGED'
    assert reference == before
    sessions[0]['summary']['completed'] += 1
    assert change_card(sessions, reference, '3', contexts)['status'] == 'STALE'


@pytest.mark.parametrize('bad', ['few', 'duplicate', 'quality', 'profile', 'target', 'context'])
def test_bad_references_are_not_health_conclusions(saved_session, bad):
    sessions, contexts = reference_records(saved_session)
    ids = ['0', '1', '2']
    if bad == 'few': ids = ['0', '1']
    if bad == 'duplicate': ids = ['0', '0', '1']
    if bad == 'quality': sessions[1]['summary']['valid_ratio'] = .1
    if bad == 'profile': sessions[1]['profile_id'] = 'changed'
    if bad == 'target': sessions[1]['config_snapshot']['plan']['target_reps'] = 2
    if bad == 'context': contexts.pop('1')
    with pytest.raises(ValueError):
        build_reference(sessions, ids, 'completed', contexts)


def test_reminder_decisions_no_new_prompt_after_refusal_and_no_false_walk():
    setup = default_setup('activity')
    setup.update(rois={'chair': [.1, .4, .9, .9]}, sedentary_trigger_s=.5, stand_target_s=.5)
    e = ActivityEngine(setup)
    for i in range(10): e.process(observed(i*.1))
    assert e.tasks[-1]['status'] == 'OFFERED'
    e.choose_task('skip', 1.)
    for i in range(10, 15): e.process(observed(i*.1, knee=5))
    for i in range(15, 40): e.process(observed(i*.1))
    assert not e.reminder_due and e.tasks[-1]['status'] == 'DECLINED'
    e.choose_task('stand', 4.)
    e.process(observed(4.1, knee=5))
    e.process(observed(4.2, knee=5))
    e.process(observed(12., knee=5))
    assert e.tasks[-1]['status'] == 'INTERRUPTED' and not e.tasks[-1]['visual_verified']
    e.choose_task('self_report', 12.)
    assert e.tasks[-1]['self_report_evidence'] == 'SELF_REPORTED'
    assert not e.tasks[-1]['visual_verified']
    assert e.tasks[-1]['history'][-1]['status'] == 'INTERRUPTED'


def test_activity_restrictions_and_offer_cannot_be_reported_as_completed():
    setup = default_setup('activity')
    setup.update(rois={'chair': [.1, .4, .9, .9]}, sedentary_trigger_s=.5, allowed_activity_tasks=[])
    e = ActivityEngine(setup)
    for i in range(15): e.process(observed(i*.1))
    assert not e.reminder_due and not e.tasks
    with pytest.raises(ValueError):
        e.choose_task('stand', 1.5)
    setup['allowed_activity_tasks'] = ['stand']
    e = ActivityEngine(setup)
    for i in range(15): e.process(observed(i*.1))
    assert e.tasks[-1]['status'] == 'OFFERED'
    with pytest.raises(ValueError):
        e.choose_task('self_report', 1.5)
    with pytest.raises(ValueError):
        e.choose_task('walk', 1.5)
    e.choose_task('stand', 1.5)
    assert [h['status'] for h in e.tasks[0]['history']] == ['OFFERED', 'ACCEPTED']


def test_safety_source_and_acknowledgement_do_not_resolve_on_offline(care, tmp_path):
    clinical = Storage(tmp_path/'clinical.sqlite3')
    try:
        clinical.save_event(dict(SCOPE, id='safe', status='OPEN', message='测试低位', created_utc='now',
                                 history=[], source_ref='PRIVATE PATH', evidence={'video': 'PRIVATE'}))
        care.consent(SCOPE, '家人', ['safety'], 0)
        d = execute(care, clinical, None, SCOPE, 'event', family=True, id='safe', status='ACKNOWLEDGED')
        assert d['events'][0]['status'] == 'ACKNOWLEDGED'
        assert 'source_ref' not in d['events'][0] and 'evidence' not in d['events'][0]
        with pytest.raises(ValueError):
            execute(care, clinical, None, SCOPE, 'event', family=True, id='safe', status='RESOLVED', note='done')
        execute(care, clinical, None, SCOPE, 'event', family=True, id='safe', status='CLAIMED')
        assert clinical.list_events()[0]['status'] == 'CLAIMED'
    finally:
        clinical.close()


def test_optional_slow_service_uses_frozen_evidence_and_does_not_block_runtime():
    runtime = Runtime.__new__(Runtime)
    runtime.messages = queue.Queue()
    runtime.controller = SimpleNamespace(session=None, setup={'plan': {'participant_id': 'before'}},
        source=None, state='ONLINE', context=None, generation=1, summary=lambda: {'valid_s': 10})
    entered, release = threading.Event(), threading.Event()
    seen = []
    def slow(name, kw):
        seen.append(kw['_controller_snapshot'])
        entered.set()
        assert release.wait(3)
        raise ValueError('simulated optional storage failure')
    runtime._execute = slow
    try:
        start = time.monotonic()
        runtime._dispatch_optional('silver', {'scope': SCOPE})
        assert time.monotonic()-start < .5
        assert entered.wait(2)
        runtime.controller.setup['plan']['participant_id'] = 'after'
        assert seen[0].setup['plan']['participant_id'] == 'before'
        assert runtime.controller.state == 'ONLINE'
    finally:
        release.set()
        runtime._close_optional()
    assert runtime.messages.get(timeout=1)['kind'] == 'error'
    assert runtime.controller.state == 'ONLINE'
