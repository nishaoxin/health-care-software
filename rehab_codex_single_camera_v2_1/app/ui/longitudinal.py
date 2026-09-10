"""Read-only native record comparison with explicit gaps and source scope."""
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QTextBrowser, QFileDialog, QSplitter)

from ..domain import SOURCES, CONTEXTS
from ..longitudinal import METRICS, DATA_LABELS, COMPARISON_LABELS, CONDITION_LABELS, plot_series
from ..reports import fmt


class HistoryPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history, self.metric_key = None, 'range_deg'
        self.setMinimumHeight(190)
        self.setAccessibleName('相同记录条件下的观测数值曲线')

    def set_history(self, history, metric):
        self.history, self.metric_key = history, metric
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#ffffff'))
        p.setPen(QColor('#534266'))
        p.drawText(14, 22, METRICS[self.metric_key]+' · 横轴为按日期排序的记录序号')
        segments = plot_series(self.history, self.metric_key) if self.history else []
        if not segments:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '没有满足比较条件的有效数据点；请查看下方原因。')
            return
        values = [value for segment in segments for _, value in segment]
        low, high = min(0., min(values)), max(values)
        span = max(1., high-low)
        high += span*.1
        left, top, width, height = 60., 36., max(1., self.width()-90.), max(1., self.height()-72.)
        count = len(self.history['rows'])
        for index in range(4):
            y = top+height*index/3
            p.setPen(QColor('#e3ddeb'))
            p.drawLine(QPointF(left, y), QPointF(left+width, y))
            p.setPen(QColor('#675675'))
            p.drawText(4, round(y+4), f'{high-(high-low)*index/3:.1f}')
        for segment in segments:
            previous = None
            for index, value in segment:
                point = QPointF(left+width*(index/max(1, count-1)), top+height*(high-value)/(high-low))
                p.setPen(QPen(QColor('#7044d5'), 2.))
                if previous is not None:
                    p.drawLine(previous, point)
                p.setBrush(QColor('#7044d5'))
                p.drawEllipse(point, 4., 4.)
                previous = point
        p.setPen(QColor('#675675'))
        p.drawText(round(left), self.height()-10, '1')
        if count > 1:
            p.drawText(round(left+width-20), self.height()-10, str(count))


