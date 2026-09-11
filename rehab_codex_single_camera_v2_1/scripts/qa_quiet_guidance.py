"""Synthetic native UI QA for quiet guidance; never opens a camera."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import argparse
import json
from pathlib import Path
import queue
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.runtime import Runtime
from app.storage import Storage
from app.reports import export_session
from app.ui.main_window import MainWindow
from app.ui.distance_coach import DistanceCoach
from test_product_navigation import PassiveRuntime
from test_dual_ui import select_pair
from test_dual_controller import DualFixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'quiet-guidance-v014')
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    window = MainWindow(runtime=PassiveRuntime())
    window.auto_distance.setChecked(False)
    window.show()
    coach = DistanceCoach(window)
    screenshots, labels = [], {}

    def capture(name, widget, controls=()):
        QTest.qWait(70)
        for control in controls:
            point = control.mapTo(widget, QPoint(0, control.height()))
            assert control.isVisible() and point.y() <= widget.height(), (name, control.text(), point.y(), widget.height())
        assert widget.grab().save(str(output/(name+'.png')))
        screenshots.append(name+'.png')

    try:
        select_pair(window, app)
        window._choose_catalog_exercise('shoulder_abduction')
        window.resize(1100, 730)
        with tempfile.TemporaryDirectory() as directory:
            f = DualFixture(Path(directory))
            runtime = Runtime.__new__(Runtime)
            runtime.controller, runtime.views, runtime.camera_test = f.c, queue.Queue(maxsize=1), False
            window.setup = f.c.setup
            window._accept_context_frames = True

            def view(now):
                with patch('app.runtime.time.monotonic', return_value=now):
                    runtime._view(f.c.latest_packet, f.c.latest_pose)
                return runtime.views.get_nowait()

            window._render_view(view(0))
            window._journey_framed = True
            window._buttons()
            window.setup_tabs.setCurrentIndex(0)
            capture('preparation-review', window, (window.preparation_review, window.confirm_button, window.privacy_button))
            window.setup_tabs.setCurrentIndex(1)
            window._handle_message(dict(kind='preparation', context=f.c.context, active=True, text='3 秒后采样，请保持当前舒适姿势。'))
            window.setup_panel.ensureWidgetVisible(window.preparation_cancel)
            capture('countdown', window, (window.preparation_cancel, window.privacy_button))
            window._handle_message(dict(kind='preparation', context=f.c.context, active=False, text='本次采样已取消。'))
            f.start()
            f.cycle()
            window.setup_tabs.setCurrentIndex(0)
            coach.resize(1100, 730)
            coach.show()

            def display(name, data):
                window._render_view(data)
                coach.render(data, f.c.setup['plan'], mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
                labels[name] = dict(data['guidance'])
                capture(name+'-main', window, (window.stop_button, window.privacy_button))
                capture(name+'-large', coach, (coach.finish, coach.privacy))

            display('valid', view(1))
            f.emit(7., auxiliary_missing=True)
            auxiliary = view(1.1)
            assert auxiliary['current_measurement_valid']
            display('auxiliary-missing', auxiliary)
            for now, t, label in ((2., 7.1, 'transient'), (3.6, 7.2, 'adjustment')):
                packet, pose = f.emit(t, return_input=True)
                pose.people[0].conf[11] = .01
                f.c.consume(packet, pose)
                data = view(now)
                assert not data['current_measurement_valid']
                display(label, data)
                assert window.angle_card.value.text() == '—'
            f.emit(7.3)
            display('recovered', view(3.7))
            assert '左髋' not in window.exercise_guide.instruction.text()
            window.resize(1360, 900)
            capture('recovered-main-wide', window, (window.stop_button, window.privacy_button))
            sid = f.c.session['id']
            f.c.stop('user_stop')
            f.close()
            reader = Storage(Path(directory)/'two-view.sqlite3')
            saved = reader.get_session(sid)
            reader.close()
            assert saved['dual_camera']['summary']['main_only_observations'] == 1
            export_session(saved, output/'export')
            failed = dict(state='SAVE_FAILED', context=None, summary={}, confirmed=False, pending=True)
            from app.guidance import GuidancePolicy
            failed['guidance'] = GuidancePolicy().render(failed, f.setup['plan'], now=4)
            window._render_view(failed)
            capture('save-failed', window, (window.retry_button, window.backup_button))
        (output/'result.json').write_text(json.dumps(dict(source_kind='SYNTHETIC', usage_context='TEST',
            camera_opened=False, storage_reopened=True, screenshots=screenshots, labels=labels,
            summary=saved['dual_camera']['summary']), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('PASS: countdown, single manual review, transient/adjustment/recovery, dual partial validity, save recovery and SQLite export.')
    finally:
        coach.close()
        window._allow_close = True
        window.close()


if __name__ == '__main__':
    main()
