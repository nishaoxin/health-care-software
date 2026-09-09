"""Training entry screen: no invented recommendations, streaks, or saved plans."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton

from ..exercises import exercise_spec
from ..exercise_instructions import exercise_instructions


class TrainingHub(QWidget):
    assessment_requested = Signal()
    records_requested = Signal()
    resume_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.has_reference = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        hero = QFrame()
        hero.setObjectName('journeyHero')
        hero_box = QVBoxLayout(hero)
        hero_box.setContentsMargins(26, 22, 26, 22)
        eyebrow = QLabel('YOUR PACE  /  YOUR PROGRESS')
        eyebrow.setObjectName('heroEyebrow')
        hero_box.addWidget(eyebrow)
        title = QLabel('每一步，都按自己的节奏')
        title.setObjectName('heroTitle')
        hero_box.addWidget(title)
        subtitle = QLabel('先了解当前表现，再按已确认的计划练习。不自动加量，不要求追求最大幅度。')
        subtitle.setObjectName('heroDescription')
        subtitle.setWordWrap(True)
        hero_box.addWidget(subtitle)
        box.addWidget(hero)
        current = QFrame()
        current.setObjectName('card')
        panel = QVBoxLayout(current)
        panel.setContentsMargins(24, 22, 24, 22)
        panel.setSpacing(14)
        self.plan_title = QLabel()
        self.plan_title.setObjectName('sectionTitle')
        self.plan_title.setWordWrap(True)
        panel.addWidget(self.plan_title)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setObjectName('muted')
        panel.addWidget(self.description)
        self.plan_details = QLabel()
        self.plan_details.setObjectName('planSummary')
        self.plan_details.setWordWrap(True)
        panel.addWidget(self.plan_details)
        self.resume = QPushButton('继续准备训练')
        self.resume.setObjectName('primary')
        self.resume.clicked.connect(self.resume_requested.emit)
        panel.addWidget(self.resume)
        actions = QHBoxLayout()
        self.records = QPushButton('从评估记录选择训练')
        self.records.clicked.connect(self.records_requested.emit)
        self.assess = QPushButton('先做身体评估')
        self.assess.clicked.connect(self.assessment_requested.emit)
        actions.addWidget(self.records)
        actions.addWidget(self.assess)
        panel.addLayout(actions)
        box.addWidget(current)
        row = QHBoxLayout()
        for number, title, text in (
            ('01', '选择已有评估', '只引用本人、同来源与情境下的可用记录。'),
            ('02', '确认训练安排', '逐项确认次数、组数、休息和活动限制。'),
            ('03', '看步骤，跟着练', '动作文字与图片位同步展示，可随时暂停。'),
        ):
            tile = QFrame()
            tile.setObjectName('card')
            content = QVBoxLayout(tile)
            content.setContentsMargins(18, 16, 18, 16)
            count = QLabel(number)
            count.setObjectName('journeyNumber')
            content.addWidget(count)
            heading = QLabel(title)
            heading.setObjectName('sectionTitle')
            heading.setWordWrap(True)
            content.addWidget(heading)
            note = QLabel(text)
            note.setWordWrap(True)
            note.setObjectName('muted')
            content.addWidget(note)
            row.addWidget(tile, 1)
        box.addLayout(row)
        box.addStretch()
        note = QLabel('仅提供二维动作观察与已确认计划的执行辅助。疼痛、头晕或不适时立即停止。')
        note.setObjectName('safetyNote')
        note.setWordWrap(True)
        box.addWidget(note)
        self.set_plan({}, {})

    def set_plan(self, plan, scope):
        reference = plan.get('assessment_reference') or {}
        self.has_reference = bool(
            plan.get('submode') == 'training' and reference.get('status') == 'ASSESSED'
            and reference.get('session_id')
            and all(scope.get(k) is not None and reference.get(k) == scope[k]
                    for k in ('participant_id', 'source_kind', 'usage_context'))
            and plan.get('participant_id') == scope.get('participant_id')
            and reference.get('exercise_id') == plan.get('exercise_id')
            and reference.get('side') == plan.get('side'))
        self.resume.setVisible(self.has_reference)
        self.plan_details.setVisible(self.has_reference)
        if not self.has_reference:
            self.plan_title.setText('准备好，再开始训练')
            self.description.setText('先从身体档案选择一个可用评估。还没有记录？完成需要的单项评估即可，不必测完全部动作。')
            self.plan_details.clear()
            return
        spec = exercise_spec(plan['exercise_id'])
        info = exercise_instructions(plan['exercise_id'])
        side = '本人左侧' if plan['side'] == 'left' else '本人右侧'
        self.plan_title.setText(spec['label'] + ' · ' + side)
        self.description.setText(info['move'])
        rest = plan.get('rest_between_sets_s')
        rest_label = '休息时间未指定' if rest is None else f'组间休息 {rest:g} 秒'
        confirmed = '已确认' if plan.get('training_plan_confirmed') else '待确认，不能直接开始'
        self.plan_details.setText(f"当前安排：{plan.get('target_reps', '—')} 次 × {plan.get('target_sets', '—')} 组\n"
                                  f"{rest_label} · 计划{confirmed}\n当前准备中的安排，不代表已完成训练。")
