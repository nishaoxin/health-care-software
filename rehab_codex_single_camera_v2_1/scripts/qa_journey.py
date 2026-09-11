"""Synthetic native layout evidence only; never opens cameras or user data."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import queue
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.ui.main_window import MainWindow
from app.ui.dialogs import ReportDialog
from app.reports import render_report
from test_result_summary import snapshot
from test_dual_ui import select_pair


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views, self.calls = queue.Queue(), queue.Queue(), []

    def command(self, name, **kwargs):
        self.calls.append((name, kwargs))
        self.messages.put(dict(kind='command_done', command=name))


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    output = ROOT/'.runtime/qa-journey-v015'
    output.mkdir(parents=True, exist_ok=True)
    w = MainWindow(runtime=PassiveRuntime())
    w.show()

    def capture(widget, name):
        w._poll()
        for _ in range(3):
            app.processEvents()
        assert widget.grab().save(str(output/(name+'.png')))
        print(name, widget.width(), widget.height())

    try:
        for width, height in ((1100, 730), (1360, 900)):
            w.state = 'UNSELECTED'
            w.resize(width, height)
            w._choose_catalog_exercise('neck_flexion')
            select_pair(w, app)
            w._render_view(dict(state='PREVIEW', confirmed=False, summary={}, context=None))
            w.canvas.caption = '合成布局检查 · 没有打开摄像头'
            w.canvas.subcaption = ''
            capture(w, f'framing-{width}')
            w._journey_framed = True
            w._buttons()
            capture(w, f'rest-{width}')
            w._journey_next()
            w._handle_message(dict(kind='preparation', active=True, text='3 秒后记录，请保持姿势'))
            capture(w, f'countdown-{width}')
            w._handle_message(dict(kind='preparation', active=False, text='已记录起点'))
            w.setup['plan']['joint_baseline'] = {'rest_value': 0.}
            w._buttons()
            capture(w, f'direction-{width}')
            w.setup['plan']['joint_baseline']['direction_sign'] = 1
            w._buttons()
            capture(w, f'confirm-{width}')
            w._render_view(dict(state='SAVE_FAILED', confirmed=False, summary={}, context=None,
                                error='合成测试：报告保存失败，请重试或备份。'))
            capture(w, f'save-failed-{width}')
        s = snapshot()
        report = ReportDialog(s, render_report(s), lambda sid: None, w)
        report.resize(1020, 680)
        report.show()
        capture(report, 'report-overview')
        report.overview.verticalScrollBar().setValue(report.overview.verticalScrollBar().maximum())
        capture(report, 'report-bottom')
        report.close()
    finally:
        w._allow_close = True
        w.close()


if __name__ == '__main__':
    main()
