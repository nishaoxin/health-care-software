"""Explicit landmark semantics shared with the isolated worker (stdlib only)."""
COCO17 = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
          'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
          'left_wrist', 'right_wrist', 'left_hip', 'right_hip', 'left_knee',
          'right_knee', 'left_ankle', 'right_ankle')
POSE33 = ('nose', 'left_eye_inner', 'left_eye', 'left_eye_outer', 'right_eye_inner',
          'right_eye', 'right_eye_outer', 'left_ear', 'right_ear', 'mouth_left', 'mouth_right',
          'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist',
          'right_wrist', 'left_pinky', 'right_pinky', 'left_index', 'right_index',
          'left_thumb', 'right_thumb', 'left_hip', 'right_hip', 'left_knee', 'right_knee',
          'left_ankle', 'right_ankle', 'left_heel', 'right_heel', 'left_foot_index', 'right_foot_index')
HAND21 = ('wrist', 'thumb_cmc', 'thumb_mcp', 'thumb_ip', 'thumb_tip',
          'index_mcp', 'index_pip', 'index_dip', 'index_tip',
          'middle_mcp', 'middle_pip', 'middle_dip', 'middle_tip',
          'ring_mcp', 'ring_pip', 'ring_dip', 'ring_tip',
          'pinky_mcp', 'pinky_pip', 'pinky_dip', 'pinky_tip')
SCHEMAS = {'coco17-v1': COCO17, 'mediapipe33-v1': POSE33, 'mediapipe-hand21-v1': HAND21}
SCHEMAS['mediapipe-wrist54-v1'] = POSE33 + tuple('hand_'+n for n in HAND21)
ORDERS = {'coco17-v1': 'coco17-anatomical-lr-v1',
          'mediapipe33-v1': 'mediapipe33-anatomical-lr-v1',
          'mediapipe-hand21-v1': 'mediapipe-hand21-v1'}
ORDERS['mediapipe-wrist54-v1'] = 'mediapipe33-plus-selected-hand21-v1'
BACKEND_SCHEMAS = {'yolo': 'coco17-v1', 'mediapipe_pose': 'mediapipe33-v1',
                   'mediapipe_hands': 'mediapipe-hand21-v1'}
BACKEND_SCHEMAS['mediapipe_wrist'] = 'mediapipe-wrist54-v1'
MAX_FRAME_BYTES = 24 * 1024 * 1024
MAX_MESSAGE_BYTES = 256 * 1024


def joint_names(schema):
    if schema not in SCHEMAS:
        raise ValueError('不支持的骨架定义：'+str(schema))
    return SCHEMAS[schema]


def skeleton_edges(schema):
    names = joint_names(schema)
    if schema == 'mediapipe-hand21-v1':
        return tuple((a, a+1) for start in (1, 5, 9, 13, 17) for a in range(start, start+3)) + (
            (0, 1), (0, 5), (5, 9), (9, 13), (13, 17), (0, 17))
    links = [('left_shoulder', 'right_shoulder'), ('left_hip', 'right_hip')]
    for side in ('left', 'right'):
        for a, b in (('shoulder', 'elbow'), ('elbow', 'wrist'), ('shoulder', 'hip'), ('hip', 'knee'), ('knee', 'ankle')):
            links.append((side+'_'+a, side+'_'+b))
        if schema in ('mediapipe33-v1', 'mediapipe-wrist54-v1'):
            for a, b in (('ankle', 'heel'), ('heel', 'foot_index'), ('ankle', 'foot_index'),
                         ('wrist', 'index'), ('wrist', 'pinky'), ('wrist', 'thumb')):
                links.append((side+'_'+a, side+'_'+b))
    edges = tuple((names.index(a), names.index(b)) for a, b in links)
    if schema == 'mediapipe-wrist54-v1':
        edges += tuple((a+33, b+33) for a, b in skeleton_edges('mediapipe-hand21-v1'))
    return edges
