from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QSizePolicy,
)

from ..exercises import EXERCISE_IDS
from ..exercise_instructions import JOINT_LABELS, exercise_instructions
from .body_map import BodyMap


class JointGlyph(QWidget):
    """Navigation glyph, not a motion demonstration or an anatomical measurement."""
    def __init__(self, joint, parent=None):
        super().__init__(parent)
        self.joint = joint
        self.setFixedSize(48, 48)
        self.setAccessibleName(JOINT_LABELS[joint])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#eff4ec'))
        painter.drawRoundedRect(self.rect(), 12, 12)
        paths = {
            'shoulder': [(10, 35), (10, 16), (25, 16), (35, 31), (39, 35)],
            'elbow': [(13, 9), (13, 32), (37, 32)],
            'wrist': [(9, 34), (23, 24), (24, 10), (32, 9), (36, 18), (29, 28), (14, 40)],
            'finger': [(13, 39), (13, 28), (19, 23), (20, 13), (28, 8), (33, 12), (27, 17), (27, 28), (20, 39)],
            'hip': [(12, 10), (13, 22), (25, 23), (31, 38)],
            'knee': [(16, 8), (30, 25), (19, 40)],
            'ankle': [(19, 8), (19, 32), (37, 37), (37, 41), (12, 41), (12, 32)],
            'neck': [(15, 40), (21, 30), (21, 22), (15, 15), (20, 8), (29, 8), (34, 15), (28, 22), (28, 30), (35, 40)],
            'trunk': [(13, 12), (35, 12), (31, 36), (17, 36), (13, 12)],
        }
        pen = QPen(QColor('#66835f'), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in paths[self.joint]]))
        cx, cy = {'shoulder': (25, 16), 'elbow': (13, 32), 'wrist': (24, 25),
                  'finger': (24, 24), 'hip': (25, 23), 'knee': (30, 25), 'ankle': (19, 32),
                  'neck': (24, 28), 'trunk': (24, 25)}[self.joint]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#b8cb85'))
        painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)


class ExerciseCard(QFrame):
    chosen = Signal(str)

    def __init__(self, exercise_id, parent=None):
        super().__init__(parent)
        self.exercise_id = exercise_id
        info = exercise_instructions(exercise_id)
        self.setObjectName('exerciseCard')
        self.setMinimumHeight(150)
        self.setMaximumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 14)
        box.setSpacing(10)
        line = QHBoxLayout()
        category = QLabel(JOINT_LABELS[info['joint']] + ' · ' + info['view_label'])
        category.setObjectName('muted')
        line.addWidget(category)
        line.addStretch()
        box.addLayout(line)
        top = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(4)
        title = QLabel(info['label'])
        title.setObjectName('sectionTitle')
        title.setWordWrap(True)
        text.addWidget(title)
        top.addLayout(text, 1)
        box.addLayout(top)
        box.addStretch()
        footer = QHBoxLayout()
        tag = QLabel('实验性观察' if info['experimental'] else '二维动作观察')
        tag.setObjectName('tag')
        tag.setProperty('experimental', info['experimental'])
        tag.setToolTip(info['boundary'])
        footer.addWidget(tag)
        footer.addStretch()
        self.open_button = QPushButton('选择动作')
        self.open_button.setObjectName('textButton')
        self.open_button.setAccessibleName('选择'+info['label'])
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.clicked.connect(lambda: self.chosen.emit(self.exercise_id))
        footer.addWidget(self.open_button)
        box.addLayout(footer)


