from dataclasses import replace
import time

import pytest

from app.domain import Context
from app.dual_camera import FramePairer, secondary_context
from app.ui.distance_coach import DistanceCoach
from test_product_navigation import desktop
from test_clarity_ui import enumerate_result, drain_commands
from test_camera_selection import camera
from test_camera_test_runtime import packet


def select_pair(window, app):
    enumerate_result(window, [camera('front'), camera('side', index=7)])
    window.dual_toggle.setChecked(True)
    window.device.setCurrentIndex(1)
    window.secondary_device.setCurrentIndex(2)
    drain_commands(window)
    app.processEvents()


def pair_view(state='PREVIEW', primary='frontal'):
    ctx = Context(12, 'rehab', 'pair-ui-fixture', 'LIVE_CAMERA', 'TEST')
    main = packet(ctx)
    main.time_s = main.received_monotonic = time.monotonic()-.1
    other = 'sagittal' if primary == 'frontal' else 'frontal'
    secondary = replace(main, context=secondary_context(ctx, other), seq=5,
                        time_s=main.time_s+.02, received_monotonic=main.received_monotonic+.02)
    pairer = FramePairer(ctx, primary)
    pairer.add(primary, main)
    pairer.add(other, secondary)
    paired = pairer.take()
    return dict(state=state, context=ctx, packet=paired, pose=None, confirmed=False, summary={},
                dual_camera=dict(primary_view=primary, secondary_view=other, pairing=paired.pairing,
                                 auxiliary_status='VALID', auxiliary_metrics={'aux_trunk_sagittal_deg': dict(valid=True, value=14.5)}))


def test_two_roles_must_be_selected_explicitly_and_do_not_open_automatically(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera('front'), camera('side', index=7)])
    w.dual_toggle.setChecked(True)
    assert w.secondary_device.currentData() is None
    with pytest.raises(ValueError):
        w._source()
    w.device.setCurrentIndex(1)
    w.secondary_device.setCurrentIndex(2)
    source = w._source()
    assert source['dual_camera']['primary_view'] == 'frontal'
    assert source['dual_camera']['devices']['sagittal']['path'] == camera('side')['path']
    assert all('index' not in d for d in source['dual_camera']['devices'].values())
    assert not any(name in ('camera_test', 'open', 'confirm', 'start') for name, _ in runtime.calls)


def test_duplicate_role_and_missing_saved_second_device_do_not_fall_back(desktop):
    w, runtime, app = desktop
    select_pair(w, app)
    w.secondary_device.setCurrentIndex(1)
    with pytest.raises(ValueError, match='同一'):
        w._source()
    w.secondary_device.setCurrentIndex(2)
    enumerate_result(w, [camera('front')])
    assert w.secondary_device.currentData() is None
    with pytest.raises(ValueError):
        w._source()


def test_action_selects_its_matching_primary_view_and_requires_two_view_confirmation(desktop):
    w, runtime, app = desktop
    select_pair(w, app)
    w._choose_catalog_exercise('elbow_flexion')
    assert w._source()['dual_camera']['primary_view'] == 'sagittal'
    assert w._source()['device_ref']['path'] == camera('side')['path']
    assert '两路' in w.manual.text() and '两路' in w.poses.text()
    assert not w._read_setup()['dual_camera']['same_participant_confirmed']
    w.manual.setChecked(True)
    assert w._read_setup()['dual_camera']['same_participant_confirmed']


def test_pair_preferences_rebind_paths_after_index_change_without_enabling_capture(desktop):
    w, runtime, app = desktop
    refs = {'frontal': camera('front'), 'sagittal': camera('side', index=7)}
    w._handle_message(dict(kind='ready', preferred_camera_pair=refs, preferred_camera=None))
    enumerate_result(w, [camera('side', index=18), camera('front', index=23)])
    drain_commands(w)
    w.dual_toggle.setChecked(True)
    assert w.device.currentData()['index'] == 23 and w.secondary_device.currentData()['index'] == 18
    assert not any(name in ('camera_test', 'open', 'start', 'confirm') for name, _ in runtime.calls)


def test_independent_raw_camera_dialog_shows_two_views_and_closes_both_through_one_command(desktop):
    w, runtime, app = desktop
    select_pair(w, app)
    w.camera_test_button.click()
    app.processEvents()
    drain_commands(w)
    dialog = w.camera_test_dialog
    assert runtime.calls[-1][0] == 'camera_test' and 'dual_camera' in runtime.calls[-1][1]['source']
    data = pair_view()
    data['camera_test'] = True
    w._render_view(data)
    assert dialog.canvas.image is not None and dialog.video_pair.secondary_canvas.image is not None
    dialog.mirror_toggle.setChecked(False)
    assert not dialog.canvas.mirror and not dialog.video_pair.secondary_canvas.mirror
    assert '接收' in dialog.video_pair.pair_info.text()
    assert not dialog.video_pair.auxiliary_values.text()
    assert '画面测试' in dialog.video_pair.primary_title.text()
    dialog.reject()
    assert runtime.calls[-1][0] == 'stop_camera_test'
    assert dialog.canvas.image is None and dialog.video_pair.secondary_canvas.image is None
    w._handle_message(dict(kind='camera_test_stopped'))


@pytest.mark.parametrize('width,height', [(1100, 730), (1360, 900)])
def test_main_pair_view_layout_and_config_change_clear_both_images(desktop, width, height):
    w, runtime, app = desktop
    select_pair(w, app)
    w._choose_catalog_exercise('shoulder_abduction')
    w._accept_context_frames = True
    w.resize(width, height)
    w._render_view(pair_view())
    app.processEvents()
    panel = w.video_pair
    assert panel.secondary_canvas.image is not None and panel.primary_canvas.image is not None
    assert panel.primary_host.geometry().right() < panel.width()+1
    assert panel.secondary_host.geometry().right() < panel.width()+1
    assert not panel.primary_host.geometry().intersects(panel.secondary_host.geometry())
    w._invalidate()
    assert panel.primary_canvas.image is None and panel.secondary_canvas.image is None
    assert runtime.calls[-1][0] == 'switch'


def test_dual_controls_are_locked_while_running_and_inactive_in_replay_or_other_scenes(desktop):
    w, runtime, app = desktop
    select_pair(w, app)
    w.state = 'ONLINE'
    w._buttons()
    assert not w.dual_toggle.isEnabled() and not w.secondary_device.isEnabled()
    w.state = 'UNSELECTED'
    w.source_kind.setCurrentIndex(1)
    assert w.dual_row.isHidden()
    w.source_kind.setCurrentIndex(0)
    w._select_scene('activity')
    assert w.dual_row.isHidden() and 'dual_camera' not in w._source()


def test_large_guidance_shows_second_view_and_clears_both_when_either_is_stale(desktop):
    w, runtime, app = desktop
    coach = DistanceCoach(w)
    data = pair_view('ONLINE')
    data.update(observation_status='VALID', summary=dict(completed=1, phase='REST', metrics={'raise_deg': dict(valid=True, value=10)}))
    try:
        coach.render(data, w.setup['plan'], mirror=True, source_kind='LIVE_CAMERA', usage_context='TEST')
        assert coach.video_pair.secondary_canvas.image is not None
        data['packet'].paired_frame.received_monotonic -= 4.
        coach.render(data, w.setup['plan'], mirror=True, source_kind='LIVE_CAMERA', usage_context='TEST')
        assert coach.canvas.image is None and coach.video_pair.secondary_canvas.image is None
        assert coach.presentation.currentWidget() is coach.hold
    finally:
        coach.close()
