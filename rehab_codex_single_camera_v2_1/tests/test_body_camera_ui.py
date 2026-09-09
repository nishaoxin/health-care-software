from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.domain import Context
from app.exercises import EXERCISE_IDS
from app.exercise_instructions import exercise_instructions, JOINT_LABELS
from app.ui.body_map import BodyMap
from test_product_navigation import desktop
from test_camera_selection import camera
from test_clarity_ui import enumerate_result, drain_commands
from test_camera_test_runtime import packet


def test_entry_has_test_button_and_no_actions_or_capture_until_user_chooses(desktop):
    w, runtime, app = desktop
    assert w.camera_test_button.isVisible() and w.camera_test_button.isEnabled()
    assert w.catalog.visible_ids == [] and w.catalog.empty.isVisible()
    assert runtime.calls == []
    w.camera_test_button.click()
    assert not runtime.calls and '摄像头' in w.notice.text()


@pytest.mark.parametrize('joint', JOINT_LABELS)
@pytest.mark.parametrize('target', ['labels', 'markers'])
def test_body_name_and_marker_filter_exact_category(desktop, joint, target):
    w, runtime, app = desktop
    body = w.catalog.body_map
    QTest.mouseClick(getattr(body, target)[joint], Qt.MouseButton.LeftButton)
    app.processEvents()
    expected = {e for e in EXERCISE_IDS if exercise_instructions(e)['joint'] == joint}
    assert set(w.catalog.visible_ids) == expected
    assert body.labels[joint].isChecked() and body.markers[joint].isChecked()
    assert w.catalog.part_title.text() == JOINT_LABELS[joint]
    assert runtime.calls == []


def test_search_from_initial_screen_and_keyboard_navigation(desktop):
    w, runtime, app = desktop
    w.catalog.search.setText('桡偏')
    assert w.catalog.visible_ids == ['wrist_radial_deviation']
    w.catalog.search.clear()
    assert w.catalog.visible_ids == []
    button = w.catalog.body_map.labels['knee']
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert w.catalog.joint == 'knee'


@pytest.mark.parametrize('width,height', [(1100, 730), (1360, 900), (1600, 1000)])
def test_body_controls_fit_and_do_not_overlap(desktop, width, height):
    w, runtime, app = desktop
    w.resize(width, height)
    app.processEvents()
    assert (w.width(), w.height()) == (width, height)
    body = w.catalog.body_map
    controls = list(body.labels.values())+list(body.markers.values())
    for index, button in enumerate(controls):
        assert body.rect().contains(button.geometry())
        for other in controls[index+1:]:
            assert not button.geometry().intersects(other.geometry()), (button.accessibleName(), other.accessibleName())


def test_missing_navigation_asset_preserves_text_controls(desktop, tmp_path):
    body = BodyMap(image_path=tmp_path/'missing.png')
    chosen = []
    body.joint_selected.connect(chosen.append)
    body.labels['hip'].click()
    assert chosen == ['hip'] and body.pixmap.isNull()
    body.close()


def begin_test(w, app):
    enumerate_result(w, [camera()])
    w.camera_test_button.click()
    app.processEvents()
    drain_commands(w)
    return w.camera_test_dialog


def test_test_is_independent_modal_and_requires_real_frame_before_success(desktop):
    w, runtime, app = desktop
    dialog = begin_test(w, app)
    assert runtime.calls[-1][0] == 'camera_test'
    assert 'setup' not in runtime.calls[-1][1]
    assert 'index' not in runtime.calls[-1][1]['source']['device_ref']
    assert w.pages.currentWidget() is w.catalog and dialog.isVisible()
    assert not w.start_button.isEnabled() and not w.device.isEnabled()
    assert '正在' in dialog.status.text() and dialog.canvas.image is None
    context = Context(4, 'rehab', 'test', 'LIVE_CAMERA', 'TEST')
    frame = packet(context)
    w._render_view(dict(camera_test=True, state='PREVIEW', context=context, packet=frame, confirmed=True))
    assert '已收到画面' in dialog.status.text() and dialog.canvas.image is not None
    assert not w._confirmed and w.canvas.image is None
    assert not w.confirm_button.isEnabled() and not w.start_button.isEnabled()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert runtime.calls[-1][0] == 'stop_camera_test'
    assert dialog.isVisible() and dialog.stopping  # Wait for release, not just a button press.
    w._handle_message(dict(kind='camera_test_stopped'))
    drain_commands(w)
    assert not w._camera_testing and w.camera_test_dialog is None
    assert w.device.currentData() == camera() and not w._confirmed
    assert w.pages.currentWidget() is w.catalog
    w._choose_catalog_exercise('elbow_flexion')
    w._preview()
    assert runtime.calls[-1][0] == 'open'
    assert not any(name in ('confirm', 'start') for name, _ in runtime.calls)


def test_error_blanks_test_frame_and_failed_release_can_retry(desktop):
    w, runtime, app = desktop
    dialog = begin_test(w, app)
    context = Context(7, 'rehab', 'test', 'LIVE_CAMERA', 'TEST')
    frame = packet(context)
    w._render_view(dict(camera_test=True, state='PREVIEW', context=context, packet=frame, confirmed=False))
    w._render_view(dict(camera_test=True, state='OFFLINE', context=None, error='输入已断开'))
    assert dialog.canvas.image is None and '断开' in dialog.status.text()
    dialog.close()
    w._handle_message(dict(kind='error', command='stop_camera_test', text='释放失败，请重试'))
    drain_commands(w)
    assert dialog.isVisible() and dialog.stop_button.isEnabled() and w._camera_testing
    dialog.stop_button.click()
    assert [name for name, _ in runtime.calls].count('stop_camera_test') == 2


@pytest.mark.parametrize('state', ['ONLINE', 'SAVE_FAILED'])
def test_running_and_unsaved_work_block_test(desktop, state):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    w.state = state
    w._buttons()
    assert not w.camera_test_button.isEnabled()
    w._start_camera_test()
    assert not runtime.calls and not w._camera_testing


def test_test_filters_stale_context_and_does_not_switch_categories(desktop):
    w, runtime, app = desktop
    w.catalog.select_joint('hip')
    dialog = begin_test(w, app)
    context = Context(10, 'rehab', 'test', 'LIVE_CAMERA', 'TEST')
    w._render_view(dict(camera_test=True, state='CONNECTING', context=context))
    old = replace(context, generation=9)
    w._render_view(dict(camera_test=True, state='PREVIEW', context=old, packet=packet(old)))
    assert dialog.canvas.image is None
    w._choose_catalog_exercise('shoulder_abduction')
    w._show_training_hub()
    assert w.pages.currentWidget() is w.catalog and w.catalog.joint == 'hip'


def test_late_duplicate_test_close_does_not_change_a_new_task(desktop):
    w, runtime, app = desktop
    w.state = 'ONLINE'
    w._handle_message(dict(kind='camera_test_stopped'))
    assert w.state == 'ONLINE'
