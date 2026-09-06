from __future__ import annotations

from pathlib import Path

from .domain import DeviceDescriptor, resolve_saved_device


def enumerate_devices(backend):
    from cv2_enumerate_cameras import enumerate_cameras
    return [DeviceDescriptor(str(x.name or ''), str(x.path or ''), int(x.backend), int(x.index),
                             getattr(x, 'vid', None), getattr(x, 'pid', None)) for x in enumerate_cameras(backend)]


class CameraManager:
    def __init__(self, enumerator=None, worker_factory=None):
        self.enumerator = enumerator or enumerate_devices
        if worker_factory is None:
            from .source_worker import SourceWorker
            worker_factory = SourceWorker
        self.worker_factory = worker_factory
        self.worker = None
        self.resolved = None

    def enumerate(self, backend):
        if backend not in (700, 1400):
            raise ValueError('请选择 DSHOW 或 MSMF 后端')
        return self.enumerator(backend)

    def _open(self, source, context, options):
        if self.worker is not None:
            raise RuntimeError('旧采集尚未确认释放，不能打开另一输入')
        self.worker = self.worker_factory(source, context, options or {})
        self.worker.start()

    def open_camera(self, saved, context, options=None):
        if self.worker is not None:
            raise RuntimeError('请先停止并确认旧采集释放')
        current = resolve_saved_device(saved, self.enumerate(saved.get('backend')))
        self.resolved = current
        self._open({'kind': 'LIVE_CAMERA', 'index': current.index, 'backend': current.backend}, context, options)

    def open_replay(self, path, context, options=None):
        file = Path(path).resolve()
        if not file.is_file():
            raise ValueError('请先选择存在的本地视频')
        self.resolved = None
        self._open({'kind': 'REPLAY_FILE', 'path': str(file)}, context, options)

    def change_context(self, context):
        if self.worker is None:
            raise RuntimeError('输入尚未打开')
        self.worker.change_context(context)

    def stop(self):
        if self.worker is not None:
            if not self.worker.stop():
                raise RuntimeError('采集进程未确认退出；新输入保持锁定')
            self.worker = None
