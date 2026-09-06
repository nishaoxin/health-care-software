"""Pure input-contract references. No camera, GUI, model or clinical inference.

These helpers are a tested starting point, not a complete CameraManager.
A production manager must also coordinate stop/join/release and persistence.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from collections.abc import Sequence


class DeviceSelectionRequired(RuntimeError):
    """The caller must obtain an explicit new selection; never open index 0."""


@dataclass(frozen=True)
class DeviceDescriptor:
    name: str
    path: str
    backend: int
    index: int
    vid: int | None = None
    pid: int | None = None


def resolve_saved_device(saved: dict, devices: Sequence[DeviceDescriptor]) -> DeviceDescriptor:
    """Resolve only one matching nonempty path in the same explicit backend.

    Index, name and VID/PID are not persistent unique identities. The matching
    candidate still requires a user preview before a clinical/task session.
    """
    path = saved.get('path')
    backend = saved.get('backend')
    if not isinstance(path, str) or not path.strip() or not isinstance(backend, int):
        raise DeviceSelectionRequired('Saved camera has no usable path/backend; select it again.')
    matched = [d for d in devices if d.path == path and d.backend == backend]
    if len(matched) != 1:
        raise DeviceSelectionRequired('Saved camera is missing or ambiguous; no automatic fallback.')
    return matched[0]


def saved_device_reference(device: DeviceDescriptor) -> dict:
    """Local settings only. Do not publish device paths in public logs."""
    return {'name': device.name, 'path': device.path, 'backend': device.backend,
            'vid': device.vid, 'pid': device.pid}


def display_to_raw_normalized(
    x: float, y: float, source_width: int, source_height: int,
    viewport_width: int, viewport_height: int, *, mirror: bool = False,
) -> tuple[float, float] | None:
    """Undo centered aspect-fit letterboxing, then horizontal display mirroring.

    Continuous image coordinates. This helper does not implement rotation/crop;
    reject those transforms or implement their inverse separately in production.
    """
    if min(source_width, source_height, viewport_width, viewport_height) <= 0:
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    scale = min(viewport_width / source_width, viewport_height / source_height)
    dw, dh = source_width * scale, source_height * scale
    left, top = (viewport_width - dw) / 2, (viewport_height - dh) / 2
    if not (left <= x <= left + dw and top <= y <= top + dh):
        return None
    u, v = (x - left) / dw, (y - top) / dh
    return (1.0 - u if mirror else u, v)


@dataclass(frozen=True)
class RunContext:
    generation: int
    scene_id: str
    source_ref: str
    source_kind: str


class RunGate:
    """Reject late packets, preview packets, and duplicate sequence numbers.

    This is only a consumer-side guard. Calling invalidate does NOT stop or
    release hardware. CameraManager must obtain worker shutdown confirmation.
    """
    def __init__(self) -> None:
        self.generation = 0
        self.context: RunContext | None = None
        self.state = 'STOPPED'
        self.last_seq = -1

    def invalidate(self) -> None:
        self.generation += 1
        self.context = None
        self.state = 'STOPPED'
        self.last_seq = -1

    def enter_preview(self, scene_id: str, source_ref: str, source_kind: str) -> RunContext:
        if self.state != 'STOPPED':
            raise RuntimeError('Stop and confirm hardware release before replacing preview.')
        if source_kind not in {'LIVE_CAMERA', 'REPLAY_FILE', 'SYNTHETIC'}:
            raise ValueError('Unknown source kind.')
        if not scene_id or not source_ref:
            raise ValueError('Scene and source must be explicit.')
        self.generation += 1
        self.context = RunContext(self.generation, scene_id, source_ref, source_kind)
        self.state = 'PREVIEW'
        self.last_seq = -1
        return self.context

    def start(self, *, setup_confirmed: bool) -> RunContext:
        if self.state != 'PREVIEW' or self.context is None:
            raise RuntimeError('Open a fresh preview first.')
        if not setup_confirmed:
            raise RuntimeError('Setup confirmation is required.')
        previous = self.context
        self.generation += 1
        self.context = RunContext(self.generation, previous.scene_id, previous.source_ref, previous.source_kind)
        self.state = 'RUNNING'
        self.last_seq = -1
        return self.context

    def admit(self, context: RunContext, seq: int) -> bool:
        if self.state != 'RUNNING' or context != self.context:
            return False
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0 or seq <= self.last_seq:
            return False
        self.last_seq = seq
        return True
