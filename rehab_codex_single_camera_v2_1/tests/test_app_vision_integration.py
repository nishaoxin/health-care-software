import importlib.util
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np
from app.domain import Context, FramePacket, utc_now
from app.settings import ROOT
from app.vision import VisionWorker


class VisionTests(unittest.TestCase):
    def packet(self, generation, seq=1):
        return FramePacket(Context(generation, 'rehab', 'blank-frame', 'SYNTHETIC', 'TEST'),
                           seq, seq*.1, time.monotonic(), utc_now(), np.zeros((480, 640, 3), dtype=np.uint8))

    def test_missing_model_does_not_download(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = VisionWorker(Path(directory)/'missing.pt')
            try:
                with self.assertRaisesRegex(RuntimeError, '不会自动下载'):
                    worker.infer(self.packet(1))
                self.assertEqual(list(Path(directory).iterdir()), [])
            finally:
                worker.close()

    @unittest.skipUnless((ROOT/'assets/models/yolo11n-pose.pt').is_file() and importlib.util.find_spec('ultralytics'), 'Official local weights / vision dependencies not prepared')
    def test_cpu_inference_and_real_bytetrack_reset_api(self):
        worker = VisionWorker(device='cpu')
        try:
            packet = self.packet(1)
            first = worker.infer(packet)
            self.assertEqual(first.people, [])
            self.assertEqual(first.schema_id, 'coco17-v1')
            packet.seq += 1
            packet.time_s += .1
            worker.infer(packet)
            self.assertEqual(worker.model.predictor.trackers[0].frame_id, 2)
            last = worker.infer(self.packet(2))
            self.assertEqual(worker.model.predictor.trackers[0].frame_id, 1)
            self.assertEqual(first.model_manifest_id, last.model_manifest_id)
        finally:
            worker.close()


if __name__ == '__main__':
    unittest.main()
