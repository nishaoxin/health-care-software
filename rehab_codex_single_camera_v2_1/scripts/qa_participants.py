"""Native Qt profile workflow through real runtime/storage; isolated QA data."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


app = QApplication([])
app.setStyle('Fusion')
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
output = ROOT/'qa-output'/'participants'
output.mkdir(parents=True, exist_ok=True)


def wait_until(window, predicate):
    end = time.monotonic()+12
    while time.monotonic() < end:
        window._poll()
        app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    raise RuntimeError('QA workflow did not finish: '+window.notice.text())


def capture(widget, name):
    app.processEvents()
    assert widget.grab().save(str(output/(name+'.png')))


with tempfile.TemporaryDirectory(prefix='rehab-profile-qa-') as temporary:
    window = MainWindow(data_dir=temporary)
    window.show()
    wait_until(window, lambda: window.runtime.ready.is_set() and not window.busy)
    window._edit_participant(new=True)
    dialog = window.participant_dialog
    dialog.name.setText('界面测试用户（非患者）')
    dialog.birth_year.setText('1952')
    dialog.choices['affected_side'].setCurrentIndex(dialog.choices['affected_side'].findData('left'))
    dialog.fields['goals'].setPlainText('自己穿外套、拿水杯。仅用于软件界面测试。')
    dialog.fields['restrictions'].setPlainText('测试填写：正式活动限制需按已有医嘱确认。')
    capture(dialog, 'profile-form')
    dialog.submit()
    wait_until(window, lambda: window.participant_dialog is None and not window.busy)
    participant_id = window.participant_id
    assert participant_id != 'participant-local'
    for size in ((1100, 730), (1360, 900)):
        window.resize(*size)
        window._show_body()
        wait_until(window, lambda: not window.busy and window.body_profile is not None)
        capture(window, f'profile-body-{size[0]}')
    assert window.runtime.store.list_sessions() == []
    assert window.runtime.camera.worker is None
    window.close()
    wait_until(window, lambda: not window.isVisible())
    window.runtime.thread.join(8)
    assert not window.runtime.thread.is_alive()
    reopened = MainWindow(data_dir=temporary)
    reopened.show()
    wait_until(reopened, lambda: reopened.runtime.ready.is_set() and not reopened.busy)
    reopened.participant_select.setCurrentIndex(reopened.participant_select.findData(participant_id))
    assert reopened.participant_records[participant_id]['goals'].startswith('自己穿外套')
    reopened._show_body()
    wait_until(reopened, lambda: not reopened.busy and reopened.body_profile is not None)
    capture(reopened, 'profile-reopened')
    assert reopened.runtime.camera.worker is None
    reopened.close()
    wait_until(reopened, lambda: not reopened.isVisible())
    reopened.runtime.thread.join(8)
    assert not reopened.runtime.thread.is_alive()
print('Profile create/save/select/body/reopen verified using isolated QA data; no camera or patient measurements.')
