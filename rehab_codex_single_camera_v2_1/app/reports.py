from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
from pathlib import Path
import re

from .assessment import (COMPARISON_NOTE, EXERCISE_IDS, STATUS_LABELS, anonymous_participant,
                         finite_number, session_conditions, session_motion_range, session_value)
from .domain import SOURCES, CONTEXTS, SCENES, clean_json, digest, dumps
from .exercises import exercise_spec
from .storage import Storage


LABELS = {'COMPLETE': '完整完成', 'PARTIAL': '部分尝试', 'INTERRUPTED': '中断',
          'UNASSESSABLE': '无法评价', 'MET': '达到个人目标', 'NOT_MET': '未达个人目标',
          'NOT_SET': '未设置目标', 'VALID': '观察有效', 'PARTIAL_OBSERVABLE': '部分可观察',
          'UNUSABLE': '观察不足', 'elbow_flexion': '抬举时可见屈肘',
          'trunk_tilt': '可见躯干侧倾', 'lowering_tempo': '下降节奏超出已设范围',
          'target_not_reached': '未达人工设置的角度目标'}
SIDES = {'left': '左侧', 'right': '右侧'}
MODES = {'assessment': '身体评估', 'training': '康复训练'}
SESSION_STATUSES = {'FINISHED': '已结束', 'COMPLETED': '已结束', 'INTERRUPTED': '已中断', 'RUNNING': '进行中'}
STYLE = """body{font-family:'Microsoft YaHei UI',sans-serif;color:#203c3d;background:#f5f8f6;
max-width:1200px;margin:24px auto;padding:24px;line-height:1.7}h1{font-size:26px}h2{font-size:18px}
.tag{color:#13776c}.muted{color:#627476}table{border-collapse:collapse;width:100%;background:white}
td,th{padding:8px;border:1px solid #dbe7e1;text-align:left;vertical-align:top}
.note{background:#e7f1eb;padding:14px}code{font-size:12px;word-break:break-all}"""


def fmt(value, decimals=1):
    if value is None:
        return '—'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = finite_number(value)
        return '—' if number is None else f'{number:.{decimals}f}'
    return html.escape(str(value), quote=True)


def _percent(value):
    number = finite_number(value)
    return fmt(number*100) + ' %' if number is not None and 0 <= number <= 1 else '—'


def _document(title, body, style=STYLE):
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{fmt(title)}</title>'
            f'<style>{style}</style></head><body>{body}</body></html>')


def _public_ref(value):
    if value is None or value == '':
        return None
    if isinstance(value, str) and re.fullmatch(r'source-[0-9a-f]{16}', value):
        return value
    return 'source-' + digest(value)[:16]


def _conditions_html(conditions):
    c = conditions or {}
    view = {'frontal': '正面', 'sagittal': '侧面', 'front': '正面'}.get(c.get('view'), c.get('view'))
    return (f'机位：{fmt(view)} · 机位版本：{fmt(c.get("profile_version"))}'
            f' · 放置版本：{fmt(c.get("placement_revision"), 0)} · 实际尺寸：{fmt(c.get("actual_size"))}<br>'
            f'模型：<code>{fmt(c.get("model_manifest_id"))}</code> · 骨架：{fmt(c.get("schema_id"))}<br>'
            f'规则：{fmt(c.get("rule_version"))} · 预处理：{fmt(c.get("preprocess_version"))}'
            f' · 时间基准：{fmt(c.get("time_basis"))}<br>来源引用：{fmt(_public_ref(c.get("source_ref")))}')


def _range_html(value):
    if not isinstance(value, dict):
        return '—（未评估或无有效测量）'
    return (f'{fmt(value.get("min_deg"))}° 至 {fmt(value.get("max_deg"))}°'
            f'<br>观察幅度 {fmt(value.get("range_deg"))}°')


def _issues_html(issues):
    rows = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        rule = issue.get('rule_id')
        label = LABELS.get(rule, rule or '未记录问题名称')
        evidence = '已记录证据' if issue.get('evidence_valid') is True else '证据未确认'
        trace = f' · 第 {fmt(issue.get("repetition_number"), 0)} 次' if 'repetition_number' in issue else ''
        rows.append(f'{fmt(label)}（{evidence}{trace}）')
    return '<br>'.join(rows) or '无已确认问题证据'


