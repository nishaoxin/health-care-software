from __future__ import annotations

import copy
from uuid import uuid4

from .domain import utc_now
from .geometry import in_roi


class SafetyEngine:
    def __init__(self, setup):
        self.setup = copy.deepcopy(setup)
        self.phase, self.message = 'UNKNOWN', '等待有效地面关注区观察'
        self.events = []
        self.previous = None
        self.first_t = self.last_t = self.low_start = self.descent_time = self.normal_since = None
        self.baseline_scale = None
        self.low_valid_s = self.valid_s = 0.
        self.latched = False
        self.previous_valid = False

    def process(self, o):
        t = o.time_s
        if self.last_t is not None and t <= self.last_t:
            return
        self.first_t = t if self.first_t is None else self.first_t
        dt = 0 if self.last_t is None else t-self.last_t
        same = self.previous is not None and o.track_key == self.previous.track_key
        continuous = same and 0 < dt <= .5
        tilt = o.value('trunk_tilt_deg')
        valid = o.status == 'VALID' and o.center_raw_px is not None and tilt is not None
        if not continuous or not valid:
            self.low_start = self.descent_time = self.normal_since = None
            self.low_valid_s = 0.
        if valid and self.previous_valid and continuous:
            self.valid_s += dt
        if not valid:
            self.phase, self.message = 'UNKNOWN', '观察不足；已有事件保持待处理状态'
        else:
            point = (o.center_raw_px[0]/o.size[0], o.center_raw_px[1]/o.size[1])
            scale = o.value('torso_scale_px')
            if self.baseline_scale is None and scale and scale > 1:
                self.baseline_scale = scale
            if continuous and self.previous_valid and self.previous.center_raw_px and self.baseline_scale:
                velocity = (o.center_raw_px[1]-self.previous.center_raw_px[1])/dt/self.baseline_scale
                if velocity > .35:
                    self.descent_time = t
            excluded = any(in_roi(point, self.setup['rois'].get(name)) for name in ('bed', 'chair', 'sofa'))
            box = o.bbox_raw_px
            broad = bool(box and box[3] > box[1] and (box[2]-box[0])/(box[3]-box[1]) > 1.2)
            low = in_roi(point, self.setup['rois'].get('floor_watch')) and not excluded and (tilt >= 60 or broad)
            if low:
                if self.low_start is None:
                    self.low_start = t
                    self.low_valid_s = 0.
                elif continuous:
                    self.low_valid_s += dt
                self.normal_since = None
                self.phase, self.message = 'LOW_CANDIDATE', '已观察疑似异常低位，请人工检查当前画面'
                if self.low_valid_s+1e-8 >= self.setup['low_hold_s']:
                    self.phase = 'LOW_EVENT'
                    if not self.latched:
                        seen_descent = self.descent_time is not None and self.low_start-.8 <= self.descent_time <= t
                        message = '观察到下降后的持续异常低位，待人工确认' if seen_descent else '持续异常低位，下降过程未观察，待人工确认'
                        self.events.append({'id': uuid4().hex, 'status': 'OPEN', 'message': message,
                            'rule_id': 'descent_then_low' if seen_descent else 'persistent_low_without_observed_descent',
                            'evidence_start_time': self.descent_time if seen_descent else self.low_start,
                            'first_observed_abnormal_time': self.low_start, 'event_emitted_time': t,
                            'created_utc': utc_now(), 'human_ack_time': None,
                            'evidence': {'low_valid_s': self.low_valid_s, 'trunk_tilt_deg': tilt,
                                         'center_raw_px': o.center_raw_px, 'baseline_torso_px': self.baseline_scale,
                                         'floor_roi': self.setup['rois']['floor_watch']}})
                        self.latched = True
                    self.message = '疑似低位事件已记录；请到事件页面查看和处理'
            else:
                self.low_start, self.low_valid_s = None, 0.
                self.normal_since = t if self.normal_since is None else self.normal_since
                if t-self.normal_since >= 2:
                    self.latched = False
                self.phase, self.message = 'OBSERVING', '当前未形成低位事件证据；这不表示安全保证'
        self.previous, self.last_t, self.previous_valid = o, t, valid

    def finish(self, reason):
        pass  # Events are only closed by explicit human transitions in Storage.

    def summary(self):
        duration = self.last_t-self.first_t if self.first_t is not None else 0.
        return {'phase': self.phase, 'message': self.message, 'event_count': len(self.events),
                'low_observed_s': self.low_valid_s, 'valid_s': self.valid_s, 'observed_span_s': duration,
                'valid_ratio': self.valid_s/duration if duration > 0 else None, 'controlled_demo': True}
