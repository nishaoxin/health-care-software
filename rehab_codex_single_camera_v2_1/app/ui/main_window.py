from __future__ import annotations

import copy
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import queue

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox,
    QDoubleSpinBox, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QPlainTextEdit, QDialog,
    QInputDialog)

from ..domain import SCENES, EXERCISES, SOURCES, CONTEXTS, digest, dumps
from ..geometry import compatible_reports
from ..settings import ROOT, default_setup, default_plan
from ..runtime import Runtime
from .dialogs import PlanDialog, ReportDialog, EventsDialog
from .widgets import VideoCanvas, MetricCard, ROI_LABELS

STYLE = '''
QMainWindow, QWidget { background:#f3f6f2; color:#213d3c; font-family:'Microsoft YaHei UI'; font-size:12px; }
QFrame#sidebar { background:#183c3d; border:0; }
QFrame#sidebar QLabel { background:transparent; color:#d7e8df; }
QLabel#brand { color:white; font-size:21px; font-weight:700; }
QLabel#sectionTitle { font-size:17px; font-weight:650; }
QLabel#pageTitle { font-size:26px; font-weight:700; }
QLabel#muted { color:#6d7e79; }
QLabel#badge { color:#1c6e60; background:#e1eee3; border-radius:12px; padding:6px 12px; }
QFrame#card, QFrame#metricCard { background:#ffffff; border:1px solid #dee6de; border-radius:12px; }
QFrame#card QLabel, QFrame#metricCard QLabel { background:transparent; }
QLabel#metricValue { font-size:27px; font-weight:600; color:#254b42; }
QPushButton { background:white; border:1px solid #cedad0; border-radius:7px; padding:9px 13px; min-height:18px; }
QPushButton:hover { background:#e9f3e9; border-color:#8daf97; }
QPushButton:pressed { background:#dbe9df; }
QPushButton:disabled { color:#95a19a; background:#eef1ed; border-color:#e3e7e1; }
QPushButton#primary { background:#236957; color:white; border:1px solid #236957; font-weight:600; }
QPushButton#primary:hover { background:#195645; }
QPushButton#primary:disabled { background:#bbcfc2; border-color:#bbcfc2; }
QPushButton#danger { color:#985848; background:#fff5ef; border-color:#e2cbc0; }
QPushButton#nav { color:#c6dcd0; background:transparent; border:0; text-align:left; padding:15px 12px; }
QPushButton#nav:checked { background:#2b5250; color:white; border-left:3px solid #c7dba2; border-radius:5px; }
QPushButton#nav:hover { background:#24494a; }
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox { border:1px solid #d4ded4; border-radius:6px; background:white; padding:7px; min-height:19px; selection-background-color:#ccdfcf; }
QComboBox::drop-down { border:0; width:22px; }
QComboBox::down-arrow { image:url(__ASSETS__/chevron.svg); width:12px; height:12px; }
QComboBox QAbstractItemView { background:white; selection-background-color:#dcebe0; color:#244436; }
QCheckBox { spacing:7px; background:transparent; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #9eb4a4; border-radius:3px; background:white; }
QCheckBox::indicator:checked { background:#236957; border-color:#236957; image:url(__ASSETS__/check.svg); }
QCheckBox::indicator:disabled { border-color:#d0d9d1; background:#eef3ed; }
QLabel#feedback { background:#e5eee0; color:#38553f; padding:12px; border-radius:8px; }
QLabel#notice { color:#6c5136; background:#f7ecd8; padding:8px 12px; border-radius:6px; }
QTableWidget { background:white; alternate-background-color:#f5f8f3; border:1px solid #d9e4d9; gridline-color:#e6ebe3; selection-background-color:#dfecdf; selection-color:#213d3c; }
QHeaderView::section { background:#eaf0e7; color:#4a6256; border:0; padding:10px; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { width:7px; background:transparent; }
QScrollBar::handle:vertical { background:#ccdacd; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QPlainTextEdit, QTextBrowser { background:white; border:1px solid #d9e4d9; border-radius:6px; padding:8px; }
'''.replace('__ASSETS__', (ROOT/'assets/ui').as_posix())

STATUS = {'UNSELECTED': '未打开', 'CONNECTING': '正在连接', 'PREVIEW': '预览 · 尚未分析',
          'ONLINE': '分析中', 'OFFLINE': '输入离线', 'PRIVACY_PAUSED': '隐私暂停 · 采集已停止',
          'ERROR': '输入异常', 'SAVE_FAILED': '报告待保存'}
PHASES = {'WAIT_READY': '等待准备', 'REST': '准备姿势', 'RAISING': '正在抬举',
          'PEAK_OR_HOLD': '上举 / 保持', 'LOWERING': '正在回位', 'SEATED_READY': '坐位准备',
          'RISING': '正在起立', 'STANDING_REACHED': '已达到站位', 'UNKNOWN': '无法判断',
          'SEATED': '可见坐位', 'STANDING': '可见站位', 'WALKING': '可见步行', 'VISIBLE_MOVING': '可见移动',
          'VISIBLE_IN_BED': '可见床区姿态', 'BED_EDGE_SIT': '可见床边坐位',
          'BED_EDGE_STAND': '可见床边站立', 'OBSERVED_EXIT': '已观察经过出口',
          'LOW_CANDIDATE': '疑似异常低位 · 待确认', 'LOW_EVENT': '持续低位事件', 'OBSERVING': '观察中'}


