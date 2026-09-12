"""Presentation-only preparation steps. Runtime remains the authority for readiness."""
from dataclasses import dataclass

from .exercises import exercise_spec
from .exercise_instructions import exercise_instructions

SCENE_LABELS = {'activity': '日常活动', 'bedroom_demo': '卧室观察演示', 'safety_demo': '安全提示演示'}
SCENE_ROIS = {'activity': (('chair', '座椅'),),
              'bedroom_demo': (('bed', '床'), ('bed_edge', '床边'), ('exit', '出口'), ('floor_watch', '地面关注区')),
              'safety_demo': (('floor_watch', '地面关注区'),)}


@dataclass(frozen=True)
class JourneyStep:
    key: str
    title: str
    instruction: str
    action: str
    number: int
    total: int


def preparation_steps(plan, *, dual=False, guided=False):
    spec = exercise_spec(plan['exercise_id'])
    info = exercise_instructions(plan['exercise_id'])
    steps = []
    if plan.get('submode') == 'training':
        steps += [('reference', '选择评估依据', '从身体档案选择本动作、本人测试侧的可用评估记录。', '选择评估记录'),
                  ('plan', '确认本次训练安排', '核对个人目标、组次、休息与支撑安排。没有确认前不会开始训练。', '确认训练计划')]
    camera = info['camera']
    if dual:
        camera = '两路均为本人：正面相机正对您，侧面相机对准测试侧。\n'+camera
        if plan['exercise_id'] in ('neck_flexion', 'neck_extension'):
            camera = '侧面画面：同侧眼、耳、肩、髋清楚入镜，不必拍到另一侧肩。\n正面画面：确认仍是本人。'
    steps += [('camera', '打开画面', '先核对顶部当前用户与摄像头。点击下方按钮打开预览，此时不会计次。', '打开预览'),
              ('framing', '调整拍摄位置', camera, '画面已摆好，继续')]
    if guided:
        # The guided path keeps the person moving when automatic measurement
        # cannot be prepared; it never fills in a baseline it did not record.
        steps += [('confirm', '核对并开始引导', info['start']+'\n引导计时只按固定节奏提示动作，本次不自动测角度或计次。', '已核对，确认准备'),
                  ('start', '准备完成', '点击开始后按提示活动。完成一次可以自己点“记一次”。', '开始引导计时'),
                  ('active', '按提示完成动作', info['move']+'\n'+info['return']+'\n完成一次点“记一次”；随时可以结束并保存。', '完成并保存'),
                  ('result', '查看本次结果', '记录已保存。本次说明哪些是自动观察到的、哪些是自己记录的。', '查看本次报告')]
        return steps
    if plan['exercise_id'] == 'sit_to_stand':
        steps += [('seated', '记录坐位起点', info['start']+' 点击记录，倒计时后保持坐位，等待记录完成。', '记录当前坐位'),
                  ('standing', '记录站位终点', '按已确认的支撑和陪同安排站起，站稳后点击记录。倒计时后保持站稳；不安全时取消。', '记录当前站位')]
    elif spec['baseline_required']:
        steps += [('rest', '记录动作起点', info['start']+' 点击记录，倒计时后保持姿势，等待记录完成。',
                   '记录侧抬臂起点' if plan['exercise_id'] == 'shoulder_adduction' else '记录舒适起点')]
    if spec['directional_calibration']:
        steps += [('direction', '记录活动方向', info['move']+' 只需小幅试动作，点击记录并在倒计时后保持；不是测试最大幅度。', '记录活动方向')]
    steps += [('confirm', '回到起点，人工核对', info['start']+'\n核对下方事项，确认无误后点击“已核对，确认准备”。', '已核对，确认准备'),
              ('start', '准备完成', '回到刚才的起点。点击开始后按大字提示动作；预览阶段不计入结果。',
               '开始训练' if plan.get('submode') == 'training' else '开始评估'),
              ('active', '按提示完成动作', info['move']+'\n'+info['return']+'\n'+info['count'], '完成并保存'),
              ('result', '查看本次结果', '报告已保存。先看结果解读，再查看详细数据；可从身体档案汇总多项评估。', '查看本次报告')]
    return steps


