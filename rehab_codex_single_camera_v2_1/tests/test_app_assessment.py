import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from app.assessment import build_body_profile, build_training_reference, session_motion_range
from app.reports import export_body_profile, export_session, render_body_profile, render_report


def session(sid='first', day=1, **changes):
    item = {'id': sid, 'scene_id': 'rehab', 'submode': 'assessment', 'participant_id': 'person-a',
            'exercise_id': 'shoulder_abduction', 'side': 'left', 'status': 'FINISHED',
            'source_kind': 'LIVE_CAMERA', 'usage_context': 'SELF_USE',
            'start_utc': f'2026-09-{day:02d}T08:00:00+00:00', 'end_utc': f'2026-09-{day:02d}T08:01:00+00:00',
            'source_ref': 'camera-one', 'profile_id': 'profile-one', 'profile_version': 'profile-v1',
            'model_manifest_id': 'model-v1', 'schema_id': 'coco17-v1',
            'keypoint_order_version': 'coco17-anatomical-lr-v1', 'coordinate_space': 'raw_image_pixels',
            'rule_version': 'rule-v1', 'preprocess_version': 'filter-v1', 'preprocessing_hash': 'filter-hash',
            'time_basis': 'monotonic_receive', 'actual_capture': {'size': [1280, 720]},
            'config_snapshot': {'view': 'front', 'placement_revision': 1, 'poses_consent': False,
                                'plan': {'max_gap_s': .5}},
            'summary': {'motion_range': {'min_deg': 10, 'max_deg': 80, 'range_deg': 70},
                        'valid_ratio': .8, 'completed': 2, 'partial': 1, 'invalid': 0},
            'repetitions': [], 'metrics': [], 'events': []}
    item.update(changes)
    return item


def get_item(profile, exercise='shoulder_abduction', side='left'):
    return next(i for i in profile['items'] if i['exercise_id'] == exercise and i['side'] == side)


def metric_rows(values, metric='raise_deg'):
    return [{'time_s': i*.1, 'observation_status': 'VALID', 'annotation_origin': 'prediction',
             'metrics': {metric: {'value': value, 'valid': value is not None, 'reason': None}}}
            for i, value in enumerate(values)]


