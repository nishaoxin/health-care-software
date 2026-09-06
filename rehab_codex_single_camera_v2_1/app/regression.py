def validate_groups(rows):
    """Split participants/recordings before windows; never use predictions as truth."""
    participants, recordings = {}, {}
    for row in rows:
        group = row.get('split')
        if group not in ('development', 'acceptance'):
            raise ValueError('每段记录必须明确开发组或最终验收组')
        if row.get('annotation_origin') != 'human':
            raise ValueError('标准答案必须来自独立人工标注')
        for key, registry in (('participant_id', participants), ('recording_id', recordings)):
            identity = row.get(key)
            if not identity:
                raise ValueError(f'缺少 {key}')
            if identity in registry and registry[identity] != group:
                raise ValueError(f'{key} 跨组泄漏：{identity}')
            registry[identity] = group
    return {'participants': len(participants), 'recordings': len(recordings), 'rows': len(rows)}
