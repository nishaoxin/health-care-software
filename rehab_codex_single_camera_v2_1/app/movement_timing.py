"""Source-clock observations, separate from counting and clinical interpretation.

Joint phase segmentation is retrospective: three-sample medians at the middle
sample's timestamp delimit a single band within 3 degrees of the observed peak.
Live hold uses only consecutive valid observations, never future samples.
"""
from __future__ import annotations

import math
from statistics import median


TIMING_VERSION = 'observed-timing-1'
TIMING_FIELDS = ('outbound_min_s', 'outbound_max_s', 'return_min_s', 'return_max_s', 'hold_min_s')


def default_timing_plan():
    return dict.fromkeys(TIMING_FIELDS)


def validate_timing_plan(value, exercise_id, target):
    if value is None:
        return default_timing_plan()
    if not isinstance(value, dict) or set(value)-set(TIMING_FIELDS):
        raise ValueError('时间安排内容无效')
    result = {key: value.get(key) for key in TIMING_FIELDS}
    for number in result.values():
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number)
                                   or not 0 <= number <= 300):
            raise ValueError('动作时间应为 0–300 秒的有限数值，或留空')
    for phase in ('outbound', 'return'):
        low, high = result[phase+'_min_s'], result[phase+'_max_s']
        if low is not None and high is not None and low > high:
            raise ValueError('最短时间不能大于最长时间')
    if result['hold_min_s'] and target is None and exercise_id != 'sit_to_stand':
        raise ValueError('连续保持需要先填写人工角度目标；未设置角度时仅记录峰区停留')
    return result


def timing_for_plan(plan):
    value = validate_timing_plan(plan.get('timing_plan'), plan['exercise_id'], plan.get('target_angle_deg'))
    if plan['exercise_id'] == 'sit_to_stand':
        for bound in ('min', 'max'):
            key = 'return_'+bound+'_s'
            legacy = plan.get('lowering_tempo_'+bound+'_s')
            if value[key] is None:
                value[key] = legacy
            elif legacy is not None and legacy != value[key]:
                raise ValueError('旧下降节奏与回程安排不一致，请重新核对本次计划')
    return validate_timing_plan(value, plan['exercise_id'], plan.get('target_angle_deg'))


def _metric(value=None, reason=None):
    return {'value': value, 'valid': value is not None, 'reason': reason if value is None else None}


