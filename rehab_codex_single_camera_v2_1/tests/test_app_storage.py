import tempfile
import unittest
from pathlib import Path

from app.storage import Storage
from app.reports import export_session


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'records.sqlite3'
        self.store = Storage(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def snapshot(self):
        return {'id': 'one', 'scene_id': 'rehab', 'start_utc': '2026-09-06T08:00:00+00:00',
                'source_kind': 'SYNTHETIC', 'usage_context': 'TEST',
                'config_snapshot': {'poses_consent': False}, 'summary': {'completed': 1},
                'repetitions': [], 'metrics': [], 'events': [], 'poses': [{'private': True}]}

    def test_report_reopens_after_connection_restart(self):
        self.store.save_session(self.snapshot())
        self.store.close()
        self.store = Storage(self.path)
        self.assertEqual(self.store.get_session('one')['summary']['completed'], 1)

    def test_closed_consent_never_saves_poses(self):
        self.store.save_session(self.snapshot())
        self.assertNotIn('poses', self.store.get_session('one'))
        out = Path(self.temp.name) / 'export'
        export_session(self.store.get_session('one'), out)
        self.assertFalse((out/'poses.jsonl').exists())
        self.assertFalse((out/'source.mp4').exists())
        self.assertTrue((out/'report.html').exists())

    def test_ack_does_not_resolve_and_events_survive_restart(self):
        self.store.save_event({'id': 'alert', 'status': 'OPEN', 'scene_id': 'safety_demo'})
        self.store.transition_event('alert', 'ACKNOWLEDGED', 'operator', '')
        self.assertEqual(self.store.list_events()[0]['status'], 'ACKNOWLEDGED')
        self.store.close()
        self.store = Storage(self.path)
        self.assertEqual(len(self.store.list_events(unresolved=True)), 1)
        self.store.transition_event('alert', 'RESOLVED', 'operator', '已检查现场')
        self.assertEqual(self.store.list_events(unresolved=True), [])

    def test_resolve_requires_ack_and_note(self):
        self.store.save_event({'id': 'alert', 'status': 'OPEN'})
        with self.assertRaises(ValueError):
            self.store.transition_event('alert', 'RESOLVED', 'operator', '')

    def test_report_delete_preserves_open_alerts(self):
        self.store.save_session(self.snapshot())
        self.store.save_event({'id': 'alert', 'run_id': 'one', 'status': 'OPEN'})
        self.store.delete_session('one')
        self.assertEqual(len(self.store.list_events(unresolved=True)), 1)

    def test_readonly_database_reports_write_failure(self):
        self.store.close()
        self.store = Storage(self.path, readonly=True)
        with self.assertRaises(Exception):
            self.store.save_session(self.snapshot())

    def test_crash_recovery_does_not_invent_end_or_results(self):
        item = self.snapshot()
        item.update(status='RUNNING', summary={})
        self.store.save_session(item)
        self.assertEqual(self.store.recover_unfinished(), 1)
        restored = self.store.get_session('one')
        self.assertEqual(restored['status'], 'INTERRUPTED')
        self.assertIsNone(restored['end_utc'])
        self.assertEqual(restored['summary'], {})


if __name__ == '__main__':
    unittest.main()
