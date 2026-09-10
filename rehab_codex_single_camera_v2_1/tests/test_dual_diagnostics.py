"""Diagnostic CLI evidence cannot turn attempted opening into observed frames."""
import time
from unittest.mock import Mock

import pytest

from scripts.check_dual_camera import check_pair
from test_dual_camera import REFS
from test_dual_runtime import current_pair


@pytest.mark.parametrize('release_error', [False, True])
def test_failed_probe_records_attempt_without_observed_images_and_always_attempts_release(release_error):
    camera = Mock()
    camera.worker.read_status.return_value = [dict(status='ERROR', view='sagittal')]
    camera.worker.diagnostics.return_value = dict(emitted_pairs=0)
    camera.worker.forced_stop = False
    if release_error:
        camera.stop.side_effect = RuntimeError('fixture release failure')
    result = check_pair(camera, REFS, .01, {}, 1)
    assert result['camera_open_attempted'] and not result['camera_frames_observed']
    assert not result['completed'] and result['released'] == (not release_error)
    camera.stop.assert_called_once()


def test_probe_uses_owned_paired_frames_and_preserves_actual_parameters_without_pixels():
    camera = Mock()
    camera.worker.read_status.return_value = []
    camera.worker.diagnostics.return_value = dict(emitted_pairs=3)
    camera.worker.forced_stop = False
    def latest():
        time.sleep(.002)
        packet = current_pair(camera.open_pair.call_args.args[2])
        packet.received_fps = 20.
        packet.paired_frame.received_fps = 18.
        return packet
    camera.worker.read_latest.side_effect = latest
    result = check_pair(camera, REFS, .012, dict(width=1280, height=720, fps=30), 1)
    assert result['completed'] and result['camera_frames_observed'] and result['received_pairs'] > 1
    assert result['streams']['frontal']['sizes'] == [[32, 24]]
    assert result['streams']['sagittal']['latest_received_fps'] == 18.
    assert 'image' not in result and result['requested_capture']['width'] == 1280
