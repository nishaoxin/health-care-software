"""Target-machine camera enumeration helpers; never open every camera to probe."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from camera_reference import DeviceDescriptor, resolve_saved_device, saved_device_reference


def enumerate_devices(backend_name: str) -> list[DeviceDescriptor]:
    import cv2
    from cv2_enumerate_cameras import enumerate_cameras
    backends = {'dshow': cv2.CAP_DSHOW, 'msmf': cv2.CAP_MSMF,
                'v4l2': cv2.CAP_V4L2, 'avfoundation': cv2.CAP_AVFOUNDATION}
    backend = backends[backend_name]
    return [DeviceDescriptor(str(d.name or ''), str(d.path or ''), int(d.backend), int(d.index),
                             getattr(d, 'vid', None), getattr(d, 'pid', None))
            for d in enumerate_cameras(backend)]


def show_devices(devices: list[DeviceDescriptor]) -> None:
    for row, d in enumerate(devices, 1):
        print(f'{row}. {d.name} | backend={d.backend} | current_index={d.index} | path_available={bool(d.path)}')


def choose_device(backend_name: str, saved_path: Path | None = None) -> DeviceDescriptor:
    devices = enumerate_devices(backend_name)
    if not devices:
        raise RuntimeError('No cameras enumerated. Check the explicit backend and OS permissions.')
    if saved_path is not None:
        saved = json.loads(saved_path.read_text(encoding='utf-8'))
        selected = resolve_saved_device(saved, devices)
    else:
        show_devices(devices)
        print('This number selects a list ENTRY, not an OpenCV device index. Empty input cancels.')
        raw = input('Choose a device by row number: ').strip()
        if not raw.isdecimal() or not 1 <= int(raw) <= len(devices):
            raise RuntimeError('No valid explicit camera selection; nothing will be opened.')
        selected = devices[int(raw) - 1]
    # Re-enumerate before opening; never silently reuse a saved numeric index.
    if selected.path:
        selected = resolve_saved_device(saved_device_reference(selected), enumerate_devices(backend_name))
    return selected
