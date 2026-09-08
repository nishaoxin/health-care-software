"""Minimal native controls for selecting and resuming an assessment round."""
import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView, QInputDialog, QMessageBox)

from ..domain import SOURCES, CONTEXTS
from ..exercises import EXERCISE_IDS, exercise_spec


class AssessmentBatchDialog(QDialog):
    create_requested = Signal(list)
    change_requested = Signal(dict)
    assessment_requested = Signal(dict, dict)
    report_requested = Signal(str)

    def __init__(self, scope, parent=None):
        super().__init__(parent)
        self.scope, self.batch, self.busy = copy.deepcopy(scope), None, False
        self.setWindowTitle('本轮评估清单')
        self.setModal(True)
        self.resize(780, 600)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        layout.addWidget(QLabel(SOURCES[scope['source_kind']]+' / '+CONTEXTS[scope['usage_context']]))
        self.choices = QListWidget()
        for eid in EXERCISE_IDS:
            for side, label in (('left', '左侧'), ('right', '右侧')):
                item = QListWidgetItem(exercise_spec(eid)['label']+' · '+label)
                item.setData(Qt.ItemDataRole.UserRole, {'exercise_id': eid, 'side': side})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.choices.addItem(item)
        layout.addWidget(self.choices, 1)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['项目', '侧别', '状态', '本轮投影范围', '跳过原因'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._buttons)
        layout.addWidget(self.table, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.error)
        row = QHBoxLayout()
        self.create = QPushButton('保存本轮清单')
        self.create.clicked.connect(self._create)
        self.run = QPushButton('评估所选项目')
        self.run.clicked.connect(self._run_item)
        self.skip = QPushButton('跳过所选项目')
        self.skip.clicked.connect(self._skip)
        self.report = QPushButton('查看报告')
        self.report.clicked.connect(self._report)
        self.finish_round = QPushButton('结束本轮')
        self.finish_round.clicked.connect(self._finish)
        for button in (self.create, self.run, self.skip, self.report, self.finish_round):
            row.addWidget(button)
        layout.addLayout(row)
        self.set_batch(None)

    def selected(self):
        row = self.table.currentRow()
        return self.batch['items'][row] if self.batch and 0 <= row < len(self.batch['items']) else None

    def set_batch(self, batch):
        self.batch = copy.deepcopy(batch)
        self.error.clear()
        self.choices.setVisible(batch is None)
        self.table.setVisible(batch is not None)
        self.table.setRowCount(0)
        if batch is None:
            self.summary.setText('只勾选本轮需要评估的动作和侧别。可分次完成，不要求测完全部项目。')
        else:
            self.summary.setText(('本轮已结束。' if batch['status'] == 'CLOSED' else '')+
                f"已评估 {batch['assessed_count']} / {len(batch['items'])} 项；需补测 {batch['review_count']} 项；"
                f"已跳过 {batch['skipped_count']} 项。只计本轮记录，旧评估不会自动填入。")
            for entry in batch['items']:
                row = self.table.rowCount()
                self.table.insertRow(row)
                motion = (entry.get('measurement') or {}).get('motion_range')
                value = f"{motion['min_deg']:.1f}° – {motion['max_deg']:.1f}°" if motion else '—'
                for col, text in enumerate((entry['label'], '左侧' if entry['side'] == 'left' else '右侧',
                                            entry['status_label'], value, entry['skip_reason'] or '')):
                    self.table.setItem(row, col, QTableWidgetItem(text))
            pending = next((i for i,e in enumerate(batch['items']) if e['status'] in ('PENDING', 'REVIEW')), 0)
            self.table.selectRow(pending)
        self._buttons()

    def set_busy(self, busy):
        self.busy = busy
        self._buttons()

    def _buttons(self):
        if not hasattr(self, 'create'):
            return
        item = self.selected()
        active = bool(self.batch and self.batch['status'] == 'ACTIVE')
        self.create.setVisible(not active)
        self.create.setText('新建下一轮' if self.batch else '保存本轮清单')
        self.create.setEnabled(not self.busy)
        self.choices.setEnabled(not self.busy)
        self.run.setEnabled(not self.busy and active and bool(item) and item['status'] not in ('SKIPPED', 'IN_PROGRESS'))
        self.skip.setEnabled(not self.busy and active and bool(item) and item['status'] in ('PENDING', 'REVIEW', 'SKIPPED'))
        self.skip.setText('恢复为待测' if item and item['status'] == 'SKIPPED' else '跳过所选项目')
        self.report.setEnabled(not self.busy and bool(item and item['session_id']) and item['status'] != 'IN_PROGRESS')
        self.finish_round.setEnabled(not self.busy and active)

    def _create(self):
        if self.batch:
            self.set_batch(None)
            return
        chosen = [self.choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.choices.count())
                  if self.choices.item(i).checkState() == Qt.CheckState.Checked]
        if not chosen:
            self.error.setText('请至少勾选一个项目。')
            return
        self.create_requested.emit(chosen)

    def _run_item(self):
        item = self.selected()
        if item and self.run.isEnabled():
            self.assessment_requested.emit(self.batch, item)

    def _report(self):
        item = self.selected()
        if item and self.report.isEnabled():
            self.report_requested.emit(item['session_id'])

    def _change(self, action, reason=None):
        self.change_requested.emit({'id': self.batch['id'], 'expected_revision': self.batch['revision'],
                                   'action': action, 'entry_key': self.selected()['key'] if self.selected() else None,
                                   'reason': reason})

    def _skip(self):
        item = self.selected()
        if not item or not self.skip.isEnabled():
            return
        if item['status'] == 'SKIPPED':
            self._change('restore')
        else:
            reason, ok = QInputDialog.getText(self, '跳过本项目', '填写原因（未完成不会记为已评估）：')
            if ok:
                self._change('skip', reason)

    def _finish(self):
        if QMessageBox.question(self, '结束本轮', '未评估和需补测项目会保留原状态，已保存报告不会删除。确定结束本轮？') == QMessageBox.StandardButton.Yes:
            self._change('close')

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
