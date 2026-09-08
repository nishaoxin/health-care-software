import importlib.util
import queue
import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.runtime import Runtime, input_timeout_reason
from app.settings import ROOT, default_setup


class RuntimeTimeoutTests(unittest.TestCase):
    def test_body_profile_command_is_read_only_and_does_not_open_input(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory)/'data')
            try:
                self.assertTrue(runtime.ready.wait(5))
                runtime.command('body_profile', participant_id='user-001', source_kind='LIVE_CAMERA', usage_context='SELF_USE')
                deadline, response = time.monotonic()+5, None
                while time.monotonic() < deadline:
                    message = runtime.messages.get(timeout=5)
                    if message['kind'] == 'body_profile':
                        response = message
                        break
                self.assertIsNotNone(response)
                self.assertEqual(response['profile']['assessed_count'], 0)
                self.assertEqual(len(response['profile']['items']), 106)
                self.assertIn('投影角度范围', response['html'])
                self.assertEqual(runtime.store.list_sessions(), [])
                self.assertIsNone(runtime.camera.worker)
            finally:
                runtime.command('shutdown')
                runtime.thread.join(10)
                self.assertFalse(runtime.thread.is_alive())

    def test_slow_initial_connection_does_not_use_stream_stale_timeout(self):
        settings = {'connect_timeout_s': 15, 'stale_after_s': 3}
        self.assertIsNone(input_timeout_reason('CONNECTING', 10, 0, None, settings))
        self.assertEqual(input_timeout_reason('CONNECTING', 15.1, 0, None, settings), 'connect_timeout')
        self.assertIsNone(input_timeout_reason('PREVIEW', 12.9, None, 10, settings))
        self.assertEqual(input_timeout_reason('ONLINE', 13.1, None, 10, settings), 'stream_stale')


@unittest.skipUnless((ROOT/'assets/models/yolo11n-pose.pt').is_file() and importlib.util.find_spec('ultralytics'), 'Official local model not prepared')
class RuntimeIntegrationTests(unittest.TestCase):
    def test_actual_blank_replay_has_no_person_no_task_and_no_false_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'synthetic-blank.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
            self.assertTrue(writer.isOpened())
            for _ in range(8):
                writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
            writer.release()
            runtime = Runtime(Path(directory)/'data')
            messages = []
            def wait_for(predicate, timeout=12):
                deadline = time.monotonic()+timeout
                while time.monotonic() < deadline:
                    try:
                        while True:
                            messages.append(runtime.messages.get_nowait())
                    except queue.Empty:
                        pass
                    if predicate():
                        return
                    time.sleep(.02)
                self.fail('Runtime condition timed out: '+str(messages))
            try:
                self.assertTrue(runtime.ready.wait(5))
                self.assertIsNotNone(runtime.controller)
                setup = default_setup()
                setup['participant_confirmed'] = True
                runtime.command('open', source={'kind': 'REPLAY_FILE', 'ref': 'synthetic-blank-clip',
                                               'file': str(path), 'usage_context': 'TEST'}, setup=setup)
                wait_for(lambda: runtime.controller.latest_observation is not None)
                self.assertEqual(runtime.controller.latest_observation.status, 'NO_PERSON_DETECTED')
                runtime.command('confirm', setup=setup)
                wait_for(lambda: runtime.controller.confirmed)
                runtime.command('start')
                wait_for(lambda: any(m.get('kind') == 'error' and m.get('command') == 'start' for m in messages))
                self.assertIsNone(runtime.controller.session)
                runtime.command('preview_segment')
                wait_for(lambda: runtime.camera.worker is None)
                self.assertEqual(runtime.store.list_sessions(), [])
                self.assertFalse(any(m.get('kind') == 'saved' for m in messages))
                self.assertFalse(any(m.get('kind') == 'notice' and '已保存本次任务' in m.get('text', '') for m in messages))
            finally:
                runtime.command('shutdown')
                runtime.thread.join(10)
                self.assertFalse(runtime.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
