from __future__ import annotations

import math
from .domain import Metric, Observation
from .geometry import angle_deg


class PoseAnalyzer:
    def __init__(self, side='left', conf_min=.5, tau=.12, max_gap=.5):
        self.side, self.conf_min, self.tau, self.max_gap = side, conf_min, tau, max_gap
        self.previous = {}
        self.previous_track = None

    def analyze(self, frame):
        if (frame.schema_id != 'coco17-v1' or frame.coordinate_space != 'raw_image_pixels'
                or frame.keypoint_order_version != 'coco17-anatomical-lr-v1'):
            raise ValueError('骨架 schema / 坐标系 / 关节顺序不兼容')
        t = frame.time_s
        if t is None or not math.isfinite(t):
            raise ValueError('视频时间不可用，不能计时')
        status = 'NO_PERSON_DETECTED' if not frame.people else 'MULTI_PERSON'
        if len(frame.people) != 1:
            self.previous.clear()
            return Observation(t, None, status, {}, size=frame.size, reasons=[status.lower()])
        p = frame.people[0]
        if len(p.xy) != 17 or len(p.conf) != 17:
            raise ValueError('COCO17 关键点数量不符合契约')
        if p.track_key is None:
            return Observation(t, None, 'UNKNOWN', {}, size=frame.size, reasons=['identity_ambiguous'])
        if p.track_key != self.previous_track:
            self.previous.clear()
            self.previous_track = p.track_key
        w, h = frame.size
        if w <= 0 or h <= 0:
            raise ValueError('画面尺寸不可用')
        points, reasons = {}, {}
        for i, (point, confidence) in enumerate(zip(p.xy, p.conf)):
            if len(point) != 2 or not all(math.isfinite(float(v)) for v in (*point, confidence)):
                reasons[i] = 'nonfinite'
            elif confidence < self.conf_min:
                reasons[i] = 'low_confidence'
            elif not (0 < point[0] < w and 0 < point[1] < h):
                reasons[i] = 'out_of_frame'
            else:
                previous = self.previous.get(i)
                raw = (float(point[0]), float(point[1]))
                if previous and 0 < t - previous[0] <= self.max_gap:
                    dt = t - previous[0]
                    if math.dist(raw, previous[2]) > math.hypot(w, h) * .35:
                        reasons[i] = 'coordinate_jump'
                        self.previous.pop(i, None)
                        continue
                    a = 1 - math.exp(-dt / self.tau)
                    points[i] = tuple(previous[1][j] + a * (raw[j] - previous[1][j]) for j in (0, 1))
                else:
                    points[i] = raw
                self.previous[i] = (t, points[i], raw)
            if i in reasons:
                self.previous.pop(i, None)

        def measured(ids, fn):
            missing = [f'{i}:{reasons.get(i, "missing")}' for i in ids if i not in points]
            if missing:
                return Metric.missing(','.join(missing))
            return Metric.of(fn(*(points[i] for i in ids)))

        sh, el, wr, hi, kn, an = (5, 7, 9, 11, 13, 15) if self.side == 'left' else (6, 8, 10, 12, 14, 16)

        def flexion(a, b, c):
            angle = angle_deg(a, b, c)
            return None if angle is None else 180 - angle

        def tilt(ls, rs, lh, rh):
            dx, dy = (ls[0]+rs[0]-lh[0]-rh[0])/2, (ls[1]+rs[1]-lh[1]-rh[1])/2
            return None if math.hypot(dx, dy) < 1e-8 else math.degrees(math.atan2(abs(dx), abs(dy)))

        metrics = {
            'raise_deg': measured([hi, sh, el], angle_deg),
            'elbow_flexion_deg': measured([sh, el, wr], flexion),
            'knee_flexion_deg': measured([hi, kn, an], flexion),
            'trunk_tilt_deg': measured([5, 6, 11, 12], tilt),
            'hip_y': measured([hi], lambda a: a[1]/h),
            'left_knee': measured([11, 13, 15], flexion),
            'right_knee': measured([12, 14, 16], flexion),
            'ankle_delta': measured([15, 16], lambda a, b: (a[0]-b[0])/w),
        }
        raw_center = None
        local = None
        if all(i in points for i in (5, 6, 11, 12)):
            # Preserve unsmoothed global displacement separately from local shape.
            raw_center = tuple((p.xy[11][j]+p.xy[12][j])/2 for j in (0, 1))
            shoulder = tuple((p.xy[5][j]+p.xy[6][j])/2 for j in (0, 1))
            scale = math.dist(raw_center, shoulder)
            metrics['torso_scale_px'] = Metric.of(scale if scale > 1 else None)
            if scale > 1:
                local = [([(p.xy[i][j]-raw_center[j])/scale for j in (0, 1)]
                          if i in points else None) for i in range(17)]
        valid = any(m.valid for m in metrics.values())
        return Observation(t, p.track_key, 'VALID' if valid else 'UNKNOWN', metrics,
                           raw_center, p.bbox, local, frame.size, sorted(set(reasons.values())))
