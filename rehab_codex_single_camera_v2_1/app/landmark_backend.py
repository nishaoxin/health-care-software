"""Bounded, camera-free bridge to the optional, isolated landmark runtime."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from .domain import PoseFrame, PosePerson
from .landmark_schemas import BACKEND_SCHEMAS, MAX_FRAME_BYTES, MAX_MESSAGE_BYTES, ORDERS, joint_names
from .settings import ROOT


def landmark_python(root=ROOT):
    return Path(root)/'.venv-landmarks'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def verified_model(backend, model_dir=None):
    folder = Path(model_dir or ROOT/'assets/models')
    if backend not in ('mediapipe_pose', 'mediapipe_hands'):
        raise ValueError('未知扩展关键点组件')
    manifest_path = folder/'landmarks-manifest.json'
    if not manifest_path.is_file():
        raise RuntimeError('尚未准备扩展模型来源清单；请运行显式准备脚本，不会自动下载')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entry = manifest.get('models', {}).get(backend)
    if (not isinstance(entry, dict) or entry.get('schema_id') != BACKEND_SCHEMAS[backend] or
            not isinstance(entry.get('filename'), str) or Path(entry['filename']).name != entry['filename']):
        raise RuntimeError('扩展模型清单的文件或骨架契约无效')
    model = folder/entry['filename']
    if not model.is_file():
        raise RuntimeError('所选动作需要尚未准备的本地扩展模型；原有动作不受影响')
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != entry.get('sha256'):
        raise RuntimeError('扩展模型 SHA256 与可信清单不一致，未加载')
    return model.resolve(), digest


class LandmarkBackend:
    def __init__(self, backend, *, side='left', model_dir=None, python_path=None, startup_timeout=25., inference_timeout=8., cancel_event=None):
        self.backend, self.schema = backend, BACKEND_SCHEMAS.get(backend)
        self.side = side
        self.cancel_event = cancel_event or threading.Event()
        self.model_dir = model_dir
        self.python = Path(python_path) if python_path else landmark_python()
        self.startup_timeout, self.inference_timeout = startup_timeout, inference_timeout
        self.process = None
        self.responses = queue.Queue(maxsize=4)
        self.reader = None
        self.log = None
        self.manifest_id = ''
        self.runtime_version = None
        self.previous = None
        self.track_number = 0

    def _read_responses(self, process, responses):
        try:
            while True:
                line = process.stdout.readline(MAX_MESSAGE_BYTES+1)
                if not line:
                    raise EOFError('扩展关键点进程已经退出')
                if len(line) > MAX_MESSAGE_BYTES or not line.endswith(b'\n'):
                    raise ValueError('扩展关键点响应过大或不完整')
                value = json.loads(line)
                responses.put(value, timeout=1)
        except Exception as exc:
            try:
                responses.put({'kind': 'error', 'message': str(exc)}, timeout=1)
            except queue.Full:
                pass

    def _receive(self, timeout):
        deadline = time.monotonic()+timeout
        while True:
            if self.cancel_event.is_set():
                raise RuntimeError('扩展关键点处理已取消')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('扩展关键点处理超时；未使用旧骨架补算')
            try:
                message = self.responses.get(timeout=min(.1, remaining))
                break
            except queue.Empty:
                continue
        if not isinstance(message, dict):
            raise RuntimeError('扩展关键点响应格式错误')
        if message.get('kind') == 'error':
            raise RuntimeError('扩展关键点组件：'+str(message.get('message', '未知错误')))
        return message

    def _start(self):
        model, digest = verified_model('mediapipe_pose' if self.backend == 'mediapipe_wrist' else self.backend, self.model_dir)
        extra_args = []
        hand_digest = None
        if self.backend == 'mediapipe_wrist':
            hand_model, hand_digest = verified_model('mediapipe_hands', self.model_dir)
            extra_args = ['--hand-model', str(hand_model), '--hand-sha256', hand_digest, '--side', self.side]
        if not self.python.is_file():
            raise RuntimeError('尚未安装扩展关键点独立环境；原有 YOLO 动作仍可使用')
        folder = ROOT/'.runtime'
        folder.mkdir(exist_ok=True)
        env = dict(os.environ, MPLCONFIGDIR=str(folder/'landmarks-mpl'), MPLBACKEND='Agg', PYTHONUNBUFFERED='1')
        self.responses = queue.Queue(maxsize=4)
        self.log = (folder/'landmarks-worker.log').open('ab')
        try:
            self.process = subprocess.Popen([str(self.python), '-m', 'app.landmark_process', '--backend', self.backend,
                                        '--model', str(model), '--sha256', digest, *extra_args],
                                       cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=self.log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.reader = threading.Thread(target=self._read_responses, args=(self.process, self.responses), name='landmark-response', daemon=True)
            self.reader.start()
            ready = self._receive(self.startup_timeout)
            if (ready.get('kind') != 'ready' or ready.get('schema_id') != self.schema or
                    ready.get('backend') != self.backend or ready.get('model_sha256') != digest or
                    ready.get('keypoint_order_version') != ORDERS[self.schema] or ready.get('runtime_version') != '1.0.1' or
                    (hand_digest and (ready.get('hand_model_sha256') != hand_digest or ready.get('selected_side') != self.side))):
                raise RuntimeError('扩展关键点握手契约不符')
            self.manifest_id = digest if not hand_digest else digest+'+'+hand_digest
            self.runtime_version = ready.get('runtime_version')
        except Exception:
            self.close()
            raise

    def _assign_track(self, packet, targets):
        if len(targets) != 1:
            self.previous = None
            return None
        target = targets[0]
        xy = target['xy']
        finite = [p for p in xy if len(p) == 2 and all(v is not None and math.isfinite(v) for v in p)]
        if len(finite) != len(xy):
            self.previous = None
            return None
        center = (sum(p[0] for p in finite)/len(finite), sum(p[1] for p in finite)/len(finite))
        hand = target.get('attributes', {}).get('model_handedness')
        previous = self.previous
        w, h = packet.image.shape[1], packet.image.shape[0]
        continuous = (previous is not None and previous[0] == packet.context and
                      0 < packet.time_s-previous[1] <= .5 and hand == previous[3] and
                      math.dist(center, previous[2]) <= .15*math.hypot(w, h))
        if not continuous:
            self.track_number += 1
        self.previous = packet.context, packet.time_s, center, hand
        return f'{packet.context.epoch}:landmark:{self.track_number}'

    def infer(self, packet):
        import numpy as np
        image = packet.image
        if (not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or
                image.shape[2] != 3 or not 0 < image.nbytes <= MAX_FRAME_BYTES):
            raise ValueError('关键点输入必须为有效的 BGR 彩色画面')
        if packet.time_s is None or not math.isfinite(packet.time_s):
            raise ValueError('关键点输入时间无效')
        if self.process is None:
            self._start()
        start = time.perf_counter()
        h, w = image.shape[:2]
        payload = np.ascontiguousarray(image[:, :, ::-1]).tobytes()
        header = {'kind': 'frame', 'seq': packet.seq, 'epoch': packet.context.epoch,
                  'width': w, 'height': h, 'byte_count': len(payload)}
        error = []
        process = self.process
        def write_request():
            try:
                process.stdin.write(json.dumps(header).encode('utf-8')+b'\n')
                process.stdin.write(payload)
                process.stdin.flush()
            except Exception as exc:
                error.append(exc)
        writer = threading.Thread(target=write_request, name='landmark-request', daemon=True)
        writer.start()
        try:
            deadline = time.monotonic()+self.inference_timeout
            while writer.is_alive() and time.monotonic() < deadline and not self.cancel_event.is_set():
                writer.join(.1)
            if self.cancel_event.is_set():
                raise RuntimeError('扩展关键点处理已取消')
            if writer.is_alive():
                raise TimeoutError('扩展关键点进程未接收画面')
            if error:
                raise RuntimeError('扩展关键点进程写入失败') from error[0]
            result = self._receive(self.inference_timeout)
            if result.get('kind') != 'result' or result.get('seq') != packet.seq or result.get('epoch') != packet.context.epoch:
                raise RuntimeError('拒绝过期或上下文不符的扩展骨架')
            targets = result.get('targets')
            if not isinstance(targets, list) or len(targets) > 2:
                raise ValueError('扩展骨架目标数量不符合契约')
            count = len(joint_names(self.schema))
            for target in targets:
                if len(target.get('xy', [])) != count or len(target.get('conf', [])) != count:
                    raise ValueError('扩展骨架点数不符合契约')
            track = self._assign_track(packet, targets)
            people = []
            for target in targets:
                finite = [p for p in target['xy'] if all(v is not None and math.isfinite(v) for v in p)]
                bbox = [min(p[0] for p in finite), min(p[1] for p in finite),
                        max(p[0] for p in finite), max(p[1] for p in finite)] if finite else [0., 0., 0., 0.]
                attributes = dict(target.get('attributes', {}), identity_kind='spatial_session_only',
                                  detector_mode='IMAGE', runtime_version=self.runtime_version)
                people.append(PosePerson(track, bbox, target['xy'], target['conf'], attributes))
            return PoseFrame(packet.context, packet.seq, packet.time_s, (w, h), people,
                             (time.perf_counter()-start)*1000, schema_id=self.schema,
                             keypoint_order_version=ORDERS[self.schema], model_manifest_id=self.manifest_id,
                             backend=self.backend, target_kind='hand' if self.backend == 'mediapipe_hands' else 'person')
        except Exception:
            self.close()
            writer.join(timeout=1)
            raise

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            # This process only owns model inference, never capture or storage.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        if self.reader:
            self.reader.join(timeout=2)
        if self.log:
            self.log.close()
            self.log = None
        self.previous = None
