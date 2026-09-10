import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from app.longitudinal import build_longitudinal_history
from test_longitudinal import saved_session, later
from test_training_ui import desktop


def open_history(window, runtime, session):
    window._handle_message({'kind': 'history', 'sessions': [session]})
    window.table.selectRow(0)
    window._open_longitudinal()
    dialog = window.longitudinal_dialog
    assert runtime.calls[-1][0] == 'longitudinal_history'
    return dialog


def test_history_entry_metric_switch_difference_details_and_original_report(desktop, saved_session):
    window, runtime, app = desktop
    dialog = open_history(window, runtime, saved_session)
    changed = later(saved_session, model_manifest_id='different')
    history = build_longitudinal_history([saved_session, changed], 'first')
    window._handle_message({'kind': 'longitudinal_history', 'history': history, 'request_id': dialog.request_id})
    assert dialog.table.rowCount() == 2
    dialog.metric_choice.setCurrentIndex(dialog.metric_choice.findData('return_s'))
    assert dialog.plot.metric_key == 'return_s'
    dialog.table.selectRow(1)
    assert '模型清单' in dialog.details.toPlainText() and 'different' in dialog.details.toPlainText()
    QTest.mouseClick(dialog.open_report, Qt.MouseButton.LeftButton)
    assert runtime.calls[-1] == ('report', {'id': 'second'})
    app.processEvents()
    assert not dialog.plot.grab().isNull()
    dialog.close()
    assert window.longitudinal_dialog is None


def test_late_reply_and_late_error_cannot_replace_new_anchor(desktop, saved_session):
    window, runtime, app = desktop
    dialog = open_history(window, runtime, saved_session)
    old_request = dialog.request_id
    history = build_longitudinal_history([saved_session, later(saved_session)], 'first')
    dialog.receive(history, old_request)
    dialog.anchor.setCurrentIndex(dialog.anchor.findData('second'))
    assert dialog.request_id != old_request
    second = build_longitudinal_history([saved_session, later(saved_session)], 'second')
    dialog.receive(second, dialog.request_id)
    dialog.receive(history, old_request)
    dialog.show_error('stale failure', old_request)
    assert dialog.history['anchor_id'] == 'second'
    assert 'stale failure' not in dialog.notice.text()
    dialog.close()


def test_missing_anchor_error_preserves_displayed_basis_and_recovers_controls(desktop, saved_session):
    window, runtime, app = desktop
    dialog = open_history(window, runtime, saved_session)
    history = build_longitudinal_history([saved_session, later(saved_session)], 'first')
    dialog.receive(history, dialog.request_id)
    dialog.anchor.setCurrentIndex(dialog.anchor.findData('second'))
    window._handle_message({'kind': 'error', 'command': 'longitudinal_history', 'text': '基准已删除', 'request_id': dialog.request_id})
    assert dialog.anchor.currentData() == 'first'
    assert dialog.anchor.isEnabled() and '基准已删除' in dialog.notice.text()
    dialog.close()


def test_export_preserves_current_metric_anchor_and_reviewed_fingerprint(desktop, saved_session, monkeypatch, tmp_path):
    window, runtime, app = desktop
    dialog = open_history(window, runtime, saved_session)
    history = build_longitudinal_history([saved_session], 'first')
    dialog.receive(history, dialog.request_id)
    dialog.metric_choice.setCurrentIndex(dialog.metric_choice.findData('outbound_s'))
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    QTest.mouseClick(dialog.export, Qt.MouseButton.LeftButton)
    command, args = runtime.calls[-1]
    assert command == 'export_longitudinal_history'
    assert args['anchor_id'] == 'first' and args['metric'] == 'outbound_s'
    assert args['expected_fingerprint'] == history['fingerprint']
    dialog.close()


def test_empty_selection_does_not_choose_a_different_person_implicitly(desktop):
    window, runtime, app = desktop
    window._open_longitudinal()
    assert window.longitudinal_dialog is None and '请选择' in window.notice.text()
