import math
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from app.camera_manager import CameraManager
from app.domain import FramePacket, PoseFrame, PosePerson, utc_now
from app.scene_controller import SceneController
from app.settings import default_setup
from app.storage import Storage


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.temp.name)/'test.sqlite3')
        self.camera = CameraManager()
        self.c = SceneController(self.store, self.camera, test_mode=True)
        self.source = {'kind': 'SYNTHETIC', 'ref': 'synthetic-fixture', 'usage_context': 'TEST'}
        self.setup = default_setup()
        self.setup['participant_confirmed'] = True
        self.c.open(self.source, self.setup)
        self.seq = 0
        self.frame(0, 0)
        self.c.confirm(self.setup)

    def tearDown(self):
        if self.c.pending:
            self.c.retry_save()
        self.c.stop('test_end')
        self.store.close()
        self.temp.cleanup()

    def frame(self, t, angle, context=None):
        self.seq += 1
        context = context or self.c.context
        xy = [[120., 100.] for _ in range(17)]
        xy[5], xy[6], xy[11], xy[12] = [200., 150.], [300., 150.], [200., 300.], [300., 300.]
        r = math.radians(angle)
        xy[7], xy[9] = [200+100*math.sin(r), 150+100*math.cos(r)], [200+150*math.sin(r), 150+150*math.cos(r)]
        xy[13], xy[15] = [200., 400.], [200., 500.]
        pose = PoseFrame(context, self.seq, t, (1280, 720), [PosePerson(context.epoch+':1', [100, 50, 500, 600], xy, [1.]*17)], model_manifest_id='synthetic-schema-test')
        packet = FramePacket(context, self.seq, t, time.monotonic(), utc_now(), np.zeros((720, 1280, 3), dtype=np.uint8), time_basis='synthetic_test_time')
        return self.c.consume(packet, pose)

    def test_preview_start_shoulder_save_and_reopen(self):
        self.c.start()
        t = 0
        for angle in (0, 90, 0):
            for _ in range(20):
                self.frame(t, angle)
                t += .1
        self.assertEqual(self.c.engine.completed, 1)
        run_id = self.c.context.run_id
        self.c.stop('user_stop')
        self.assertIsNone(self.c.latest_packet)
        self.store.close()
        self.store = Storage(Path(self.temp.name)/'test.sqlite3')
        self.c.storage = self.store
        saved = self.store.get_session(run_id)
        self.assertEqual(saved['summary']['completed'], 1)
        self.assertEqual(saved['source_kind'], 'SYNTHETIC')
        self.assertEqual(saved['usage_context'], 'TEST')
        self.assertNotIn('poses', saved)

    def test_preview_packets_rejected_after_start(self):
        old = self.c.context
        self.c.start()
        self.assertFalse(self.frame(1, 90, old))
        self.assertEqual(self.c.engine.completed, 0)

    def test_privacy_has_no_active_context_and_rejects_late_data(self):
        self.c.start()
        old = self.c.context
        self.c.stop('privacy_pause', privacy=True)
        self.assertEqual(self.c.state, 'PRIVACY_PAUSED')
        self.assertIsNone(self.camera.worker)
        self.assertFalse(self.frame(1, 90, old))

    def test_failed_save_keeps_snapshot_and_blocks_new_run(self):
        self.c.start()
        original = self.store.save_session
        def failure(snapshot):
            raise OSError('simulated disk full')
        self.store.save_session = failure
        try:
            with self.assertRaises(RuntimeError):
                self.c.stop('user_stop')
            self.assertEqual(self.c.state, 'SAVE_FAILED')
            self.assertIsNotNone(self.c.pending)
            self.assertTrue(self.c.pending_path.exists())
            with self.assertRaises(RuntimeError):
                self.c.open(self.source, self.setup)
        finally:
            self.store.save_session = original
        self.c.retry_save()
        self.assertIsNone(self.c.pending)

    def test_session_rules_are_immutable_after_start(self):
        self.c.start()
        self.setup['plan']['target_angle_deg'] = 150
        self.assertIsNone(self.c.session['config_snapshot']['plan']['target_angle_deg'])
        self.assertEqual(self.c.session['config_snapshot']['preprocessing']['imgsz'], 640)
        self.c.vision_config['imgsz'] = 320
        self.assertEqual(self.c.session['config_snapshot']['preprocessing']['imgsz'], 640)

    def test_pending_backup_and_explicit_discard_are_audited(self):
        self.c.pending = {'id': 'pending-fixture', 'config_snapshot': {'poses_consent': False}}
        out = self.c.backup_pending(self.temp.name)
        self.assertTrue(out.exists())
        with self.assertRaises(ValueError):
            self.c.discard_pending('')
        self.c.discard_pending('synthetic test explicitly discarded')
        self.assertIsNone(self.c.pending)
        rows = self.store._call(lambda db: db.execute("SELECT COUNT(*) FROM audit WHERE action='discard_pending_session'").fetchone()[0])
        self.assertEqual(rows, 1)

    def test_changed_frame_shape_ends_task(self):
        self.c.start()
        ctx = self.c.context
        self.seq += 1
        packet = FramePacket(ctx, self.seq, 1, time.monotonic(), utc_now(), np.zeros((480, 640, 3), dtype=np.uint8))
        pose = PoseFrame(ctx, self.seq, 1, (640, 480), [])
        with self.assertRaises(RuntimeError):
            self.c.consume(packet, pose)
        self.assertIsNone(self.c.context)


if __name__ == '__main__':
    unittest.main()
