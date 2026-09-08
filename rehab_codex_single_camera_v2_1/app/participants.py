"""Manually entered local information, separate from visual observations."""
from datetime import date
from uuid import uuid4


SIDES = {'unknown': '未填写', 'left': '左侧', 'right': '右侧', 'both': '双侧', 'other': '其他 / 不分侧'}
REPORTERS = {'self': '本人', 'family': '家属 / 照护者', 'professional': '专业人员'}
SUPPORT = {'unknown': '未填写', 'independent': '通常独立完成',
           'assisted': '通常需要陪同', 'to_confirm': '需要进一步确认'}
TEXT_FIELDS = {'reason': '康复原因', 'restrictions': '已知活动限制', 'goals': '生活目标',
               'aids': '辅助器具', 'notes': '补充说明'}


def legacy_participant(participant_id):
    return {'schema_version': 1, 'participant_id': participant_id,
            'display_name': '本机用户' if participant_id == 'participant-local' else participant_id,
            'birth_year': None, 'affected_side': 'unknown', 'reported_by': 'self', 'support': 'unknown',
            **{key: '' for key in TEXT_FIELDS}, 'revision': 0, 'record_origin': 'not_recorded',
            'created_utc': None, 'updated_utc': None}


def new_participant():
    result = legacy_participant('person-'+uuid4().hex)
    result['display_name'] = ''
    return result


def validate_participant(value):
    if not isinstance(value, dict):
        raise ValueError('档案内容无效')
    result = {'schema_version': 1}
    for key, label, limit in [('participant_id', '用户编号', 80), ('display_name', '称呼', 60),
                              *((key, label, 1000) for key, label in TEXT_FIELDS.items())]:
        text = value.get(key, '')
        if not isinstance(text, str) or len(text.strip()) > limit:
            raise ValueError(f'{label}最多 {limit} 个字')
        text = text.strip()
        if key in ('participant_id', 'display_name') and (not text or any(ord(c) < 32 for c in text)):
            raise ValueError(f'请填写单行{label}')
        result[key] = text
    year = value.get('birth_year')
    if year is not None and (type(year) is not int or not 1900 <= year <= date.today().year):
        raise ValueError('出生年份应为 1900 年至今年，或留空')
    result['birth_year'] = year
    for key, options, default in [('affected_side', SIDES, 'unknown'), ('reported_by', REPORTERS, 'self'),
                                  ('support', SUPPORT, 'unknown')]:
        selected = value.get(key, default)
        if not isinstance(selected, str) or selected not in options:
            raise ValueError('请选择有效的信息来源、侧别和陪同情况')
        result[key] = selected
    return result


def participant_summary(profile):
    if not profile or not profile.get('revision'):
        return '尚未填写个人信息。评估记录仍按当前用户保存。'
    values = [f"{profile['birth_year']} 年出生" if profile.get('birth_year') else None,
              SIDES.get(profile.get('affected_side')) if profile.get('affected_side') != 'unknown' else None,
              SUPPORT.get(profile.get('support')) if profile.get('support') != 'unknown' else None]
    return ' · '.join(v for v in values if v) or '个人信息已保存'
