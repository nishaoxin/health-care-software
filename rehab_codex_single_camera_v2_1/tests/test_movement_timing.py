"""Known source-clock trajectories; these are measurement-logic checks only."""
import math

import pytest

from app.movement_timing import MovementTiming, default_timing_plan, validate_timing_plan


def trajectory(direction=1, target=60., goals=None):
    timer = MovementTiming(direction=direction, max_gap_s=.5, target=target,
                           goals=goals or default_timing_plan())
    samples = [(0., 0.), (.1, 0.), (.2, 0.), (.3, 20.), (.4, 40.), (.5, 60.),
               (.6, 80.), (.7, 80.), (1., 80.), (1.3, 80.), (1.5, 80.),
               (1.6, 60.), (1.7, 40.), (1.8, 20.), (1.9, 0.), (2., 0.), (2.1, 0.)]
    for t, angle in samples:
        timer.add(t, direction*angle)
    return timer


def test_joint_phase_durations_use_observed_timestamps_and_plateau_band():
    result = trajectory().snapshot('COMPLETE', cycle_complete=True)
    assert result['version'] == 'observed-timing-1'
    assert result['outbound_s']['value'] == pytest.approx(.6)
    assert result['endpoint_dwell_s']['value'] == pytest.approx(.9)
    assert result['return_s']['value'] == pytest.approx(.6)
    assert result['target_hold_s']['value'] == pytest.approx(1.1)
    assert sum(result[k]['value'] for k in ('outbound_s', 'endpoint_dwell_s', 'return_s')) == pytest.approx(2.1)
    assert result['goals']['hold'] == 'NOT_SET'


def test_decreasing_metric_has_the_same_timing_and_target_direction():
    a = trajectory().snapshot('COMPLETE', cycle_complete=True)
    b = trajectory(direction=-1, target=-60.).snapshot('COMPLETE', cycle_complete=True)
    for key in ('outbound_s', 'endpoint_dwell_s', 'return_s', 'target_hold_s'):
        assert b[key] == a[key]


def test_hold_goal_is_continuous_not_sum_of_separate_visits():
    timer = MovementTiming(direction=1, max_gap_s=.5, target=60.,
                           goals=dict(default_timing_plan(), hold_min_s=.5))
    for t, angle in [(0, 70), (.2, 70), (.3, 40), (.4, 70), (.6, 70), (.7, 0)]:
        timer.add(t, angle)
    result = timer.snapshot('COMPLETE', cycle_complete=True)
    assert result['target_hold_s']['value'] == pytest.approx(.2)
    assert result['goals']['hold'] == 'NOT_MET'


def test_gap_resets_live_hold_and_never_fills_missing_duration():
    timer = MovementTiming(direction=1, max_gap_s=.5, target=60.,
                           goals=dict(default_timing_plan(), hold_min_s=.5))
    timer.add(0, 70)
    timer.add(.2, 70)
    timer.break_continuity(.3, 'occlusion')
    assert timer.live()['hold_elapsed_s'] is None
    timer.add(.4, 70)
    assert timer.live()['hold_elapsed_s'] == 0
    timer.add(.6, 70)
    result = timer.snapshot('COMPLETE', cycle_complete=True)
    assert result['target_hold_s']['value'] == pytest.approx(.2)
    assert result['goals']['hold'] == 'UNASSESSABLE'
    assert result['outbound_s']['value'] is None and result['return_s']['value'] is None
    timer.add(.9, 70)
    assert timer.snapshot('COMPLETE', cycle_complete=True)['goals']['hold'] == 'MET'


def test_implicit_long_gap_also_resets_hold_and_stale_samples_add_nothing():
    timer = MovementTiming(direction=1, max_gap_s=.5, target=60., goals=default_timing_plan())
    timer.add(0, 70)
    timer.add(.2, 70)
    timer.add(2., 70)
    timer.add(2., 99)
    timer.add(1., 99)
    assert timer.live()['hold_elapsed_s'] == 0
    timer.add(2.2, 70)
    assert timer.snapshot('COMPLETE', cycle_complete=True)['target_hold_s']['value'] == pytest.approx(.2)


