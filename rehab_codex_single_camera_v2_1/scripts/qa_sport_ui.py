"""Render the real v0.6 desktop UI with explicit in-memory SYNTHETIC/TEST states."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import queue
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.assessment import build_body_profile
from app.ui.main_window import MainWindow


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()

    def command(self, name, **kwargs):
        self.messages.put({'kind': 'command_done', 'command': name})


app = QApplication([])
app.setStyle('Fusion')
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / font))
output = ROOT / 'qa-output' / 'sport-v06'
output.mkdir(parents=True, exist_ok=True)
w = MainWindow(runtime=PassiveRuntime())
w.show()


def capture(name):
    w._poll()
    for _ in range(3):
        app.processEvents()
    assert w.grab().save(str(output / (name + '.png')))
    print(name, w.width(), w.height())


try:
    for width, height in ((1100, 730), (1360, 900), (1600, 1000)):
        w.resize(width, height)
        w._show_catalog()
        w.catalog.search.clear()
        w.catalog.select_joint('all')
        capture(f'catalog-{width}')
        w.catalog.search.setText('不存在的动作')
        capture(f'empty-search-{width}')
        w._show_training_hub()
        capture(f'training-center-{width}')
        w._choose_catalog_exercise('wrist_flexion')
        w.exercise_guide.step_buttons[1].click()
        capture(f'action-guide-{width}')
        w.setup_tabs.setCurrentIndex(1)
        capture(f'preparation-{width}')
    w.resize(1360, 900)
    w.source_kind.addItem('合成布局测试', 'SYNTHETIC')
    w.source_kind.setCurrentIndex(w.source_kind.findData('SYNTHETIC'))
    w.usage.setCurrentIndex(w.usage.findData('TEST'))
    w._poll()
    profile = build_body_profile([], **w._body_scope_key())
    profile['items'][0].update(status='ASSESSED', session_id='synthetic-sport-ui',
                               motion_range={'min_deg': 0, 'max_deg': 60, 'range_deg': 60})
    w._handle_message({'kind': 'body_profile', 'profile': profile, 'html': 'SYNTHETIC / TEST'})
    w._train_from_body()
    w._show_training_hub()
    capture('training-with-unconfirmed-plan')
    w.training_hub.resume.click()
    w.setup_tabs.setCurrentIndex(0)
    w._render_view(dict(state='ONLINE', context=None, confirmed=True, observation_status='VALID',
                        summary={'phase': 'RAISING', 'completed': 2, 'valid_ratio': .9,
                                 'metrics': {'raise_deg': {'value': 42, 'valid': True}},
                                 'training': {'stage': 'ACTIVE', 'exercise_label': '肩外展', 'side': 'left',
                                              'set_number': 1, 'target_sets': 2, 'target_reps': 8,
                                              'set_reps': 2, 'can_pause': True}}))
    capture('training-active-SYNTHETIC')
    w._render_view(dict(state='OFFLINE', context=None, confirmed=False, summary={}))
    capture('offline-SYNTHETIC')
    w._render_view(dict(state='SAVE_FAILED', context=None, confirmed=False, summary={},
                        error='合成测试：报告尚未保存，请重试或备份。'))
    capture('save-failure-SYNTHETIC')
finally:
    w._allow_close = True
    w.close()
