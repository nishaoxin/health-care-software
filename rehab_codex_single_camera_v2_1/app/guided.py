"""Guided, time-prompted continuation when automatic measurement cannot carry a session.

A prompt is a local timer telling the person what to do now. It is never an
observation: this engine records observed valid time and an explicitly
approximate angle span, and it never derives repetitions, phases or targets.
Counting a repetition here is an explicit human report stored by the controller.
"""
from __future__ import annotations

import copy
import math

from .domain import clean_json
from .exercise_instructions import exercise_instructions
from .exercises import exercise_spec
from .rehab import _AngleEvidence

GUIDED_VERSION = 'guided-prompt-1'
MEASUREMENT_MODES = ('auto_observed', 'guided_timed')
CONTINUATION_MODES = ('auto', 'guided')
# Fixed, conservative prompt rhythm. Not a dose, not a clinical tempo.
PROMPT_STEPS = (('ready', 3., 'start', '回到起点'), ('outbound', 4., 'move', '做动作'),
                ('return', 4., 'return', '慢慢回位'))
CYCLE_S = sum(step[1] for step in PROMPT_STEPS)
GUIDED_NOTE = ('引导计时只按固定节奏提示动作，本次不自动判定角度或次数；'
               '完成情况由本人点击记录，报告会分别说明。')


def measurement_mode(continuation_mode):
    return 'guided_timed' if continuation_mode == 'guided' else 'auto_observed'


def prompt_plan():
    """The immutable prompt contract saved with a guided session."""
    return {'version': GUIDED_VERSION, 'origin': 'fixed_local_prompt_timer',
            'ready_s': PROMPT_STEPS[0][1], 'outbound_s': PROMPT_STEPS[1][1],
            'return_s': PROMPT_STEPS[2][1], 'cycle_s': CYCLE_S, 'note': GUIDED_NOTE}


def prompt_state(elapsed_s, exercise_id):
    """Presentation-only prompt for the elapsed time of this guided session."""
    if not isinstance(elapsed_s, (int, float)) or isinstance(elapsed_s, bool):
        return None
    if not math.isfinite(elapsed_s) or elapsed_s < 0:
        return None
    info = exercise_instructions(exercise_id)
    cycle = int(elapsed_s//CYCLE_S)+1
    offset = elapsed_s-(cycle-1)*CYCLE_S
    for key, duration, text_key, label in PROMPT_STEPS:
        if offset < duration-1e-9:
            return {'version': GUIDED_VERSION, 'key': key, 'cycle': cycle, 'label': label,
                    'remaining_s': max(0., duration-offset), 'instruction': info[text_key]}
        offset -= duration
    return None


class GuidedEngine:
    """Same engine surface as the measuring engines, with no inferred results."""

    def __init__(self, plan):
        self.plan = copy.deepcopy(plan)
        self.exercise = plan['exercise_id']
        self.spec = exercise_spec(self.exercise)
        self.primary_metric = self.spec['metric']
        self.phase = 'GUIDED'
        self.repetitions, self.intervals, self.tasks, self.events = [], [], [], []
        self.evidence = _AngleEvidence()
        self.latest_metrics = {}
        self.valid_s = 0.
        self.first_t = self.last_t = None
        self.previous_valid = False
        self.prompted_cycles = 0
        self.self_reported = 0
        self.paused = False
        self.paused_s = 0.
        self.pause_count = 0
        self.message = '按提示在舒适范围活动；本次不自动计次。'

    @property
    def completed(self):
        # Guided sessions never infer a repetition from the picture.
        return 0

    def note_prompt_cycle(self, cycle):
        if isinstance(cycle, int) and cycle > self.prompted_cycles:
            self.prompted_cycles = cycle

    def note_self_report(self, total):
        if isinstance(total, int) and total >= 0:
            self.self_reported = total

    def set_paused(self, paused):
        """Pausing the prompt also stops crediting observed time."""
        paused = bool(paused)
        if paused == self.paused:
            return False
        self.paused = paused
        self.previous_valid = False
        self.evidence.break_continuity()
        if paused:
            self.pause_count += 1
            self.message = '提示已暂停，准备好后点“继续提示”。'
        else:
            self.message = '按提示在舒适范围活动；本次不自动计次。'
        return True

    def process(self, o):
        t = o.time_s
        if self.phase == 'FINISHED' or t is None or not math.isfinite(t):
            return
        if self.last_t is not None and t <= self.last_t:
            return
        if self.first_t is None:
            self.first_t = t
        dt = 0. if self.last_t is None else t-self.last_t
        gap = dt > self.plan['max_gap_s']
        self.last_t = t
        self.latest_metrics = clean_json(o.metrics)
        if self.paused:
            if not gap:
                self.paused_s += dt
            self.previous_valid = False
            self.evidence.break_continuity()
            return
        value = o.value(self.primary_metric)
        usable = (o.status == 'VALID' and o.track_key is not None and value is not None
                  and isinstance(value, (int, float)) and math.isfinite(value))
        if not usable:
            self.evidence.break_continuity()
            self.previous_valid = False
            self.message = '暂时看不清，按提示继续活动；本次不自动测量。'
            return
        if self.previous_valid and not gap:
            self.valid_s += dt
        self.previous_valid = True
        self.evidence.add(value)
        self.message = '按提示在舒适范围活动；本次不自动计次。'

    def finish(self, reason):
        self.phase = 'FINISHED'

    def approximate_range(self):
        """Observed span across valid frames, without movement phase analysis."""
        span = self.evidence.motion_range()
        if span is None:
            return None
        return dict(span, approximate=True, origin='valid_frames_without_phase_analysis',
                    note='按有效帧统计的角度范围，没有按动作出程 / 回程分期，不能作为一次完整动作的幅度。')

    def summary(self):
        duration = (self.last_t-self.first_t) if self.first_t is not None else 0.
        approximate = self.approximate_range()
        return {'exercise_id': self.exercise, 'joint': self.spec['joint'],
                'measurement_mode': 'guided_timed', 'guided_prompt': prompt_plan(),
                'prompted_cycles': self.prompted_cycles,
                'self_reported_reps': self.self_reported,
                'prompt_paused': self.paused, 'paused_s': self.paused_s, 'pause_count': self.pause_count,
                'movement_timing_version': None, 'movement_timing_live': None, 'last_movement_timing': None,
                'primary_metric': self.primary_metric, 'primary_metric_label': self.spec['metric_label'],
                'motion_range': None, 'motion_range_valid': False,
                'motion_range_reason': 'guided_timed_no_phase_analysis',
                'approximate_range': approximate,
                'valid_sample_count': self.evidence.sample_count,
                'measurement_type': '2d_projection', 'clinical_rom': False,
                'readiness_note': self.spec['readiness_note'],
                'target_direction': self.spec['target_direction'],
                'completed': 0, 'target_met': 0, 'partial': 0, 'invalid': 0,
                'valid_s': self.valid_s, 'observed_span_s': duration,
                'valid_ratio': self.valid_s/duration if duration > 0 else None,
                'phase': self.phase, 'message': self.message, 'metrics': self.latest_metrics,
                'current_issues': [], 'plan_completed': False, 'completed_sets': 0}