class MovementTiming:
    def __init__(self, *, direction, max_gap_s, target, goals, sit_to_stand=False):
        self.direction, self.max_gap_s, self.target = direction, max_gap_s, target
        self.goals = dict(default_timing_plan(), **goals)
        self.sit_to_stand = sit_to_stand
        self.samples = []
        self.gaps = []
        self.open_gap = None
        self.last_t = None
        self.hold_start = None
        self.hold_max = 0.
        self.hold_seen = False
        self.live_valid = False
        self.standing_t = self.return_t = None

    def break_continuity(self, t, reason):
        self.hold_start = None
        self.live_valid = False
        if self.open_gap is None:
            start = self.last_t if self.last_t is not None else t
            self.open_gap = [start, reason]

    def add(self, t, angle, *, at_standing=False):
        if type(t) not in (int, float) or not math.isfinite(t) or (self.last_t is not None and t <= self.last_t):
            return
        if type(angle) not in (int, float) or not math.isfinite(angle):
            self.break_continuity(t, 'invalid_metric')
            return
        if self.last_t is not None and t-self.last_t > self.max_gap_s:
            self.break_continuity(t, 'stream_gap')
        if self.open_gap is not None:
            self.gaps.append((self.open_gap[0], t, self.open_gap[1]))
            self.open_gap = None
        self.last_t = t
        self.samples.append((t, self.direction*angle))
        anchored = self.sit_to_stand or self.target is not None
        qualifies = at_standing if self.sit_to_stand else anchored and self.direction*(angle-self.target) >= 0
        self.live_valid = anchored
        if anchored:
            self.hold_seen = True
        if qualifies:
            if self.hold_start is None:
                self.hold_start = t
            self.hold_max = max(self.hold_max, t-self.hold_start)
        else:
            self.hold_start = None

    def mark_standing(self, t):
        self.standing_t = t

    def mark_return(self, t):
        self.return_t = t

    def live(self):
        elapsed = None if not self.live_valid else 0. if self.hold_start is None else self.last_t-self.hold_start
        return {'hold_elapsed_s': elapsed, 'hold_min_s': self.goals['hold_min_s'],
                'at_target': self.live_valid and self.hold_start is not None}

    def _interval(self, start, end, missing_reason):
        if start is None or end is None or end <= start:
            return _metric(reason=missing_reason)
        for left, right, reason in self.gaps:
            if left < end and right > start:
                return _metric(reason=reason)
        if self.open_gap and self.open_gap[0] < end:
            return _metric(reason=self.open_gap[1])
        return _metric(end-start)

    def snapshot(self, completion, *, cycle_complete=False, reason=None):
        missing = reason or 'incomplete_cycle'
        phases = {key: _metric(reason=missing) for key in ('outbound_s', 'endpoint_dwell_s', 'return_s')}
        if self.samples and self.sit_to_stand:
            start, end = self.samples[0][0], self.samples[-1][0]
            phases['outbound_s'] = self._interval(start, self.standing_t, 'standing_not_observed')
            phases['endpoint_dwell_s'] = self._interval(self.standing_t, self.return_t, missing)
            if cycle_complete:
                phases['return_s'] = self._interval(self.return_t, end, missing)
        elif completion == 'COMPLETE' and cycle_complete:
            if self.gaps or self.open_gap:
                why = self.gaps[0][2] if self.gaps else self.open_gap[1]
            elif len(self.samples) < 5:
                why = 'insufficient_valid_samples'
            else:
                smooth = [(self.samples[i][0], median(v for _, v in self.samples[i-1:i+2]))
                          for i in range(1, len(self.samples)-1)]
                peak = max(v for _, v in smooth)
                indices = [i for i, (_, value) in enumerate(smooth) if value >= peak-3.]
                first, last = indices[0], indices[-1]
                if self.samples[0][1] >= peak-3. or self.samples[-1][1] >= peak-3.:
                    why = 'unobserved_phase_boundary'
                elif len(indices) != last-first+1:
                    why = 'ambiguous_peak_band'
                else:
                    phases = dict(outbound_s=_metric(smooth[first][0]-self.samples[0][0]),
                                  endpoint_dwell_s=_metric(smooth[last][0]-smooth[first][0]),
                                  return_s=_metric(self.samples[-1][0]-smooth[last][0]))
                    why = None
            if why:
                phases = {key: _metric(reason=why) for key in phases}
        phases['target_hold_s'] = (_metric(self.hold_max) if self.hold_seen else
                                   _metric(reason='no_hold_anchor' if self.target is None and not self.sit_to_stand else 'no_valid_samples'))
        partial = bool(self.gaps or self.open_gap or completion != 'COMPLETE' or not cycle_complete)
        statuses = {}
        for phase in ('outbound', 'return', 'hold'):
            low = self.goals[phase+'_min_s']
            high = self.goals.get(phase+'_max_s')
            measured = phases['target_hold_s' if phase == 'hold' else phase+'_s']['value']
            if low is None and high is None:
                status = 'NOT_SET'
            elif measured is None:
                status = 'UNASSESSABLE'
            else:
                met = (low is None or measured+1e-8 >= low) and (high is None or measured <= high+1e-8)
                status = 'MET' if met else 'UNASSESSABLE' if phase == 'hold' and partial else 'NOT_MET'
            statuses[phase] = status
        return dict(phases, version=TIMING_VERSION, method='calibrated_standing' if self.sit_to_stand else 'peak_band_3deg_median3',
                    cycle_complete=cycle_complete, partial_observation=partial,
                    goals=statuses, arrangement=dict(self.goals))