def _short_utc(value):
    if not isinstance(value, str):
        return '—'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return '—'


def _compact_body_profile(profile):
    rows = []
    for item in profile.get('items') or []:
        motion = item.get('motion_range') if item.get('status') == 'ASSESSED' else None
        angles = f'{fmt(motion.get("min_deg"))}–{fmt(motion.get("max_deg"))}°' if motion else '—'
        completed = fmt(item.get('completed'), 0)
        status = fmt(STATUS_LABELS.get(item.get('status'), '未记录'))
        if item.get('session_status') == 'INTERRUPTED':
            status += '<br>中断结束'
        cells = (f'{fmt(item.get("exercise_label"))} · {fmt(SIDES.get(item.get("side"), item.get("side")))}'+
                 ('<br>实验性观察' if item.get('experimental') else ''),
                 status,
                 angles, f'{_percent(item.get("valid_ratio"))} / {completed} 次',
                 _short_utc(item.get('end_utc')))
        rows.append('<tr>' + ''.join(f'<td>{cell}</td>' for cell in cells) + '</tr>')
    body = (f'<p>匿名参与者：{fmt(profile.get("participant_id") or profile.get("participant_label"))}'
            f'　已评估 {fmt(profile.get("assessed_count"), 0)} / {fmt(profile.get("total_items"), 0)} 项<br>'
            f'{fmt(SOURCES.get(profile.get("source_kind"), "来源未记录"))} / '
            f'{fmt(CONTEXTS.get(profile.get("usage_context"), "用途未记录"))}</p>'
            '<table cellspacing="0" cellpadding="5"><tr><th width="23%">动作 / 侧别</th>'
            '<th width="12%">状态</th><th width="20%">投影角度范围</th>'
            '<th width="21%">有效观察 / 完整次数</th><th width="24%">最近评估（UTC）</th></tr>'
            + ''.join(rows) + '</table>'
            '<p class="muted">— 表示未测量；本次不可用时不沿用旧结果。完整证据请打开所选评估报告。</p>'+
            _coverage_html(profile))
    style = ("body{font-family:'Microsoft YaHei UI',sans-serif;font-size:12px;color:#203c3d;"
             'margin:4px;padding:4px;line-height:1.3}p{margin:4px 0 8px}.muted{color:#627476}'
             'table{border-collapse:collapse;width:100%;background:white}'
             'td,th{padding:5px;border-bottom:1px solid #dbe7e1;text-align:left;vertical-align:middle}')
    return _document('身体评估汇总', body, style)


def render_body_profile(profile, compact=False):
    """Self-contained HTML using the table/text subset supported by QTextBrowser."""
    if compact:
        return _compact_body_profile(profile)
    rows = []
    for item in profile.get('items') or []:
        status = STATUS_LABELS.get(item.get('status'), '状态未记录')
        motion_range = item.get('motion_range') if item.get('status') == 'ASSESSED' else None
        origin = '由旧记录连续有效样本三点中位数派生' if item.get('motion_range_source') == 'metrics' else '原会话汇总'
        trace = (f'记录 ID：<code>{fmt(item.get("session_id"))}</code><br>'
                 f'开始：{fmt(item.get("start_utc"))}<br>结束：{fmt(item.get("end_utc"))}<br>'
                 f'会话状态：{fmt(SESSION_STATUSES.get(item.get("session_status"), item.get("session_status")))}<br>'
                 f'结束原因：{fmt(item.get("stop_reason"))}')
        counts = (f'完整 {fmt(item.get("completed"), 0)} / 部分 {fmt(item.get("partial"), 0)}'
                  f' / 无效 {fmt(item.get("invalid"), 0)}')
        rows.append('<tr>' + ''.join(f'<td>{value}</td>' for value in (
            f'{fmt(item.get("exercise_label"))}<br>{fmt(SIDES.get(item.get("side"), item.get("side")))}'
            f'<br><span class="muted">{fmt(item.get("primary_metric_label"))}</span>',
            f'{status}<br>{fmt(item.get("reason")) if item.get("reason") else ""}',
            _range_html(motion_range) + (f'<br><span class="muted">{origin}</span>' if motion_range else ''),
            f'{_percent(item.get("valid_ratio"))}<br>{counts}',
            _issues_html(item.get('issues')), trace, _conditions_html(item.get('conditions')))) + '</tr>')
    body = (f'<p class="tag">居家康复助手 · 个人身体评估汇总</p><h1>身体评估汇总</h1>'
            f'<p>匿名参与者：{fmt(profile.get("participant_id") or profile.get("participant_label"))}</p>'
            f'<p>{fmt(SOURCES.get(profile.get("source_kind"), "来源未记录"))} / '
            f'{fmt(CONTEXTS.get(profile.get("usage_context"), "用途未记录"))} · '
            f'已评估 {fmt(profile.get("assessed_count"), 0)} / {fmt(profile.get("total_items"), 0)} 项</p>'
            '<p class="note">每项展示最近一次已结束评估；本次不可用时不沿用旧成功结果。'
            '— 表示缺失，不代表 0。仅描述本次观察，不能推断疾病、肌力或真实负重，不能作为自动训练处方。</p>'
            '<table><tr><th>动作与侧别</th><th>评估状态</th><th>二维投影角度</th>'
            '<th>有效观察 / 次数</th><th>可见问题</th><th>原始评估记录</th><th>测量条件</th></tr>'
            + ''.join(rows) + '</table>'
            f'<p class="muted">{fmt(COMPARISON_NOTE)}</p>'+_coverage_html(profile))
    return _document('身体评估汇总', body)


