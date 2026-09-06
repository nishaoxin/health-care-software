from __future__ import annotations

import csv
import html
from pathlib import Path

from .domain import SOURCES, CONTEXTS, SCENES, EXERCISES, dumps
from .storage import Storage

LABELS = {'COMPLETE': '完整完成', 'PARTIAL': '部分尝试', 'INTERRUPTED': '中断',
          'UNASSESSABLE': '无法评价', 'MET': '达到个人目标', 'NOT_MET': '未达个人目标',
          'NOT_SET': '未设置目标', 'VALID': '观察有效', 'PARTIAL_OBSERVABLE': '部分可观察',
          'UNUSABLE': '观察不足', 'elbow_flexion': '抬举时可见屈肘',
          'trunk_tilt': '可见躯干侧倾', 'lowering_tempo': '下降节奏超出已设范围',
          'target_not_reached': '未达人工站位角度目标'}


def fmt(value, decimals=1):
    if value is None:
        return '—'
    if isinstance(value, (int, float)):
        return f'{value:.{decimals}f}'
    return html.escape(str(value))


def render_report(s):
    summary = s.get('summary', {})
    ratio = summary.get('valid_ratio')
    source = SOURCES.get(s.get('source_kind'), '来源未记录')
    usage = CONTEXTS.get(s.get('usage_context'), '用途未记录')
    rows = []
    for rep in s.get('repetitions', []):
        issues = '、'.join(LABELS.get(i['rule_id'], i['rule_id']) for i in rep.get('issues', [])) or '无已确认问题证据'
        rows.append('<tr>'+''.join(f'<td>{fmt(v) if not isinstance(v, str) else html.escape(v)}</td>' for v in (
            rep['number'], LABELS.get(rep['completion_status'], rep['completion_status']),
            LABELS.get(rep['target_status'], rep['target_status']),
            rep.get('max_raise_projection_deg') if s.get('exercise_id') == 'shoulder_abduction' else rep.get('min_knee_flexion_projection_deg'),
            rep.get('duration_s'), LABELS.get(rep['observation_status'], ''), issues))+'</tr>')
    scene = s.get('scene_id')
    name = EXERCISES.get(s.get('exercise_id'), '康复任务') if scene == 'rehab' else SCENES.get(scene, '任务')
    detail = ''
    if scene == 'activity':
        labels = {'SEATED': '可见坐位', 'STANDING': '可见站位', 'WALKING': '可见步行', 'VISIBLE_MOVING': '可见移动'}
        detail = '<h2>有效可见时长</h2><table><tr><th>状态</th><th>有效秒数</th></tr>'
        detail += ''.join(f'<tr><td>{labels.get(k, k)}</td><td>{fmt(v)} 秒</td></tr>' for k, v in summary.get('totals', {}).items())+'</table>'
        detail += '<h2>活动任务</h2><table><tr><th>任务</th><th>状态</th><th>视觉核实</th><th>另行自报</th></tr>'
        for task in s.get('tasks', []):
            status = {'ACTIVE': '进行中', 'COMPLETED': '已完成', 'INTERRUPTED': '已中断'}.get(task['status'], '待确认')
            detail += f"<tr><td>{'站立' if task['kind'] == 'stand' else '步行'}</td><td>{status}</td><td>{fmt(task['visible_s'])} / {fmt(task['target_s'])} 秒</td><td>{'已自报' if task['self_reported'] else '无'}</td></tr>"
        detail += '</table>'
        if summary.get('demo_thresholds'):
            detail += '<p class="note">本次使用演示阈值，实际时间正常流逝。</p>'
    if scene in ('bedroom_demo', 'safety_demo'):
        detail += '<h2>观察记录</h2><p>'+html.escape(summary.get('message', '暂无有效观察'))+'</p>'
        if scene == 'bedroom_demo':
            detail += '<p>'+('已人工确认真实床区；仍为受控演示。' if summary.get('real_bed_confirmed') else '本次为模拟区域演示。')+'</p>'
        detail += '<h2>本次建立的事件</h2><ul>'
        detail += ''.join('<li>'+html.escape(e.get('message', '疑似事件'))+f"（触发时间 {fmt(e.get('event_emitted_time'))} 秒）</li>" for e in s.get('events', []))
        detail += '</ul><p>事件的最新处理状态请在应用的事件页面查看；报告保留当次建立记录。</p>'
    rep_section = f'''<h2>每次动作</h2><p class="muted">角度列：{'上臂相对躯干的二维投影抬举角' if s.get('exercise_id') == 'shoulder_abduction' else '膝屈曲二维投影角'}。— 表示无有效证据或不适用。</p>
    <table><tr><th>序号</th><th>完成情况</th><th>个人目标</th><th>角度 °</th><th>时长 s</th><th>观察情况</th><th>可见问题</th></tr>{''.join(rows) or '<tr><td colspan="7">没有已记录的动作重复。</td></tr>'}</table>''' if scene == 'rehab' else ''
    headline = f'''<table><tr><th>完整次数</th><th>部分尝试</th><th>中断 / 无法评价</th><th>有效观察</th></tr>
    <tr><td>{summary.get('completed', '—')}</td><td>{summary.get('partial', '—')}</td><td>{summary.get('invalid', '—')}</td><td>{fmt(None if ratio is None else ratio*100)} %</td></tr></table>''' if scene == 'rehab' else f'<p>有效观察比例：{fmt(None if ratio is None else ratio*100)} %</p>'
    body = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>任务报告</title>
    <style>body{{font-family:'Microsoft YaHei UI',sans-serif;color:#203c3d;background:#f5f8f6;max-width:1080px;margin:32px auto;padding:32px;line-height:1.7}}h1{{font-size:28px}}h2{{font-size:18px;margin-top:28px}}.tag{{color:#13776c}}.muted{{color:#627476}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:10px;border-bottom:1px solid #dbe7e1;text-align:left}}.note{{background:#e7f1eb;padding:16px;border-radius:10px}}code{{font-size:12px;word-break:break-all}}</style></head><body>
    <p class="tag">居家康复助手 · 本地任务报告</p><h1>{html.escape(name)}记录</h1>
    <p>{html.escape(source)} / {html.escape(usage)} · {fmt(s.get('start_utc'))}</p>
    <p class="note">仅报告所选场景的可见时段。二维投影测量；缺测不是动作差，个人目标不是通用医学标准。</p>
    {headline}
    <p>有效观察 {fmt(summary.get('valid_s'))} 秒 / 观察跨度 {fmt(summary.get('observed_span_s'))} 秒。结束原因：{fmt(s.get('stop_reason'))}。</p>
    {rep_section}
    {detail}
    <h2>测量条件</h2><p>测试侧：{fmt(s.get('side'))} · 机位版本：{fmt(s.get('profile_version'))} · 实际尺寸：{fmt(s.get('actual_capture', {}).get('size'))}</p>
    <p>时间基准：{fmt(s.get('time_basis'))} · 规则：{fmt(s.get('rule_version'))} · 预处理：{fmt(s.get('preprocess_version'))}</p>
    <p class="muted">模型 SHA256：<code>{fmt(s.get('model_manifest_id'))}</code></p>
    <p class="muted">记录 ID：<code>{fmt(s.get('id'))}</code>。只有相同参与者、动作、侧别、机位、来源及规则条件下才提供比较。</p>
    </body></html>'''
    return body


def export_session(snapshot, directory):
    s = Storage.authorized_snapshot(snapshot)
    out = Path(directory)
    if out.exists() and any(out.iterdir()):
        raise ValueError('导出目录须为空，避免残留此前授权的骨架或视频')
    out.mkdir(parents=True, exist_ok=True)
    metadata = {k: v for k, v in s.items() if k not in ('metrics', 'poses', 'events', 'repetitions')}
    # Public export uses a hashed input reference. Full device paths stay in local settings.
    metadata.pop('device_ref', None)
    if isinstance(metadata.get('config_snapshot'), dict):
        metadata['config_snapshot'].pop('device_ref', None)
    (out/'session.json').write_text(dumps(metadata, indent=2), encoding='utf-8')
    (out/'repetitions.json').write_text(dumps(s.get('repetitions', []), indent=2), encoding='utf-8')
    for key, filename in (('metrics', 'metrics.jsonl'), ('events', 'events.jsonl')):
        (out/filename).write_text(''.join(dumps(row)+'\n' for row in s.get(key, [])), encoding='utf-8')
    if s.get('config_snapshot', {}).get('poses_consent'):
        (out/'poses.jsonl').write_text(''.join(dumps(row)+'\n' for row in s.get('poses', [])), encoding='utf-8')
    (out/'report.html').write_text(render_report(s), encoding='utf-8')
    with (out/'repetitions.csv').open('w', newline='', encoding='utf-8-sig') as f:
        columns = ['number', 'completion_status', 'target_status', 'observation_status', 'duration_s', 'max_raise_projection_deg', 'min_knee_flexion_projection_deg']
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(s.get('repetitions', []))
    with (out/'annotations.csv').open('w', newline='', encoding='utf-8-sig') as f:
        csv.writer(f).writerow(['annotation_origin', 'annotator', 'annotation_version', 'participant_id', 'recording_id', 'evidence_time_s', 'human_label', 'notes'])
    return out
