import json
import unittest

from app.domain import Context, PoseFrame, PosePerson, PacketGate, dumps
from app.quality import PoseAnalyzer


def pose(t=0., seq=1, context=None):
    xy = [[120., 100.] for _ in range(17)]
    xy[5], xy[6] = [200., 150.], [300., 150.]
    xy[11], xy[12] = [200., 300.], [300., 300.]
    xy[7], xy[9] = [350., 150.], [450., 150.]
    xy[13], xy[15] = [200., 400.], [200., 500.]
    return PoseFrame(context or Context(1, 'rehab', 'test', 'SYNTHETIC', 'TEST'), seq, t,
                     (1280, 720), [PosePerson('1', [150., 80., 480., 600.], xy, [1.]*17)])


class ContractTests(unittest.TestCase):
    def test_invalid_schema_is_rejected_even_with_seventeen_points(self):
        p = pose()
        p.schema_id = 'other17'
        with self.assertRaises(ValueError):
            PoseAnalyzer().analyze(p)

    def test_wrong_order_rejected(self):
        p = pose()
        p.keypoint_order_version = 'swapped'
        with self.assertRaises(ValueError):
            PoseAnalyzer().analyze(p)

    def test_wrist_missing_independent_shoulder(self):
        p = pose()
        p.people[0].conf[9] = .1
        o = PoseAnalyzer().analyze(p)
        self.assertAlmostEqual(o.value('raise_deg'), 90)
        self.assertIsNone(o.value('elbow_flexion_deg'))

    def test_missing_knee_is_null(self):
        p = pose()
        p.people[0].conf[13] = .1
        o = PoseAnalyzer().analyze(p)
        self.assertIsNone(o.value('knee_flexion_deg'))

    def test_global_downward_motion_not_removed_by_local_normalization(self):
        analyzer = PoseAnalyzer()
        a = analyzer.analyze(pose())
        p = pose(.1, 2)
        p.people[0].xy = [[x, y+30] for x, y in p.people[0].xy]
        b = analyzer.analyze(p)
        self.assertAlmostEqual(b.center_raw_px[1]-a.center_raw_px[1], 30)
        self.assertEqual(a.local_pose, b.local_pose)

    def test_old_generation_and_duplicate_are_rejected(self):
        gate = PacketGate()
        p = pose()
        gate.reset(p.context)
        self.assertTrue(gate.admit(p))
        self.assertFalse(gate.admit(p))
        gate.reset(Context(2, 'rehab', 'test', 'SYNTHETIC', 'TEST'))
        self.assertFalse(gate.admit(p))

    def test_bad_time_rejected(self):
        p = pose()
        gate = PacketGate()
        gate.reset(p.context)
        p.time_s = None
        self.assertFalse(gate.admit(p))

    def test_json_is_standard_and_nan_is_null(self):
        self.assertEqual(json.loads(dumps({'x': float('nan'), 'y': float('inf')})), {'x': None, 'y': None})


if __name__ == '__main__':
    unittest.main()
