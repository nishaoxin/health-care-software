import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import queue
import unittest

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from app.domain import Context, FramePacket
from app.settings import default_plan
from app.assessment import build_body_profile
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

    def test_assessment_training_are_separate_sections_and_expanded_actions_available(self):
        self.assertEqual(self.window.title.text(), '身体评估')
        self.assertEqual(self.window.exercise.count(), 53)
        self.assertTrue(self.window.submode.isHidden())
        self.window._select_rehab('training')
        self.assertEqual(self.window.title.text(), '训练指导')
        self.assertEqual(self.window._read_setup()['plan']['submode'], 'training')
        self.window.state, self.window._confirmed = 'PREVIEW', True
        self.window._buttons()
        self.assertFalse(self.window.start_button.isEnabled())

    def test_exercise_switch_preserves_person_and_mode_but_not_goal(self):
        self.window.participant.setText('user-002')
        self.window._apply_participant()
        self.window._select_rehab('training')
        self.window.setup['plan'].update(target_angle_deg=90, assessment_reference={'session_id': 'old'})
        self.window.exercise.setCurrentIndex(self.window.exercise.findData('hip_abduction'))
        plan = self.window._read_setup()['plan']
        self.assertEqual(plan['participant_id'], 'user-002')
        self.assertEqual(plan['submode'], 'training')
        self.assertIsNone(plan['target_angle_deg'])
        self.assertFalse(plan.get('assessment_reference'))
        self.assertEqual(self.window.view.currentData(), 'frontal')

    def test_body_part_filter_and_calibration_controls(self):
        w = self.window
        w.joint_group.setCurrentIndex(w.joint_group.findData('wrist'))
        self.assertEqual(w.exercise.count(), 4)
        self.assertEqual(w.exercise.currentData(), 'wrist_flexion')
        self.assertFalse(w.joint_direction_button.isHidden())
        self.assertIn('实验性', w.action_guide.text())
        w.setup['plan']['joint_baseline'] = {'rest_value': 10}
        w.side.setCurrentIndex(1)
        self.assertFalse(w.setup['plan']['joint_baseline'])
        w.joint_group.setCurrentIndex(w.joint_group.findData('finger'))
        self.assertEqual(w.exercise.count(), 28)
        self.assertTrue(w.joint_direction_button.isHidden())
        self.assertFalse(w.joint_rest_button.isEnabled())
        w.state = 'PREVIEW'
        w._buttons()
        self.assertTrue(w.joint_rest_button.isEnabled())

    def test_hand_canvas_accepts_unknown_confidence_and_missing_points(self):
        from test_app_landmarks import frame
        pose = frame('mediapipe-hand21-v1')
        pose.people[0].xy[4] = [None, None]
        packet = FramePacket(pose.context, 1, 0., 0., '', np.zeros((720,1280,3), dtype=np.uint8))
        self.window.canvas.set_frame(packet, pose)
        self.window.canvas.grab()  # Exercise actual Qt paint path without a camera.

    def test_body_summary_waits_for_successful_save_even_when_retrying(self):
        self.window._choose_catalog_exercise('shoulder_abduction')
        self.window.state = 'ONLINE'
        self.window._finish_task()
        self.assertEqual(self.runtime.calls[-1][0], 'stop')
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.window._handle_message({'kind': 'error', 'command': 'stop', 'text': '保存失败'})
        self.assertNotIn('body_profile', [x[0] for x in self.runtime.calls])
        self.window._handle_message({'kind': 'command_done', 'command': 'stop'})
        self.window._handle_message({'kind': 'saved', 'id': 'assessment-001'})
        self.assertEqual(self.runtime.calls[-1][0], 'body_profile')
        self.assertEqual(self.window.pages.currentIndex(), 2)

    def test_body_profile_response_for_other_person_is_ignored(self):
        profile = build_body_profile([], 'somebody-else')
        self.window._handle_message({'kind': 'body_profile', 'profile': profile, 'html': 'WRONG USER'})
        self.assertIsNone(self.window.body_profile)
        self.assertNotIn('WRONG USER', self.window.body_browser.toPlainText())

    def test_empty_body_profile_has_no_training_entry(self):
        profile = build_body_profile([], self.window.participant_id)
        self.window._handle_message({'kind': 'body_profile', 'profile': profile, 'html': '<p>尚未评估</p>'})
        self.assertEqual(self.window.body_action.count(), 0)
        self.assertFalse(self.window.body_train.isEnabled())

    def test_switch_person_clears_previous_goal_and_reference(self):
        self.window.setup['plan'].update(target_angle_deg=90, assessment_reference={'session_id': 'old'}, training_plan_confirmed=True)
        self.window.participant.setText('person-b')
        self.window._apply_participant()
        self.assertEqual(self.window._read_setup()['plan']['participant_id'], 'person-b')
        self.assertIsNone(self.window.setup['plan']['target_angle_deg'])
        self.assertFalse(self.window.setup['plan'].get('assessment_reference'))

    def test_side_switch_cannot_inherit_other_side_goal_or_training_reference(self):
        self.window._select_rehab('training')
        self.window.setup['plan'].update(target_angle_deg=90, assessment_reference={'session_id': 'left'}, training_plan_confirmed=True)
        self.window.side.setCurrentIndex(self.window.side.findData('right'))
        plan = self.window._read_setup()['plan']
        self.assertEqual(plan['side'], 'right')
        self.assertIsNone(plan['target_angle_deg'])
        self.assertFalse(plan.get('assessment_reference'))
        self.assertFalse(plan.get('training_plan_confirmed'))

    def test_pending_user_name_cannot_be_mistaken_for_applied_identity(self):
        self.window.state, self.window._confirmed = 'PREVIEW', True
        self.window.participant.setText('not-yet-applied')
        self.assertFalse(self.window.start_button.isEnabled())
        self.window._preview()
        self.assertIn('尚未应用', self.window.notice.text())
        self.assertFalse(any(n == 'open' for n, _ in self.runtime.calls))

    def test_late_same_scene_frame_cannot_relabel_previous_exercise_as_new_one(self):
        self.window.state = 'ONLINE'
        self.window.last_generation = 5
        self.window.exercise.setCurrentIndex(self.window.exercise.findData('hip_abduction'))
        self.window._render_view({'state': 'ONLINE', 'context': Context(5, 'rehab', 'old', 'SYNTHETIC', 'TEST'),
                                  'confirmed': True, 'summary': {'completed': 99}})
        self.assertEqual(self.window.state, 'UNSELECTED')
        self.assertFalse(self.window._confirmed)

    def test_each_new_action_switches_to_its_required_camera_view(self):
        for exercise, view in (('shoulder_flexion', 'sagittal'), ('elbow_flexion', 'sagittal'),
                               ('knee_extension', 'sagittal'), ('hip_abduction', 'frontal')):
            self.window.exercise.setCurrentIndex(self.window.exercise.findData(exercise))
            self.assertEqual(self.window.view.currentData(), view)
            self.assertNotIn('站位膝', self.window.action_guide.text())

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
