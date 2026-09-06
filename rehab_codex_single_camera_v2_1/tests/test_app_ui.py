import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import queue
import unittest

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from app.domain import Context, FramePacket
from app.settings import default_plan
from app.ui.dialogs import PlanDialog
from app.ui.main_window import MainWindow


class DummyRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()
        self.calls = []

    def command(self, name, **kw):
        self.calls.append((name, kw))


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.runtime = DummyRuntime()
        self.window = MainWindow(runtime=self.runtime)

    def tearDown(self):
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_no_source_selected_no_auto_start_or_pose_consent(self):
        self.assertIsNone(self.window.device.currentData())
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertFalse(self.window.poses.isChecked())
        self.assertEqual(self.runtime.calls, [])

    def test_scene_change_interrupts_previous_run(self):
        self.window.state = 'ONLINE'
        self.window._select_scene('activity')
        self.assertIn('switch', [n for n, _ in self.runtime.calls])
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertEqual(self.window.setup['scene_id'], 'activity')

    def test_uncheck_confirmation_revokes_start(self):
        self.window.state = 'PREVIEW'
        self.window.manual.setChecked(True)
        self.window._confirmed = True
        self.window._buttons()
        self.assertTrue(self.window.start_button.isEnabled())
        self.window.manual.setChecked(False)
        self.assertFalse(self.window.start_button.isEnabled())

    def test_roi_edit_revokes_confirmation(self):
        self.window.state = 'PREVIEW'
        self.window._confirmed = True
        self.window._roi_changed('chair', [.1, .1, .5, .5])
        self.assertFalse(self.window.start_button.isEnabled())

    def test_privacy_clears_image(self):
        ctx = Context(1, 'rehab', 'synthetic-ui', 'SYNTHETIC', 'TEST')
        packet = FramePacket(ctx, 1, 0, 0, '', np.zeros((720, 1280, 3), dtype=np.uint8))
        self.window.canvas.set_frame(packet)
        self.window._render_view({'state': 'PRIVACY_PAUSED', 'context': None, 'confirmed': False,
                                   'packet': None, 'pose': None, 'summary': {}})
        self.assertIsNone(self.window.canvas.image)

    def test_canvas_inverse_mapping_handles_mirror_and_letterbox(self):
        ctx = Context(1, 'rehab', 'synthetic-ui', 'SYNTHETIC', 'TEST')
        packet = FramePacket(ctx, 1, 0, 0, '', np.zeros((720, 1280, 3), dtype=np.uint8))
        self.window.canvas.set_frame(packet)
        self.window.canvas.resize(800, 600)
        self.window.canvas.mirror = True
        self.assertIsNone(self.window.canvas.to_raw(QPointF(200, 10)))
        x, y = self.window.canvas.to_raw(QPointF(200, 300))
        self.assertAlmostEqual(x, .75)
        self.assertAlmostEqual(y, .5)

    def test_history_starts_empty(self):
        self.assertEqual(self.window.table.rowCount(), 0)

    def test_personal_goal_can_remain_null(self):
        dialog = PlanDialog(default_plan())
        dialog._save()
        self.assertIsNone(dialog.plan['target_angle_deg'])
        dialog.close()

    def test_new_device_discards_old_baseline_and_roi_candidates(self):
        self.window.setup['plan']['calibration'] = {'seated_knee': 90}
        self.window.setup['rois'] = {'chair': [.1, .1, .5, .5]}
        self.window._device_changed()
        self.assertEqual(self.window.setup['plan']['calibration'], {})
        self.assertEqual(self.window.setup['rois'], {})


if __name__ == '__main__':
    unittest.main()
