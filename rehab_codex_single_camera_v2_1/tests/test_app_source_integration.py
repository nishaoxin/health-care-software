import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.domain import Context
from app.source_worker import SourceWorker


class ReplayIntegrationTests(unittest.TestCase):
    """Actual codec/capture subprocess integration on synthetic video; no camera claim."""
    def test_preview_boundary_media_time_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'synthetic.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
            self.assertTrue(writer.isOpened())
            for i in range(15):
                writer.write(np.full((240, 320, 3), i*10, dtype=np.uint8))
            writer.release()
            preview = Context(1, 'rehab', 'synthetic-recording', 'REPLAY_FILE', 'TEST')
            worker = SourceWorker({'kind': 'REPLAY_FILE', 'path': str(path)}, preview, {'speed': 2})
            worker.start()
            def next_frame():
                deadline = time.monotonic()+8
                while time.monotonic() < deadline:
                    packet = worker.read_latest()
                    if packet is not None:
                        return packet
                    time.sleep(.01)
                self.fail('Replay subprocess did not deliver a frame')
            try:
                first = next_frame()
                self.assertEqual(first.context, preview)
                worker.acknowledge(first.seq)
                time.sleep(.15)
                self.assertIsNone(worker.read_latest())
                worker.preview_segment(.4)
                for _ in range(4):
                    inspected = next_frame()
                    self.assertEqual(inspected.context, preview)
                    worker.acknowledge(inspected.seq)
                time.sleep(.15)
                self.assertIsNone(worker.read_latest())
                active = Context(2, 'rehab', 'synthetic-recording', 'REPLAY_FILE', 'TEST', run_id='run')
                worker.change_context(active)
                times = []
                for _ in range(5):
                    packet = next_frame()
                    self.assertEqual(packet.context, active)
                    self.assertEqual(packet.time_basis, 'opencv_media_pts')
                    times.append(packet.time_s)
                    worker.acknowledge(packet.seq)
                self.assertAlmostEqual(times[-1]-times[0], .4, places=3)
            finally:
                self.assertTrue(worker.stop())
                self.assertFalse(worker.process.is_alive())


if __name__ == '__main__':
    unittest.main()
