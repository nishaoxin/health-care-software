"""Optional support records. Separate versioned SQLite file, short owned transactions.

No camera, model, network or clinical-database ownership lives here. Failure of
this optional store must not stop rehabilitation. Each call owns its connection.
"""
import copy
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .domain import SOURCES, CONTEXTS, digest, dumps, utc_now


SCOPES = ('participant_id', 'source_kind', 'usage_context')
GRANTS = ('summary', 'requests', 'safety', 'changes', 'checklist')
FEELINGS = ('今天较累', '疼痛或不舒服', '椅子或机位变化', '希望家人联系', '不想回答')
CHECKLIST = ('通道杂物', '地毯翘边', '夜间照明', '座椅稳定与扶手', '常用物品取放')


def scope_key(scope):
    if (not isinstance(scope, dict) or not isinstance(scope.get('participant_id'), str)
            or not 0 < len(scope['participant_id'].strip()) <= 120
            or scope.get('source_kind') not in SOURCES or scope.get('usage_context') not in CONTEXTS):
        raise ValueError('请选择明确的用户、来源与使用情境')
    return {k: scope[k] for k in SCOPES}


def text(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'请填写 1～{limit} 字的说明')
    return value.strip()


class SilverStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('银发记录版本不兼容，未更改原文件')
            if version == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError('银发记录文件包含未知表，未覆盖')
            db.executescript('''CREATE TABLE IF NOT EXISTS records(
                scope TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(scope,kind,id));
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at_utc TEXT, payload TEXT);
                PRAGMA user_version=1;''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=4)
        try:
            with db:
                yield db
        finally:
            db.close()

    def records(self, scope, kind):
        key = digest(scope_key(scope))
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                'SELECT payload FROM records WHERE scope=? AND kind=? ORDER BY rowid DESC', (key, kind))]

    def get(self, scope, kind, rid):
        return next((r for r in self.records(scope, kind) if r['id'] == rid), None)

    def save(self, scope, kind, record, *, expected_revision=0):
        scope = scope_key(scope)
        item = copy.deepcopy(record)
        rid = text(item.get('id'), 160)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('记录版本无效')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM records WHERE scope=? AND kind=? AND id=?',
                             (digest(scope), kind, rid)).fetchone()
            old = json.loads(row[0]) if row else None
            if (old or {}).get('revision', 0) != expected_revision:
                raise ValueError('记录已更新，请刷新后再操作')
            item.update(id=rid, scope=scope, revision=expected_revision+1, updated_utc=utc_now())
            db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (digest(scope), kind, rid, dumps(item)))
            db.execute('INSERT INTO audit(at_utc,payload) VALUES (?,?)',
                       (item['updated_utc'], dumps(dict(scope=scope, kind=kind, id=rid, revision=item['revision']))))
        return item

    def policy(self, scope):
        return self.get(scope, 'policy', 'sharing') or dict(id='sharing', revision=0, recipient='', grants=[])

    def authorize(self, scope, category):
        policy = self.policy(scope)
        if category not in policy['grants'] or not policy['recipient']:
            raise ValueError('本项未获共享授权或授权已撤销；请返回本人页面')
        return policy['recipient']

    def consent(self, scope, recipient, grants, revision):
        if not isinstance(grants, list) or set(grants)-set(GRANTS):
            raise ValueError('共享范围无效')
        return self.save(scope, 'policy', dict(id='sharing', recipient=text(recipient, 60) if grants else '',
                         grants=list(dict.fromkeys(grants))), expected_revision=revision)

    def create_request(self, scope, kind, note, request_id):
        if kind not in ('help', 'contact', 'checklist'):
            raise ValueError('不支持的请求类型')
        rid, note = text(request_id, 160), text(note)
        existing = self.get(scope, 'request', rid)
        if existing:
            if existing['kind'] != kind or existing['note'] != note:
                raise ValueError('重复请求编号对应内容不一致')
            return existing
        return self.save(scope, 'request', dict(id=rid, kind=kind, note=note, status='OPEN',
            origin='USER_REQUEST' if kind != 'checklist' else 'MANUAL_CHECKLIST',
            created_utc=utc_now(), history=[], remote_delivery='NOT_CONNECTED'))

    def transition_request(self, scope, rid, action, note, revision, *, family=False, channel='LOCAL_ROLE'):
        if channel not in ('LOCAL_ROLE', 'LAN_FOREGROUND_TEST_ONLY'):
            raise ValueError('回应通道无效')
        item = self.get(scope, 'request', rid)
        if item is None:
            raise ValueError('请求不存在')
        category = 'checklist' if item['kind'] == 'checklist' else 'requests'
        actor = self.authorize(scope, category) if family else '本人/本机工作人员'
        edges = {'ack': ('OPEN', 'ACKNOWLEDGED'), 'claim': ('ACKNOWLEDGED', 'CLAIMED'),
                 'resolve': ('CLAIMED', 'RESOLVED'), 'submit': ('CLAIMED', 'AWAITING_CONFIRMATION'),
                 'confirm': ('AWAITING_CONFIRMATION', 'RESOLVED')}
        if action not in edges or (family and action == 'confirm'):
            raise ValueError('本操作需要本人确认')
        if item['kind'] == 'checklist' and action == 'resolve':
            raise ValueError('整改须先提交完成记录，再由本人确认')
        if item['kind'] != 'checklist' and action in ('submit', 'confirm'):
            raise ValueError('此操作只适用于整改任务')
        start, end = edges[action]
        if item['status'] == end and item['history'] and item['history'][-1]['actor'] == actor:
            return item  # A repeated acknowledgement is not another real-world action.
        if item['status'] != start or item['revision'] != revision:
            raise ValueError('处理状态已变化，请刷新；已查看、认领与完成须分别记录')
        note = text(note) if action in ('resolve', 'submit', 'confirm') else str(note or '')[:500]
        item['status'] = end
        item['history'].append(dict(action=action, actor=actor, note=note, at_utc=utc_now(), channel=channel))
        if channel == 'LAN_FOREGROUND_TEST_ONLY':
            item['remote_delivery'] = 'ACKNOWLEDGED_BY_FAMILY_PAGE'
        return self.save(scope, 'request', item, expected_revision=revision)

    def feedback(self, scope, source_id, feeling, share):
        if feeling not in FEELINGS or type(share) is not bool:
            raise ValueError('请选择本人情况和是否分享')
        if share:
            self.authorize(scope, 'changes')
        rid = text(source_id, 160)
        old = self.get(scope, 'feedback', rid)
        return self.save(scope, 'feedback', dict(id=rid, feeling=feeling, shared=share,
            evidence_method='SELF_REPORTED'), expected_revision=(old or {}).get('revision', 0))
