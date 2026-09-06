import copy
import unittest

from app.domain import Metric, Observation
from app.rehab import RehabEngine
from app.settings import default_plan


def observation(t, angle=0, knee=90, hip=.65, track='one', valid=True, elbow=0, tilt=0):
    values = {'raise_deg': angle, 'knee_flexion_deg': knee, 'hip_y': hip,
              'elbow_flexion_deg': elbow, 'trunk_tilt_deg': tilt}
    metrics = {k: Metric.of(v) for k, v in values.items()}
    if not valid:
        metrics['raise_deg'] = Metric.missing('occlusion')
        metrics['knee_flexion_deg'] = Metric.missing('occlusion')
    return Observation(t, track, 'VALID' if valid else 'UNKNOWN', metrics)


class RehabTests(unittest.TestCase):
    def setUp(self):
        self.plan = default_plan('shoulder_abduction')
        self.engine = RehabEngine(self.plan)
        self.t = 0.0

    def frames(self, angle, n=15, **kw):
        for _ in range(n):
            self.engine.process(observation(self.t, angle, **kw))
            self.t += .1

    def cycle(self, angle=70, **kw):
        self.frames(0)
        self.frames(angle, **kw)
        self.frames(0)

    def test_full_return_without_target_is_complete_and_not_set(self):
        self.cycle()
        self.assertEqual(self.engine.completed, 1)
        self.assertEqual(self.engine.repetitions[0]['target_status'], 'NOT_SET')

    def test_below_personal_target_still_counts(self):
        self.plan['target_angle_deg'] = 100
        self.engine = RehabEngine(self.plan)
        self.cycle(60)
        self.assertEqual(self.engine.completed, 1)
        self.assertEqual(self.engine.repetitions[0]['target_status'], 'NOT_MET')

    def test_start_with_arm_raised_does_not_complete_a_preview_half_cycle(self):
        self.frames(90)
        self.frames(0)
        self.assertEqual(self.engine.completed, 0)

    def test_stop_without_return_records_interrupted(self):
        self.frames(0)
        self.frames(70)
        self.engine.finish('user_stop')
        self.assertEqual(self.engine.completed, 0)
        self.assertEqual(self.engine.repetitions[-1]['completion_status'], 'INTERRUPTED')

    def test_missing_wrist_keeps_count_but_no_elbow_feedback(self):
        self.plan['allowed_elbow_flexion_deg'] = 10
        self.engine = RehabEngine(self.plan)
        self.cycle(elbow=None)
        rep = self.engine.repetitions[0]
        self.assertEqual(self.engine.completed, 1)
        self.assertFalse(rep['metric_validity']['elbow_flexion_deg']['valid'])
        self.assertEqual(rep['issues'], [])

    def test_two_issues_coexist_and_config_is_snapshot(self):
        self.plan.update(allowed_elbow_flexion_deg=10, allowed_trunk_tilt_deg=10)
        self.engine = RehabEngine(self.plan)
        self.plan['allowed_elbow_flexion_deg'] = 150
        self.cycle(elbow=35, tilt=30)
        ids = {x['rule_id'] for x in self.engine.repetitions[0]['issues']}
        self.assertEqual(ids, {'elbow_flexion', 'trunk_tilt'})

    def test_stream_gap_cannot_complete_a_cycle(self):
        self.frames(0)
        self.frames(80)
        self.t += 2
        self.frames(0)
        self.assertEqual(self.engine.completed, 0)
        self.assertEqual(self.engine.repetitions[0]['completion_status'], 'UNASSESSABLE')

    def test_identity_change_cannot_join_people(self):
        self.frames(0)
        self.frames(80)
        self.frames(0, track='two')
        self.assertEqual(self.engine.completed, 0)

    def test_nonmonotonic_frames_have_no_effect(self):
        self.cycle()
        before = copy.deepcopy(self.engine.summary())
        self.engine.process(observation(0, 100))
        self.assertEqual(self.engine.summary(), before)


class SitStandTests(unittest.TestCase):
    def setUp(self):
        plan = default_plan('sit_to_stand')
        plan['calibration'] = {'seated_knee': 90, 'standing_knee': 5,
                               'seated_hip_y': .65, 'standing_hip_y': .40}
        self.engine = RehabEngine(plan)
        self.t = 0

    def phase(self, knee, hip, n=15):
        for _ in range(n):
            self.engine.process(observation(self.t, knee=knee, hip=hip))
            self.t += .1

    def test_count_at_standing_and_finish_keeps_n(self):
        self.phase(90, .65)
        self.phase(45, .52)
        self.phase(5, .4)
        self.assertEqual(self.engine.completed, 1)
        self.engine.finish('user_stop')
        self.assertEqual(self.engine.completed, 1)
        self.assertIsNone(self.engine.repetitions[0]['lowering_time_s'])

    def test_standing_alone_does_not_count_or_rearm(self):
        self.phase(5, .4)
        self.assertEqual(self.engine.completed, 0)
        self.phase(90, .65)
        self.phase(40, .5)
        self.phase(5, .4, 30)
        self.assertEqual(self.engine.completed, 1)

    def test_partial_rise_is_retained(self):
        self.phase(90, .65)
        self.phase(50, .54)
        self.phase(90, .65)
        self.assertEqual(self.engine.completed, 0)
        self.assertEqual(self.engine.repetitions[0]['completion_status'], 'PARTIAL')


if __name__ == '__main__':
    unittest.main()
