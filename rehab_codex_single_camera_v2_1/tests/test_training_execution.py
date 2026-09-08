"""Time-ordered synthetic observations, not camera/clinical validation."""
import copy

import pytest

from app.training import TrainingEngine, validate_training_feedback
from app.settings import default_plan
from test_app_rehab import observation


class Sequence:
    def __init__(self, exercise='shoulder_abduction', **settings):
        plan = default_plan(exercise)
        plan.update(submode='training', target_reps=2, target_sets=2, rest_between_sets_s=2)
        plan.update(settings)
        if exercise == 'sit_to_stand':
            plan['calibration'] = {'seated_knee': 90, 'standing_knee': 5, 'seated_hip_y': .65, 'standing_hip_y': .4}
        self.engine, self.t = TrainingEngine(plan), 0.

    def frames(self, angle=0, n=15, **kwargs):
        for _ in range(n):
            self.engine.process(observation(self.t, angle, **kwargs))
            self.t += .1

    def cycle(self):
        for angle in (0, 75, 0):
            self.frames(angle)

    def command(self, action):
        self.engine.control(action, self.t)
        self.t += .1


def test_sets_rest_and_manual_next_enforce_plan_without_counting_rest_movements():
    seq = Sequence()
    seq.cycle()
    assert seq.engine.stage == 'ACTIVE'
    seq.cycle()
    assert seq.engine.stage == 'RESTING'
    assert seq.engine.summary()['training']['set_reps'] == 2
    with pytest.raises(ValueError, match='休息'):
        seq.command('next_set')
    evidence = copy.deepcopy(seq.engine.summary()['motion_range'])
    for _ in range(3):
        seq.cycle()
    assert seq.engine.completed == 2 and seq.engine.stage == 'RESTING'
    assert seq.engine.summary()['motion_range'] == evidence
    seq.command('next_set')
    assert seq.engine.phase == 'WAIT_READY'
    seq.frames(75)
    seq.frames(0)
    assert seq.engine.completed == 2  # Half-cycle before new ready state ignored.
    seq.cycle()
    seq.cycle()
    assert seq.engine.stage == 'COMPLETE'
    assert seq.engine.completed == 4
    seq.cycle()
    assert seq.engine.completed == 4
    result = seq.engine.summary()
    assert result['plan_completed'] and result['completed_sets'] == 2
    assert [r['set_number'] for r in seq.engine.repetitions] == [1, 1, 2, 2]
    assert all(s['status'] == 'COMPLETE' for s in result['training']['sets'])


def test_pause_interrupts_partial_and_resume_never_joins_old_motion():
    seq = Sequence()
    seq.frames(0)
    seq.frames(80)
    seq.command('pause')
    assert seq.engine.stage == 'PAUSED'
    assert seq.engine.repetitions[-1]['completion_status'] == 'INTERRUPTED'
    assert seq.engine.repetitions[-1]['observation_reasons'] == ['user_pause']
    old_range = copy.deepcopy(seq.engine.summary()['motion_range'])
    seq.frames(170, n=30)
    seq.frames(0)
    assert seq.engine.completed == 0 and seq.engine.summary()['metrics'] == {}
    assert seq.engine.summary()['motion_range'] == old_range
    seq.command('resume')
    seq.frames(80)
    seq.frames(0)
    assert seq.engine.completed == 0
    seq.cycle()
    assert seq.engine.completed == 1
    assert seq.engine.summary()['training']['paused_s'] > 4


def test_rest_time_and_measurement_time_are_separate_and_gaps_still_reject():
    seq = Sequence(target_reps=1)
    seq.cycle()
    before = seq.engine.summary()
    seq.frames(0, n=100, valid=False)
    after = seq.engine.summary()
    assert after['observed_span_s'] == before['observed_span_s']
    assert after['valid_s'] == before['valid_s']
    assert after['valid_ratio'] == before['valid_ratio']
    assert after['training']['rest_s'] > 9
    seq.command('next_set')
    seq.frames(0)
    seq.frames(80)
    seq.t += 2
    seq.frames(0)
    assert seq.engine.completed == 1
    assert seq.engine.repetitions[-1]['completion_status'] == 'UNASSESSABLE'


