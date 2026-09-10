import copy
import json
import queue
from types import SimpleNamespace

import pytest

from app.runtime import Runtime
from app.storage import Storage
from app.reports import render_report, export_session
from app.training_plans import new_training_plan, prepare_training_plan
from test_saved_training_plans import SCOPE, item, assessment, profile
from test_training_runtime import response
import test_app_controller as controller_fixtures


def test_real_runtime_create_prepare_archive_reopen_without_camera(tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    store.save_session(assessment())
    store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        draft = new_training_plan(SCOPE, '我的计划', [item()])
        replies = response(runtime, 'save_training_plan', scope=SCOPE, plan=draft, expected_revision=0)
        library = next(m for m in replies if m['kind'] == 'training_plans')
        assert library['plans'][0]['items'][0]['available']
        replies = response(runtime, 'prepare_training_plan', scope=SCOPE, id=draft['id'],
                           expected_revision=1, entry_key='shoulder_abduction:left')
        prepared = next(m['plan'] for m in replies if m['kind'] == 'training_plan_prepared')
        assert prepared['assessment_reference']['session_id'] == 'assessment-1'
        assert prepared['training_plan_confirmed'] is False
        replies = response(runtime, 'archive_training_plan', scope=SCOPE, id=draft['id'],
                           expected_revision=1, archived=True)
        assert next(m['plans'][0] for m in replies if m['kind'] == 'training_plans')['status'] == 'ARCHIVED'
        replies = response(runtime, 'prepare_training_plan', scope=SCOPE, id=draft['id'],
                           expected_revision=1, entry_key='shoulder_abduction:left')
        assert any(m['kind'] == 'error' for m in replies)
        assert runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)
        assert not runtime.thread.is_alive()
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        assert store.get_training_plan(draft['id'])['status'] == 'ARCHIVED'
    finally:
        store.close()


@pytest.mark.parametrize('state', ['PREVIEW', 'CONNECTING', 'ONLINE', 'SAVE_FAILED'])
@pytest.mark.parametrize('command', ['save_training_plan', 'archive_training_plan', 'prepare_training_plan'])
def test_plan_mutation_and_preparation_cannot_bypass_active_capture_or_pending_save(state, command):
    runtime = Runtime.__new__(Runtime)
    runtime.controller = SimpleNamespace(state=state, session=None, pending=None)
    runtime.store = None
    with pytest.raises(ValueError, match='先结束'):
        runtime._execute(command, {'scope': SCOPE})


@pytest.fixture
def fixture():
    f = controller_fixtures.ControllerTests(methodName='test_preview_start_shoulder_save_and_reopen')
    f.setUp()
    try:
        f._assessment_reference()
        yield f
    finally:
        f.tearDown()


def prepare_fixture(f):
    scope = dict(SCOPE, participant_id='participant-local')
    record = f.store.save_training_plan(new_training_plan(scope, '<计划测试>', [item()]), expected_revision=0)
    from app.assessment import build_body_profile
    current = build_body_profile(f.store.list_sessions(), **scope)
    plan = prepare_training_plan(record, 'shoulder_abduction:left', current)
    f.setup['plan'] = plan
    return scope, record, plan


def test_controller_rebuilds_saved_snapshot_and_keeps_per_use_changes_in_report(fixture, tmp_path):
    f = fixture
    scope, record, plan = prepare_fixture(f)
    plan['target_reps'] = 3
    plan['saved_plan_reference']['name'] = 'forged'
    f._training_preview(plan['assessment_reference'])
    f.c.start()
    assert f.c.session['saved_plan_reference']['name'] == '<计划测试>'
    assert f.c.session['saved_plan_reference']['session_overrides']['target_reps'] == {'saved': 5, 'used': 3}
    for k in range(25):
        f.frame(k*.1, 0)
    f.c.stop('user_stop')
    session = f.store.get_session(f.c.last_saved_id)
    before = copy.deepcopy(session)
    f.store.set_training_plan_archived(record['id'], scope, True, expected_revision=1)
    assert f.store.get_session(session['id']) == before
    html = render_report(session)
    assert '来源计划' in html and '&lt;计划测试&gt;' in html and '<计划测试>' not in html
    export_session(session, tmp_path/'export')
    public = json.loads((tmp_path/'export/session.json').read_text(encoding='utf-8'))
    assert public['saved_plan_reference']['id'] == record['id']
    assert 'name' not in public['saved_plan_reference']
    assert 'name' not in public['config_snapshot']['plan']['saved_plan_reference']


@pytest.mark.parametrize('action', ['revise', 'archive'])
def test_controller_rejects_stale_saved_plan_at_start(fixture, action):
    f = fixture
    scope, record, plan = prepare_fixture(f)
    f._training_preview(plan['assessment_reference'])
    if action == 'revise':
        f.store.save_training_plan(dict(record, name='新版本'), expected_revision=1)
    else:
        f.store.set_training_plan_archived(record['id'], scope, True, expected_revision=1)
    with pytest.raises(ValueError):
        f.c.start()
    assert f.c.session is None
