"""Explicit controls for the isolated family-web demonstration."""
from PySide6.QtCore import Signal, QTimer, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton, QListWidget


class FamilyDemoDialog(QDialog):
    operation = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('手机家属联动 · 仅隔离测试资料')
        self.resize(800, 640)
        box = QVBoxLayout(self)
        self.info = QLabel('只提供 SYNTHETIC / TEST 演示请求，不读取患者档案、视频或真实求助。\nHTTP 只用于可信局域网演示，不适合真实敏感数据。首次默认只监听本机。')
        self.info.setWordWrap(True)
        box.addWidget(self.info)
        self.allow = QCheckBox('我确认仅演示测试资料，并了解网页关闭 / 锁屏 / 离网不保证送达')
        box.addWidget(self.allow)
        self.host = QLineEdit('127.0.0.1')
        self.host.setPlaceholderText('手机演示请改为本机可信局域网 IPv4，例如 192.168.1.10')
        box.addWidget(self.host)
        row = QHBoxLayout()
        self.start = QPushButton('手动开启演示')
        self.start.clicked.connect(lambda: self.operation.emit(dict(action='start', host=self.host.text(), demo_confirmed=self.allow.isChecked())))
        self.stop = QPushButton('撤销配对并关闭服务')
        self.stop.clicked.connect(lambda: self.operation.emit(dict(action='stop')))
        row.addWidget(self.start)
        row.addWidget(self.stop)
        box.addLayout(row)
        self.address = QLabel('服务未开启')
        self.address.setTextFormat(Qt.TextFormat.PlainText)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.address.setWordWrap(True)
        self.address.setStyleSheet('font-size:22px;')
        box.addWidget(self.address)
        self.approve = QPushButton('我已核对手机：确认待配对家属')
        self.approve.clicked.connect(self._approve)
        box.addWidget(self.approve)
        self.test = QPushButton('注入 TEST_EVENT 演示求助（非视觉检测）')
        self.test.clicked.connect(lambda: self.operation.emit(dict(action='request')))
        box.addWidget(self.test)
        self.requests = QListWidget()
        box.addWidget(self.requests, 1)
        self.message = QLabel('尚无手机回执。请将手机与电脑连接同一可信局域网，并保持页面前台。')
        self.message.setWordWrap(True)
        box.addWidget(self.message)
        self.data = {}
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(lambda: self.operation.emit(dict(action='status')) if self.isVisible() else None)
        self.timer.start()

    def _approve(self):
        pending = self.data.get('pending', [])
        if len(pending) == 1:
            self.operation.emit(dict(action='approve', id=pending[0]))

    def render(self, data):
        self.data = data
        running = data.get('running', False)
        self.start.setEnabled(not running)
        self.host.setEnabled(not running)
        self.stop.setEnabled(running)
        self.test.setEnabled(running)
        self.approve.setEnabled(len(data.get('pending', [])) == 1)
        self.address.setText(f"手机地址：{data['url']}\n配对码：{data['code'] or '已使用 / 过期'}（剩余 {data['code_remaining_s']} 秒）\n已批准配对：{data['approved']}；不代表网页当前在线。"
                             if running else '服务未开启；原配对已失效。')
        self.requests.clear()
        for r in data.get('requests', []):
            trail = '；'.join(f"{h['action']} / {h['channel']} / {h['note']}" for h in r['history'])
            self.requests.addItem(f"{r['status']} · {r['note']}\n{trail or '尚未收到回应'}")
        self.message.setText('仅测试资料。手机回执落库后才显示；已查看、认领和处理是不同状态。')

    def show_error(self, message):
        self.message.setText('操作未确认成功：'+message)

    def closeEvent(self, event):
        # Closing the control panel revokes the demo instead of silently serving in background.
        if self.data.get('running'):
            self.operation.emit(dict(action='stop'))
        super().closeEvent(event)
