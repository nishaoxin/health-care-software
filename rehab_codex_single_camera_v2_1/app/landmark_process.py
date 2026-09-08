"""Model-only subprocess. Consumes RGB bytes on stdin; NEVER opens a camera.

Runs in .venv-landmarks so OpenCV/NumPy dependencies do not alter the main app.
One request: JSON line (dimensions/context) followed by exactly byte_count bytes.
One response: bounded JSON line. IMAGE mode deliberately has no hidden history
across participants, pause/resume or replay seeks. Identity is not inferred here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from .landmark_schemas import BACKEND_SCHEMAS, MAX_FRAME_BYTES, MAX_MESSAGE_BYTES, ORDERS


def _finite(value):
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _reply(value):
    data = json.dumps(value, ensure_ascii=True, allow_nan=False).encode('utf-8') + b'\n'
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError('Model response too large')
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _read_exact(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        data = stream.read(size-len(chunks))
        if not data:
            raise EOFError('Incomplete frame')
        chunks.extend(data)
    return bytes(chunks)


def encode_result(result, backend, width, height):
    is_hand = backend == 'mediapipe_hands'
    groups = result.hand_landmarks if is_hand else result.pose_landmarks
    output = []
    for index, points in enumerate(groups):
        expected = 21 if is_hand else 33
        if len(points) != expected:
            raise ValueError('Unexpected landmark schema')
        xy = [[_finite(p.x*width), _finite(p.y*height)] for p in points]
        attributes = {'confidence_kind': 'not_provided' if is_hand else 'min_presence_visibility'}
        if is_hand:
            # Handedness score is NOT landmark confidence. Preserve unknowns.
            confidence = [None] * expected
            categories = result.handedness[index] if index < len(result.handedness) else []
            category = categories[0] if categories else None
            attributes.update(model_handedness=getattr(category, 'category_name', None),
                              handedness_score=_finite(getattr(category, 'score', None)),
                              side_assignment='manual_confirmation_required')
        else:
            confidence = []
            for point in points:
                visibility, presence = _finite(point.visibility), _finite(point.presence)
                confidence.append(min(visibility, presence) if visibility is not None and presence is not None else None)
        output.append({'xy': xy, 'conf': confidence, 'attributes': attributes})
    return output


def merge_wrist(pose_result, hand_result, width, height, side):
    bodies = encode_result(pose_result, 'mediapipe_pose', width, height)
    hands = encode_result(hand_result, 'mediapipe_hands', width, height)
    for body in bodies:
        hand = hands[0] if len(bodies) == len(hands) == 1 else None
        selected, other = (15, 16) if side == 'left' else (16, 15)
        matched = False
        if hand and all(v is not None for i in (selected, other) for v in body['xy'][i]):
            a, b, wrist = body['xy'][selected], body['xy'][other], hand['xy'][0]
            if all(v is not None for v in wrist) and (body['conf'][selected] or 0) >= .5:
                distance = math.dist(a, wrist)
                matched = distance < .08*math.hypot(width, height) and distance+10 < math.dist(b, wrist)
        body['xy'] += hand['xy'] if matched else [[None, None] for _ in range(21)]
        body['conf'] += [None]*21
        body['attributes'].update(confidence_kind='pose_visibility_and_hand_unknown',
                                  selected_side=side, hand_matched=matched,
                                  hand_confidence_kind='not_provided')
    return bodies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=('mediapipe_pose', 'mediapipe_hands', 'mediapipe_wrist'), required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--hand-model', type=Path)
    parser.add_argument('--hand-sha256')
    parser.add_argument('--side', choices=('left', 'right'), default='left')
    args = parser.parse_args()
    actual_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    if actual_hash != args.sha256:
        raise ValueError('Model SHA256 mismatch')
    import numpy as np
    import mediapipe as mp
    base = mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve()))
    vision = mp.tasks.vision
    extra_task = None
    if args.backend in ('mediapipe_pose', 'mediapipe_wrist'):
        options = vision.PoseLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.IMAGE,
                    num_poses=2, min_pose_detection_confidence=.6, min_pose_presence_confidence=.6)
        task = vision.PoseLandmarker.create_from_options(options)
        if args.backend == 'mediapipe_wrist':
            if hashlib.sha256(args.hand_model.read_bytes()).hexdigest() != args.hand_sha256:
                raise ValueError('Hand model SHA256 mismatch')
            extra_task = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(args.hand_model.resolve())),
                running_mode=vision.RunningMode.IMAGE, num_hands=2,
                min_hand_detection_confidence=.6, min_hand_presence_confidence=.6))
    else:
        options = vision.HandLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.IMAGE,
                    num_hands=2, min_hand_detection_confidence=.6, min_hand_presence_confidence=.6)
        task = vision.HandLandmarker.create_from_options(options)
    schema = BACKEND_SCHEMAS[args.backend]
    _reply({'kind': 'ready', 'backend': args.backend, 'schema_id': schema,
            'keypoint_order_version': ORDERS[schema], 'model_sha256': actual_hash,
            'hand_model_sha256': args.hand_sha256, 'selected_side': args.side,
            'runtime_version': mp.__version__})
    try:
        while True:
            header = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES+1)
            if not header:
                break
            if len(header) > MAX_MESSAGE_BYTES or not header.endswith(b'\n'):
                raise ValueError('Invalid request header')
            request = json.loads(header)
            if request.get('kind') == 'close':
                break
            width, height, count = request['width'], request['height'], request['byte_count']
            if (any(type(v) is not int for v in (width, height, count)) or
                    width <= 0 or height <= 0 or count != width*height*3 or not 0 < count <= MAX_FRAME_BYTES):
                raise ValueError('Invalid frame dimensions')
            raw = _read_exact(sys.stdin.buffer, count)
            rgb = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3).copy()
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = task.detect(image)
            targets = (merge_wrist(result, extra_task.detect(image), width, height, args.side) if extra_task else
                       encode_result(result, args.backend, width, height))
            _reply({'kind': 'result', 'seq': request['seq'], 'epoch': request['epoch'],
                    'targets': targets})
    finally:
        task.close()
        if extra_task:
            extra_task.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        _reply({'kind': 'error', 'error_type': type(exc).__name__, 'message': str(exc)})
        raise SystemExit(1)