def _coverage_html(profile):
    rows = ''.join(f'<p><b>{fmt(item.get("label"))}</b><br>{fmt(item.get("reason"))}</p>'
                   for item in profile.get('unsupported_coverage') or [])
    return ('<h2>当前测量边界</h2><p>不要求完成全部项目；按已确认的适用范围选择。腕、踝和手指为实验性二维观察，'
            '需清楚可见且运动处于成像平面。标记“已评估”仅表示保存了观察值，不表示临床验证通过。</p>'
            '<h3>暂不输出关节角及原因</h3>'+rows) if rows else ''


def _assessment_reference(session):
    if 'assessment_reference' in session:
        return session['assessment_reference']
    return ((session.get('config_snapshot') or {}).get('plan') or {}).get('assessment_reference')


def _training_html(session):
    if session_value(session, 'submode') != 'training':
        return ''
    reference = _assessment_reference(session)
    title = '<h2>训练所用的评估参考</h2>'
    if not isinstance(reference, dict) or not reference:
        return title + '<p>未记录评估参考（旧报告可无此字段）。训练目标以当次人工确认的计划为准。</p>'
    status = reference.get('status')
    same_scope = all(reference.get(key) == session_value(session, key) for key in
                     ('participant_id', 'exercise_id', 'side'))
    same_scope = same_scope and all(reference.get(key) == session.get(key) for key in ('source_kind', 'usage_context'))
    usable = status == 'ASSESSED' and same_scope
    explanation = '原评估的观察结果；训练目标仍需人工确认。' if usable else '引用不可用于当前训练：未评估、本次不可用或参与者/动作/侧别/来源情境不一致。'
    return (title + f'<p>{fmt(STATUS_LABELS.get(status, "状态未记录"))} · {fmt(explanation)}</p>'
            f'<p>匿名参与者：{fmt(reference.get("participant_id"))} · '
            f'{fmt(reference.get("exercise_label") or reference.get("exercise_id"))} / '
            f'{fmt(SIDES.get(reference.get("side"), reference.get("side")))} · '
            f'{fmt(SOURCES.get(reference.get("source_kind"), "来源未记录"))} / '
            f'{fmt(CONTEXTS.get(reference.get("usage_context"), "用途未记录"))}</p>'
            f'<p>评估记录 ID：<code>{fmt(reference.get("session_id"))}</code><br>'
            f'评估开始：{fmt(reference.get("start_utc"))} · 评估结束：{fmt(reference.get("end_utc"))}<br>'
            f'原评估状态：{fmt(SESSION_STATUSES.get(reference.get("session_status"), reference.get("session_status")))} · '
            f'结束原因：{fmt(reference.get("stop_reason"))}<br>'
            f'参考投影角度：{_range_html(reference.get("motion_range") if usable else None)} · '
            f'有效观察：{_percent(reference.get("valid_ratio"))}</p>'
            f'<p>{_conditions_html(reference.get("conditions"))}</p>'
            f'<p class="muted">{fmt(COMPARISON_NOTE)}本报告不计算跨条件改善幅度。</p>')


