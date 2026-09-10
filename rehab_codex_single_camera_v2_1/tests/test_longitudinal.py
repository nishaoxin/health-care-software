"""Snapshot-based history checks; these are not longitudinal clinical outcomes."""
import copy
import math

import pytest

from app.longitudinal import condition_snapshot, compare_conditions, build_longitudinal_history, plot_series
import test_app_controller as controller_fixtures


@pytest.fixture
def saved_session():
    f = controller_fixtures.ControllerTests()
    f.setUp()
    try:
        f._assessment_reference()
        result = f.store.get_session(f.c.last_saved_id)
        result.update(id='first', start_utc='2026-09-01T08:00:00+00:00', end_utc='2026-09-01T08:01:00+00:00')
        yield result
    finally:
        f.tearDown()


def later(session, sid='second', day=2, **changes):
    result = copy.deepcopy(session)
    result.update(id=sid, start_utc=f'2026-09-{day:02d}T08:00:00+00:00',
                  end_utc=f'2026-09-{day:02d}T08:01:00+00:00')
    result.update(changes)
    return result


def test_current_real_controller_snapshot_has_complete_recorded_conditions(saved_session):
    conditions = condition_snapshot(saved_session)
    assert conditions['missing'] == []
    assert compare_conditions(saved_session, later(saved_session))['status'] == 'MATCH'


def test_volatile_names_confirmations_and_reference_ids_do_not_prevent_equal_measurements(saved_session):
    other = later(saved_session, plan_hash='different-frozen-plan', profile_version='different-confirmation')
    other['config_snapshot']['setup_confirmed_at'] = 'later'
    other['config_snapshot']['plan'].update(assessment_reference={'session_id': 'new-assessment'},
        saved_plan_reference={'name': 'Renamed', 'revision': 99}, training_plan_confirmed=True)
    assert compare_conditions(saved_session, other)['status'] == 'MATCH'


@pytest.mark.parametrize('field,value', [('source_ref', 'another-camera'), ('model_manifest_id', 'other-model'),
    ('measurement_contract', 'other-definition'), ('schema_id', 'other-schema'), ('coordinate_space', 'normalised'),
    ('keypoint_order_version', 'changed'), ('rule_version', 'changed'), ('preprocessing_hash', 'changed'),
    ('preprocess_version', 'changed'), ('time_basis', 'wall-time'), ('pose_backend', 'other-backend'),
    ('profile_id', 'other-placement'), ('movement_timing_version', 'other-timing')])
def test_recorded_measurement_changes_are_explicitly_different(saved_session, field, value):
    other = later(saved_session, **{field: value})
    comparison = compare_conditions(saved_session, other)
    assert comparison['status'] == 'DIFFERENT' and field in comparison['differences']


@pytest.mark.parametrize('field', ['source_ref', 'model_manifest_id', 'measurement_contract', 'schema_id', 'profile_id'])
def test_shared_missing_metadata_is_unknown_not_matching(saved_session, field):
    saved_session.pop(field, None)
    saved_session['config_snapshot'].pop(field, None)
    assert compare_conditions(saved_session, later(saved_session))['status'] == 'UNKNOWN'
    assert field in condition_snapshot(saved_session)['missing']


@pytest.mark.parametrize('field,value', [('target_reps', 7), ('target_angle_deg', 60), ('rest_deg', 15),
    ('dwell_s', .25), ('max_gap_s', .8), ('use_of_hands', 'allowed'), ('needs_companion', True)])
def test_arrangement_and_rule_parameters_are_comparison_conditions(saved_session, field, value):
    other = later(saved_session)
    other['config_snapshot']['plan'][field] = value
    assert 'plan.'+field in compare_conditions(saved_session, other)['differences']


def test_new_timing_goal_splits_group_and_missing_legacy_metrics_are_not_derived(saved_session):
    other = later(saved_session)
    other['config_snapshot']['plan']['timing_plan']['outbound_min_s'] = 2
    assert compare_conditions(saved_session, other)['status'] == 'DIFFERENT'
    old = later(saved_session, 'legacy', 3)
    old.pop('movement_timing_version')
    for rep in old['repetitions']:
        rep.pop('movement_timing')
    history = build_longitudinal_history([saved_session, old], 'first')
    assert history['rows'][1]['values']['outbound_s'] is None


def test_calibration_values_matter_but_recording_timestamp_and_tracking_epoch_do_not(saved_session):
    saved_session['config_snapshot']['plan']['joint_baseline'] = {
        'rest_value': 10., 'raw_metric': 'raise_deg', 'recorded_at': 'first', 'provenance': {'preview_epoch': 'first'}}
    other = later(saved_session)
    other['config_snapshot']['plan']['joint_baseline'].update(recorded_at='next', provenance={'preview_epoch': 'next'})
    assert compare_conditions(saved_session, other)['status'] == 'MATCH'
    other['config_snapshot']['plan']['joint_baseline']['rest_value'] = 10.01
    assert 'joint_baseline' in compare_conditions(saved_session, other)['differences']


@pytest.mark.parametrize('field,value', [('participant_id', 'other-person'), ('source_kind', 'REPLAY_FILE'),
    ('usage_context', 'CONTROLLED_DEMO'), ('exercise_id', 'knee_extension'), ('side', 'right'), ('submode', 'training')])
def test_history_scope_never_mixes_people_sources_tasks_or_sides(saved_session, field, value):
    other = later(saved_session, **{field: value})
    result = build_longitudinal_history([other, saved_session], 'first')
    assert [r['session_id'] for r in result['rows']] == ['first']


def test_failed_and_unknown_time_rows_remain_and_break_the_chart(saved_session):
    failed = later(saved_session, 'failed', 2, status='INTERRUPTED', summary={}, metrics=[], repetitions=[])
    latest = later(saved_session, 'latest', 3)
    undated = later(saved_session, 'undated', 4, start_utc=None)
    history = build_longitudinal_history([latest, undated, saved_session, failed], 'latest')
    assert [r['session_id'] for r in history['rows']] == ['first', 'failed', 'latest', 'undated']
    assert history['rows'][1]['values']['range_deg'] is None
    assert history['rows'][3]['data_state'] == 'TIME_UNKNOWN'
    assert [len(segment) for segment in plot_series(history, 'range_deg')] == [1, 1]


def test_different_conditions_never_get_connected_across_an_intervening_row(saved_session):
    changed = later(saved_session, 'changed', 2, model_manifest_id='other')
    third = later(saved_session, 'third', 3)
    history = build_longitudinal_history([saved_session, changed, third], 'first')
    assert [len(segment) for segment in plot_series(history, 'completed')] == [1, 1]
    assert history['rows'][1]['values']['completed'] == 1


def test_timing_medians_have_valid_denominators_and_nonfinite_values_never_plot(saved_session):
    first = saved_session['repetitions'][0]
    second = copy.deepcopy(first)
    second['number'] = 2
    second['movement_timing']['return_s'] = dict(value=None, valid=False, reason='occlusion')
    saved_session['repetitions'].append(second)
    original = copy.deepcopy(saved_session)
    row = build_longitudinal_history([saved_session], 'first')['rows'][0]
    assert row['timing_counts']['return_s'] == {'measured': 1, 'complete_repetitions': 2}
    assert saved_session == original
    saved_session['summary']['completed'] = math.nan
    assert not plot_series(build_longitudinal_history([saved_session], 'first'), 'completed')


def test_removed_anchor_does_not_silently_fall_back_to_another_record(saved_session):
    with pytest.raises(ValueError, match='不存在'):
        build_longitudinal_history([saved_session], 'deleted')
