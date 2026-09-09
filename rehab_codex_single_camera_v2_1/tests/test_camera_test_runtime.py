import queue
import time
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from app.camera_manager import CameraManager
from app.domain import DeviceDescriptor, FramePacket, utc_now
from app.runtime import Runtime, input_timeout_reason
from app.scene_controller import SceneController
from app.storage import Storage
from app.settings import default_setup
from test_app_camera import FakeWorker


@pytest.fixture
def runtime(tmp_path):
    r = Runtime.__new__(Runtime)
    r.store = Storage(tmp_path/'camera-test.sqlite3')
    r.camera = CameraManager(enumerator=lambda backend: [DeviceDescriptor('Test camera', 'test-path', 700, 8)],
                             worker_factory=FakeWorker)
    r.controller = SceneController(r.store, r.camera)
    r.audio, r.vision = Mock(), Mock()
    r.messages, r.views = queue.Queue(), queue.Queue(maxsize=1)
    r.capture_settings = {}
    r.camera_test, r.camera_test_frames = False, 0
    r.preview_history = []
    r.connect_started_wall = r.last_frame_wall = None
    yield r
    if r.camera.worker:
        r.camera.worker.stop_ok = True
    r.camera.stop()
    r.store.close()


def source(path='test-path'):
    return {'kind': 'LIVE_CAMERA', 'device_ref': {'path': path, 'backend': 700},
            'ref': 'camera:test-path', 'usage_context': 'TEST'}


def packet(context, seq=1):
    now = time.monotonic()
    return FramePacket(context, seq, now, now, utc_now(), np.zeros((120, 160, 3), dtype=np.uint8))


def test_raw_test_uses_resolved_device_but_no_model_measurement_or_report(runtime):
    r, c = runtime, runtime.controller
    r._execute('camera_test', {'source': source()})
    assert r.camera.worker.source['index'] == 8
    assert c.state == 'CONNECTING' and not c.context.run_id
    worker = Mock()
    frame = packet(c.context)
    r._receive_packet(frame, worker)
    view = r.views.get_nowait()
    assert view['camera_test'] and view['packet'] is frame and view['camera_test_frames'] == 1
    assert view['summary'] == {} and view['pose'] is None and not view['confirmed']
    assert c.state == 'PREVIEW' and c.session is None and c.latest_observation is None
    r.vision.submit.assert_not_called()
    assert r.preview_history == [] and c.processed_frames == 0
    assert r.store.list_sessions() == []
    r._execute('stop_camera_test', {})
    assert r.camera.worker is None and not r.camera_test and c.context is None
    assert c.state == 'UNSELECTED' and r.store.list_sessions() == []
    assert any(m['kind'] == 'camera_test_stopped' for m in list(r.messages.queue))


@pytest.mark.parametrize('command', ['confirm', 'start', 'baseline', 'joint_baseline', 'training_control',
                                    'open', 'camera_test', 'save_participant', 'create_assessment_batch'])
def test_raw_test_cannot_confirm_record_or_mutate_patient_state(runtime, command):
    runtime._execute('camera_test', {'source': source()})
    with pytest.raises(ValueError, match='先关闭摄像头测试'):
        runtime._execute(command, {})
    assert not runtime.controller.confirmed and runtime.controller.session is None


@pytest.mark.parametrize('state', ['ONLINE', 'SAVE_FAILED'])
def test_active_or_unsaved_session_cannot_be_replaced_by_test(runtime, state):
    runtime.controller.state = state
    with pytest.raises(ValueError, match='先结束并保存'):
        runtime._execute('camera_test', {'source': source()})
    assert not runtime.camera_test and runtime.camera.worker is None


def test_test_rejects_replay_and_missing_devices_without_fallback(runtime):
    with pytest.raises(ValueError, match='仅支持实时'):
        runtime._execute('camera_test', {'source': {'kind': 'REPLAY_FILE'}})
    with pytest.raises(RuntimeError):
        runtime._execute('camera_test', {'source': source('missing')})
    assert runtime.camera.worker is None
    runtime._execute('stop_camera_test', {})
    assert not runtime.camera_test


def test_release_failure_keeps_test_lock_and_blocks_second_open(runtime):
    r = runtime
    r._execute('camera_test', {'source': source()})
    worker = r.camera.worker
    worker.stop_ok = False
    with pytest.raises(RuntimeError):
        r._execute('stop_camera_test', {})
    assert r.camera_test and r.camera.worker is worker
    assert not any(m['kind'] == 'camera_test_stopped' for m in list(r.messages.queue))
    with pytest.raises(ValueError):
        r._execute('open', {'source': source(), 'setup': default_setup()})
    worker.stop_ok = True
    r._execute('stop_camera_test', {})
    assert not r.camera_test and r.camera.worker is None


def test_duplicate_close_does_not_stop_subsequent_assessment_preview(runtime):
    runtime._execute('camera_test', {'source': source()})
    runtime._execute('stop_camera_test', {})
    runtime._execute('open', {'source': source(), 'setup': default_setup()})
    context = runtime.controller.context
    runtime._execute('stop_camera_test', {})
    assert runtime.controller.context == context and runtime.camera.worker is not None


def test_stale_duplicate_and_old_context_frames_never_pass_or_refresh_watchdog(runtime):
    r = runtime
    r._execute('camera_test', {'source': source()})
    frame = packet(r.controller.context)
    worker = Mock()
    r._receive_packet(frame, worker)
    accepted_wall = r.last_frame_wall
    for bad in (frame, replace(frame, seq=2, time_s=frame.time_s-1),
                replace(frame, seq=3, received_monotonic=time.monotonic()-4),
                replace(frame, seq=4, context=replace(frame.context, generation=0))):
        r._receive_packet(bad, worker)
        assert r.last_frame_wall == accepted_wall and r.camera_test_frames == 1
    assert input_timeout_reason(r.controller.state, accepted_wall+4, None, accepted_wall, {}) == 'stream_stale'
    r.vision.submit.assert_not_called()


def test_test_then_assessment_still_requires_new_pose_and_confirmation(runtime):
    r = runtime
    r._execute('camera_test', {'source': source()})
    old = packet(r.controller.context)
    r._receive_packet(old, Mock())
    r._execute('stop_camera_test', {})
    r._execute('open', {'source': source(), 'setup': default_setup()})
    assert not r.controller.confirmed and r.controller.latest_packet is None
    r._receive_packet(old, Mock())
    r.vision.submit.assert_not_called()
    r._receive_packet(packet(r.controller.context), Mock())
    r.vision.submit.assert_called_once()
