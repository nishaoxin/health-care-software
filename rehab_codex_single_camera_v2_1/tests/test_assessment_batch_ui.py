import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.assessment_batches import new_batch, batch_view
from app.ui.main_window import MainWindow
from test_training_ui import PassiveRuntime


@pytest.fixture
def desktop():
    app = QApplication.instance() or QApplication([])
    runtime = PassiveRuntime()
    w = MainWindow(runtime=runtime)
    w.show()
    app.processEvents()
    yield w, runtime, app
    if w.batch_dialog:
        w.batch_dialog.set_busy(False)
        w.batch_dialog.reject()
    w._allow_close = True
    w.close()
    w.deleteLater()
    app.processEvents()


def finish(w, name):
    w._handle_message({'kind': 'command_done', 'command': name})


def test_create_failure_keeps_selection_and_success_binds_selected_side(desktop):
    w, runtime, app = desktop
    QTest.mouseClick(w.catalog.checklist, Qt.MouseButton.LeftButton)
    assert runtime.calls[-1][0] == 'assessment_batch'
    dialog = w.batch_dialog
    assert dialog.busy
    w._handle_message({'kind': 'assessment_batch', 'scope': dialog.scope, 'batch': None})
    finish(w, 'assessment_batch')
    dialog.choices.item(1).setCheckState(Qt.CheckState.Checked)
    QTest.mouseClick(dialog.create, Qt.MouseButton.LeftButton)
    command, kwargs = runtime.calls[-1]
    assert command == 'create_assessment_batch'
    assert kwargs['items'] == [{'exercise_id': 'shoulder_abduction', 'side': 'right'}]
    w._handle_message({'kind': 'error', 'command': command, 'text': '测试保存失败'})
    finish(w, command)
    assert dialog.choices.item(1).checkState() == Qt.CheckState.Checked
    assert '失败' in dialog.error.text() and dialog.batch is None
    QTest.mouseClick(dialog.create, Qt.MouseButton.LeftButton)
    batch = batch_view(new_batch(dialog.scope, kwargs['items']), [])
    w._handle_message({'kind': 'assessment_batch', 'scope': dialog.scope, 'batch': batch})
    finish(w, command)
    assert dialog.table.rowCount() == 1 and dialog.run.isEnabled()
    QTest.mouseClick(dialog.run, Qt.MouseButton.LeftButton)
    assert w.batch_dialog is None
    assert w.setup['plan']['assessment_batch_id'] == batch['id']
    assert w.setup['plan']['side'] == 'right' and w.setup['plan']['submode'] == 'assessment'
    assert not any(name == 'start' for name, _ in runtime.calls)
    w.side.setCurrentIndex(w.side.findData('left'))
    assert 'assessment_batch_id' not in w.setup['plan']
    w.setup['plan'].update(assessment_batch_id=batch['id'], assessment_entry_key=batch['items'][0]['key'])
    w._choose_catalog_exercise('shoulder_abduction')
    assert 'assessment_batch_id' not in w.setup['plan']


def test_unchosen_or_skipped_rows_do_not_start_and_other_user_response_is_ignored(desktop):
    w, runtime, app = desktop
    w._open_assessment_batch()
    dialog = w.batch_dialog
    batch = new_batch(dialog.scope, [{'exercise_id': 'neck_flexion', 'side': 'left'}])
    batch['items'][0]['skip_reason'] = '本轮不做'
    w._handle_message({'kind': 'assessment_batch', 'scope': dict(dialog.scope, participant_id='other'),
                      'batch': batch_view(batch, [])})
    assert dialog.batch is None
    w._handle_message({'kind': 'assessment_batch', 'scope': dialog.scope, 'batch': batch_view(batch, [])})
    finish(w, 'assessment_batch')
    assert not dialog.run.isEnabled()
    assert dialog.skip.text() == '恢复为待测'
    QTest.mouseClick(dialog.skip, Qt.MouseButton.LeftButton)
    assert runtime.calls[-1][0] == 'change_assessment_batch' and runtime.calls[-1][1]['action'] == 'restore'
    finish(w, 'change_assessment_batch')


@pytest.mark.parametrize('state', ['ONLINE', 'SAVE_FAILED'])
def test_running_or_unsaved_task_cannot_open_round_editor(desktop, state):
    w, runtime, app = desktop
    w.state = state
    w._open_assessment_batch()
    assert w.batch_dialog is None and not runtime.calls
