"""Native-window layout fixtures only: no camera, model or participant data."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import queue
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.ui.main_window import MainWindow
from app.ui.distance_coach import DistanceCoach
from app.settings import default_plan


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()

    def command(self, name, **kwargs):
        self.messages.put(dict(kind='command_done', command=name))


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    out = ROOT/'qa-output/neck-shoulder-v091'
    out.mkdir(parents=True, exist_ok=True)
    w = MainWindow(runtime=PassiveRuntime())
    c = DistanceCoach(w)
    w.show()

    def capture(widget, name):
        w._poll()
        for _ in range(3):
            app.processEvents()
        assert widget.grab().save(str(out/(name+'.png')))
        print(name, widget.width(), widget.height())

    try:
        for width, height in ((1100, 730), (1360, 900)):
            w.resize(width, height)
            w._choose_catalog_exercise('shoulder_adduction')
            w.setup['plan']['joint_baseline'] = {'rest_value': 55.}
            w._sync_scene()
            w.setup_tabs.setCurrentIndex(1)
            w.canvas.caption, w.canvas.subcaption = '合成布局测试', '没有打开摄像头'
            w._render_view(dict(state='PREVIEW', context=None, confirmed=False, summary={},
                                measurement_hint='侧抬臂起点 55°；向身体收回后，再抬回起点计 1 次。'))
            capture(w, f'shoulder-start-{width}')
            w.state = 'UNSELECTED'
            w._choose_catalog_exercise('neck_flexion')
            w.setup_tabs.setCurrentIndex(1)
            w.canvas.caption, w.canvas.subcaption = '合成布局测试', '没有打开摄像头'
            hint = '未看清：左髋；让测试侧朝向镜头，同侧眼、耳、肩、髋入镜。'
            w._render_view(dict(state='PREVIEW', context=None, confirmed=False, summary={}, measurement_hint=hint))
            capture(w, f'neck-missing-hip-{width}')
            c.resize(width, height)
            c.show()
            c.render(dict(state='ONLINE', observation_status='VALID', summary={'metrics': {}}, measurement_hint=hint),
                     default_plan('neck_flexion'), mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
            capture(c, f'neck-large-hint-{width}')
            c.hide()
    finally:
        c.close()
        w._allow_close = True
        w.close()


if __name__ == '__main__':
    main()
