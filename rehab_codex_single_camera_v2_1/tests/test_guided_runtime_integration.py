"""Actual Runtime command loop for the guided continuation; injected synthetic input."""
import time

from app.dual_camera import make_dual_source
from app.settings import default_setup
from app.storage import Storage
from test_dual_runtime_integration import runtime, checked_command, wait_view
from test_dual_camera import REFS


def guided_setup(exercise='shoulder_abduction'):
    setup = default_setup(exercise=exercise)
    setup.update(participant_confirmed=True, continuation_mode='guided',
                 dual_camera=dict(primary_view=setup['view'], same_participant_confirmed=True))
    return setup


def test_guided_run_starts_prompts_self_reports_and_saves_through_the_real_loop(runtime, tmp_path):
    r = runtime
    setup = guided_setup()
    checked_command(r, 'open', source=make_dual_source(REFS, setup['view'], 'TEST'), setup=setup)
    wait_view(r, lambda v: v['state'] == 'PREVIEW')
    checked_command(r, 'confirm', setup=setup)
    checked_command(r, 'start')
    data = wait_view(r, lambda v: v['state'] == 'ONLINE' and v.get('guided_prompt'))
    assert data['continuation_mode'] == 'guided'
    assert data['guided_prompt']['key'] == 'ready' and data['guidance']['level'] == 'status'
    assert data['guidance']['prompt_label'] == '回到起点'
    sid = r.controller.session['id']
    checked_command(r, 'self_report')
    checked_command(r, 'self_report')
    data = wait_view(r, lambda v: v.get('self_reported') == 2)
    checked_command(r, 'guided_pause', paused=True)
    data = wait_view(r, lambda v: (v.get('guided_prompt') or {}).get('paused'))
    assert data['guidance']['level'] == 'paused' and '继续提示' in data['guidance']['instruction']
    frozen = data['guided_prompt']['remaining_s']
    time.sleep(.2)
    assert r._guided_prompt()['remaining_s'] == frozen
    checked_command(r, 'guided_pause', paused=False)
    wait_view(r, lambda v: not (v.get('guided_prompt') or {}).get('paused'))
    checked_command(r, 'stop')
    reader = Storage(tmp_path/'home_rehab.sqlite3')
    saved = reader.get_session(sid)
    reader.close()
    assert saved['measurement_mode'] == 'guided_timed'
    assert saved['summary']['self_reported_reps'] == 2 and saved['summary']['completed'] == 0
    assert saved['continuation']['prompt_pauses'] == 1
    assert len(saved['continuation']['self_reports']) == 2
    assert saved['repetitions'] == []


def test_guided_mode_does_not_relax_save_or_identity_gates(runtime):
    r = runtime
    setup = guided_setup()
    checked_command(r, 'open', source=make_dual_source(REFS, setup['view'], 'TEST'), setup=setup)
    wait_view(r, lambda v: v['state'] == 'PREVIEW')
    # A self report before the run starts must be refused, not silently stored.
    r.command('self_report')
    message = next(m for m in iter(lambda: r.messages.get(timeout=4), None) if m['kind'] in ('error', 'fatal'))
    assert message['kind'] == 'error' and '请先开始' in message['text']
    checked_command(r, 'confirm', setup=setup)
    checked_command(r, 'start')
    wait_view(r, lambda v: v['state'] == 'ONLINE')
    checked_command(r, 'stop')
    assert r.controller.pending is None and r.controller.last_saved_id


def record_baseline(r, setup, source):
    checked_command(r, 'open', source=source, setup=setup)
    data = wait_view(r, lambda v: v.get('current_measurement_valid'))
    checked_command(r, 'prepare_sample', sample='joint_baseline', position='rest', expected_context=data['context'])
    baseline, deadline = None, time.monotonic()+8.
    while time.monotonic() < deadline:
        message = r.messages.get(timeout=8)
        assert message['kind'] != 'fatal'
        if message['kind'] == 'joint_baseline':
            baseline = message['baseline']
        if message['kind'] == 'preparation' and not message['active']:
            assert '已记录' in message['text'], message
            break
    assert baseline is not None
    return baseline


def test_reopening_the_same_preview_reuses_a_still_applicable_baseline(runtime):
    r = runtime
    setup = default_setup()
    setup.update(participant_confirmed=True,
                 dual_camera=dict(primary_view=setup['view'], same_participant_confirmed=True))
    source = make_dual_source(REFS, setup['view'], 'TEST')
    setup['plan']['joint_baseline'] = record_baseline(r, setup, source)
    checked_command(r, 'stop')
    # Opening the same action again must not demand the same recording twice.
    checked_command(r, 'open', source=source, setup=setup)
    data = wait_view(r, lambda v: v.get('preparation_reuse'))
    assert data['preparation_reuse'] == dict(reused=['joint_baseline'], reasons=[])
    assert r.controller.live_joint_baseline['rest_value'] == setup['plan']['joint_baseline']['rest_value']
    checked_command(r, 'confirm', setup=setup)
    assert r.controller.confirmed
    checked_command(r, 'stop')


def test_a_changed_test_side_still_requires_a_new_baseline_with_a_stated_reason(runtime):
    r = runtime
    setup = default_setup()
    setup.update(participant_confirmed=True,
                 dual_camera=dict(primary_view=setup['view'], same_participant_confirmed=True))
    source = make_dual_source(REFS, setup['view'], 'TEST')
    baseline = record_baseline(r, setup, source)
    checked_command(r, 'stop')
    setup['plan'].update(side='right', joint_baseline=baseline)
    checked_command(r, 'open', source=source, setup=setup)
    data = wait_view(r, lambda v: v.get('preparation_reuse'))
    assert data['preparation_reuse']['reused'] == []
    assert data['preparation_reuse']['reasons'] and '重新记录起点' in data['preparation_reuse']['reasons'][0]
    assert not r.controller.live_joint_baseline
    assert not r.controller.setup['plan']['joint_baseline']
    checked_command(r, 'stop')
