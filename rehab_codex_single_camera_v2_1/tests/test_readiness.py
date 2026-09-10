import csv
import hashlib

from app.readiness import content_inventory, check_sample_manifest, SAMPLE_COLUMNS


def manifest(tmp_path, rows):
    path = tmp_path/'manifest.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def row(**changes):
    value = dict.fromkeys(SAMPLE_COLUMNS, 'fixture')
    value.update(participant_id='person-a', recording_id='record-a', split='acceptance',
                 exercise_id='shoulder_abduction', side='left', view='frontal',
                 source_kind='REPLAY_FILE', usage_context='TEST', annotation_origin='human',
                 recording_sha256='0'*64)
    value.update(changes)
    return value


def test_inventory_checks_all_text_but_never_labels_missing_images_or_humans_as_passed(tmp_path):
    result = content_inventory(tmp_path)
    assert result['action_count'] == 53 and result['side_entries'] == 106
    assert result['image_slots'] == 318 and result['present_images'] == 0
    assert result['content_structure_errors'] == []
    assert all(r['human_accuracy'] == 'EVIDENCE_NOT_PROVIDED' for r in result['rows'])
    target = tmp_path/'shoulder_abduction/left/start.png'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'not even a real image')
    present = content_inventory(tmp_path)
    assert present['present_images'] == 1
    asset = next(a for r in present['rows'] for a in r['assets'] if a['status'] != 'MISSING')
    assert asset['status'] == 'PRESENT_NOT_CONTENT_REVIEWED'


def test_empty_manifest_is_not_acceptance(tmp_path):
    result = check_sample_manifest(manifest(tmp_path, []))
    assert not result['ready'] and not result['accuracy_validated']


def test_incomplete_csv_row_is_reported_as_missing_inputs(tmp_path):
    path = tmp_path/'short.csv'
    path.write_text(','.join(SAMPLE_COLUMNS)+'\nonly-one-cell\n', encoding='utf-8')
    result = check_sample_manifest(path)
    assert not result['ready'] and result['errors']


def test_human_origin_and_person_recording_splits_are_enforced(tmp_path):
    result = check_sample_manifest(manifest(tmp_path, [row(split='development'), row(recording_id='record-b')]))
    assert not result['ready'] and any('分组' in e for e in result['errors'])
    result = check_sample_manifest(manifest(tmp_path, [row(annotation_origin='prediction')]))
    assert not result['ready']


def test_absent_consent_wrong_view_and_synthetic_source_are_not_ready(tmp_path):
    result = check_sample_manifest(manifest(tmp_path, [row(consent_reference='', source_kind='SYNTHETIC', view='sagittal')]))
    assert not result['ready'] and len(result['errors']) == 3


def test_metadata_only_success_does_not_claim_file_consent_or_accuracy_verification(tmp_path):
    result = check_sample_manifest(manifest(tmp_path, [row()]))
    assert result['ready'] and result['check_level'] == 'metadata_only'
    assert result['verified_file_sets'] == 0 and not result['consent_authenticity_verified'] and not result['accuracy_validated']


def test_explicit_file_hash_check_refuses_missing_or_changed_recording(tmp_path):
    recording = tmp_path/'recording.bin'
    recording.write_bytes(b'synthetic-file-hash-fixture')
    (tmp_path/'labels.csv').write_text('human_label\n', encoding='utf-8')
    (tmp_path/'session.json').write_text('{}', encoding='utf-8')
    path = manifest(tmp_path, [row(recording_path='recording.bin', annotations_path='labels.csv',
                                 session_export_path='session.json', recording_sha256=hashlib.sha256(recording.read_bytes()).hexdigest())])
    result = check_sample_manifest(path, verify_files=True)
    assert result['ready'] and result['verified_file_sets'] == 1 and not result['accuracy_validated']
    recording.write_bytes(b'changed')
    assert not check_sample_manifest(path, verify_files=True)['ready']
