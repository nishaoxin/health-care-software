import copy
import pytest

from app.camera_selection import camera_preference, choose_camera
from app.storage import Storage
from app.runtime import Runtime
from test_participant_runtime import response


def camera(path='test-camera-a', backend=700, index=4, name='Test RGB camera'):
    return dict(path=path, backend=backend, index=index, name=name, vid=1, pid=2)


def test_unique_camera_is_selected_without_mutation():
    devices = [camera()]
    before = copy.deepcopy(devices)
    assert choose_camera(devices) is devices[0]
    assert devices == before
    assert choose_camera(devices, allow_single=False) is None


@pytest.mark.parametrize('devices', [[], [camera(), camera('second')], [camera(path='')],
                                    [camera(name='Integrated IR Camera')], [camera(name='Depth Camera')],
                                    [camera(name='红外相机')], [camera(backend=0)]])
def test_unidentified_or_multiple_inputs_are_not_guessed(devices):
    assert choose_camera(devices) is None


@pytest.mark.parametrize('devices,preferred', [
    ([camera('second')], camera()), ([camera(), camera(index=8)], camera()),
    ([camera(backend=1400)], camera()), ([camera(path='')], camera(path='')),
    ([camera()], {}), ([camera()], {'path': 'test-camera-a', 'backend': '700'}),
])
def test_missing_ambiguous_or_invalid_preference_never_falls_back(devices, preferred):
    assert choose_camera(devices, preferred) is None


def test_saved_path_resolves_current_index_not_row_or_old_index():
    current = camera(index=19)
    assert choose_camera([camera('other'), current], camera(index=0)) is current
    assert 'index' not in camera_preference(current)


def test_initial_default_prefers_only_rgb_candidate_over_virtual_and_ir_names():
    rgb = camera(name='Integrated Camera')
    devices = [camera('webcast', name='WebcastMate VirtualCamera'), rgb,
               camera('obs', name='OBS Virtual Camera'), camera('ir', name='Integrated IR Camera')]
    assert choose_camera(devices) is rgb
    assert choose_camera(devices, camera('obs'))['path'] == 'obs'  # Explicit preference wins.
    assert choose_camera(devices, camera('missing')) is None
    assert choose_camera(devices + [camera('usb', name='USB Camera')]) is None


def test_no_physical_candidate_or_duplicate_identity_is_not_auto_selected():
    assert choose_camera([camera(name='OBS Virtual Camera')]) is None
    assert choose_camera([camera(), camera(name='IR Camera')]) is None


def test_preference_survives_reopen_without_changing_schema_or_records(tmp_path):
    path = tmp_path/'data.sqlite3'
    store = Storage(path)
    try:
        assert store.get_camera_preference() is None
        store.save_device('camera:existing', camera('old'))
        store.save_profile(dict(profile_id='existing', scene_id='rehab'))
        store.save_camera_preference(camera(index=89))
        assert store._call(lambda c: c.execute('PRAGMA user_version').fetchone()[0]) == 3
    finally:
        store.close()
    store = Storage(path)
    try:
        assert store.get_camera_preference() == camera_preference(camera())
        assert store.get_profile('existing')['scene_id'] == 'rehab'
        assert store._call(lambda c: c.execute('SELECT COUNT(*) FROM devices').fetchone()[0]) == 2
        assert not store.list_sessions()
    finally:
        store.close()


def test_real_runtime_remembers_then_restarts_without_capture(tmp_path):
    for first in (True, False):
        runtime = Runtime(tmp_path)
        try:
            assert runtime.ready.wait(8)
            replies = response(runtime, 'participants')
            ready = next(m for m in replies if m['kind'] == 'ready')
            assert ready['preferred_camera'] == (None if first else camera_preference(camera(backend=1400)))
            if first:
                response(runtime, 'remember_camera', device=camera(backend=1400))
            assert runtime.camera.worker is None
            assert not runtime.store.list_sessions()
        finally:
            response(runtime, 'shutdown')
            runtime.thread.join(8)
            assert not runtime.thread.is_alive()


def test_corrupt_preference_is_nonfatal_but_disables_default_guess(tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    store.save_device('preference:camera:v1', {'path': '', 'backend': 700})
    store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(8)
        replies = response(runtime, 'participants')
        ready = next(m for m in replies if m['kind'] == 'ready')
        assert ready['camera_preference_error'] and ready['preferred_camera'] is None
        assert runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(8)


def test_preference_write_failure_does_not_change_active_state(tmp_path, monkeypatch):
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(8)
        def fail(_):
            raise OSError('test read-only preference')
        monkeypatch.setattr(runtime.store, 'save_camera_preference', fail)
        runtime.controller.state = 'ONLINE'  # Explicit lifecycle fixture; no camera/session.
        replies = response(runtime, 'remember_camera', device=camera())
        assert any(m['kind'] == 'notice' and '未能记住' in m['text'] for m in replies)
        assert not any(m['kind'] == 'error' for m in replies)
        assert runtime.controller.state == 'ONLINE'
        assert runtime.camera.worker is None
    finally:
        runtime.controller.state = 'UNSELECTED'
        response(runtime, 'shutdown')
        runtime.thread.join(8)


def test_confirm_remembers_live_default_and_preference_error_remains_visible(tmp_path, monkeypatch):
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(8)
        response(runtime, 'participants')
        runtime.controller.source = {'kind': 'LIVE_CAMERA', 'device_ref': camera()}
        monkeypatch.setattr(runtime.controller, 'confirm', lambda setup: setup)
        replies = response(runtime, 'confirm', setup={'fixture': True})
        assert runtime.store.get_camera_preference() == camera_preference(camera())
        def fail(_):
            raise OSError('test preference write failure')
        monkeypatch.setattr(runtime.store, 'save_camera_preference', fail)
        replies = response(runtime, 'confirm', setup={'fixture': True})
        kinds = [m['kind'] for m in replies]
        assert kinds.index('notice') > kinds.index('confirmed')
        assert runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(8)