def test_pause_during_rest_preserves_remaining_timer_and_does_not_advance_sets():
    seq = Sequence(target_reps=1, rest_between_sets_s=20)
    seq.cycle()
    seq.command('pause')
    remaining = seq.engine.summary()['training']['rest_remaining_s']
    seq.frames(n=50)
    assert seq.engine.summary()['training']['rest_remaining_s'] == remaining
    seq.command('resume')
    assert seq.engine.stage == 'RESTING'
    assert seq.engine.set_number == 1
    assert seq.engine.summary()['training']['rest_remaining_s'] == pytest.approx(remaining)


def test_sitstand_counts_at_standing_but_group_rest_waits_for_return():
    seq = Sequence('sit_to_stand', target_reps=1)
    seq.frames(knee=90, hip=.65)
    seq.frames(knee=40, hip=.52)
    seq.frames(knee=5, hip=.4)
    assert seq.engine.completed == 1 and seq.engine.stage == 'RECOVERY'
    with pytest.raises(ValueError):
        seq.command('next_set')
    seq.frames(knee=45, hip=.52)
    seq.frames(knee=90, hip=.65)
    assert seq.engine.stage == 'RESTING'
    assert seq.engine.repetitions[0]['lowering_time_s'] is not None
    seq.frames(knee=90, hip=.65, n=30)
    seq.command('next_set')
    seq.frames(knee=90, hip=.65)
    seq.frames(knee=40, hip=.52)
    seq.frames(knee=5, hip=.4)
    assert seq.engine.summary()['plan_completed']
    seq.engine.finish('user_stop')
    result = seq.engine.summary()
    assert result['completed'] == 2 and result['training']['sets'][-1]['status'] == 'COMPLETE'
    assert seq.engine.repetitions[-1]['lowering_time_s'] is None


def test_lost_return_is_not_invented_and_final_count_remains():
    seq = Sequence('sit_to_stand', target_reps=1, target_sets=1)
    seq.frames(knee=90, hip=.65)
    seq.frames(knee=40, hip=.52)
    seq.frames(knee=5, hip=.4)
    seq.frames(valid=False, n=20)
    seq.frames(knee=90, hip=.65)
    assert seq.engine.stage == 'COMPLETE'
    assert seq.engine.completed == 1
    assert seq.engine.repetitions[0]['lowering_time_s'] is None


def test_out_of_order_or_old_control_frames_cannot_change_evidence():
    seq = Sequence()
    seq.frames(0)
    seq.command('pause')
    before = copy.deepcopy(seq.engine.summary())
    seq.engine.process(observation(0, 180))
    seq.engine.process(observation(float('nan'), 180))
    assert seq.engine.summary() == before
    seq.command('resume')
    with pytest.raises(ValueError):
        seq.engine.control('pause', 0)


@pytest.mark.parametrize('field,value', [('target_reps', 0), ('target_reps', True), ('target_sets', 0),
    ('target_sets', 1.5), ('rest_between_sets_s', -1), ('rest_between_sets_s', float('inf')),
    ('rest_between_sets_s', True)])
def test_invalid_plan_does_not_start(field, value):
    plan = default_plan()
    plan.update(submode='training', **{field: value})
    with pytest.raises(ValueError):
        TrainingEngine(plan)


def test_manual_rest_can_be_unset_without_inventing_a_duration():
    seq = Sequence(target_reps=1, rest_between_sets_s=None)
    seq.cycle()
    assert seq.engine.summary()['training']['rest_remaining_s'] is None
    assert seq.engine.summary()['training']['can_next_set']
    seq.command('next_set')
    assert seq.engine.set_number == 2


def test_feedback_null_is_not_zero_and_text_is_not_a_diagnosis():
    value = validate_training_feedback({'pain': None, 'fatigue': 0, 'reason': 'completed', 'notes': '自行填写'})
    assert value == {'pain': None, 'fatigue': 0, 'reason': 'completed', 'notes': '自行填写', 'record_origin': 'self_report'}
    for invalid in (True, -1, 11, '5', float('nan')):
        with pytest.raises(ValueError):
            validate_training_feedback({'pain': invalid})
