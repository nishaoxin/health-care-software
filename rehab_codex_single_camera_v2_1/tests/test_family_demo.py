import http.client
import json
import sqlite3
import time

import pytest
from app.family_demo import FamilyDemo, DEMO_SCOPE


@pytest.fixture
def demo(tmp_path):
    server = FamilyDemo(tmp_path/'demo')  # Loopback only. No real LAN or patient data.
    yield server
    server.stop()


def call(demo, method, path, body=None, *, cookie='', csrf='', origin=None, host=None):
    connection = http.client.HTTPConnection('127.0.0.1', demo.http.server_port, timeout=5)
    headers = {'Host': host or demo.authority, 'Origin': origin or demo.url,
               'Content-Type': 'application/json', 'Cookie': cookie, 'X-CSRF': csrf}
    try:
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        return response.status, json.loads(data) if path != '/family' or response.status != 200 else data.decode(), response.getheader('Set-Cookie')
    finally:
        connection.close()


def pair(demo):
    code = demo.code
    status, data, cookie = call(demo, 'POST', '/api/pair', {'code': code})
    assert status == 202 and data['pending'] and 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    assert call(demo, 'GET', '/api/state', cookie=cookie)[0] == 202
    demo.approve(demo.status()['pending'][0])
    status, state, _ = call(demo, 'GET', '/api/state', cookie=cookie)
    assert status == 200 and state['scope'] == DEMO_SCOPE
    return cookie, state['csrf']


def test_pair_requires_desktop_consent_and_code_is_one_time(demo):
    assert call(demo, 'GET', '/api/state')[0] == 401
    code = demo.code
    cookie, csrf = pair(demo)
    assert call(demo, 'POST', '/api/pair', {'code': code})[0] == 403
    assert call(demo, 'GET', '/api/state', cookie=cookie, host='evil.example')[0] == 403
    assert demo.status()['approved'] == 1
    assert demo.clinical.list_sessions() == []


def test_real_http_acknowledgement_is_committed_not_delivery_guess(demo):
    cookie, csrf = pair(demo)
    request = demo.request()
    assert request['origin'] == 'TEST_EVENT' and not request['history']
    for action, expected in (('ack', 'ACKNOWLEDGED'), ('claim', 'CLAIMED'), ('resolve', 'RESOLVED')):
        payload = dict(id=request['id'], action=action, revision=request['revision'], note='测试人工说明')
        status, data, _ = call(demo, 'POST', '/api/respond', payload, cookie=cookie, csrf=csrf)
        assert status == 200 and data['saved']
        request = demo.store.get(DEMO_SCOPE, 'request', request['id'])
        assert request['status'] == expected and request['history'][-1]['channel'] == 'LAN_FOREGROUND_TEST_ONLY'
        assert call(demo, 'POST', '/api/respond', payload, cookie=cookie, csrf=csrf)[0] == 200
    assert len(request['history']) == 3
    assert request['remote_delivery'] == 'ACKNOWLEDGED_BY_FAMILY_PAGE'


def test_csrf_origin_wrong_scope_and_revocation(demo):
    cookie, csrf = pair(demo)
    r = demo.request()
    payload = dict(id=r['id'], action='ack', revision=r['revision'])
    assert call(demo, 'POST', '/api/respond', payload, cookie=cookie)[0] == 403
    assert call(demo, 'POST', '/api/respond', payload, cookie=cookie, csrf=csrf, origin='http://evil.example')[0] == 403
    assert demo.store.get(DEMO_SCOPE, 'request', r['id'])['status'] == 'OPEN'
    policy = demo.store.policy(DEMO_SCOPE)
    demo.store.consent(DEMO_SCOPE, '', [], policy['revision'])
    assert call(demo, 'GET', '/api/state', cookie=cookie)[0] == 401
    assert call(demo, 'POST', '/api/respond', payload, cookie=cookie, csrf=csrf)[0] != 200


def test_pair_expiry_and_attempt_limit(demo):
    code = demo.code
    demo.code_deadline = time.monotonic()-1
    assert call(demo, 'POST', '/api/pair', {'code': code})[0] == 403
    demo.code_deadline = time.monotonic()+30
    for _ in range(6):
        assert call(demo, 'POST', '/api/pair', {'code': 'WRONG'})[0] == 403
    assert call(demo, 'POST', '/api/pair', {'code': code})[0] == 403


def test_failed_sqlite_write_does_not_return_saved(demo):
    cookie, csrf = pair(demo)
    r = demo.request()
    with sqlite3.connect(demo.store.path) as db:
        db.execute("CREATE TRIGGER write_fail BEFORE INSERT ON records BEGIN SELECT RAISE(FAIL,'test'); END")
    try:
        status, body, _ = call(demo, 'POST', '/api/respond', dict(id=r['id'], action='ack', revision=r['revision']), cookie=cookie, csrf=csrf)
        assert status == 503 and 'saved' not in body
        assert demo.store.get(DEMO_SCOPE, 'request', r['id'])['status'] == 'OPEN'
    finally:
        with sqlite3.connect(demo.store.path) as db:
            db.execute('DROP TRIGGER write_fail')


@pytest.mark.parametrize('host', ['0.0.0.0', '8.8.8.8', '224.0.0.1', '169.254.2.3', '::1'])
def test_no_public_wildcard_or_unapproved_bind(tmp_path, host):
    with pytest.raises(ValueError):
        FamilyDemo(tmp_path/'no-server', host)


def test_static_page_declares_limits_and_has_no_live_video(demo):
    status, page, _ = call(demo, 'GET', '/family')
    assert status == 200 and 'SYNTHETIC / TEST' in page
    assert 'textContent' in page and 'innerHTML' not in page
    assert '<video' not in page and '锁屏' in page