def combo(items):
    widget = QComboBox()
    for key, title in items.items():
        widget.addItem(title, key)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName('card')
    return frame


class MainWindow(QMainWindow):
    def __init__(self, runtime=None, data_dir=None):
        super().__init__()
        self.setWindowTitle('居家康复助手 · 单摄像头本地版')
        self.resize(1360, 900)
        self.setMinimumSize(1100, 730)
        self.setStyleSheet(STYLE)
        self.runtime = runtime or Runtime(data_dir)
        self.scene = 'rehab'
        self.setup = default_setup()
        self.state = 'UNSELECTED'
        self.busy = 0
        self.pending_commands = Counter()
        self.constructing = True
        self._allow_close = False
        self._closing = False
        self.sessions = []
        self.report_windows = []
        self.events_dialog = None
        self.last_generation = -1
        self._build()
        self.constructing = False
        self._sync_scene()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(30)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(194)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(18, 28, 18, 24)
        brand = QLabel('居家康复助手')
        brand.setObjectName('brand')
        nav.addWidget(brand)
        nav.addWidget(QLabel('HOME REHAB  /  本地版'))
        nav.addSpacing(38)
        nav.addWidget(QLabel('选择本次场景'))
        nav.addSpacing(10)
        self.scene_buttons = {}
        for scene, title in SCENES.items():
            button = QPushButton(title)
            button.setObjectName('nav')
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, s=scene: self._select_scene(s))
            nav.addWidget(button)
            self.scene_buttons[scene] = button
        nav.addSpacing(20)
        self.history_nav = QPushButton('历史报告')
        self.history_nav.setObjectName('nav')
        self.history_nav.clicked.connect(self._history)
        nav.addWidget(self.history_nav)
        event_button = QPushButton('事件查看与处理')
        event_button.setObjectName('nav')
        event_button.clicked.connect(self._events)
        nav.addWidget(event_button)
        nav.addStretch()
        self.coverage = QLabel('当前未开始监测\n\n每次仅运行一个场景\n其余场景均未监测')
        self.coverage.setWordWrap(True)
        nav.addWidget(self.coverage)
        nav.addSpacing(20)
        nav.addWidget(QLabel('v0.1  ·  v2.1 规范实现'))
        root.addWidget(sidebar)
        body = QVBoxLayout()
        body.setContentsMargins(24, 20, 24, 18)
        body.setSpacing(12)
        heading = QHBoxLayout()
        titlebox = QVBoxLayout()
        self.title = QLabel('康复评估与训练')
        self.title.setObjectName('pageTitle')
        titlebox.addWidget(self.title)
        self.subtitle = QLabel('看见每一次动作，记录可见的变化。')
        self.subtitle.setObjectName('muted')
        titlebox.addWidget(self.subtitle)
        heading.addLayout(titlebox, 1)
        self.status_badge = QLabel('未打开')
        self.status_badge.setObjectName('badge')
        heading.addWidget(self.status_badge)
        body.addLayout(heading)
        self.notice = QLabel('先选择输入并预览，确认机位和参与者后再开始。')
        self.notice.setWordWrap(True)
        self.notice.setObjectName('notice')
        body.addWidget(self.notice)
        self.pages = QStackedWidget()
        self.work_page = QWidget()
        work = QVBoxLayout(self.work_page)
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(12)
        self._source_card(work)
        split = QHBoxLayout()
        split.setSpacing(16)
        monitor = QVBoxLayout()
        monitor.setSpacing(10)
        row = QHBoxLayout()
        self.source_badge = QLabel('视频预览')
        self.source_badge.setObjectName('muted')
        row.addWidget(self.source_badge, 1)
        self.frame_info = QLabel('等待输入')
        self.frame_info.setObjectName('muted')
        row.addWidget(self.frame_info)
        monitor.addLayout(row)
        self.canvas = VideoCanvas()
        self.canvas.roi_changed.connect(self._roi_changed)
        monitor.addWidget(self.canvas, 1)
        metrics = QHBoxLayout()
        self.count_card = MetricCard('完整完成', ' 次')
        self.angle_card = MetricCard('二维投影角', '°')
        self.valid_card = MetricCard('有效观察', '%')
        for item in (self.count_card, self.angle_card, self.valid_card):
            metrics.addWidget(item)
        monitor.addLayout(metrics)
        self.feedback = QLabel('准备开始：选择输入 → 预览 → 确认机位 → 开始任务')
        self.feedback.setObjectName('feedback')
        self.feedback.setWordWrap(True)
        monitor.addWidget(self.feedback)
        self.debug_toggle = QCheckBox('调试详情：阶段、关节置信度与拒测原因')
        self.debug_toggle.toggled.connect(lambda checked: self.debug.setVisible(checked))
        monitor.addWidget(self.debug_toggle)
        self.debug = QPlainTextEdit()
        self.debug.setReadOnly(True)
        self.debug.setMaximumHeight(125)
        self.debug.setVisible(False)
        monitor.addWidget(self.debug)
        split.addLayout(monitor, 1)
        panel = self._setup_panel()
        panel.setFixedWidth(290)
        split.addWidget(panel)
        work.addLayout(split, 1)
        actions = QHBoxLayout()
        self.preview_button = QPushButton('1  预览输入')
        self.preview_button.setObjectName('previewButton')
        self.preview_button.clicked.connect(self._preview)
        self.confirm_button = QPushButton('2  确认机位')
        self.confirm_button.clicked.connect(self._confirm)
        self.start_button = QPushButton('3  开始任务')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(lambda: self._send('start'))
        self.stop_button = QPushButton('停止并保存')
        self.stop_button.clicked.connect(lambda: self._send('stop', reason='user_stop'))
        self.privacy_button = QPushButton('隐私暂停')
        self.privacy_button.setObjectName('danger')
        self.privacy_button.clicked.connect(lambda: self._send('privacy', reason='privacy_pause'))
        self.retry_button = QPushButton('重试保存')
        self.retry_button.clicked.connect(lambda: self._send('retry_save'))
        self.retry_button.setVisible(False)
        self.backup_button = QPushButton('备份未保存结果')
        self.backup_button.clicked.connect(self._backup_pending)
        self.backup_button.setVisible(False)
        self.discard_button = QPushButton('明确丢弃')
        self.discard_button.clicked.connect(self._discard_pending)
        self.discard_button.setVisible(False)
        for button in (self.preview_button, self.confirm_button, self.start_button, self.stop_button, self.privacy_button, self.retry_button, self.backup_button, self.discard_button):
            actions.addWidget(button)
        work.addLayout(actions)
        self.pages.addWidget(self.work_page)
        self._history_page()
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)
        self._buttons()

    def _source_card(self, parent):
        frame = card()
        grid = QGridLayout(frame)
        grid.setContentsMargins(14, 12, 14, 12)
        self.source_kind = combo({'LIVE_CAMERA': '实时摄像头', 'REPLAY_FILE': '本地录像回放'})
        self.source_kind.currentIndexChanged.connect(self._source_changed)
        self.backend = combo({700: 'DSHOW', 1400: 'MSMF'})
        self.backend.currentIndexChanged.connect(self._backend_changed)
        self.device = QComboBox()
        self.device.addItem('请选择设备 · 不默认打开相机', None)
        self.device.currentIndexChanged.connect(self._device_changed)
        self.refresh = QPushButton('刷新设备')
        self.refresh.clicked.connect(lambda: self._send('enumerate', backend=self.backend.currentData()))
        self.usage = combo({'SELF_USE': '自主使用', 'CONTROLLED_DEMO': '受控演示', 'TEST': '软件测试'})
        self.usage.currentIndexChanged.connect(self._invalidate)
        grid.addWidget(QLabel('视频来源'), 0, 0)
        grid.addWidget(self.source_kind, 0, 1)
        grid.addWidget(self.backend, 0, 2)
        grid.addWidget(self.device, 0, 3)
        grid.addWidget(self.refresh, 0, 4)
        grid.addWidget(self.usage, 0, 5)
        grid.setColumnStretch(3, 1)
        self.replay_row = QWidget()
        replay = QHBoxLayout(self.replay_row)
        replay.setContentsMargins(0, 0, 0, 0)
        self.file = QLineEdit()
        self.file.setPlaceholderText('选择已获许可的本地视频；回放始终保留来源标签')
        self.file.setReadOnly(True)
        browse = QPushButton('选择视频')
        browse.clicked.connect(self._browse)
        self.speed = combo({.5: '0.5× 播放', 1.: '1× 播放', 2.: '2× 播放'})
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._invalidate)
        self.seek = QDoubleSpinBox()
        self.seek.setRange(0, 86400)
        self.seek.setSuffix(' 秒起播')
        self.seek.valueChanged.connect(self._invalidate)
        self.preview_segment_button = QPushButton('预览 1.2 秒片段')
        self.preview_segment_button.clicked.connect(lambda: self._send('preview_segment'))
        replay.addWidget(self.file, 1)
        replay.addWidget(browse)
        replay.addWidget(self.speed)
        replay.addWidget(self.seek)
        replay.addWidget(self.preview_segment_button)
        grid.addWidget(self.replay_row, 1, 0, 1, 6)
        self.replay_row.setVisible(False)
        parent.addWidget(frame)

    def _setup_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = card()
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(12)
        title = QLabel('本次任务')
        title.setObjectName('sectionTitle')
        box.addWidget(title)
        self.rehab_controls = QWidget()
        form = QFormLayout(self.rehab_controls)
        form.setContentsMargins(0, 0, 0, 0)
        self.exercise = combo(EXERCISES)
        self.exercise.currentIndexChanged.connect(self._exercise_changed)
        self.submode = combo({'assessment': '评估', 'training': '训练'})
        self.submode.currentIndexChanged.connect(self._invalidate)
        self.side = combo({'left': '左侧（本人左侧）', 'right': '右侧（本人右侧）'})
        self.side.currentIndexChanged.connect(self._placement_changed)
        form.addRow('动作', self.exercise)
        form.addRow('模式', self.submode)
        form.addRow('测试侧', self.side)
        box.addWidget(self.rehab_controls)
        self.view = combo({'frontal': '正面机位', 'sagittal': '侧面机位', 'fixed': '固定观察机位'})
        self.view.currentIndexChanged.connect(self._placement_changed)
        box.addWidget(self.view)
        self.plan_text = QLabel()
        self.plan_text.setWordWrap(True)
        box.addWidget(self.plan_text)
        self.plan_button = QPushButton('设置个人目标与计划')
        self.plan_button.clicked.connect(self._plan)
        box.addWidget(self.plan_button)
        self.baselines = QWidget()
        baselinebox = QVBoxLayout(self.baselines)
        baselinebox.setContentsMargins(0, 0, 0, 0)
        baselinebox.addWidget(QLabel('舒适姿势基线 · 只在预览中记录'))
        for label, position in (('记录当前坐位', 'seated'), ('记录当前站位', 'standing')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, p=position: self._send('baseline', position=p))
            baselinebox.addWidget(button)
        self.baseline_text = QLabel('坐位：未记录  /  站位：未记录')
        self.baseline_text.setWordWrap(True)
        baselinebox.addWidget(self.baseline_text)
        box.addWidget(self.baselines)
        self.region_controls = QWidget()
        region = QVBoxLayout(self.region_controls)
        region.setContentsMargins(0, 0, 0, 0)
        region.addWidget(QLabel('圈定本场景区域'))
        self.roi_select = combo({'': '选择区域后在预览上拖动', **ROI_LABELS})
        self.roi_select.currentIndexChanged.connect(lambda: self._edit_region())
        region.addWidget(self.roi_select)
        self.roi_info = QLabel('尚未圈区')
        self.roi_info.setWordWrap(True)
        region.addWidget(self.roi_info)
        clear = QPushButton('重新圈区')
        clear.clicked.connect(self._clear_regions)
        region.addWidget(clear)
        box.addWidget(self.region_controls)
        self.activity_controls = QWidget()
        activity = QVBoxLayout(self.activity_controls)
        activity.setContentsMargins(0, 0, 0, 0)
        self.demo = QCheckBox('使用演示阈值：坐位 15 秒提醒')
        self.demo.toggled.connect(self._invalidate)
        activity.addWidget(self.demo)
        self.permission = QCheckBox('已确认本次站立 / 步行活动许可')
        self.permission.toggled.connect(self._confirmation_changed)
        activity.addWidget(self.permission)
        self.task_buttons = []
        for label, task in (('选择站立任务', 'stand'), ('选择步行任务', 'walk'), ('延期本次提醒', 'snooze'), ('拒绝本次提醒', 'skip'), ('停止活动任务', 'stop'), ('仅自报已完成', 'self_report')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, t=task: self._send('task', task=t))
            activity.addWidget(button)
            self.task_buttons.append(button)
        box.addWidget(self.activity_controls)
        self.bed_controls = QWidget()
        bed = QVBoxLayout(self.bed_controls)
        bed.setContentsMargins(0, 0, 0, 0)
        self.real_bed = QCheckBox('本次画面是真实床区')
        self.assistance = QCheckBox('已人工配置需要协助')
        self.night = QCheckBox('本次按夜间情境演示')
        for w in (self.real_bed, self.assistance, self.night):
            bed.addWidget(w)
            w.toggled.connect(self._invalidate)
        box.addWidget(self.bed_controls)
        self.mirror = QCheckBox('镜像预览（不交换解剖左右）')
        self.mirror.toggled.connect(self._mirror_changed)
        box.addWidget(self.mirror)
        self.manual = QCheckBox('已确认单人、机位与舒适动作')
        self.manual.setObjectName('manualConfirmation')
        self.manual.toggled.connect(self._confirmation_changed)
        box.addWidget(self.manual)
        self.companion = QCheckBox('陪同者已在场（计划要求时）')
        self.companion.toggled.connect(self._confirmation_changed)
        box.addWidget(self.companion)
        self.poses = QCheckBox('同意保存本次逐帧骨架供调试')
        self.poses.setToolTip('只影响本次会话。未勾选时只保存指标报告。')
        self.poses.toggled.connect(self._confirmation_changed)
        box.addWidget(self.poses)
        note = QLabel('默认不录制原始视频和截图。\n动作示范素材：待配置。\n如有疼痛、头晕或不适，请立即停止。')
        note.setObjectName('muted')
        note.setWordWrap(True)
        box.addWidget(note)
        load = QPushButton('载入已保存机位')
        load.clicked.connect(lambda: self._send('profile'))
        box.addWidget(load)
        box.addStretch()
        scroll.setWidget(panel)
        return scroll

    def _history_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        intro = QLabel('报告保存在本机。实时、回放和受控演示分别标记；不同测量条件不直接比较。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['开始时间', '任务', '来源 / 情境', '完整次数', '有效观察', '结束原因'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda: self._open_report())
        box.addWidget(self.table, 1)
        self.history_empty = QLabel('尚无历史报告。完成并保存一次任务后，记录会出现在这里。')
        self.history_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.history_empty)
        row = QHBoxLayout()
        for title, callback in (('刷新', self._history), ('打开报告', self._open_report), ('导出所选报告', self._export_selected), ('比较两份报告', self._compare), ('删除所选报告', self._delete_report), ('返回任务', lambda: self._select_scene(self.scene))):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)
        self.pages.addWidget(page)

    def _send(self, name, **kw):
        self.busy += 1
        self.pending_commands[name] += 1
        self._buttons()
        self.runtime.command(name, **kw)

    def _invalidate(self, *args):
        if self.constructing:
            return
        self.manual.setChecked(False)
        self._confirmed = False
        self.start_button.setEnabled(False)
        if self.state in ('ONLINE', 'PREVIEW', 'CONNECTING', 'ERROR'):
            self.canvas.set_frame(None)
            self._send('switch', reason='configuration_change')
        self.state = 'UNSELECTED' if self.state != 'SAVE_FAILED' else self.state
        self._buttons()

    def _source_changed(self):
        if self.constructing:
            return
        self._invalidate()
        live = self.source_kind.currentData() == 'LIVE_CAMERA'
        for w in (self.device, self.refresh, self.backend):
            w.setVisible(live)
        self.replay_row.setVisible(not live)
        self.usage.setCurrentIndex(0 if live else 2)
        self.setup['rois'] = {}
        self.setup['plan']['calibration'] = {}
        self.canvas.rois = {}
        self._sync_scene()

    def _backend_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self._send('enumerate', backend=self.backend.currentData())

    def _device_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self.setup['rois'] = {}
        self.canvas.rois = {}
        self._sync_scene()

    def _placement_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self._sync_scene()

    def _exercise_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan'] = default_plan(self.exercise.currentData())
        self.view.setCurrentIndex(self.view.findData(self.setup['plan']['view']))
        self._sync_scene()

    def _select_scene(self, scene):
        if scene != self.scene:
            self._invalidate()
            self.scene = scene
            self.setup = default_setup(scene, self.exercise.currentData())
            self.canvas.rois = {}
            self.view.setCurrentIndex(self.view.findData(self.setup['view'] if scene == 'rehab' else 'fixed'))
        self.pages.setCurrentIndex(0)
        self._sync_scene()

    def _sync_scene(self):
        self.title.setText(SCENES[self.scene])
        self.rehab_controls.setVisible(self.scene == 'rehab')
        self.plan_button.setVisible(self.scene == 'rehab')
        self.plan_text.setVisible(self.scene == 'rehab')
        self.baselines.setVisible(self.scene == 'rehab' and self.exercise.currentData() == 'sit_to_stand')
        self.region_controls.setVisible(self.scene != 'rehab')
        self.activity_controls.setVisible(self.scene == 'activity')
        self.manual.setText('已确认单人、机位与舒适动作' if self.scene == 'rehab' else '已确认单人、机位与全部区域')
        self.bed_controls.setVisible(self.scene == 'bedroom_demo')
        for key, button in self.scene_buttons.items():
            button.setChecked(key == self.scene)
        is_demo = self.scene in ('bedroom_demo', 'safety_demo')
        self.usage.setEnabled(not is_demo)
        if is_demo:
            self.usage.blockSignals(True)
            self.usage.setCurrentIndex(self.usage.findData('CONTROLLED_DEMO'))
            self.usage.blockSignals(False)
        plan = self.setup['plan']
        goal = '未设置幅度目标 · 仅测量' if plan['target_angle_deg'] is None else f"个人角度目标：{plan['target_angle_deg']:g}°"
        self.plan_text.setText(f"{plan['target_reps']} 次 × {plan['target_sets']} 组\n{goal}\n达到计划次数后提示，人工停止。")
        cal = plan.get('calibration', {})
        self.baseline_text.setText('坐位：'+('已记录' if 'seated_knee' in cal else '未记录')+' / 站位：'+('已记录' if 'standing_knee' in cal else '未记录'))
        self.subtitle.setText({'rehab': '看见每一次动作，记录可见的变化。', 'activity': '只累计画面内有证据的活动时段。',
                              'bedroom_demo': '受控区域演示 · 只报告已观察到的过程。', 'safety_demo': '受控低位演示 · 疑似事件需要人工确认。'}[self.scene])
        self.roi_info.setText('已圈定：'+('、'.join(ROI_LABELS.get(k, k) for k in self.setup['rois']) or '无'))
        labels = {'rehab': [('完整完成', ' 次'), ('二维投影角', '°')],
                  'activity': [('累计可见坐位', ' 秒'), ('连续可见坐位', ' 秒')],
                  'bedroom_demo': [('已记录状态变化', ' 次'), ('有效可见时长', ' 秒')],
                  'safety_demo': [('本次疑似事件', ' 条'), ('持续低位观察', ' 秒')]}[self.scene]
        self.count_card.configure(*labels[0])
        self.angle_card.configure(*labels[1])
        self._buttons()

    def _mirror_changed(self):
        self._invalidate()
        self.canvas.mirror = self.mirror.isChecked()
        self.canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择本地视频', '', '视频 (*.mp4 *.avi *.mov *.mkv *.wmv);;所有文件 (*)')
        if path:
            self._invalidate()
            self.file.setText(path)
            self.setup['plan']['calibration'] = {}
            self.setup['rois'] = {}
            self.canvas.rois = {}

    def _read_setup(self):
        setup = copy.deepcopy(self.setup)
        setup.update(scene_id=self.scene, view=self.view.currentData(), mirror=self.mirror.isChecked(),
                     participant_confirmed=self.manual.isChecked(), companion_confirmed=self.companion.isChecked(),
                     poses_consent=self.poses.isChecked(), activity_permission=self.permission.isChecked(),
                     demo_thresholds=self.demo.isChecked(), real_bed=self.real_bed.isChecked(),
                     needs_assistance=self.assistance.isChecked(), night_confirmed=self.night.isChecked())
        setup['plan'].update(exercise_id=self.exercise.currentData(), side=self.side.currentData(),
                             submode=self.submode.currentData(), view=self.view.currentData())
        if setup['demo_thresholds']:
            setup.update(sedentary_trigger_s=15., stand_target_s=5., walk_target_s=8.)
        return setup

    def _source(self):
        kind = self.source_kind.currentData()
        if kind == 'LIVE_CAMERA':
            d = self.device.currentData()
            if not d:
                raise ValueError('请刷新并人工选择一个摄像头')
            saved = {k: v for k, v in d.items() if k != 'index'}
            return {'kind': kind, 'device_ref': saved, 'ref': 'camera:'+digest(saved)[:24], 'usage_context': self.usage.currentData()}
        if not self.file.text() or not Path(self.file.text()).is_file():
            raise ValueError('请先选择本地视频文件')
        path = Path(self.file.text()).resolve()
        ref = 'file:'+digest({'path': str(path), 'size': path.stat().st_size, 'mtime': path.stat().st_mtime_ns})[:24]
        return {'kind': kind, 'file': str(path), 'ref': ref, 'recording_id': ref, 'usage_context': self.usage.currentData()}

    def _preview(self):
        try:
            source = self._source()
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self.manual.setChecked(False)
        if source['kind'] == 'LIVE_CAMERA':
            self.setup['plan']['calibration'] = {}
            self._sync_scene()
        self.canvas.caption = '正在连接输入'
        self.canvas.set_frame(None)
        self.last_generation = -1
        self._send('open', source=source, setup=self._read_setup(), options={'speed': self.speed.currentData(), 'seek_s': self.seek.value()})

    def _confirm(self):
        self._send('confirm', setup=self._read_setup())

    def _plan(self):
        dialog = PlanDialog(self.setup['plan'], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._invalidate()
            self.setup['plan'] = dialog.plan
            self._sync_scene()

    def _edit_region(self):
        self.canvas.edit_roi = self.roi_select.currentData() if self.state == 'PREVIEW' else None
        if self.roi_select.currentData() and self.state != 'PREVIEW':
            self.notice.setText('请先预览，再选择区域并在画面中拖出矩形。')

    def _roi_changed(self, name, roi):
        self.setup['rois'][name] = roi
        self._confirmed = False
        self.runtime.command('unconfirm')
        self.manual.setChecked(False)
        self.start_button.setEnabled(False)
        self._sync_scene()

    def _confirmation_changed(self, *args):
        if self.constructing:
            return
        self._confirmed = False
        if self.state == 'PREVIEW':
            self.runtime.command('unconfirm')
        self._buttons()

    def _clear_regions(self):
        self._invalidate()
        self.setup['rois'] = {}
        self.setup['plan']['calibration'] = {}
        self.canvas.rois = {}
        self._sync_scene()

    def _buttons(self):
        if not hasattr(self, 'preview_button'):
            return
        available = self.busy == 0
        self.preview_button.setEnabled(available and self.state not in ('ONLINE', 'SAVE_FAILED'))
        self.confirm_button.setEnabled(available and self.state == 'PREVIEW')
        self.start_button.setEnabled(available and self.state == 'PREVIEW' and getattr(self, '_confirmed', False))
        self.stop_button.setEnabled(available and self.state in ('ONLINE', 'PREVIEW', 'CONNECTING', 'ERROR'))
        self.privacy_button.setEnabled(available and self.state in ('ONLINE', 'PREVIEW', 'CONNECTING'))
        self.retry_button.setVisible(self.state == 'SAVE_FAILED')
        self.retry_button.setEnabled(available)
        self.backup_button.setVisible(self.state == 'SAVE_FAILED')
        self.discard_button.setVisible(self.state == 'SAVE_FAILED')
        self.backup_button.setEnabled(available)
        self.discard_button.setEnabled(available)
        for button in (self.preview_button, self.confirm_button, self.start_button):
            button.setVisible(self.state != 'SAVE_FAILED')
        if hasattr(self, 'poses'):
            self.poses.setEnabled(self.state != 'ONLINE' and available)
            self.manual.setEnabled(self.state != 'ONLINE' and available)
            self.roi_select.setEnabled(self.state == 'PREVIEW' and available)
            self.canvas.edit_roi = self.roi_select.currentData() if self.state == 'PREVIEW' else None
            self.permission.setEnabled(self.state != 'ONLINE' and available)
            self.preview_segment_button.setEnabled(available and self.state == 'PREVIEW' and self.source_kind.currentData() == 'REPLAY_FILE')
            for button in self.task_buttons:
                button.setEnabled(available and self.state == 'ONLINE' and self.scene == 'activity')

    def _poll(self):
        try:
            while True:
                message = self.runtime.messages.get_nowait()
                self._handle_message(message)
        except queue.Empty:
            pass
        try:
            view = self.runtime.views.get_nowait()
        except queue.Empty:
            return
        self._render_view(view)

    def _handle_message(self, m):
        kind = m['kind']
        if kind == 'command_done':
            if self.pending_commands[m['command']] > 0:
                self.pending_commands[m['command']] -= 1
                self.busy = max(0, self.busy-1)
            self._buttons()
        elif kind == 'ready':
            self._send('enumerate', backend=self.backend.currentData())
        elif kind in ('error', 'fatal'):
            self.notice.setText(m['text'])
            self._closing = False
            if kind == 'fatal':
                self.preview_button.setEnabled(False)
        elif kind == 'notice':
            self.notice.setText(m['text'])
        elif kind == 'devices':
            previous = self.device.currentData()
            self.device.blockSignals(True)
            self.device.clear()
            self.device.addItem('请选择设备 · 不默认打开相机', None)
            for d in m['devices']:
                self.device.addItem(f"{d['name']} · 当前索引 {d['index']} · {digest(d.get('path', ''))[:5]}", d)
            if previous:
                matching = [i for i in range(1, self.device.count()) if self.device.itemData(i).get('path') == previous.get('path') and self.device.itemData(i).get('backend') == previous.get('backend')]
                if previous.get('path') and len(matching) == 1:
                    self.device.setCurrentIndex(matching[0])
            self.device.blockSignals(False)
            if not m['devices']:
                self.notice.setText('此后端未枚举到相机。可人工切换后端重新枚举，或选择本地录像。')
            else:
                self.notice.setText(f"发现 {len(m['devices'])} 个设备条目；刷新仅枚举，尚未打开相机。")
        elif kind == 'confirmed':
            self.setup = m['setup']
            self._confirmed = True
            self.notice.setText('本次机位已确认。点击“开始任务”后才正式计数、计时。')
        elif kind == 'baseline':
            self._confirmed = False
            self.runtime.command('unconfirm')
            self.setup['plan']['calibration'][m['position']+'_knee'] = m['knee']
            self.setup['plan']['calibration'][m['position']+'_hip_y'] = m['hip']
            self.setup['plan']['calibration']['provenance'] = m['provenance']
            self._sync_scene()
        elif kind == 'saved':
            self.notice.setText('本次报告已保存，可在“历史报告”中重新查看。')
        elif kind == 'history':
            self.sessions = m['sessions']
            self.table.setRowCount(len(self.sessions))
            for i, s in enumerate(self.sessions):
                summary = s.get('summary', {})
                ratio = summary.get('valid_ratio')
                task_name = EXERCISES.get(s.get('exercise_id'), '康复任务') if s.get('scene_id') == 'rehab' else SCENES.get(s.get('scene_id'), '任务')
                values = [s.get('start_utc', '').replace('T', ' ')[:19]+' UTC', task_name,
                          SOURCES.get(s.get('source_kind'), '未知')+' / '+CONTEXTS.get(s.get('usage_context'), '未知'),
                          str(summary.get('completed', '—')), '—' if ratio is None else f'{ratio*100:.0f}%', s.get('stop_reason', s.get('status', '未知'))]
                for j, value in enumerate(values):
                    self.table.setItem(i, j, QTableWidgetItem(value))
                self.table.setRowHeight(i, 54)
            self.history_empty.setVisible(not self.sessions)
        elif kind == 'report':
            dialog = ReportDialog(m['snapshot'], m['html'], self._export, self)
            self.report_windows.append(dialog)
            dialog.show()
        elif kind == 'events':
            if self.events_dialog:
                self.events_dialog.populate(m['events'])
        elif kind == 'profiles':
            try:
                source = self._source()
            except ValueError as exc:
                self.notice.setText(str(exc))
                return
            candidates = [p for p in m['profiles'] if p['scene_id'] == self.scene and p.get('source_ref') == source['ref']
                          and p['plan']['exercise_id'] == self.exercise.currentData() and p['plan']['side'] == self.side.currentData()]
            if not candidates:
                self.notice.setText('当前来源、场景、动作与侧别下尚无可载入机位。')
                return
            names = [f"机位 {i+1} · {p.get('setup_confirmed_at', '')[:19]}" for i, p in enumerate(candidates)]
            chosen, ok = QInputDialog.getItem(self, '载入机位候选', '载入后需要重新预览确认：', names, 0, False)
            if ok:
                self._invalidate()
                self.setup = copy.deepcopy(candidates[names.index(chosen)])
                self.setup['participant_confirmed'] = False
                self.canvas.rois = copy.deepcopy(self.setup['rois'])
                self.view.blockSignals(True)
                self.view.setCurrentIndex(self.view.findData(self.setup['view']))
                self.view.blockSignals(False)
                self._sync_scene()
        elif kind == 'shutdown_done':
            self._allow_close = True
            self.close()

    def _render_view(self, data):
        context = data.get('context')
        if context and context.scene_id != self.scene:
            return
        if context and context.generation < self.last_generation:
            return
        if context:
            self.last_generation = context.generation
        self.state = data['state']
        self._confirmed = data['confirmed']
        self.status_badge.setText(STATUS.get(self.state, self.state))
        self.coverage.setText(('当前活动：'+SCENES[self.scene] if self.state == 'ONLINE' else '当前未开始监测')+'\n\n其余三个场景未监测\n每次仅运行一路输入')
        packet, pose = data.get('packet'), data.get('pose')
        if packet:
            self.canvas.set_frame(packet, pose)
            self.source_badge.setText(SOURCES.get(packet.context.source_kind, '')+' / '+CONTEXTS.get(packet.context.usage_context, '')+(' · 演示阈值' if self.demo.isChecked() and self.scene == 'activity' else ''))
            h, w = packet.image.shape[:2]
            fps = packet.received_fps
            self.frame_info.setText(f'{w} × {h}  ·  '+('速率测量中' if fps is None else f'接收 {fps:.1f} fps')+(f' · 推理 {pose.inference_ms:.0f} ms' if pose else ''))
        elif self.state not in ('PREVIEW', 'ONLINE'):
            self.canvas.set_frame(None)
            self.canvas.caption = STATUS.get(self.state, '输入未打开')
            self.canvas.subcaption = '点击预览重新打开；确认机位后再开始新的任务' if self.state == 'PRIVACY_PAUSED' else '选择一个视频来源，预览并确认机位后开始'
            self.canvas.update()
        summary = data.get('summary', {})
        metrics = summary.get('metrics', {})
        if pose and self.state == 'PREVIEW':
            # Preview readout only. Business processing stays in the runtime worker.
            # Use model confidence in debug without calculating a second action result.
            self.debug.setPlainText(dumps({'people': len(pose.people), 'keypoint_confidence': [p.conf for p in pose.people],
                                           'schema': pose.schema_id, 'inference_ms': pose.inference_ms}, indent=2))
        if summary:
            if self.scene == 'rehab':
                self.count_card.show_value(summary.get('completed'))
                angle = metrics.get('raise_deg' if self.exercise.currentData() == 'shoulder_abduction' else 'knee_flexion_deg', {}).get('value')
                self.angle_card.show_value(None if angle is None else f'{angle:.1f}')
            elif self.scene == 'activity':
                self.count_card.show_value(f"{summary.get('totals', {}).get('SEATED', 0):.1f}")
                self.angle_card.show_value(f"{summary.get('continuous_sitting_s', 0):.1f}")
            elif self.scene == 'bedroom_demo':
                self.count_card.show_value(len(summary.get('observations', [])))
                self.angle_card.show_value(f"{summary.get('valid_s', 0):.1f}")
            else:
                self.count_card.show_value(summary.get('event_count', 0))
                self.angle_card.show_value(f"{summary.get('low_observed_s', 0):.1f}")
            ratio = summary.get('valid_ratio')
            self.valid_card.show_value(None if ratio is None else f'{ratio*100:.0f}')
            phase = PHASES.get(summary.get('phase'), summary.get('phase', ''))
            self.feedback.setText(phase+' · '+summary.get('message', ''))
            self.debug.setPlainText(dumps(summary, indent=2))
        elif self.state not in ('ONLINE',):
            for c in (self.count_card, self.angle_card, self.valid_card):
                c.show_value(None)
            self.feedback.setText('预览尚未计数、计时。请确认单人站位与可见关节。' if self.state == 'PREVIEW' else '本次任务结束后，可在历史报告中查看结果。' if data.get('last_saved_id') else '准备开始：选择输入 → 预览 → 确认机位 → 开始任务')
        if data.get('error'):
            self.notice.setText(data['error'])
        observed = data.get('observation_status')
        if observed in ('NO_PERSON_DETECTED', 'MULTI_PERSON', 'UNKNOWN'):
            self.feedback.setText({'NO_PERSON_DETECTED': '未检测到人 · 当前画面没有足够人体证据，不等于确认房间无人。',
                                   'MULTI_PERSON': '检测到多人 · 请重新确认单一参与者，暂不归属个人动作。',
                                   'UNKNOWN': '人物或动作未知 · 当前证据不足，暂不评价。'}[observed])
        self._buttons()

    def _history(self):
        self.title.setText('历史报告')
        self.pages.setCurrentIndex(1)
        self._send('history')

    def _selected(self):
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _open_report(self):
        rows = self._selected()
        if rows:
            self._send('report', id=self.sessions[rows[0]]['id'])

    def _export_selected(self):
        rows = self._selected()
        if rows:
            self._export(self.sessions[rows[0]]['id'])

    def _export(self, sid):
        parent = QFileDialog.getExistingDirectory(self, '选择导出文件夹')
        if parent:
            out = Path(parent)/('session-'+sid[:12])
            self._send('export', id=sid, directory=str(out))

    def _delete_report(self):
        rows = self._selected()
        if not rows:
            return
        if QMessageBox.question(self, '删除报告', '删除所选的一份本地报告？已生成的待处理事件会继续保留。') == QMessageBox.StandardButton.Yes:
            self._send('delete', id=self.sessions[rows[0]]['id'])

    def _compare(self):
        rows = self._selected()
        if len(rows) != 2:
            self.notice.setText('按住 Ctrl 选择两份报告再比较。')
            return
        a, b = (self.sessions[i] for i in rows)
        if not compatible_reports(a, b):
            QMessageBox.information(self, '条件不同', '两份报告的参与者、动作、侧别、机位、来源或规则条件不同，不宜直接比较。')
        else:
            QMessageBox.information(self, '相同条件记录对照', f"完整次数：{a['summary'].get('completed', '—')} / {b['summary'].get('completed', '—')}\n这是两次任务记录，不自动解释为康复改善。")

    def _events(self):
        if self.events_dialog is None:
            self.events_dialog = EventsDialog(self.runtime, self)
        self.events_dialog.show()
        self.events_dialog.raise_()
        self.runtime.command('events')

    def _backup_pending(self):
        directory = QFileDialog.getExistingDirectory(self, '选择可写的备份目录')
        if directory:
            self._send('backup_pending', directory=directory)

    def _discard_pending(self):
        reason, accepted = QInputDialog.getText(self, '丢弃未保存结果', '此操作会放弃本次未保存结果。建议先备份。\n输入丢弃原因以确认：')
        if accepted and reason.strip():
            self._send('discard_pending', reason=reason)

    def closeEvent(self, event):
        if self._allow_close:
            self.timer.stop()
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self.notice.setText('正在停止采集并保存本次任务…')
            self._send('shutdown')
