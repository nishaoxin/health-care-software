import copy
import unittest

from app.activity import ActivityEngine
from app.bedroom import BedroomEngine
from app.safety import SafetyEngine
from app.domain import Metric, Observation
from app.settings import default_setup


def observed(t, knee=90, center=(.5, .65), tilt=0, valid=True, track='one', ankle=0):
    values = {'knee_flexion_deg': knee, 'hip_y': center[1], 'left_knee': knee,
              'right_knee': knee, 'trunk_tilt_deg': tilt, 'ankle_delta': ankle, 'torso_scale_px': 200}
    return Observation(t, track if valid else None, 'VALID' if valid else 'NO_PERSON_DETECTED',
                       {k: Metric.of(v) for k, v in values.items()},
                       tuple(v*1000 for v in center) if valid else None,
                       [300, 400, 800, 700], size=(1000, 1000))


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.setup = default_setup('activity')
        self.setup.update(rois={'chair': [.1, .4, .9, .9]}, sedentary_trigger_s=1, stand_target_s=1)
        self.engine = ActivityEngine(self.setup)

    def test_visible_sitting_reminder_and_stand_task(self):
        for i in range(15):
            self.engine.process(observed(i*.1))
        self.assertTrue(self.engine.reminder_due)
        self.engine.choose_task('stand', 1.4)
        for i in range(15, 30):
            self.engine.process(observed(i*.1, knee=5, center=(.5, .35)))
        self.assertEqual(self.engine.tasks[-1]['status'], 'COMPLETED')
        self.assertTrue(self.engine.tasks[-1]['visual_verified'])

    def test_gap_does_not_add_sitting_time_or_resume_continuous_timer(self):
        self.engine.process(observed(0))
        self.engine.process(observed(.2))
        self.engine.process(observed(100))
        self.assertAlmostEqual(self.engine.totals['SEATED'], .2)
        self.assertEqual(self.engine.continuous_sitting, 0)

    def test_self_report_is_not_visual_completion(self):
        self.engine.choose_task('walk', 0)
        self.engine.choose_task('self_report', .1)
        task = self.engine.tasks[-1]
        self.assertTrue(task['self_reported'])
        self.assertFalse(task['visual_verified'])
        self.assertNotEqual(task['status'], 'COMPLETED')

    def test_missing_person_interrupts_task(self):
        self.engine.choose_task('stand', 0)
        self.engine.process(observed(0, knee=5))
        self.engine.process(observed(.2, valid=False))
        self.engine.process(observed(.8, valid=False))
        self.assertEqual(self.engine.tasks[-1]['status'], 'INTERRUPTED')

    def test_upper_body_motion_does_not_complete_walk(self):
        self.engine.choose_task('walk', 0)
        for i in range(30):
            o = observed(i*.1, knee=None, center=(.2+i*.01, .35))
            o.metrics['ankle_delta'] = Metric.missing('occlusion')
            self.engine.process(o)
        self.assertFalse(self.engine.tasks[-1]['visual_verified'])

    def test_playback_speed_is_not_a_business_clock(self):
        a, b = ActivityEngine(self.setup), ActivityEngine(self.setup)
        sequence = [observed(i*.1) for i in range(30)]
        for o in sequence:
            a.process(o)
        for o in sequence:
            b.process(copy.deepcopy(o))
        self.assertEqual(a.totals, b.totals)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.setup = default_setup('safety_demo')
        self.setup['rois'] = {'floor_watch': [0, .5, 1, 1]}
        self.engine = SafetyEngine(self.setup)

    def test_sustained_low_without_descent_has_honest_evidence(self):
        for i in range(30):
            self.engine.process(observed(i*.1, tilt=80))
        self.assertEqual(len(self.engine.events), 1)
        self.assertEqual(self.engine.events[0]['rule_id'], 'persistent_low_without_observed_descent')
        self.assertEqual(self.engine.events[0]['status'], 'OPEN')

    def test_bed_exclusion_does_not_raise_floor_event(self):
        self.setup['rois']['bed'] = [.1, .5, .9, .9]
        engine = SafetyEngine(self.setup)
        for i in range(30):
            engine.process(observed(i*.1, tilt=80))
        self.assertEqual(engine.events, [])

    def test_missing_and_long_gap_cannot_bridge_low_hold(self):
        self.engine.process(observed(0, tilt=80))
        self.engine.process(observed(.1, tilt=80))
        self.engine.process(observed(10, tilt=80))
        self.assertEqual(self.engine.events, [])

    def test_future_frames_do_not_rewrite_emitted_time(self):
        for i in range(25):
            self.engine.process(observed(i*.1, tilt=80))
        event = copy.deepcopy(self.engine.events[0])
        for i in range(25, 60):
            self.engine.process(observed(i*.1, tilt=0, center=(.5, .3)))
        self.assertEqual(event, self.engine.events[0])
        self.assertEqual(event['status'], 'OPEN')

    def test_duplicate_time_does_not_emit_again(self):
        self.engine.process(observed(0, tilt=80))
        for _ in range(100):
            self.engine.process(observed(0, tilt=80))
        self.assertEqual(self.engine.events, [])


class BedroomTests(unittest.TestCase):
    def test_no_person_is_not_observed_exit(self):
        setup = default_setup('bedroom_demo')
        setup['rois'] = {'bed': [0, .5, .4, 1], 'bed_edge': [.4, .4, .7, 1], 'exit': [.8, 0, 1, 1]}
        e = BedroomEngine(setup)
        e.process(observed(0, center=(.5, .6), knee=5))
        e.process(observed(.2, valid=False))
        self.assertEqual(e.phase, 'UNKNOWN')
        self.assertNotIn('OBSERVED_EXIT', [x['state'] for x in e.intervals])


if __name__ == '__main__':
    unittest.main()
