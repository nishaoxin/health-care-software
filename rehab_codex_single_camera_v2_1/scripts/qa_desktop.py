"""Render application-owned UI states only. No camera or private screen capture."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import queue
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.ui.dialogs import PlanDialog, EventsDialog
from app.settings import default_plan


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()
    def command(self, name, **kwargs):
        pass


app = QApplication([])
app.setStyle('Fusion')
for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/name))
out = ROOT/'qa-output'
out.mkdir(exist_ok=True)
window = MainWindow(runtime=PassiveRuntime())
window.show()
for scene in ('rehab', 'activity', 'bedroom_demo', 'safety_demo'):
    window._select_scene(scene)
    app.processEvents()
    window.grab().save(str(out/f'{scene}.png'))
window._history()
app.processEvents()
window.grab().save(str(out/'history-empty.png'))
plan = PlanDialog(default_plan(), window)
plan.show()
app.processEvents()
plan.grab().save(str(out/'plan.png'))
plan.close()
window._allow_close = True
window.close()
print('Rendered four scene layouts, empty history and plan dialog; no camera opened.')
