import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.runtime import Runtime
from app.storage import Storage


def response(runtime, command, **kwargs):
    runtime.command(command, **kwargs)
    replies, deadline = [], time.monotonic()+5
    while time.monotonic() < deadline:
        message = runtime.messages.get(timeout=max(.001, deadline-time.monotonic()))
        replies.append(message)
        if message['kind'] == 'command_done' and message['command'] == command:
            return replies
    raise AssertionError('Runtime command did not complete in five seconds')


def test_inference_error_clears_old_observation_and_preview_baseline():
    runtime = Runtime.__new__(Runtime)
    runtime.controller = SimpleNamespace(latest_packet='old', latest_pose='old', latest_observation='old',
                                         context='test-context')
    runtime.preview_history = ['old']
    runtime.audio, runtime._view = Mock(), Mock()
    runtime._inference_failed('new-error-frame', 'synthetic error')
    assert runtime.controller.latest_pose is None and runtime.controller.latest_observation is None
    assert runtime.preview_history == []
    runtime._view.assert_called_once_with('new-error-frame', error='synthetic error')


def test_rejected_training_command_does_not_disable_subsequent_audio():
    runtime = Runtime.__new__(Runtime)
    runtime.controller = SimpleNamespace(context='test-context', training_control=Mock(side_effect=ValueError('not ready')))
    runtime.store, runtime.audio = Mock(), Mock()
    with pytest.raises(ValueError):
        runtime._execute('training_control', {'action': 'resume'})
    assert runtime.audio.reset.call_args.args == ('test-context',)


def test_single_camera_inference_exception_stops_data_before_showing_recovery(tmp_path):
    import queue
    from test_app_joint_expansion_flow import SyntheticSession
    task = SyntheticSession(tmp_path, 'elbow_flexion', 'left')
    r = Runtime.__new__(Runtime)
    r.controller, r.audio, r.vision = task.controller, Mock(), Mock()
    r.messages, r.views = queue.Queue(), queue.Queue(maxsize=1)
    r.preview_history, r.camera_test = [], False
    try:
        task.calibrate()
        task.controller.start()
        task.feed(0., count=10)
        sid = task.controller.session['id']
        r._inference_failed(task.controller.latest_packet, 'injected model failure')
        assert task.controller.context is None and task.controller.session is None
        saved = task.store.get_session(sid)
        assert saved['stop_reason'] == 'inference_error'
        assert r.views.get_nowait()['guidance']['level'] == 'critical'
    finally:
        task.close()


def test_real_runtime_saves_feedback_reopens_report_and_closes_without_camera(tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        store.save_session({'id': 'training-test', 'scene_id': 'rehab', 'submode': 'training',
                            'exercise_id': 'shoulder_abduction', 'participant_id': 'test-person',
                            'source_kind': 'SYNTHETIC', 'usage_context': 'TEST', 'status': 'FINISHED',
                            'summary': {'completed': 2}, 'repetitions': [], 'config_snapshot': {}})
    finally:
        store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        replies = response(runtime, 'save_training_feedback', id='training-test',
                           feedback={'pain': 0, 'fatigue': None, 'reason': 'time'}, expected_revision=0)
        saved = next(m['snapshot'] for m in replies if m['kind'] == 'training_feedback_saved')
        assert saved['training_feedback']['pain'] == 0
        assert saved['summary']['completed'] == 2
        replies = response(runtime, 'training_review', id='training-test')
        assert next(m['snapshot'] for m in replies if m['kind'] == 'training_review') == saved
        assert runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)
        assert not runtime.thread.is_alive()
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        assert store.get_session('training-test') == saved
    finally:
        store.close()
