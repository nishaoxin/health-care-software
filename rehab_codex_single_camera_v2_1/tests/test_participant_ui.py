import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import queue

import pytest
from PySide6.QtWidgets import QApplication

from app.participants import legacy_participant, new_participant
from app.ui.main_window import MainWindow
from app.ui.participants import ParticipantDialog


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
    if window.participant_dialog:
        window.participant_dialog.set_busy(False)
        window.participant_dialog.reject()
    window._allow_close = True
    window.close()
    window.deleteLater()
    app.processEvents()


def test_real_selector_retains_old_ids_and_distinguishes_same_names(desktop):
    w, runtime, app = desktop
    a = dict(legacy_participant('a'), display_name='同名', revision=1)
    b = dict(legacy_participant('b'), display_name='同名', revision=1)
    w._handle_message({'kind': 'participants', 'participants': [a, b]})
    assert w.participant.isHidden()
    assert w.participant_select.findData(w.participant_id) >= 0
    assert w.participant_select.itemText(w.participant_select.findData('a')) != w.participant_select.itemText(w.participant_select.findData('b'))
    w.setup['plan'].update(target_angle_deg=75, training_plan_confirmed=True,
                            assessment_reference={'status': 'ASSESSED'}, joint_baseline={'test': 'old'})
    w.participant_select.setCurrentIndex(w.participant_select.findData('a'))
    assert w.participant_id == 'a'
    assert w.setup['plan']['target_angle_deg'] is None
    assert not w.setup['plan'].get('assessment_reference')
    assert not w.setup['plan']['joint_baseline']
    assert not runtime.calls  # Selecting a person doesn't start input.


def test_new_profile_activates_only_after_committed_response(desktop):
    w, runtime, app = desktop
    old_id = w.participant_id
    w._edit_participant(new=True)
    dialog = w.participant_dialog
    assert dialog.error.isHidden()
    dialog.name.setText('王女士')
    dialog.fields['goals'].setPlainText('自己拿杯子')
    dialog.submit()
    assert w.participant_id == old_id
    assert dialog.isVisible() and dialog.pending
    name, kw = runtime.calls[-1]
    assert name == 'save_participant' and kw['expected_revision'] == 0
    saved = dict(kw['profile'], revision=1, record_origin='manual', created_utc='now', updated_utc='now')
    w._handle_message({'kind': 'participant_saved', 'profile': saved})
    w._handle_message({'kind': 'command_done', 'command': 'save_participant'})
    assert w.participant_id == saved['participant_id']
    assert w.participant_records[saved['participant_id']]['goals'] == '自己拿杯子'
    assert not dialog.isVisible()


def test_save_failure_keeps_draft_and_current_user_unchanged(desktop):
    w, runtime, app = desktop
    old_id = w.participant_id
    w._edit_participant(new=True)
    dialog = w.participant_dialog
    dialog.name.setText('保留草稿')
    dialog.submit()
    dialog.reject()
    assert dialog.isVisible()  # Do not discard an in-flight save.
    w._handle_message({'kind': 'error', 'command': 'save_participant', 'text': '磁盘无法写入'})
    w._handle_message({'kind': 'command_done', 'command': 'save_participant'})
    assert dialog.isVisible() and not dialog.pending
    assert dialog.name.text() == '保留草稿'
    assert '磁盘' in dialog.error.text() and w.participant_id == old_id
    assert not any('已保存' in t for t in [w.notice.text(), dialog.error.text()])


@pytest.mark.parametrize('state', ['ONLINE', 'SAVE_FAILED'])
def test_profile_edit_and_switch_are_blocked_during_run_or_pending_save(desktop, state):
    w, runtime, app = desktop
    w.state = state
    w._buttons()
    w._edit_participant(new=True)
    assert w.participant_dialog is None
    assert not w.participant_select.isEnabled()
    assert not w.participant_button.isEnabled()
    assert not w.participant_new.isEnabled()
    assert not runtime.calls


def test_preview_is_stopped_before_profile_edit_and_save_waits(desktop):
    w, runtime, app = desktop
    w.state = 'PREVIEW'
    w._edit_participant()
    assert runtime.calls[-1][0] == 'switch'
    assert w.participant_dialog.pending
    w.participant_dialog.submit()
    assert runtime.calls[-1][0] == 'switch'
    w._handle_message({'kind': 'command_done', 'command': 'switch'})
    assert not w.participant_dialog.pending


def test_dialog_validates_and_keeps_unknown_year_empty(desktop):
    w, runtime, app = desktop
    w._edit_participant(new=True)
    dialog = w.participant_dialog
    dialog.submit()
    assert '称呼' in dialog.error.text() and not runtime.calls
    dialog.name.setText('测试')
    dialog.birth_year.setText('no')
    dialog.submit()
    assert '出生' in dialog.error.text() and not runtime.calls
    dialog.birth_year.clear()
    dialog.submit()
    assert runtime.calls[-1][1]['profile']['birth_year'] is None


@pytest.mark.parametrize('size', [(1100, 730), (1360, 900)])
def test_profile_summary_and_dialog_fit_and_text_is_not_html(desktop, size):
    w, runtime, app = desktop
    w.resize(*size)
    profile = dict(legacy_participant(w.participant_id), revision=1, record_origin='manual',
                   display_name='<b>测试</b>', goals='x'*1000, restrictions='y'*1000)
    w._handle_message({'kind': 'participants', 'participants': [profile]})
    w.pages.setCurrentIndex(2)
    app.processEvents()
    assert (w.width(), w.height()) == size
    assert w.personal_summary.heading.text() == '<b>测试</b>'
    assert '摄像头' in w.personal_summary.origin.text()
    assert '已填活动限制' in w.personal_summary.restrictions.text()
    w._choose_catalog_exercise('shoulder_abduction')
    assert not w.personal_reminders.isHidden()
    assert '活动限制' in w.personal_reminders.text()
    w._edit_participant()
    dialog = w.participant_dialog
    app.processEvents()
    assert dialog.height() <= 680
    assert dialog.save.mapTo(dialog, dialog.save.rect().bottomRight()).y() < dialog.height()
