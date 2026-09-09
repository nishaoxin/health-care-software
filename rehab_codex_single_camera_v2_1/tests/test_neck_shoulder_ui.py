import pytest
from PySide6.QtWidgets import QMessageBox

from app.settings import default_plan
from test_product_navigation import desktop
from test_distance_ui import coach, render, state


def test_shoulder_setup_names_and_confirmed_start_are_visible(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_adduction')
    assert w.joint_rest_button.text() == '记录侧抬臂起点'
    assert '不是垂臂' in w.joint_baseline_text.text()
    assert '不是横向抱胸' in w.camera_instruction.text()
    w.setup['plan']['joint_baseline'] = {'rest_value': 55.}
    w._sync_scene()
    assert '55°' in w.joint_baseline_text.text()
    w._choose_catalog_exercise('neck_flexion')
    assert '另一侧肩膀' in w.camera_instruction.text()
    assert w.joint_rest_button.text() == '记录舒适起始姿势'


@pytest.mark.parametrize('accepted', [False, True])
def test_shoulder_recording_requires_explicit_raised_start_confirmation(desktop, monkeypatch, accepted):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_adduction')
    prompts = []
    def question(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, 'question', question)
    w._record_joint_baseline('rest')
    assert '不是垂臂' in prompts[0]
    assert runtime.calls == ([('joint_baseline', {'position': 'rest'})] if accepted else [])


@pytest.mark.parametrize('ui_state', ['PREVIEW', 'ONLINE'])
def test_named_missing_points_show_in_main_feedback(desktop, ui_state):
    w, runtime, app = desktop
    w._choose_catalog_exercise('neck_flexion')
    w._render_view(dict(state=ui_state, context=None, confirmed=False, summary={},
                        measurement_hint='未看清：左髋；请让同侧髋入镜。'))
    assert '左髋' in w.feedback.text()


def test_large_guidance_names_missing_point_and_never_overwrites_rest(coach):
    c, app = coach
    plan = default_plan('neck_flexion')
    data = state('neck_flexion')
    data['summary']['metrics']['neck_flexion_excursion_deg']['valid'] = False
    data['measurement_hint'] = '未看清：左髋；请让同侧髋入镜。'
    render(c, data, plan)
    assert c.presentation.currentWidget() is c.hold
    assert '左髋' in c.feedback.text()
    data['summary']['training'] = state('neck_flexion', stage='PAUSED')['summary']['training']
    plan['submode'] = 'training'
    render(c, data, plan)
    assert '暂停' in c.hold.text() and '左髋' not in c.feedback.text()
