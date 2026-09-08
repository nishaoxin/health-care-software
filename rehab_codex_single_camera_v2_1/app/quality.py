from __future__ import annotations

import math
from .domain import Metric, Observation
from .geometry import angle_deg
from .landmark_schemas import SCHEMAS, ORDERS
from .exercises import exercise_spec


def signed_angle(a, b):
    if min(math.hypot(*a), math.hypot(*b)) < 1.:
        return None
    return math.degrees(math.atan2(a[0]*b[1]-a[1]*b[0], a[0]*b[0]+a[1]*b[1]))


def angle_delta(value, reference):
    return (value-reference+180) % 360-180


class PoseAnalyzer:
    def __init__(self, side='left', conf_min=.5, tau=.12, max_gap=.5, exercise_id=None, joint_baseline=None):
        self.side, self.conf_min, self.tau, self.max_gap = side, conf_min, tau, max_gap
        self.previous = {}
        self.previous_track = None
        self.exercise_id = exercise_id
        self.joint_baseline = joint_baseline or {}

    def analyze(self, frame):
        if (frame.schema_id not in SCHEMAS or frame.coordinate_space != 'raw_image_pixels'
                or frame.keypoint_order_version != ORDERS.get(frame.schema_id)):
            raise ValueError('骨架 schema / 坐标系 / 关节顺序不兼容')
        t = frame.time_s
        if t is None or not math.isfinite(t):
            raise ValueError('视频时间不可用，不能计时')
        status = 'NO_PERSON_DETECTED' if not frame.people else 'MULTI_PERSON'
        if len(frame.people) != 1:
            self.previous.clear()
            return Observation(t, None, status, {}, size=frame.size, reasons=[status.lower()])
        p = frame.people[0]
        names = SCHEMAS[frame.schema_id]
        if len(p.xy) != len(names) or len(p.conf) != len(names):
            raise ValueError('关键点数量不符合骨架契约')
        if p.track_key is None:
            return Observation(t, None, 'UNKNOWN', {}, size=frame.size, reasons=['identity_ambiguous'])
        track_context = (frame.context, frame.schema_id, p.track_key)
        if track_context != self.previous_track:
            self.previous.clear()
            self.previous_track = track_context
        w, h = frame.size
        if w <= 0 or h <= 0:
            raise ValueError('画面尺寸不可用')
        points, reasons = {}, {}
        for i, (point, confidence) in enumerate(zip(p.xy, p.conf)):
            hand_point = frame.schema_id == 'mediapipe-hand21-v1' or (frame.schema_id == 'mediapipe-wrist54-v1' and i >= 33)
            if len(point) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point):
                reasons[i] = 'nonfinite'
            elif not hand_point and (confidence is None or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)):
                reasons[i] = 'confidence_unavailable'
            elif not hand_point and confidence < self.conf_min:
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
                first_seen = previous[3] if previous and 0 < t-previous[0] <= self.max_gap else t
                self.previous[i] = (t, points[i], raw, first_seen)
                if hand_point and t-first_seen < .15:
                    points.pop(i, None)
                    reasons[i] = 'hand_temporal_warmup'
            if i in reasons:
                if reasons[i] != 'hand_temporal_warmup':
                    self.previous.pop(i, None)

        def measured(ids, fn):
            ids = [names.index(i) if isinstance(i, str) and i in names else -1 if isinstance(i, str) else i for i in ids]
            missing = [f'{i}:{reasons.get(i, "missing")}' for i in ids if i not in points]
            if missing:
                return Metric.missing(','.join(missing))
            return Metric.of(fn(*(points[i] for i in ids)))

        sh, el, wr, hi, kn, an = [self.side+'_'+n for n in ('shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle')]

        def flexion(a, b, c):
            angle = angle_deg(a, b, c)
            return None if angle is None else 180 - angle

        def tilt(ls, rs, lh, rh):
            dx, dy = (ls[0]+rs[0]-lh[0]-rh[0])/2, (ls[1]+rs[1]-lh[1]-rh[1])/2
            return None if math.hypot(dx, dy) < 1e-8 else math.degrees(math.atan2(abs(dx), abs(dy)))

        def hip_abduction(hip, other_hip, knee):
            # Pelvis-relative signed projection. Outward is positive; shoulders
            # do not participate, so trunk tilt cannot masquerade as a hip angle.
            outward = (hip[0]-other_hip[0], hip[1]-other_hip[1])
            thigh = (knee[0]-hip[0], knee[1]-hip[1])
            width, length = math.hypot(*outward), math.hypot(*thigh)
            if width < 1. or length < 1. or abs(outward[0]) < 1.:
                return None
            outward = tuple(v/width for v in outward)
            down = (-outward[1], outward[0])
            if down[1] < 0:
                down = tuple(-v for v in down)
            return math.degrees(math.atan2(
                sum(thigh[i]*outward[i] for i in (0, 1)),
                sum(thigh[i]*down[i] for i in (0, 1))))

        metrics = {
            'raise_deg': measured([hi, sh, el], angle_deg),
            'elbow_flexion_deg': measured([sh, el, wr], flexion),
            'knee_flexion_deg': measured([hi, kn, an], flexion),
            'hip_abduction_deg': measured([hi, 'right_hip' if self.side == 'left' else 'left_hip', kn], hip_abduction),
            'trunk_tilt_deg': measured(['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip'], tilt),
            'hip_y': measured([hi], lambda a: a[1]/h),
            'left_knee': measured(['left_hip', 'left_knee', 'left_ankle'], flexion),
            'right_knee': measured(['right_hip', 'right_knee', 'right_ankle'], flexion),
            'ankle_delta': measured(['left_ankle', 'right_ankle'], lambda a, b: (a[0]-b[0])/w),
            'shoulder_sagittal_raw_deg': measured([hi, sh, el], lambda a,b,c: signed_angle(
                (a[0]-b[0], a[1]-b[1]), (c[0]-b[0], c[1]-b[1]))),
            'hip_sagittal_raw_deg': measured([sh, hi, kn], lambda a,b,c: signed_angle(
                (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1]))),
        }
        if frame.schema_id in ('mediapipe33-v1', 'mediapipe-wrist54-v1'):
            def ankle(k,a,h,f):
                if math.dist(k,a) < 20 or math.dist(h,f) < 15:
                    return None
                return signed_angle((k[0]-a[0], k[1]-a[1]), (f[0]-h[0], f[1]-h[1]))
            metrics['ankle_raw_deg'] = measured([kn, an, self.side+'_heel', self.side+'_foot_index'],
                                                ankle)
        if frame.schema_id == 'mediapipe-wrist54-v1':
            def wrist(e, w, hw, m):
                if math.dist(w, hw) > .08*math.hypot(*frame.size) or math.dist(hw, m) < 20:
                    return None
                return signed_angle((w[0]-e[0], w[1]-e[1]), (m[0]-hw[0], m[1]-hw[1]))
            metrics['wrist_raw_deg'] = measured([el, wr, 'hand_wrist', 'hand_middle_mcp'], wrist)
        if frame.schema_id == 'mediapipe-hand21-v1':
            metrics = {}
            # The SDK exposes no per-landmark confidence. Geometric and temporal
            # checks are limited engineering guards, never an occlusion guarantee.
            def finger_angle(a,b,c):
                if min(math.dist(a,b), math.dist(b,c)) < 4:
                    return None
                return flexion(a,b,c)
            for finger in ('thumb', 'index', 'middle', 'ring', 'pinky'):
                joints = ('mcp', 'ip') if finger == 'thumb' else ('mcp', 'pip', 'dip')
                for joint in joints:
                    i = names.index(finger+'_'+joint)
                    before = 'wrist' if joint == 'mcp' and finger != 'thumb' else names[i-1]
                    metrics[f'{finger}_{joint}_flexion_deg'] = measured([before, names[i], names[i+1]], finger_angle)
            reasons[-2] = 'hand_point_confidence_not_provided'
        if self.exercise_id:
            spec = exercise_spec(self.exercise_id)
            if spec['joint'] in ('neck', 'trunk'):
                from .axial_geometry import head_roll, head_pitch, trunk_frontal, trunk_sagittal
                raw_contracts = {
                    'head_roll_raw_deg': (['left_shoulder', 'right_shoulder', 'left_eye', 'right_eye'], head_roll),
                    'head_pitch_raw_deg': ([hi, sh, self.side+'_ear', self.side+'_eye'], head_pitch),
                    'trunk_frontal_raw_deg': (['left_hip', 'right_hip', 'left_shoulder', 'right_shoulder'], trunk_frontal),
                    'trunk_sagittal_raw_deg': ([hi, sh], trunk_sagittal),
                }
                ids, function = raw_contracts[spec['raw_metric']]
                metrics[spec['raw_metric']] = measured(ids, function)
            if spec['directional_calibration']:
                raw = metrics.get(spec['raw_metric'], Metric.missing('missing_raw_metric'))
                baseline = self.joint_baseline
                if raw.valid and baseline.get('direction_sign') in (-1, 1) and isinstance(baseline.get('rest_value'), (int, float)):
                    metrics[spec['metric']] = Metric.of(baseline['direction_sign']*angle_delta(raw.value, baseline['rest_value']))
                else:
                    metrics[spec['metric']] = Metric.missing('direction_calibration_required' if raw.valid else raw.reason)
        raw_center = None
        local = None
        body_indices = [names.index(n) for n in ('left_shoulder', 'right_shoulder', 'left_hip', 'right_hip') if n in names]
        if len(body_indices) == 4 and all(i in points for i in body_indices):
            ls, rs, lh, rh = body_indices
            # Preserve unsmoothed global displacement separately from local shape.
            raw_center = tuple((p.xy[lh][j]+p.xy[rh][j])/2 for j in (0, 1))
            shoulder = tuple((p.xy[ls][j]+p.xy[rs][j])/2 for j in (0, 1))
            scale = math.dist(raw_center, shoulder)
            metrics['torso_scale_px'] = Metric.of(scale if scale > 1 else None)
            if scale > 1:
                local = [([(p.xy[i][j]-raw_center[j])/scale for j in (0, 1)]
                          if i in points else None) for i in range(len(names))]
        valid = any(m.valid for m in metrics.values())
        return Observation(t, p.track_key, 'VALID' if valid else 'UNKNOWN', metrics,
                           raw_center, p.bbox, local, frame.size, sorted(set(reasons.values())))
