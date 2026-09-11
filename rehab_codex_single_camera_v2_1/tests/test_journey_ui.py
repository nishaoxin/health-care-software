import pytest
from app.reports import render_report
from app.ui.dialogs import ReportDialog
from test_product_navigation import desktop
from test_result_summary import snapshot


def preview_neck(w):
    w._choose_catalog_exercise('neck_flexion')
    w.state = 'PREVIEW'
    w._confirmed = False
    w._buttons()


def test_guided_next_samples_then_one_explicit_confirmation_without_start(desktop):
    w, runtime, app = desktop
    preview_neck(w)
    assert w.setup_tabs.currentIndex() == 2
    assert '肩—髋' in w.journey.explanation.text()
    assert '另一侧肩' in w.journey.explanation.text()
    w.confirm_button.click()
    assert w._journey_step().key == 'rest'
    assert not runtime.calls and not w.manual.isChecked()
    w.confirm_button.click()
    assert runtime.calls[-1] == ('prepare_sample', {'sample': 'joint_baseline', 'position': 'rest', 'expected_context': None})
    w._handle_message(dict(kind='command_done', command='prepare_sample'))
    assert not w.confirm_button.isEnabled()
    assert w.preparation_cancel.isVisible() and w.privacy_button.isEnabled()
    count = len(runtime.calls)
    w._journey_next()
    assert len(runtime.calls) == count
    w.setup['plan']['joint_baseline'] = dict(rest_value=0.)
    assert w._journey_step().key == 'rest'  # Do not advance until sampling completes.
    w._handle_message(dict(kind='preparation', active=False, text='已记录起点'))
    w._buttons()
    assert w.confirm_button.text() == '记录活动方向'
    w.confirm_button.click()
    assert runtime.calls[-1] == ('prepare_sample', {'sample': 'joint_baseline', 'position': 'direction', 'expected_context': None})
    w._handle_message(dict(kind='command_done', command='prepare_sample'))
    w.setup['plan']['joint_baseline']['direction_sign'] = 1
    w._handle_message(dict(kind='preparation', active=False, text='已记录方向'))
    w._buttons()
    assert w.confirm_button.text() == '已核对，确认准备'
    assert w.preparation_review.isVisible()
    assert runtime.calls[-1][0] != 'confirm'
    assert not w.manual.isChecked()
    w.confirm_button.click()
    assert runtime.calls[-1][0] == 'confirm'
    assert runtime.calls[-1][1]['setup']['participant_confirmed'] is True
    assert not any(name == 'start' for name, args in runtime.calls)


def test_error_stays_at_current_step_then_invalidation_resets_guidance(desktop):
    w, runtime, app = desktop
    preview_neck(w)
    w.confirm_button.click()
    w._handle_message(dict(kind='error', command='joint_baseline', text='左髋未看清，请调整取景'))
    w._buttons()
    assert w._journey_step().key == 'rest'
    assert '左髋' in w.journey.message.text()
    w._invalidate()
    assert w._journey_step().key == 'camera'
    assert not w._journey_error


def test_save_failure_does_not_open_report_and_success_requests_persisted_id_once(desktop):
    w, runtime, app = desktop
    preview_neck(w)
    w.state = 'ONLINE'
    w._finish_task()
    w.state = 'SAVE_FAILED'
    w._buttons()
    assert w._journey_step().key == 'save_failed'
    assert not any(n == 'report' for n, _ in runtime.calls)
    w.state = 'UNSELECTED'
    w._handle_message(dict(kind='saved', id='persisted-id'))
    assert ('report', {'id': 'persisted-id'}) in runtime.calls
    assert w._journey_step().key == 'result'
    w._handle_message(dict(kind='saved', id='persisted-id'))
    assert sum(n == 'report' for n, _ in runtime.calls) == 1


def test_report_opens_understandable_summary_and_preserves_details(desktop):
    w, runtime, app = desktop
    s = snapshot()
    d = ReportDialog(s, render_report(s), lambda sid: None, w)
    d.show()
    app.processEvents()
    assert d.overview.isVisible()
    assert '这些数字怎么理解' in d.overview.toPlainText()
    assert '每次动作' in d.browser.toPlainText()
    d.close()


def test_companion_is_explicit_and_not_bypassed(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state = 'PREVIEW'
    w._journey_framed = True
    w.setup['plan']['needs_companion'] = True
    w._buttons()
    w.confirm_button.click()
    assert '陪同' in w.journey.message.text()
    assert not any(n == 'confirm' for n, _ in runtime.calls)
    w.journey.companion.setChecked(True)
    w.confirm_button.click()
    assert runtime.calls[-1][1]['setup']['companion_confirmed'] is True


@pytest.mark.parametrize('position', ['seated', 'standing'])
def test_sit_stand_journey_uses_cancellable_sampling_and_resets_on_change(desktop, position):
    w, runtime, app = desktop
    w._choose_catalog_exercise('sit_to_stand')
    w.state = 'PREVIEW'
    w._journey_framed = True
    if position == 'standing':
        w.setup['plan']['calibration'] = {'seated_knee': 90., 'seated_hip_y': .5}
    w._buttons()
    assert w._journey_step().key == position
    w.confirm_button.click()
    assert runtime.calls[-1] == ('prepare_sample', {'sample': 'baseline', 'position': position, 'expected_context': None})
    w._handle_message(dict(kind='command_done', command='prepare_sample'))
    w._handle_message(dict(kind='preparation', active=True, text='3 秒后记录，请保持姿势'))
    assert w.preparation_status.isVisible() and w.preparation_cancel.isVisible()
    assert not w.confirm_button.isEnabled() and not w.manual.isChecked()
    w.preparation_cancel.click()
    assert runtime.calls[-1][0] == 'cancel_preparation'
    w._handle_message(dict(kind='command_done', command='cancel_preparation'))
    w._handle_message(dict(kind='preparation', active=False, text='已取消，可重新记录'))
    assert w._journey_step().key == position and w.confirm_button.isEnabled()
    w._invalidate()
    assert not w.preparation_active and not w.preparation_status.text()
    assert w._last_sample_request is None and w.preparation_retry.isHidden()


def test_training_preflight_has_an_action_but_no_enabled_start(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    w.state, w._confirmed = 'PREVIEW', True
    w._buttons()
    assert not w.start_button.isEnabled() and not w.start_button.isVisible()
    assert w.confirm_button.text() == '选择评估记录'
    w.confirm_button.click()
    assert not any(n == 'start' for n, _ in runtime.calls)
    assert w.pages.currentIndex() == 2


def test_training_result_follows_feedback_close_but_not_after_context_change(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    w.state = 'ONLINE'
    w._finish_task()
    w.state = 'UNSELECTED'
    w._handle_message(dict(kind='saved', id='training-saved'))
    assert not any(n == 'report' for n, _ in runtime.calls)
    w._feedback_closed()
    assert ('report', {'id': 'training-saved'}) in runtime.calls
    count = len(runtime.calls)
    w._feedback_closed()
    assert len(runtime.calls) == count
    w._result_after_feedback = ('old-training', w._body_scope_key())
    w._invalidate()
    w._feedback_closed()
    assert ('report', {'id': 'old-training'}) not in runtime.calls
