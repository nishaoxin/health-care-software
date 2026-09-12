"""Opt-in trusted-LAN demo, isolated synthetic data only. Not a production server.

Never receives the clinical database or a camera/controller. Pairing requires
short-lived code + explicit desktop approval. Sessions are memory-only and are
invalidated on revoke/stop. HTTP is intentionally NOT approved for real patients.
"""
import ipaddress
import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
from uuid import uuid4

from .silver_store import SilverStore
from .silver_service import execute
from .storage import Storage
from .domain import dumps

DEMO_SCOPE = dict(participant_id='silver-family-demo', source_kind='SYNTHETIC', usage_context='TEST')


class FamilyDemo:
    def __init__(self, directory, host='127.0.0.1', port=0):
        ip = ipaddress.ip_address(host)
        private = ip.version == 4 and any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8'))
        if not private:
            raise ValueError('请填写本机明确的可信局域网 IPv4；不允许公网或 0.0.0.0')
        self.lock = threading.RLock()
        self.closed = False
        self.sessions = {}
        self.code = f'{secrets.randbelow(1000000):06d}'
        self.code_deadline = time.monotonic()+120
        self.attempts = 0
        self.store = SilverStore(Path(directory)/'support.sqlite3')
        self.clinical = Storage(Path(directory)/'empty-test-history.sqlite3')
        # This new file is only an empty synthetic read model, never user history.
        if self.clinical.list_sessions():
            self.clinical.close()
            raise ValueError('手机演示库意外包含会话；拒绝提供数据')
        policy = self.store.policy(DEMO_SCOPE)
        self.store.consent(DEMO_SCOPE, '已配对的演示家属', ['summary', 'requests', 'checklist'], policy['revision'])
        demo = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def log_message(self, *args):
                pass  # Do not log pairing codes, cookies, IPs or user messages.

            def reply(self, status, value, *, cookie=None, html=False):
                body = value.encode('utf-8') if html else dumps(value).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'")
                if cookie:
                    self.send_header('Set-Cookie', cookie)
                self.end_headers()
                self.wfile.write(body)

            def origin_ok(self, post=False):
                return self.headers.get('Host') == demo.authority and (not post or self.headers.get('Origin') == demo.url)

            def session(self, *, csrf=False):
                cookies = SimpleCookie()
                cookies.load(self.headers.get('Cookie', ''))
                sid = cookies.get('silver_demo')
                session = demo.sessions.get(sid.value if sid else '')
                if (not session or demo.closed or time.monotonic() > session['expires']
                        or (csrf and not secrets.compare_digest(self.headers.get('X-CSRF', ''), session['csrf']))):
                    raise PermissionError('配对已失效，请在电脑重新开启演示')
                return session

            def do_GET(self):
                if not self.origin_ok():
                    self.reply(403, {'error': '来源不匹配'})
                    return
                try:
                    with demo.lock:
                        if self.path == '/family':
                            self.reply(200, PAGE, html=True)
                        elif self.path == '/api/state':
                            session = self.session()
                            if not session['approved']:
                                self.reply(202, {'pending': True, 'message': '等待电脑端确认此配对'})
                                return
                            result = execute(demo.store, demo.clinical, None, DEMO_SCOPE, family=True)
                            result.update(channel='LAN_FOREGROUND_TEST_ONLY', csrf=session['csrf'])
                            self.reply(200, result)
                        else:
                            self.reply(404, {'error': '不存在的页面'})
                except (PermissionError, ValueError):
                    self.reply(401, {'error': '未授权或授权已撤销；当前状态未知'})
                except Exception:
                    self.reply(503, {'error': '演示服务不可用，未确认本次操作成功'})

            def do_POST(self):
                if not self.origin_ok(post=True) or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    self.reply(403, {'error': '请求来源或格式不允许'})
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8192:
                        raise ValueError('请求过大或为空')
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError('请求必须为对象')
                    with demo.lock:
                        if self.path == '/api/pair':
                            demo.attempts += 1
                            if (demo.attempts > 6 or time.monotonic() > demo.code_deadline or not demo.code
                                    or not secrets.compare_digest(str(body.get('code', '')), demo.code)):
                                raise PermissionError('配对码失效，请在电脑重新开启演示')
                            token = secrets.token_urlsafe(32)
                            session = dict(id=uuid4().hex, csrf=secrets.token_urlsafe(32), approved=False,
                                           expires=time.monotonic()+3600)
                            demo.sessions[token] = session
                            demo.code = ''  # One-time code. Desktop approval is still required.
                            self.reply(202, {'pending': True}, cookie=f'silver_demo={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')
                        elif self.path == '/api/respond':
                            session = self.session(csrf=True)
                            if not session['approved']:
                                raise PermissionError('尚未由电脑端确认')
                            result = execute(demo.store, demo.clinical, None, DEMO_SCOPE, 'respond', family=True,
                                channel='LAN_FOREGROUND_TEST_ONLY',
                                id=body.get('id'), action=body.get('action'), note=body.get('note', ''), revision=body.get('revision'))
                            self.reply(200, {'saved': True, 'updated_utc': result['refreshed_utc']})
                        else:
                            self.reply(404, {'error': '不存在的操作'})
                except PermissionError:
                    self.reply(403, {'error': '配对、授权或请求凭证无效'})
                except (ValueError, TypeError, KeyError):
                    self.reply(400, {'error': '内容或处理顺序无效，请刷新后重试'})
                except Exception:
                    self.reply(503, {'error': '保存失败，未确认操作成功；请刷新核对'})

        try:
            self.http = ThreadingHTTPServer((host, port), Handler)
            self.http.daemon_threads = True
        except Exception:
            self.clinical.close()
            raise
        self.authority = f'{host}:{self.http.server_port}'
        self.url = 'http://'+self.authority
        self.thread = threading.Thread(target=self.http.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        self.thread.start()

    def status(self):
        with self.lock:
            return dict(url=self.url+'/family', code=self.code if time.monotonic() < self.code_deadline else '',
                code_remaining_s=max(0, int(self.code_deadline-time.monotonic())),
                pending=[s['id'] for s in self.sessions.values() if not s['approved'] and time.monotonic() < s['expires']],
                approved=sum(s['approved'] and time.monotonic() < s['expires'] for s in self.sessions.values()),
                requests=self.store.records(DEMO_SCOPE, 'request'), running=not self.closed,
                scope=DEMO_SCOPE, channel='LAN_FOREGROUND_TEST_ONLY')

    def approve(self, sid):
        with self.lock:
            session = next((s for s in self.sessions.values() if s['id'] == sid and time.monotonic() < s['expires']), None)
            if session is None:
                raise ValueError('待确认的配对已过期')
            session['approved'] = True

    def request(self):
        with self.lock:
            r = self.store.create_request(DEMO_SCOPE, 'help', 'TEST_EVENT：按钮注入的演示求助，不是实际求救或视觉检测', uuid4().hex)
            r['origin'] = 'TEST_EVENT'
            return self.store.save(DEMO_SCOPE, 'request', r, expected_revision=r['revision'])

    def stop(self):
        try:
            with self.lock:
                self.closed = True
                self.sessions.clear()
                policy = self.store.policy(DEMO_SCOPE)
                self.store.consent(DEMO_SCOPE, '', [], policy['revision'])
        finally:
            self.http.shutdown()
            self.http.server_close()
            self.thread.join(timeout=3)
            self.clinical.close()


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>银发健康 · 家属演示</title><style>
body{font:20px/1.6 system-ui,sans-serif;margin:0;background:#f5f3fa;color:#2b2340}main{max-width:760px;margin:auto;padding:20px}
h1{font-size:30px}button,input,textarea{font:inherit;padding:12px;border-radius:12px;border:1px solid #bcb2d2;box-sizing:border-box}
button{background:#6941d9;color:white;cursor:pointer;margin:6px 4px 6px 0;min-height:48px}input,textarea{width:100%}
article,.card{padding:18px;background:white;border:1px solid #e0d9ed;border-radius:16px;margin:16px 0}.note{color:#715529;background:#fff1d5;padding:12px}
#status{font-weight:700}.muted{font-size:16px;color:#625a70}button:disabled{opacity:.45}</style>
<main><h1>家庭安心 · 联动演示</h1><p class="note">SYNTHETIC / TEST · 仅测试资料。不是实际救援，不包含患者记录或摄像头直播。网页前台保持打开才轮询；锁屏、关闭或离网不保证收到。</p>
<section id="pair" class="card"><label>电脑显示的短时配对码<input id="code" inputmode="numeric" maxlength="6" autocomplete="off"></label><button id="pairButton">申请配对</button></section>
<p id="status" role="status" aria-live="polite">尚未连接 · 当前状态未知</p><p id="updated" class="muted"></p>
<button id="sound">启用提示音并测试</button><p class="muted">若听不见，请以页面文字为准；这不是系统后台通知。</p><div id="items"></div></main>
<script>
let csrf='',active=false,busy=false,audio=null,known=new Set();
const $=id=>document.getElementById(id);
function tone(){if(!audio)return;const o=audio.createOscillator(),g=audio.createGain();o.connect(g);g.connect(audio.destination);g.gain.value=.08;o.frequency.value=620;o.start();o.stop(audio.currentTime+.18)}
$('sound').onclick=async()=>{try{audio=new (window.AudioContext||window.webkitAudioContext)();await audio.resume();tone();$('sound').textContent='提示音已启用（本页前台）'}catch(e){$('status').textContent='声音不可用，请看文字提示'}};
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify(data),signal:AbortSignal.timeout(5000)});const j=await r.json();if(!r.ok)throw Error(j.error||'请求失败');return j}
$('pairButton').onclick=async()=>{try{await post('/api/pair',{code:$('code').value});$('code').value='';active=true;$('status').textContent='配对申请已提交，等待电脑确认';await update()}catch(e){$('status').textContent=e.message}};
async function update(){if(busy)return;busy=true;try{const r=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(5000)});const j=await r.json();if(!r.ok){active=false;csrf='';$('items').replaceChildren();throw Error(j.error||'授权不可用')}
if(j.pending){$('status').textContent='等待电脑确认配对，尚不能读取资料';return}active=true;csrf=j.csrf;$('pair').hidden=true;
$('status').textContent='已连接演示家属页 · 仅本页前台更新';$('updated').textContent='最近收到：'+new Date(j.refreshed_utc).toLocaleString()+'；其他时间未知';
const nodes=[];for(const q of j.requests){if(!known.has(q.id)&&known.size)tone();known.add(q.id);const a=document.createElement('article'),h=document.createElement('h2'),p=document.createElement('p');
const labels={OPEN:'待回应',ACKNOWLEDGED:'已查看',CLAIMED:'已认领 / 准备处理',RESOLVED:'已记录处理结果'};h.textContent=labels[q.status]||q.status;p.textContent=q.note;a.append(h,p);
for(const x of q.history){const t=document.createElement('p');t.className='muted';t.textContent=x.actor+' · '+x.action+' · '+x.note;a.append(t)}
const action={OPEN:'ack',ACKNOWLEDGED:'claim',CLAIMED:'resolve'}[q.status];if(action){const b=document.createElement('button');b.textContent={ack:'我已查看',claim:'我来联系 / 处理',resolve:'记录实际处理结果'}[action];b.onclick=async()=>{let note='';if(action==='resolve'){note=prompt('请记录实际做了什么；不自动代表已到场：')||'';if(!note.trim())return}b.disabled=true;try{await post('/api/respond',{id:q.id,action,note,revision:q.revision});await update()}catch(e){$('status').textContent=e.message;b.disabled=false}};a.append(b)}nodes.push(a)}$('items').replaceChildren(...nodes)
}catch(e){$('status').textContent='连接 / 授权不可用：'+e.message+'。当前状态未知，未确认操作成功'}finally{busy=false}}
setInterval(()=>{if(!document.hidden)update()},3000);update();
</script></html>'''
