import time

import pytest

from app.participants import new_participant
from app.runtime import Runtime


def response(runtime, command, **kwargs):
    runtime.command(command, **kwargs)
    messages = []
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        message = runtime.messages.get(timeout=8)
        messages.append(message)
        if message['kind'] == 'command_done' and message['command'] == command:
            return messages
    raise AssertionError('No runtime command completion')


def test_real_runtime_creates_reopens_profiles_and_preserves_reports_without_camera(tmp_path):
    runtime = Runtime(tmp_path/'data')
    try:
        assert runtime.ready.wait(8)
        draft = dict(new_participant(), display_name='本地测试用户', goals='自己穿外套')
        replies = response(runtime, 'save_participant', profile=draft, expected_revision=0)
        saved = next(m['profile'] for m in replies if m['kind'] == 'participant_saved')
        assert saved['revision'] == 1
        replies = response(runtime, 'body_profile', participant_id=saved['participant_id'],
                           source_kind='LIVE_CAMERA', usage_context='SELF_USE')
        body = next(m['profile'] for m in replies if m['kind'] == 'body_profile')
        assert body['assessed_count'] == 0
        assert runtime.camera.worker is None and runtime.store.list_sessions() == []
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(8)
        assert not runtime.thread.is_alive()
    runtime = Runtime(tmp_path/'data')
    try:
        assert runtime.ready.wait(8)
        replies = response(runtime, 'participants')
        assert next(m['participants'] for m in replies if m['kind'] == 'participants') == [saved]
        assert runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(8)


@pytest.mark.parametrize('state', ['ONLINE', 'PREVIEW', 'CONNECTING', 'SAVE_FAILED'])
def test_runtime_itself_rejects_profile_write_in_active_or_pending_state(tmp_path, state):
    runtime = Runtime(tmp_path/'data')
    try:
        assert runtime.ready.wait(8)
        # Explicit lifecycle fixture; never opens a camera or generates evidence.
        runtime.controller.state = state
        replies = response(runtime, 'save_participant', profile=dict(new_participant(), display_name='不可保存'), expected_revision=0)
        assert any(m['kind'] == 'error' and m['command'] == 'save_participant' for m in replies)
        assert not any(m['kind'] == 'participant_saved' for m in replies)
        assert runtime.store.list_participants() == []
    finally:
        runtime.controller.state = 'UNSELECTED'
        response(runtime, 'shutdown')
        runtime.thread.join(8)
