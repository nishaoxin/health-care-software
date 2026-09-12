from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QComboBox, QWidget, QScrollArea,
    QDoubleSpinBox, QSpinBox, QCheckBox, QDialogButtonBox, QLineEdit, QTextBrowser,
    QPushButton, QHBoxLayout, QListWidget, QInputDialog, QMessageBox, QTabWidget)

from ..reports import LABELS, render_result_summary
from ..exercises import exercise_spec
from ..movement_timing import timing_for_plan, validate_timing_plan


def nullable_spin(value, maximum=180, suffix=' °'):
    widget = QDoubleSpinBox()
    widget.setRange(-1, maximum)
    widget.setDecimals(1)
    widget.setSpecialValueText('未设置 · 仅测量')
    widget.setSuffix(suffix)
    widget.setValue(-1 if value is None else value)
    return widget


class PlanDialog(QDialog):
    def __init__(self, plan, parent=None, *, template_mode=False):
        super().__init__(parent)
        self.setWindowTitle('训练计划')
        self.setMinimumWidth(540)
        self.resize(620, 650)
        self.plan = copy.deepcopy(plan)
        self.template_mode = template_mode
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        spec = exercise_spec(plan['exercise_id'])
        title = QLabel(spec['label']+' · '+('左侧' if plan['side'] == 'left' else '右侧'))
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        intro = QLabel('填写要保存的安排；每次使用仍需确认本次计划和机位。' if template_mode else
                       '按已确认的训练安排填写。角度目标可不设置。')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form_host = QWidget()
        form_host.setObjectName('scrollContent')
        form = QFormLayout(form_host)
        form.setContentsMargins(0, 0, 10, 0)
        self.participant = QLineEdit(plan['participant_id'])
        self.participant.setReadOnly(True)
        self.participant.setToolTip('请在主界面“当前用户”处切换，以免混入其他用户记录。')
        self.reps, self.sets = QSpinBox(), QSpinBox()
        self.reps.setRange(1, 999)
        self.reps.setValue(plan['target_reps'])
        self.sets.setRange(1, 20)
        self.sets.setValue(plan['target_sets'])
        self.rest = nullable_spin(plan.get('rest_between_sets_s'), 1800, ' 秒')
        self.rest.setDecimals(0)
        self.rest.setSpecialValueText('未指定 · 手动继续')
        self.target = nullable_spin(plan['target_angle_deg'])
        self.elbow = nullable_spin(plan['allowed_elbow_flexion_deg'])
        self.tilt = nullable_spin(plan['allowed_trunk_tilt_deg'], 90)
        timing = timing_for_plan(plan)
        self.timing_controls = {key: nullable_spin(value, 300, ' 秒') for key, value in timing.items()}
        self.tempo_min = self.timing_controls['return_min_s']
        self.tempo_max = self.timing_controls['return_max_s']
        self.hands = QComboBox()
        for title, key in (('未记录', 'not_recorded'), ('允许扶物', 'allowed'), ('不允许扶物', 'not_allowed'), ('人工记录已使用双手', 'used_hands')):
            self.hands.addItem(title, key)
        self.hands.setCurrentIndex(max(0, self.hands.findData(plan['use_of_hands'])))
        self.companion = QCheckBox('此计划需要陪同')
        self.companion.setChecked(plan['needs_companion'])
        self.sound = QCheckBox('开启提示音')
        self.sound.setChecked(plan['sound_enabled'])
        self.participant.setParent(self)
        self.participant.hide()
        person = getattr(parent, 'participant_records', {}).get(plan['participant_id'], {})
        person_label = QLabel(person.get('display_name', plan['participant_id']))
        person_label.setTextFormat(Qt.TextFormat.PlainText)
        person_label.setWordWrap(True)
        form.addRow('当前用户', person_label)
        form.addRow('每组目标次数', self.reps)
        form.addRow('计划组数', self.sets)
        form.addRow('组间休息时间', self.rest)
        direction = '投影角上限' if spec['target_direction'] == 'decrease' else '投影角目标'
        self.target.setToolTip(spec['metric_label'])
        form.addRow(direction, self.target)
        if plan['exercise_id'] in ('shoulder_abduction', 'shoulder_flexion'):
            form.addRow('允许可见屈肘上限', self.elbow)
        if spec['joint'] == 'shoulder':
            form.addRow('允许躯干侧倾上限', self.tilt)
        if plan['exercise_id'] == 'sit_to_stand':
            form.addRow('扶物 / 双手使用', self.hands)
        timing_note = QLabel('可选时间安排：留空仅记录。保持按人工角度目标范围内的连续观察计算；坐站按已确认站位范围计算。')
        timing_note.setWordWrap(True)
        form.addRow(timing_note)
        for key, label in (('outbound_min_s', '出程最短时间'), ('outbound_max_s', '出程最长时间'),
                           ('return_min_s', '回程最短时间'), ('return_max_s', '回程最长时间'),
                           ('hold_min_s', '连续保持至少')):
            form.addRow(label, self.timing_controls[key])
        form.addRow(self.companion)
        form.addRow(self.sound)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_host)
        layout.addWidget(scroll, 1)
        if spec['joint'] != 'shoulder' and plan['exercise_id'] != 'sit_to_stand':
            note = QLabel('本动作支持可见角度、往返计数和人工目标提示；暂不识别代偿、坐位保持或支撑稳定性。')
            note.setWordWrap(True)
            layout.addWidget(note)
        measure = QLabel(spec['metric_label']+'。目标由本人或专业人员确认，不由评估结果自动生成。')
        measure.setObjectName('muted')
        measure.setWordWrap(True)
        layout.addWidget(measure)
        layout.addWidget(QLabel('疼痛、头晕或不适时，请立即停止。'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存项目' if template_mode else '确认本次计划')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        if not self.participant.text().strip():
            QMessageBox.information(self, '需要编号', '请输入匿名参与者编号，便于区分历史记录。')
            return
        def optional(w):
            return w.value() if w.value() >= 0 else None
        try:
            timing = validate_timing_plan({key: optional(w) for key, w in self.timing_controls.items()},
                                          self.plan['exercise_id'], optional(self.target))
        except ValueError as exc:
            QMessageBox.information(self, '检查时间安排', str(exc))
            return
        self.plan.update(participant_id=self.participant.text().strip(), target_reps=self.reps.value(), target_sets=self.sets.value(),
                         rest_between_sets_s=optional(self.rest),
                         target_angle_deg=optional(self.target), allowed_elbow_flexion_deg=optional(self.elbow),
                         allowed_trunk_tilt_deg=optional(self.tilt), lowering_tempo_min_s=None, lowering_tempo_max_s=None,
                         timing_plan=timing,
                         use_of_hands=self.hands.currentData(), needs_companion=self.companion.isChecked(), sound_enabled=self.sound.isChecked())
        self.plan['training_plan_confirmed'] = self.plan.get('submode') == 'training' and not self.template_mode
        self.accept()


class ReportDialog(QDialog):
    def __init__(self, snapshot, html, on_export, parent=None, on_feedback=None):
        super().__init__(parent)
        self.setWindowTitle('本地任务报告')
        self.resize(1080, 760)
        self.snapshot = snapshot
        box = QVBoxLayout(self)
        browser = QTextBrowser()
        self.browser = browser
        browser.setOpenExternalLinks(False)
        browser.setHtml(html)
        self.overview = None
        if snapshot.get('scene_id') == 'rehab':
            tabs = QTabWidget()
            self.overview = QTextBrowser()
            self.overview.setOpenExternalLinks(False)
            self.overview.setHtml(render_result_summary(snapshot))
            self.overview.setStyleSheet('font-size:18px;')
            tabs.addTab(self.overview, '结果解读')
            tabs.addTab(browser, '详细数据')
            box.addWidget(tabs)
        else:
            box.addWidget(browser)
        row = QHBoxLayout()
        label = QLabel('原始视频默认不保存；报告中的 — 表示没有有效证据或不适用。')
        row.addWidget(label, 1)
        if on_feedback and snapshot.get('submode') == 'training' and snapshot.get('status') in ('FINISHED', 'INTERRUPTED'):
            feedback = QPushButton('填写训练感受')
            feedback.clicked.connect(lambda: on_feedback(snapshot['id']))
            row.addWidget(feedback)
        export = QPushButton('导出 HTML / JSON / CSV')
        export.clicked.connect(lambda: on_export(snapshot['id']))
        row.addWidget(export)
        close = QPushButton('返回')
        close.clicked.connect(self.accept)
        row.addWidget(close)
        box.addLayout(row)


class EventsDialog(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.setWindowTitle('事件查看与处理')
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        label = QLabel('“已查看”只表示有人查看了提示；处理完成后请记录现场情况。\n切换场景或断流不会自动关闭事件。只提供本地提示。')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.details = QLabel('选择一条事件查看证据')
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.list.currentRowChanged.connect(self._select)
        row = QHBoxLayout()
        self.ack = QPushButton('标记已查看')
        self.resolve = QPushButton('记录处理结果并关闭')
        self.ack.clicked.connect(lambda: self._transition('ACKNOWLEDGED'))
        self.resolve.clicked.connect(lambda: self._transition('RESOLVED'))
        row.addWidget(self.ack)
        row.addWidget(self.resolve)
        layout.addLayout(row)
        self.events = []

    def populate(self, events):
        self.events = events
        self.list.clear()
        titles = {'OPEN': '待查看', 'ACKNOWLEDGED': '已查看 · 待处理', 'CLAIMED': '已认领 · 待处理', 'RESOLVED': '已处理'}
        for event in events:
            self.list.addItem(f"{titles.get(event['status'], event['status'])}   {event.get('message', '疑似异常事件')}\n{event.get('source_kind', '未记录')} / {event.get('usage_context', '未记录')}")
        if events:
            self.list.setCurrentRow(0)
        else:
            self.details.setText('暂无事件。未运行场景没有监测结果。')
            self.ack.setEnabled(False)
            self.resolve.setEnabled(False)

    def _select(self, row):
        if not 0 <= row < len(self.events):
            return
        event = self.events[row]
        self.details.setText(f"{event.get('message', '')}\n证据时间：{event.get('evidence_start_time', '—')} → {event.get('event_emitted_time', '—')}；时间来源：{event.get('time_basis', '未记录')}")
        self.ack.setEnabled(event['status'] == 'OPEN')
        self.resolve.setEnabled(event['status'] in ('ACKNOWLEDGED', 'CLAIMED'))

    def _transition(self, status):
        row = self.list.currentRow()
        if not 0 <= row < len(self.events):
            return
        note = ''
        if status == 'RESOLVED':
            note, accepted = QInputDialog.getMultiLineText(self, '处理结果', '请记录现场确认和处理结果：')
            if not accepted or not note.strip():
                return
        self.runtime.command('event_transition', id=self.events[row]['id'], status=status, operator='local-operator', note=note)
