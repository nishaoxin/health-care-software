"""Presentation policy only. It never admits observations or changes a rule."""
import math

from .exercise_instructions import exercise_instructions


class GuidancePolicy:
    adjustment_after_s = 1.5
    recovery_status_s = 1.

    def __init__(self):
        self.context = None
        self.invalid_since = None
        self.recovered_at = None
        self.adjustment = None
        self.candidate_adjustment = None
        self.candidate_since = None
        self.critical = None

    def render(self, data, plan, *, now):
        context = (data.get('context'), plan['exercise_id'], plan['side'], data['state'])
        if context != self.context:
            self.invalid_since = self.recovered_at = self.adjustment = self.critical = None
            self.candidate_adjustment = self.candidate_since = None
            self.context = context
        info = exercise_instructions(plan['exercise_id'])
        state = data['state']
        summary = data.get('summary') or {}
        stage = (summary.get('training') or {}).get('stage')
        valid = bool(data.get('current_measurement_valid'))
        result = dict(level='action', instruction=info['move'], status='', phase=None,
                      measurement_valid=valid, recovery=None)

        def display(level, instruction, status='', recovery=None):
            return dict(result, level=level, instruction=instruction, status=status, recovery=recovery)

        if state == 'SAVE_FAILED':
            return display('critical', '结果尚未保存，请重试保存。', recovery='save')
        if data.get('error') and not data.get('operation_error'):
            self.critical = str(data['error'])
        identity = data.get('identity_ambiguous') or data.get('observation_status') == 'MULTI_PERSON'
        if identity:
            return display('critical', '请只保留当前参与者，再重新确认。', recovery='confirm')
        if state in ('OFFLINE', 'ERROR') or self.critical:
            text = ('请只保留当前参与者，再重新预览确认。' if '归属' in (self.critical or '') else
                    '画面已中断，请重新预览。')
            return dict(display('critical', text, recovery='preview'), detail=self.critical or text)
        if data.get('error'):
            return display('adjust', str(data['error']).split('；')[0])
        if state == 'PRIVACY_PAUSED':
            return display('paused', '采集已暂停，准备好后重新预览。', recovery='preview')
        if state not in ('PREVIEW', 'ONLINE'):
            return display('paused', '请先打开预览，完成本次准备。')
        if state == 'ONLINE' and stage in ('PAUSED', 'RESTING', 'COMPLETE', 'FINISHED'):
            self.invalid_since = self.recovered_at = None
            self.adjustment = self.candidate_adjustment = self.candidate_since = None
            text = {'PAUSED': '训练已暂停，请先休息。', 'RESTING': '组间休息，准备好后继续。',
                    'COMPLETE': '本次训练已完成，请结束并保存。', 'FINISHED': '训练已结束。'}[stage]
            remaining = (summary.get('training') or {}).get('rest_remaining_s')
            if stage == 'RESTING' and isinstance(remaining, (int, float)) and math.isfinite(remaining) and remaining > 0:
                text = f'组间休息，还需 {math.ceil(remaining)} 秒。'
            return display('paused', text)
        if not valid:
            if self.invalid_since is None:
                self.invalid_since = now
            self.recovered_at = None
            if now-self.invalid_since + 1e-8 < self.adjustment_after_s:
                return display('status', info['move'], '正在重新识别，当前不计次')
            # A newly missing point must persist before replacing the single instruction.
            action = data.get('adjustment') or '请让测试部位清楚进入画面。'
            if self.adjustment is None:
                self.adjustment = action
            elif action == self.adjustment:
                self.candidate_adjustment = self.candidate_since = None
            elif action != self.candidate_adjustment:
                self.candidate_adjustment, self.candidate_since = action, now
            elif now-self.candidate_since >= .6:
                self.adjustment = action
                self.candidate_adjustment = self.candidate_since = None
            return display('adjust', self.adjustment)
        if self.invalid_since is not None:
            self.invalid_since = self.adjustment = None
            self.candidate_adjustment = self.candidate_since = None
            self.recovered_at = now
        if self.recovered_at is not None and now-self.recovered_at < self.recovery_status_s:
            result['status'] = '已重新识别'
        if data.get('auxiliary_missing'):
            result['status'] = '辅助指标：本项无法评价'
        if state == 'PREVIEW':
            return dict(result, instruction=data.get('preparation_instruction') or '保持舒适起点，完成本次准备。')
        phase = summary.get('phase')
        if plan.get('submode') == 'training' and stage not in ('ACTIVE', 'RECOVERY'):
            return display('paused', '请暂停动作，等待训练状态确认。')
        if summary.get('current_issues') and summary.get('message'):
            rule = summary['current_issues'][0].get('rule_id')
            action = {'trunk_tilt': '请保持躯干稳定。', 'elbow_flexion': '请按已确认的安排调整肘部姿势。'}.get(rule)
            return display('adjust', action or summary['message'].split('；')[0])
        timing = summary.get('movement_timing_live') or {}
        held, goal = timing.get('hold_elapsed_s'), timing.get('hold_min_s')
        if (plan.get('submode') == 'training' and isinstance(held, (float, int)) and isinstance(goal, (float, int))
                and held+1e-8 < goal and phase in ('RAISING', 'PEAK_OR_HOLD', 'RISING', 'STANDING_REACHED')):
            return dict(result, instruction=f'本段连续保持 {held:.1f} / {goal:g} 秒。')
        returning = stage == 'RECOVERY' or phase in ('LOWERING', 'STANDING_REACHED') or (
            plan.get('submode') == 'training' and (phase == 'PEAK_OR_HOLD' or summary.get('message', '').startswith('已观察到目标范围；')))
        if returning:
            phase = 'LOWERING'
        key = {'REST': 'start', 'WAIT_READY': 'start', 'SEATED_READY': 'start', 'RAISING': 'move',
               'RISING': 'move', 'PEAK_OR_HOLD': 'move', 'LOWERING': 'return'}.get(phase)
        return dict(result, instruction=info[key] if key else info['move'], phase=phase if key else None)
