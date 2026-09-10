import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy

import pytest
from PySide6.QtWidgets import QApplication

from app.assessment import build_body_profile
from app.settings import default_plan
from app.training_plans import new_training_plan, prepare_training_plan, training_plan_view
from app.ui.dialogs import PlanDialog
from app.ui.main_window import MainWindow
from app.ui.plan_library import PlanLibraryDialog
from test_product_navigation import PassiveRuntime
from test_saved_training_plans import SCOPE, item, saved_record, assessment, profile


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def library(qt_app):
    dialog = PlanLibraryDialog(SCOPE)
    dialog.show()
    qt_app.processEvents()
    yield dialog
    dialog.set_busy(False)
    dialog._cancel_edit()
    dialog.reject()
    dialog.deleteLater()
    qt_app.processEvents()


def test_manual_multiaction_draft_save_and_reorder_never_imports_capture_state(library):
    dialog = library
    assert not dialog.use.isEnabled() and dialog.table.rowCount() == 0
    dialog.new.click()
    dialog.name.setText('每周练习')
    first = default_plan()
    first.update(training_plan_confirmed=True, calibration={'old': 9})
    dialog._append_item(first)
    dialog._append_item(dict(default_plan('knee_extension'), side='right'))
    dialog.up.click()
    assert dialog.draft['items'][0]['exercise_id'] == 'knee_extension'
    assert dialog.name.text() == '每周练习'
    received = []
    dialog.save_requested.connect(lambda record, rev: received.append((record, rev)))
    dialog.save.click()
    assert received[0][0]['name'] == '每周练习'
    assert received[0][1] == 0 and len(received[0][0]['items']) == 2
    assert 'calibration' not in str(received)
    assert 'training_plan_confirmed' not in str(received)


def test_failed_save_or_late_read_preserves_unsaved_fields(library):
    dialog = library
    original = saved_record()
    dialog.populate([training_plan_view(original, profile())])
    dialog.edit.click()
    dialog.name.setText('尚未保存的名称')
    dialog.set_busy(True)
    dialog.populate([], saved=False)
    dialog.error.setText('计划已更新，本次草稿尚未保存')
    dialog.set_busy(False)
    assert dialog.editing and dialog.name.text() == '尚未保存的名称'
    assert dialog.draft['revision'] == 1
    dialog.reject()
    assert dialog.isVisible()  # Close cannot silently discard a draft.
    dialog.cancel_edit.click()
    assert not dialog.editing and dialog.name.text() == original['name']


def test_archived_or_unassessed_items_cannot_be_used_but_archive_is_reversible(library):
    dialog = library
    record = saved_record()
    dialog.populate([training_plan_view(record, profile())])
    assert dialog.use.isEnabled()
    selected = []
    dialog.training_requested.connect(lambda *args: selected.append(args))
    dialog.use.click()
    assert selected == [(record['id'], 1, 'shoulder_abduction:left')]
    dialog.table.selectRow(1)
    assert not dialog.use.isEnabled()
    assert '有效评估' in dialog.detail.text()
    archived = dict(record, status='ARCHIVED', revision=2)
    dialog.populate([training_plan_view(archived, profile())])
    assert not dialog.use.isEnabled() and not dialog.edit.isEnabled()
    assert dialog.archive.text() == '恢复计划'
    actions = []
    dialog.archive_requested.connect(lambda *args: actions.append(args))
    dialog.archive.click()
    assert actions == [(record['id'], 2, False)]


def test_template_item_editor_never_confirms_a_live_plan(qt_app):
    plan = dict(default_plan(), submode='training')
    dialog = PlanDialog(plan, template_mode=True)
    dialog.reps.setValue(6)
    dialog._save()
    assert dialog.plan['target_reps'] == 6
    assert not dialog.plan['training_plan_confirmed']
    assert plan['target_reps'] == 5


@pytest.fixture
def desktop(qt_app):
    runtime = PassiveRuntime()
    window = MainWindow(runtime=runtime)
    window.show()
    qt_app.processEvents()
    yield window, runtime
    if window.plan_library_dialog:
        window.plan_library_dialog.set_busy(False)
        window.plan_library_dialog._cancel_edit()
        window.plan_library_dialog.reject()
    window._allow_close = True
    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_native_library_loads_selected_item_after_command_done_and_requires_fresh_confirmation(desktop):
    w, runtime = desktop
    scope = w._body_scope_key()
    current = build_body_profile([assessment(**scope)], **scope)
    record = new_training_plan(scope, '本地计划', [item()])
    record['revision'] = 1
    w._show_training_hub()
    w.training_hub.library.click()
    assert runtime.calls[-1][0] == 'training_plans'
    w._handle_message(dict(kind='training_plans', scope=scope, plans=[training_plan_view(record, current)]))
    w._handle_message(dict(kind='command_done', command='training_plans'))
    dialog = w.plan_library_dialog
    dialog.use.click()
    assert runtime.calls[-1][0] == 'prepare_training_plan'
    plan = prepare_training_plan(record, 'shoulder_abduction:left', current)
    w._handle_message(dict(kind='training_plan_prepared', scope=scope, plan=plan))
    assert w.plan_library_dialog is dialog  # Do not race a pending runtime command.
    w._handle_message(dict(kind='command_done', command='prepare_training_plan'))
    assert w.plan_library_dialog is None and w.pages.currentIndex() == 0
    assert w.submode.currentData() == 'training'
    assert w.setup['plan']['saved_plan_reference']['id'] == record['id']
    assert w.setup['plan']['calibration'] == w.setup['plan']['joint_baseline'] == {}
    assert not w.setup['plan']['training_plan_confirmed'] and not w.manual.isChecked()
    assert not any(name in ('open', 'start', 'camera_test') for name, _ in runtime.calls)
    w.usage.setCurrentIndex(w.usage.findData('TEST'))
    assert 'saved_plan_reference' not in w.setup['plan']


def test_late_library_reply_for_another_scope_is_ignored(desktop):
    w, runtime = desktop
    w._open_plan_library()
    other = dict(w._body_scope_key(), participant_id='other')
    w._handle_message(dict(kind='training_plans', scope=other, plans=[saved_record()]))
    assert not w.plan_library_dialog.records
    w._handle_message(dict(kind='training_plan_prepared', scope=other, plan={'bad': True}))
    w._handle_message(dict(kind='command_done', command='training_plans'))
    assert w._plan_to_activate is None and w.plan_library_dialog is not None


@pytest.mark.parametrize('state', ['ONLINE', 'SAVE_FAILED'])
def test_running_or_pending_save_blocks_library_navigation(desktop, state):
    w, runtime = desktop
    w.state = state
    w._open_plan_library()
    assert w.plan_library_dialog is None and runtime.calls == []
