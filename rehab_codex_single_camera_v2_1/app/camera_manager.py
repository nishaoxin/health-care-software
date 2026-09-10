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
        self.resolved_views = {}

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
        self.resolved_views = {}
        self._open({'kind': 'LIVE_CAMERA', 'index': current.index, 'backend': current.backend}, context, options)

    def open_pair(self, devices, primary_view, context, options=None):
        from .dual_camera import checked_devices, other_view, PairedSourceWorker
        if self.worker is not None:
            raise RuntimeError('请先停止并确认旧采集释放')
        other_view(primary_view)
        saved = checked_devices(devices)
        # Resolve BOTH before either process can open a capture. No partial open
        # when a saved path disappears, becomes ambiguous or changes backend.
        enumerated = self.enumerate(saved['frontal']['backend'])
        current = {view: resolve_saved_device(ref, enumerated) for view, ref in saved.items()}
        if current['frontal'].index == current['sagittal'].index:
            raise ValueError('两个机位解析到同一设备，请重新选择')
        self.resolved_views = current
        self.resolved = current[primary_view]
        self.worker = PairedSourceWorker(current, context, primary_view, options, self.worker_factory)
        try:
            self.worker.start()
        except Exception:
            self.stop()  # A failed rollback deliberately retains the owner lock.
            raise

    def open_replay(self, path, context, options=None):
        file = Path(path).resolve()
        if not file.is_file():
            raise ValueError('请先选择存在的本地视频')
        self.resolved = None
        self.resolved_views = {}
        self._open({'kind': 'REPLAY_FILE', 'path': str(file)}, context, options)

    def change_context(self, context):
        if self.worker is None:
            raise RuntimeError('输入尚未打开')
        try:
            self.worker.change_context(context)
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self.worker is not None:
            if not self.worker.stop():
                raise RuntimeError('采集进程未确认退出；新输入保持锁定')
            self.worker = None
