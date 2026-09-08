"""Render application-owned UI states only. No camera or private screen capture."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import queue
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.ui.dialogs import PlanDialog, EventsDialog
from app.settings import default_plan
from app.assessment import build_body_profile
from app.reports import render_body_profile
from app.exercises import exercise_spec


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()
    def command(self, name, **kwargs):
        self.messages.put({'kind': 'command_done', 'command': name})


app = QApplication([])
app.setStyle('Fusion')
for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/name))
out = ROOT/'qa-output'
out.mkdir(exist_ok=True)
window = MainWindow(runtime=PassiveRuntime())
window.show()
for scene in ('rehab', 'activity', 'bedroom_demo', 'safety_demo'):
    window._select_scene(scene)
    app.processEvents()
    window.grab().save(str(out/f'{scene}.png'))
window._history()
window._poll()
app.processEvents()
window.grab().save(str(out/'history-empty.png'))
window._select_rehab('training')
window._poll()
app.processEvents()
window.grab().save(str(out/'training-empty.png'))
window._select_rehab('assessment')
window._show_body()
window._poll()
profile = build_body_profile([], **window._body_scope_key())
window._handle_message({'kind': 'body_profile', 'profile': profile, 'html': render_body_profile(profile, compact=True)})
app.processEvents()
window.grab().save(str(out/'body-empty.png'))

# Explicitly labelled, in-memory fixtures for layout only; never save to user DB.
window._select_rehab('assessment')
window.source_kind.addItem('合成软件测试 · 布局样本', 'SYNTHETIC')
window.source_kind.setCurrentIndex(window.source_kind.findData('SYNTHETIC'))
window._poll()
sessions = []
for i, exercise in enumerate(('shoulder_abduction', 'shoulder_flexion', 'elbow_flexion', 'knee_extension', 'hip_abduction')):
    spec = exercise_spec(exercise)
    sessions.append({'id': 'synthetic-layout-'+str(i), 'participant_id': window.participant_id,
                     'scene_id': 'rehab', 'submode': 'assessment', 'exercise_id': exercise, 'side': 'left',
                     'source_kind': 'SYNTHETIC', 'usage_context': 'TEST', 'source_ref': 'synthetic-layout',
                     'status': 'FINISHED', 'stop_reason': 'user_stop',
                     'start_utc': '2026-09-08T00:00:00+00:00', 'end_utc': '2026-09-08T00:00:10+00:00',
                     'summary': {'primary_metric': spec['metric'], 'valid_s': 9, 'observed_span_s': 10,
                                 'valid_ratio': .9, 'completed': 3, 'partial': 0, 'invalid': 0,
                                 'motion_range': {'min_deg': 5, 'max_deg': 85, 'range_deg': 80},
                                 'motion_range_valid': True, 'valid_sample_count': 30}})
window._show_body()
window._poll()
profile = build_body_profile(sessions, window.participant_id, 'SYNTHETIC', 'TEST')
window._handle_message({'kind': 'body_profile', 'profile': profile, 'html': render_body_profile(profile, compact=True)})
app.processEvents()
window.grab().save(str(out/'body-synthetic.png'))
window._train_from_body()
window._poll()
app.processEvents()
window.grab().save(str(out/'training-linked.png'))
plan = PlanDialog(window.setup['plan'], window)
plan.show()
app.processEvents()
plan.grab().save(str(out/'plan.png'))
plan.close()
for eid in ('hip_flexion', 'wrist_flexion', 'ankle_dorsiflexion', 'index_pip_flexion'):
    window._select_rehab('assessment')
    window.joint_group.setCurrentIndex(window.joint_group.findData('all'))
    window.exercise.setCurrentIndex(window.exercise.findData(eid))
    window._poll()
    app.processEvents()
    window.grab().save(str(out/f'expanded-{eid}.png'))
window._allow_close = True
window.close()
print('Rendered scenes, assessment/body/training workflow, history and plan; only labelled synthetic fixtures, no camera or user DB opened.')
