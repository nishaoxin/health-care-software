"""Real native navigation with inert runtime; no camera or patient data."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.assessment import build_body_profile
from test_product_navigation import desktop


def test_training_nav_opens_hub_without_changing_plan_or_starting_camera(desktop):
    w, runtime, app = desktop
    QTest.mouseClick(w.training_nav, Qt.MouseButton.LeftButton)
    assert w.pages.currentWidget() is w.training_hub
    assert w.title.text() == '训练中心' and w.training_nav.isChecked()
    assert not w.training_hub.has_reference and not runtime.calls
    w.training_hub.assess.click()
    assert w.pages.currentWidget() is w.catalog
    assert not runtime.calls


def test_running_or_unsaved_task_cannot_be_replaced_by_training_hub(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('wrist_flexion')
    for state in ('ONLINE', 'SAVE_FAILED'):
        w.state = state
        w._show_training_hub()
        assert w.pages.currentWidget() is w.work_page
        assert not runtime.calls


def test_assessment_to_training_hub_preserves_selected_reference_not_auto_confirm(desktop):
    w, runtime, app = desktop
    profile = build_body_profile([], **w._body_scope_key())
    profile['items'][0].update(status='ASSESSED', session_id='synthetic-guide-assessment',
                               motion_range={'min_deg': 0, 'max_deg': 60, 'range_deg': 60})
    w._handle_message({'kind': 'body_profile', 'profile': profile, 'html': 'SYNTHETIC TEST'})
    w._train_from_body()
    assert not w.setup['plan']['training_plan_confirmed']
    assert w.setup_tabs.currentIndex() == 1
    w._show_training_hub()
    assert w.training_hub.has_reference
    w.training_hub.resume.click()
    assert w.pages.currentWidget() is w.work_page
    assert w.setup['plan']['assessment_reference']['session_id'] == 'synthetic-guide-assessment'
    assert not w.setup['plan']['training_plan_confirmed'] and not w.start_button.isEnabled()
    assert not runtime.calls
    w._show_training_hub()
    w.setup['plan'].pop('assessment_reference')
    w._sync_scene()
    assert not w.training_hub.has_reference and w.title.text() == '训练中心'


def test_live_guide_uses_only_current_valid_observation_and_switches_tabs(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('wrist_flexion')
    w.setup_tabs.setCurrentIndex(1)
    summary = {'phase': 'RAISING', 'metrics': {'wrist_flexion_excursion_deg': {'value': 10, 'valid': True}}}
    w._render_view(dict(state='ONLINE', context=None, confirmed=True, summary=summary, observation_status='VALID'))
    assert w.setup_tabs.currentIndex() == 0 and w.exercise_guide.step_index == 1
    summary['phase'] = 'LOWERING'
    w._render_view(dict(state='ONLINE', context=None, confirmed=True, summary=summary, observation_status='UNKNOWN'))
    assert w.exercise_guide.step_index == 1 and '不足' in w.exercise_guide.status.text()
    w._render_view(dict(state='OFFLINE', context=None, confirmed=False, summary=summary))
    assert '中断' in w.exercise_guide.status.text()
    assert not runtime.calls


def test_patient_instruction_visible_at_small_window_and_side_changes_reset_steps(desktop):
    w, runtime, app = desktop
    w.resize(1100, 730)
    w._choose_catalog_exercise('index_dip_extension')
    app.processEvents()
    guide = w.exercise_guide
    guide.step_buttons[1].click()
    app.processEvents()
    bottom = guide.instruction.mapTo(w, guide.instruction.rect().bottomRight())
    assert bottom.y() < w.stop_button.mapTo(w, w.stop_button.rect().topLeft()).y()
    assert '伸展' in guide.instruction.text()
    w.side.setCurrentIndex(w.side.findData('right'))
    assert guide.step_index == 0 and '右侧' in guide.side_label.text()
    assert not runtime.calls


def test_invalidating_context_clears_previous_visual_step_even_for_same_action(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('wrist_flexion')
    w.exercise_guide.follow_observation('ONLINE', 'LOWERING', valid=True)
    assert w.exercise_guide.step_index == 2
    w._invalidate()
    assert w.exercise_guide.step_index == 0
    assert '当前动作' not in w.exercise_guide.status.text()
    assert not runtime.calls
