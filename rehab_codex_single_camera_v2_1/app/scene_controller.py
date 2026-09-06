from __future__ import annotations

import copy
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from .domain import Context, PacketGate, RULE_VERSION, PREPROCESS_VERSION, JOINTS, digest, utc_now, dumps
from .geometry import valid_roi
from .quality import PoseAnalyzer
from .rehab import RehabEngine


class SceneController:
    """Single owner, used by runtime worker; no UI toolkit or camera construction."""
    def __init__(self, storage, camera, test_mode=False, vision_config=None):
        self.storage, self.camera, self.test_mode = storage, camera, test_mode
        self.generation = 0
        self.vision_config = copy.deepcopy(vision_config or {'imgsz': 640, 'keypoint_conf_min': .5, 'filter_tau_s': .12, 'invalid_gap_s': .5})
        self.capture_options = {}
        self.input_diagnostics = {}
        self.gate = PacketGate()
        self.context = None
        self.state = 'UNSELECTED'
        self.source = None
        self.setup = {}
        self.confirmed = False
        self.engine = None
        self.session = None
        self.latest_packet = self.latest_pose = self.latest_observation = None
        self.pending_path = self.storage.path.parent/'pending-session.json'
        self.pending = None
        self.recovery_backup_dir = None
        self.persisted_events = set()
        self.last_saved_id = None
        self.last_error = ''
        self.processed_frames = 0
        self.dropped_frames = 0
        self.previous_seq = None
        if self.pending_path.is_file():
            self.pending = json.loads(self.pending_path.read_text(encoding='utf-8'))
            self.state = 'SAVE_FAILED'

    def _context(self, run_id=''):
        self.generation += 1
        source = self.source
        return Context(self.generation, self.setup['scene_id'], source['ref'], source['kind'], source['usage_context'], run_id)

    def _analyzer(self, side):
        return PoseAnalyzer(side=side, conf_min=self.vision_config.get('keypoint_conf_min', .5),
                            tau=self.vision_config.get('filter_tau_s', .12), max_gap=self.vision_config.get('invalid_gap_s', .5))

    def open(self, source, setup, options=None):
        if self.pending is not None:
            raise RuntimeError('仍有未保存结果，请先重试保存或明确导出备份')
        if self.camera.worker is not None or self.context is not None:
            self.stop('configuration_change')
        self.source, self.setup = copy.deepcopy(source), copy.deepcopy(setup)
        self.capture_options = copy.deepcopy(options or {})
        self.input_diagnostics = {}
        self.last_error = ''
        kind = source['kind']
        if kind == 'SYNTHETIC' and not self.test_mode:
            raise ValueError('合成输入仅用于明确标记的软件测试')
        if kind not in ('LIVE_CAMERA', 'REPLAY_FILE', 'SYNTHETIC'):
            raise ValueError('仅支持本地摄像头和录像')
        if self.setup['scene_id'] in ('bedroom_demo', 'safety_demo'):
            self.source['usage_context'] = 'CONTROLLED_DEMO'
        if kind == 'SYNTHETIC':
            self.source['usage_context'] = 'TEST'
        self.context = self._context()
        self.gate.reset(self.context)
        self.confirmed = False
        self.analyzer = self._analyzer(setup['plan']['side'])
        self.latest_packet = self.latest_pose = self.latest_observation = None
        self.state = 'CONNECTING'
        try:
            if kind == 'LIVE_CAMERA':
                self.camera.open_camera(source['device_ref'], self.context, options)
                self.storage.save_device(source['ref'], source['device_ref'])
            elif kind == 'REPLAY_FILE':
                self.camera.open_replay(source['file'], self.context, options)
        except Exception:
            self.gate.reset()
            self.context = None
            self.state = 'ERROR'
            self.camera.stop()
            raise
        return self.context

    def confirm(self, setup):
        if self.state != 'PREVIEW' or self.latest_packet is None:
            raise ValueError('请先打开有效画面预览')
        setup = copy.deepcopy(setup)
        if (setup['scene_id'] != self.context.scene_id or setup['plan']['side'] != self.setup['plan']['side']
                or setup['plan']['exercise_id'] != self.setup['plan']['exercise_id'] or setup['view'] != self.setup['view']
                or setup.get('mirror') != self.setup.get('mirror')):
            raise ValueError('场景、动作、侧别或机位已经改变，请重新预览')
        if not setup.get('participant_confirmed'):
            raise ValueError('请人工确认参与者和机位')
        scene, exercise = setup['scene_id'], setup['plan']['exercise_id']
        required = {'activity': ['chair'], 'bedroom_demo': ['bed', 'bed_edge', 'exit', 'floor_watch'],
                    'safety_demo': ['floor_watch']}.get(scene, [])
        missing = [name for name in required if not valid_roi(setup.get('rois', {}).get(name))]
        if missing:
            raise ValueError('请在原画面圈定并确认区域：'+', '.join(missing))
        if scene == 'activity' and not setup.get('activity_permission'):
            raise ValueError('活动任务需要人工确认活动许可')
        if scene == 'rehab':
            expected_view = 'frontal' if exercise == 'shoulder_abduction' else 'sagittal'
            if setup['view'] != expected_view:
                raise ValueError('此动作需要'+('正面' if expected_view == 'frontal' else '侧面')+'机位')
            if exercise == 'sit_to_stand':
                c = setup['plan'].get('calibration', {})
                if not all(k in c for k in ('seated_knee', 'standing_knee', 'seated_hip_y', 'standing_hip_y')):
                    raise ValueError('请分别记录舒适坐位与站位基线')
                if c['seated_knee']-c['standing_knee'] < 20 or c['seated_hip_y']-c['standing_hip_y'] < .05:
                    raise ValueError('坐位/站位基线区分不足，请检查完整下肢视野并重新记录')
                expected = {'source_ref': self.source['ref'], 'frame_size': list(self.latest_pose.size) if self.latest_pose else None,
                            'side': setup['plan']['side'], 'view': setup['view']}
                if c.get('provenance') != expected:
                    raise ValueError('坐站基线不属于当前来源、尺寸、侧别或机位，请重新记录')
        setup['setup_confirmed_at'] = utc_now()
        setup['actual_size_confirmed'] = list(self.latest_packet.image.shape[1::-1])
        setup['source_ref'] = self.source['ref']
        setup['profile_id'] = digest({k: setup.get(k) for k in ('scene_id', 'source_ref', 'view', 'rois', 'placement_revision')}
                                     | {'exercise': exercise, 'side': setup['plan']['side']})[:24]
        setup['profile_version'] = digest({'view': setup['view'], 'rois': setup['rois'], 'size': setup['actual_size_confirmed'],
                                           'calibration': setup['plan'].get('calibration'), 'placement_revision': setup['placement_revision']})[:16]
        self.storage.save_profile(setup)
        self.setup, self.confirmed = setup, True
        return copy.deepcopy(setup)

    def start(self):
        if self.pending is not None or self.state != 'PREVIEW' or not self.confirmed:
            raise ValueError('需要有效预览和本次机位确认后才能开始')
        if self.latest_pose is None or self.latest_observation is None or self.latest_observation.status != 'VALID':
            raise ValueError('尚未取得有效的单人姿态，请检查模型与站位')
        necessary = ('raise_deg',) if self.setup['plan']['exercise_id'] == 'shoulder_abduction' else ('knee_flexion_deg', 'hip_y')
        if self.setup['scene_id'] == 'rehab' and any(self.latest_observation.value(k) is None for k in necessary):
            raise ValueError('动作必要关节不可见，请调整机位后再开始')
        if self.setup['plan']['needs_companion'] and not self.setup.get('companion_confirmed'):
            raise ValueError('训练计划要求陪同，请确认陪同者在场')
        run_id = uuid4().hex
        context = self._context(run_id)
        packet = self.latest_packet
        plan = copy.deepcopy(self.setup['plan'])
        self.setup['preprocessing'] = {k: self.vision_config.get(k) for k in ('imgsz', 'keypoint_conf_min', 'filter_tau_s', 'invalid_gap_s', 'device_at_start')}
        self.session = {'id': run_id, 'run_id': run_id, 'status': 'RUNNING', 'scene_id': self.setup['scene_id'],
                        'source_ref': self.source['ref'], 'source_kind': self.source['kind'],
                        'usage_context': self.source['usage_context'], 'submode': plan['submode'],
                        'exercise_id': plan['exercise_id'], 'side': plan['side'],
                        'participant_id': plan['participant_id'], 'recording_id': self.source.get('recording_id', run_id),
                        'start_utc': utc_now(), 'local_utc_offset': datetime.now().astimezone().strftime('%z'),
                        'time_basis': packet.time_basis, 'generation': context.generation, 'epoch': context.epoch,
                        'device_ref': self.source.get('device_ref'), 'backend': self.source.get('device_ref', {}).get('backend'),
                        'resolved_index_at_start': self.camera.resolved.index if self.camera.resolved else None,
                        'profile_id': self.setup['profile_id'], 'profile_version': self.setup['profile_version'],
                        'model_manifest_id': self.latest_pose.model_manifest_id,
                        'schema_id': 'coco17-v1', 'coordinate_space': 'raw_image_pixels',
                        'keypoint_order_version': 'coco17-anatomical-lr-v1', 'joint_order': JOINTS,
                        'rule_version': RULE_VERSION, 'preprocess_version': PREPROCESS_VERSION,
                        'preprocessing_hash': digest(self.setup['preprocessing']),
                        'requested_capture': {k: self.capture_options.get(k) for k in ('width', 'height', 'fps')} if self.source['kind'] == 'LIVE_CAMERA' else None,
                        'capture_backend_report': copy.deepcopy(self.input_diagnostics),
                        'plan_hash': digest(plan), 'config_snapshot': copy.deepcopy(self.setup),
                        'actual_capture': {'size': list(packet.image.shape[1::-1]), 'reported_fps': packet.reported_fps,
                                           'received_fps': packet.received_fps},
                        'repetitions': [], 'events': [], 'metrics': [], 'summary': {}}
        if self.setup['poses_consent']:
            self.session['poses'] = []
        scene = self.setup['scene_id']
        if scene == 'rehab':
            self.engine = RehabEngine(plan)
        else:
            from .activity import ActivityEngine
            from .bedroom import BedroomEngine
            from .safety import SafetyEngine
            self.engine = {'activity': ActivityEngine, 'bedroom_demo': BedroomEngine, 'safety_demo': SafetyEngine}[scene](self.setup)
        try:
            self.storage.save_session(self.session)
        except Exception:
            self.stop('initial_save_failed')
            raise
        self.context = context
        self.gate.reset(context)
        self.analyzer = self._analyzer(plan['side'])
        self.processed_frames = self.dropped_frames = 0
        self.previous_seq = None
        self.latest_packet = self.latest_pose = self.latest_observation = None
        if self.source['kind'] != 'SYNTHETIC':
            self.camera.change_context(context)
        self.state = 'ONLINE'
        return context

    def consume(self, packet, pose):
        if packet.context != self.context or not self.gate.admit(pose):
            return False
        if tuple(packet.image.shape[1::-1]) != tuple(pose.size):
            raise ValueError('画面与姿态尺寸不一致')
        if self.state == 'ONLINE' and list(pose.size) != self.setup.get('actual_size_confirmed'):
            self.stop('frame_shape_changed')
            raise RuntimeError('采集尺寸改变，已结束任务；需重新确认机位与区域')
        obs = self.analyzer.analyze(pose)
        self.latest_packet, self.latest_pose, self.latest_observation = packet, pose, obs
        if self.state == 'CONNECTING':
            self.state = 'PREVIEW'
        if self.state != 'ONLINE' or self.engine is None:
            return True
        previous_track = getattr(self, 'active_track', None)
        if obs.status == 'MULTI_PERSON' or (previous_track and obs.track_key and obs.track_key != previous_track):
            self.engine.process(obs)
            self.stop('identity_ambiguous')
            self.last_error = '参与者归属不明确，任务已保存；请重新预览并人工确认'
            return True
        if obs.track_key:
            self.active_track = obs.track_key
        self.engine.process(obs)
        self.processed_frames += 1
        if self.previous_seq is not None:
            self.dropped_frames += max(0, pose.seq-self.previous_seq-1)
        self.previous_seq = pose.seq
        self.session['metrics'].append({'time_s': obs.time_s, 'seq': pose.seq, 'phase': self.engine.phase,
                                        'observation_status': obs.status, 'metrics': asdict_metrics(obs.metrics),
                                        'annotation_origin': 'prediction', 'reasons': obs.reasons})
        if self.setup['poses_consent']:
            self.session['poses'].append({'pose': asdict(pose), 'center_raw_px': obs.center_raw_px,
                                           'local_pose': obs.local_pose})
        self.session['actual_capture'].update(received_fps=packet.received_fps, inference_ms=pose.inference_ms)
        for event in getattr(self.engine, 'events', []):
            if event['id'] not in self.persisted_events:
                event.update(run_id=self.context.run_id, source_kind=self.context.source_kind,
                             usage_context=self.context.usage_context, scene_id=self.context.scene_id,
                             source_ref=self.context.source_ref, profile_id=self.setup['profile_id'],
                             time_basis=self.session['time_basis'], rule_version=RULE_VERSION)
                self.session['events'].append(copy.deepcopy(event))
                try:
                    self.storage.save_event(event)
                except Exception:
                    self.stop('event_save_failed')
                    raise
                self.persisted_events.add(event['id'])
        return True

    def stop(self, reason='user_stop', privacy=False):
        if self.pending is not None and self.session is None:
            self.camera.stop()
            self.state = 'SAVE_FAILED'
            raise RuntimeError('仍有未保存结果，请先重试保存')
        self.generation += 1
        self.gate.reset()
        self.context = None
        self.confirmed = False
        self.active_track = None
        self.latest_packet = self.latest_pose = self.latest_observation = None
        stop_error = None
        try:
            self.camera.stop()
        except Exception as exc:
            stop_error = exc
        if self.session is not None:
            self.engine.finish(reason)
            snapshot = self.session
            snapshot.update(end_utc=utc_now(), stop_reason=reason, status='FINISHED' if reason == 'user_stop' else 'INTERRUPTED',
                            summary=self.engine.summary(), repetitions=copy.deepcopy(getattr(self.engine, 'repetitions', [])),
                            intervals=copy.deepcopy(getattr(self.engine, 'intervals', [])), tasks=copy.deepcopy(getattr(self.engine, 'tasks', [])),
                            processed_frames=self.processed_frames, skipped_capture_frames=self.dropped_frames)
            self.pending = self.storage.authorized_snapshot(snapshot)
            self.session, self.engine = None, None
            try:
                self.retry_save()
            except Exception as exc:
                self.last_error = f'报告保存失败，结果已保留待重试：{exc}'
                self.state = 'SAVE_FAILED'
                raise RuntimeError(self.last_error) from exc
        self.state = 'ERROR' if stop_error else ('PRIVACY_PAUSED' if privacy else 'UNSELECTED')
        if stop_error:
            raise stop_error

    def retry_save(self):
        if self.pending is None:
            return
        try:
            sid = self.storage.save_session(self.pending)
        except Exception:
            try:
                temp = self.pending_path.with_suffix('.tmp')
                temp.write_text(dumps(self.pending), encoding='utf-8')
                temp.replace(self.pending_path)
            except OSError:
                pass  # In-memory snapshot remains intact even if the disk is full.
            raise
        self.last_saved_id, self.pending = sid, None
        if self.pending_path.exists():
            self.pending_path.unlink()
        self.state = 'UNSELECTED'

    def backup_pending(self, directory):
        if self.pending is None:
            raise ValueError('没有待保存结果')
        target = Path(directory)/('pending-'+self.pending['id']+'.json')
        with target.open('x', encoding='utf-8') as stream:
            stream.write(dumps(self.pending, indent=2))
        self.recovery_backup_dir = target.parent
        return target

    def discard_pending(self, reason):
        if self.pending is None or not reason.strip():
            raise ValueError('明确填写丢弃原因后才能继续')
        record = {'run_id': self.pending['id'], 'reason': reason, 'at_utc': utc_now()}
        try:
            self.storage.audit('discard_pending_session', record)
        except Exception:
            directory = self.recovery_backup_dir or self.pending_path.parent
            with (directory/'recovery-actions.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(dumps({'action': 'discard_pending_session', **record})+'\n')
        if self.pending_path.exists():
            self.pending_path.unlink()
        self.pending = None
        self.state = 'UNSELECTED'

    def summary(self):
        return self.engine.summary() if self.engine else {}


def asdict_metrics(metrics):
    return {k: asdict(v) for k, v in metrics.items()}