def test_sitstand_rise_remains_valid_when_return_is_missing_or_occluded():
    timer = MovementTiming(direction=-1, max_gap_s=.5, target=None,
                           goals=default_timing_plan(), sit_to_stand=True)
    for t, knee in [(0, 90), (.2, 60), (.4, 30), (.6, 5)]:
        timer.add(t, knee, at_standing=knee <= 10)
    timer.mark_standing(.6)
    first = timer.snapshot('COMPLETE')
    assert first['outbound_s']['value'] == pytest.approx(.6)
    assert first['return_s']['value'] is None
    timer.add(.8, 5, at_standing=True)
    timer.break_continuity(.9, 'occlusion')
    timer.add(1., 30, at_standing=False)
    timer.mark_return(1.)
    timer.add(1.2, 90, at_standing=False)
    final = timer.snapshot('COMPLETE', cycle_complete=True)
    assert final['outbound_s']['value'] == pytest.approx(.6)
    assert final['endpoint_dwell_s']['value'] is None
    assert final['return_s']['value'] == pytest.approx(.2)


def test_sitstand_standing_dwell_and_return_are_independent_of_rise_endpoint():
    timer = MovementTiming(direction=-1, max_gap_s=.5, target=None,
                           goals=dict(default_timing_plan(), hold_min_s=.5), sit_to_stand=True)
    for t, knee in [(0, 90), (.3, 40), (.6, 5), (.9, 5), (1.2, 5), (1.3, 30), (1.6, 90)]:
        timer.add(t, knee, at_standing=knee <= 10)
        if t == .6:
            timer.mark_standing(t)
        if t == 1.3:
            timer.mark_return(t)
    result = timer.snapshot('COMPLETE', cycle_complete=True)
    assert result['outbound_s']['value'] == pytest.approx(.6)
    assert result['endpoint_dwell_s']['value'] == pytest.approx(.7)
    assert result['return_s']['value'] == pytest.approx(.3)
    assert result['target_hold_s']['value'] == pytest.approx(.6)
    assert result['goals']['hold'] == 'MET'


def test_optional_tempo_targets_use_valid_segments_only_and_do_not_change_counts():
    goals = dict(default_timing_plan(), outbound_min_s=.8, return_max_s=.8, hold_min_s=1)
    result = trajectory(goals=goals).snapshot('COMPLETE', cycle_complete=True)
    assert result['goals'] == {'outbound': 'NOT_MET', 'return': 'MET', 'hold': 'MET'}
    interrupted = trajectory(goals=goals).snapshot('INTERRUPTED', reason='user_pause')
    assert interrupted['outbound_s']['value'] is None
    assert interrupted['goals']['outbound'] == 'UNASSESSABLE'
    assert interrupted['goals']['hold'] == 'MET'  # A separately observed continuous interval remains evidence.


@pytest.mark.parametrize('field,value', [('outbound_min_s', -1), ('return_max_s', math.inf),
                                      ('hold_min_s', math.nan), ('hold_min_s', True), ('hold_min_s', 301)])
def test_invalid_or_nonfinite_timing_arrangements_are_rejected(field, value):
    with pytest.raises(ValueError):
        validate_timing_plan(dict(default_timing_plan(), **{field: value}), 'shoulder_abduction', 60.)


def test_hold_requires_an_explicit_angle_anchor_except_calibrated_sitstand():
    hold = dict(default_timing_plan(), hold_min_s=1)
    with pytest.raises(ValueError, match='角度'):
        validate_timing_plan(hold, 'shoulder_abduction', None)
    assert validate_timing_plan(hold, 'sit_to_stand', None)['hold_min_s'] == 1
    with pytest.raises(ValueError, match='最短'):
        validate_timing_plan(dict(default_timing_plan(), outbound_min_s=3, outbound_max_s=2), 'shoulder_abduction', None)
