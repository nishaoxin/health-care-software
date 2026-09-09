"""Render native large-text guidance with explicit SYNTHETIC fixtures, no capture."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app.ui.distance_coach import DistanceCoach
from app.ui.theme import STYLE
from app.settings import default_plan
from app.exercises import exercise_spec


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    for name in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/name))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    out = ROOT/'qa-output/distance-v09'
    out.mkdir(parents=True, exist_ok=True)
    coach = DistanceCoach()
    coach.show()

    def capture(name):
        for _ in range(3):
            app.processEvents()
        assert coach.grab().save(str(out/(name+'.png')))
        print(name, coach.width(), coach.height())

    try:
        for width, height in ((1100, 730), (1360, 900), (1600, 1000)):
            coach.resize(width, height)
            for eid in ('shoulder_abduction', 'sit_to_stand', 'index_pip_flexion'):
                plan = default_plan(eid)
                metric = exercise_spec(eid)['metric']
                data = dict(state='ONLINE', observation_status='VALID', summary=dict(
                    phase='RAISING', completed=2, metrics={metric: dict(valid=True, value=40)}))
                coach.render(data, plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
                capture(f'{eid}-{width}')
            plan['submode'] = 'training'
            data['summary']['message'] = '按已确认方向，在舒适范围缓慢完成食指近端指间关节屈伸；当前 40°；未设置角度目标，按舒适范围活动'
            data['summary']['training'] = dict(stage='ACTIVE', set_number=1, target_sets=2,
                set_reps=2, target_reps=5, can_resume=False, can_pause=True)
            coach.render(data, plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
            capture(f'training-active-{width}')
            data['summary']['training'] = dict(stage='PAUSED', set_number=1, target_sets=2,
                set_reps=2, target_reps=5, can_resume=True, can_pause=False)
            coach.render(data, plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
            capture(f'paused-{width}')
            data.update(state='OFFLINE', error='合成界面测试：输入断开，未采集真实视频。')
            coach.render(data, plan, mirror=True, source_kind='SYNTHETIC', usage_context='TEST')
            capture(f'offline-{width}')
        coach.resize(1100, 730)
        coach.font_choice.setCurrentIndex(coach.font_choice.findData(48))
        plan = default_plan('index_pip_flexion')
        coach.render(dict(state='ONLINE', observation_status='VALID', summary=dict(
            phase='RAISING', metrics={exercise_spec('index_pip_flexion')['metric']: dict(valid=True, value=35)})),
            plan, mirror=False, source_kind='SYNTHETIC', usage_context='TEST')
        capture('large-font-48-1100')
    finally:
        coach.close()


if __name__ == '__main__':
    main()
