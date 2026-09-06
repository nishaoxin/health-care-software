from __future__ import annotations

import copy
from concurrent.futures import Future
import json
from pathlib import Path
import queue
import sqlite3
import threading

from .domain import dumps, utc_now


class Storage:
    """One owning SQLite thread. Critical writes always return a commit result."""
    def __init__(self, path, readonly=False):
        self.path, self.readonly = Path(path), readonly
        self.jobs = queue.Queue()
        self.ready = Future()
        self.closed = False
        self.thread = threading.Thread(target=self._run, name='sqlite-writer', daemon=True)
        self.thread.start()
        self.ready.result(timeout=10)

    def _run(self):
        conn = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            existed = self.path.exists()
            conn = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True) if self.readonly else sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=4000')
            if not self.readonly:
                version = conn.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, 1):
                    raise RuntimeError('数据库版本高于本程序支持范围，原数据已保留')
                if version == 0 and existed:
                    backup_path = self.path.with_name(self.path.name+'.before-v1-'+utc_now().replace(':', '-')+'.bak')
                    with sqlite3.connect(backup_path) as backup:
                        conn.backup(backup)
                    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if tables:
                        raise RuntimeError('发现未知旧数据库，已备份；需要显式迁移，未覆盖原表')
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS config_snapshots(session_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS repetitions(session_id TEXT, ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                    CREATE TABLE IF NOT EXISTS activity_intervals(session_id TEXT, ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                    CREATE TABLE IF NOT EXISTS tasks(session_id TEXT, ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS scene_profiles(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at_utc TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
                    PRAGMA user_version=1;
                ''')
                conn.commit()
            self.ready.set_result(True)
        except Exception as exc:
            self.ready.set_exception(exc)
            if conn is not None:
                conn.close()
            return
        while True:
            job = self.jobs.get()
            if job is None:
                break
            fn, future = job
            try:
                result = fn(conn)
                conn.commit()
                future.set_result(result)
            except Exception as exc:
                conn.rollback()
                future.set_exception(exc)
        conn.close()

    def _call(self, fn):
        if self.closed:
            raise RuntimeError('数据库已关闭')
        future = Future()
        self.jobs.put((fn, future))
        return future.result(timeout=15)

    def close(self):
        if not self.closed:
            self.closed = True
            self.jobs.put(None)
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError('数据库线程尚未结束')

    @staticmethod
    def authorized_snapshot(snapshot):
        item = copy.deepcopy(snapshot)
        if not item.get('config_snapshot', {}).get('poses_consent', False):
            item.pop('poses', None)
        item.pop('raw_frames', None)
        return item

    def save_session(self, snapshot):
        item = self.authorized_snapshot(snapshot)
        def save(c):
            c.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)',
                      (item['id'], item.get('start_utc'), item.get('scene_id'), dumps(item)))
            c.execute('INSERT OR REPLACE INTO config_snapshots VALUES (?,?)',
                      (item['id'], dumps(item.get('config_snapshot', {}))))
            for table, key in (('repetitions', 'repetitions'), ('activity_intervals', 'intervals'), ('tasks', 'tasks')):
                c.execute(f'DELETE FROM {table} WHERE session_id=?', (item['id'],))
                c.executemany(f'INSERT INTO {table} VALUES (?,?,?)',
                              [(item['id'], i, dumps(r)) for i, r in enumerate(item.get(key, []))])
            for event in item.get('events', []):
                # Never overwrite a user's ACK / RESOLVED with an old run snapshot.
                c.execute('INSERT OR IGNORE INTO events VALUES (?,?,?)', (event['id'], event['status'], dumps(event)))
            return item['id']
        return self._call(save)

    def get_session(self, sid):
        row = self._call(lambda c: c.execute('SELECT payload FROM sessions WHERE id=?', (sid,)).fetchone())
        return json.loads(row['payload']) if row else None

    def list_sessions(self):
        return self._call(lambda c: [json.loads(r[0]) for r in c.execute('SELECT payload FROM sessions ORDER BY start_utc DESC')])

    def recover_unfinished(self):
        def recover(c):
            count = 0
            for row in c.execute('SELECT id,payload FROM sessions').fetchall():
                item = json.loads(row['payload'])
                if item.get('status') == 'RUNNING':
                    item.update(status='INTERRUPTED', stop_reason='unexpected_exit', end_utc=None,
                                recovered_utc=utc_now(), recovery_note='上次非正常退出；仅保留当时成功写入的记录，未补造结束时间或动作。')
                    c.execute('UPDATE sessions SET payload=? WHERE id=?', (dumps(item), row['id']))
                    count += 1
            return count
        return self._call(recover)

    def delete_session(self, sid):
        def delete(c):
            for table in ('config_snapshots', 'repetitions', 'activity_intervals', 'tasks'):
                c.execute(f'DELETE FROM {table} WHERE session_id=?', (sid,))
            c.execute('DELETE FROM sessions WHERE id=?', (sid,))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)', (utc_now(), 'delete_session', dumps({'id': sid})))
        self._call(delete)

    def save_event(self, event):
        return self._call(lambda c: c.execute('INSERT OR IGNORE INTO events VALUES (?,?,?)',
                          (event['id'], event.get('status', 'OPEN'), dumps(event))).rowcount)

    def list_events(self, unresolved=False):
        query = "SELECT payload FROM events WHERE status!='RESOLVED'" if unresolved else 'SELECT payload FROM events'
        return self._call(lambda c: [json.loads(r[0]) for r in c.execute(query+' ORDER BY rowid DESC')])

    def transition_event(self, eid, status, operator, note):
        def change(c):
            row = c.execute('SELECT payload FROM events WHERE id=?', (eid,)).fetchone()
            if row is None:
                raise ValueError('事件不存在')
            item = json.loads(row[0])
            expected = {'ACKNOWLEDGED': 'OPEN', 'RESOLVED': 'ACKNOWLEDGED'}
            if expected.get(status) != item['status'] or not operator.strip():
                raise ValueError('请先查看事件，再记录处理结果')
            if status == 'RESOLVED' and not note.strip():
                raise ValueError('关闭事件需要填写处理结果')
            at = utc_now()
            item.update(status=status)
            item['human_ack_time' if status == 'ACKNOWLEDGED' else 'human_resolved_time'] = at
            item.setdefault('history', []).append({'status': status, 'at_utc': at, 'operator': operator, 'note': note})
            c.execute('UPDATE events SET status=?,payload=? WHERE id=?', (status, dumps(item), eid))
            return item
        return self._call(change)

    def save_profile(self, profile):
        return self._call(lambda c: c.execute('INSERT OR REPLACE INTO scene_profiles VALUES (?,?)',
                          (profile['profile_id'], dumps(profile))).rowcount)

    def get_profile(self, pid):
        row = self._call(lambda c: c.execute('SELECT payload FROM scene_profiles WHERE id=?', (pid,)).fetchone())
        return json.loads(row[0]) if row else None

    def save_device(self, ref, descriptor):
        return self._call(lambda c: c.execute('INSERT OR REPLACE INTO devices VALUES (?,?)', (ref, dumps(descriptor))).rowcount)

    def audit(self, action, payload):
        return self._call(lambda c: c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)',
                                              (utc_now(), action, dumps(payload))).rowcount)
