"""Native UI layout fixtures only; never opens a camera or writes clinical data."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import argparse
from pathlib import Path
import queue
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app.ui.main_window import MainWindow


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()

    def command(self, name, **kwargs):
        if name == 'stop_camera_test':
            self.messages.put(dict(kind='camera_test_stopped'))
        self.messages.put(dict(kind='command_done', command=name))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output/body-camera-v08')
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    w = MainWindow(runtime=PassiveRuntime())
    w._handle_message(dict(kind='devices', backend=700, devices=[
        dict(name='测试摄像头（仅界面测试）', path='layout-fixture', backend=700, index=9)]))
    w.show()

    def capture(name, widget=w):
        w._poll()
        for _ in range(3):
            app.processEvents()
        assert widget.grab().save(str(output/(name+'.png')))
        print(name, widget.width(), widget.height())

    try:
        for size in ((1100, 730), (1360, 900), (1600, 1000)):
            w.resize(*size)
            # The fresh entry intentionally has no preselected part.
            if size[0] == 1100:
                capture('entry-1100')
            for joint in ('shoulder', 'finger', 'knee'):
                w.catalog.select_joint(joint)
                capture(f'{joint}-{size[0]}')
        w.camera_test_button.click()
        dialog = w.camera_test_dialog
        capture('camera-connecting-layout-only', dialog)
        dialog.show_error('界面测试：设备被占用，请关闭占用它的软件后重试。')
        capture('camera-error-layout-only', dialog)
        dialog.stop_button.click()
        w._poll()
        capture('returned-to-category')
    finally:
        w._allow_close = True
        w.close()


if __name__ == '__main__':
    main()
