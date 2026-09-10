"""Two independent local cameras, paired by receive time; no coordinate fusion."""
from __future__ import annotations

from collections import deque
import copy
from dataclasses import replace
import math
import time

from .camera_selection import camera_preference
from .domain import CONTEXTS, PacketGate, digest

DUAL_VERSION = 'dual-2d-1'
PAIRING_VERSION = 'receive-nearest-1'
MAX_RECEIVE_DELTA_S = .12
MAX_FRAME_AGE_S = 3.
VIEWS = {'frontal': '正面', 'sagittal': '侧面'}


def other_view(view):
    if view not in VIEWS:
        raise ValueError('双摄机位需要明确为正面或侧面')
    return 'sagittal' if view == 'frontal' else 'frontal'


def checked_devices(devices):
    if not isinstance(devices, dict) or set(devices) != set(VIEWS):
        raise ValueError('请分别选择正面与侧面摄像头')
    result = {view: camera_preference(devices[view]) for view in VIEWS}
    front, side = result['frontal'], result['sagittal']
    if front['backend'] != side['backend']:
        raise ValueError('双摄必须使用同一明确的采集接口，请重新选择')
    if front['path'].casefold() == side['path'].casefold():
        raise ValueError('正面与侧面不能选择同一摄像头')
    return result


def make_dual_source(devices, primary_view, usage_context):
    other_view(primary_view)
    devices = checked_devices(devices)
    if usage_context not in CONTEXTS:
        raise ValueError('请明确使用情境')
    identity = {view: {key: ref[key] for key in ('path', 'backend')} for view, ref in devices.items()}
    return dict(kind='LIVE_CAMERA', usage_context=usage_context,
                ref='camera-pair:'+digest(dict(devices=identity, primary_view=primary_view))[:24],
                device_ref=copy.deepcopy(devices[primary_view]),
                dual_camera=dict(version=DUAL_VERSION, primary_view=primary_view, devices=devices,
                                 pairing_version=PAIRING_VERSION, max_receive_delta_s=MAX_RECEIVE_DELTA_S))


def validate_dual_source(source, expected_view, *, allow_synthetic=False):
    if source.get('kind') != 'LIVE_CAMERA' and not (allow_synthetic and source.get('kind') == 'SYNTHETIC'):
        raise ValueError('双摄只支持两个本地实时摄像头')
    config = source.get('dual_camera') or {}
    canonical = make_dual_source(config.get('devices'), config.get('primary_view'), source.get('usage_context'))
    if (config != canonical['dual_camera'] or source.get('device_ref') != canonical['device_ref']
            or source.get('ref') != canonical['ref'] or config['primary_view'] != expected_view):
        raise ValueError('双摄来源或主机位与本次动作不一致，请重新选择和预览')
    return copy.deepcopy(config)


def secondary_context(context, view):
    other_view(view)
    return replace(context, source_ref=context.source_ref+':'+view, epoch=context.epoch+':'+view)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _usable_packet(packet, context, now=None):
    if (packet.context != context or type(packet.seq) is not int or packet.seq < 0
            or not _finite(packet.time_s) or not _finite(packet.received_monotonic)
            or packet.time_s != packet.received_monotonic or packet.time_basis != 'monotonic_receive'):
        return False
    return now is None or 0 <= now-packet.received_monotonic <= MAX_FRAME_AGE_S


def validate_pair(packet, primary_view, *, now=None):
    secondary_view = other_view(primary_view)
    paired = packet.paired_frame
    info = packet.pairing or {}
    if (paired is None or paired.paired_frame is not None or packet.camera_view != primary_view
            or paired.camera_view != secondary_view or not _usable_packet(packet, packet.context, now)
            or not _usable_packet(paired, secondary_context(packet.context, secondary_view), now)):
        raise ValueError('两路画面缺失、过期或来源不匹配，请重新预览')
    delta = abs(paired.received_monotonic-packet.received_monotonic)
    if (delta > MAX_RECEIVE_DELTA_S or info.get('version') != PAIRING_VERSION
            or info.get('max_receive_delta_s') != MAX_RECEIVE_DELTA_S
            or info.get('primary_view') != primary_view or info.get('secondary_view') != secondary_view
            or not _finite(info.get('receive_delta_s')) or not math.isclose(info['receive_delta_s'], delta, abs_tol=1e-9)):
        raise ValueError('两路接收时间未配对，不使用旧帧补齐')
    return paired


