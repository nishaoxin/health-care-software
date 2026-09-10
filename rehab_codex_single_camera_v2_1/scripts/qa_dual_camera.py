"""Render native two-view UI using explicitly synthetic observations and a temporary database."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import argparse
import json
from pathlib import Path
import queue
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.runtime import Runtime
from app.storage import Storage
from app.reports import render_report, export_session
from app.ui.main_window import MainWindow
from app.ui.camera_test import CameraTestDialog
from app.ui.distance_coach import DistanceCoach
from app.ui.dialogs import ReportDialog
from test_training_ui import PassiveRuntime
from test_dual_ui import select_pair
from test_dual_controller import DualFixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'dual-camera-v013')
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    window = MainWindow(runtime=PassiveRuntime())
    window.auto_distance.setChecked(False)
    window.show()
    screenshots, geometry = [], {}

    def capture(name, widget):
        QTest.qWait(60)
        assert widget.grab().save(str(output/(name+'.png')))
        screenshots.append(name+'.png')

    try:
        select_pair(window, app)
        window._choose_catalog_exercise('shoulder_abduction')
        window.resize(1100, 730)
        capture('selection', window)
        with tempfile.TemporaryDirectory() as directory:
            fixture = DualFixture(Path(directory))
            runtime = Runtime.__new__(Runtime)
            runtime.controller, runtime.views, runtime.camera_test = fixture.c, queue.Queue(maxsize=1), False
            fixture.start()
            fixture.cycle()
            runtime._view(fixture.c.latest_packet, fixture.c.latest_pose)
            data = runtime.views.get_nowait()
            assert data['context'].source_kind == 'SYNTHETIC' and data['context'].usage_context == 'TEST'
            window.setup = fixture.c.setup
            window._accept_context_frames = True
            window._render_view(data)
            for width, height in ((1100, 730), (1360, 900)):
                window.resize(width, height)
                capture(f'paired-{width}', window)
                panel = window.video_pair
                hosts = [panel.primary_host, panel.secondary_host]
                geometry[str(width)] = [list(w.geometry().getRect()) for w in hosts]
                assert not hosts[0].geometry().intersects(hosts[1].geometry())
                assert all(w.geometry().right() < panel.width()+1 for w in hosts)
                for canvas in (panel.primary_canvas, panel.secondary_canvas):
                    bottom = canvas.mapTo(window.monitor_scroll.viewport(), QPoint(0, canvas.height())).y()
                    assert bottom <= window.monitor_scroll.viewport().height(), (width, bottom)
            raw = CameraTestDialog('合成双摄输入 · 软件界面检查', window, dual_view=fixture.source['dual_camera'])
            raw.show()
            raw.render(dict(data, state='PREVIEW', pose=None, camera_test=True, confirmed=False, summary={}))
            capture('raw-pair-test', raw)
            assert not raw.video_pair.auxiliary_values.text()
            raw.finish_close()
            coach = DistanceCoach(window)
            coach.show()
            coach.render(data, fixture.c.setup['plan'], mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
            capture('distance-pair', coach)
            coach.close()
            fixture.emit(7., auxiliary_missing=True)
            runtime._view(fixture.c.latest_packet, fixture.c.latest_pose)
            missing = runtime.views.get_nowait()
            window._render_view(missing)
            capture('auxiliary-missing', window)
            assert missing['observation_status'] == 'UNKNOWN' and '辅助机位' in missing['measurement_hint']
            sid = fixture.c.session['id']
            fixture.c.stop('user_stop')
            fixture.close()
            reader = Storage(Path(directory)/'two-view.sqlite3')
            saved = reader.get_session(sid)
            reader.close()
            assert saved['summary']['completed'] == 1 and saved['dual_camera']['summary']['paired_observations'] == 61
            exported = export_session(saved, output/'export')
            assert (exported/'dual-camera.csv').is_file()
            report = ReportDialog(saved, render_report(saved), lambda _: None, window)
            report.show()
            report.browser.find('双摄观察')
            report.browser.verticalScrollBar().setValue(report.browser.verticalScrollBar().value()+580)
            capture('report-dual', report)
            report.close()
        result = dict(source_kind='SYNTHETIC', usage_context='TEST', camera_opened=False,
                      storage_reopened=True, completed=1, paired_observations=61,
                      screenshots=screenshots, geometry=geometry,
                      evidence_scope='Synthetic trajectories, native UI and SQLite reopen; no human or camera accuracy validation.')
        (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('PASS: native two-view selection, paired display, raw test, large guide, auxiliary missingness, SQLite reopen and export.')
    finally:
        window._allow_close = True
        window.close()


if __name__ == '__main__':
    main()
