import unittest
from camera_reference import (
    DeviceDescriptor, DeviceSelectionRequired, resolve_saved_device,
    saved_device_reference, display_to_raw_normalized, RunGate, RunContext,
)


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.a = DeviceDescriptor('USB Camera', 'path-A', 700, 0, 1, 2)
        self.b = DeviceDescriptor('USB Camera', 'path-B', 700, 1, 1, 2)

    def test_current_index_resolved_not_saved_index(self):
        current = DeviceDescriptor('USB Camera', 'path-A', 700, 3, 1, 2)
        self.assertEqual(resolve_saved_device(saved_device_reference(self.a), [self.b, current]).index, 3)

    def test_name_vid_pid_are_not_unique_identity(self):
        self.assertEqual(resolve_saved_device(saved_device_reference(self.b), [self.a, self.b]), self.b)

    def test_missing_does_not_open_another_camera(self):
        with self.assertRaises(DeviceSelectionRequired):
            resolve_saved_device(saved_device_reference(self.a), [self.b])

    def test_backend_mismatch_requires_selection(self):
        changed = DeviceDescriptor('USB Camera', 'path-A', 1400, 0)
        with self.assertRaises(DeviceSelectionRequired):
            resolve_saved_device(saved_device_reference(self.a), [changed])

    def test_empty_path_requires_selection(self):
        with self.assertRaises(DeviceSelectionRequired):
            resolve_saved_device({'path': '', 'backend': 700, 'index': 0}, [self.a])

    def test_duplicate_path_is_ambiguous(self):
        with self.assertRaises(DeviceSelectionRequired):
            resolve_saved_device(saved_device_reference(self.a), [self.a, self.a])

    def test_no_persistent_index(self):
        self.assertNotIn('index', saved_device_reference(self.a))


class MappingTests(unittest.TestCase):
    def test_letterbox_center(self):
        self.assertEqual(display_to_raw_normalized(400, 400, 1280, 720, 800, 800), (.5, .5))

    def test_black_border_rejected(self):
        self.assertIsNone(display_to_raw_normalized(400, 10, 1280, 720, 800, 800))

    def test_horizontal_mirror(self):
        self.assertEqual(display_to_raw_normalized(200, 400, 1280, 720, 800, 800, mirror=True), (.75, .5))

    def test_same_aspect_different_resolution(self):
        self.assertEqual(display_to_raw_normalized(200, 400, 1280, 720, 800, 800),
                         display_to_raw_normalized(200, 400, 1920, 1080, 800, 800))

    def test_invalid_dimensions_and_point(self):
        self.assertIsNone(display_to_raw_normalized(0, 0, 0, 720, 800, 800))
        self.assertIsNone(display_to_raw_normalized(float('nan'), 0, 1280, 720, 800, 800))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate = RunGate()
        self.preview = self.gate.enter_preview('rehab', 'camera-A', 'LIVE_CAMERA')

    def test_preview_never_drives_business(self):
        self.assertFalse(self.gate.admit(self.preview, 1))

    def test_setup_required(self):
        with self.assertRaises(RuntimeError):
            self.gate.start(setup_confirmed=False)

    def test_old_preview_packet_rejected_after_start(self):
        running = self.gate.start(setup_confirmed=True)
        self.assertFalse(self.gate.admit(self.preview, 10))
        self.assertTrue(self.gate.admit(running, 11))

    def test_duplicate_and_reversed_sequence(self):
        running = self.gate.start(setup_confirmed=True)
        self.assertTrue(self.gate.admit(running, 5))
        self.assertFalse(self.gate.admit(running, 5))
        self.assertFalse(self.gate.admit(running, 4))

    def test_switch_rejects_old_inference(self):
        old = self.gate.start(setup_confirmed=True)
        self.gate.invalidate()
        self.gate.enter_preview('safety_demo', 'camera-A', 'LIVE_CAMERA')
        current = self.gate.start(setup_confirmed=True)
        self.assertFalse(self.gate.admit(old, 99))
        self.assertTrue(self.gate.admit(current, 1))

    def test_context_source_mismatch(self):
        cur = self.gate.start(setup_confirmed=True)
        wrong = RunContext(cur.generation, cur.scene_id, 'camera-B', cur.source_kind)
        self.assertFalse(self.gate.admit(wrong, 1))

    def test_cannot_replace_active_preview_without_stop(self):
        with self.assertRaises(RuntimeError):
            self.gate.enter_preview('activity', 'camera-B', 'LIVE_CAMERA')

    def test_stop_rejects_late_results(self):
        cur = self.gate.start(setup_confirmed=True)
        self.gate.invalidate()
        self.assertFalse(self.gate.admit(cur, 100))

    def test_replay_and_live_are_distinct(self):
        live = self.gate.start(setup_confirmed=True)
        self.gate.invalidate()
        self.gate.enter_preview('rehab', 'clip-A', 'REPLAY_FILE')
        replay = self.gate.start(setup_confirmed=True)
        self.assertNotEqual(live.source_kind, replay.source_kind)
        self.assertFalse(self.gate.admit(live, 1))


if __name__ == '__main__':
    unittest.main()
