"""Content inventory and acceptance-input checks, never an accuracy score."""
import csv
import hashlib
from pathlib import Path
import re

from .exercise_guides import guide_steps, GUIDE_ROOT
from .exercise_instructions import exercise_instructions
from .exercises import EXERCISE_IDS, exercise_spec, UNSUPPORTED_COVERAGE
from .regression import validate_groups


SAMPLE_COLUMNS = ('participant_id', 'recording_id', 'split', 'exercise_id', 'side', 'view',
                  'source_kind', 'usage_context', 'annotation_origin', 'annotator', 'annotation_version',
                  'consent_reference', 'license_reference', 'recording_sha256',
                  'recording_path', 'annotations_path', 'session_export_path')


def content_inventory(root=None):
    root = Path(root) if root else GUIDE_ROOT
    rows, errors = [], []
    for eid in EXERCISE_IDS:
        spec, info = exercise_spec(eid), exercise_instructions(eid)
        missing = [key for key in ('label', 'position', 'camera', 'start', 'move', 'return', 'count', 'boundary', 'measurement_label')
                   if not isinstance(info.get(key), str) or not info[key].strip()]
        if missing:
            errors.append(eid+': missing '+','.join(missing))
        if info.get('view_label') != ('正面拍摄' if spec['view'] == 'frontal' else '侧面拍摄'):
            errors.append(eid+': view mismatch')
        for side in ('left', 'right'):
            steps = guide_steps(eid, side, root=root)
            rows.append(dict(exercise_id=eid, exercise_label=spec['label'], joint=spec['joint'], side=side,
                             view=spec['view'], primary_metric=spec['metric'], measurement_contract=spec['measurement_contract'],
                             target_direction=spec['target_direction'], baseline_required=spec['baseline_required'],
                             content_fields_complete=not missing,
                             start=info['position']+' '+info['start'], move=info['move'], return_step=info['return'],
                             camera=info['camera'], count=info['count'], boundary=info['boundary'],
                             assets=[dict(step=s['key'], relative_path=f"{eid}/{side}/{s['key']}.png",
                                          status='PRESENT_NOT_CONTENT_REVIEWED' if s['image_path'].is_file() else 'MISSING') for s in steps],
                             expert_content_review='EVIDENCE_NOT_PROVIDED', human_accuracy='EVIDENCE_NOT_PROVIDED'))
    assets = [asset for row in rows for asset in row['assets']]
    return dict(schema_version=1, action_count=len(EXERCISE_IDS), body_part_count=len({r['joint'] for r in rows}),
                side_entries=len(rows), image_slots=len(assets), present_images=sum(a['status'] != 'MISSING' for a in assets),
                content_structure_errors=errors, unsupported_coverage=UNSUPPORTED_COVERAGE, rows=rows,
                evidence_scope='Registered text/measurement structure and local file presence only; no expert or human-accuracy sign-off.')


def check_sample_manifest(path, *, verify_files=False):
    path = Path(path)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        rows = [{key: value.strip() if isinstance(value, str) else '' for key, value in row.items() if key is not None}
                for row in reader]
    errors = []
    absent = sorted(set(SAMPLE_COLUMNS)-set(fields))
    if absent:
        errors.append('缺少列：'+','.join(absent))
    if not rows:
        errors.append('没有样本；空模板不是验收通过')
    try:
        groups = validate_groups(rows) if rows else {'rows': 0, 'participants': 0, 'recordings': 0}
    except ValueError:
        errors.append('人员 / 录制分组或独立人工标注来源不符合要求')
        groups = None
    seen = set()
    verified = 0
    for number, row in enumerate(rows, 2):
        prefix = f'第 {number} 行：'
        missing = [key for key in SAMPLE_COLUMNS if not row.get(key, '').strip()]
        if missing:
            errors.append(prefix+'未填写 '+','.join(missing))
        identity = row.get('recording_id')
        if identity in seen:
            errors.append(prefix+'录制编号重复；每段原始录制登记一次')
        seen.add(identity)
        eid = row.get('exercise_id')
        if eid not in EXERCISE_IDS or row.get('side') not in ('left', 'right'):
            errors.append(prefix+'动作或本人侧别无效')
        elif row.get('view') != exercise_spec(eid)['view']:
            errors.append(prefix+'拍摄方向与当前动作定义不一致')
        if row.get('source_kind') not in ('LIVE_CAMERA', 'REPLAY_FILE') or row.get('usage_context') not in ('SELF_USE', 'CONTROLLED_DEMO', 'TEST'):
            errors.append(prefix+'真实验收来源 / 情境无效；合成数据不能填写为真人证据')
        if not re.fullmatch(r'[0-9a-fA-F]{64}', row.get('recording_sha256', '')):
            errors.append(prefix+'录制 SHA256 格式无效')
        if verify_files:
            files = {}
            for key in ('recording_path', 'annotations_path', 'session_export_path'):
                raw = row.get(key, '')
                candidate = Path(raw) if raw else None
                candidate = (path.parent/candidate).resolve() if candidate and not candidate.is_absolute() else candidate
                if candidate is None or not candidate.is_file():
                    errors.append(prefix+key+' 文件不存在')
                else:
                    files[key] = candidate
            if 'recording_path' in files:
                with files['recording_path'].open('rb') as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual != row.get('recording_sha256', '').lower():
                    errors.append(prefix+'录制文件与 SHA256 不一致')
                elif len(files) == 3:
                    verified += 1
    return dict(rows=len(rows), group_counts=groups, errors=errors, ready=bool(rows) and not errors,
                check_level='files_and_recording_hash' if verify_files else 'metadata_only', verified_file_sets=verified,
                accuracy_validated=False, consent_authenticity_verified=False,
                note='只检查登记结构、分组，以及显式选择时的文件存在和录制哈希；不评判标签正确性、授权真实性或识别准确度。')