class LongitudinalDialog(QDialog):
    anchor_requested = Signal(str, str)
    report_requested = Signal(str)
    export_requested = Signal(str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('纵向记录 · 条件核对')
        self.resize(1180, 820)
        self.setMinimumSize(880, 650)
        self.history = None
        self.request_id = None
        box = QVBoxLayout(self)
        self.heading = QLabel('正在读取历史记录…')
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        self.heading.setObjectName('sectionTitle')
        box.addWidget(self.heading)
        note = QLabel('曲线仅连接已结束、有完整动作、日期明确且记录条件一致的相邻记录。缺测、失败和条件变化会断开；所有记录保留在表中。')
        note.setWordWrap(True)
        box.addWidget(note)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('比较基准'))
        self.anchor = QComboBox()
        self.anchor.setMinimumWidth(230)
        self.anchor.currentIndexChanged.connect(self._anchor_changed)
        controls.addWidget(self.anchor, 1)
        controls.addWidget(QLabel('查看指标'))
        self.metric_choice = QComboBox()
        for key, label in METRICS.items():
            self.metric_choice.addItem(label, key)
        self.metric_choice.currentIndexChanged.connect(self._metric_changed)
        controls.addWidget(self.metric_choice)
        box.addLayout(controls)
        split = QSplitter(Qt.Orientation.Vertical)
        self.plot = HistoryPlot()
        split.addWidget(self.plot)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['序号 / 开始 UTC', '记录状态', '条件核对', '完整次数', '当前指标', '有效观察', '时间样本数'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((215, 165, 150, 90, 110, 90, 110)):
            self.table.setColumnWidth(index, width)
        self.table.itemSelectionChanged.connect(self._details)
        split.addWidget(self.table)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        split.addWidget(self.details)
        split.setSizes([210, 240, 140])
        box.addWidget(split, 1)
        self.notice = QLabel('')
        self.notice.setWordWrap(True)
        box.addWidget(self.notice)
        footer = QHBoxLayout()
        self.open_report = QPushButton('打开所选原报告')
        self.open_report.clicked.connect(self._open_report)
        footer.addWidget(self.open_report)
        self.export = QPushButton('导出纵向 HTML / JSON / CSV')
        self.export.clicked.connect(self._export)
        footer.addWidget(self.export)
        close = QPushButton('关闭')
        close.clicked.connect(self.close)
        footer.addWidget(close)
        box.addLayout(footer)
        self._set_busy(True)

    def _set_busy(self, busy):
        self.anchor.setEnabled(not busy)
        self.export.setEnabled(not busy and self.history is not None)
        self.open_report.setEnabled(not busy and self.history is not None)

    def request(self, anchor_id):
        self.request_id = uuid4().hex
        self._set_busy(True)
        self.notice.setText('正在核对原始记录…')
        self.anchor_requested.emit(anchor_id, self.request_id)

    def receive(self, history, request_id):
        if request_id != self.request_id:
            return
        self.history = history
        scope = history['scope']
        self.heading.setText(history['exercise_label']+' · '+('本人左侧' if scope['side'] == 'left' else '本人右侧')+
                             ' · '+('训练' if scope['submode'] == 'training' else '评估')+'\n'+scope['participant_id']+' · '+
                             SOURCES[scope['source_kind']]+' / '+CONTEXTS[scope['usage_context']])
        self.anchor.blockSignals(True)
        self.anchor.clear()
        for row in history['rows']:
            self.anchor.addItem((row.get('start_utc') or '日期未记录')[:19]+' · '+row['session_id'][:8], row['session_id'])
        self.anchor.setCurrentIndex(self.anchor.findData(history['anchor_id']))
        self.anchor.blockSignals(False)
        self.notice.setText(history['note'])
        self._set_busy(False)
        self._metric_changed()

    def show_error(self, message, request_id):
        if request_id == self.request_id:
            self._set_busy(False)
            if self.history:
                self.anchor.blockSignals(True)
                self.anchor.setCurrentIndex(self.anchor.findData(self.history['anchor_id']))
                self.anchor.blockSignals(False)
            self.notice.setText(message)

    def _anchor_changed(self):
        if self.anchor.currentData():
            self.request(self.anchor.currentData())

    def _metric_changed(self):
        if not self.history:
            return
        metric = self.metric_choice.currentData()
        self.plot.set_history(self.history, metric)
        selected = self.table.currentRow()
        self.table.setRowCount(len(self.history['rows']))
        for index, row in enumerate(self.history['rows']):
            value = row['values'].get(metric)
            number = '—' if value is None else f'{value:g}' if metric == 'completed' else f'{value:.2f}'
            count = row['timing_counts'].get(metric)
            ratio = row['valid_ratio']
            values = [f"{index+1} · "+(row.get('start_utc') or '日期未记录')[:19].replace('T', ' '),
                      DATA_LABELS[row['data_state']], COMPARISON_LABELS[row['comparison']['status']],
                      str(row['values']['completed']) if row['values']['completed'] is not None else '—',
                      number, f'{ratio:.0%}' if ratio is not None else '—',
                      f"{count['measured']} / {count['complete_repetitions']} 次" if count else '不适用']
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(index, column, item)
        if self.history['rows']:
            self.table.selectRow(max(0, min(selected, len(self.history['rows'])-1)))
        self._details()

    def _selected(self):
        index = self.table.currentRow()
        return self.history['rows'][index] if self.history and 0 <= index < len(self.history['rows']) else None

    def _details(self):
        row = self._selected()
        if row is None:
            return
        anchor = next(r for r in self.history['rows'] if r['session_id'] == self.history['anchor_id'])
        comparison = row['comparison']
        keys = sorted(set(comparison['differences']+comparison['missing']))
        text = '<b>'+fmt(COMPARISON_LABELS[comparison['status']])+'</b> · 原报告 '+fmt(row['session_id'])+'<br>'
        text += '开始 UTC：'+fmt(row['start_utc'])+'；结束 UTC：'+fmt(row['end_utc'])+'。<br>'
        text += '记录状态：'+fmt(row['status'])+'；结束原因：'+fmt(row['stop_reason'])+'。'
        if keys:
            text += '<table border="1" cellpadding="5"><tr><th>条件</th><th>基准</th><th>本记录</th></tr>'
            for key in keys:
                a, b = anchor['conditions']['values'].get(key), row['conditions']['values'].get(key)
                text += '<tr><td>'+fmt(CONDITION_LABELS.get(key, key))+('</td><td>'+fmt(json.dumps(a, ensure_ascii=False))+
                         '</td><td>'+fmt(json.dumps(b, ensure_ascii=False))+'</td></tr>')
            text += '</table>'
        else:
            text += '<p>记录中的来源、模型、规则、机位数值、基线和目标一致；未记录的现场变化仍需人工核对。</p>'
        self.details.setHtml(text)

    def _open_report(self):
        row = self._selected()
        if row:
            self.report_requested.emit(row['session_id'])

    def _export(self):
        parent = QFileDialog.getExistingDirectory(self, '选择纵向记录导出位置')
        if parent and self.history:
            out = Path(parent)/('history-'+self.history['anchor_id'][:12])
            self.export_requested.emit(self.history['anchor_id'], self.metric_choice.currentData(), str(out), self.history['fingerprint'])
