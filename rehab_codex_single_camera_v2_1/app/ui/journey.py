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
        self.manual = QCheckBox('画面为本人，测试侧正确\n所需关节点可见，已回到起点')
        self.manual.setAccessibleName('人工核对本人、测试侧、关节点和起点')
        self.companion = QCheckBox('陪同者已在场')
        self.message = QLabel()
        self.message.setObjectName('notice')
        self.settings = QPushButton('调整测试侧 / 机位与设置')
        self.settings.setObjectName('textButton')
        self.repeat = QPushButton('重新测量本动作')
        for widget in (self.progress, self.title, self.context, self.instruction, self.explanation,
                       self.manual, self.companion, self.message, self.settings, self.repeat):
            if isinstance(widget, QLabel):
                widget.setWordWrap(True)
                widget.setTextFormat(Qt.TextFormat.PlainText)
            box.addWidget(widget)
        box.addStretch()

    def render(self, step, *, context, manual, companion, needs_companion, dual, enabled, message=''):
        self.progress.setText(f'第 {step.number} / {step.total} 步 · 按下方主按钮继续')
        self.title.setText(step.title)
        self.context.setText(context)
        self.instruction.setText(step.instruction)
        self.manual.setText('两路均为本人，正侧机位正确\n测试侧和关节点已核对，已回到起点' if dual else
                            '画面为本人，测试侧正确\n所需关节点可见，已回到起点')
        for widget, checked in ((self.manual, manual), (self.companion, companion)):
            widget.blockSignals(True)
            widget.setChecked(checked)
            widget.blockSignals(False)
            widget.setEnabled(enabled)
        self.manual.setVisible(step.key == 'confirm')
        self.companion.setVisible(step.key == 'confirm' and needs_companion)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        self.repeat.setVisible(step.key == 'result')
        self.repeat.setEnabled(enabled)
        self.settings.setEnabled(enabled and step.key not in ('active', 'save_failed'))
