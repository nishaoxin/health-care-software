from __future__ import annotations

import copy
from statistics import median
from .domain import clean_json


class RehabEngine:
    """Causal, explicit exercise state machines. No camera/model access."""

    def __init__(self, plan):
        self.plan = copy.deepcopy(plan)
        self.exercise = plan['exercise_id']
        self.phase = 'WAIT_READY'
        self.repetitions = []
        self.current = None
        self.last_standing_rep = None
        self.last_t = self.first_t = self.last_good_t = None
        self.last_track = None
        self.previous_valid = False
        self.valid_s = 0.
        self.holds = {}
        self.issue_starts = {}
        self.latest_metrics = {}
        self.message = '请在舒适的准备姿势保持约 1 秒'

    @property
    def completed(self):
        return sum(r['completion_status'] == 'COMPLETE' for r in self.repetitions)

    def _held(self, key, condition, t, duration):
        if not condition:
            self.holds.pop(key, None)
            return False
        return t - self.holds.setdefault(key, t) + 1e-8 >= duration

    def _new(self, t):
        self.current = {'start_time_s': t, 'samples': {}, 'unavailable': {}, 'issues': []}
        self.issue_starts.clear()

    def _collect(self, o):
        if self.current is None:
            return
        for name, metric in o.metrics.items():
            if (self.exercise == 'shoulder_abduction' and name in ('elbow_flexion_deg', 'trunk_tilt_deg')
                    and (self.phase not in ('RAISING', 'PEAK_OR_HOLD') or (o.value('raise_deg') or 0) <= self.plan['rest_deg'])):
                continue
            if metric.valid:
                self.current['samples'].setdefault(name, []).append(metric.value)
            else:
                self.current['unavailable'][name] = metric.reason
        if self.exercise != 'shoulder_abduction' or self.phase not in ('RAISING', 'PEAK_OR_HOLD'):
            return
        for rule, name, limit_name in (
            ('elbow_flexion', 'elbow_flexion_deg', 'allowed_elbow_flexion_deg'),
            ('trunk_tilt', 'trunk_tilt_deg', 'allowed_trunk_tilt_deg'),
        ):
            value, limit = o.value(name), self.plan[limit_name]
            if value is None or limit is None or value <= limit:
                self.issue_starts.pop(rule, None)
                continue
            start = self.issue_starts.setdefault(rule, o.time_s)
            if o.time_s - start + 1e-8 < self.plan['issue_hold_s']:
                continue
            issue = next((x for x in self.current['issues'] if x['rule_id'] == rule), None)
            if issue is None:
                issue = {'rule_id': rule, 'phase': self.phase, 'start_time_s': start,
                         'end_time_s': o.time_s, 'metric': name, 'measured_value': value,
                         'configured_limit': limit, 'evidence_valid': True,
                         'feedback_emitted_at': None}
                self.current['issues'].append(issue)
            issue['end_time_s'] = o.time_s
            issue['measured_value'] = max(issue['measured_value'], value)

    @staticmethod
    def _stable_peak(samples):
        if len(samples) < 3:
            return None
        return max(median(samples[i:i+3]) for i in range(len(samples)-2))

    def _record(self, t, completion, reason=None):
        if self.current is None:
            return None
        c = self.current
        sample_metrics = c['samples']
        validity = {}
        for key in set(sample_metrics) | set(c['unavailable']):
            present = bool(sample_metrics.get(key))
            validity[key] = {'valid': present, 'reason': None if present else c['unavailable'][key],
                             'partial_observation': key in c['unavailable']}
        peak = self._stable_peak(sample_metrics.get('raise_deg', []))
        knee_samples = sample_metrics.get('knee_flexion_deg', [])
        knee_min = min(knee_samples) if len(knee_samples) >= 3 else None
        target = self.plan['target_angle_deg']
        measured = peak if self.exercise == 'shoulder_abduction' else knee_min
        if target is None:
            target_status = 'NOT_SET'
        elif measured is None or completion in ('UNASSESSABLE', 'INTERRUPTED'):
            target_status = 'UNASSESSABLE'
        else:
            met = measured >= target if self.exercise == 'shoulder_abduction' else measured <= target
            target_status = 'MET' if met else 'NOT_MET'
        observation_status = ('UNUSABLE' if completion == 'UNASSESSABLE' else
                              'PARTIAL_OBSERVABLE' if c['unavailable'] or reason else 'VALID')
        rep = {'number': len(self.repetitions)+1, 'start_time_s': c['start_time_s'],
               'end_time_s': t, 'duration_s': max(0., t-c['start_time_s']),
               'observation_status': observation_status,
               'observation_reasons': sorted(set(c['unavailable'].values()) | ({reason} if reason else set())),
               'completion_status': completion, 'target_status': target_status,
               'max_raise_projection_deg': peak, 'min_knee_flexion_projection_deg': knee_min,
               'rise_time_s': max(0., t-c['start_time_s']) if self.exercise == 'sit_to_stand' and completion == 'COMPLETE' else None,
               'lowering_time_s': None, 'metric_validity': validity, 'issues': copy.deepcopy(c['issues'])}
        if self.exercise == 'sit_to_stand' and target_status == 'NOT_MET':
            rep['issues'].append({'rule_id': 'target_not_reached', 'phase': self.phase,
                                 'start_time_s': c['start_time_s'], 'end_time_s': t,
                                 'metric': 'knee_flexion_deg', 'measured_value': knee_min,
                                 'configured_limit': target, 'evidence_valid': True,
                                 'feedback_emitted_at': None})
        self.repetitions.append(rep)
        self.current = None
        self.issue_starts.clear()
        return rep

    def _interrupt(self, t, reason):
        self._record(t, 'UNASSESSABLE', reason)
        self.phase = 'WAIT_READY'
        self.holds.clear()
        self.last_standing_rep = None

    def process(self, o):
        t = o.time_s
        if self.last_t is not None and t <= self.last_t:
            return
        if self.first_t is None:
            self.first_t = t
        dt = 0 if self.last_t is None else t-self.last_t
        identity_change = self.last_track is not None and o.track_key is not None and self.last_track != o.track_key
        gap = dt > self.plan['max_gap_s']
        if gap or identity_change or o.status == 'MULTI_PERSON':
            self._interrupt(t, 'identity_ambiguous' if identity_change or o.status == 'MULTI_PERSON' else 'stream_gap')
            self.previous_valid = False
        self.last_t = t
        if o.track_key is not None:
            self.last_track = o.track_key
        necessary = ('raise_deg',) if self.exercise == 'shoulder_abduction' else ('knee_flexion_deg', 'hip_y')
        valid = o.status == 'VALID' and all(o.value(k) is not None for k in necessary)
        self.latest_metrics = clean_json(o.metrics)
        if not valid:
            self.holds.clear()
            self.issue_starts.clear()
            self.previous_valid = False
            self.message = '当前画面无法可靠测量，请检查单人站位和必要关节'
            if self.last_good_t is not None and t-self.last_good_t > self.plan['max_gap_s']:
                self._interrupt(t, 'occlusion')
            return
        if self.previous_valid and not gap and not identity_change:
            self.valid_s += dt
        self.previous_valid, self.last_good_t = True, t
        self._collect(o)
        if self.exercise == 'shoulder_abduction':
            self._shoulder(o)
        else:
            self._sitstand(o)

    def _shoulder(self, o):
        t, angle = o.time_s, o.value('raise_deg')
        rest, dwell = self.plan['rest_deg'], self.plan['dwell_s']
        if self.phase == 'WAIT_READY':
            self.message = '请自然垂臂，保持舒适准备姿势约 1 秒'
            if self._held('ready', angle <= rest, t, self.plan['ready_s']):
                self.phase, self.message = 'REST', '准备就绪，可按已确认计划抬臂'
        elif self.phase == 'REST':
            if self._held('raise', angle >= rest+self.plan['raising_delta_deg'], t, dwell):
                self._new(t-dwell)
                self.phase, self.message = 'RAISING', '正在观察抬举'
                self._collect(o)
        else:
            peak = max(self.current['samples'].get('raise_deg', [angle]))
            if angle <= rest and self._held('return', True, t, dwell):
                self._record(t, 'COMPLETE')
                self.phase, self.message = 'REST', f'已记录 {self.completed} 次完整往返'
                self.holds.clear()
            elif angle > rest:
                self.holds.pop('return', None)
                if angle < peak-8:
                    self.phase, self.message = 'LOWERING', '正在观察回位'
                elif self.phase == 'RAISING' and t-self.current['start_time_s'] > .5:
                    self.phase = 'PEAK_OR_HOLD'

    def _sitstand(self, o):
        t, knee, hip = o.time_s, o.value('knee_flexion_deg'), o.value('hip_y')
        c = self.plan['calibration']
        if not all(k in c for k in ('seated_knee', 'standing_knee', 'seated_hip_y', 'standing_hip_y')):
            self.message = '请先确认舒适坐位和站位基线'
            return
        seated = knee >= c['seated_knee']-12 and hip >= c['seated_hip_y']-.04
        standing = knee <= c['standing_knee']+10 and hip <= c['standing_hip_y']+.04
        rising = knee < c['seated_knee']-10 and hip < c['seated_hip_y']-.025
        dwell = self.plan['dwell_s']
        if self.phase == 'WAIT_READY':
            self.message = '请在已确认的座椅上保持舒适坐位约 1 秒'
            if self._held('sit_ready', seated, t, self.plan['ready_s']):
                self.phase, self.message = 'SEATED_READY', '准备就绪，可按已确认计划起立'
        elif self.phase == 'SEATED_READY':
            if self._held('rise', rising, t, dwell):
                self._new(t-dwell)
                self.phase, self.message = 'RISING', '正在观察起立'
                self._collect(o)
        elif self.phase == 'RISING':
            if self._held('stand', standing, t, dwell):
                self.last_standing_rep = self._record(t, 'COMPLETE')
                self.phase, self.message = 'STANDING_REACHED', f'已完成 {self.completed} 次起立；回坐后才开始下一次'
                self.holds.clear()
            elif self._held('partial', seated, t, dwell):
                self._record(t, 'PARTIAL')
                self.phase, self.message = 'SEATED_READY', '已记录部分起立'
                self.holds.clear()
        elif self.phase == 'STANDING_REACHED':
            if not standing and self._held('lower', knee > c['standing_knee']+15, t, dwell):
                self.phase = 'LOWERING'
                self.lower_start = t-dwell
        elif self.phase == 'LOWERING' and self._held('reseat', seated, t, dwell):
            if self.last_standing_rep is not None:
                duration = t-self.lower_start
                self.last_standing_rep['lowering_time_s'] = duration
                low, high = self.plan['lowering_tempo_min_s'], self.plan['lowering_tempo_max_s']
                if (low is not None and duration < low) or (high is not None and duration > high):
                    self.last_standing_rep['issues'].append({
                        'rule_id': 'lowering_tempo', 'phase': 'LOWERING', 'start_time_s': self.lower_start,
                        'end_time_s': t, 'metric': 'lowering_time_s', 'measured_value': duration,
                        'configured_limit': [low, high], 'evidence_valid': True, 'feedback_emitted_at': None})
            self.phase, self.message = 'SEATED_READY', '已观察回坐，可开始下一次'
            self.holds.clear()

    def finish(self, reason):
        self._record(self.last_t or 0, 'INTERRUPTED', reason)
        self.phase = 'FINISHED'

    def summary(self):
        duration = (self.last_t-self.first_t) if self.first_t is not None else 0
        current_issues = []
        if self.current and self.phase in ('RAISING', 'PEAK_OR_HOLD'):
            for issue in self.current['issues']:
                metric = self.latest_metrics.get(issue['metric'], {})
                if metric.get('valid') and metric.get('value', 0) > issue['configured_limit']:
                    current_issues.append(copy.deepcopy(issue))
        message = self.message
        if current_issues:
            labels = {'elbow_flexion': '本次上举时可见屈肘超出已设范围', 'trunk_tilt': '本次上举时可见躯干侧倾超出已设范围'}
            message = '；'.join(labels[i['rule_id']] for i in current_issues[:2])
        goal = self.plan['target_reps']*self.plan['target_sets']
        if self.completed >= goal:
            message = f'已完成计划的 {goal} 次，可停止并保存本次任务'
        return {'completed': self.completed, 'target_met': sum(r['target_status'] == 'MET' for r in self.repetitions),
                'partial': sum(r['completion_status'] == 'PARTIAL' for r in self.repetitions),
                'invalid': sum(r['completion_status'] in ('INTERRUPTED', 'UNASSESSABLE') for r in self.repetitions),
                'valid_s': self.valid_s, 'observed_span_s': duration,
                'valid_ratio': self.valid_s/duration if duration > 0 else None,
                'phase': self.phase, 'message': message, 'metrics': self.latest_metrics,
                'current_issues': current_issues, 'plan_completed': self.completed >= goal,
                'completed_sets': min(self.plan['target_sets'], self.completed//self.plan['target_reps'])}