def _rep_angle(rep, spec):
    key = spec.get('rep_value_key')
    if key in rep:
        return rep[key]
    legacy = {'raise_deg': 'max_raise_projection_deg', 'knee_flexion_deg': 'min_knee_flexion_projection_deg'}
    return rep.get(legacy.get(spec.get('metric')))


def render_report(s):
    summary = s.get('summary') or {}
    source = SOURCES.get(s.get('source_kind'), '来源未记录')
    usage = CONTEXTS.get(s.get('usage_context'), '用途未记录')
    scene = s.get('scene_id')
    exercise_id = session_value(s, 'exercise_id')
    spec = exercise_spec(exercise_id) if exercise_id in EXERCISE_IDS else {}
    name = spec.get('label', '康复任务') if scene == 'rehab' else SCENES.get(scene, '任务')
    detail = ''
    if scene == 'rehab':
        rows = []
        for rep in s.get('repetitions') or []:
            values = (fmt(rep.get('number'), 0), fmt(LABELS.get(rep.get('completion_status'), rep.get('completion_status'))),
                      fmt(LABELS.get(rep.get('target_status'), rep.get('target_status'))), fmt(_rep_angle(rep, spec)),
                      fmt(rep.get('min_angle_deg')), fmt(rep.get('peak_angle_deg')), fmt(rep.get('range_deg')),
                      fmt(rep.get('duration_s')), fmt(LABELS.get(rep.get('observation_status'), rep.get('observation_status'))),
                      _issues_html(rep.get('issues')))
            rows.append('<tr>' + ''.join(f'<td>{value}</td>' for value in values) + '</tr>')
        motion_range, evidence_source = session_motion_range(s)
        evidence_note = '由旧记录连续有效样本三点中位数派生' if evidence_source == 'metrics' else '原会话汇总'
        metric_label = summary.get('primary_metric_label') or spec.get('metric_label', '二维投影角')
        detail += (f'<h2>本次投影角度</h2><p>{fmt(metric_label)}：{_range_html(motion_range)}'
                   + (f'（{evidence_note}）' if motion_range else '') + '</p>'
                   '<h2>每次动作</h2><p class="muted">代表角度按动作定义取抬举峰值或最小屈曲角；'
                   '最小、最大及幅度列保留本次可观察范围。— 表示无有效证据或不适用。</p>'
                   '<table><tr><th>序号</th><th>完成情况</th><th>个人目标</th><th>代表角度 °</th>'
                   '<th>最小 °</th><th>最大 °</th><th>幅度 °</th><th>时长 s</th><th>观察情况</th><th>可见问题</th></tr>'
                   + (''.join(rows) or '<tr><td colspan="10">没有已记录的动作重复。</td></tr>') + '</table>')
        detail += _training_html(s)
        if s.get('measurement_limitations'):
            detail += '<h2>本动作的测量限制</h2><p>'+fmt(s['measurement_limitations'])+'</p>'
        baseline = ((s.get('config_snapshot') or {}).get('plan') or {}).get('joint_baseline') or {}
        if baseline:
            detail += ('<h2>舒适起点记录</h2><p>起点原始投影角 '+fmt(baseline.get('rest_value'))+
                       '°；记录时间 '+fmt(baseline.get('recorded_at'))+'。'+
                       ('本动作报告相对该起点、按人工确认方向的角度变化；不是临床绝对ROM。' if spec.get('directional_calibration') else
                        '起点仅用于动作分期，不是正常值或训练目标。')+'</p>')
    elif scene == 'activity':
        labels = {'SEATED': '可见坐位', 'STANDING': '可见站位', 'WALKING': '可见步行', 'VISIBLE_MOVING': '可见移动'}
        detail = '<h2>有效可见时长</h2><table><tr><th>状态</th><th>有效秒数</th></tr>'
        detail += ''.join(f'<tr><td>{fmt(labels.get(k, k))}</td><td>{fmt(v)} 秒</td></tr>' for k, v in (summary.get('totals') or {}).items()) + '</table>'
        detail += '<h2>活动任务</h2><table><tr><th>任务</th><th>状态</th><th>视觉核实</th><th>另行自报</th></tr>'
        for task in s.get('tasks') or []:
            status = {'ACTIVE': '进行中', 'COMPLETED': '已完成', 'INTERRUPTED': '已中断'}.get(task.get('status'), '待确认')
            detail += (f'<tr><td>{fmt({"stand": "站立", "walk": "步行"}.get(task.get("kind"), task.get("kind")))}</td>'
                       f'<td>{status}</td><td>{fmt(task.get("visible_s"))} / {fmt(task.get("target_s"))} 秒</td>'
                       f'<td>{"已自报" if task.get("self_reported") else "无"}</td></tr>')
        detail += '</table>'
        if summary.get('demo_thresholds'):
            detail += '<p class="note">本次使用演示阈值，实际时间正常流逝。</p>'
    elif scene in ('bedroom_demo', 'safety_demo'):
        detail += '<h2>观察记录</h2><p>' + fmt(summary.get('message', '暂无有效观察')) + '</p>'
        if scene == 'bedroom_demo':
            detail += '<p>' + ('已人工确认真实床区；仍为受控演示。' if summary.get('real_bed_confirmed') else '本次为模拟区域演示。') + '</p>'
        detail += '<h2>本次建立的事件</h2><ul>'
        detail += ''.join('<li>' + fmt(e.get('message', '疑似事件')) + f'（触发时间 {fmt(e.get("event_emitted_time"))} 秒）</li>' for e in s.get('events') or [])
        detail += '</ul><p>事件的最新处理状态请在应用的事件页面查看；报告保留当次建立记录。</p>'
    headline = (f'<table><tr><th>完整次数</th><th>部分尝试</th><th>中断 / 无法评价</th><th>有效观察</th></tr>'
                f'<tr><td>{fmt(summary.get("completed"), 0)}</td><td>{fmt(summary.get("partial"), 0)}</td>'
                f'<td>{fmt(summary.get("invalid"), 0)}</td><td>{_percent(summary.get("valid_ratio"))}</td></tr></table>') if scene == 'rehab' else f'<p>有效观察比例：{_percent(summary.get("valid_ratio"))}</p>'
    body = (f'<p class="tag">居家康复助手 · 本地任务报告</p><h1>{fmt(name)}记录</h1>'
            f'<p>模式：{fmt(MODES.get(session_value(s, "submode"), "模式未记录"))} · '
            f'匿名参与者：{fmt(session_value(s, "participant_id"))}</p>'
            f'<p>{fmt(source)} / {fmt(usage)} · 开始 {fmt(s.get("start_utc"))} · 结束 {fmt(s.get("end_utc"))}</p>'
            '<p class="note">仅报告所选场景的可见时段。二维投影测量；缺测不是动作差，个人目标不是通用医学标准。'
            '不据此推断疾病、肌力或真实负重。</p>'
            + headline + f'<p>有效观察 {fmt(summary.get("valid_s"))} 秒 / 观察跨度 {fmt(summary.get("observed_span_s"))} 秒。'
            f'会话状态：{fmt(SESSION_STATUSES.get(s.get("status"), s.get("status")))} · '
            f'结束原因：{fmt(s.get("stop_reason"))}。</p>' + detail
            + f'<h2>测量条件</h2><p>测试侧：{fmt(SIDES.get(session_value(s, "side"), session_value(s, "side")))}</p>'
            f'<p>{_conditions_html(session_conditions(s))}</p>'
            f'<p class="muted">记录 ID：<code>{fmt(s.get("id"))}</code>。{fmt(COMPARISON_NOTE)}</p>')
    return _document('任务报告', body)


