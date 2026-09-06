import unittest

from app.camera_manager import CameraManager
from app.domain import Context, DeviceDescriptor


class FakeWorker:
    created = []
    def __init__(self, source, context, options):
        self.source, self.context = source, context
        self.stop_ok = True
        self.created.append(self)

    def start(self):
        pass

    def stop(self):
        return self.stop_ok

    def change_context(self, c):
        self.context = c


class CameraTests(unittest.TestCase):
    def setUp(self):
        FakeWorker.created = []
        self.devices = [DeviceDescriptor('same', 'path1', 700, 4), DeviceDescriptor('same', 'path2', 700, 8)]
        self.manager = CameraManager(enumerator=lambda backend: self.devices, worker_factory=FakeWorker)
        self.context = Context(1, 'rehab', 'camera', 'LIVE_CAMERA', 'SELF_USE')

    def test_refresh_only_enumerates(self):
        self.manager.enumerate(700)
        self.assertEqual(FakeWorker.created, [])

    def test_open_re_resolves_index_and_keeps_backend(self):
        saved = {'path': 'path1', 'backend': 700, 'index': 0}
        self.manager.open_camera(saved, self.context)
        self.assertEqual(self.manager.worker.source['index'], 4)
        self.assertEqual(self.manager.worker.source['backend'], 700)

    def test_missing_device_never_falls_back(self):
        with self.assertRaises(RuntimeError):
            self.manager.open_camera({'path': 'missing', 'backend': 700}, self.context)
        self.assertEqual(FakeWorker.created, [])

    def test_stop_failure_blocks_new_source(self):
        self.manager.open_camera({'path': 'path1', 'backend': 700}, self.context)
        self.manager.worker.stop_ok = False
        with self.assertRaises(RuntimeError):
            self.manager.stop()
        with self.assertRaises(RuntimeError):
            self.manager.open_camera({'path': 'path2', 'backend': 700}, self.context)
        self.assertEqual(len(FakeWorker.created), 1)

    def test_cannot_open_second_source_before_release(self):
        self.manager.open_camera({'path': 'path1', 'backend': 700}, self.context)
        with self.assertRaises(RuntimeError):
            self.manager.open_camera({'path': 'path2', 'backend': 700}, self.context)
        self.manager.stop()
        self.manager.open_camera({'path': 'path2', 'backend': 700}, self.context)
        self.assertEqual(len(FakeWorker.created), 2)


if __name__ == '__main__':
    unittest.main()
