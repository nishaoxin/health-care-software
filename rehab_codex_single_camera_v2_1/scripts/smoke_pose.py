"""Single-source pose preview check with explicit camera selection.

Not a completed rehabilitation application. No rep counting, falls, reports,
mode switching or hardware hotplug validation. Never automatically open camera 0.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
from camera_tools import choose_device, saved_device_reference


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--live', action='store_true', help='Enumerate and interactively select one camera.')
    group.add_argument('--camera-ref', type=Path, help='Local single-device reference previously saved by this script.')
    group.add_argument('--video', type=Path, help='Local file; always labelled REPLAY TEST.')
    p.add_argument('--backend', choices=['dshow', 'msmf', 'v4l2', 'avfoundation'], default='dshow')
    p.add_argument('--save-camera-ref', type=Path)
    p.add_argument('--weights', type=Path, default=Path('assets/models/yolo11n-pose.pt'))
    p.add_argument('--device', default='auto', help='auto, cpu, or CUDA index such as 0; unrelated to camera index.')
    p.add_argument('--request-width', type=int, default=1280)
    p.add_argument('--request-height', type=int, default=720)
    p.add_argument('--request-fps', type=float, default=30)
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--max-frames', type=int, default=120)
    p.add_argument('--display', action='store_true')
    args = p.parse_args()
    if not args.weights.is_file():
        p.error('Trusted local pose weights are missing; this script will not download them.')
    if args.video and not args.video.is_file():
        p.error('Local video not found.')
    if args.camera_ref and not args.camera_ref.is_file():
        p.error('Camera reference file not found.')
    if args.video and args.save_camera_ref:
        p.error('A replay file cannot be saved as a camera reference.')
    if min(args.request_width, args.request_height, args.max_frames) < 1 or args.imgsz < 32:
        p.error('Invalid size or frame count.')
    if not math.isfinite(args.request_fps) or args.request_fps <= 0:
        p.error('Requested FPS must be positive and finite.')
    return args


def main() -> int:
    args = parse_args()
    try:
        import cv2
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        print(f'Missing dependency: {exc.name}', file=sys.stderr)
        return 2
    device = ('0' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device != 'cpu' and not torch.cuda.is_available():
        print('CUDA requested but unavailable. Use --device cpu or repair the target environment.', file=sys.stderr)
        return 2
    cap = None
    processed = 0
    error = False
    track_times = []
    actual_shape = None
    driver_reported_fps = None
    key = 'REPLAY_FILE' if args.video else 'LIVE_CAMERA'
    start = time.monotonic()
    try:
        if args.video:
            cap = cv2.VideoCapture(str(args.video.resolve()))
        else:
            selected = choose_device(args.backend, args.camera_ref)
            print(f'Opening selected device: {selected.name}; backend={selected.backend}; index={selected.index}')
            cap = cv2.VideoCapture(selected.index, selected.backend)
        if not cap.isOpened():
            raise RuntimeError('Source did not open. No automatic device/backend fallback is permitted.')
        if not args.video:
            requested_results = {}
            for name, flag, value in [('width', cv2.CAP_PROP_FRAME_WIDTH, args.request_width),
                                      ('height', cv2.CAP_PROP_FRAME_HEIGHT, args.request_height),
                                      ('fps', cv2.CAP_PROP_FPS, args.request_fps)]:
                requested_results[name] = bool(cap.set(flag, value))
            print(json.dumps({'property_set_return_values': requested_results,
                              'note': 'Successful set() is not proof of actual negotiated output.'}))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        driver_reported_fps = fps if math.isfinite(fps) and fps > 0 else None
        model = YOLO(str(args.weights.resolve()))
        if getattr(model, 'task', None) != 'pose':
            raise RuntimeError('The supplied model is not a pose model.')
        digest = hashlib.sha256()
        with args.weights.open('rb') as f:
            for chunk in iter(lambda: f.read(1024*1024), b''):
                digest.update(chunk)
        print(json.dumps({'source_kind': key, 'purpose': 'pose_preview_integration_only',
                          'compute_device': device, 'weights_sha256': digest.hexdigest()}))
        while processed < args.max_frames:
            ok, frame = cap.read()
            received_ns = time.monotonic_ns()
            if not ok or frame is None:
                if args.video:
                    break
                raise RuntimeError('Camera read failed; not a normal or no-person result.')
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                raise RuntimeError('Expected a BGR camera frame. Select the RGB stream rather than an IR/depth input.')
            actual_shape = [int(frame.shape[1]), int(frame.shape[0])]
            t0 = time.perf_counter()
            result = model.track(frame, persist=True, tracker='bytetrack.yaml', conf=.35,
                                 imgsz=args.imgsz, device=device, verbose=False)[0]
            track_times.append(1000*(time.perf_counter()-t0))
            processed += 1
            if processed == 1 and args.save_camera_ref:
                args.save_camera_ref.parent.mkdir(parents=True, exist_ok=True)
                args.save_camera_ref.write_text(json.dumps(saved_device_reference(selected), ensure_ascii=False, indent=2), encoding='utf-8')
                print('Saved device candidate only; not a validated scene/camera placement profile.')
            if processed == 1 or processed % 30 == 0:
                print(json.dumps({'frame': processed, 'frame_shape': actual_shape,
                                  'person_count': 0 if result.boxes is None else len(result.boxes),
                                  'received_monotonic_ns': received_ns, 'source_kind': key}))
            if args.display:
                canvas = result.plot()
                label = 'REPLAY TEST - PREVIEW ONLY' if args.video else 'LIVE CAMERA - PREVIEW ONLY'
                cv2.putText(canvas, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2)
                cv2.imshow('Selected source / pose check - q to stop', canvas)
                if cv2.waitKey(1) & 0xff == ord('q'):
                    break
    except KeyboardInterrupt:
        print('Stopped by user.', file=sys.stderr)
    except Exception as exc:
        print(f'Check failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        error = True
    finally:
        if cap is not None:
            cap.release()
        if args.display:
            cv2.destroyAllWindows()
        elapsed = max(time.monotonic()-start, 1e-9)
        usable = track_times[5:] or track_times
        print(json.dumps({'frames': processed, 'actual_frame_shape': actual_shape,
                          'driver_reported_fps': driver_reported_fps,
                          'processed_fps_including_startup': round(processed/elapsed, 3),
                          'median_track_ms': round(statistics.median(usable), 3) if usable else None,
                          'note': 'Not pure capture FPS, end-to-end latency, hotplug, angle accuracy or product validation.'}))
    return 0 if processed and not error else 5


if __name__ == '__main__':
    raise SystemExit(main())
