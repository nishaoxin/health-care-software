"""Text + explicitly side-specific image slots; no generated demonstration assets."""
from pathlib import Path

from .exercise_instructions import exercise_instructions
from .settings import ROOT

GUIDE_ROOT = ROOT / 'assets' / 'exercise-guides'
STEPS = (('start', '准备姿势'), ('move', '开始动作'), ('return', '缓慢回位'))


def guide_steps(exercise_id, side, *, root=None):
    info = exercise_instructions(exercise_id)  # Validate IDs before constructing paths.
    if side not in ('left', 'right'):
        raise ValueError('动作图解需要明确本人左侧或右侧')
    base = Path(root) if root is not None else GUIDE_ROOT
    label = '本人左侧' if side == 'left' else '本人右侧'
    return tuple({
        'key': key, 'title': title, 'text': (info['position'] + ' ' if key == 'start' else '') + info[key],
        'alt': f"{info['label']} · {label} · {title} · {info['view_label']}",
        'image_path': base / exercise_id / side / (key + '.png'),
    } for key, title in STEPS)
