import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import queue

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from app.settings import default_plan
from app.ui.main_window import MainWindow
from app.ui.dialogs import PlanDialog
from app.reports import render_report
from test_training_execution import Sequence


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views, self.calls = queue.Queue(), queue.Queue(), []
    def command(self, name, **kwargs):
        self.calls.append((name, kwargs))


@pytest.fixture
def desktop():
    app = QApplication.instance() or QApplication([])
    runtime = PassiveRuntime()
    window = MainWindow(runtime=runtime)
    window.show()
    app.processEvents()
    yield window, runtime, app
    if window.feedback_dialog:
        window.feedback_dialog.set_busy(False)
        window.feedback_dialog.reject()
    window._allow_close = True
    window.close()
    window.deleteLater()
    app.processEvents()


def render(window, summary, state='ONLINE', observation_status='VALID'):
    window._render_view({'state': state, 'context': None, 'confirmed': True,
                         'summary': summary, 'observation_status': observation_status})


def finished_snapshot():
    sequence = Sequence(target_reps=1, target_sets=1)
    sequence.cycle()
    sequence.engine.finish('user_stop')
    return {'id': 'synthetic-training', 'participant_id': 'participant-local', 'scene_id': 'rehab',
            'exercise_id': 'shoulder_abduction', 'side': 'left', 'submode': 'training', 'status': 'FINISHED',
            'source_kind': 'SYNTHETIC', 'usage_context': 'TEST', 'summary': sequence.engine.summary(),
            'config_snapshot': {'plan': sequence.engine.plan}, 'repetitions': sequence.engine.repetitions}


def test_training_pause_rest_and_next_controls_follow_real_summary(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    seq = Sequence(target_reps=1)
    render(w, seq.engine.summary())
    assert w.training_panel.isVisible() and w.training_panel.pause.isEnabled()
    QTest.mouseClick(w.training_panel.pause, Qt.MouseButton.LeftButton)
    assert runtime.calls[-1][0] == 'training_control' and runtime.calls[-1][1]['action'] == 'pause'
    w._handle_message({'kind': 'command_done', 'command': 'training_control'})
    seq.frames(0)
    seq.command('pause')
    render(w, seq.engine.summary(), observation_status='NO_PERSON_DETECTED')
    assert '相机开启' in w.status_badge.text()
    assert '摄像头仍' in w.feedback.text()
    assert not w.training_panel.pause.isEnabled()
    w.training_panel.confirm.setChecked(True)
    assert w.training_panel.pause.isEnabled()
    QTest.mouseClick(w.training_panel.pause, Qt.MouseButton.LeftButton)
    assert runtime.calls[-1][1] == {'action': 'resume', 'setup_confirmed': True}
    w._handle_message({'kind': 'command_done', 'command': 'training_control'})
    seq.command('resume')
    seq.cycle()
    render(w, seq.engine.summary())
    assert not w.training_panel.next_set.isEnabled()
    seq.frames(n=40)
    render(w, seq.engine.summary())
    assert not w.training_panel.next_set.isEnabled()  # New stage requires a new confirmation.
    w.training_panel.confirm.setChecked(True)
    assert w.training_panel.next_set.isEnabled()
    render(w, seq.engine.summary(), state='OFFLINE')
    assert not w.training_panel.next_set.isEnabled() and not w.training_panel.pause.isEnabled()


def test_finish_opens_feedback_only_after_successful_save_and_keeps_failed_draft(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    w.state = 'ONLINE'
    w._finish_task()
    assert w.feedback_dialog is None
    w._handle_message({'kind': 'saved', 'id': 'synthetic-training'})
    w._handle_message({'kind': 'command_done', 'command': 'stop'})
    assert runtime.calls[-1] == ('training_review', {'id': 'synthetic-training'})
    snapshot = finished_snapshot()
    w.state = 'UNSELECTED'
    w._handle_message({'kind': 'training_review', 'snapshot': snapshot, 'html': render_report(snapshot)})
    w._handle_message({'kind': 'command_done', 'command': 'training_review'})
    dialog = w.feedback_dialog
    assert dialog.isVisible() and dialog.scores['pain'].value() == -1
    dialog.scores['pain'].setValue(0)
    dialog.notes.setPlainText('保存失败也保留这段填写')
    dialog.submit()
    assert runtime.calls[-1][1]['feedback']['pain'] == 0
    assert runtime.calls[-1][1]['feedback']['fatigue'] is None
    dialog.reject()
    assert dialog.isVisible()
    w._handle_message({'kind': 'error', 'command': 'save_training_feedback', 'text': '数据库只读'})
    w._handle_message({'kind': 'command_done', 'command': 'save_training_feedback'})
    assert not dialog.pending and dialog.notes.toPlainText() == '保存失败也保留这段填写'
    assert '只读' in dialog.error.text()
    dialog.submit()
    saved = copy.deepcopy(snapshot)
    saved['training_feedback'] = dict(runtime.calls[-1][1]['feedback'], revision=1)
    w._handle_message({'kind': 'training_feedback_saved', 'snapshot': saved, 'html': render_report(saved)})
    w._handle_message({'kind': 'command_done', 'command': 'save_training_feedback'})
    assert not dialog.isVisible() and w.feedback_dialog is None


@pytest.mark.parametrize('exercise', ['shoulder_abduction', 'sit_to_stand', 'wrist_extension'])
def test_plan_dialog_keeps_rest_nullable_and_save_visible(desktop, exercise):
    w, runtime, app = desktop
    plan = default_plan(exercise)
    plan['submode'] = 'training'
    dialog = PlanDialog(plan, w)
    dialog.show()
    app.processEvents()
    assert dialog.height() <= 700
    buttons = dialog.findChild(QDialogButtonBox)
    button = buttons.button(QDialogButtonBox.StandardButton.Save)
    assert button.mapTo(dialog, button.rect().bottomRight()).y() < dialog.height()
    assert dialog.rest.value() == -1
    dialog.rest.setValue(25)
    dialog._save()
    assert dialog.plan['rest_between_sets_s'] == 25
    assert dialog.plan['training_plan_confirmed']
    dialog.close()


@pytest.mark.parametrize('size', [(1100, 730), (1360, 900)])
def test_training_layout_keeps_footer_and_controls_in_bounds(desktop, size):
    w, runtime, app = desktop
    w.resize(*size)
    w._select_rehab('training')
    seq = Sequence(target_reps=1)
    seq.cycle()
    render(w, seq.engine.summary())
    app.processEvents()
    assert (w.width(), w.height()) == size
    assert w.stop_button.mapTo(w, w.stop_button.rect().bottomRight()).y() < w.height()
    assert w.training_panel.minimumSizeHint().width() <= w.training_panel.width()
    w.monitor_scroll.verticalScrollBar().setValue(w.monitor_scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert w.training_panel.mapTo(w, w.training_panel.rect().topLeft()).y() >= 0
    assert w.training_panel.mapTo(w, w.training_panel.rect().bottomRight()).y() < w.stop_button.mapTo(w, w.stop_button.rect().topLeft()).y()
