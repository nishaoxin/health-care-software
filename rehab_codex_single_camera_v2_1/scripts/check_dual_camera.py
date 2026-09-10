"""Explicit two-camera capture check. Does not infer poses or save camera images."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from statistics import median
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.camera_manager import CameraManager
from app.domain import Context, digest, utc_now
from app.dual_camera import make_dual_source, validate_pair


def check_pair(camera, refs, seconds, options, run_number):
    source = make_dual_source(refs, 'frontal', 'TEST')
    context = Context(run_number, 'rehab', source['ref'], 'LIVE_CAMERA', 'TEST')
    result = dict(run=run_number, camera_open_attempted=False, completed=False, released=False,
                  source_kind='LIVE_CAMERA', usage_context='TEST', requested_capture=options,
                  streams={}, received_pairs=0, error=None)
    received_times, deltas, worker = [], [], None
    try:
        result['camera_open_attempted'] = True
        camera.open_pair(refs, 'frontal', context, options)
        worker = camera.worker
        deadline = time.monotonic()+15
        sample_until = None
        while time.monotonic() < (sample_until if sample_until is not None else deadline):
            for status in worker.read_status():
                if status['status'] == 'ERROR':
                    result['error'] = dict(category='input_error', view=status.get('view'))
                    return result
                if status['status'] == 'OPENED':
                    result['backend_reports'] = status['streams']
            packet = worker.read_latest()
            if packet is None:
                time.sleep(.01)
                continue
            paired = validate_pair(packet, 'frontal', now=time.monotonic())
            received_times.append(time.monotonic())
            deltas.append(packet.pairing['receive_delta_s'])
            if sample_until is None:
                sample_until = time.monotonic()+seconds
            for view, frame in (('frontal', packet), ('sagittal', paired)):
                record = result['streams'].setdefault(view, dict(sizes=[], latest_received_fps=None, reported_fps=None))
                size = list(frame.image.shape[1::-1])
                if size not in record['sizes']:
                    record['sizes'].append(size)
                record.update(latest_received_fps=frame.received_fps, reported_fps=frame.reported_fps, last_seq=frame.seq)
        result['received_pairs'] = len(received_times)
        result['median_receive_delta_ms'] = median(deltas)*1000 if deltas else None
        result['max_receive_delta_ms'] = max(deltas)*1000 if deltas else None
        result['observed_pair_rate'] = ((len(received_times)-1)/(received_times[-1]-received_times[0])
                                        if len(received_times) > 1 else None)
        result['completed'] = len(received_times) >= 2 and time.monotonic()-received_times[-1] <= 3
        if not result['completed']:
            result['error'] = dict(category='insufficient_or_stale_pairs', view=None)
    except Exception as exc:
        result['error'] = dict(category=type(exc).__name__, view=None)
        print(f'Capture check failed: {type(exc).__name__}: {exc}', flush=True)
    finally:
        result['received_pairs'] = len(received_times)
        result['camera_frames_observed'] = bool(received_times)
        if worker is not None:
            result['pairing_diagnostics'] = worker.diagnostics()
        try:
            camera.stop()
            result['released'] = True
        except Exception as exc:
            result['error'] = dict(category='release_unconfirmed', view=None)
            print(f'Release failed: {exc}', flush=True)
        result['forced_stop'] = bool(getattr(worker, 'forced_stop', False))
        result['completed'] = result['completed'] and result['released']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Only enumerate the selected backend; open no devices')
    parser.add_argument('--backend', choices=('dshow', 'msmf'), default='dshow')
    parser.add_argument('--frontal-index', type=int, help='Explicit CURRENT index from --list, not list row')
    parser.add_argument('--sagittal-index', type=int, help='Explicit CURRENT index from --list, not list row')
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--runs', type=int, choices=(1, 2, 3), default=2, help='Stop and reopen between runs')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fps', type=float, default=30)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory; existing paths are refused')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 30 or not 160 <= args.width <= 4096 or not 120 <= args.height <= 2160 or not 1 <= args.fps <= 60:
        parser.error('Invalid bounded duration or capture settings')
    if not args.list and (args.frontal_index is None or args.sagittal_index is None):
        parser.error('First run --list, then supply both explicit current device indices')
    camera = CameraManager()
    devices = camera.enumerate(700 if args.backend == 'dshow' else 1400)
    evidence = dict(observed_utc=utc_now(), backend=args.backend, enumeration_only=args.list,
                    camera_open_attempted=False, camera_frames_observed=False, image_saved=False, model_loaded=False, runs=[],
                    physical_view_placement_verified=False, human_accuracy_validated=False,
                    evidence_scope='Read-only enumeration or explicitly requested capture/release checks; receive pairing is not exposure synchronization.',
                    devices=[dict(name=d.name, backend=d.backend, current_index=d.index, path_available=bool(d.path),
                                  device_fingerprint=digest(dict(path=d.path, backend=d.backend))[:16]) for d in devices])
    refs = None
    if not args.list:
        refs = {}
        for view, index in (('frontal', args.frontal_index), ('sagittal', args.sagittal_index)):
            matches = [d for d in devices if d.index == index]
            if len(matches) != 1:
                parser.error('Each requested index must resolve to exactly one currently enumerated camera')
            refs[view] = asdict(matches[0])
        make_dual_source(refs, 'frontal', 'TEST')  # Validate both before creating an evidence directory or opening either.
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if args.list:
        evidence['status'] = 'ENUMERATION_ONLY'
    else:
        options = dict(width=args.width, height=args.height, fps=args.fps)
        for run_number in range(1, args.runs+1):
            print(f'Capture/release run {run_number}/{args.runs}: {args.seconds:g} seconds after first pair.', flush=True)
            result = check_pair(camera, refs, args.seconds, options, run_number)
            evidence['runs'].append(result)
            evidence['camera_open_attempted'] = evidence['camera_open_attempted'] or result['camera_open_attempted']
            evidence['camera_frames_observed'] = evidence['camera_frames_observed'] or result['camera_frames_observed']
            if not result['completed']:
                break
        evidence['status'] = 'CAPTURE_RELEASE_CHECK_PASSED' if all(r['completed'] for r in evidence['runs']) and len(evidence['runs']) == args.runs else 'CAPTURE_RELEASE_CHECK_FAILED'
    (output/'result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 1 if evidence['status'] == 'CAPTURE_RELEASE_CHECK_FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
