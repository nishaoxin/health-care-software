"""Reusable manual plans retain provenance without reusing capture consent."""
import copy
import json
import sqlite3

import pytest

from app.assessment import build_body_profile
from app.exercises import exercise_spec
from app.settings import default_plan
from app.storage import Storage
from app.training_plans import (item_from_plan, new_training_plan, validate_training_plan,
                                prepare_training_plan, validate_saved_binding)


SCOPE = dict(participant_id='plan-person', source_kind='SYNTHETIC', usage_context='TEST')


def item(exercise='shoulder_abduction', side='left', **settings):
    plan = default_plan(exercise)
    plan.update(side=side, **settings)
    return item_from_plan(plan)


def saved_record(**changes):
    record = new_training_plan(SCOPE, '晚间练习', [item(), item('knee_extension', 'right')])
    record.update(revision=1, **changes)
    return record


def assessment(**changes):
    spec = exercise_spec('shoulder_abduction')
    session = dict(SCOPE, id='assessment-1', scene_id='rehab', submode='assessment',
                   exercise_id='shoulder_abduction', side='left', status='FINISHED',
                   start_utc='2026-09-10T08:00:00+00:00', end_utc='2026-09-10T08:01:00+00:00',
                   measurement_contract=spec['measurement_contract'],
                   summary=dict(primary_metric=spec['metric'], valid_ratio=.9, valid_sample_count=12,
                                motion_range=dict(min_deg=5., max_deg=65., range_deg=60.)))
    session.update(changes)
    return session


def profile(sessions=None):
    return build_body_profile([assessment()] if sessions is None else sessions, **SCOPE)


def test_only_manual_settings_are_persistent_and_nested_values_are_copied():
    current = default_plan()
    current.update(target_reps=7, training_plan_confirmed=True, calibration={'old': 1},
                   joint_baseline={'rest_value': 22}, assessment_reference={'session_id': 'old'},
                   saved_plan_reference={'id': 'old'}, participant_confirmed=True)
    entry = item_from_plan(current)
    record = new_training_plan(SCOPE, ' 晚间练习 ', [entry])
    text = json.dumps(record)
    for key in ('calibration', 'joint_baseline', 'assessment_reference', 'saved_plan_reference',
                'training_plan_confirmed', 'participant_confirmed'):
        assert key not in text
    current['target_reps'] = 8
    entry['settings']['target_reps'] = 9
    assert record['items'][0]['settings']['target_reps'] == 7
    assert record['name'] == '晚间练习' and record['revision'] == 0


@pytest.mark.parametrize('field,value', [
    ('target_reps', 0), ('target_reps', True), ('target_reps', 1000),
    ('target_sets', 0), ('target_sets', 21), ('target_sets', 1.5),
    ('rest_between_sets_s', -1), ('rest_between_sets_s', float('nan')),
    ('target_angle_deg', float('inf')), ('target_angle_deg', True), ('target_angle_deg', 181),
    ('allowed_trunk_tilt_deg', 91), ('lowering_tempo_min_s', -1),
    ('sound_enabled', 1), ('needs_companion', 'yes'), ('use_of_hands', 'guess'),
])
def test_invalid_manual_settings_are_rejected(field, value):
    with pytest.raises(ValueError):
        item(**{field: value})


def test_bad_range_scope_duplicate_items_and_stale_contract_are_rejected():
    with pytest.raises(ValueError, match='节奏'):
        item('sit_to_stand', lowering_tempo_min_s=3, lowering_tempo_max_s=2)
    for scope in ({}, dict(SCOPE, participant_id=''), dict(SCOPE, source_kind='OTHER')):
        with pytest.raises(ValueError):
            new_training_plan(scope, '计划', [item()])
    for items in ([], [item(), item()]):
        with pytest.raises(ValueError):
            new_training_plan(SCOPE, '计划', items)
    bad = saved_record()
    bad['items'][0]['measurement_contract'] = 'older-definition'
    with pytest.raises(ValueError, match='测量定义'):
        validate_training_plan(bad)


@pytest.mark.parametrize('settings', [None, [], {}, {'target_reps': 8}])
def test_incomplete_stored_arrangement_is_not_filled_with_invented_defaults(settings):
    value = saved_record()
    value['items'][0]['settings'] = settings
    with pytest.raises(ValueError, match='不完整'):
        validate_training_plan(value)


def test_prepare_reloads_current_assessment_but_clears_confirmations_and_baselines():
    record = saved_record()
    plan = prepare_training_plan(record, 'shoulder_abduction:left', profile())
    assert plan['assessment_reference']['session_id'] == 'assessment-1'
    assert plan['training_plan_confirmed'] is False
    assert plan['joint_baseline'] == plan['calibration'] == {}
    assert plan['target_angle_deg'] is None  # Never derived from the 65 degree assessment.
    assert plan['saved_plan_reference']['revision'] == 1
    plan['target_reps'] = 11
    assert record['items'][0]['settings']['target_reps'] == 5


