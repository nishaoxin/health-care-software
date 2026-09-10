"""Actual Runtime/SQLite lifecycle with two injected captures; no hardware evidence."""
import queue
import time

import numpy as np
import pytest

from app.camera_manager import CameraManager
from app.domain import FramePacket
from app.dual_camera import make_dual_source
from app.runtime import Runtime
from app.settings import default_setup
from app.storage import Storage
from test_dual_camera import Worker, DEVICES, REFS
from test_dual_vision import pose
from test_participant_runtime import response


class Stream(Worker):
    def __init__(self, *args):
        super().__init__(*args)
        self.seq, self.mode = 0, 'frames'
        self.statuses.append(dict(status='OPENED', reported_fps=30.))

    def read_latest(self):
        if self.mode != 'frames':
            return None
        self.seq += 1
        now = time.monotonic()
        return FramePacket(self.context, self.seq, now, now, '', np.zeros((480, 640, 3), np.uint8), 30., 29.)


class SyntheticInference:
    def __init__(self, *args, **kwargs):
        self.outputs, self.submitted = queue.Queue(), 0
        self.model_path, self.imgsz, self.device = 'synthetic-test-model', 640, 'cpu'

    def submit(self, packet, **kwargs):
        self.submitted += 1
        result = pose(packet)
        result.paired_pose = pose(packet.paired_frame)
        self.outputs.put((packet, result, None))

    def clear(self):
        while not self.outputs.empty():
            self.outputs.get_nowait()

    def close(self):
        return True


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(Stream, 'made', [])
    camera = CameraManager(enumerator=lambda b: DEVICES, worker_factory=Stream)
    monkeypatch.setattr('app.runtime.CameraManager', lambda: camera)
    monkeypatch.setattr('app.runtime.VisionWorker', SyntheticInference)
    r = Runtime(tmp_path)
    assert r.ready.wait(5)
    r.capture_settings.update(connect_timeout_s=.5, stale_after_s=.2)
    yield r
    response(r, 'shutdown')
    r.thread.join(5)
    assert not r.thread.is_alive()


def wait_view(runtime, predicate):
    deadline = time.monotonic()+4
    while time.monotonic() < deadline:
        data = runtime.views.get(timeout=4)
        if predicate(data):
            return data
    raise AssertionError('No matching runtime view')


def checked_command(runtime, command, **kw):
    replies = response(runtime, command, **kw)
    assert not any(m['kind'] in ('error', 'fatal') for m in replies), replies
    return replies


@pytest.mark.parametrize('failed_view, failure', [('frontal', 'error'), ('sagittal', 'error'), ('sagittal', 'silent')])
def test_two_raw_streams_failure_releases_both_then_reopens_without_inference(runtime, failed_view, failure):
    r = runtime
    source = make_dual_source(REFS, 'frontal', 'TEST')
    checked_command(r, 'camera_test', source=source)
    wait_view(r, lambda v: v.get('camera_test_frames', 0) >= 3)
    workers = dict(r.camera.worker.workers)
    workers[failed_view].mode = failure
    if failure == 'error':
        workers[failed_view].statuses.append(dict(status='ERROR', message='injected disconnect'))
    data = wait_view(r, lambda v: bool(v.get('error')))
    assert data['packet'] is None and r.camera.worker is None and all(w.stopped for w in workers.values())
    assert r.vision.submitted == 0 and r.store.list_sessions() == []
    checked_command(r, 'stop_camera_test')
    checked_command(r, 'camera_test', source=source)
    wait_view(r, lambda v: v.get('camera_test_frames', 0) >= 2)
    checked_command(r, 'stop_camera_test')
    assert r.camera.worker is None and r.vision.submitted == 0


@pytest.mark.parametrize('ending', ['error', 'privacy'])
def test_running_dual_session_persists_failure_and_pair_diagnostics_on_real_command_loop(runtime, tmp_path, ending):
    r = runtime
    setup = default_setup()
    setup.update(participant_confirmed=True,
                 dual_camera=dict(primary_view='frontal', same_participant_confirmed=True))
    checked_command(r, 'open', source=make_dual_source(REFS, 'frontal', 'TEST'), setup=setup)
    wait_view(r, lambda v: v.get('observation_status') == 'VALID')
    checked_command(r, 'confirm', setup=setup)
    checked_command(r, 'start')
    wait_view(r, lambda v: v['state'] == 'ONLINE' and v.get('pose') is not None)
    sid = r.controller.session['id']
    workers = dict(r.camera.worker.workers)
    if ending == 'error':
        workers['sagittal'].statuses.append(dict(status='ERROR', message='injected disconnect'))
        wait_view(r, lambda v: bool(v.get('error')))
    else:
        checked_command(r, 'privacy')
    assert all(w.stopped for w in workers.values()) and r.camera.worker is None
    reader = Storage(tmp_path/'home_rehab.sqlite3')
    saved = reader.get_session(sid)
    reader.close()
    dual = saved['dual_camera']
    assert dual['summary']['paired_observations'] > 0
    assert dual['capture_pairing_diagnostics']['emitted_pairs'] >= dual['summary']['paired_observations']
    assert not saved.get('poses') and not saved.get('raw_frames')
    if ending == 'error':
        assert saved['stop_reason'] == 'input_error'
        assert dual['input_failure']['category'] == 'input_error' and dual['input_failure']['view'] == 'sagittal'
    else:
        assert r.controller.state == 'PRIVACY_PAUSED'
