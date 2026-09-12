"""Synthetic native UI QA for the calmer exercise flow; never opens a camera.

It renders the real windows with injected synthetic frames and a temporary
database. It proves interface behaviour only: no human accuracy, no hardware.
"""
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
from app.guidance import GuidancePolicy
from app.guided import prompt_state
from app.journey import SCENE_ROIS
from app.reports import continuation_evidence, export_session, render_result_summary
from app.runtime import Runtime
from app.storage import Storage
from app.ui.distance_coach import DistanceCoach
from app.ui.main_window import MainWindow
from test_dual_controller import DualFixture
from test_dual_ui import select_pair
from test_product_navigation import PassiveRuntime

SIZES = ((1100, 730), (1360, 900))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'smooth-flow-v017')
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
    screenshots, steps, notes = [], [], {}

    def capture(name, widget, controls=()):
        QTest.qWait(70)
        for control in controls:
            point = control.mapTo(widget, QPoint(0, control.height()))
            assert control.isVisible() and point.y() <= widget.height(), (name, control.text(), point.y(), widget.height())
            assert point.x() >= 0 and point.x()+control.width() <= widget.width(), (name, control.text())
        assert widget.grab().save(str(output/(name+'.png')))
        screenshots.append(name+'.png')

    def note_step(label):
        step = window._journey_step()
        steps.append(dict(label=label, key=step.key, number=step.number, total=step.total,
                          title=step.title, action=step.action))
        return step

    try:
        select_pair(window, app)
        window._choose_catalog_exercise('shoulder_abduction')
        window.resize(*SIZES[0])
        note_step('closed-camera')
        capture('start-closed', window, (window.preview_button, window.camera_test_button))
        with tempfile.TemporaryDirectory() as directory:
            f = DualFixture(Path(directory))
            runtime = Runtime.__new__(Runtime)
            runtime.controller, runtime.views, runtime.camera_test = f.c, queue.Queue(maxsize=1), False
            runtime.guided_started, runtime.guided_paused_at = None, None
            window.setup = f.c.setup
            window._accept_context_frames = True

            def view(now, **extra):
                with patch('app.runtime.time.monotonic', return_value=now):
                    runtime._view(f.c.latest_packet, f.c.latest_pose)
                data = runtime.views.get_nowait()
                data.update(extra)
                return data

            def show(data, now):
                with patch('app.ui.main_window.time.monotonic', return_value=now):
                    window._render_view(data)

            # Framing is acknowledged by a steady picture, not an extra click.
            show(view(0.), 100.)
            assert not window._journey_framed
            note_step('framing-waiting')
            f.emit(6.)
            show(view(.1), 101.4)
            assert window._journey_framed, 'a steady picture should advance framing'
            step = note_step('after-auto-framing')
            assert step.key == 'confirm'
            capture('auto-framing', window, (window.confirm_button, window.privacy_button))

            # A failed sampling offers the guided path instead of a dead end.
            window._handle_message(dict(kind='preparation', context=f.c.context, active=False,
                                        text='尚未取得连续稳定画面。可以再试一次，也可以改用引导计时练习。'))
            assert window.journey.offer.isVisible()
            notes['sampling_offer'] = window.journey.offer.text()
            capture('sampling-offer', window, (window.preparation_retry, window.journey.guided, window.privacy_button))

            # A long gap offers it quietly, without a dialog.
            policy = GuidancePolicy()
            for i in range(40):
                data = view(.2, current_measurement_valid=False, observation_status='UNKNOWN',
                            adjustment='请让测试部位清楚进入画面。')
                data['guidance'] = policy.render(data, f.c.setup['plan'], now=i*.5)
                show(data, 110.+i*.5)
            assert data['guidance']['offer'] == 'guided', data['guidance']
            notes['gap_offer'] = data['guidance']['offer_text']
            assert window.notice.isHidden(), 'a quiet offer must not raise the top banner'
            capture('gap-offer', window, (window.journey.offer, window.privacy_button))

            # Countdown before starting, cancellable.
            f.emit(6.1)
            show(view(.3), 140.)
            window._confirmed = True
            window._buttons()
            assert note_step('ready-to-start').key == 'start'
            window.start_button.click()
            assert window._start_countdown == 3
            capture('countdown', window, (window.journey.cancel_countdown, window.privacy_button))
            window._cancel_start_countdown()

            # Guided run: prompts, self report and prompt pause in both views.
            window._set_guided_mode(True)
            assert window._read_setup()['continuation_mode'] == 'guided'
            note_step('guided-confirm')
            capture('guided-preview', window, (window.journey.guided, window.confirm_button))
            f.setup['continuation_mode'] = 'guided'
            f.c.setup['continuation_mode'] = 'guided'
            f.start()
            runtime.guided_started = 0.
            coach.resize(*SIZES[0])
            coach.show()
            for name, now, self_reported in (('guided-prompt', 4., 0), ('guided-reported', 5., 2)):
                data = view(now, self_reported=self_reported)
                data['guided_prompt'] = prompt_state(now, 'shoulder_abduction')
                data['guidance'] = GuidancePolicy().render(data, f.c.setup['plan'], now=now)
                show(data, 150.+now)
                coach.render(data, f.c.setup['plan'], mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
                notes[name] = dict(instruction=data['guidance']['instruction'], status=data['guidance']['status'],
                                   quality=data['guidance']['measurement_quality'])
                capture(name+'-main', window, (window.self_report_button, window.guided_pause_button, window.privacy_button))
                capture(name+'-large', coach, (coach.self_report, coach.guided_pause, coach.finish, coach.privacy))
            paused = view(9., self_reported=2)
            paused['guided_prompt'] = dict(prompt_state(9., 'shoulder_abduction'), paused=True)
            paused['guidance'] = GuidancePolicy().render(paused, f.c.setup['plan'], now=9.)
            assert paused['guidance']['level'] == 'paused'
            show(paused, 162.)
            coach.render(paused, f.c.setup['plan'], mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
            assert coach.guided_pause.text() == '继续提示'
            capture('guided-paused-large', coach, (coach.guided_pause, coach.finish, coach.privacy))

            # A guided record saves, reopens and says what it cannot claim.
            f.c.record_self_report()
            f.c.record_self_report()
            sid = f.c.session['id']
            f.c.stop('user_stop')
            f.close()
            reader = Storage(Path(directory)/'two-view.sqlite3')
            saved = reader.get_session(sid)
            reader.close()
            assert saved['measurement_mode'] == 'guided_timed'
            assert saved['summary']['self_reported_reps'] == 2 and saved['summary']['completed'] == 0
            evidence = continuation_evidence(saved)
            summary_html = render_result_summary(saved)
            assert '引导计时' in summary_html and '不作为训练所需的评估依据' in summary_html
            export_session(saved, output/'export-guided')
            window._summarize_after_save = window._body_scope_key()
            show(dict(state='UNSELECTED', context=None, confirmed=False, summary={}), 170.)
            assert window.setup_tabs.currentIndex() == 2, 'finishing returns to the step list'
            window._handle_message(dict(kind='saved', id=saved['id']))
            assert window._latest_report_id == saved['id']
            window._handle_message(dict(kind='report', snapshot=saved, html=summary_html))
            for dialog in list(window.report_windows):
                dialog.close()
            window._buttons()
            step = note_step('completion-summary')
            assert step.key == 'result'
            notes['completion_summary'] = window._completion_summary(step)
            assert '自己记录的完成次数：2 次' in notes['completion_summary']
            window.journey_scroll.ensureWidgetVisible(window.journey.another)
            capture('completion-summary', window, (window.journey.another, window.journey.detail, window.preview_button))

        # Companion scenes now use the same short step list.
        for command in ('report', 'body_profile'):
            window._handle_message(dict(kind='command_done', command=command))
        assert window.busy == 0, window.busy
        for scene in ('activity', 'bedroom_demo', 'safety_demo'):
            window._select_scene(scene)
            note_step(scene+'-closed')
            window.state = 'PREVIEW'
            window._buttons()
            note_step(scene+'-regions')
            window._journey_next()
            assert '还需要圈定' in window.journey.message.text()
            window.setup['rois'] = {name: [.1, .1, .6, .6] for name, _ in SCENE_ROIS[scene]}
            window._buttons()
            note_step(scene+'-next')
            if scene == 'activity':
                window._journey_next()
                assert window.permission.isChecked()
                note_step(scene+'-permitted')
            window.setup_tabs.setCurrentIndex(2)
            capture(scene+'-steps', window, (window.confirm_button, window.privacy_button))
            window.state = 'UNSELECTED'
            window.setup['rois'] = {}
            window.permission.setChecked(False)
        window._select_scene('rehab')
        for width, height in SIZES:
            window.resize(width, height)
            window.state = 'UNSELECTED'
            window._buttons()
            capture(f'layout-closed-{width}x{height}', window, (window.preview_button, window.camera_test_button))
            window.state = 'PREVIEW'
            window._buttons()
            capture(f'layout-preview-{width}x{height}', window,
                    (window.confirm_button, window.privacy_button, window.distance_button))
            window.state = 'ONLINE'
            window._buttons()
            capture(f'layout-running-{width}x{height}', window,
                    (window.stop_button, window.privacy_button, window.self_report_button))
        window.state = 'UNSELECTED'
        window._buttons()
        (output/'result.json').write_text(json.dumps(dict(
            source_kind='SYNTHETIC', usage_context='TEST', camera_opened=False, storage_reopened=True,
            screenshots=screenshots, journey_steps=steps, notes=notes, continuation=evidence,
            window_sizes=[list(size) for size in SIZES]), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('PASS: auto framing, quiet guided offer, cancellable countdown, guided prompts with pause '
              'and self report, saved guided record with honest labels, and companion-scene steps.')
    finally:
        coach.close()
        window._allow_close = True
        window.close()


if __name__ == '__main__':
    main()