def test_latest_failed_assessment_never_falls_back_to_previous_success():
    failed = assessment(id='assessment-2', end_utc='2026-09-10T09:01:00+00:00',
                        summary={'valid_ratio': 0, 'motion_range': None})
    with pytest.raises(ValueError, match='评估'):
        prepare_training_plan(saved_record(), 'shoulder_abduction:left', profile([assessment(), failed]))


@pytest.mark.parametrize('change', [dict(status='ARCHIVED'), dict(participant_id='other'),
                                  dict(source_kind='LIVE_CAMERA'), dict(usage_context='SELF_USE')])
def test_prepare_rejects_archived_or_cross_scope_plans(change):
    with pytest.raises(ValueError):
        prepare_training_plan(saved_record(**change), 'shoulder_abduction:left', profile())


def test_preparing_changed_measurement_definition_requires_new_assessment():
    with pytest.raises(ValueError, match='测量定义'):
        prepare_training_plan(saved_record(), 'shoulder_abduction:left',
                              profile([assessment(measurement_contract='older-definition')]))


def test_binding_is_rebuilt_and_manual_session_overrides_remain_explicit():
    record = saved_record()
    plan = prepare_training_plan(record, 'shoulder_abduction:left', profile())
    supplied = copy.deepcopy(plan['saved_plan_reference'])
    supplied['name'] = 'forged'
    supplied['item']['settings']['target_reps'] = 999
    plan['target_reps'] = 3
    rebuilt = validate_saved_binding(record, supplied, plan, SCOPE)
    assert rebuilt['name'] == '晚间练习'
    assert rebuilt['item']['settings']['target_reps'] == 5
    assert rebuilt['session_overrides'] == {'target_reps': {'saved': 5, 'used': 3}}
    for newer in (dict(record, revision=2), dict(record, status='ARCHIVED'), None):
        with pytest.raises(ValueError):
            validate_saved_binding(newer, supplied, plan, SCOPE)
    with pytest.raises(ValueError):
        validate_saved_binding(record, supplied, dict(plan, side='right'), SCOPE)


def test_store_reopen_revisions_archive_scope_and_session_immutability(tmp_path):
    path = tmp_path/'plans.sqlite3'
    store = Storage(path)
    try:
        record = store.save_training_plan(new_training_plan(SCOPE, '计划', [item()]), expected_revision=0)
        assert record['revision'] == 1 and len(store.list_training_plans(SCOPE)) == 1
        assert not store.list_training_plans(dict(SCOPE, participant_id='other'))
        assert not store.list_training_plans(dict(SCOPE, source_kind='LIVE_CAMERA'))
        plan = prepare_training_plan(record, 'shoulder_abduction:left', profile())
        snapshot = dict(assessment(), id='training-1', submode='training',
                        saved_plan_reference=plan['saved_plan_reference'])
        store.save_session(snapshot)
        updated = store.save_training_plan(dict(record, name='已修改'), expected_revision=1)
        assert updated['revision'] == 2
        with pytest.raises(ValueError, match='已更新'):
            store.save_training_plan(record, expected_revision=1)
        with pytest.raises(ValueError, match='用户'):
            store.save_training_plan(dict(updated, participant_id='other'), expected_revision=2)
        archived = store.set_training_plan_archived(record['id'], SCOPE, True, expected_revision=2)
        assert archived['revision'] == 3 and not store.list_training_plans(SCOPE)
        assert len(store.list_training_plans(SCOPE, include_archived=True)) == 1
        assert store.get_session('training-1') == snapshot
    finally:
        store.close()
    store = Storage(path)
    try:
        assert store.get_training_plan(record['id']) == archived
        restored = store.set_training_plan_archived(record['id'], SCOPE, False, expected_revision=3)
        assert restored['revision'] == 4 and restored['status'] == 'ACTIVE'
        assert store.get_session('training-1') == snapshot
    finally:
        store.close()


def test_v3_migration_backs_up_and_readonly_legacy_returns_empty_plans(tmp_path):
    path = tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT)')
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('old', None, 'rehab', '{"id":"old"}'))
        db.execute('PRAGMA user_version=3')
    readonly = Storage(path, readonly=True)
    try:
        assert readonly.list_training_plans(SCOPE) == []
        assert readonly.get_training_plan('missing') is None
        with pytest.raises(Exception):
            readonly.save_training_plan(new_training_plan(SCOPE, '计划', [item()]), expected_revision=0)
    finally:
        readonly.close()
    assert not list(tmp_path.glob('*.bak'))
    store = Storage(path)
    try:
        assert store.get_session('old') == {'id': 'old'}
        assert store._call(lambda db: db.execute('PRAGMA user_version').fetchone()[0]) == 4
        backup = next(tmp_path.glob('legacy.sqlite3.before-v4-*.bak'))
        with sqlite3.connect(backup) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == 3
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='training_plans'").fetchone()
    finally:
        store.close()