class BodyProfileTests(unittest.TestCase):
    def test_lists_all_twelve_items_and_does_not_invent_missing_values(self):
        profile = build_body_profile([], 'person-a')
        self.assertEqual((profile['total_items'], profile['assessed_count']), (12, 0))
        self.assertEqual(len({(i['exercise_id'], i['side']) for i in profile['items']}), 12)
        for item in profile['items']:
            self.assertEqual(item['status'], 'NOT_ASSESSED')
            for key in ('session_id', 'valid_ratio', 'completed', 'motion_range'):
                self.assertIsNone(item[key])

    def test_person_and_anatomical_sides_are_separate(self):
        left = session()
        right = session('right', side='right')
        other = session('other', day=3, participant_id='person-b')
        profile = build_body_profile([other, right, left], 'person-a')
        self.assertEqual(profile['assessed_count'], 2)
        self.assertEqual(get_item(profile)['session_id'], 'first')
        self.assertEqual(get_item(profile, side='right')['session_id'], 'right')
        self.assertTrue(profile['participant_label'].startswith('anon-'))
        self.assertNotEqual(profile['participant_label'], 'person-a')

    def test_missing_participant_never_groups_unidentified_people(self):
        for participant in (None, ''):
            self.assertEqual(build_body_profile([session(participant_id=participant)], participant)['assessed_count'], 0)

    def test_training_other_scenes_replay_and_test_do_not_enter_live_self_use(self):
        excluded = [session('training', submode='training'), session('activity', scene_id='activity'),
                    session('replay', source_kind='REPLAY_FILE'), session('synthetic', source_kind='SYNTHETIC'),
                    session('demo', usage_context='CONTROLLED_DEMO'), session('test', usage_context='TEST'),
                    session('unknown_source', source_kind=None), session('unknown_mode', submode=None)]
        self.assertEqual(build_body_profile(excluded, 'person-a')['assessed_count'], 0)
        self.assertEqual(build_body_profile(excluded, 'person-a', 'REPLAY_FILE')['assessed_count'], 1)
        self.assertEqual(build_body_profile(excluded, 'person-a', usage_context='TEST')['assessed_count'], 1)

    def test_only_ended_records_are_eligible(self):
        records = [session('running', status='RUNNING'), session('crash', status='INTERRUPTED', end_utc=None),
                   session('bad_end', end_utc='not-a-time'), session('backwards', end_utc='2026-08-01T00:00:00Z')]
        self.assertEqual(build_body_profile(records, 'person-a')['assessed_count'], 0)
        self.assertEqual(build_body_profile([session(status='INTERRUPTED')], 'person-a')['assessed_count'], 1)

    def test_latest_invalid_attempt_cannot_show_an_older_success(self):
        bad = session('latest', day=3, summary={'motion_range': None, 'valid_ratio': 0, 'completed': 0})
        for records in ([bad, session()], [session(), bad]):
            item = get_item(build_body_profile(records, 'person-a'))
            self.assertEqual((item['session_id'], item['status']), ('latest', 'UNAVAILABLE'))
            self.assertIsNone(item['motion_range'])
            self.assertEqual(item['completed'], 0)

    def test_last_ended_time_is_normalized_across_timezones(self):
        older = session('older', end_utc='2026-09-01T11:59:00+04:00', start_utc='2026-09-01T11:50:00+04:00')
        self.assertEqual(get_item(build_body_profile([older, session()], 'person-a'))['session_id'], 'first')

    def test_new_conditions_are_preserved_without_cross_model_or_camera_averages(self):
        newer = session('new', day=2, model_manifest_id='model-v2', source_ref='camera-two', profile_version='profile-v2')
        newer['summary']['motion_range'] = {'min_deg': 30, 'max_deg': 50, 'range_deg': 20}
        profile = build_body_profile([session(), newer], 'person-a')
        item = get_item(profile)
        self.assertEqual(item['motion_range']['range_deg'], 20)
        for key in ('model_manifest_id', 'source_ref', 'profile_version'):
            self.assertEqual(item['conditions'][key], newer[key])
        self.assertIn('不宜直接比较', profile['comparison_note'])

    def test_source_records_and_evidence_are_traceable_and_not_aliased(self):
        source = session()
        source['repetitions'] = [{'number': 2, 'issues': [{'rule_id': 'trunk_tilt', 'evidence_valid': True,
                                                        'start_time_s': 2, 'end_time_s': 3, 'measured_value': 15}]}]
        before = copy.deepcopy(source)
        profile = build_body_profile([source], 'person-a')
        item = get_item(profile)
        self.assertEqual(item['session_id'], source['id'])
        self.assertEqual(item['end_utc'], source['end_utc'])
        self.assertEqual(item['issues'][0]['session_id'], source['id'])
        self.assertEqual(item['issues'][0]['repetition_number'], 2)
        ref = build_training_reference(profile, 'shoulder_abduction', 'left')
        ref['conditions']['actual_size'][0] = 1
        ref['issues'][0]['measured_value'] = 999
        self.assertEqual(item['conditions']['actual_size'], [1280, 720])
        self.assertEqual(source, before)

    def test_missing_counts_and_ratios_do_not_turn_into_zero(self):
        source = session(summary={'motion_range': {'min_deg': 0, 'max_deg': 0, 'range_deg': 0}})
        item = get_item(build_body_profile([source], 'person-a'))
        self.assertEqual(item['status'], 'ASSESSED')
        self.assertEqual(item['motion_range']['range_deg'], 0)
        self.assertIsNone(item['completed'])
        self.assertIsNone(item['valid_ratio'])

    def test_nonfinite_missing_invalid_range_or_metric_mismatch_is_not_assessed(self):
        ranges = [None, {'min_deg': None, 'max_deg': 80, 'range_deg': 80},
                  {'min_deg': 0, 'max_deg': float('nan'), 'range_deg': 50},
                  {'min_deg': 80, 'max_deg': 10, 'range_deg': 70},
                  {'min_deg': 10, 'max_deg': 80, 'range_deg': 0}]
        for value in ranges:
            self.assertIsNone(get_item(build_body_profile([session(summary={'motion_range': value})], 'person-a'))['motion_range'])
        source = session()
        source['summary']['primary_metric'] = 'unrelated_angle'
        self.assertEqual(build_body_profile([source], 'person-a')['assessed_count'], 0)
        source['summary']['primary_metric'] = 'raise_deg'
        source['summary']['valid_ratio'] = 0
        self.assertEqual(build_body_profile([source], 'person-a')['assessed_count'], 0)

    def test_old_reports_derive_robust_range_from_valid_metric_samples(self):
        source = session(summary={'completed': 1, 'valid_ratio': .8}, metrics=metric_rows([10]*3+[40, 170, 40]+[80]*3))
        item = get_item(build_body_profile([source], 'person-a'))
        self.assertEqual(item['motion_range'], {'min_deg': 10, 'max_deg': 80, 'range_deg': 70})
        self.assertEqual(item['motion_range_source'], 'metrics')
        self.assertNotIn('motion_range', source['summary'])

    def test_signed_hip_range_is_valid_in_summary_without_inventing_adduction_reps(self):
        source = session(exercise_id='hip_abduction', summary={
            'primary_metric': 'hip_abduction_deg', 'valid_sample_count': 12, 'valid_ratio': .8,
            'motion_range': {'min_deg': -12, 'max_deg': 20, 'range_deg': 32}, 'completed': 0})
        item = get_item(build_body_profile([source], 'person-a'), 'hip_abduction')
        self.assertEqual(item['status'], 'ASSESSED')
        self.assertEqual(item['motion_range'], {'min_deg': -12, 'max_deg': 20, 'range_deg': 32})
        self.assertEqual(item['completed'], 0)

    def test_signed_hip_legacy_range_uses_valid_samples_with_negative_stance(self):
        source = session(exercise_id='hip_abduction', summary={'valid_ratio': .8},
                         metrics=metric_rows([-8]*3+[12]*3, 'hip_abduction_deg'))
        item = get_item(build_body_profile([source], 'person-a'), 'hip_abduction')
        self.assertEqual(item['status'], 'ASSESSED')
        self.assertEqual(item['motion_range_source'], 'metrics')
        self.assertEqual(item['motion_range'], {'min_deg': -8, 'max_deg': 12, 'range_deg': 20})
        self.assertIsNone(item['completed'])

    def test_signed_range_bounds_and_consistency_do_not_relax_other_metrics(self):
        for exercise_id, minimum, maximum, span in (
                ('hip_abduction', -181, 10, 191), ('hip_abduction', -10, 181, 191),
                ('hip_abduction', -10, 10, 5), ('shoulder_abduction', -1, 80, 81),
                ('knee_extension', -1, 80, 81), ('elbow_flexion', -1, 80, 81)):
            source = session(exercise_id=exercise_id, summary={
                'motion_range': {'min_deg': minimum, 'max_deg': maximum, 'range_deg': span}})
            self.assertIsNone(session_motion_range(source)[0])
        for exercise_id, metric in (('shoulder_abduction', 'raise_deg'), ('knee_extension', 'knee_flexion_deg'),
                                    ('elbow_flexion', 'elbow_flexion_deg')):
            self.assertIsNone(session_motion_range(session(exercise_id=exercise_id, summary={}, metrics=metric_rows([-3]*3, metric)))[0])

    def test_interrupted_session_with_evidence_stays_assessed_and_preserves_end_reason(self):
        source = session('new', day=2, status='INTERRUPTED', stop_reason='source_changed')
        profile = build_body_profile([source, session()], 'person-a')
        item = get_item(profile)
        self.assertEqual(item['status'], 'ASSESSED')
        self.assertEqual((item['session_status'], item['stop_reason']), ('INTERRUPTED', 'source_changed'))
        reference = build_training_reference(profile, 'shoulder_abduction', 'left')
        self.assertEqual(reference['session_status'], 'INTERRUPTED')
        self.assertEqual(reference['session_id'], 'new')

    def test_legacy_requires_three_valid_observations_not_rep_counts_or_last_value(self):
        for values in ([], [10], [10, 80], [10, None, 80], [float('inf')]*3):
            source = session(summary={'completed': 10, 'metrics': {'raise_deg': {'value': 90, 'valid': True}}}, metrics=metric_rows(values))
            item = get_item(build_body_profile([source], 'person-a'))
            self.assertEqual(item['status'], 'NOT_ASSESSED')
            self.assertIsNone(item['motion_range'])

    def test_legacy_invalid_flags_human_labels_gaps_and_unknown_observations_are_excluded(self):
        for mutate in ('invalid', 'unknown', 'human', 'gap'):
            source = session(summary={}, metrics=metric_rows([10, 20, 80]))
            for i, row in enumerate(source['metrics']):
                if mutate == 'invalid':
                    row['metrics']['raise_deg']['valid'] = False
                elif mutate == 'unknown':
                    row['observation_status'] = 'UNKNOWN'
                elif mutate == 'human':
                    row['annotation_origin'] = 'human'
                else:
                    row['time_s'] = i*10
            self.assertIsNone(session_motion_range(source)[0])

    def test_explicit_new_missing_range_never_falls_back_to_legacy_metrics(self):
        source = session(summary={'motion_range': None}, metrics=metric_rows([10]*3+[80]*3))
        self.assertIsNone(session_motion_range(source)[0])

    def test_summary_validity_and_sample_count_are_respected(self):
        for extra in ({'motion_range_valid': False}, {'valid_sample_count': 2},
                      {'valid_sample_count': None}, {'valid_sample_count': float('nan')}):
            source = session()
            source['summary'].update(extra)
            self.assertIsNone(session_motion_range(source)[0])
        source = session()
        source['summary']['valid_sample_count'] = 3
        self.assertIsNotNone(session_motion_range(source)[0])

    def test_snapshot_plan_fallback_supports_older_metadata_without_inventing_mode(self):
        source = session()
        for key in ('participant_id', 'exercise_id', 'side', 'submode'):
            source['config_snapshot']['plan'][key] = source.pop(key)
        self.assertEqual(build_body_profile([source], 'person-a')['assessed_count'], 1)
        source['submode'] = None
        self.assertEqual(build_body_profile([source], 'person-a')['assessed_count'], 0)

    def test_training_reference_keeps_unavailable_status_and_never_sets_goals(self):
        profile = build_body_profile([session(summary={'motion_range': None})], 'person-a')
        ref = build_training_reference(profile, 'shoulder_abduction', 'left')
        self.assertEqual(ref['status'], 'UNAVAILABLE')
        self.assertIsNone(ref['motion_range'])
        self.assertEqual(ref['session_id'], 'first')
        self.assertNotIn('target_angle_deg', ref)
        with self.assertRaises(ValueError):
            build_training_reference(profile, 'shoulder_abduction', 'both')


