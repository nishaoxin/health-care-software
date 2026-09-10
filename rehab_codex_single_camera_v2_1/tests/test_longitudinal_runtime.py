import csv
import json

import pytest

from app.domain import digest
from app.longitudinal import build_longitudinal_history
from app.reports import export_longitudinal_history
from app.runtime import Runtime
from app.storage import Storage
from test_longitudinal import saved_session, later
from test_training_runtime import response


def test_export_retains_values_gaps_and_condition_details_without_person_or_file_identifiers(saved_session, tmp_path):
    saved_session['participant_id'] = 'private-person-id'
    saved_session['source_ref'] = 'C:/private-person-id/private-recording.mp4'
    changed = later(saved_session, 'changed', 2, model_manifest_id='different')
    history = build_longitudinal_history([saved_session, changed], 'first')
    out = tmp_path/'report'
    export_longitudinal_history(history, out, 'return_s')
    text = (out/'history.json').read_text(encoding='utf-8')
    html = (out/'history.html').read_text(encoding='utf-8')
    assert 'private-person-id' not in text+html and 'private-recording.mp4' not in text+html
    saved = json.loads(text)
    checksum = saved.pop('export_content_sha256')
    assert digest(saved) == checksum
    assert saved['source_fingerprint'] == history['fingerprint']
    assert saved['rows'][0]['values'] == history['rows'][0]['values']
    with (out/'history.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[1]['comparison'] == 'DIFFERENT' and 'model_manifest_id' in rows[1]['differences']
    assert 'not_applicable' in text and '模型清单' in html
    assert (out/'chart.svg').is_file()
    with pytest.raises(ValueError):
        export_longitudinal_history(history, out)


def test_real_runtime_reads_scope_exports_reviewed_snapshot_and_refuses_stale_export(saved_session, tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    store.save_session(saved_session)
    store.save_session(later(saved_session))
    store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        replies = response(runtime, 'longitudinal_history', anchor_id='first', request_id='one')
        history = next(m['history'] for m in replies if m['kind'] == 'longitudinal_history')
        assert [r['session_id'] for r in history['rows']] == ['first', 'second']
        assert next(m['request_id'] for m in replies if m['kind'] == 'longitudinal_history') == 'one'
        replies = response(runtime, 'export_longitudinal_history', anchor_id='first', request_id='two',
                            expected_fingerprint=history['fingerprint'], metric='range_deg', directory=str(tmp_path/'export'))
        assert any(m['kind'] == 'longitudinal_exported' for m in replies)
        response(runtime, 'delete', id='second')
        replies = response(runtime, 'export_longitudinal_history', anchor_id='first', request_id='stale',
                            expected_fingerprint=history['fingerprint'], directory=str(tmp_path/'stale'))
        error = next(m for m in replies if m['kind'] == 'error')
        assert '已变化' in error['text'] and error['request_id'] == 'stale'
        assert not (tmp_path/'stale').exists()
        replies = response(runtime, 'longitudinal_history', anchor_id='deleted', request_id='absent')
        assert next(m for m in replies if m['kind'] == 'error')['request_id'] == 'absent'
        assert runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)
        assert not runtime.thread.is_alive()
    reopened = Storage(tmp_path/'home_rehab.sqlite3')
    assert reopened.get_session('first')['summary'] == saved_session['summary']
    reopened.close()
