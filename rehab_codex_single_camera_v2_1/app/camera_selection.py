"""Device selection only: never opens a camera or treats an index as identity."""


def camera_preference(device):
    if not isinstance(device, dict) or not isinstance(device.get('path'), str) or not device['path'].strip():
        raise ValueError('设备缺少唯一标识，请重新选择摄像头。')
    if type(device.get('backend')) is not int or device['backend'] not in (700, 1400):
        raise ValueError('摄像头接口无效，请重新选择。')
    return {key: device.get(key) for key in ('name', 'path', 'backend', 'vid', 'pid')}


def choose_camera(devices, preferred=None, *, allow_single=True):
    """An absent/ambiguous saved path must never fall back to another device."""
    if preferred is not None:
        try:
            preference = camera_preference(preferred)
        except ValueError:
            return None
        matches = [d for d in devices if d.get('path') == preference['path']
                   and d.get('backend') == preference['backend']]
        return matches[0] if len(matches) == 1 else None
    if allow_single:
        import re
        # First launch: ignore explicitly labelled IR/depth and virtual inputs.
        # Names are only a default-selection hint, never a hardware guarantee.
        candidates = [d for d in devices if not re.search(
            r'\b(ir|infrared|depth|virtual)\b|virtualcamera|红外|深度|虚拟',
            str(d.get('name') or '').casefold())]
        if len(candidates) != 1:
            return None
        try:
            camera_preference(candidates[0])
        except ValueError:
            return None
        return choose_camera(devices, candidates[0], allow_single=False)
    return None
