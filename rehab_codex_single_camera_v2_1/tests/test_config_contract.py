from pathlib import Path
import json
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = yaml.safe_load((ROOT/'configs/app.example.yaml').read_text(encoding='utf-8'))
        cls.scenes = yaml.safe_load((ROOT/'configs/scenes.example.yaml').read_text(encoding='utf-8'))

    def test_single_active_source(self):
        self.assertEqual(self.app['capture']['max_active_sources'], 1)
        self.assertEqual(self.scenes['max_active_scenes'], 1)
        self.assertEqual(self.app['vision']['inference_concurrency'], 1)

    def test_no_implicit_camera_or_fallback(self):
        self.assertIsNone(self.app['app']['current_device_ref'])
        self.assertFalse(self.app['capture']['automatic_device_fallback'])
        self.assertFalse(self.app['capture']['automatic_backend_fallback'])

    def test_initial_connection_allows_slow_camera_startup(self):
        self.assertGreater(self.app['capture']['connect_timeout_s'], self.app['capture']['stale_after_s'])

    def test_four_scenes_not_background_jobs(self):
        self.assertEqual(set(self.scenes['scenes']), {'rehab','activity','bedroom_demo','safety_demo'})
        for scene in self.scenes['scenes'].values():
            self.assertFalse(scene['background_monitoring'])
            self.assertIsNone(scene['default_device_ref'])

    def test_future_devices_not_required(self):
        self.assertFalse(any(self.app['future_extensions'].values()))
        self.assertEqual(self.app['capture']['allowed_source_kinds'], ['LIVE_CAMERA','REPLAY_FILE'])

    def test_switch_keeps_alerts_and_requires_release(self):
        self.assertTrue(self.app['lifecycle']['persist_unresolved_alerts'])
        self.assertTrue(self.app['lifecycle']['block_new_capture_until_old_released'])
        self.assertFalse(self.scenes['scenes']['safety_demo']['auto_resolve_on_mode_switch'])

    def test_profile_is_unconfigured_not_default_roi(self):
        p = json.loads((ROOT/'configs/setup_profile.example.json').read_text(encoding='utf-8'))
        self.assertEqual(p['status'], 'NEEDS_SETUP')
        self.assertIsNone(p['device_ref'])
        self.assertEqual(p['rois'], {})

    def test_radar_not_core_dependency(self):
        entries = (ROOT/'requirements.in').read_text(encoding='utf-8').splitlines()
        self.assertNotIn('pyserial', [s.strip() for s in entries if not s.startswith('#')])
        self.assertIn('cv2-enumerate-cameras', entries)


if __name__ == '__main__':
    unittest.main()
