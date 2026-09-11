"""Presentation-only preparation steps. Runtime remains the authority for readiness."""
from dataclasses import dataclass

from .exercises import exercise_spec
from .exercise_instructions import exercise_instructions


@dataclass(frozen=True)
class JourneyStep:
    key: str
    title: str
    instruction: str
    action: str
    number: int
    total: int


def preparation_steps(plan, *, dual=False):
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
    if plan['exercise_id'] == 'sit_to_stand':
        steps += [('seated', '记录坐位起点', info['start']+' 保持坐位后点击记录。', '记录当前坐位'),
                  ('standing', '记录站位终点', '按已确认的支撑和陪同安排站起，站稳后点击记录。不安全时停止。', '记录当前站位')]
    elif spec['baseline_required']:
        steps += [('rest', '记录动作起点', info['start']+' 保持不动后点击记录。',
                   '记录侧抬臂起点' if plan['exercise_id'] == 'shoulder_adduction' else '记录舒适起点')]
    if spec['directional_calibration']:
        steps += [('direction', '记录活动方向', info['move']+' 只需小幅试动作，稍停后点击记录；不是测试最大幅度。', '记录活动方向')]
    steps += [('confirm', '回到起点，人工核对', info['start']+'\n核对下方事项并勾选，再点击“确认准备”。', '确认准备'),
              ('start', '准备完成', '回到刚才的起点。点击开始后按大字提示动作；预览阶段不计入结果。',
               '开始训练' if plan.get('submode') == 'training' else '开始评估'),
              ('active', '按提示完成动作', info['move']+'\n'+info['return']+'\n'+info['count'], '完成并保存'),
              ('result', '查看本次结果', '报告已保存。先看结果解读，再查看详细数据；可从身体档案汇总多项评估。', '查看本次报告')]
    return steps


def current_step(plan, state, *, framed=False, confirmed=False, dual=False, saved=False):
    steps = preparation_steps(plan, dual=dual)
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
