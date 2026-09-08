from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any
from uuid import uuid4

from camera_reference import DeviceDescriptor, resolve_saved_device, saved_device_reference
from .exercises import EXERCISE_IDS, exercise_spec

SCENES = {'rehab': '康复评估与训练', 'activity': '日常活动管理',
          'bedroom_demo': '卧室照护演示', 'safety_demo': '安全报警演示'}
EXERCISES = {key: exercise_spec(key)['label'] for key in EXERCISE_IDS}
SOURCES = {'LIVE_CAMERA': '实时摄像头', 'REPLAY_FILE': '录像回放', 'SYNTHETIC': '合成测试'}
CONTEXTS = {'SELF_USE': '自主使用', 'CONTROLLED_DEMO': '受控演示', 'TEST': '软件测试'}
JOINTS = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder',
          'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist',
          'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
RULE_VERSION = 'rules-0.2.0'
PREPROCESS_VERSION = 'causal-ema-0.1.0'


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_json(value):
    if is_dataclass(value):
        return clean_json(asdict(value))
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, 'item'):
        return clean_json(value.item())
    return value


def dumps(value, **kw):
    return json.dumps(clean_json(value), ensure_ascii=False, allow_nan=False, **kw)


def digest(value):
    return hashlib.sha256(dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Context:
    generation: int
    scene_id: str
    source_ref: str
    source_kind: str
    usage_context: str
    run_id: str = ''
    epoch: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class FramePacket:
    context: Context
    seq: int
    time_s: float | None
    received_monotonic: float
    captured_utc: str
    image: Any
    reported_fps: float | None = None
    received_fps: float | None = None
    time_basis: str = 'monotonic_receive'


@dataclass
class PosePerson:
    track_key: str | None
    bbox: list[float]
    xy: list[list[float]]
    conf: list[float]


@dataclass
class PoseFrame:
    context: Context
    seq: int
    time_s: float | None
    size: tuple[int, int]
    people: list[PosePerson]
    inference_ms: float = 0.0
    schema_id: str = 'coco17-v1'
    coordinate_space: str = 'raw_image_pixels'
    keypoint_order_version: str = 'coco17-anatomical-lr-v1'
    model_manifest_id: str = ''


@dataclass(frozen=True)
class Metric:
    value: float | None
    valid: bool
    reason: str | None = None

    @classmethod
    def of(cls, value):
        if value is None or not math.isfinite(float(value)):
            return cls.missing('missing_or_nonfinite')
        return cls(float(value), True)

    @classmethod
    def missing(cls, reason):
        return cls(None, False, reason)


@dataclass
class Observation:
    time_s: float
    track_key: str | None
    status: str
    metrics: dict[str, Metric]
    center_raw_px: tuple[float, float] | None = None
    bbox_raw_px: list[float] | None = None
    local_pose: list | None = None
    size: tuple[int, int] = (1, 1)
    reasons: list[str] = field(default_factory=list)

    def value(self, key):
        metric = self.metrics.get(key)
        return metric.value if metric and metric.valid else None


class PacketGate:
    def __init__(self):
        self.context = None
        self.last_seq = -1
        self.last_time = None

    def reset(self, context=None):
        self.context, self.last_seq, self.last_time = context, -1, None

    def admit(self, frame):
        if self.context is None or frame.context != self.context or frame.seq <= self.last_seq:
            return False
        t = frame.time_s
        if t is None or not math.isfinite(t) or (self.last_time is not None and t <= self.last_time):
            return False
        self.last_seq, self.last_time = frame.seq, t
        return True
