from __future__ import annotations

import copy
from dataclasses import asdict
from pathlib import Path
import queue
from statistics import median
import threading
import time

from .audio import AudioGate
from .camera_manager import CameraManager
from .domain import digest, dumps, utc_now
from .reports import export_session, render_report, render_body_profile, export_body_profile
from .assessment import build_body_profile
from .exercises import exercise_spec
from .scene_controller import SceneController
from .settings import ROOT, load_settings
from .source_worker import put_latest
from .storage import Storage
from .vision import VisionWorker


def input_timeout_reason(state, now, connect_started_wall, last_frame_wall, settings):
    """Keep slow camera startup separate from an established stream going stale."""
    if state == 'CONNECTING' and connect_started_wall is not None:
        if now-connect_started_wall > settings.get('connect_timeout_s', 15):
            return 'connect_timeout'
    elif state in ('PREVIEW', 'ONLINE') and last_frame_wall is not None:
        if now-last_frame_wall > settings.get('stale_after_s', 3):
            return 'stream_stale'
    return None


class Runtime:
    """UI sends commands; this thread owns orchestration, rules, and storage calls."""
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or ROOT/'data')
        self.commands, self.messages, self.views = queue.Queue(), queue.Queue(), queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.controller = None
        self.preview_history = []
        self.connect_started_wall = None
        self.last_frame_wall = None
        self.last_sound_count = 0
        self.last_sound_event = None
        self.capture_settings = {}
        self.thread = threading.Thread(target=self._run, name='application-runtime', daemon=True)
        self.thread.start()

    def command(self, name, **kw):
        self.commands.put((name, kw))

    def _view(self, packet=None, pose=None, error=None):
        c = self.controller
        put_latest(self.views, {'state': c.state, 'context': c.context, 'summary': c.summary(),
                               'confirmed': c.confirmed, 'packet': packet, 'pose': pose,
                               'error': error, 'last_saved_id': c.last_saved_id,
                               'pending': c.pending is not None,
                               'observation_status': c.latest_observation.status if pose and c.latest_observation else None})

    def _message(self, kind, **data):
        self.messages.put({'kind': kind, **data})

    def _inference_failed(self, packet, error):
        self.controller.latest_packet = packet
        self.controller.latest_pose = self.controller.latest_observation = None
        self.preview_history = []
        self.audio.reset(self.controller.context)
        self._view(packet, error=error)

    def _execute(self, name, kw):
        c, store = self.controller, self.store
        if name == 'enumerate':
            devices = self.camera.enumerate(kw['backend'])
            self._message('devices', devices=[asdict(d) for d in devices])
        elif name == 'open':
            self.audio.reset()
            self.vision.clear()
            options = {k: self.capture_settings.get('request_'+k, default) for k, default in (('width', 1280), ('height', 720), ('fps', 30))}
            options.update(kw.get('options') or {})
            c.open(kw['source'], kw['setup'], options)
            self.preview_history = []
            self.connect_started_wall = time.monotonic()
            self.last_frame_wall = None
            self._view()
        elif name == 'confirm':
            confirmed = c.confirm(kw['setup'])
            self._message('confirmed', setup=confirmed)
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'unconfirm':
            c.confirmed = False
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'start':
            if c.source['kind'] == 'LIVE_CAMERA' and (c.latest_packet is None or time.monotonic()-c.latest_packet.received_monotonic > 3):
                raise ValueError('画面过期，请重新预览')
            c.vision_config['device_at_start'] = self.vision.device
            context = c.start()
            self.vision.clear()
            self.audio.reset(context)
            self.preview_history = []
            self.last_sound_count = 0
            self.last_sound_event = None
            self._view()
        elif name in ('stop', 'privacy', 'switch'):
            self.audio.reset()
            self.vision.clear()
            had_session = c.session is not None
            c.stop(kw.get('reason', name), privacy=name == 'privacy')
            self.preview_history = []
            self.connect_started_wall = None
            self.last_frame_wall = None
            self._view()
            if had_session and c.last_saved_id:
                self._message('saved', id=c.last_saved_id)
        elif name == 'training_control':
            self.audio.reset()
            try:
                c.training_control(kw['action'], setup_confirmed=kw.get('setup_confirmed', False))
            finally:
                self.audio.reset(c.context)
            self.last_sound_count = c.engine.completed
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'preview_segment':
            if c.state != 'PREVIEW' or c.context.source_kind != 'REPLAY_FILE' or self.camera.worker is None:
                raise ValueError('请先打开录像预览')
            self.camera.worker.preview_segment(1.2)
            self._message('notice', text='正在分析 1.2 秒预览片段；不计正式动作，可用于检查稳定机位和坐站基线。')
        elif name == 'baseline':
            if c.state != 'PREVIEW':
                raise ValueError('基线只在预览中记录')
            valid = [o for o in self.preview_history if o.value('knee_flexion_deg') is not None and o.value('hip_y') is not None]
            if len(valid) < 5 or valid[-1].time_s-valid[0].time_s < .8:
                raise ValueError('请让指定侧肩、髋、膝、踝完整可见，并稳定保持约 1 秒')
            knees, hips = [o.value('knee_flexion_deg') for o in valid], [o.value('hip_y') for o in valid]
            if max(knees)-min(knees) > 10 or max(hips)-min(hips) > .03:
                raise ValueError('姿势还不稳定，请保持舒适姿势后重新记录')
            self._message('baseline', position=kw['position'], knee=median(knees), hip=median(hips),
                          provenance={'source_ref': c.source['ref'], 'frame_size': list(c.latest_pose.size),
                                      'side': c.setup['plan']['side'], 'view': c.setup['view']})
        elif name == 'joint_baseline':
            if (c.latest_packet is None or (c.source['kind'] == 'LIVE_CAMERA' and
                    time.monotonic()-c.latest_packet.received_monotonic > 3)):
                raise ValueError('预览画面过期，请重新预览后记录')
            baseline = c.record_joint_baseline(self.preview_history, kw['position'])
            self.preview_history = []
            self._message('joint_baseline', baseline=baseline, context=c.context)
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'history':
            sessions = store.list_sessions()
            self._message('history', sessions=[{k: v for k, v in s.items() if k not in ('metrics', 'poses')} for s in sessions])
        elif name == 'participants':
            self._message('participants', participants=store.list_participants())
        elif name in ('assessment_batch', 'create_assessment_batch', 'change_assessment_batch'):
            from .assessment_batches import scope_key, batch_view
            scope = scope_key(kw['scope'])
            if name != 'assessment_batch' and (c.session is not None or c.pending is not None
                                               or c.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING')):
                raise ValueError('请先结束并保存当前任务，再修改评估清单')
            if name == 'create_assessment_batch':
                batch = store.create_assessment_batch(scope, kw['items'])
            elif name == 'change_assessment_batch':
                batch = store.get_assessment_batch(kw['id'])
                if batch is None or scope_key(batch) != scope:
                    raise ValueError('清单不属于当前用户与来源')
                batch = store.change_assessment_batch(kw['id'], kw['action'], expected_revision=kw['expected_revision'],
                                                       entry_key=kw.get('entry_key'), reason=kw.get('reason'))
            else:
                batch = store.current_assessment_batch(scope)
            self._message('assessment_batch', scope=scope,
                          batch=batch_view(batch, store.list_sessions()) if batch else None)
        elif name == 'save_participant':
            if c.session is not None or c.pending is not None or c.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING'):
                raise ValueError('请先停止采集并保存当前任务，再编辑个人信息')
            profile = store.save_participant(kw['profile'], expected_revision=kw['expected_revision'])
            self._message('participant_saved', profile=profile)
        elif name in ('body_profile', 'export_body_profile'):
            profile = build_body_profile(store.list_sessions(), kw['participant_id'],
                                         kw['source_kind'], kw['usage_context'])
            if name == 'body_profile':
                self._message('body_profile', profile=profile, html=render_body_profile(profile, compact=True))
            else:
                output = export_body_profile(profile, kw['directory'])
                self._message('notice', text=f'身体信息已导出：{output}')
        elif name in ('report', 'training_review'):
            s = store.get_session(kw['id'])
            if s is None:
                raise ValueError('报告不存在')
            self._message(name, snapshot=s, html=render_report(s))
        elif name == 'save_training_feedback':
            saved = store.save_training_feedback(kw['id'], kw['feedback'], expected_revision=kw['expected_revision'])
            self._message('training_feedback_saved', snapshot=saved, html=render_report(saved))
        elif name == 'export':
            snapshot = store.get_session(kw['id'])
            if snapshot is None:
                raise ValueError('报告不存在')
            out = export_session(snapshot, kw['directory'])
            self._message('notice', text=f'报告已导出到：{out}')
        elif name == 'delete':
            store.delete_session(kw['id'])
            self._execute('history', {})
        elif name == 'events':
            self._message('events', events=store.list_events())
        elif name == 'event_transition':
            store.transition_event(kw['id'], kw['status'], kw['operator'], kw['note'])
            self._execute('events', {})
        elif name == 'retry_save':
            c.retry_save()
            self._view()
            self._message('saved', id=c.last_saved_id)
        elif name == 'backup_pending':
            output = c.backup_pending(kw['directory'])
            self._message('notice', text=f'待保存结果已备份到：{output}')
        elif name == 'discard_pending':
            c.discard_pending(kw['reason'])
            self._view()
            self._message('notice', text='已按明确操作丢弃待保存结果，并记录了丢弃原因。')
        elif name == 'task':
            if c.state != 'ONLINE' or c.context.scene_id != 'activity':
                raise ValueError('请先开始活动场景')
            c.engine.choose_task(kw['task'], c.latest_observation.time_s if c.latest_observation else 0)
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'profile':
            profiles = store._call(lambda db: [__import__('json').loads(r[0]) for r in db.execute('SELECT payload FROM scene_profiles')])
            self._message('profiles', profiles=profiles)
        elif name == 'shutdown':
            self.audio.reset()
            self.vision.clear()
            c.stop('application_exit')
            if c.pending is not None:
                raise RuntimeError('存在未保存结果，不能关闭')
            self.stop_event.set()
        else:
            raise ValueError('未知操作')

    def _run(self):
        self.store = None
        self.camera = CameraManager()
        self.vision = None
        self.audio = AudioGate()
        try:
            settings = load_settings()
            self.capture_settings = settings['capture']
            self.store = Storage(self.data_dir/'home_rehab.sqlite3')
            recovered = self.store.recover_unfinished()
            self.controller = SceneController(self.store, self.camera, vision_config=settings['vision'])
            self.vision = VisionWorker(ROOT/settings['vision']['model_path'],
                                       imgsz=settings['vision']['imgsz'], device=settings['vision'].get('device', 'cpu'))
            self._message('ready')
            if recovered:
                self._message('notice', text=f'发现 {recovered} 条上次非正常结束的任务，已标记中断；未补造缺失结果。')
            self._view()
            self.ready.set()
            while not self.stop_event.is_set():
                try:
                    name, kw = self.commands.get_nowait()
                except queue.Empty:
                    name = None
                if name is not None:
                    try:
                        self._execute(name, kw)
                    except Exception as exc:
                        self._message('error', text=str(exc), command=name)
                        self._view(error=str(exc))
                    finally:
                        self._message('command_done', command=name)
                c = self.controller
                worker = self.camera.worker
                if worker is not None:
                    statuses = worker.read_status()
                    for status in statuses:
                        if status['status'] == 'OPENED':
                            c.input_diagnostics = {k: v for k, v in status.items() if k != 'status'}
                    error = next((s for s in statuses if s['status'] == 'ERROR'), None)
                    ended = any(s['status'] == 'EOF' for s in statuses)
                    if error or ended:
                        had_session = c.session is not None
                        save_ok = True
                        try:
                            c.stop('input_error' if error else 'replay_end')
                        except Exception as exc:
                            save_ok = False
                            self._message('error', text=str(exc))
                        self.audio.reset()
                        self.vision.clear()
                        self.connect_started_wall = None
                        self.last_frame_wall = None
                        self._view(error=error['message'] if error else None)
                        if save_ok:
                            if had_session and c.last_saved_id:
                                self._message('saved', id=c.last_saved_id)
                            self._message('notice', text=error['message'] if error else
                                          '回放结束，已保存本次任务。' if had_session else '回放已结束；预览没有生成任务报告。')
                        continue
                    packet = worker.read_latest()
                    if packet is not None and packet.context == c.context:
                        self.last_frame_wall = time.monotonic()
                        self.connect_started_wall = None
                        if c.state == 'CONNECTING':
                            c.state = 'PREVIEW'
                        backend = exercise_spec(c.setup['plan']['exercise_id'])['backend'] if c.setup['scene_id'] == 'rehab' else 'yolo'
                        self.vision.submit(packet, backend=backend, side=c.setup['plan']['side'])
                        if c.latest_pose is None:
                            self._view(packet)
                    elif packet is not None:
                        worker.acknowledge(packet.seq)
                    timeout_reason = (input_timeout_reason(c.state, time.monotonic(), self.connect_started_wall,
                                                           self.last_frame_wall, self.capture_settings)
                                      if c.context and c.context.source_kind == 'LIVE_CAMERA' else None)
                    if timeout_reason:
                        try:
                            c.stop(timeout_reason)
                            c.state = 'OFFLINE'
                        except Exception as exc:
                            self._message('error', text=str(exc))
                        self.audio.reset()
                        self.vision.clear()
                        self.connect_started_wall = None
                        self.last_frame_wall = None
                        connect_timeout = self.capture_settings.get('connect_timeout_s', 15)
                        stale_timeout = self.capture_settings.get('stale_after_s', 3)
                        message = (f'摄像头启动超过 {connect_timeout:g} 秒仍未取得画面；请检查占用后重新预览'
                                   if timeout_reason == 'connect_timeout' else
                                   f'超过 {stale_timeout:g} 秒未取得新画面，任务已中断；请重新预览')
                        self._view(error=message)
                try:
                    packet, pose, error = self.vision.outputs.get_nowait()
                except queue.Empty:
                    time.sleep(.01)
                    continue
                if self.camera.worker is not None:
                    self.camera.worker.acknowledge(packet.seq)
                if packet.context != c.context:
                    continue
                if error:
                    self._inference_failed(packet, error)
                    continue
                try:
                    c.consume(packet, pose)
                    if c.state == 'PREVIEW' and c.latest_observation:
                        obs = c.latest_observation
                        self.preview_history = [o for o in self.preview_history if 0 <= obs.time_s-o.time_s <= 1.2 and o.track_key == obs.track_key]
                        self.preview_history.append(obs)
                    if c.state == 'ONLINE' and c.setup['plan']['sound_enabled']:
                        summary = c.summary()
                        events = getattr(c.engine, 'events', [])
                        new_event = events and events[-1]['id'] != self.last_sound_event
                        issues = summary.get('current_issues', []) if c.setup['plan']['submode'] == 'training' else []
                        new_count = summary.get('completed', 0) > self.last_sound_count
                        due = summary.get('reminder_due', False)
                        if new_event or issues or new_count or due:
                            priority = 0 if new_event else 2 if issues else 3
                            if self.audio.play(c.context, packet.time_s, ROOT/'assets/audio'/('alert.wav' if new_event else 'cue.wav'), priority):
                                if new_event:
                                    self.last_sound_event = events[-1]['id']
                                self.last_sound_count = summary.get('completed', 0)
                                if issues and getattr(c.engine, 'current', None):
                                    for issue in c.engine.current['issues']:
                                        if issue['rule_id'] == issues[0]['rule_id']:
                                            issue['feedback_emitted_at'] = utc_now()
                    self._view(packet if c.context else None, pose if c.context else None, error=c.last_error or None)
                except Exception as exc:
                    try:
                        c.stop('analysis_error')
                    except Exception as save_exc:
                        self._message('error', text=str(save_exc))
                    self.audio.reset()
                    self.vision.clear()
                    self._view(error=str(exc))
        except Exception as exc:
            self._message('fatal', text=str(exc))
            self.ready.set()
        finally:
            self.audio.reset()
            try:
                self.camera.stop()
            except Exception:
                pass
            if self.vision:
                self.vision.close()
            if self.store:
                self.store.close()
            self._message('shutdown_done')
