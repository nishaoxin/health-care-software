import copy
import json
import sqlite3

import pytest

from app.assessment_batches import new_batch, batch_view, validate_binding
from app.storage import Storage
from app.runtime import Runtime
from test_training_runtime import response
import test_app_controller as controller_tests


SCOPE = {'participant_id': 'person-a', 'source_kind': 'SYNTHETIC', 'usage_context': 'TEST'}
ITEMS = [{'exercise_id': 'shoulder_abduction', 'side': 'left'}, {'exercise_id': 'knee_extension', 'side': 'right'}]


def saved_attempt(batch, sid='attempt', **changes):
    item = batch['items'][0]
    result = dict(SCOPE, id=sid, scene_id='rehab', submode='assessment', exercise_id=item['exercise_id'], side=item['side'],
                  assessment_batch_id=batch['id'], assessment_entry_key=item['key'], status='FINISHED',
                  start_utc='2026-09-08T01:00:00+00:00', end_utc='2026-09-08T01:01:00+00:00',
                  summary={'motion_range': {'min_deg': 0., 'max_deg': 60., 'range_deg': 60.}, 'valid_ratio': .9})
    result.update(changes)
    return result


def test_round_uses_only_its_bound_results_not_old_success_or_another_person():
    batch = new_batch(SCOPE, ITEMS)
    old = saved_attempt(batch, assessment_batch_id='another-round')
    other = saved_attempt(batch, participant_id='other-person')
    assert batch_view(batch, [old, other])['remaining_count'] == 2
    valid = saved_attempt(batch)
    view = batch_view(batch, [valid])
    assert view['assessed_count'] == 1 and view['items'][0]['attempt_count'] == 1
    failed = saved_attempt(batch, 'later', start_utc='2026-09-08T02:00:00+00:00',
                           end_utc='2026-09-08T02:01:00+00:00', summary={'motion_range': None})
    view = batch_view(batch, [valid, failed])
    assert view['items'][0]['status'] == 'REVIEW' and view['assessed_count'] == 0
    recovered = saved_attempt(batch, 'unexpected', start_utc='2026-09-08T03:00:00+00:00',
                              end_utc=None, status='INTERRUPTED')
    assert batch_view(batch, [valid, recovered])['items'][0]['status'] == 'REVIEW'


@pytest.mark.parametrize('items', [[], ITEMS+ITEMS, [{'exercise_id': 'unknown', 'side': 'left'}],
                                 [{'exercise_id': 'knee_extension', 'side': 'both'}]])
def test_invalid_round_is_rejected(items):
    with pytest.raises(ValueError):
        new_batch(SCOPE, items)


@pytest.mark.parametrize('scope', [None, {}, dict(SCOPE, source_kind=[]), dict(SCOPE, usage_context=True)])
def test_invalid_scope_is_a_readable_validation_error(scope):
    with pytest.raises(ValueError, match='当前用户'):
        new_batch(scope, ITEMS)


def test_batch_persists_skip_restore_conflict_close_and_does_not_delete_results(tmp_path):
    store = Storage(tmp_path/'data.sqlite3')
    try:
        batch = store.create_assessment_batch(SCOPE, ITEMS)
        with pytest.raises(ValueError, match='已有'):
            store.create_assessment_batch(SCOPE, ITEMS)
        with pytest.raises(ValueError, match='跳过原因'):
            store.change_assessment_batch(batch['id'], 'skip', entry_key=batch['items'][0]['key'], reason='', expected_revision=1)
        batch = store.change_assessment_batch(batch['id'], 'skip', entry_key=batch['items'][1]['key'], reason='本轮不做', expected_revision=1)
        assert batch_view(batch, [])['skipped_count'] == 1
        with pytest.raises(ValueError, match='已更新'):
            store.change_assessment_batch(batch['id'], 'close', expected_revision=1)
        assert store.current_assessment_batch(dict(SCOPE, participant_id='another')) is None
        assert store.current_assessment_batch(dict(SCOPE, source_kind='LIVE_CAMERA')) is None
        store.save_session(saved_attempt(batch))
        with pytest.raises(ValueError, match='不能用跳过'):
            store.change_assessment_batch(batch['id'], 'skip', entry_key=batch['items'][0]['key'], reason='不可覆盖', expected_revision=2)
        batch = store.change_assessment_batch(batch['id'], 'restore', entry_key=batch['items'][1]['key'], expected_revision=2)
        store.close()
        store = Storage(tmp_path/'data.sqlite3')
        assert store.current_assessment_batch(SCOPE) == batch
        store.change_assessment_batch(batch['id'], 'close', expected_revision=3)
        assert store.current_assessment_batch(SCOPE) is None
        assert store.get_assessment_batch(batch['id'])['status'] == 'CLOSED'
        assert store.get_session('attempt') is not None
        new = store.create_assessment_batch(SCOPE, ITEMS)
        assert batch_view(new, store.list_sessions())['assessed_count'] == 0
    finally:
        store.close()


