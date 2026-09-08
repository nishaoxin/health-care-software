"""Exercise contracts shared by measurement, session gates and presentation.

Angles are camera-plane projections, never clinical ROM measurements. A chosen
view must still be confirmed by the participant; geometry cannot verify it.
"""
from __future__ import annotations

import copy


_SPECS = {
    'shoulder_abduction': {
        'label': '肩外展', 'joint': 'shoulder', 'view': 'frontal',
        'metric': 'raise_deg', 'metric_label': '肩外展二维投影抬举角',
        'required_metrics': ('raise_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '正面机位，测试侧髋、肩、肘入镜；在舒适范围向侧方抬臂，再回到垂臂姿势。',
        'ready_hint': '请自然垂臂，保持舒适准备姿势约 1 秒',
        'outbound_hint': '在舒适范围缓慢向侧方抬臂',
        'return_hint': '缓慢放下手臂，回到起始垂臂姿势',
    },
    'sit_to_stand': {
        'label': '居家坐站', 'joint': 'knee', 'view': 'sagittal',
        'metric': 'knee_flexion_deg', 'metric_label': '坐站膝屈曲二维投影角',
        'required_metrics': ('knee_flexion_deg', 'hip_y'),
        'rep_value_key': 'min_angle_deg', 'target_direction': 'decrease',
        'guide': '侧面机位，测试侧髋、膝、踝入镜；先确认舒适坐位和站位基线，达到站位记一次，回坐后才可再计。',
        'ready_hint': '请在已确认的座椅上保持舒适坐位约 1 秒',
        'outbound_hint': '按已确认计划缓慢起立',
        'return_hint': '缓慢回坐到已确认的座椅，回坐后才可开始下一次',
    },
    'shoulder_flexion': {
        'label': '肩前屈', 'joint': 'shoulder', 'view': 'sagittal',
        'metric': 'raise_deg', 'metric_label': '肩前屈二维投影抬举角',
        'required_metrics': ('raise_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '侧面机位，测试侧髋、肩、肘入镜；在舒适范围向前抬臂，再回到垂臂姿势。',
        'ready_hint': '请侧对镜头，自然垂臂并保持舒适准备姿势约 1 秒',
        'outbound_hint': '在舒适范围缓慢向前抬臂',
        'return_hint': '缓慢放下手臂，回到起始垂臂姿势',
    },
    'elbow_flexion': {
        'label': '肘屈伸', 'joint': 'elbow', 'view': 'sagittal',
        'metric': 'elbow_flexion_deg', 'metric_label': '肘屈曲二维投影角',
        'required_metrics': ('elbow_flexion_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '侧面机位，测试侧肩、肘、腕入镜；上臂保持舒适位置，缓慢屈肘，再回到起始伸肘姿势。',
        'ready_hint': '请舒适伸肘，保持起始姿势约 1 秒，不要强行伸直',
        'outbound_hint': '保持上臂舒适，缓慢屈肘',
        'return_hint': '缓慢伸肘，回到起始姿势',
    },
    'knee_extension': {
        'label': '坐位膝屈伸', 'joint': 'knee', 'view': 'sagittal',
        'metric': 'knee_flexion_deg', 'metric_label': '坐位膝屈曲二维投影角',
        'required_metrics': ('knee_flexion_deg',), 'rep_value_key': 'min_angle_deg',
        'target_direction': 'decrease',
        'guide': '侧面机位，坐稳并让测试侧髋、膝、踝入镜；保持坐位，缓慢伸膝再屈膝回位。伸展时屈曲投影角减小。',
        'ready_hint': '请坐稳，舒适屈膝并保持起始坐位约 1 秒',
        'outbound_hint': '保持坐稳，缓慢伸膝；屈曲角随伸展减小',
        'return_hint': '保持坐稳，缓慢屈膝回到起始坐位',
    },
    'hip_abduction': {
        'label': '髋外展', 'joint': 'hip', 'view': 'frontal',
        'metric': 'hip_abduction_deg', 'metric_label': '骨盆参考髋外展二维投影角',
        'required_metrics': ('hip_abduction_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '正面机位，双髋与测试侧膝入镜；按已确认的支撑与陪同安排，在舒适范围向侧方移腿并回位。仅记录骨盆参考二维投影，不是临床ROM。',
        'ready_hint': '请按已确认的支撑安排站稳，测试腿自然下垂并保持约 1 秒',
        'outbound_hint': '保持支撑稳定，在舒适范围缓慢向侧方移腿',
        'return_hint': '缓慢收回测试腿，回到起始站位',
    },
}

EXERCISE_IDS = tuple(_SPECS)


def exercise_spec(exercise_id: str) -> dict:
    """Return a detached spec; reject unknown actions instead of guessing."""
    if not isinstance(exercise_id, str) or exercise_id not in _SPECS:
        raise ValueError(f'未知康复动作：{exercise_id!r}')
    spec = copy.deepcopy(_SPECS[exercise_id])
    spec.update(measurement_type='2d_projection', clinical_rom=False,
                readiness_note='准备阈值仅为 v0.2 工程分期参数，不是正常值；不适用时应停止并调整已确认计划。')
    return spec
