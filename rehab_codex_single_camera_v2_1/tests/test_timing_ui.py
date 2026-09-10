import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from app.movement_timing import default_timing_plan
from app.settings import default_plan
from app.ui.dialogs import PlanDialog
from test_training_ui import desktop, render
from test_training_execution import Sequence
from app.ui.distance_coach import DistanceCoach


def test_optional_timing_controls_roundtrip_in_plan_and_reopen(desktop):
    window, _, app = desktop
    plan = default_plan()
    plan['submode'] = 'training'
    dialog = PlanDialog(plan, window, template_mode=True)
    dialog.target.setValue(60)
    dialog.timing_controls['outbound_min_s'].setValue(1.5)
    dialog.timing_controls['hold_min_s'].setValue(2)
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.plan['timing_plan']['hold_min_s'] == 2
    assert not dialog.plan['training_plan_confirmed']
    reopened = PlanDialog(dialog.plan, window)
    assert reopened.timing_controls['outbound_min_s'].value() == 1.5
    assert reopened.timing_controls['return_max_s'].value() == -1
    reopened._save()
    assert reopened.plan['training_plan_confirmed']


def test_missing_hold_anchor_keeps_draft_open_with_reason(desktop, monkeypatch):
    window, _, app = desktop
    notices = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: notices.append(args[2]))
    dialog = PlanDialog(default_plan(), window)
    dialog.timing_controls['hold_min_s'].setValue(2)
    dialog._save()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.timing_controls['hold_min_s'].value() == 2
    assert '角度' in notices[-1]


def test_old_sitstand_arrangement_has_one_editable_return_range(desktop):
    window, _, app = desktop
    plan = default_plan('sit_to_stand')
    plan['lowering_tempo_min_s'] = 2
    dialog = PlanDialog(plan, window)
    assert dialog.timing_controls['return_min_s'].value() == 2
    dialog.timing_controls['return_min_s'].setValue(3)
    dialog._save()
    assert dialog.plan['lowering_tempo_min_s'] is None
    assert dialog.plan['timing_plan']['return_min_s'] == 3


def test_live_timing_hides_on_missing_pause_and_scene_change(desktop):
    window, _, app = desktop
    window._select_rehab('training')
    seq = Sequence(target_angle_deg=60, timing_plan=dict(default_timing_plan(), hold_min_s=3))
    seq.frames(0)
    seq.frames(75)
    render(window, seq.engine.summary())
    assert '本段连续保持 1.4 秒' in window.timing_readout.text()
    assert '连续观察' in window.feedback.text()
    render(window, seq.engine.summary(), observation_status='UNKNOWN')
    assert not window.timing_readout.isVisible()
    seq.command('pause')
    render(window, seq.engine.summary())
    assert not window.timing_readout.isVisible()
    assert '已暂停' in window.feedback.text()
    window._sync_scene()
    assert not window.timing_readout.text()


def test_large_guidance_does_not_prompt_return_before_manual_hold_is_observed(desktop):
    window, _, app = desktop
    seq = Sequence('sit_to_stand', target_reps=1, target_sets=1,
                   timing_plan=dict(default_timing_plan(), hold_min_s=3))
    seq.frames(knee=90, hip=.65)
    seq.frames(knee=40, hip=.52)
    seq.frames(knee=5, hip=.4)
    coach = DistanceCoach(window)
    data = dict(state='ONLINE', context=None, summary=seq.engine.summary(), observation_status='VALID')
    coach.render(data, seq.engine.plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
    assert coach.presentation.currentWidget() is coach.hold
    assert '1.4 / 3 秒' in coach.hold.text()
    data['observation_status'] = 'UNKNOWN'
    coach.render(data, seq.engine.plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
    assert '看不清' in coach.hold.text() and '1.4' not in coach.hold.text()
    coach.close()
