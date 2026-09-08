"""Plain-language presentation of existing measurement contracts.

These instructions neither prescribe a dose nor change measurement geometry.
Technical validity rules remain in exercises, geometry and the scene controller.
"""
from .exercises import exercise_spec


JOINT_LABELS = {
    'shoulder': '肩部', 'elbow': '肘部', 'wrist': '腕部', 'finger': '手指',
    'hip': '髋部', 'knee': '膝部', 'ankle': '踝部',
}

# Start, outbound and return are separate: extension from a flexed start is not
# equivalent to a flexion task whose return happens to contain extension.
_MOVEMENTS = {
    'shoulder_abduction': ('手臂自然下垂。', '向身体侧方缓慢抬臂。', '缓慢放下，回到起始位置。'),
    'shoulder_flexion': ('手臂自然下垂。', '向身体前方缓慢抬臂。', '缓慢放下，回到起始位置。'),
    'shoulder_extension': ('手臂停在舒适的起始位置。', '向身体后方缓慢移臂。', '缓慢回到起始位置。'),
    'shoulder_adduction': ('手臂侧抬到舒适位置，不要求达到水平。', '向身体方向缓慢收回手臂。', '向侧方抬回刚才记录的起点。'),
    'elbow_flexion': ('舒适伸肘，不要用力绷直。', '上臂保持原位，缓慢屈肘。', '缓慢伸肘，回到起点。'),
    'elbow_extension': ('保持舒适屈肘姿势。', '上臂保持原位，缓慢伸肘。', '缓慢屈肘，回到起点。'),
    'hip_abduction': ('按已确认的支撑安排站稳，测试腿自然下垂。', '向身体侧方缓慢移腿。', '缓慢收回，回到起始位置。'),
    'hip_adduction': ('按已确认的支撑安排站稳，测试腿停在舒适外展位置。', '向身体中线方向缓慢收腿。', '缓慢移回刚才记录的外展起点。'),
    'hip_flexion': ('按已确认的支撑安排保持稳定起始姿势。', '向身体前方缓慢移腿。', '缓慢回到起始位置。'),
    'hip_extension': ('按已确认的支撑安排保持稳定起始姿势。', '向身体后方缓慢移腿。', '缓慢回到起始位置。'),
    'knee_extension': ('坐稳，膝盖保持舒适弯曲。', '保持坐稳，缓慢伸膝。', '缓慢屈膝，回到起始坐位。'),
    'knee_flexion': ('在已确认的稳定坐位或支撑姿势中，记录舒适起点。', '保持身体稳定，缓慢屈膝。', '缓慢伸膝，回到起点。'),
    'sit_to_stand': ('坐在固定座椅上，按计划使用扶手或支撑。', '按已确认计划缓慢起立，到达已记录的站位。', '缓慢回坐。回坐后才可开始下一次。'),
    'wrist_flexion': ('前臂保持稳定，手腕处于舒适起点。', '向掌侧缓慢弯腕，手指姿势尽量不变。', '缓慢回到起点，避免整条手臂一起移动。'),
    'wrist_extension': ('前臂保持稳定，手腕处于舒适起点。', '向手背侧缓慢弯腕，手指姿势尽量不变。', '缓慢回到起点，避免整条手臂一起移动。'),
    'wrist_radial_deviation': ('前臂保持稳定，手腕处于舒适起点。', '向拇指侧缓慢偏腕。', '缓慢回到起点，手掌保持原来的朝向。'),
    'wrist_ulnar_deviation': ('前臂保持稳定，手腕处于舒适起点。', '向小指侧缓慢偏腕。', '缓慢回到起点，手掌保持原来的朝向。'),
    'ankle_dorsiflexion': ('坐稳，让测试脚处于舒适起点。', '向小腿方向缓慢抬脚尖。', '缓慢放回起点，不以抬腿代替踝部活动。'),
    'ankle_plantarflexion': ('坐稳，让测试脚处于舒适起点。', '向远离小腿的方向缓慢下压脚尖。', '缓慢回到起点，不以踮脚站立代替。'),
}


