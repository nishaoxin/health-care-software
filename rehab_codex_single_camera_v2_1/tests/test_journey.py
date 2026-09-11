from app.journey import current_step, preparation_steps
from app.settings import default_plan
from app.exercises import EXERCISE_IDS, exercise_spec
import pytest


@pytest.mark.parametrize('eid', EXERCISE_IDS)
def test_each_action_has_a_complete_specific_journey(eid):
    steps = preparation_steps(default_plan(eid), dual=True)
    keys = [s[0] for s in steps]
    assert keys[:2] == ['camera', 'framing']
    assert keys[-4:] == ['confirm', 'start', 'active', 'result']
    assert len(keys) == len(set(keys))
    assert all(all(isinstance(x, str) and x for x in step) for step in steps)
    spec = exercise_spec(eid)
    assert ('direction' in keys) == spec['directional_calibration']
    if eid != 'sit_to_stand':
        assert ('rest' in keys) == spec['baseline_required']


def test_neck_sequence_requires_recorded_baseline_direction_and_explicit_confirmation():
    p = default_plan('neck_flexion')
    assert current_step(p, 'UNSELECTED').key == 'camera'
    assert current_step(p, 'PREVIEW').key == 'framing'
    assert current_step(p, 'PREVIEW', framed=True).key == 'rest'
    p['joint_baseline'] = {'rest_value': 0.}
    assert current_step(p, 'PREVIEW', framed=True).key == 'direction'
    p['joint_baseline']['direction_sign'] = -1
    assert current_step(p, 'PREVIEW', framed=True).key == 'confirm'
    assert current_step(p, 'PREVIEW', framed=True, confirmed=True).key == 'start'
    assert current_step(p, 'ONLINE').key == 'active'
    assert current_step(p, 'SAVE_FAILED', saved=True).key == 'save_failed'
    assert current_step(p, 'UNSELECTED', saved=True).key == 'result'


def test_sit_stand_and_shoulder_have_different_preparation():
    p = default_plan('sit_to_stand')
    assert current_step(p, 'PREVIEW', framed=True).key == 'seated'
    p['calibration'] = {'seated_knee': 90., 'seated_hip_y': .7}
    assert current_step(p, 'PREVIEW', framed=True).key == 'standing'
    p['calibration'].update(standing_knee=5., standing_hip_y=.5)
    assert current_step(p, 'PREVIEW', framed=True).key == 'confirm'
    p = default_plan('shoulder_adduction')
    assert '侧抬臂' in current_step(p, 'PREVIEW', framed=True).action
    p['joint_baseline'] = {'rest_value': 55.}
    assert current_step(p, 'PREVIEW', framed=True).key == 'confirm'


def test_training_plan_cannot_be_skipped_by_camera_confirmation():
    p = default_plan('shoulder_abduction')
    p['submode'] = 'training'
    assert current_step(p, 'PREVIEW', confirmed=True).key == 'reference'
    p['assessment_reference'] = {'status': 'ASSESSED'}
    assert current_step(p, 'PREVIEW', confirmed=True).key == 'plan'
    p['training_plan_confirmed'] = True
    assert current_step(p, 'PREVIEW', confirmed=True).key == 'start'
