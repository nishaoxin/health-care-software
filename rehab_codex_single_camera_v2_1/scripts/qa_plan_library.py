"""Native plan create/save/reopen/prepare using synthetic evidence and temp data."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from app.storage import Storage
from app.ui.main_window import MainWindow
from app.ui.dialogs import PlanDialog
import test_app_controller as fixtures


app = QApplication([])
app.setStyle('Fusion')
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
output = ROOT/'qa-output/plan-library-v010'
output.mkdir(parents=True, exist_ok=True)


def wait(window, predicate):
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        window._poll()
        app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    raise RuntimeError('Plan library QA did not finish: '+window.notice.text())


def capture(widget, name):
    app.processEvents()
    assert widget.grab().save(str(output/(name+'.png')))


def fill_item_after_click(button, reps=3, sets=2):
    errors = []
    def fill():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, PlanDialog)
            dialog.reps.setValue(reps)
            dialog.sets.setValue(sets)
            dialog.rest.setValue(5)
            dialog._save()
        except Exception as exc:
            errors.append(exc)
            if dialog:
                dialog.reject()
    QTimer.singleShot(50, fill)
    button.click()
    if errors:
        raise errors[0]


def open_window(directory):
    window = MainWindow(data_dir=directory)
    window.show()
    wait(window, lambda: window.runtime.ready.is_set() and not window.busy)
    window.source_kind.addItem('合成流程测试', 'SYNTHETIC')
    window.source_kind.setCurrentIndex(window.source_kind.findData('SYNTHETIC'))
    window.usage.setCurrentIndex(window.usage.findData('TEST'))
    window.replay_row.hide()
    window._show_training_hub()
    return window


def close_window(window):
    if window.plan_library_dialog:
        window.plan_library_dialog.set_busy(False)
        window.plan_library_dialog._cancel_edit()
        window.plan_library_dialog.reject()
    window.close()
    wait(window, lambda: not window.isVisible())
    window.runtime.thread.join(5)
    assert not window.runtime.thread.is_alive()


fixture = fixtures.ControllerTests(methodName='test_preview_start_shoulder_save_and_reopen')
fixture.setUp()
try:
    fixture._assessment_reference()
    synthetic_assessment = fixture.store.list_sessions()[0]
finally:
    fixture.tearDown()

with tempfile.TemporaryDirectory(prefix='rehab-plan-qa-') as temporary:
    store = Storage(Path(temporary)/'home_rehab.sqlite3')
    store.save_session(synthetic_assessment)
    store.close()
    window = open_window(temporary)
    try:
        window.training_hub.library.click()
        wait(window, lambda: not window.busy)
        dialog = window.plan_library_dialog
        dialog.new.click()
        dialog.name.setText('日常练习（合成界面验收）')
        dialog.exercise.setCurrentIndex(dialog.exercise.findData('shoulder_abduction'))
        fill_item_after_click(dialog.add_item)
        dialog.exercise.setCurrentIndex(dialog.exercise.findData('knee_extension'))
        dialog.side.setCurrentIndex(dialog.side.findData('right'))
        fill_item_after_click(dialog.add_item, reps=4, sets=1)
        capture(dialog, 'draft')
        dialog.save.click()
        wait(window, lambda: not window.busy and not dialog.editing)
        assert dialog.table.rowCount() == 2
        plan_id = dialog.current_record()['id']
        for size in ((780, 540), (980, 660)):
            dialog.resize(*size)
            capture(dialog, f'saved-{size[0]}')
        dialog.edit.click()
        dialog.name.setText('我的日常练习（合成界面验收）')
        dialog.save.click()
        wait(window, lambda: not window.busy and not dialog.editing)
        assert dialog.current_record()['revision'] == 2
        dialog.archive.click()
        wait(window, lambda: not window.busy)
        assert dialog.current_record()['status'] == 'ARCHIVED' and not dialog.use.isEnabled()
        dialog.archive.click()
        wait(window, lambda: not window.busy)
        assert dialog.current_record()['revision'] == 4
        assert window.runtime.camera.worker is None
        assert len(window.runtime.store.list_sessions()) == 1
    finally:
        close_window(window)
    reopened = open_window(temporary)
    try:
        reopened.training_hub.library.click()
        wait(reopened, lambda: not reopened.busy)
        dialog = reopened.plan_library_dialog
        assert dialog.current_record()['id'] == plan_id and dialog.current_record()['revision'] == 4
        assert dialog.table.rowCount() == 2
        capture(dialog, 'reopened')
        dialog.table.selectRow(0)
        dialog.use.click()
        wait(reopened, lambda: not reopened.busy and reopened.plan_library_dialog is None)
        assert reopened.setup['plan']['saved_plan_reference']['id'] == plan_id
        assert not reopened.setup['plan']['training_plan_confirmed']
        fill_item_after_click(reopened.plan_button)
        assert reopened.setup['plan']['training_plan_confirmed'] and not reopened.manual.isChecked()
        capture(reopened, 'prepared-awaiting-camera')
        assert reopened.runtime.camera.worker is None and len(reopened.runtime.store.list_sessions()) == 1
    finally:
        close_window(reopened)
print('Native plan create/edit/save/archive/restore/reopen/prepare verified with real runtime and temporary SQLite. No camera or human accuracy validation.')
