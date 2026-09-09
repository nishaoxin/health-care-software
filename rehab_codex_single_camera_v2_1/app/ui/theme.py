"""Shared native desktop theme. No stylesheet changes measurement behaviour."""
from ..settings import ROOT

STYLE = '''
QMainWindow, QDialog { background:#f5f4f8; }
QWidget#scrollContent { background:#f5f4f8; }
QWidget { color:#292536; font-family:'Microsoft YaHei UI'; font-size:15px; }
QWidget:disabled { color:#85818d; }
QLabel { background:transparent; }
QFrame#sidebar { background:#ffffff; border-right:1px solid #e8e4f0; }
QLabel#brand { color:#34234f; font-size:22px; font-weight:700; }
QLabel#brandMark { background:#7048df; color:white; border-radius:12px; font-size:25px; font-weight:700; }
QLabel#navHeading { color:#81788d; font-size:12px; padding:0 12px; }
QLabel#pageTitle { color:#292135; font-size:27px; font-weight:700; }
QLabel#sectionTitle { font-size:18px; font-weight:700; }
QLabel#muted { color:#726b80; font-size:14px; }
QLabel#eyebrow { color:#817191; font-size:12px; }
QLabel#badge { color:#645473; background:#ede8f5; border-radius:13px; padding:6px 12px; font-size:14px; }
QLabel#badge[tone="active"] { background:#e2f3e8; color:#296c45; }
QLabel#badge[tone="error"] { background:#fae9e4; color:#994c35; }
QLabel#badge[tone="preview"] { background:#e5edf8; color:#3a6081; }
QFrame#card, QFrame#metricCard, QFrame#exerciseCard { background:white; border:1px solid #e6e1ed; border-radius:12px; }
QFrame#exerciseCard:hover { border-color:#b49adc; }
QFrame#taskHeader { background:white; border:1px solid #e6e1ed; border-radius:10px; }
QFrame#personBar { background:white; border:1px solid #e6e1ed; border-radius:9px; }
QLabel#metricValue { color:#4b306d; font-size:30px; font-weight:600; }
QLabel#tag { color:#69547f; background:#f0ebf8; border-radius:5px; padding:4px 8px; font-size:12px; }
QLabel#tag[experimental="true"] { color:#95612f; background:#fbf0df; }
QPushButton { background:white; border:1px solid #ded6eb; border-radius:8px; padding:8px 12px; min-height:24px; }
QPushButton:hover { background:#f4effb; border-color:#aa8ecd; }
QPushButton:pressed { background:#e9def8; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QToolButton:focus { border:2px solid #7851bb; }
QPushButton:disabled { color:#898193; background:#eeebf2; border-color:#e4deec; }
QPushButton#primary { background:#7048df; color:white; border-color:#7048df; font-weight:600; }
QPushButton#primary:hover { background:#5c37c6; }
QPushButton#primary:disabled { color:#ffffff; background:#b6a8d7; border-color:#b6a8d7; }
QPushButton#danger { color:#a44c38; background:#fff7f3; border-color:#e8d1c7; }
QPushButton#nav { color:#777083; background:transparent; border:0; text-align:left; padding:12px 14px; min-height:24px; }
QPushButton#nav:checked { background:#efe8fb; color:#6740c6; font-weight:700; }
QPushButton#nav:hover { background:#f1ecf8; }
QPushButton#nav:focus { border:1px solid #7851bb; }
QPushButton#filter { padding:8px 13px; border:1px solid transparent; background:transparent; color:#72667f; }
QPushButton#filter:checked { background:#7048df; color:white; }
QPushButton#filter:hover:!checked { background:#eae3f3; }
QPushButton#textButton { background:transparent; border:0; color:#7048cf; padding:4px 6px; }
QToolButton { border:0; background:transparent; color:#776985; padding:8px; text-align:left; }
QToolButton:hover { background:#efe8f7; border-radius:6px; }
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox { border:1px solid #ded6e8; border-radius:7px; background:white; padding:7px 10px; min-height:24px; selection-background-color:#e7ddf7; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox::down-arrow { image:url(__ASSETS__/chevron.svg); width:12px; height:12px; }
QComboBox QAbstractItemView { background:white; selection-background-color:#e8dff9; color:#292536; padding:4px; }
QCheckBox { spacing:8px; background:transparent; padding:3px 0; }
QCheckBox::indicator { width:18px; height:18px; border:1px solid #a18fb4; border-radius:4px; background:white; }
QCheckBox::indicator:checked { background:#7048df; border-color:#7048df; image:url(__ASSETS__/check.svg); }
QCheckBox::indicator:disabled { border-color:#ded6e8; background:#f0edf5; }
QLabel#feedback { background:#eee7fa; color:#584373; padding:12px 14px; border-radius:9px; }
QLabel#notice { color:#855731; background:#faf0df; padding:9px 13px; border-radius:7px; }
QLabel#safetyNote { color:#8a6247; font-size:12px; }
QTableWidget { background:white; alternate-background-color:#faf8fc; border:1px solid #e7e0ef; border-radius:8px; gridline-color:#ece6f3; selection-background-color:#e9def9; selection-color:#37284a; }
QHeaderView::section { background:#f1ecf8; color:#786789; border:0; padding:12px; }
QTableWidget::item { padding:8px; }
QProgressBar { border:0; border-radius:5px; background:#eee8f5; color:#4f366b; text-align:center; font-size:12px; }
QProgressBar::chunk { background:#a585ec; border-radius:5px; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { width:8px; background:transparent; }
QScrollBar::handle:vertical { background:#d5c9e3; border-radius:4px; min-height:32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QPlainTextEdit, QTextBrowser { background:white; border:1px solid #e7e0ef; border-radius:8px; padding:12px; }
QToolTip { color:#292536; background:#ffffff; border:1px solid #b9a4d0; padding:8px; }

QFrame#journeyHero { background:#30233f; border:0; border-radius:18px; }
QLabel#heroTitle { color:#ffffff; font-size:26px; font-weight:700; }
QLabel#heroEyebrow { color:#c9efa8; font-size:11px; letter-spacing:2px; }
QLabel#heroDescription { color:#d4c9e1; font-size:14px; }
QPushButton#heroAction { color:#263518; background:#c7ec9f; border:0; border-radius:10px; font-weight:700; padding:10px 18px; }
QPushButton#heroAction:hover { background:#d9f6ba; }
QPushButton#heroSecondary { color:#eee6f5; background:#493657; border:1px solid #69527b; padding:7px 16px; }
QFrame#courseCover { background:#eee6f8; border:0; border-radius:10px; }
QLabel#coverCategory { color:#5c3c82; font-size:16px; font-weight:700; }
QLabel#coverMeta { color:#80708f; font-size:12px; }
QFrame#guideCard { background:#f6f1fc; border:1px solid #e4d8f3; border-radius:12px; }
QLabel#guidePicture { background:#ece3f5; color:#81708f; border:1px dashed #c7b5dc; border-radius:10px; font-size:14px; }
QLabel#guideInstruction { color:#33283f; font-size:16px; font-weight:600; }
QPushButton#stepTab { color:#7b688d; background:transparent; border:0; padding:5px 4px; min-height:28px; }
QPushButton#stepTab:checked { color:white; background:#7048df; border-radius:8px; }
QPushButton#stepTab:focus { border:2px solid #4b2d91; }
QLabel#planSummary { background:#f2ecfa; color:#56416f; padding:16px; border-radius:10px; font-size:17px; }
QLabel#journeyNumber { color:#8e67d7; font-size:27px; font-weight:700; }
QScrollBar:horizontal { height:7px; background:transparent; }
QScrollBar::handle:horizontal { background:#d5c9e3; border-radius:3px; min-width:30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QTabWidget#coachTabs::pane { border:0; background:transparent; }
QTabBar::tab { color:#776389; background:#ede6f5; padding:11px 18px; min-width:110px; border:0; }
QTabBar::tab:selected { color:#6940c9; background:white; border-bottom:3px solid #7048df; font-weight:700; }
QTabBar::tab:focus { border:2px solid #7851bb; }

'''.replace('__ASSETS__', (ROOT/'assets/ui').as_posix())