# Nested plans/calibrations/references can carry the same sensitive metadata as
# the top-level session. Redact recursively, not just the device_ref at the root.
PRIVATE_KEYS = {'device_ref', 'device_path', 'path', 'file_path', 'video_path', 'model_path',
                'participant_name', 'person_name', 'patient_name', 'full_name', 'display_name',
                'name', 'operator', 'annotator', 'email', 'phone', 'address', 'serial_number'}


def _export_snapshot(snapshot):
    def redact(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if str(key).lower() in PRIVATE_KEYS:
                    continue
                if key == 'participant_id':
                    result[key] = anonymous_participant(item)
                elif key == 'participant_label':
                    result[key] = anonymous_participant(value.get('participant_id'))
                elif key == 'source_ref':
                    result[key] = _public_ref(item)
                else:
                    result[key] = redact(item)
            return result
        if isinstance(value, (list, tuple)):
            return [redact(item) for item in value]
        return clean_json(value)
    return redact(snapshot)


def _empty_export_directory(directory):
    out = Path(directory)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('导出目录须为空，避免残留此前授权的骨架或视频')
    out.mkdir(parents=True, exist_ok=True)
    return out


def _csv_value(value):
    # Spreadsheet formula injection applies to untrusted labels as well as HTML.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return clean_json(value)


def export_session(snapshot, directory):
    s = _export_snapshot(Storage.authorized_snapshot(snapshot))
    out = _empty_export_directory(directory)
    metadata = {k: v for k, v in s.items() if k not in ('metrics', 'poses', 'events', 'repetitions')}
    (out/'session.json').write_text(dumps(metadata, indent=2), encoding='utf-8')
    (out/'repetitions.json').write_text(dumps(s.get('repetitions') or [], indent=2), encoding='utf-8')
    for key, filename in (('metrics', 'metrics.jsonl'), ('events', 'events.jsonl')):
        (out/filename).write_text(''.join(dumps(row)+'\n' for row in s.get(key) or []), encoding='utf-8')
    if (s.get('config_snapshot') or {}).get('poses_consent'):
        (out/'poses.jsonl').write_text(''.join(dumps(row)+'\n' for row in s.get('poses') or []), encoding='utf-8')
    (out/'report.html').write_text(render_report(s), encoding='utf-8')
    with (out/'repetitions.csv').open('w', newline='', encoding='utf-8-sig') as f:
        columns = ['number', 'completion_status', 'target_status', 'observation_status', 'duration_s',
                   'peak_angle_deg', 'min_angle_deg', 'range_deg', 'max_raise_projection_deg',
                   'min_knee_flexion_projection_deg', 'rise_time_s', 'lowering_time_s',
                   'exercise_id', 'side', 'submode', 'participant_id', 'source_kind', 'usage_context',
                   'primary_metric', 'primary_metric_label', 'assessment_session_id', 'issues']
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        exercise_id = session_value(s, 'exercise_id')
        spec = exercise_spec(exercise_id) if exercise_id in EXERCISE_IDS else {}
        reference = _assessment_reference(s) or {}
        for rep in s.get('repetitions') or []:
            row = dict(rep)
            row.update({key: session_value(s, key) for key in ('exercise_id', 'side', 'submode', 'participant_id')})
            row.update({key: s.get(key) for key in ('source_kind', 'usage_context')})
            row.update(primary_metric=(s.get('summary') or {}).get('primary_metric') or spec.get('metric'),
                       primary_metric_label=(s.get('summary') or {}).get('primary_metric_label') or spec.get('metric_label'),
                       assessment_session_id=reference.get('session_id') if isinstance(reference, dict) else None,
                       issues=dumps(rep.get('issues') or []))
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
    with (out/'annotations.csv').open('w', newline='', encoding='utf-8-sig') as f:
        csv.writer(f).writerow(['annotation_origin', 'annotator', 'annotation_version', 'participant_id', 'recording_id', 'evidence_time_s', 'human_label', 'notes'])
    return out


def export_body_profile(profile, folder) -> dict:
    """Export anonymised summary and evidence IDs; return absolute html/json paths."""
    exported = _export_snapshot(profile)
    out = _empty_export_directory(folder).resolve()
    html_path, json_path = out/'body_profile.html', out/'body_profile.json'
    html_path.write_text(render_body_profile(exported), encoding='utf-8')
    json_path.write_text(dumps(exported, indent=2), encoding='utf-8')
    return {'html': str(html_path), 'json': str(json_path)}
