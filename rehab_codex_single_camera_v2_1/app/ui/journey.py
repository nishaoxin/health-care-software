"""One instruction at a time, with explicit human acknowledgement controls."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QCheckBox, QPushButton


class JourneyPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 20, 18, 16)
        box.setSpacing(12)
        self.progress = QLabel()
        self.progress.setObjectName('muted')
        self.title = QLabel()
        self.title.setStyleSheet('font-size:24px;font-weight:600;')
        self.context = QLabel()
        self.context.setObjectName('muted')
        self.instruction = QLabel()
        self.instruction.setStyleSheet('font-size:20px;')
        self.explanation = QLabel()
        self.explanation.setObjectName('muted')
        self.companion = QCheckBox('陪同者已在场')
        self.message = QLabel()
        self.message.setObjectName('notice')
        self.settings = QPushButton('调整测试侧 / 机位与设置')
        self.settings.setObjectName('textButton')
        self.repeat = QPushButton('重新测量本动作')
        for widget in (self.progress, self.title, self.context, self.instruction, self.explanation,
                       self.companion, self.message, self.settings, self.repeat):
            if isinstance(widget, QLabel):
                widget.setWordWrap(True)
                widget.setTextFormat(Qt.TextFormat.PlainText)
            box.addWidget(widget)
        box.addStretch()

    def render(self, step, *, context, companion, needs_companion, enabled, message=''):
        hint = '记录中，请保持姿势' if step.action == '正在记录…' else '按下方主按钮继续'
        self.progress.setText(f'第 {step.number} / {step.total} 步 · {hint}')
        self.title.setText(step.title)
        self.context.setText(context)
        self.instruction.setText(step.instruction)
        for widget, checked in ((self.companion, companion),):
            widget.blockSignals(True)
            widget.setChecked(checked)
            widget.blockSignals(False)
            widget.setEnabled(enabled)
        self.companion.setVisible(step.key == 'confirm' and needs_companion)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        self.repeat.setVisible(step.key == 'result')
        self.repeat.setEnabled(enabled)
        self.settings.setEnabled(enabled and step.key not in ('active', 'save_failed'))