def test_running_result_blocks_edit_and_deleted_result_returns_to_pending(tmp_path):
    store = Storage(tmp_path/'data.sqlite3')
    try:
        batch = store.create_assessment_batch(SCOPE, ITEMS)
        store.save_session(saved_attempt(batch, status='RUNNING', end_utc=None))
        with pytest.raises(ValueError, match='先结束'):
            store.change_assessment_batch(batch['id'], 'close', expected_revision=1)
        store.delete_session('attempt')
        assert batch_view(batch, store.list_sessions())['items'][0]['status'] == 'PENDING'
    finally:
        store.close()


def test_v2_migration_backs_up_before_adding_table_and_readonly_does_not_migrate(tmp_path):
    path = tmp_path/'v2.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT)')
        c.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('old', None, 'rehab', json.dumps({'id': 'old'})))
        c.execute('PRAGMA user_version=2')
    store = Storage(path, readonly=True)
    try:
        assert store.current_assessment_batch(SCOPE) is None
    finally:
        store.close()
    assert not list(tmp_path.glob('*.bak'))
    store = Storage(path)
    try:
        assert store.get_session('old') == {'id': 'old'}
        backup_path = next(tmp_path.glob('v2.sqlite3.before-v3-*.bak'))
        with sqlite3.connect(backup_path) as c:
            assert c.execute('PRAGMA user_version').fetchone()[0] == 2
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='assessment_batches'").fetchone()
    finally:
        store.close()


def test_controller_revalidates_round_before_start_and_binds_only_assessment():
    fixture = controller_tests.ControllerTests(methodName='test_preview_start_shoulder_save_and_reopen')
    fixture.setUp()
    c = fixture.c
    try:
        scope = dict(SCOPE, participant_id='participant-local')
        batch = fixture.store.create_assessment_batch(scope, ITEMS)
        c.setup['plan'].update(assessment_batch_id=batch['id'], assessment_entry_key=batch['items'][0]['key'])
        c.start()
        sid = c.session['id']
        assert c.session['assessment_batch_id'] == batch['id']
        t = 0.
        for angle in (0., 80., 0.):
            for _ in range(20):
                fixture.frame(t, angle)
                t += .1
        c.stop('user_stop')
        assert fixture.store.get_session(sid)['assessment_entry_key'] == 'shoulder_abduction:left'
        assert batch_view(batch, fixture.store.list_sessions())['assessed_count'] == 1
        fixture.store.change_assessment_batch(batch['id'], 'close', expected_revision=1)
        fixture.setup = copy.deepcopy(c.setup)
        c.open(fixture.source, fixture.setup)
        fixture.frame(1., 0)
        c.confirm(fixture.setup)
        with pytest.raises(ValueError, match='清单已结束'):
            c.start()
        assert c.session is None
    finally:
        fixture.tearDown()


@pytest.mark.parametrize('change', [{'participant_id': 'other'}, {'source_kind': 'LIVE_CAMERA'},
                                   {'usage_context': 'SELF_USE'}])
def test_binding_rejects_different_person_or_source_context(change):
    batch = new_batch(SCOPE, ITEMS)
    with pytest.raises(ValueError):
        validate_binding(batch, dict(SCOPE, **change), ITEMS[0]['exercise_id'], 'left', batch['items'][0]['key'])


def test_binding_rejects_wrong_side_or_skipped_entry():
    batch = new_batch(SCOPE, ITEMS)
    with pytest.raises(ValueError):
        validate_binding(batch, SCOPE, ITEMS[0]['exercise_id'], 'right', batch['items'][0]['key'])
    batch['items'][0]['skip_reason'] = '暂不测试'
    with pytest.raises(ValueError):
        validate_binding(batch, SCOPE, ITEMS[0]['exercise_id'], 'left', batch['items'][0]['key'])


def test_real_runtime_creates_reloads_and_guards_batch_without_opening_input(tmp_path):
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        replies = response(runtime, 'create_assessment_batch', scope=SCOPE, items=ITEMS)
        batch = next(m['batch'] for m in replies if m['kind'] == 'assessment_batch')
        assert batch['remaining_count'] == 2
        runtime.controller.state = 'ONLINE'
        replies = response(runtime, 'change_assessment_batch', scope=SCOPE, id=batch['id'],
                           action='close', expected_revision=1)
        assert any(m['kind'] == 'error' for m in replies)
        runtime.controller.state = 'UNSELECTED'
        replies = response(runtime, 'assessment_batch', scope=SCOPE)
        assert next(m['batch'] for m in replies if m['kind'] == 'assessment_batch')['id'] == batch['id']
        assert runtime.camera.worker is None
    finally:
        runtime.controller.state = 'UNSELECTED'
        response(runtime, 'shutdown')
        runtime.thread.join(5)
        assert not runtime.thread.is_alive()
