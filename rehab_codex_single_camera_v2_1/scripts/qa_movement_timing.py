"""Native timing controls/readouts/report with synthetic trajectories only."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QScrollArea
from app.ui.main_window import MainWindow
from app.ui.dialogs import PlanDialog, ReportDialog
from app.ui.distance_coach import DistanceCoach
from app.settings import default_plan
from app.storage import Storage
from app.reports import render_report, export_session
from test_training_execution import Sequence
from test_training_ui import PassiveRuntime, render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'movement-timing')
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    window = MainWindow(runtime=PassiveRuntime())
    window.auto_distance.setChecked(False)
    window._select_rehab('training')
    window.source_kind.addItem('合成测试', 'SYNTHETIC')
    window.source_kind.setCurrentIndex(window.source_kind.findData('SYNTHETIC'))
    window.replay_row.hide()
    window.pages.setCurrentIndex(0)
    window.resize(1180, 800)
    window.show()

    def capture(name, widget):
        app.processEvents()
        assert widget.grab().save(str(output/(name+'.png')))

    try:
        plan = default_plan('sit_to_stand')
        plan['submode'] = 'training'
        dialog = PlanDialog(plan, window)
        dialog.timing_controls['hold_min_s'].setValue(3)
        dialog.timing_controls['outbound_min_s'].setValue(.5)
        dialog.timing_controls['return_max_s'].setValue(6)
        dialog.show()
        capture('plan', dialog)
        dialog.findChild(QScrollArea).ensureWidgetVisible(dialog.timing_controls['hold_min_s'])
        capture('plan-timing', dialog)
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
        assert dialog.plan['training_plan_confirmed']
        seq = Sequence('sit_to_stand', target_reps=1, target_sets=1, timing_plan=dialog.plan['timing_plan'])
        window.exercise.setCurrentIndex(window.exercise.findData('sit_to_stand'))
        window.setup['plan'] = seq.engine.plan
        window._sync_scene()
        seq.frames(knee=90, hip=.65)
        seq.frames(knee=40, hip=.52)
        seq.frames(knee=5, hip=.4)
        render(window, seq.engine.summary())
        window.source_badge.setText('合成数据 / 软件测试 · 无摄像头')
        capture('hold', window)
        coach = DistanceCoach(window)
        data = dict(state='ONLINE', context=None, summary=seq.engine.summary(), observation_status='VALID')
        coach.render(data, seq.engine.plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
        coach.show()
        capture('hold-large', coach)
        assert '1.4 / 3 秒' in coach.hold.text()
        coach.close()
        seq.frames(knee=5, hip=.4, n=25)
        seq.frames(knee=45, hip=.52)
        seq.frames(knee=90, hip=.65)
        seq.engine.finish('user_stop')
        snapshot = dict(id='timing-ui-qa', participant_id='synthetic-timing', scene_id='rehab', exercise_id='sit_to_stand',
                        side='left', submode='training', source_kind='SYNTHETIC', usage_context='TEST', status='FINISHED',
                        start_utc='2026-09-10T08:00:00+00:00', end_utc='2026-09-10T08:00:12+00:00',
                        config_snapshot={'plan': seq.engine.plan}, summary=seq.engine.summary(), repetitions=seq.engine.repetitions)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'test.sqlite3'
            store = Storage(path)
            store.save_session(snapshot)
            store.close()
            store = Storage(path)
            reopened = store.get_session(snapshot['id'])
            store.close()
        timing = reopened['repetitions'][0]['movement_timing']
        assert timing['goals']['hold'] == 'MET' and timing['return_s']['valid']
        exported = export_session(reopened, output/'export')
        report = ReportDialog(reopened, render_report(reopened), lambda _: None, window)
        report.show()
        report.browser.find('动作时间')
        app.processEvents()
        bar = report.browser.verticalScrollBar()
        bar.setValue(bar.value()+500)
        capture('report-timing', report)
        report.close()
        result = dict(source_kind='SYNTHETIC', usage_context='TEST', camera_opened=False,
                      ui_confirmed=True, storage_reopened=True, completed=seq.engine.completed,
                      timing=timing, export_directory=exported.name,
                      evidence_scope='Controlled observations and native UI only; no human accuracy validation.')
        (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('PASS: native manual timing plan, standing hold, large guide, SQLite reopen and timing report/export.')
    finally:
        window._allow_close = True
        window.close()


if __name__ == '__main__':
    main()
