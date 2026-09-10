"""Native history and real Runtime/SQLite using explicitly synthetic dated cases."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from app.ui.longitudinal import LongitudinalDialog
from app.ui.theme import STYLE
from app.runtime import Runtime
from app.storage import Storage
from test_training_runtime import response
import test_app_controller as fixtures


def sample(angle, index):
    f = fixtures.ControllerTests()
    f.setUp()
    try:
        f.c.start()
        t = 0.
        for value in (0, angle, 0):
            for _ in range(20):
                f.frame(t, value)
                t += .1
        f.c.stop('user_stop')
        result = f.store.get_session(f.c.last_saved_id)
        # Dates are test inputs for sorting, not a claimed observation history.
        result.update(id=f'synthetic-history-{index}', start_utc=f'2026-09-{index:02d}T08:00:00+00:00',
                      end_utc=f'2026-09-{index:02d}T08:01:00+00:00')
        return result
    finally:
        f.tearDown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'longitudinal')
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases = [sample(angle, index) for index, angle in enumerate((65, 75, 80, 0, 70, 72), 1)]
    cases[2]['model_manifest_id'] = 'synthetic-other-model'
    cases[3].update(status='INTERRUPTED', stop_reason='synthetic_missing_case', summary={}, metrics=[], repetitions=[])
    cases[5]['model_manifest_id'] = None
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        store = Storage(directory/'home_rehab.sqlite3')
        for case in cases:
            store.save_session(case)
        store.close()
        runtime = Runtime(directory)
        dialog = LongitudinalDialog()
        dialog.setStyleSheet(STYLE)
        try:
            assert runtime.ready.wait(5)
            def fetch(sid, request):
                messages = response(runtime, 'longitudinal_history', anchor_id=sid, request_id=request)
                message = next(m for m in messages if m['kind'] == 'longitudinal_history')
                dialog.receive(message['history'], message['request_id'])
            dialog.anchor_requested.connect(fetch)
            dialog.show()
            dialog.request(cases[0]['id'])
            assert dialog.table.rowCount() == 6
            for width, height in ((1180, 820), (880, 650)):
                dialog.resize(width, height)
                app.processEvents()
                assert dialog.grab().save(str(output/f'history-{width}.png'))
            dialog.resize(1180, 820)
            dialog.table.selectRow(2)
            app.processEvents()
            dialog.grab().save(str(output/'condition-difference.png'))
            dialog.metric_choice.setCurrentIndex(dialog.metric_choice.findData('return_s'))
            app.processEvents()
            dialog.grab().save(str(output/'timing-history.png'))
            history = dialog.history
            replies = response(runtime, 'export_longitudinal_history', anchor_id=history['anchor_id'],
                                metric='return_s', expected_fingerprint=history['fingerprint'], directory=str(output/'export'), request_id='qa-export')
            assert any(m['kind'] == 'longitudinal_exported' for m in replies)
            renderer = QSvgRenderer(str(output/'export/chart.svg'))
            assert renderer.isValid()
            canvas = QImage(940, 270, QImage.Format.Format_ARGB32)
            canvas.fill(Qt.GlobalColor.white)
            painter = QPainter(canvas)
            renderer.render(painter)
            painter.end()
            canvas.save(str(output/'export-chart.png'))
            assert runtime.camera.worker is None
            result = dict(source_kind='SYNTHETIC', usage_context='TEST', dates='constructed_fixture_dates', camera_opened=False,
                          rows=len(history['rows']), comparison_statuses=[r['comparison']['status'] for r in history['rows']],
                          export_content_verified=True, native_sizes=[[1180,820],[880,650]],
                          evidence_scope='Synthetic snapshot sorting, source conditions, UI and report export only.')
            (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print('PASS: native longitudinal chart, condition gaps, metric selection, real Runtime, temp SQLite and SVG/HTML/JSON/CSV export.')
        finally:
            dialog.close()
            response(runtime, 'shutdown')
            runtime.thread.join(5)
            assert not runtime.thread.is_alive()


if __name__ == '__main__':
    main()
