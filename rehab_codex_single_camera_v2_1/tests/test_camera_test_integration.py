"""Real Runtime loop + SQLite, injected in-memory capture; no hardware or models."""
import queue
import time

import pytest

from app.camera_manager import CameraManager
from app.domain import DeviceDescriptor
from app.runtime import Runtime
from test_camera_test_runtime import source, packet
from test_participant_runtime import response
from test_app_camera import FakeWorker


class StreamWorker(FakeWorker):
    mode = 'frames'

    def __init__(self, *args):
        super().__init__(*args)
        self.seq = 0

    def read_latest(self):
        if self.mode != 'frames':
            return None
        self.seq += 1
        return packet(self.context, self.seq)

    def read_status(self):
        return [{'status': 'ERROR', 'message': '测试输入断开'}] if self.mode == 'error' else []

    def acknowledge(self, seq):
        pass


class NoInference:
    def __init__(self, *args, **kwargs):
        self.outputs = queue.Queue()
        self.submitted = 0

    def submit(self, *args, **kwargs):
        self.submitted += 1
        raise AssertionError('Camera test must not run inference')

    def clear(self):
        pass

    def close(self):
        pass


@pytest.mark.parametrize('mode', ['frames', 'error', 'silent'])
def test_real_command_loop_test_stop_and_input_failure(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(StreamWorker, 'mode', mode)
    camera = CameraManager(enumerator=lambda backend: [DeviceDescriptor('Test', 'test-path', 700, 8)],
                           worker_factory=StreamWorker)
    monkeypatch.setattr('app.runtime.CameraManager', lambda: camera)
    monkeypatch.setattr('app.runtime.VisionWorker', NoInference)
    r = Runtime(tmp_path)
    try:
        assert r.ready.wait(5)
        assert camera.worker is None
        r.capture_settings.update(connect_timeout_s=.05, stale_after_s=.05)
        messages = response(r, 'camera_test', source=source())
        assert not any(m['kind'] in ('error', 'fatal') for m in messages)
        deadline = time.monotonic()+2
        matched = None
        while time.monotonic() < deadline:
            view = r.views.get(timeout=2)
            if ((mode == 'frames' and view.get('camera_test_frames', 0) >= 3) or
                    (mode != 'frames' and view.get('error'))):
                matched = view
                break
        assert matched and matched['camera_test']
        assert matched['summary'] == {} and not matched['confirmed']
        if mode == 'frames':
            assert matched['packet'] is not None and matched['state'] == 'PREVIEW'
        else:
            assert matched['packet'] is None and camera.worker is None
        assert r.vision.submitted == 0 and r.store.list_sessions() == []
        messages = response(r, 'stop_camera_test')
        assert any(m['kind'] == 'camera_test_stopped' for m in messages)
        assert camera.worker is None and not r.camera_test
    finally:
        response(r, 'shutdown')
        r.thread.join(5)
        assert not r.thread.is_alive()