class ExerciseCatalog(QWidget):
    exercise_selected = Signal(str)
    checklist_requested = Signal()
    body_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.joint = None
        self.visible_ids = []
        self._columns = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        title = QLabel('今天想评估哪里？')
        title.setObjectName('sectionTitle')
        heading.addWidget(title, 1)
        self.checklist = QPushButton('本轮评估清单')
        self.checklist.clicked.connect(self.checklist_requested.emit)
        heading.addWidget(self.checklist)
        self.body_button = QPushButton('评估结果')
        self.body_button.clicked.connect(self.body_requested.emit)
        heading.addWidget(self.body_button)
        layout.addLayout(heading)
        split = QHBoxLayout()
        split.setSpacing(20)
        body_panel = QFrame()
        body_panel.setObjectName('card')
        body_panel.setMaximumWidth(480)
        body_box = QVBoxLayout(body_panel)
        body_box.setContentsMargins(12, 12, 12, 10)
        self.body_map = BodyMap()
        self.body_map.joint_selected.connect(self.select_joint)
        body_box.addWidget(self.body_map, 1)
        hint = QLabel('点击图标或名称')
        hint.setObjectName('muted')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_box.addWidget(hint)
        split.addWidget(body_panel, 5)
        action_panel = QWidget()
        action_box = QVBoxLayout(action_panel)
        action_box.setContentsMargins(0, 0, 0, 0)
        action_box.setSpacing(12)
        action_heading = QHBoxLayout()
        self.part_title = QLabel('选择身体部位')
        self.part_title.setObjectName('sectionTitle')
        action_heading.addWidget(self.part_title, 1)
        all_button = QPushButton('全部动作')
        all_button.setObjectName('filter')
        all_button.setCheckable(True)
        all_button.clicked.connect(lambda: self.select_joint('all'))
        action_heading.addWidget(all_button)
        self.group_buttons = {'all': all_button, **self.body_map.labels}
        action_box.addLayout(action_heading)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索动作 / 关节')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('搜索评估动作')
        self.search.textChanged.connect(self._filter)
        tools.addWidget(self.search, 1)
        self.results = QLabel()
        self.results.setObjectName('muted')
        tools.addWidget(self.results)
        action_box.addLayout(tools)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName('scrollContent')
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 8, 0)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards = {}
        for eid in EXERCISE_IDS:
            item = ExerciseCard(eid)
            item.chosen.connect(self.exercise_selected)
            self.cards[eid] = item
        self.scroll.setWidget(self.content)
        action_box.addWidget(self.scroll, 1)
        self.empty = QLabel()
        self.empty.setObjectName('muted')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(100)
        action_box.addWidget(self.empty, 1)
        split.addWidget(action_panel, 6)
        layout.addLayout(split, 1)
        note = QLabel('按需选择部位 · 二维观察不替代专业评估')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self._filter()

    def select_joint(self, joint):
        if joint not in self.group_buttons:
            raise ValueError('未知部位')
        self.joint = joint
        for key, button in self.group_buttons.items():
            button.setChecked(key == joint)
        self.body_map.select_joint(joint)
        self.search.clear()
        self._filter()

    def _filter(self):
        words = self.search.text().casefold().split()
        self.visible_ids = []
        ordered_ids = [eid for joint in JOINT_LABELS for eid in EXERCISE_IDS
                       if exercise_instructions(eid)['joint'] == joint]
        for eid in ordered_ids:
            info = exercise_instructions(eid)
            if (self.joint == 'all' or info['joint'] == self.joint or (self.joint is None and words)) and all(
                    word in (info['search_terms']+' '+info['move']).casefold() for word in words):
                self.visible_ids.append(eid)
        self.results.setText(f'{len(self.visible_ids)} 项动作')
        self.results.setVisible(self.joint is not None or bool(words))
        self.part_title.setText(JOINT_LABELS.get(self.joint, '全部动作' if self.joint == 'all' else
                                               '搜索结果' if words else '选择身体部位'))
        self.empty.setText('先点击左侧的一个部位' if self.joint is None and not words else '没有匹配的动作，换个关键词试试')
        self.empty.setWordWrap(True)
        self.empty.setVisible(not self.visible_ids)
        self.scroll.setVisible(bool(self.visible_ids))
        self._relayout()
        self.scroll.verticalScrollBar().setValue(0)

    def _relayout(self):
        self._columns = 2 if self.scroll.width() >= 620 else 1
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
        for col in range(3):
            self.grid.setColumnStretch(col, 1 if col < self._columns else 0)
        for index, eid in enumerate(self.visible_ids):
            item = self.cards[eid]
            self.grid.addWidget(item, index // self._columns, index % self._columns)
            item.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.scroll.width() >= 620 else 1
        if columns != self._columns:
            self._relayout()
