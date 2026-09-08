import copy

import pytest

from app.storage import Storage
from app.reports import export_session, render_report


@pytest.fixture
def store(tmp_path):
    storage = Storage(tmp_path/'data.sqlite3')
    storage.save_session({'id': 'training-test', 'scene_id': 'rehab', 'submode': 'training',
                         'exercise_id': 'shoulder_abduction', 'participant_id': 'test-person',
                         'source_kind': 'SYNTHETIC', 'usage_context': 'TEST', 'status': 'FINISHED',
                         'summary': {'completed': 2}, 'repetitions': [{'number': 1}], 'config_snapshot': {}})
    yield storage
    storage.close()


def test_feedback_is_separate_and_revisioned_not_a_change_to_measured_data(store, tmp_path):
    before = store.get_session('training-test')
    updated = store.save_training_feedback('training-test', {'pain': 0, 'fatigue': None,
                  'notes': '<script>private-test</script>', 'reason': 'fatigue'}, expected_revision=0)
    assert updated['summary'] == before['summary'] and updated['repetitions'] == before['repetitions']
    assert updated['training_feedback']['pain'] == 0
    assert updated['training_feedback']['fatigue'] is None
    assert updated['training_feedback']['record_origin'] == 'self_report'
    assert updated['training_feedback']['revision'] == 1
    assert store.get_session('training-test') == updated
    html = render_report(updated)
    assert '本次训练感受' in html and '&lt;script&gt;' in html and '<script>' not in html
    assert '本人自述' in html
    with pytest.raises(ValueError, match='已更新'):
        store.save_training_feedback('training-test', {}, expected_revision=0)
    assert store.get_session('training-test') == updated
    output = export_session(updated, tmp_path/'export')
    assert 'private-test' not in (output/'session.json').read_text(encoding='utf-8')
    assert 'private-test' not in (output/'report.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('change', [{'status': 'RUNNING'}, {'submode': 'assessment'}, {'scene_id': 'activity'}])
def test_feedback_never_attaches_to_active_or_wrong_kind_of_session(store, change):
    snapshot = copy.deepcopy(store.get_session('training-test'))
    snapshot.update(change)
    store.save_session(snapshot)
    with pytest.raises(ValueError):
        store.save_training_feedback('training-test', {}, expected_revision=0)
    assert 'training_feedback' not in store.get_session('training-test')


def test_deleted_report_is_not_recreated_by_late_feedback(store):
    store.delete_session('training-test')
    with pytest.raises(ValueError, match='不存在'):
        store.save_training_feedback('training-test', {}, expected_revision=0)
    assert store.get_session('training-test') is None
