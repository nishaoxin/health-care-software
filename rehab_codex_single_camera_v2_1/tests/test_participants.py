"""Local manual profiles: no camera, no inferred diagnoses, no old-data loss."""
import json
import sqlite3
from datetime import date

import pytest

from app.domain import dumps
from app.participants import new_participant, validate_participant
from app.storage import Storage
from app.reports import export_session, render_report


@pytest.fixture
def store(tmp_path):
    value = Storage(tmp_path/'records.sqlite3')
    yield value
    value.close()


def test_profile_reopens_with_explicit_origin_and_empty_unknowns(tmp_path):
    path = tmp_path/'records.sqlite3'
    store = Storage(path)
    draft = new_participant()
    draft.update(display_name='林女士', goals='自己穿外套', reported_by='family')
    saved = store.save_participant(draft, expected_revision=0)
    assert saved['revision'] == 1 and saved['record_origin'] == 'manual'
    assert saved['birth_year'] is None and saved['affected_side'] == 'unknown'
    assert saved['created_utc'] == saved['updated_utc']
    store.close()
    reopened = Storage(path)
    try:
        assert reopened.get_participant(saved['participant_id']) == saved
        assert reopened.list_participants() == [saved]
        assert reopened.list_sessions() == []
    finally:
        reopened.close()


@pytest.mark.parametrize('key,value', [
    ('display_name', ''), ('display_name', 'x'*61), ('display_name', 'a\nb'),
    ('birth_year', True), ('birth_year', date.today().year+1), ('birth_year', float('nan')),
    ('birth_year', 1750), ('birth_year', '1950'), ('affected_side', 'diagnosed-left'),
    ('reported_by', 'camera'), ('support', 'safe'), ('goals', 'x'*1001),
    ('participant_id', ''), ('participant_id', 'x'*81), ('restrictions', 3),
])
def test_invalid_manual_data_is_rejected_without_writing(store, key, value):
    draft = new_participant()
    draft.update({'display_name': '测试用户', key: value})
    with pytest.raises(ValueError):
        store.save_participant(draft, expected_revision=0)
    assert store.list_participants() == []


def test_revision_conflict_never_overwrites_and_metadata_cannot_be_spoofed(store):
    draft = new_participant()
    draft.update(display_name='旧称呼', revision=999, record_origin='model', created_utc='fake')
    first = store.save_participant(draft, expected_revision=0)
    updated = store.save_participant(dict(first, display_name='新称呼'), expected_revision=1)
    assert updated['participant_id'] == first['participant_id']
    assert updated['created_utc'] == first['created_utc'] != 'fake'
    assert updated['revision'] == 2 and updated['record_origin'] == 'manual'
    with pytest.raises(ValueError, match='已更新'):
        store.save_participant(dict(first, goals='stale'), expected_revision=1)
    assert store.get_participant(first['participant_id']) == updated


def test_legacy_ids_are_not_renamed_or_automatically_filled(store):
    old = {'id': 'old', 'scene_id': 'rehab', 'participant_id': 'older-id',
           'config_snapshot': {'plan': {'participant_id': 'older-id'}}, 'summary': {'completed': 2}}
    store.save_session(old)
    store.save_profile({'profile_id': 'camera-old', 'plan': {'participant_id': 'setup-only'}})
    people = {p['participant_id']: p for p in store.list_participants()}
    assert set(people) == {'older-id', 'setup-only'}
    assert people['older-id']['revision'] == 0
    assert people['older-id']['record_origin'] == 'not_recorded'
    assert people['older-id']['birth_year'] is None
    store.save_participant(dict(people['older-id'], display_name='补充称呼'), expected_revision=0)
    assert store.get_session('old') == old
    assert len(store.list_participants()) == 2
    assert store.get_participant('setup-only') is None


def test_v1_migration_backs_up_before_adding_table_and_never_rewrites_sessions(tmp_path):
    path = tmp_path/'legacy.sqlite3'
    original = {'id': 'old', 'scene_id': 'rehab', 'participant_id': 'legacy-user'}
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT NOT NULL)')
        conn.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('old', None, 'rehab', dumps(original)))
        conn.execute('PRAGMA user_version=1')
    store = Storage(path)
    try:
        assert store.get_session('old') == original
        assert store._call(lambda c: c.execute('PRAGMA user_version').fetchone()[0]) == 2
        backups = list(tmp_path.glob('legacy.sqlite3.before-v2-*.bak'))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as backup:
            assert backup.execute('PRAGMA user_version').fetchone()[0] == 1
            assert json.loads(backup.execute('SELECT payload FROM sessions').fetchone()[0]) == original
            assert not backup.execute("SELECT name FROM sqlite_master WHERE name='participants'").fetchall()
    finally:
        store.close()
    store = Storage(path)
    store.close()
    assert len(list(tmp_path.glob('legacy.sqlite3.before-v2-*.bak'))) == 1


def test_failed_migration_backup_leaves_original_schema_untouched(tmp_path, monkeypatch):
    path = tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT NOT NULL)')
        conn.execute('PRAGMA user_version=1')
    original_connect = sqlite3.connect
    def connect(target, *args, **kwargs):
        if str(target).endswith('.bak'):
            raise OSError('backup unavailable')
        return original_connect(target, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    with pytest.raises(OSError, match='backup unavailable'):
        Storage(path)
    with original_connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='participants'").fetchall()


def test_readonly_v1_can_read_legacy_people_without_migration(tmp_path):
    path = tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT NOT NULL)')
        conn.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('one', None, 'rehab', dumps({'participant_id': 'old'})))
        conn.execute('PRAGMA user_version=1')
    store = Storage(path, readonly=True)
    try:
        assert store.list_participants()[0]['participant_id'] == 'old'
        assert store.get_participant('old') is None
        with pytest.raises(Exception):
            store.save_participant(dict(new_participant(), display_name='No write'), expected_revision=0)
    finally:
        store.close()
    assert not list(tmp_path.glob('*.bak'))


def test_local_report_has_manual_snapshot_but_exports_exclude_free_text(store, tmp_path):
    draft = dict(new_participant(), display_name='<script>秘密称呼</script>',
                 goals='私密目标', restrictions='私密限制', reported_by='family')
    profile = store.save_participant(draft, expected_revision=0)
    snapshot = {'id': 'local-test', 'scene_id': 'rehab', 'exercise_id': 'shoulder_abduction',
                'participant_id': profile['participant_id'], 'source_kind': 'SYNTHETIC', 'usage_context': 'TEST',
                'participant_snapshot': profile, 'summary': {}, 'config_snapshot': {}}
    html = render_report(snapshot)
    assert '私密目标' in html and '手工填写' in html and '家属' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    out = export_session(snapshot, tmp_path/'export')
    for name in ('session.json', 'report.html'):
        text = (out/name).read_text(encoding='utf-8')
        assert all(secret not in text for secret in ('秘密称呼', '私密目标', '私密限制'))