class FramePairer:
    """Bounded one-use nearest receive-time pairs. All metadata is recomputed."""
    def __init__(self, context, primary_view):
        self.primary_view, self.secondary_view = primary_view, other_view(primary_view)
        self.context = context
        self.contexts = {primary_view: context, self.secondary_view: secondary_context(context, self.secondary_view)}
        self.buffers = {view: deque() for view in VIEWS}
        self.gates = {view: PacketGate() for view in VIEWS}
        for view, gate in self.gates.items():
            gate.reset(self.contexts[view])
        self.received = dict.fromkeys(VIEWS, 0)
        self.dropped = dict.fromkeys(VIEWS, 0)
        self.pairs = 0

    def add(self, view, packet, *, now=None):
        now = time.monotonic() if now is None else now
        if view not in VIEWS or not _usable_packet(packet, self.contexts[view], now) or not self.gates[view].admit(packet):
            return False
        self.received[view] += 1
        buffer = self.buffers[view]
        if len(buffer) >= 4:
            buffer.popleft()
            self.dropped[view] += 1
        buffer.append(replace(packet, camera_view=view, paired_frame=None, pairing=None))
        return True

    def take(self, *, now=None):
        if now is not None:
            for view, buffer in self.buffers.items():
                while buffer and now-buffer[0].received_monotonic > MAX_FRAME_AGE_S:
                    buffer.popleft()
                    self.dropped[view] += 1
        primary, secondary = self.buffers[self.primary_view], self.buffers[self.secondary_view]
        while primary and secondary:
            first = primary[0]
            index = min(range(len(secondary)), key=lambda i: abs(secondary[i].received_monotonic-first.received_monotonic))
            delta = abs(secondary[index].received_monotonic-first.received_monotonic)
            if delta <= MAX_RECEIVE_DELTA_S:
                primary.popleft()
                for _ in range(index):
                    secondary.popleft()
                    self.dropped[self.secondary_view] += 1
                paired = secondary.popleft()
                self.pairs += 1
                return replace(first, paired_frame=paired,
                               pairing=dict(version=PAIRING_VERSION, primary_view=self.primary_view,
                                            secondary_view=self.secondary_view, receive_delta_s=delta,
                                            max_receive_delta_s=MAX_RECEIVE_DELTA_S))
            view = self.primary_view if first.received_monotonic < secondary[0].received_monotonic else self.secondary_view
            self.buffers[view].popleft()
            self.dropped[view] += 1
        return None


class PairedSourceWorker:
    """CameraManager-owned adapter; only its SourceWorkers create captures."""
    def __init__(self, devices, context, primary_view, options, worker_factory):
        self.context, self.primary_view = context, primary_view
        self.pairer = FramePairer(context, primary_view)
        self.devices, self.options, self.worker_factory = devices, options or {}, worker_factory
        self.workers = {}
        self.opened = {}
        self.sent_opened = False
        self.stopping = False
        self.forced_stop = False

    def start(self):
        for view, device in self.devices.items():
            source = dict(kind='LIVE_CAMERA', index=device.index, backend=device.backend)
            worker = self.worker_factory(source, self.pairer.contexts[view], copy.deepcopy(self.options))
            self.workers[view] = worker
            worker.start()

    def change_context(self, context):
        self.context = context
        self.pairer = FramePairer(context, self.primary_view)
        for view, worker in self.workers.items():
            if worker is None:
                raise RuntimeError('双摄输入已经释放，需重新预览')
            worker.change_context(self.pairer.contexts[view])

    def read_latest(self):
        if self.stopping:
            return None
        for view, worker in self.workers.items():
            packet = worker.read_latest() if worker is not None else None
            if packet is not None:
                self.pairer.add(view, packet, now=time.monotonic())
        return self.pairer.take(now=time.monotonic())

    def read_status(self):
        result = []
        for view, worker in self.workers.items():
            for status in worker.read_status() if worker is not None else []:
                kind = status.get('status')
                if kind == 'OPENED':
                    self.opened[view] = {key: value for key, value in status.items() if key != 'status'}
                elif kind in ('ERROR', 'EOF', 'RELEASED', 'RELEASE_UNCONFIRMED') and not self.stopping:
                    result.append(dict(status='ERROR', view=view,
                                       message=VIEWS[view]+'摄像头：'+status.get('message', '输入已结束，请检查连接后重新预览')))
        if len(self.opened) == 2 and not self.sent_opened:
            self.sent_opened = True
            result.append(dict(status='OPENED', streams=copy.deepcopy(self.opened), pairing_version=PAIRING_VERSION))
        return result

    def acknowledge(self, seq):
        # Both streams are live; replay acknowledgements must not be routed by a
        # sequence number shared by two different devices.
        return None

    def diagnostics(self):
        return dict(pairing_version=PAIRING_VERSION, emitted_pairs=self.pairer.pairs,
                    received_by_pairer=dict(self.pairer.received),
                    discarded_unpaired=dict(self.pairer.dropped),
                    still_buffered={view: len(buffer) for view, buffer in self.pairer.buffers.items()},
                    scope='current_context_after_source_latest_queue')

    def stop(self):
        self.stopping = True
        for worker in self.workers.values():
            if worker is not None and callable(getattr(worker, 'request_stop', None)):
                try:
                    worker.request_stop()
                except Exception:
                    pass
        complete = True
        for view, worker in self.workers.items():
            if worker is None:
                continue
            try:
                released = worker.stop()
            except Exception:
                released = False
            self.forced_stop = self.forced_stop or bool(getattr(worker, 'forced_stop', False))
            if released:
                self.workers[view] = None
            else:
                complete = False
        self.pairer = FramePairer(self.context, self.primary_view)
        return complete