class AssessmentReportTests(unittest.TestCase):
    def test_interrupted_assessment_status_and_reason_are_visible_in_reports(self):
        source = session(status='INTERRUPTED', stop_reason='source_changed')
        profile = build_body_profile([source], 'person-a')
        self.assertIn('中断结束', render_body_profile(profile, compact=True))
        train = session('train', submode='training', assessment_reference=build_training_reference(profile, 'shoulder_abduction', 'left'))
        for rendered in (render_report(source), render_body_profile(profile), render_report(train)):
            self.assertIn('已中断', rendered)
            self.assertIn('source_changed', rendered)

    def test_compact_body_has_twelve_rows_five_columns_and_no_repeated_evidence(self):
        profile = build_body_profile([session()], 'person-a')
        rendered = render_body_profile(profile, compact=True)
        self.assertEqual(rendered.count('<tr>'), 13)
        self.assertEqual(rendered.count('<td>'), 60)
        self.assertIn('2026-09-01 08:01', rendered)
        self.assertIn('最近评估（UTC）', rendered)
        self.assertIn('10.0–80.0°', rendered)
        for verbose in ('model-v1', 'profile-v1', '本次缺少可追溯', '尚无当前参与者', '测量条件'):
            self.assertNotIn(verbose, rendered)
        self.assertIn('model-v1', render_body_profile(profile))

    def test_compact_body_time_and_dynamic_values_are_escaped(self):
        attack = '<script>alert(1)</script>'
        profile = build_body_profile([session(end_utc='2026-09-01T16:01:00+08:00')], attack)
        profile['items'][0].update(exercise_label=attack, end_utc=attack)
        rendered = render_body_profile(profile, compact=True)
        self.assertNotIn(attack, rendered)
        self.assertIn('&lt;script&gt;', rendered)
        profile = build_body_profile([session(end_utc='2026-09-01T16:01:00+08:00')], 'person-a')
        self.assertIn('2026-09-01 08:01', render_body_profile(profile, compact=True))

    def test_body_html_includes_all_sides_provenance_conditions_and_missing_labels(self):
        profile = build_body_profile([session()], 'person-a')
        rendered = render_body_profile(profile)
        for expected in ('已评估', '未评估', '左侧', '右侧', 'first', 'model-v1', 'profile-v1', '80.0', '二维投影', '不宜直接比较'):
            self.assertIn(expected, rendered)
        self.assertIn('person-a', rendered)

    def test_every_dynamic_html_field_is_escaped(self):
        attack = '<img src=x onerror=alert(1)>'
        source = session(attack, stop_reason=attack, model_manifest_id=attack)
        source['summary']['primary_metric_label'] = attack
        source['summary']['completed'] = attack
        source['repetitions'] = [{'number': attack, 'completion_status': attack, 'target_status': attack,
                                  'observation_status': attack, 'issues': [{'rule_id': attack}]}]
        profile = build_body_profile([source], 'person-a')
        for rendered in (render_body_profile(profile), render_report(source)):
            self.assertNotIn(attack, rendered)
            self.assertIn('&lt;img', rendered)

    def test_training_report_shows_original_assessment_and_mode_and_person(self):
        profile = build_body_profile([session()], 'person-a')
        train = session('train', submode='training', assessment_reference=build_training_reference(profile, 'shoulder_abduction', 'left'))
        rendered = render_report(train)
        for expected in ('训练', '参与者', 'person-a', '评估参考', 'first', '2026-09-01', 'profile-v1'):
            self.assertIn(expected, rendered)
        del train['assessment_reference']
        self.assertIn('未记录评估参考', render_report(train))

    def test_old_report_without_new_fields_still_renders(self):
        source = session(summary={'completed': 1})
        source.pop('submode')
        source['repetitions'] = [{'number': 1, 'completion_status': 'COMPLETE', 'target_status': 'NOT_SET',
                                  'observation_status': 'VALID', 'max_raise_projection_deg': 73}]
        rendered = render_report(source)
        self.assertIn('73.0', rendered)
        self.assertIn('模式未记录', rendered)
        self.assertIn('未评估', rendered)

    def test_six_actions_render_their_metric_labels_and_generic_csv_fields(self):
        from app.assessment import EXERCISE_IDS
        from app.exercises import exercise_spec
        for exercise_id in EXERCISE_IDS:
            source = session(exercise_id=exercise_id)
            source['repetitions'] = [{'number': 1, 'completion_status': 'COMPLETE', 'target_status': 'NOT_SET',
                                      'observation_status': 'VALID', 'peak_angle_deg': 80, 'min_angle_deg': 10,
                                      'range_deg': 70, 'max_raise_projection_deg': 80,
                                      'min_knee_flexion_projection_deg': 10}]
            self.assertIn(exercise_spec(exercise_id)['metric_label'], render_report(source))
            with tempfile.TemporaryDirectory() as temp:
                export_session(source, temp)
                with (Path(temp)/'repetitions.csv').open(encoding='utf-8-sig', newline='') as stream:
                    row = next(csv.DictReader(stream))
                self.assertEqual((row['peak_angle_deg'], row['min_angle_deg'], row['range_deg']), ('80', '10', '70'))
                self.assertIn('max_raise_projection_deg', row)
                self.assertIn('min_knee_flexion_projection_deg', row)

    def test_export_removes_private_identifiers_even_inside_training_reference(self):
        source = session(participant_id='张某-private-person', device_ref={'path': r'C:\private-device-path', 'name': 'private-device-name'})
        source['config_snapshot']['plan']['participant_id'] = source['participant_id']
        source['config_snapshot']['operator'] = 'private-operator'
        profile = build_body_profile([source], source['participant_id'])
        source['assessment_reference'] = build_training_reference(profile, 'shoulder_abduction', 'left')
        source['assessment_reference']['conditions']['device_ref'] = source['device_ref']
        source['assessment_reference']['participant_name'] = 'private-participant-name'
        before = copy.deepcopy(source)
        with tempfile.TemporaryDirectory() as temp:
            export_session(source, temp)
            combined = ''.join(path.read_text(encoding='utf-8-sig') for path in Path(temp).iterdir())
            for secret in ('张某-private-person', 'private-device-path', 'private-device-name', 'private-operator', 'private-participant-name'):
                self.assertNotIn(secret, combined)
            metadata = json.loads((Path(temp)/'session.json').read_text(encoding='utf-8'))
            self.assertTrue(metadata['participant_id'].startswith('anon-'))
            self.assertEqual(metadata['assessment_reference']['session_id'], source['id'])
        self.assertEqual(source, before)

    def test_body_export_returns_absolute_paths_anonymises_and_preserves_trace(self):
        profile = build_body_profile([session()], 'person-a')
        before = copy.deepcopy(profile)
        with tempfile.TemporaryDirectory() as temp:
            paths = export_body_profile(profile, Path(temp)/'profile')
            self.assertEqual(set(paths), {'html', 'json'})
            self.assertTrue(all(Path(path).is_absolute() and Path(path).is_file() for path in paths.values()))
            exported = json.loads(Path(paths['json']).read_text(encoding='utf-8'))
            self.assertEqual(exported['participant_id'], profile['participant_label'])
            self.assertEqual(get_item(exported)['session_id'], 'first')
            for path in paths.values():
                self.assertNotIn('person-a', Path(path).read_text(encoding='utf-8'))
            with self.assertRaises(ValueError):
                export_body_profile(profile, Path(temp)/'profile')
        self.assertEqual(profile, before)

    def test_training_plan_reference_fallback_and_mismatched_person_are_explicit(self):
        profile = build_body_profile([session()], 'person-a')
        train = session('train', submode='training')
        train['config_snapshot']['plan']['assessment_reference'] = build_training_reference(profile, 'shoulder_abduction', 'left')
        self.assertIn('first', render_report(train))
        train['participant_id'] = 'person-b'
        self.assertIn('引用不可用于当前训练', render_report(train))

    def test_null_numeric_csv_fields_stay_empty_and_formula_text_is_quoted(self):
        source = session()
        source['repetitions'] = [{'number': '=1+1', 'peak_angle_deg': None, 'range_deg': float('nan')}]
        with tempfile.TemporaryDirectory() as temp:
            export_session(source, temp)
            with (Path(temp)/'repetitions.csv').open(encoding='utf-8-sig', newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row['number'], "'=1+1")
            self.assertEqual(row['peak_angle_deg'], '')
            self.assertEqual(row['range_deg'], '')

    def test_unknown_activity_labels_and_participant_ids_are_html_escaped(self):
        attack = '<script>alert(1)</script>'
        source = session(scene_id='activity', participant_id=attack, summary={'totals': {attack: 1}})
        self.assertNotIn(attack, render_report(source))
        profile = build_body_profile([], attack)
        self.assertNotIn(attack, render_body_profile(profile))
        self.assertIn('&lt;script&gt;', render_body_profile(profile))


if __name__ == '__main__':
    unittest.main()
