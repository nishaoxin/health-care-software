from __future__ import annotations

import copy
from collections import deque
from uuid import uuid4

from .geometry import in_roi, observed_interval_s


class ActivityEngine:
    def __init__(self, setup):
        self.setup = copy.deepcopy(setup)
        self.phase, self.message = 'UNKNOWN', '等待有效单人活动观察'
        self.totals = {k: 0. for k in ('SEATED', 'STANDING', 'WALKING', 'VISIBLE_MOVING')}
        self.continuous_sitting = 0.
        self.history = deque()
        self.previous = None
        self.last_good = self.first_t = self.last_t = None
        self.valid_s = 0.
        self.reminder_due = False
        self.snooze_until = 0.
        self.skip_until_change = False
        self.tasks, self.intervals = [], []

    def _classify(self, o):
        if o.status != 'VALID' or o.center_raw_px is None:
            return 'UNKNOWN'
        point = (o.center_raw_px[0]/o.size[0], o.center_raw_px[1]/o.size[1])
        knee, tilt = o.value('knee_flexion_deg'), o.value('trunk_tilt_deg')
        if knee is not None and knee >= 45 and in_roi(point, self.setup['rois'].get('chair')) and tilt is not None and tilt < 60:
            return 'SEATED'
        self.history.append((o.time_s, point[0], o.value('ankle_delta')))
        while self.history and o.time_s-self.history[0][0] > 2.5:
            self.history.popleft()
        moving = len(self.history) >= 3 and abs(point[0]-self.history[0][1]) > .03
        upright = knee is not None and knee <= 35 and tilt is not None and tilt <= 35
        lower_valid = o.value('left_knee') is not None and o.value('right_knee') is not None and o.value('ankle_delta') is not None
        signs = [1 if x[2] > .015 else -1 for x in self.history if x[2] is not None and abs(x[2]) > .015]
        alternations = sum(a != b for a, b in zip(signs, signs[1:]))
        if upright and lower_valid and moving and alternations >= 2:
            return 'WALKING'
        if moving:
            return 'VISIBLE_MOVING'
        return 'STANDING' if upright else 'UNKNOWN'

    def _interrupt_task(self, reason):
        if self.tasks and self.tasks[-1]['status'] == 'ACTIVE':
            self._transition(self.tasks[-1], 'INTERRUPTED', self.last_t, reason=reason)

    @staticmethod
    def _transition(task, status, time_s, **evidence):
        task.update(status=status, end_time_s=time_s, **evidence)
        task.setdefault('history', []).append(dict(status=status, time_s=time_s, **evidence))

    def process(self, o):
        t = o.time_s
        if self.last_t is not None and t <= self.last_t:
            return
        self.first_t = t if self.first_t is None else self.first_t
        broken = self.previous is not None and (t-self.previous.time_s > .5 or o.track_key != self.previous.track_key)
        if broken:
            self.history.clear()
            self.continuous_sitting = 0.
            self._interrupt_task('stream_gap_or_identity')
        state = self._classify(o)
        dt = 0.
        if self.previous is not None:
            dt = observed_interval_s(self.previous.time_s, t, self.phase, state,
                                     same_track=o.track_key == self.previous.track_key,
                                     previous_valid=self.phase != 'UNKNOWN', current_valid=state != 'UNKNOWN')
        if state in self.totals:
            self.totals[state] += dt
            self.valid_s += dt
            self.last_good = t
        if state == 'UNKNOWN':
            self.history.clear()
            if self.last_good is None or t-self.last_good > .5:
                self._interrupt_task('observation_unavailable')
        if state != 'SEATED' or broken:
            self.continuous_sitting = 0.
            self.reminder_due = False
            # A refusal applies to this observation run; movement is not consent to remind again.
        else:
            self.continuous_sitting += dt
        if state != self.phase:
            self.intervals.append({'state': state, 'time_s': t, 'track_key': o.track_key})
        self.phase, self.previous, self.last_t = state, o, t
        if (self.continuous_sitting >= self.setup['sedentary_trigger_s'] and t >= self.snooze_until
                and self.setup.get('allowed_activity_tasks', ('stand', 'walk'))
                and not self.skip_until_change and not (self.tasks and self.tasks[-1]['status'] == 'ACTIVE')):
            if not self.reminder_due and not (self.tasks and self.tasks[-1]['status'] == 'OFFERED'):
                self.tasks.append(self._new_task('offer', 'OFFERED', t, 0.))
            self.reminder_due = True
        if self.tasks and self.tasks[-1]['status'] == 'ACTIVE':
            task = self.tasks[-1]
            expected = 'STANDING' if task['kind'] == 'stand' else 'WALKING'
            if state == expected:
                task['visible_s'] += dt
            if task['visible_s']+1e-8 >= task['target_s']:
                self._transition(task, 'COMPLETED', t, visual_verified=True, evidence_method='VISION_VERIFIED')
        self.message = '已到可见久坐提醒时间，可选择任务、延期或拒绝' if self.reminder_due else '只累计相邻有效观察；缺测与出画不计入活动时间'
        if self.tasks and self.tasks[-1]['kind'] != 'offer':
            task = self.tasks[-1]
            label = {'ACTIVE': '进行中', 'COMPLETED': '已完成', 'INTERRUPTED': '已中断'}.get(task['status'], '待确认')
            self.message = f"任务{label} · 已视觉核实 {task['visible_s']:.1f} / {task['target_s']:.1f} 秒"
            if task['self_reported']:
                self.message += ' · 已另记自报完成'

    def _new_task(self, kind, status, time_s, target):
        return {'id': uuid4().hex, 'kind': kind, 'status': status, 'start_time_s': time_s,
                'target_s': target, 'visible_s': 0., 'visual_verified': False, 'self_reported': False,
                'evidence_method': None, 'threshold_profile': 'DEMO_THRESHOLDS' if self.setup['demo_thresholds'] else 'PERSONAL_SETTINGS',
                'history': [{'status': status, 'time_s': time_s}]}

    def choose_task(self, kind, time_s):
        if kind in ('stand', 'walk'):
            if kind not in self.setup.get('allowed_activity_tasks', ('stand', 'walk')):
                raise ValueError('本次未允许这项活动，请先核对本人活动安排')
            if self.tasks and self.tasks[-1]['status'] == 'ACTIVE' and self.tasks[-1]['kind'] == kind:
                return
            self._interrupt_task('new_task')
            if self.tasks and self.tasks[-1]['status'] == 'OFFERED':
                self._transition(self.tasks[-1], 'ACCEPTED', time_s)
            self.tasks.append(self._new_task(kind, 'ACTIVE', time_s,
                              self.setup['stand_target_s' if kind == 'stand' else 'walk_target_s']))
            self.reminder_due = False
        elif kind == 'snooze':
            self.snooze_until = time_s+(15 if self.setup['demo_thresholds'] else 300)
            self.reminder_due = False
            self._reminder_decision('SNOOZED', time_s)
        elif kind == 'skip':
            self.reminder_due, self.skip_until_change = False, True
            self._reminder_decision('DECLINED', time_s)
        elif kind == 'stop':
            self._interrupt_task('user_stop')
        elif kind == 'self_report' and self.tasks and self.tasks[-1]['kind'] in ('stand', 'walk'):
            self._interrupt_task('self_reported_stop')
            self.tasks[-1].update(self_reported=True, self_report_time_s=time_s, self_report_evidence='SELF_REPORTED')
        else:
            raise ValueError('请选择一个活动任务')

    def _reminder_decision(self, status, time_s):
        if self.tasks and self.tasks[-1]['status'] == 'ACTIVE':
            self._interrupt_task('user_'+status.lower())
        if self.tasks and self.tasks[-1]['status'] == 'OFFERED':
            self._transition(self.tasks[-1], status, time_s, snooze_until=self.snooze_until)
        elif not self.tasks or self.tasks[-1]['status'] != status:
            self.tasks.append(self._new_task('offer', status, time_s, 0.))

    def finish(self, reason):
        self._interrupt_task(reason)

    def summary(self):
        duration = self.last_t-self.first_t if self.first_t is not None else 0.
        return {'phase': self.phase, 'message': self.message, 'totals': self.totals.copy(),
                'continuous_sitting_s': self.continuous_sitting, 'reminder_due': self.reminder_due,
                'demo_thresholds': self.setup['demo_thresholds'], 'valid_s': self.valid_s,
                'observed_span_s': duration, 'valid_ratio': self.valid_s/duration if duration > 0 else None,
                'tasks': copy.deepcopy(self.tasks)}
