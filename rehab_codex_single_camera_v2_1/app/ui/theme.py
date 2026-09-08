"""Shared native desktop theme. No stylesheet changes measurement behaviour."""
from ..settings import ROOT

STYLE = '''
QMainWindow, QDialog { background:#f5f6f8; }
QWidget#scrollContent { background:#f5f6f8; }
QWidget { color:#25352f; font-family:'Microsoft YaHei UI'; font-size:14px; }
QWidget:disabled { color:#8b9691; }
QLabel { background:transparent; }
QFrame#sidebar { background:#ffffff; border-right:1px solid #e2e7e3; }
QLabel#brand { color:#1d4938; font-size:22px; font-weight:700; }
QLabel#brandMark { background:#285641; color:white; border-radius:12px; font-size:25px; font-weight:700; }
QLabel#navHeading { color:#8a948e; font-size:12px; padding:0 12px; }
QLabel#pageTitle { color:#1f3329; font-size:27px; font-weight:700; }
QLabel#sectionTitle { font-size:18px; font-weight:700; }
QLabel#muted { color:#6c7b73; font-size:13px; }
QLabel#eyebrow { color:#73816f; font-size:12px; }
QLabel#badge { color:#4e6558; background:#e8eee8; border-radius:13px; padding:6px 12px; font-size:13px; }
QLabel#badge[tone="active"] { background:#dceee3; color:#1e6847; }
QLabel#badge[tone="error"] { background:#fae9e4; color:#994c35; }
QLabel#badge[tone="preview"] { background:#e5edf8; color:#3a6081; }
QFrame#card, QFrame#metricCard, QFrame#exerciseCard { background:white; border:1px solid #e1e6e2; border-radius:12px; }
QFrame#exerciseCard:hover { border-color:#9aaf9f; }
QFrame#taskHeader { background:white; border:1px solid #e1e6e2; border-radius:10px; }
QFrame#personBar { background:white; border:1px solid #e1e6e2; border-radius:9px; }
QLabel#metricValue { color:#233e30; font-size:30px; font-weight:600; }
QLabel#tag { color:#5f7265; background:#f0f4f0; border-radius:5px; padding:4px 8px; font-size:12px; }
QLabel#tag[experimental="true"] { color:#95612f; background:#fbf0df; }
QPushButton { background:white; border:1px solid #d9e1da; border-radius:8px; padding:8px 12px; min-height:24px; }
QPushButton:hover { background:#f1f6f1; border-color:#9daf9f; }
QPushButton:pressed { background:#e6eee6; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QToolButton:focus { border:2px solid #527b60; }
QPushButton:disabled { color:#91a095; background:#f0f3f0; border-color:#e5e9e4; }
QPushButton#primary { background:#315e46; color:white; border-color:#315e46; font-weight:600; }
QPushButton#primary:hover { background:#264e39; }
QPushButton#primary:disabled { color:#eef3ee; background:#a9bdb0; border-color:#a9bdb0; }
QPushButton#danger { color:#a44c38; background:#fff7f3; border-color:#e8d1c7; }
QPushButton#nav { color:#68766c; background:transparent; border:0; text-align:left; padding:12px 14px; min-height:24px; }
QPushButton#nav:checked { background:#e9f0e7; color:#244c35; font-weight:700; }
QPushButton#nav:hover { background:#f0f4ed; }
QPushButton#nav:focus { border:1px solid #527b60; }
QPushButton#filter { padding:8px 13px; border:1px solid transparent; background:transparent; color:#6b7970; }
QPushButton#filter:checked { background:#315e46; color:white; }
QPushButton#filter:hover:!checked { background:#e9efe8; }
QPushButton#textButton { background:transparent; border:0; color:#366847; padding:4px 6px; }
QToolButton { border:0; background:transparent; color:#67766b; padding:8px; text-align:left; }
QToolButton:hover { background:#edf2eb; border-radius:6px; }
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox { border:1px solid #dbe2dc; border-radius:7px; background:white; padding:7px 10px; min-height:24px; selection-background-color:#d9e7d9; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox::down-arrow { image:url(__ASSETS__/chevron.svg); width:12px; height:12px; }
QComboBox QAbstractItemView { background:white; selection-background-color:#e5eee1; color:#25352f; padding:4px; }
QCheckBox { spacing:8px; background:transparent; padding:3px 0; }
QCheckBox::indicator { width:18px; height:18px; border:1px solid #9cb09e; border-radius:4px; background:white; }
QCheckBox::indicator:checked { background:#315e46; border-color:#315e46; image:url(__ASSETS__/check.svg); }
QCheckBox::indicator:disabled { border-color:#d7dfd6; background:#f0f3ed; }
QLabel#feedback { background:#eaf0e5; color:#3d5941; padding:12px 14px; border-radius:9px; }
QLabel#notice { color:#855731; background:#faf0df; padding:9px 13px; border-radius:7px; }
QLabel#safetyNote { color:#8a6247; font-size:12px; }
QTableWidget { background:white; alternate-background-color:#f8faf7; border:1px solid #e1e7df; border-radius:8px; gridline-color:#e9eee6; selection-background-color:#e0eadb; selection-color:#273a2d; }
QHeaderView::section { background:#f0f4ed; color:#64765f; border:0; padding:12px; }
QTableWidget::item { padding:8px; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { width:8px; background:transparent; }
QScrollBar::handle:vertical { background:#cfd9cc; border-radius:4px; min-height:32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QPlainTextEdit, QTextBrowser { background:white; border:1px solid #e1e7df; border-radius:8px; padding:12px; }
QToolTip { color:#25352f; background:#ffffff; border:1px solid #bac9b7; padding:8px; }
'''.replace('__ASSETS__', (ROOT/'assets/ui').as_posix())
