"""Local profile form and manually entered information card."""
import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QLabel, QLineEdit, QPlainTextEdit, QComboBox,
                              QPushButton, QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFormLayout)

from ..participants import SIDES, REPORTERS, SUPPORT, TEXT_FIELDS, validate_participant, participant_summary
from .widgets import NoticeLabel


def plain_label(text='', name=None):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


class ParticipantDialog(QDialog):
    save_requested = Signal(dict, int)

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = copy.deepcopy(profile)
        self.pending = False
        self.setWindowTitle('个人信息' if profile.get('revision') else '填写个人信息')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(660, 650)
        self.setMinimumSize(520, 420)
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 20, 24, 20)
        box.setSpacing(12)
        box.addWidget(plain_label(self.windowTitle(), 'sectionTitle'))
        box.addWidget(plain_label('只需填写称呼，其余可留空。活动限制按已有医嘱或本人情况填写。', 'muted'))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.form_host = QWidget()
        self.form_host.setObjectName('scrollContent')
        form = QFormLayout(self.form_host)
        form.setContentsMargins(0, 4, 12, 4)
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name = QLineEdit(profile['display_name'])
        self.name.setMaxLength(60)
        self.name.setPlaceholderText('姓名、称呼或昵称')
        self.birth_year = QLineEdit(str(profile['birth_year']) if profile.get('birth_year') else '')
        self.birth_year.setPlaceholderText('例如 1950；不知道可留空')
        self.birth_year.setMaxLength(4)
        form.addRow('称呼 *', self.name)
        form.addRow('出生年份', self.birth_year)
        self.choices = {}
        for key, label, options in [('affected_side', '关注侧别', SIDES), ('support', '日常陪同', SUPPORT),
                                     ('reported_by', '本次填写者', REPORTERS)]:
            choice = QComboBox()
            for value, title in options.items():
                choice.addItem(title, value)
            choice.setCurrentIndex(choice.findData(profile.get(key)))
            self.choices[key] = choice
            form.addRow(label, choice)
        self.fields = {}
        placeholders = {'reason': '例如：出院后的日常活动练习', 'restrictions': '已有医嘱、避免的动作或尚待确认的限制；不要自行推断',
                        'goals': '例如：自己穿外套、拿水杯', 'aids': '例如：手杖、助行器；没有可留空', 'notes': '其他需要记住的情况'}
        for key, label in TEXT_FIELDS.items():
            editor = QPlainTextEdit(profile.get(key, ''))
            editor.setPlaceholderText(placeholders[key])
            editor.setFixedHeight(80 if key != 'aids' else 62)
            editor.setAccessibleName(label)
            self.fields[key] = editor
            form.addRow(label, editor)
        self.scroll.setWidget(self.form_host)
        box.addWidget(self.scroll, 1)
        self.error = NoticeLabel()
        self.error.setObjectName('notice')
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.clear()
        box.addWidget(self.error)
        box.addWidget(plain_label('手工填写，不代表已完成专业审核；不会自动改变训练目标。', 'muted'))
        row = QHBoxLayout()
        self.cancel = QPushButton('取消')
        self.cancel.clicked.connect(self.reject)
        self.save = QPushButton('保存个人信息')
        self.save.setObjectName('primary')
        self.save.clicked.connect(self.submit)
        row.addStretch()
        row.addWidget(self.cancel)
        row.addWidget(self.save)
        box.addLayout(row)

    def submit(self):
        if self.pending:
            return
        try:
            year_text = self.birth_year.text().strip()
            if year_text and (not year_text.isascii() or not year_text.isdigit()):
                raise ValueError('出生年份请填写四位数字，或留空')
            draft = dict(self.profile, display_name=self.name.text(), birth_year=int(year_text) if year_text else None)
            draft.update({key: widget.currentData() for key, widget in self.choices.items()})
            draft.update({key: widget.toPlainText() for key, widget in self.fields.items()})
            value = validate_participant(draft)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.error.clear()
        self.save_requested.emit(value, self.profile.get('revision', 0))

    def set_busy(self, busy):
        self.pending = bool(busy)
        self.form_host.setEnabled(not busy)
        self.save.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self.save.setText('正在处理…' if busy else '保存个人信息')

    def reject(self):
        if not self.pending:
            super().reject()

    def closeEvent(self, event):
        if self.pending:
            event.ignore()
        else:
            super().closeEvent(event)


class ParticipantSummary(QFrame):
    edit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)
        row = QHBoxLayout()
        self.heading = plain_label('', 'sectionTitle')
        row.addWidget(self.heading, 1)
        self.edit = QPushButton('编辑个人信息')
        self.edit.setObjectName('textButton')
        self.edit.clicked.connect(self.edit_requested)
        row.addWidget(self.edit)
        layout.addLayout(row)
        self.summary = plain_label()
        self.goals = plain_label()
        self.restrictions = plain_label()
        self.origin = plain_label('', 'muted')
        layout.addWidget(self.summary)
        layout.addWidget(self.goals)
        layout.addWidget(self.restrictions)
        layout.addWidget(self.origin)

    def set_profile(self, profile):
        self.heading.setText(profile['display_name'])
        self.summary.setText(participant_summary(profile))
        goal = profile.get('goals', '').replace('\n', ' ')
        self.goals.setText('生活目标：'+goal[:90]+('…' if len(goal) > 90 else ''))
        self.goals.setToolTip(profile.get('goals', ''))
        self.goals.setVisible(bool(goal))
        restriction = profile.get('restrictions', '').replace('\n', ' ')
        self.restrictions.setText('已填活动限制：'+restriction[:90]+('…（查看个人信息）' if len(restriction) > 90 else ''))
        self.restrictions.setToolTip(profile.get('restrictions', ''))
        self.restrictions.setVisible(bool(restriction))
        self.origin.setText(('手工填写 · '+REPORTERS.get(profile.get('reported_by'), '来源未记录')+' · ' if profile.get('revision') else '')
                            +'以下为摄像头评估记录，与个人填写信息分开。')