def exercise_instructions(exercise_id: str) -> dict:
    spec = exercise_spec(exercise_id)
    joint = spec['joint']
    camera = {
        'shoulder': '髋、肩、肘完整入镜；前屈和后伸从身体侧面拍摄。',
        'elbow': '从测试侧拍摄，肩、肘、腕完整入镜。',
        'hip': '正面动作让双髋和测试侧膝入镜；侧面动作让肩、髋、膝入镜。',
        'knee': '从测试侧拍摄，髋、膝、踝完整入镜。',
        'wrist': '肘、腕和整只测试手入镜，另一只手移出画面。',
        'ankle': '从测试侧拍摄，小腿、踝、足跟和足尖完整入镜。',
        'finger': '单只手近景；从所测手指侧面拍摄，让各关节展开在画面内。',
    }[joint]
    position = {
        'shoulder': '坐稳或按已确认的支撑安排站稳。',
        'elbow': '坐稳，让上臂保持舒适且稳定的位置。',
        'hip': '使用已确认的稳定姿势、支撑和陪同安排。',
        'knee': '使用稳定坐位或已确认的支撑姿势。',
        'wrist': '坐稳，前臂保持稳定，手腕留出活动空间。',
        'ankle': '稳定坐位；不要站立踮脚测试。',
        'finger': '手保持稳定，其余手指不要挡住所测关节。',
    }[joint]
    boundary = {
        'shoulder': '记录上臂相对躯干的二维变化，不分离肩胛与盂肱关节。',
        'elbow': '记录肩—肘—腕的二维屈曲角；不测前臂旋转或超伸。',
        'hip': '记录腿部相对身体参考线的二维变化；骨盆或躯干转动会影响结果。',
        'knee': '记录髋—膝—踝的二维屈曲角；不测超伸、肌力或支撑受力。',
        'wrist': '实验性二维观察。手部点没有逐点置信度；遮挡和离面运动可能无法自动发现。',
        'ankle': '实验性小腿—足部二维观察，不测后足内外翻或足弓。',
        'finger': '实验性二维观察。手部点没有逐点置信度；遮挡和离面运动可能无法自动发现。',
    }[joint]
    search_terms = f"{spec['label']} {JOINT_LABELS[joint]} {exercise_id}"
    if joint == 'finger':
        finger, articulation, _ = exercise_id.split('_')
        name = {'thumb': '拇指', 'index': '食指', 'middle': '中指', 'ring': '无名指', 'pinky': '小指'}[finger]
        location = {'mcp': '指根的掌指关节', 'pip': '中间的近端指间关节',
                    'dip': '靠近指尖的远端指间关节', 'ip': '拇指的指间关节'}[articulation]
        start = f'{name}保持舒适伸展，不要强行掰直。'
        move = f'缓慢弯曲{name}{location}，保持该关节两侧指段可见。'
        back = '缓慢伸回起始姿势，不要求所有手指同时握拳。'
        search_terms += ' '+articulation.upper()
        if articulation == 'mcp' and finger != 'thumb':
            boundary += ' 掌指角使用腕—掌指连线作为近端参考，不是骨性关节角。'
    else:
        start, move, back = _MOVEMENTS[exercise_id]
    if joint == 'shoulder':
        camera = ('正对镜头' if spec['view'] == 'frontal' else '测试侧朝向镜头')+'，髋、肩、肘完整入镜。'
    elif joint == 'hip':
        camera = '正对镜头，双髋与测试侧膝入镜。' if spec['view'] == 'frontal' else '测试侧朝向镜头，肩、髋、膝入镜。'
    elif joint == 'wrist':
        camera += ' 从手的侧缘拍摄。' if spec['view'] == 'sagittal' else ' 手掌或手背正对镜头。'
    return {
        'label': spec['label'], 'joint': joint, 'position': position,
        'camera': camera, 'start': start, 'move': move, 'return': back,
        'count': ('到达已记录的站位计 1 次；回坐后可再计数。' if exercise_id == 'sit_to_stand'
                  else '完成出程并返回起点计 1 次；次数与幅度目标分别记录。'),
        'boundary': boundary, 'measurement_label': spec['metric_label'],
        'search_terms': search_terms, 'clinical_rom': False,
        'view_label': '正面拍摄' if spec['view'] == 'frontal' else '侧面拍摄',
        'experimental': spec['experimental'],
        'calibration': ('记录坐位和站位' if exercise_id == 'sit_to_stand' else
                        '记录起点和方向' if spec['directional_calibration'] else
                        '记录舒适起点' if spec['baseline_required'] else '可记录舒适起点'),
    }
