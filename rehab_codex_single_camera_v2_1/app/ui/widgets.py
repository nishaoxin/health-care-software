from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QImage
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel, QToolButton

from ..geometry import display_to_raw_normalized
from ..landmark_schemas import skeleton_edges

SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
ROI_LABELS = {'chair': '座椅', 'bed': '床', 'bed_edge': '床边', 'exit': '出口',
              'floor_watch': '地面关注区', 'sofa': '沙发排除区'}


class NoticeLabel(QLabel):
    def flash(self, text, milliseconds=4000):
        if not hasattr(self, '_expiry'):
            self._expiry = QTimer(self)
            self._expiry.setSingleShot(True)
            self._expiry.timeout.connect(lambda: self.setText(''))
        if text == self.text() and self._expiry.isActive():
            return
        self.setText(text)
        self._expiry.start(milliseconds)

    def setText(self, text):
        if hasattr(self, '_expiry'):
            self._expiry.stop()
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self):
        self.setText('')


class Disclosure(QWidget):
    """Keyboard-accessible optional details without removing safety controls."""
    def __init__(self, title, parent=None, *, expanded=False):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setChecked(expanded)
        layout.addWidget(self.toggle)
        self.content = QWidget()
        self.box = QVBoxLayout(self.content)
        self.box.setContentsMargins(6, 2, 6, 8)
        self.box.setSpacing(9)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._set_expanded)
        self._set_expanded(expanded)

    def _set_expanded(self, expanded):
        self.content.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)


class VideoCanvas(QWidget):
    roi_changed = Signal(str, list)

    def __init__(self):
        super().__init__()
        self.setObjectName('videoCanvas')
        self.setMinimumSize(360, 200)
        self.image = None
        self.pose = None
        self.mirror = False
        self.rois = {}
        self.edit_roi = None
        self.drag_start = self.drag_end = None
        self.caption = '摄像头尚未打开'
        self.subcaption = '选择摄像头，点击“打开预览”'

    def set_frame(self, packet, pose=None):
        if packet is None:
            self.image = self.pose = None
        else:
            frame = packet.image
            h, w, _ = frame.shape
            self.image = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
            self.pose = pose
        self.update()

    def image_rect(self):
        if self.image is None:
            return QRectF(self.rect())
        scale = min(self.width()/self.image.width(), self.height()/self.image.height())
        w, h = self.image.width()*scale, self.image.height()*scale
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)

    def map_raw(self, x, y):
        rect = self.image_rect()
        return QPointF(rect.left()+rect.width()*(1-x if self.mirror else x), rect.top()+rect.height()*y)

    def to_raw(self, pos):
        if self.image is None:
            return None
        return display_to_raw_normalized(pos.x(), pos.y(), self.image.width(), self.image.height(),
                                         self.width(), self.height(), mirror=self.mirror)

    def mousePressEvent(self, event):
        if self.edit_roi and event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = self.to_raw(event.position())
            self.drag_end = self.drag_start

    def mouseMoveEvent(self, event):
        if self.drag_start:
            self.drag_end = self.to_raw(event.position()) or self.drag_end
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_start and self.drag_end and self.edit_roi:
            x1, y1 = self.drag_start
            x2, y2 = self.drag_end
            roi = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            if roi[2]-roi[0] >= .02 and roi[3]-roi[1] >= .02:
                self.rois[self.edit_roi] = roi
                self.roi_changed.emit(self.edit_roi, roi)
        self.drag_start = self.drag_end = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#292236'))
        p.drawRoundedRect(self.rect(), 12, 12)
        if self.image is None:
            cx, cy = self.width()/2, self.height()*.35
            radius = min(64, self.height()*.22)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor('#4b3c5c'), 1))
            for radius in (radius*.72, radius):
                p.drawEllipse(QPointF(cx, cy), radius, radius)
            pen = QPen(QColor('#baabd0'), 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawRoundedRect(QRectF(cx-24, cy-15, 40, 30), 6, 6)
            p.drawLine(QPointF(cx+16, cy-7), QPointF(cx+29, cy-14))
            p.drawLine(QPointF(cx+29, cy-14), QPointF(cx+29, cy+14))
            p.drawLine(QPointF(cx+29, cy+14), QPointF(cx+16, cy+7))
            p.setFont(QFont('Microsoft YaHei UI', 13, QFont.Weight.DemiBold))
            p.setPen(QColor('#edf5f1'))
            p.drawText(QRectF(20, self.height()*.64, self.width()-40, 28), Qt.AlignmentFlag.AlignCenter, self.caption)
            p.setFont(QFont('Microsoft YaHei UI', 10))
            p.setPen(QColor('#b8abc9'))
            p.drawText(QRectF(20, self.height()*.80, self.width()-40, self.height()*.18), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.subcaption)
        else:
            rect = self.image_rect()
            # Reflect only the painter, not the raw frame or anatomical labels.
            p.save()
            if self.mirror:
                p.translate(rect.center().x()*2, 0)
                p.scale(-1, 1)
            p.drawImage(rect, self.image)
            p.restore()
            if self.pose:
                w, h = self.pose.size
                for person in self.pose.people:
                    p.setPen(QPen(QColor('#a6ffe0'), 3))
                    def drawable(i):
                        if i >= len(person.xy) or i >= len(person.conf):
                            return False
                        xy, confidence = person.xy[i], person.conf[i]
                        return (len(xy) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in xy)
                                and 0 < xy[0] < w and 0 < xy[1] < h and (confidence is None or confidence >= .5))
                    for a, b in skeleton_edges(self.pose.schema_id):
                        if drawable(a) and drawable(b):
                            p.drawLine(self.map_raw(person.xy[a][0]/w, person.xy[a][1]/h), self.map_raw(person.xy[b][0]/w, person.xy[b][1]/h))
                    p.setBrush(QColor('#e9fff4'))
                    for i, (x, y) in enumerate(person.xy):
                        if drawable(i):
                            p.setBrush(QColor('#ffc77d' if person.conf[i] is None else '#e9fff4'))
                            p.drawEllipse(self.map_raw(x/w, y/h), 3, 3)
            for name, roi in self.rois.items():
                a, b = self.map_raw(roi[0], roi[1]), self.map_raw(roi[2], roi[3])
                region = QRectF(a, b).normalized()
                p.setBrush(QColor(202, 223, 131, 28))
                p.setPen(QPen(QColor('#d8eca4'), 2, Qt.PenStyle.DashLine))
                p.drawRect(region)
                p.setFont(QFont('Microsoft YaHei UI', 10))
                p.drawText(region.adjusted(8, 6, -4, -4), Qt.AlignmentFlag.AlignTop, ROI_LABELS.get(name, name))
            if self.drag_start and self.drag_end:
                p.setPen(QPen(QColor('#ffffff'), 2))
                p.drawRect(QRectF(self.map_raw(*self.drag_start), self.map_raw(*self.drag_end)).normalized())
        p.end()


class MetricCard(QFrame):
    def __init__(self, label, unit=''):
        super().__init__()
        self.setObjectName('metricCard')
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 10, 16, 10)
        box.setSpacing(4)
        self.caption = QLabel(label)
        self.caption.setObjectName('muted')
        self.caption.setWordWrap(True)
        self.value = QLabel('—')
        self.value.setObjectName('metricValue')
        self.unit = unit
        box.addWidget(self.caption)
        box.addWidget(self.value)

    def show_value(self, value):
        self.value.setText('—' if value is None else f'{value}{self.unit}')

    def configure(self, label, unit=''):
        self.caption.setText(label)
        self.caption.setToolTip(label)
        self.unit = unit
        self.show_value(None)
