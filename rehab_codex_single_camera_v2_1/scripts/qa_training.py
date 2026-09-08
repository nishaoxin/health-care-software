"""Native UI and production command dispatch with explicit synthetic pose input.

Camera/model are not used. All records are in a temporary test database.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import queue
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.runtime import Runtime
from app.audio import AudioGate
from app.ui.main_window import MainWindow
from app.ui.dialogs import PlanDialog
from app.reports import render_report
from test_app_controller import ControllerTests


class FixtureRuntime(Runtime):
    """Use production dispatch in one controlled test thread, not live capture."""
    def __init__(self, fixture):
        self.controller, self.store, self.camera = fixture.c, fixture.store, fixture.camera
        self.messages, self.views = queue.Queue(), queue.Queue(maxsize=1)
        self.audio = AudioGate()
        self.vision = SimpleNamespace(clear=lambda: None)
        self.commands = queue.Queue()
        self.preview_history = []
        self.last_sound_count, self.last_sound_event = 0, None

    def command(self, name, **kwargs):
        self.commands.put((name, kwargs))

    def pump(self):
        while not self.commands.empty():
            name, kwargs = self.commands.get_nowait()
            try:
                self._execute(name, kwargs)
            except Exception as exc:
                self._message('error', command=name, text=str(exc))
            finally:
                self._message('command_done', command=name)


app = QApplication([])
app.setStyle('Fusion')
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
output = ROOT/'qa-output'/'training'
output.mkdir(parents=True, exist_ok=True)
fixture = ControllerTests()
fixture.setUp()
window = None
try:
    reference = fixture._assessment_reference()
    fixture.setup['plan'].update(target_reps=1, target_sets=2, rest_between_sets_s=2)
    fixture._training_preview(reference)
    fixture.c.start()
    runtime = FixtureRuntime(fixture)
    window = MainWindow(runtime=runtime)
    window._select_rehab('training')
    window.source_kind.addItem('合成流程测试', 'SYNTHETIC')
    window.source_kind.setCurrentIndex(window.source_kind.findData('SYNTHETIC'))
    window.replay_row.hide()  # This fixture uses explicit synthetic poses, not a video file.
    window.setup = fixture.c.setup.copy()
    window._sync_scene()
    window._accept_context_frames = True
    window.notice.clear()
    window.show()
    t = 1.

    def pump():
        for _ in range(3):
            runtime.pump()
            window._poll()
            app.processEvents()

    def frames(angle, count=20):
        global t
        for _ in range(count):
            fixture.frame(t, angle)
            t += .1
        runtime._view(fixture.c.latest_packet, fixture.c.latest_pose)
        pump()

    def capture(name, widget=None):
        pump()
        assert (widget or window).grab().save(str(output/(name+'.png')))

    frames(0)
    frames(70)
    capture('active')
    QTest.mouseClick(window.training_panel.pause, Qt.MouseButton.LeftButton)
    pump()
    assert fixture.c.engine.stage == 'PAUSED'
    capture('paused')
    frames(0)
    window.training_panel.confirm.setChecked(True)
    QTest.mouseClick(window.training_panel.pause, Qt.MouseButton.LeftButton)
    pump()
    assert fixture.c.engine.stage == 'ACTIVE'
    for angle in (0, 70, 0):
        frames(angle)
    assert fixture.c.engine.stage == 'RESTING'
    for size in ((1100, 730), (1360, 900)):
        window.resize(*size)
        capture(f'rest-{size[0]}')
    frames(0, 30)
    window.training_panel.confirm.setChecked(True)
    QTest.mouseClick(window.training_panel.next_set, Qt.MouseButton.LeftButton)
    pump()
    assert fixture.c.engine.set_number == 2
    for angle in (0, 70, 0):
        frames(angle)
    assert fixture.c.engine.stage == 'COMPLETE'
    capture('completed')
    window._finish_task()
    pump()
    assert window.feedback_dialog is not None and fixture.camera.worker is None
    capture('end-feedback', window.feedback_dialog)
    window.feedback_dialog.scores['pain'].setValue(0)
    window.feedback_dialog.scores['fatigue'].setValue(2)
    window.feedback_dialog.notes.setPlainText('合成流程测试，不是真人训练感受。')
    window.feedback_dialog.submit()
    pump()
    assert window.feedback_dialog is None
    saved = fixture.store.get_session(fixture.c.last_saved_id)
    assert saved['training_feedback']['fatigue'] == 2
    assert saved['summary']['completed'] == 2
    assert saved['summary']['training']['sets'][1]['completed'] == 1
    window._handle_message({'kind': 'report', 'snapshot': saved, 'html': render_report(saved)})
    capture('saved-report', window.report_windows[-1])
    dialog = PlanDialog(saved['config_snapshot']['plan'], window)
    dialog.show()
    capture('plan', dialog)
    dialog.close()
    print('Synthetic pose → action engine → production control dispatch → SQLite → native training/review UI verified.')
finally:
    if window:
        window._allow_close = True
        window.close()
    fixture.tearDown()
