"""Render actual Qt product states using in-memory SYNTHETIC/TEST data only."""
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
from app.reports import render_body_profile
from app.assessment import build_body_profile


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()

    def command(self, name, **kwargs):
        self.messages.put({'kind': 'command_done', 'command': name})


app = QApplication([])
app.setStyle('Fusion')
for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/name))
output = ROOT/'qa-output'/'product-v04'
output.mkdir(parents=True, exist_ok=True)
window = MainWindow(runtime=PassiveRuntime())
window.show()


def capture(name):
    window._poll()
    app.processEvents()
    path = output/(name+'.png')
    if not window.grab().save(str(path)):
        raise RuntimeError('Could not save '+str(path))
    print(name, window.width(), window.height())


for width, height in ((1100, 730), (1360, 900), (1600, 1000)):
    window.resize(width, height)
    window._show_catalog()
    window.catalog.search.clear()
    window.catalog.select_joint('all')
    capture(f'catalog-{width}')
    window.catalog.select_joint('finger')
    capture(f'fingers-{width}')
    window._choose_catalog_exercise('wrist_flexion')
    capture(f'workspace-{width}')
    window.source_options.toggle.setChecked(True)
    capture(f'input-settings-{width}')
    window.source_options.toggle.setChecked(False)

window.resize(1360, 900)
window._show_body()
window._poll()
profile = build_body_profile([], **window._body_scope_key())
window._handle_message({'kind': 'body_profile', 'profile': profile, 'html': render_body_profile(profile, compact=True)})
capture('body-empty')

window._select_rehab('assessment')
window.source_kind.addItem('合成布局测试', 'SYNTHETIC')
window.source_kind.setCurrentIndex(window.source_kind.findData('SYNTHETIC'))
window._poll()
profile = build_body_profile([], **window._body_scope_key())
# Explicit synthetic data; no user storage, camera, or model involved.
profile['items'][0].update(status='ASSESSED', session_id='synthetic-layout-1',
                          motion_range={'min_deg': 0, 'max_deg': 60, 'range_deg': 60},
                          valid_ratio=.85, start_utc='2026-09-08T00:00:00+00:00')
profile['items'][1].update(status='UNAVAILABLE', session_id='synthetic-layout-2', valid_ratio=0)
profile['assessed_count'] = 1
window._show_body()
window._poll()
window._handle_message({'kind': 'body_profile', 'profile': profile, 'html': render_body_profile(profile, compact=True)})
capture('body-synthetic')
window._train_from_body()
capture('training-linked-synthetic')
window._render_view({'state': 'SAVE_FAILED', 'context': None, 'confirmed': False,
                     'summary': {}, 'error': '测试状态：报告尚未保存，请重试或备份。'})
capture('save-failure-synthetic')
window._allow_close = True
window.close()
