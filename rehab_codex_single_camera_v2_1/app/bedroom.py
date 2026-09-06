from __future__ import annotations

import copy
from uuid import uuid4

from .domain import utc_now
from .geometry import in_roi


class BedroomEngine:
    def __init__(self, setup):
        self.setup = copy.deepcopy(setup)
        self.phase, self.message = 'UNKNOWN', '等待床区有效观察'
        self.previous = None
        self.first_t = self.last_t = None
        self.valid_s = 0.
        self.intervals, self.events = [], []
        self.edge_stand_seen = False
        self.assistance_notified = False

    def process(self, o):
        t = o.time_s
        if self.last_t is not None and t <= self.last_t:
            return
        self.first_t = t if self.first_t is None else self.first_t
        continuity = self.previous is not None and 0 < t-self.previous.time_s <= .5 and self.previous.track_key == o.track_key
        if not continuity:
            self.edge_stand_seen = False
        state = 'UNKNOWN'
        if o.status == 'VALID' and o.center_raw_px is not None:
            point = (o.center_raw_px[0]/o.size[0], o.center_raw_px[1]/o.size[1])
            knee, tilt = o.value('knee_flexion_deg'), o.value('trunk_tilt_deg')
            rois = self.setup['rois']
            if in_roi(point, rois.get('bed_edge')) and knee is not None and tilt is not None:
                if knee >= 45 and tilt < 60:
                    state = 'BED_EDGE_SIT'
                elif knee < 30 and tilt < 35:
                    state = 'BED_EDGE_STAND'
                    self.edge_stand_seen = True
            elif in_roi(point, rois.get('bed')) and tilt is not None and tilt >= 50:
                state = 'VISIBLE_IN_BED'
                self.edge_stand_seen = False
                self.assistance_notified = False
            elif in_roi(point, rois.get('exit')) and self.edge_stand_seen and continuity:
                state = 'OBSERVED_EXIT'
        if state == 'UNKNOWN':
            self.edge_stand_seen = False
        elif self.phase != 'UNKNOWN' and continuity:
            self.valid_s += t-self.previous.time_s
        if state != self.phase:
            self.intervals.append({'time_s': t, 'state': state})
        if (state in ('BED_EDGE_SIT', 'BED_EDGE_STAND') and self.setup['needs_assistance']
                and self.setup['night_confirmed'] and not self.assistance_notified):
            self.events.append({'id': uuid4().hex, 'status': 'OPEN', 'rule_id': 'assistance_during_configured_night_demo',
                'message': '已配置需要协助：夜间演示中观察到床边起身，请人工查看',
                'evidence_start_time': t, 'first_observed_abnormal_time': t, 'event_emitted_time': t,
                'created_utc': utc_now(), 'human_ack_time': None, 'evidence': {'observed_state': state}})
            self.assistance_notified = True
        self.phase, self.previous, self.last_t = state, o, t
        prefix = '床区受控演示' if self.setup['real_bed'] else '模拟区域演示'
        self.message = prefix+' · '+('当前观察不足；没有看到人不等于已离床' if state == 'UNKNOWN' else '仅记录当前可见过程')

    def finish(self, reason):
        pass

    def summary(self):
        duration = self.last_t-self.first_t if self.first_t is not None else 0.
        return {'phase': self.phase, 'message': self.message, 'valid_s': self.valid_s,
                'observed_span_s': duration, 'valid_ratio': self.valid_s/duration if duration > 0 else None,
                'real_bed_confirmed': self.setup['real_bed'], 'observations': copy.deepcopy(self.intervals)}