def current_step(plan, state, *, framed=False, confirmed=False, dual=False, saved=False, guided=False):
    steps = preparation_steps(plan, dual=dual, guided=guided)
    done = {'reference': (plan.get('assessment_reference') or {}).get('status') == 'ASSESSED',
            'plan': bool(plan.get('training_plan_confirmed')), 'camera': state == 'PREVIEW',
            'framing': framed, 'rest': (plan.get('joint_baseline') or {}).get('rest_value') is not None,
            'direction': (plan.get('joint_baseline') or {}).get('direction_sign') in (-1, 1),
            'seated': all((plan.get('calibration') or {}).get('seated_'+k) is not None for k in ('knee', 'hip_y')),
            'standing': all((plan.get('calibration') or {}).get('standing_'+k) is not None for k in ('knee', 'hip_y')),
            'confirm': confirmed, 'start': False}
    if state == 'ONLINE':
        key = 'active'
    elif saved and state not in ('PREVIEW', 'CONNECTING', 'SAVE_FAILED'):
        key = 'result'
    elif state == 'SAVE_FAILED':
        return JourneyStep('save_failed', '结果尚未保存', '本次数据仍保留。请重试保存；仍失败可先备份，暂不要关闭程序。', '重试保存', len(steps), len(steps))
    elif state == 'CONNECTING':
        return JourneyStep('connecting', '正在打开画面', '正在连接输入，请稍候。此时还未开始评估或训练。', '连接中…', next(i for i,s in enumerate(steps,1) if s[0]=='camera'), len(steps))
    elif confirmed and state == 'PREVIEW' and done['reference'] and done['plan']:
        key = 'start'
    elif confirmed and state == 'PREVIEW' and plan.get('submode') != 'training':
        key = 'start'
    else:
        key = next(s[0] for s in steps if not done.get(s[0], False))
    index = next(i for i,s in enumerate(steps) if s[0] == key)
    return JourneyStep(*steps[index], index+1, len(steps))


def scene_steps(scene):
    """The same short shape for the companion scenes, which had no step list."""
    label = SCENE_LABELS[scene]
    regions = '、'.join(title for _, title in SCENE_ROIS[scene])
    steps = [('camera', '打开画面', '先核对顶部当前用户与摄像头。点击下方按钮打开预览，此时还不会开始观察。', '打开预览'),
             ('regions', '圈定观察区域', f'在右侧“设置”里选择区域名称，再在画面上拖出矩形。本场景需要：{regions}。', '区域已圈好，继续')]
    if scene == 'activity':
        steps += [('permission', '确认活动安排', '勾选“已确认本次站立 / 步行活动许可”，并按本人情况选择任务与时间。', '已确认活动许可')]
    steps += [('confirm', '核对并确认', '核对画面中只有本人、区域位置正确。确认本身不会开始观察。', '已核对，确认准备'),
              ('start', '准备完成', f'点击开始后才记录{label}。其他场景不会被监测。', '开始观察'),
              ('active', '观察进行中', f'{label}正在记录。随时可以停止并保存本次记录。', '停止并保存'),
              ('result', '查看本次记录', '记录已保存，可在历史记录中查看；未关闭的事件不会自动消失。', '查看本次报告')]
    return steps


def current_scene_step(scene, state, *, rois=(), permission=False, confirmed=False, saved=False):
    steps = scene_steps(scene)
    done = {'camera': state == 'PREVIEW',
            'regions': all(name in set(rois) for name, _ in SCENE_ROIS[scene]),
            'permission': scene != 'activity' or bool(permission),
            'confirm': confirmed, 'start': False}
    if state == 'ONLINE':
        key = 'active'
    elif saved and state not in ('PREVIEW', 'CONNECTING', 'SAVE_FAILED'):
        key = 'result'
    elif state == 'SAVE_FAILED':
        return JourneyStep('save_failed', '记录尚未保存', '本次数据仍保留。请重试保存；仍失败可先备份，暂不要关闭程序。', '重试保存', len(steps), len(steps))
    elif state == 'CONNECTING':
        return JourneyStep('connecting', '正在打开画面', '正在连接输入，请稍候。此时还没有开始观察。', '连接中…', 1, len(steps))
    elif confirmed and state == 'PREVIEW':
        key = 'start'
    else:
        key = next(s[0] for s in steps if not done.get(s[0], False))
    index = next(i for i, s in enumerate(steps) if s[0] == key)
    return JourneyStep(*steps[index], index+1, len(steps))
