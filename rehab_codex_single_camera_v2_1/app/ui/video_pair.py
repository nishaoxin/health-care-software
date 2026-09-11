"""Responsive view labels and independently sourced images; no capture or inference."""
import math
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QBoxLayout

from ..dual_camera import VIEWS, other_view, validate_pair
from ..dual_view import AUXILIARY_METRICS
from .widgets import VideoCanvas


class VideoPairPanel(QWidget):
    def __init__(self, primary_canvas=None, *, compact=False):
        super().__init__()
        self.primary_canvas = primary_canvas or VideoCanvas()
        self.base_minimum = self.primary_canvas.minimumSize()
        self.compact = compact
        self.secondary_canvas = VideoCanvas()
        self.secondary_canvas.setMinimumSize(160, 130) if compact else self.secondary_canvas.setMinimumSize(210, 150)
        self.secondary_canvas.subcaption = '两路都取得新画面后显示'
        self.dual_enabled = False
        self.primary_view = 'frontal'
        self.last_received = None
        self.live = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.images = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.images.setSpacing(12)
        self.primary_host, self.primary_title, self.primary_info = self._image_host(self.primary_canvas)
        self.secondary_host, self.secondary_title, self.secondary_info = self._image_host(self.secondary_canvas)
        self.images.addWidget(self.primary_host, 1)
        self.images.addWidget(self.secondary_host, 1)
        box.addLayout(self.images, 1)
        self.auxiliary_values = self._label()
        box.addWidget(self.auxiliary_values)
        self.pair_info = self._label()
        box.addWidget(self.pair_info)
        self.configure(False)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._check_freshness)

    @staticmethod
    def _label():
        label = QLabel()
        label.setObjectName('muted')
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _image_host(self, canvas):
        host = QWidget()
        box = QVBoxLayout(host)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        title, info = self._label(), self._label()
        box.addWidget(title)
        box.addWidget(canvas, 1)
        box.addWidget(info)
        return host, title, info

    def configure(self, enabled, primary_view='frontal'):
        self.dual_enabled = bool(enabled)
        self.primary_view = primary_view if primary_view in VIEWS else 'frontal'
        self.primary_title.setText(VIEWS[self.primary_view]+' · 动作测量')
        secondary = other_view(self.primary_view)
        self.secondary_title.setText(VIEWS[secondary]+' · 辅助观察')
        self.secondary_canvas.caption = VIEWS[secondary]+'摄像头未打开'
        for widget in (self.primary_title, self.primary_info, self.secondary_host, self.pair_info, self.auxiliary_values):
            widget.setVisible(self.dual_enabled)
        self.primary_info.setVisible(self.dual_enabled and not self.compact)
        self.secondary_info.setVisible(not self.compact)
        self.auxiliary_values.setVisible(self.dual_enabled and not self.compact)
        if enabled:
            self.primary_canvas.setMinimumSize(160, 130) if self.compact else self.primary_canvas.setMinimumSize(210, 150)
        else:
            self.primary_canvas.setMinimumSize(self.base_minimum)
        if not enabled:
            self.secondary_canvas.set_frame(None)
            self.last_received = None
        self._layout_direction()

    def _layout_direction(self):
        horizontal = self.dual_enabled and self.width() >= (350 if self.compact else 450)
        self.images.setDirection(QBoxLayout.Direction.LeftToRight if horizontal else QBoxLayout.Direction.TopToBottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_direction()

    def set_mirror(self, value):
        for canvas in (self.primary_canvas, self.secondary_canvas):
            canvas.mirror = value
            canvas.update()

    def clear(self):
        self.primary_canvas.set_frame(None)
        self.secondary_canvas.set_frame(None)
        self.primary_info.clear()
        self.secondary_info.clear()
        self.auxiliary_values.clear()
        self.pair_info.clear()
        self.last_received = None

    @staticmethod
    def _frame_text(packet, pose=None):
        w, h = packet.image.shape[1::-1]
        fps = packet.received_fps
        return f'{w} × {h} · '+(f'{fps:.1f} 帧/秒' if isinstance(fps, (int, float)) and math.isfinite(fps) else '帧率统计中')

    def render(self, data, *, mirror=True, enabled=None, primary_view=None):
        self.central_guidance = bool(data.get('guidance'))
        packet, pose = data.get('packet'), data.get('pose')
        raw_test = bool(data.get('camera_test'))
        if raw_test:
            pose = None
        dual = data.get('dual_camera') or {}
        enabled = bool(dual or packet and packet.paired_frame) if enabled is None else enabled
        self.configure(enabled, primary_view or dual.get('primary_view') or getattr(packet, 'camera_view', None) or self.primary_view)
        if raw_test:
            self.primary_title.setText(VIEWS[self.primary_view]+' · 画面测试')
            self.secondary_title.setText(VIEWS[other_view(self.primary_view)]+' · 画面测试')
        self.set_mirror(mirror)
        active = data.get('state') in ('PREVIEW', 'ONLINE') and not data.get('error')
        if packet is None or packet.context != data.get('context') or not active:
            self.clear()
            return False
        self.live = packet.context.source_kind == 'LIVE_CAMERA'
        if not enabled:
            self.primary_canvas.set_frame(packet, pose)
            return True
        try:
            auxiliary_packet = validate_pair(packet, self.primary_view, now=time.monotonic() if self.live else None)
        except ValueError:
            self.clear()
            if not self.central_guidance:
                self.pair_info.setText('两路画面未就绪或更新超时，请暂停动作')
            return False
        self.primary_canvas.set_frame(packet, pose)
        auxiliary_pose = pose.paired_pose if pose else None
        self.secondary_canvas.set_frame(auxiliary_packet, auxiliary_pose)
        self.last_received = min(packet.received_monotonic, auxiliary_packet.received_monotonic)
        self.primary_info.setText(self._frame_text(packet, pose))
        self.secondary_info.setText(self._frame_text(auxiliary_packet, auxiliary_pose))
        self.pair_info.setText(f"两路接收差 {packet.pairing['receive_delta_s']*1000:.0f} 毫秒 · 接收时间配对")
        values = []
        for key, metric in ({} if raw_test else dual.get('auxiliary_metrics') or {}).items():
            definition = AUXILIARY_METRICS.get(key)
            if not definition or definition['view'] != other_view(self.primary_view):
                continue
            value = metric.get('value') if metric.get('valid') else None
            formatted = f'{value:.1f}°' if isinstance(value, (int, float)) and math.isfinite(value) else '—'
            values.append(definition['label']+' '+formatted)
        self.auxiliary_values.setText('；'.join(values))
        return True

    def _check_freshness(self):
        if self.dual_enabled and self.live and self.last_received is not None and time.monotonic()-self.last_received > 3:
            self.clear()
            if not getattr(self, 'central_guidance', False):
                self.pair_info.setText('双摄画面更新超时，请暂停动作')

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
