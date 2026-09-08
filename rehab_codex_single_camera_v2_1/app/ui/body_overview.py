from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView)

from ..assessment import finite_number
from ..exercise_instructions import JOINT_LABELS
from .widgets import MetricCard


def _date(value):
    if not isinstance(value, str):
        return '—'
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone().strftime('%m-%d %H:%M') if stamp.tzinfo else '—'
    except ValueError:
        return '—'


class BodyOverview(QWidget):
    item_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = None
        self.rows = []
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(16)
        stats = QHBoxLayout()
        self.available = MetricCard('可用评估', ' 项')
        self.review = MetricCard('需补测', ' 项')
        self.joints = MetricCard('已记录部位', ' 个')
        self.review.setToolTip('已完成记录，但缺少可用的测量范围。不是动作不合格。')
        for item in (self.available, self.review, self.joints):
            stats.addWidget(item, 1)
        box.addLayout(stats)
        tools = QHBoxLayout()
        title = QLabel('关节评估')
        title.setObjectName('sectionTitle')
        tools.addWidget(title)
        tools.addStretch()
        self.joint = QComboBox()
        for key, label in {'all': '全部部位', **JOINT_LABELS}.items():
            self.joint.addItem(label, key)
        self.joint.currentIndexChanged.connect(self._populate)
        tools.addWidget(self.joint)
        self.show_unassessed = QCheckBox('显示未评估项目')
        self.show_unassessed.toggled.connect(self._populate)
        tools.addWidget(self.show_unassessed)
        box.addLayout(tools)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['动作', '侧别', '记录状态', '观察角度范围', '有效观察', '评估时间（本地）'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection)
        box.addWidget(self.table, 1)
        self.empty = QLabel('还没有评估记录\n选择需要的部位，完成一次评估后会显示在这里。')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName('muted')
        self.empty.setMinimumHeight(140)
        box.addWidget(self.empty, 1)
        self.selection_hint = QLabel('选择一项记录，查看报告或进入训练。')
        self.selection_hint.setObjectName('muted')
        self.selection_hint.setWordWrap(True)
        box.addWidget(self.selection_hint)
        note = QLabel('各行保留各自测量条件。不同机位、模型或起点的角度不能直接解释为康复变化。')
        note.setObjectName('muted')
        note.setWordWrap(True)
        box.addWidget(note)

    def set_loading(self):
        self.profile = None
        self.rows = []
        self.table.setRowCount(0)
        self.table.hide()
        self.empty.setText('正在读取评估记录…')
        self.empty.show()
        self.selection_hint.setText('')
        for item in (self.available, self.review, self.joints):
            item.show_value(None)
        self.item_selected.emit(None)

    def set_profile(self, profile):
        self.profile = profile
        items = profile['items']
        self.available.show_value(sum(i['status'] == 'ASSESSED' for i in items))
        self.review.show_value(sum(bool(i.get('session_id')) and i['status'] != 'ASSESSED' for i in items))
        self.joints.show_value(len({i['joint'] for i in items if i.get('session_id')}))
        self._populate()

    def _populate(self, *args):
        selected = self.current_item()
        selected_key = (selected['exercise_id'], selected['side']) if selected else None
        self.rows = [i for i in (self.profile or {}).get('items', [])
                     if (self.joint.currentData() == 'all' or self.joint.currentData() == i['joint'])
                     and (self.show_unassessed.isChecked() or i.get('session_id'))]
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(self.rows))
        selected_row = None
        for row, item in enumerate(self.rows):
            available = item['status'] == 'ASSESSED'
            status = '可用评估' if available else '需重新评估' if item.get('session_id') else '未评估'
            interval = item.get('motion_range') if available else None
            low = finite_number((interval or {}).get('min_deg'))
            high = finite_number((interval or {}).get('max_deg'))
            angle = f'{low:.1f}° – {high:.1f}°' if low is not None and high is not None else '—'
            ratio = finite_number(item.get('valid_ratio'))
            coverage = f'{ratio*100:.0f}%' if ratio is not None and 0 <= ratio <= 1 else '—'
            values = (item['exercise_label'], '左侧' if item['side'] == 'left' else '右侧',
                      status, angle, coverage, _date(item.get('start_utc')))
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col == 3:
                    cell.setToolTip(item.get('primary_metric_label', '')+'\n'+item.get('measurement_note', ''))
                elif col == 2:
                    cell.setToolTip(item.get('reason') or '可引用此评估；训练目标仍需单独确认。')
                elif col == 5:
                    cell.setToolTip(item.get('start_utc') or '')
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 60)
            if (item['exercise_id'], item['side']) == selected_key:
                selected_row = row
        self.table.setVisible(bool(self.rows))
        self.empty.setVisible(not self.rows)
        self.empty.setText('还没有评估记录\n选择需要的部位，完成一次评估后会显示在这里。'
                           if not any(i.get('session_id') for i in (self.profile or {}).get('items', []))
                           else '这个部位还没有评估记录。')
        if self.rows:
            self.table.selectRow(selected_row if selected_row is not None else 0)
        self.table.blockSignals(False)
        self._selection()

    def current_item(self):
        selected = self.table.selectionModel().selectedRows()
        row = selected[0].row() if selected else -1
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def _selection(self):
        item = self.current_item()
        text = '选择一项记录，查看报告或进入训练。'
        if item:
            text = item['exercise_label']+' · '+('左侧' if item['side'] == 'left' else '右侧')+'：'
            text += '可进入训练，目标需另行确认。' if item['status'] == 'ASSESSED' else '需要先完成或重新评估。'
        self.selection_hint.setText(text)
        self.item_selected.emit(item)
