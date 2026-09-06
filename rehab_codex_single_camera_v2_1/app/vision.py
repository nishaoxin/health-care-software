from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time

from .domain import PoseFrame, PosePerson
from .settings import ROOT
from .source_worker import put_latest


class VisionWorker:
    def __init__(self, model_path=None, imgsz=640, device='cpu'):
        self.model_path = Path(model_path or ROOT/'assets/models/yolo11n-pose.pt')
        self.imgsz, self.device = imgsz, device
        self.inputs, self.outputs = queue.Queue(maxsize=1), queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name='vision-worker', daemon=True)
        self.model = None
        self.context = None
        self.manifest_id = ''
        self.thread.start()

    def _load(self):
        if not self.model_path.is_file():
            raise RuntimeError('尚未配置本地 YOLO11n-pose 权重，程序不会自动下载')
        manifest_path = self.model_path.with_name('manifest.json')
        if not manifest_path.is_file():
            raise RuntimeError('缺少模型来源与 SHA256 清单，未加载权重')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        h = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        if h != manifest.get('sha256') or manifest.get('schema_id') != 'coco17-v1':
            raise RuntimeError('模型 hash 或骨架契约与可信清单不一致，未加载')
        config_dir = ROOT/'.runtime/ultralytics'
        config_dir.mkdir(parents=True, exist_ok=True)
        os.environ['YOLO_CONFIG_DIR'] = str(config_dir)
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        os.environ['YOLO_OFFLINE'] = 'true'
        from ultralytics import YOLO, settings
        import torch
        settings.update({'sync': False})
        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2)//2)))
        if self.device == 'auto':
            self.device = '0' if torch.cuda.is_available() else 'cpu'
        self.model = YOLO(str(self.model_path.resolve()))
        if self.model.task != 'pose':
            self.model = None
            raise RuntimeError('文件不是姿态模型')
        self.manifest_id = h

    def infer(self, packet):
        if self.model is None:
            self._load()
        if self.context != packet.context:
            predictor = getattr(self.model, 'predictor', None)
            if predictor is not None:
                for tracker in getattr(predictor, 'trackers', []):
                    tracker.reset()
            self.context = packet.context
        start = time.perf_counter()
        result = self.model.track(packet.image, persist=True, tracker='bytetrack.yaml',
                                  conf=.35, imgsz=self.imgsz, device=self.device, verbose=False)[0]
        people = []
        if result.boxes is not None and result.keypoints is not None:
            boxes = result.boxes.xyxy.cpu().tolist()
            ids = result.boxes.id.cpu().tolist() if result.boxes.id is not None else [None]*len(boxes)
            xy = result.keypoints.xy.cpu().tolist()
            conf = result.keypoints.conf.cpu().tolist() if result.keypoints.conf is not None else None
            if conf is not None:
                for box, track, points, confidence in zip(boxes, ids, xy, conf):
                    key = f'{packet.context.epoch}:{int(track)}' if track is not None else None
                    people.append(PosePerson(key, box, points, confidence))
        h, w = packet.image.shape[:2]
        return PoseFrame(packet.context, packet.seq, packet.time_s, (w, h), people,
                         (time.perf_counter()-start)*1000, model_manifest_id=self.manifest_id)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                packet = self.inputs.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                result = self.infer(packet)
                put_latest(self.outputs, (packet, result, None))
            except Exception as exc:
                put_latest(self.outputs, (packet, None, f'{type(exc).__name__}: {exc}'))

    def submit(self, packet):
        put_latest(self.inputs, packet)

    def clear(self):
        for slot in (self.inputs, self.outputs):
            try:
                while True:
                    slot.get_nowait()
            except queue.Empty:
                pass

    def close(self):
        self.stop_event.set()
        self.clear()
        self.thread.join(timeout=5)
        return not self.thread.is_alive()
