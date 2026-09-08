from __future__ import annotations

import copy
import sys
from pathlib import Path
from .exercises import exercise_spec

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def _overrides(filename, section, key):
    path = ROOT/'configs'/filename
    if not path.is_file():
        return {}
    import yaml
    return yaml.safe_load(path.read_text(encoding='utf-8')).get(section, {}).get(key, {})


def load_settings():
    import yaml
    path = ROOT / 'configs' / 'app.yaml'
    fallback = ROOT / 'configs' / 'app.example.yaml'
    return yaml.safe_load((path if path.exists() else fallback).read_text(encoding='utf-8'))


def default_plan(exercise='shoulder_abduction'):
    spec = exercise_spec(exercise)
    plan = copy.deepcopy({
        'exercise_id': exercise, 'side': 'left', 'submode': 'assessment',
        'target_reps': 5, 'target_sets': 1, 'target_angle_deg': None,
        'allowed_elbow_flexion_deg': None, 'allowed_trunk_tilt_deg': None,
        'lowering_tempo_min_s': None, 'lowering_tempo_max_s': None,
        'use_of_hands': 'not_recorded', 'needs_companion': False, 'sound_enabled': False,
        'stop_instruction': '如有疼痛、头晕或不适，立即停止并寻求适当帮助。',
        'view': spec['view'],
        'ready_s': 1.0, 'dwell_s': .18, 'max_gap_s': .5,
        'rest_deg': {'knee_extension': 75., 'hip_abduction': 10.}.get(exercise, 20.),
        'raising_delta_deg': 10., 'issue_hold_s': .5, 'feedback_cooldown_s': 8.,
        'calibration': {}, 'joint_baseline': {}, 'participant_id': 'participant-local',
    })
    plan.update(_overrides('exercises.yaml', 'exercises', exercise))
    return plan


def default_setup(scene='rehab', exercise='shoulder_abduction'):
    setup = {'scene_id': scene, 'plan': default_plan(exercise), 'rois': {},
            'view': exercise_spec(exercise)['view'],
            'mirror': False, 'placement_revision': 1, 'profile_id': '',
            'participant_confirmed': False, 'setup_confirmed_at': None,
            'activity_permission': False, 'real_bed': False, 'needs_assistance': False,
            'night_confirmed': False, 'demo_thresholds': False,
            'sedentary_trigger_s': 2700., 'stand_target_s': 60., 'walk_target_s': 120.,
            'low_hold_s': 2., 'poses_consent': False, 'raw_video_consent': False,
            'reference_frame_consent': False}
    setup.update(_overrides('scenes.yaml', 'scenes', scene))
    return setup
