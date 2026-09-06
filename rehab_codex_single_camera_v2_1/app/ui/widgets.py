from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QImage
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel

from ..geometry import display_to_raw_normalized

SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
ROI_LABELS = {'chair': '座椅', 'bed': '床', 'bed_edge': '床边', 'exit': '出口',
              'floor_watch': '地面关注区', 'sofa': '沙发排除区'}


class VideoCanvas(QWidget):
    roi_changed = Signal(str, list)

    def __init__(self):
        super().__init__()
        self.setObjectName('videoCanvas')
        self.setMinimumSize(450, 280)
        self.image = None
        self.pose = None
        self.mirror = False
        self.rois = {}
        self.edit_roi = None
        self.drag_start = self.drag_end = None
        self.caption = '摄像头尚未打开'
        self.subcaption = '选择一个视频来源，预览并确认机位后开始'

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
        p.fillRect(self.rect(), QColor('#142e33'))
        if self.image is None:
            cx, cy = self.width()/2, self.height()/2-40
            p.setPen(QPen(QColor('#31575a'), 1))
            for radius in (66, 94):
                p.drawEllipse(QPointF(cx, cy), radius, radius)
            pen = QPen(QColor('#99c6b9'), 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawRoundedRect(QRectF(cx-30, cy-20, 52, 40), 8, 8)
            p.drawLine(QPointF(cx+22, cy-9), QPointF(cx+38, cy-18))
            p.drawLine(QPointF(cx+38, cy-18), QPointF(cx+38, cy+18))
            p.drawLine(QPointF(cx+38, cy+18), QPointF(cx+22, cy+9))
            p.setFont(QFont('Microsoft YaHei UI', 15, QFont.Weight.DemiBold))
            p.setPen(QColor('#edf5f1'))
            p.drawText(QRectF(20, cy+105, self.width()-40, 32), Qt.AlignmentFlag.AlignCenter, self.caption)
            p.setFont(QFont('Microsoft YaHei UI', 10))
            p.setPen(QColor('#aac0bc'))
            p.drawText(QRectF(20, cy+144, self.width()-40, 48), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.subcaption)
        else:
            rect = self.image_rect()
            p.drawImage(rect, self.image.mirrored(True, False) if self.mirror else self.image)
            if self.pose:
                w, h = self.pose.size
                for person in self.pose.people:
                    p.setPen(QPen(QColor('#a6ffe0'), 3))
                    for a, b in SKELETON:
                        if person.conf[a] >= .5 and person.conf[b] >= .5:
                            p.drawLine(self.map_raw(person.xy[a][0]/w, person.xy[a][1]/h), self.map_raw(person.xy[b][0]/w, person.xy[b][1]/h))
                    p.setBrush(QColor('#e9fff4'))
                    for i, (x, y) in enumerate(person.xy):
                        if person.conf[i] >= .5 and 0 < x < w and 0 < y < h:
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
        box.setContentsMargins(18, 12, 18, 12)
        self.caption = QLabel(label)
        self.caption.setObjectName('muted')
        self.value = QLabel('—')
        self.value.setObjectName('metricValue')
        self.unit = unit
        box.addWidget(self.caption)
        box.addWidget(self.value)

    def show_value(self, value):
        self.value.setText('—' if value is None else f'{value}{self.unit}')

    def configure(self, label, unit=''):
        self.caption.setText(label)
        self.unit = unit
        self.show_value(None)
